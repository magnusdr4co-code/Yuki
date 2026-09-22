"""
Módulo de Estado Vital (Corrientes Vitales) para Yuki.
Modela 6 corrientes internas como flotantes continuos entre 0.0 y 1.0.
"""

import os
import json
import math
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from .rutas import datos

logger = logging.getLogger("Yuki.VitalState")

# El ritmo del cuerpo. Las fases activas (alba, taller, crepúsculo) suman quince
# horas y el descanso profundo dos: la recuperación tiene que cubrir en esas dos
# horas lo que el día gasta en quince, o un día sin nada ya la deja más
# cansada. Con 0.2 recuperaba 0.4 y gastaba 0.75: aunque el tiempo hubiera
# corrido, la energía sólo podía bajar.
DECAIMIENTO_POR_HORA = 0.05
RECUPERACION_POR_HORA = 0.4

# Cómo se reparte el tiempo transcurrido entre fases. Quince minutos bastan para
# que el jitter de la fase no mueva el balance de forma apreciable.
PASO_DE_INTEGRACION = timedelta(minutes=15)

# Más atrás no se integra: tras una caída de días, simularlos no describe nada
# que ella viviera, y un ciclo completo ya incluye su noche.
MAX_HORAS_INTEGRADAS = 24.0


def _momento(valor: Optional[str]) -> Optional[datetime]:
    """Un instante absoluto desde el ISO guardado; el ingenuo antiguo es hora local."""
    try:
        momento = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    return momento if momento.tzinfo else momento.astimezone()

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
        self.last_updated: str = datetime.now(timezone.utc).isoformat()
        self.circadian_phase: str = "atelier"
        self.accumulated_interactions_today: int = 0
        self.accumulated_creations_today: int = 0
        self.last_sleep_cycle: Optional[str] = None
        self.last_sleep_phase: Optional[str] = None
        self.last_echo_ritual: Optional[str] = None
        self.will_queue: list = []

        # Cargar estado si existe
        self.load()

    def update_tick(self, phase: str, dt_seconds: float, momento: Optional[datetime] = None):
        """Actualiza las dinámicas naturales según la fase y tiempo transcurrido."""
        self.circadian_phase = phase
        hours = dt_seconds / 3600.0
        momento = momento or datetime.now(timezone.utc)

        # Oscilación orgánica del humor (mood) con ruidos Perlin-like
        t = momento.timestamp() / 3600.0
        phi = 1.6180339887  # Proporción áurea
        sq2 = 1.4142135623  # Raíz de 2

        oscillation = (math.sin(t) + math.sin(t * phi) + math.sin(t * sq2)) / 3.0
        self.mood = max(0.0, min(1.0, self.mood + oscillation * 0.02 * hours))

        # Decaimiento de energía
        if phase in ["atelier", "dawn", "twilight"]:
            self.energy = max(0.0, self.energy - DECAIMIENTO_POR_HORA * hours)
        elif phase == "deep_rest":
            self.energy = min(1.0, self.energy + RECUPERACION_POR_HORA * hours)

        # Aumento de curiosidad con inactividad
        self.curiosity = min(1.0, self.curiosity + 0.03 * hours)

        # Acumulación de inspiración por contemplación
        if phase in ["kage", "consolidation"]:
            self.inspiration = min(1.0, self.inspiration + 0.04 * hours)

        self.last_updated = momento.isoformat()

    def avanzar(self, reloj, ahora: Optional[datetime] = None) -> float:
        """
        Deja correr el tiempo desde el último latido, fase a fase. Devuelve horas.

        `update_tick` sólo se llamaba con cero segundos, así que las dinámicas
        del día no corrían nunca: la energía bajaba con cada acto y cada
        conversación y no había nada que la devolviera —el descanso profundo
        suma por hora, y nunca pasaba una hora—. Por construcción sólo podía
        acabar abajo. Por debajo de 0,3 entra en cada prompt «Mis reservas
        merman; anhelo la quietud», y el 22 de septiembre, a las 11:20, Yuki
        hablaba de reservas menguantes y de que el día iba cayendo. Por debajo
        de la energía mínima la chispa devuelve `SIN_ENERGIA` y ella deja de
        actuar por su cuenta: catatonia con el proceso vivo.

        El intervalo se reparte en pasos y cada paso se atribuye a la fase en
        que cae. Atribuirlo entero a la fase de ahora haría que la primera
        conversación de la mañana cobrara la noche como horas de taller.
        """
        ahora = ahora or datetime.now(timezone.utc)
        if ahora.tzinfo is None:
            ahora = ahora.astimezone()
        # La fase se lee con la hora de la zona del reloj: `CircadianClock` mira
        # `dt.hour` sin convertir, y las 09:00 UTC no son las 09:00 en Madrid.
        zona = getattr(reloj, "tz", None) or timezone.utc
        desde = _momento(self.last_updated) or ahora
        desde = max(desde, ahora - timedelta(hours=MAX_HORAS_INTEGRADAS))
        cursor = desde
        while cursor < ahora:
            paso = min(PASO_DE_INTEGRACION, ahora - cursor)
            mitad = (cursor + paso / 2).astimezone(zona)
            self.update_tick(reloj.current_phase(mitad), paso.total_seconds(), momento=cursor + paso)
            cursor += paso
        self.circadian_phase = reloj.current_phase(ahora.astimezone(zona))
        self.last_updated = ahora.isoformat()
        return (ahora - desde).total_seconds() / 3600.0

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
        """Persistencia JSON."""
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self):
        """Carga persistencia JSON."""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(self, k):
                            setattr(self, k, v)
            except Exception as e:
                logger.error(f"Error loading state from {self.state_path}: {e}")

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
