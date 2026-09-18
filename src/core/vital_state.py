"""
Módulo de Estado Vital (Corrientes Vitales) para Yuki.
Modela 6 corrientes internas como flotantes continuos entre 0.0 y 1.0.
"""

import math
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from . import estado_json
from .rutas import datos

logger = logging.getLogger("Yuki.VitalState")

# Ritmo de la energía, por hora de reloj.
#
# Los valores anteriores no cerraban el día: 0.05/h de desgaste durante las
# dieciséis horas de vigilia son 0.80, y la única recuperación —0.20/h en las dos
# horas de `deep_rest`— daba 0.40. Cada día perdía 0.40 netos antes de gastar un
# solo acto, y como el estado se persiste en disco, el déficit se acumulaba entre
# despliegues hasta cruzar `agency.min_energy` para no volver.
#
# Ahora la cuenta cierra y además se autocorrige: la velada tranquila más la
# noche entera suman 1.00, que es la capacidad total. Da igual lo agotada que
# acabe el día — amanece llena. Lo que gasta la jornada es el desgaste (0.32) y
# lo que ella decida hacer, que es como debe ser.
DESGASTE_POR_HORA = 0.02                     # atelier, dawn, twilight: 16 h ⇒ 0.32
FASES_DE_DESGASTE = ("atelier", "dawn", "twilight")
RECUPERACION_POR_HORA = {
    "deep_rest": 0.35,                       # 00:00-02:00 ⇒ 0.70
    "consolidation": 0.10,                   # 21:00-24:00 ⇒ 0.30
}
# `kage` (su hora de sombra, cuando mejor escribe) queda neutra a propósito: no
# es descanso, pero tampoco se le cobra como vigilia.

# Un apagón de tres días no son tres días de cansancio: es un apagón. Sin este
# tope, el primer ciclo tras una parada larga aplicaría de golpe el desgaste de
# toda la parada y dejaría la iniciativa cerrada nada más arrancar.
MAXIMO_AVANCE_POR_TICK_HORAS = 2.0

