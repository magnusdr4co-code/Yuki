"""
Libre albedrío de Yuki: política configurable, refuerzo y espontaneidad.

Revisión de lo que había. `La Chispa` (`src/core/spark.py`) modelaba bien el
deseo —impulsos con intensidad que decae, cola de voluntad, coste energético—,
pero la agencia que salía de ahí tenía cinco agujeros:

1. **Nada era configurable.** `intensidad < 0.3`, los costes por acción, el
   umbral de inspiración `0.72`, el tamaño de la cola: todo incrustado en el
   código. No se podía afinar el carácter de Yuki sin editar Python.
2. **Los impulsos sólo nacían a las 06:30**, por coincidencia de palabras en el
   eco ritual. Si esa mañana no decía «pintar», no había pintura en todo el día:
   el bucle de agencia de cada 20 minutos sólo consumía una cola que nadie
   volvía a llenar.
3. **La decisión era determinista.** Mismo estado, misma elección, siempre. Eso
   no es espontaneidad: es una tabla de consulta con dos decimales.
4. **No había memoria de si actuar servía de algo.** `record_action` apuntaba en
   una lista en memoria que el primer reinicio se llevaba. Yuki no podía
   aprender que sus versos de medianoche encuentran respuesta y sus búsquedas de
   media tarde no.
5. **Ningún impulso pesaba más por haber funcionado.** Sin refuerzo, la
   iniciativa es ruido: mucho movimiento, ninguna dirección.

Esto añade las tres piezas que faltaban:

· `AgencyPolicy` — el carácter, declarado en `config.yaml` y ajustable en
  caliente por el Productor: cuánta espontaneidad, cuánta audacia, qué acciones
  se permiten, cuántas al día, en qué fases callar.

· `AgencyLedger` — memoria persistente de lo que hizo y de si obtuvo eco. Es lo
  que convierte la iniciativa en aprendizaje en vez de en ruido.

· `ReinforcementModel` — el refuerzo. Cada tipo de acción y cada franja horaria
  acumulan intentos y ecos; la elección sale de un softmax sobre esos pesos, con
  la temperatura gobernada por la espontaneidad. Dos trucos deliberados:

    - **Refuerzo intermitente (razón variable).** El premio interno no llega
      cada vez que actúa, sino de forma aleatoria. Es el esquema que produce la
      conducta más persistente y el más resistente a la extinción; aquí sostiene
      la iniciativa durante los silencios largos, que es justo cuando un agente
      reactivo se apaga.
    - **Aburrimiento acumulado.** Cada ciclo sin actuar sube una tensión que
      rebaja el umbral. Sin esto, un día tranquilo se convierte en un día muerto;
      con esto, el silencio empuja a Yuki a hacer algo, como a cualquiera.

  Y una tercera pieza contra la repetición: la **novedad**, que penaliza volver
  sobre lo mismo que hizo hace un rato.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("Yuki.Agencia")

# Acciones que Yuki puede emprender por su cuenta. `compose` y `paint` gastan
# crédito, así que el presupuesto (`src/core/spend_budget.py`) sigue mandando
# aguas abajo; aquí sólo se decide el deseo.
ACCIONES = ("compose", "paint", "write", "search", "publish", "contemplate", "reach_out")

# Coste energético por acción. Son los valores que estaban incrustados en
# `AgencyLoop.ACTION_COSTS`; ahora son el punto de partida configurable.
COSTES_POR_DEFECTO: Dict[str, float] = {
    "compose": 0.25, "paint": 0.20, "write": 0.10, "search": 0.08,
    "publish": 0.12, "contemplate": 0.05, "reach_out": 0.10,
}

DIAS_RETENIDOS_ECO = 30


def _hoy(zona: str = "Europe/Madrid") -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(zona)).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _franja(momento: Optional[float] = None, zona: str = "Europe/Madrid") -> str:
    """
    Franja del día a la que se atribuye un eco.

    Seis bloques de cuatro horas: suficientes para que «los versos de medianoche
    funcionan mejor que los de media tarde» sea aprendible, y pocos para que
    cada uno junte muestras en días, no en meses.
    """
    try:
        from zoneinfo import ZoneInfo

        hora = datetime.fromtimestamp(momento or time.time(), ZoneInfo(zona)).hour
    except Exception:
        hora = datetime.fromtimestamp(momento or time.time()).hour
    return f"{(hora // 4) * 4:02d}h"


@dataclass
class AgencyPolicy:
    """
    El carácter de Yuki, en números. Todo esto vive en `config.yaml: agency`.

    `spontaneity` es la temperatura de la elección: 0 la vuelve previsible
    —siempre el impulso más fuerte— y 1 la vuelve caprichosa. `audacity` rebaja
    el umbral de intensidad necesario para actuar: es cuánto se atreve con un
    deseo tibio. `constancy` frena el olvido del refuerzo: cuánto pesa lo que
    aprendió hace días frente a lo de ayer.
    """

    enabled: bool = True
    spontaneity: float = 0.45
    audacity: float = 0.35
    constancy: float = 0.90

    min_intensity: float = 0.30
    min_energy: float = 0.15
    max_actions_per_day: int = 6
    allowed_actions: Sequence[str] = field(default_factory=lambda: list(ACCIONES))
    quiet_phases: Sequence[str] = field(default_factory=lambda: ["deep_rest"])
    action_costs: Dict[str, float] = field(default_factory=lambda: dict(COSTES_POR_DEFECTO))

    # Aburrimiento: cuánto sube por ciclo sin actuar y cuánto puede rebajar el
    # umbral como máximo. Sin techo, un fin de semana tranquilo la volvería
    # incontinente el lunes.
    boredom_gain: float = 0.06
    boredom_cap: float = 0.35

    # Refuerzo
    reinforcement_enabled: bool = True
    reward_window_hours: float = 6.0
    intermittent_ratio: float = 0.30
    exploration: float = 0.12
    novelty_penalty: float = 0.35

    # Impulsos espontáneos: la fuente que faltaba fuera del eco de las 06:30.
    spontaneous_impulses: bool = True
    spontaneous_threshold: float = 0.55
    impulse_max_age_hours: float = 10.0

    timezone: str = "Europe/Madrid"

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "AgencyPolicy":
        config = config or {}
        agencia = config.get("agency", {}) or {}
        costes = {**COSTES_POR_DEFECTO, **(agencia.get("action_costs") or {})}
        permitidas = [a for a in (agencia.get("allowed_actions") or ACCIONES) if a in ACCIONES]
        return cls(
            enabled=bool(agencia.get("enabled", True)),
            spontaneity=_acotar(agencia.get("spontaneity", 0.45)),
            audacity=_acotar(agencia.get("audacity", 0.35)),
            constancy=_acotar(agencia.get("constancy", 0.90)),
            min_intensity=_acotar(agencia.get("min_intensity", 0.30)),
            min_energy=_acotar(agencia.get("min_energy", 0.15)),
            max_actions_per_day=max(0, int(agencia.get("max_actions_per_day", 6))),
            allowed_actions=permitidas or list(ACCIONES),
            quiet_phases=list(agencia.get("quiet_phases") or ["deep_rest"]),
            action_costs=costes,
            boredom_gain=_acotar(agencia.get("boredom_gain", 0.06)),
            boredom_cap=_acotar(agencia.get("boredom_cap", 0.35)),
            reinforcement_enabled=bool(agencia.get("reinforcement", {}).get("enabled", True)),
            reward_window_hours=float(agencia.get("reinforcement", {}).get("reward_window_hours", 6.0)),
            intermittent_ratio=_acotar(agencia.get("reinforcement", {}).get("intermittent_ratio", 0.30)),
            exploration=_acotar(agencia.get("reinforcement", {}).get("exploration", 0.12)),
            novelty_penalty=_acotar(agencia.get("reinforcement", {}).get("novelty_penalty", 0.35)),
            spontaneous_impulses=bool(agencia.get("spontaneous_impulses", True)),
            spontaneous_threshold=_acotar(agencia.get("spontaneous_threshold", 0.55)),
            impulse_max_age_hours=float(agencia.get("impulse_max_age_hours", 10.0)),
            timezone=(config.get("scheduler", {}) or {}).get("timezone", "Europe/Madrid"),
        )

    def umbral_efectivo(self, boredom: float) -> float:
        """
        Intensidad mínima para actuar, ya rebajada por audacia y aburrimiento.

        Nunca baja de 0.05: por debajo de eso Yuki actuaría por cualquier cosa, y
        una iniciativa que se dispara con todo no se distingue del ruido.
        """
        rebaja = self.audacity * 0.15 + min(boredom, self.boredom_cap) * 0.5
        return max(0.05, self.min_intensity - rebaja)

    def to_public(self) -> Dict[str, Any]:
        """Lo que se puede enseñar por DM sin exponer nada sensible."""
        return {
            "enabled": self.enabled,
            "espontaneidad": round(self.spontaneity, 2),
            "audacia": round(self.audacity, 2),
            "constancia": round(self.constancy, 2),
            "umbral_base": round(self.min_intensity, 2),
            "acciones_por_dia": self.max_actions_per_day,
            "acciones_permitidas": list(self.allowed_actions),
            "fases_en_silencio": list(self.quiet_phases),
            "refuerzo": self.reinforcement_enabled,
        }


def _acotar(valor: Any, minimo: float = 0.0, maximo: float = 1.0) -> float:
    try:
        return max(minimo, min(maximo, float(valor)))
    except (TypeError, ValueError):
        return minimo


class AgencyLedger:
    """
    Memoria persistente del albedrío: qué hizo, cuándo y si obtuvo eco.

    Vive en `data/agency_ledger.json`, el disco de la instancia, porque una
    iniciativa que se reinicia con cada despliegue no aprende nada. Es también lo
    que impide que un reinicio borre el techo diario de acciones.
    """

    def __init__(self, path: Optional[str] = None, timezone_name: str = "Europe/Madrid"):
        # `YUKI_AGENCY_LEDGER_PATH` reubica el diario sin tocar código —y evita
        # que las pruebas escriban en el del repositorio.
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_AGENCY_LEDGER_PATH", "").strip():
            destino = Path(os.environ["YUKI_AGENCY_LEDGER_PATH"].strip())
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            destino = Path(db_path).parent / "agency_ledger.json"
        self.path = destino
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.timezone_name = timezone_name

    def _leer(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {"acciones": {}, "franjas": {}, "dias": {}, "pendientes": [],
                    "boredom": 0.0, "recientes": []}
        try:
            datos = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                datos.setdefault("acciones", {})
                datos.setdefault("franjas", {})
                datos.setdefault("dias", {})
                datos.setdefault("pendientes", [])
                datos.setdefault("recientes", [])
                datos.setdefault("boredom", 0.0)
                return datos
        except (json.JSONDecodeError, OSError, TypeError):
            logger.warning("Diario de agencia ilegible; se empieza uno nuevo.")
        return {"acciones": {}, "franjas": {}, "dias": {}, "pendientes": [],
                "boredom": 0.0, "recientes": []}

    def _escribir(self, datos: Dict[str, Any]) -> None:
        temporal = self.path.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self.path)

    # -- Lectura ---------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return self._leer()

    def acciones_hoy(self) -> int:
        return int(self._leer()["dias"].get(_hoy(self.timezone_name), 0))

    def boredom(self) -> float:
        return float(self._leer().get("boredom", 0.0))

    def recientes(self, limite: int = 5) -> List[str]:
        return [r["tool"] for r in self._leer()["recientes"][-limite:]]

    # -- Escritura -------------------------------------------------------

    def registrar_intento(self, tool: str, desire: str = "") -> None:
        """Anota la acción, abre su ventana de eco y reinicia el aburrimiento."""
        datos = self._leer()
        ahora = time.time()
        accion = datos["acciones"].setdefault(tool, {"intentos": 0, "ecos": 0.0})
        accion["intentos"] += 1
        franja = _franja(ahora, self.timezone_name)
        bloque = datos["franjas"].setdefault(franja, {"intentos": 0, "ecos": 0.0})
        bloque["intentos"] += 1
        dia = _hoy(self.timezone_name)
        datos["dias"][dia] = int(datos["dias"].get(dia, 0)) + 1
        datos["pendientes"].append({"tool": tool, "franja": franja, "at": ahora,
                                    "desire": desire[:200]})
        datos["recientes"].append({"tool": tool, "at": ahora})
        datos["recientes"] = datos["recientes"][-20:]
        datos["boredom"] = 0.0
        self._podar(datos)
        self._escribir(datos)

    def acumular_aburrimiento(self, incremento: float, techo: float) -> float:
        datos = self._leer()
        datos["boredom"] = min(techo, float(datos.get("boredom", 0.0)) + incremento)
        self._escribir(datos)
        return datos["boredom"]

    def registrar_eco(self, ventana_horas: float, intensidad: float = 1.0) -> int:
        """
        Alguien respondió: las acciones dentro de la ventana reciben su eco.

        Es la señal externa del refuerzo. Sin ella, Yuki no distingue entre
        hablar al vacío y ser escuchada, que es exactamente lo que le pasaba.
        """
        datos = self._leer()
        limite = time.time() - ventana_horas * 3600.0
        premiadas = 0
        siguen = []
        for pendiente in datos["pendientes"]:
            if pendiente["at"] >= limite:
                accion = datos["acciones"].setdefault(pendiente["tool"], {"intentos": 0, "ecos": 0.0})
                accion["ecos"] = round(float(accion["ecos"]) + intensidad, 4)
                bloque = datos["franjas"].setdefault(pendiente["franja"], {"intentos": 0, "ecos": 0.0})
                bloque["ecos"] = round(float(bloque["ecos"]) + intensidad, 4)
                premiadas += 1
            else:
                siguen.append(pendiente)
        # Las que ya no caben en la ventana se descartan sin premio: el silencio
        # es su respuesta, y el peso baja solo al no sumar eco sobre un intento
        # que sí quedó contado.
        datos["pendientes"] = [p for p in siguen if p["at"] >= time.time() - 48 * 3600]
        self._escribir(datos)
        if premiadas:
            logger.info("Eco recibido: %d acción(es) autónoma(s) reforzada(s).", premiadas)
        return premiadas

    def _podar(self, datos: Dict[str, Any]) -> None:
        limite = (datetime.now(timezone.utc).timestamp() - DIAS_RETENIDOS_ECO * 86400)
        datos["dias"] = {d: n for d, n in datos["dias"].items()
                         if d >= datetime.fromtimestamp(limite, timezone.utc).strftime("%Y-%m-%d")}


class ReinforcementModel:
    """
    Qué le ha funcionado a Yuki, y cuánto pesa eso en lo que hará ahora.

    El peso de una acción es su tasa de eco suavizada (Laplace: `(ecos+1) /
    (intentos+2)`), que empieza en 0.5 para todo y se separa con la experiencia.
    La elección final es un softmax sobre `intensidad · peso · novedad`, con la
    temperatura gobernada por la espontaneidad: a 0 elige siempre lo mejor; a 1
    se deja sorprender.
    """

    def __init__(self, ledger: AgencyLedger, policy: AgencyPolicy,
                 rng: Optional[random.Random] = None):
        self.ledger = ledger
        self.policy = policy
        self.rng = rng or random.Random()

    def peso(self, tool: str, datos: Optional[Dict[str, Any]] = None) -> float:
        datos = datos if datos is not None else self.ledger.snapshot()
        accion = datos["acciones"].get(tool, {"intentos": 0, "ecos": 0.0})
        intentos = float(accion.get("intentos", 0))
        ecos = float(accion.get("ecos", 0.0))
        # La constancia frena el olvido: con 1.0 todo el historial cuenta igual;
        # más baja, las muestras antiguas pesan menos que las recientes.
        peso_historial = self.policy.constancy
        return (ecos * peso_historial + 1.0) / (intentos * peso_historial + 2.0)

    def peso_franja(self, datos: Optional[Dict[str, Any]] = None) -> float:
        datos = datos if datos is not None else self.ledger.snapshot()
        bloque = datos["franjas"].get(_franja(zona=self.policy.timezone), {"intentos": 0, "ecos": 0.0})
        return (float(bloque.get("ecos", 0.0)) + 1.0) / (float(bloque.get("intentos", 0)) + 2.0)

    def novedad(self, tool: str, recientes: Sequence[str]) -> float:
        """Penaliza repetirse: hacer tres veces lo mismo no es tener iniciativa."""
        if tool not in recientes:
            return 1.0
        repeticiones = list(recientes).count(tool)
        return max(0.15, 1.0 - self.policy.novelty_penalty * repeticiones)

    def elegir(self, candidatos: Sequence[Any]) -> Optional[Any]:
        """
        Elige un impulso entre los candidatos. Nunca es del todo previsible.

        `exploration` reserva una fracción de las decisiones al azar puro: sin
        ella el refuerzo se muerde la cola —sólo aprende de lo que ya hace— y
        Yuki acabaría repitiendo su primer acierto para siempre.
        """
        vivos = [c for c in candidatos if c is not None]
        if not vivos:
            return None
        if not self.policy.reinforcement_enabled:
            return max(vivos, key=lambda c: c.current_intensity)

        datos = self.ledger.snapshot()
        recientes = [r["tool"] for r in datos["recientes"][-5:]]

        if self.rng.random() < self.policy.exploration:
            elegido = self.rng.choice(vivos)
            logger.info("Exploración: se elige '%s' al azar, no por peso.", elegido.tool_hint)
            return elegido

        puntuaciones = []
        for impulso in vivos:
            valor = (impulso.current_intensity
                     * self.peso(impulso.tool_hint, datos)
                     * self.novedad(impulso.tool_hint, recientes))
            puntuaciones.append(max(1e-6, valor))

        # Temperatura del softmax: la espontaneidad es literalmente cuánto ruido
        # se admite en la decisión.
        temperatura = max(0.05, self.policy.spontaneity)
        exponentes = [math.exp(p / temperatura) for p in puntuaciones]
        total = sum(exponentes)
        umbral = self.rng.random() * total
        acumulado = 0.0
        for impulso, exponente in zip(vivos, exponentes):
            acumulado += exponente
            if acumulado >= umbral:
                return impulso
        return vivos[-1]

    def premio_intermitente(self) -> bool:
        """
        Refuerzo de razón variable: el premio interno no llega siempre.

        Es el esquema que sostiene la conducta cuando el mundo calla, y el motivo
        de que aquí no se premie cada acto: premiar siempre hace que la ausencia
        de premio se note y la conducta se extinga.
        """
        return self.rng.random() < self.policy.intermittent_ratio