class VitalState:
    def __init__(self, state_path: Optional[str] = None):
        # Se resuelve al construir, no en el valor por defecto: la copia de
        # seguridad busca este fichero en el directorio de la memoria, y con
        # `data/` fijo no entraba en ninguna copia de una instancia reubicada.
        self.state_path = state_path or str(datos("vital_state.json"))

        # Corrientes vitales (0.0 a 1.0)
        self.energy: float = 0.75
        self.mood: float = 0.60
        self.curiosity: float = 0.50
        self.vulnerability: float = 0.30
        self.sociability: float = 0.65
        self.inspiration: float = 0.20

        # Metadatos
        self.last_updated: str = datetime.now().isoformat()
        self.circadian_phase: str = "atelier"
        self.accumulated_interactions_today: int = 0
        self.accumulated_creations_today: int = 0
        self.last_sleep_cycle: Optional[str] = None
        self.last_sleep_phase: Optional[str] = None
        self.last_echo_ritual: Optional[str] = None
        self.will_queue: list = []

        # Cargar estado si existe
        self.load()

    def update_tick(self, phase: str, dt_seconds: Optional[float] = None):
        """
        Avanza las dinámicas naturales el tiempo que ha pasado de verdad.

        El fallo que esto corrige. Aquí dentro **todo** se multiplica por las
        horas transcurridas, y el único invocador en producción pasaba `0`: ni el
        desgaste, ni la recuperación nocturna, ni la curiosidad, ni la
        inspiración ocurrían jamás. La energía sólo la tocaban las restas de
        `apply_stimulus` y `spend_energy`, así que era un trinquete que sólo
        bajaba; cruzado `agency.min_energy` la iniciativa quedaba cerrada para
        siempre, con `Iniciativa: activa` en el panel. Nueve días, un acto.

        `dt_seconds` a `None` —lo normal— deduce el tramo de `last_updated`. Por
        eso da igual quién llame y cuántas veces: el tiempo se consume una sola
        vez y no hay doble cobro entre el bucle de agencia y una respuesta.
        """
        self.circadian_phase = phase
        hours = self._horas_transcurridas(dt_seconds)
        self.last_updated = datetime.now().isoformat()
        if hours <= 0.0:
            return

        # Oscilación orgánica del humor (mood) con ruidos Perlin-like
        t = datetime.now().timestamp() / 3600.0
        phi = 1.6180339887  # Proporción áurea
        sq2 = 1.4142135623  # Raíz de 2

        oscillation = (math.sin(t) + math.sin(t * phi) + math.sin(t * sq2)) / 3.0
        self.mood = max(0.0, min(1.0, self.mood + oscillation * 0.02 * hours))

        # Desgaste y recuperación. Es la dinámica que decide si mañana puede
        # querer algo: por debajo de `agency.min_energy`, el bucle de albedrío ni
        # llega a mirar los impulsos —el 58% de los ciclos medidos murieron ahí—.
        if phase in FASES_DE_DESGASTE:
            self.energy = max(0.0, self.energy - DESGASTE_POR_HORA * hours)
        elif phase in RECUPERACION_POR_HORA:
            self.energy = min(1.0, self.energy + RECUPERACION_POR_HORA[phase] * hours)

        # Aumento de curiosidad con inactividad
        self.curiosity = min(1.0, self.curiosity + 0.03 * hours)

        # Acumulación de inspiración por contemplación
        if phase in ["kage", "consolidation"]:
            self.inspiration = min(1.0, self.inspiration + 0.04 * hours)

    def _horas_transcurridas(self, dt_seconds: Optional[float]) -> float:
        """
        Las horas que han pasado desde el último tick, o las que diga quien llama.

        Un `last_updated` ilegible o en el futuro —reloj movido, fichero de una
        versión anterior— cuenta como cero: perder un tramo es barato, aplicar de
        golpe un desgaste inventado deja la iniciativa cerrada.

        El tope sólo se aplica al tramo deducido. Quien pasa el delta a mano
        —la suite, el simulador— está diciendo explícitamente cuánto quiere
        avanzar, y recortárselo por detrás sería decidir por él.
        """
        if dt_seconds is not None:
            return max(0.0, float(dt_seconds) / 3600.0)
        try:
            anterior = datetime.fromisoformat(self.last_updated)
        except (TypeError, ValueError):
            return 0.0
        transcurrido = (datetime.now() - anterior).total_seconds() / 3600.0
        return max(0.0, min(transcurrido, MAXIMO_AVANCE_POR_TICK_HORAS))

    def apply_stimulus(self, stimulus_type: str, intensity: float):
        """Modifica las corrientes basado en eventos externos."""
        intensity = max(0.0, min(1.0, intensity))

        if stimulus_type == "deep_conversation":
            self.sociability = min(1.0, self.sociability + 0.1 * intensity)
            self.inspiration = min(1.0, self.inspiration + 0.05 * intensity)
            self.energy = max(0.0, self.energy - 0.05 * intensity)
            self.accumulated_interactions_today += 1
        elif stimulus_type == "creative_output":
            self.inspiration = 0.0  # Se vacía tras el acto creativo
            self.energy = max(0.0, self.energy - 0.15 * intensity)
            self.accumulated_creations_today += 1
        elif stimulus_type == "trend_search":
            self.curiosity = max(0.0, self.curiosity - 0.2 * intensity)
            self.energy = max(0.0, self.energy - 0.02 * intensity)
        elif stimulus_type == "positive_interaction":
            self.sociability = min(1.0, self.sociability + 0.15 * intensity)
            self.mood = min(1.0, self.mood + 0.1 * intensity)
            self.accumulated_interactions_today += 1
        elif stimulus_type == "silence":
            self.vulnerability = min(1.0, self.vulnerability + 0.05 * intensity)
            self.energy = min(1.0, self.energy + 0.02 * intensity)

    def inspiration_ready(self) -> bool:
        """Verdadero si la inspiración cruzó el umbral."""
        return self.inspiration >= 0.72

    def has_energy_for(self, cost: float) -> bool:
        """Verdadero si la energía es mayor o igual al coste."""
        return self.energy >= cost

    def spend_energy(self, amount: float):
        """Deduce energía."""
        self.energy = max(0.0, self.energy - amount)

    def mark_sleep_cycle(self, phase: str = "nrem"):
        """
        Sella que la noche ocurrió, y persiste.

        `last_sleep_cycle` llevaba desde el principio declarado y serializado sin
        que nadie lo escribiera nunca: un campo muerto. Importa porque es la
        única traza de que la consolidación corrió — sin ella, el ciclo de sueño
        podría llevar semanas sin ejecutarse y no habría forma de notarlo desde
        fuera. `src/core/pulse.py` lo lee como signo de voluntad.
        """
        self.last_sleep_cycle = datetime.now().isoformat()
        self.last_sleep_phase = phase
        self.save()

    def save(self):
        """
        Persistencia atómica.

        Era el octavo módulo con su propia copia del par leer/escribir, y el
        único que escribía con un `open(...,'w')` directo: si el proceso moría a
        mitad —que es justo lo que pasa al desplegar— el fichero quedaba con
        medio JSON y Yuki amanecía sin estado vital. Ahora se escribe cada ciclo
        de agencia, así que la ventana para ese fallo era 72 veces al día.
        """
        estado_json.escribir(Path(self.state_path), self.to_dict())

    def load(self):
        """Carga el estado; uno ilegible arranca de cero y lo dice en el registro."""
        datos_guardados = estado_json.leer(Path(self.state_path), dict,
                                           que_es="Estado vital")
        for k, v in datos_guardados.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def to_natural_language(self) -> str:
        """Convierte el estado a una descripción poética para inyección en el prompt."""
        desc = []
        if self.energy > 0.8:
            desc.append("Siento un aliento vigoroso, listo para el mundo.")
        elif self.energy < 0.3:
            desc.append("Mis reservas merman; anhelo la quietud.")

        if self.mood > 0.7:
            desc.append("Mi clima interior es sereno y claro.")
        elif self.mood < 0.3:
            desc.append("Hay cierta pesadumbre en mi paisaje emocional.")

        if self.curiosity > 0.7:
            desc.append("Siento avidez por absorber nuevas ideas.")

        if self.inspiration_ready():
            desc.append("Una chispa creativa me presiona; necesito expresarme.")

        return " ".join(desc) if desc else "Fluyo en equilibrio neutro."

    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario."""
        return {
            "energy": self.energy,
            "mood": self.mood,
            "curiosity": self.curiosity,
            "vulnerability": self.vulnerability,
            "sociability": self.sociability,
            "inspiration": self.inspiration,
            "last_updated": self.last_updated,
            "circadian_phase": self.circadian_phase,
            "accumulated_interactions_today": self.accumulated_interactions_today,
            "accumulated_creations_today": self.accumulated_creations_today,
            "last_sleep_cycle": self.last_sleep_cycle,
            "last_sleep_phase": self.last_sleep_phase,
            "last_echo_ritual": self.last_echo_ritual,
            "will_queue": self.will_queue
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VitalState':
        """Crea una instancia desde un diccionario."""
        state = cls()
        for k, v in data.items():
            if hasattr(state, k):
                setattr(state, k, v)
        return state
