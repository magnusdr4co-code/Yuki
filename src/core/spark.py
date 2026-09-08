"""
Módulo La Chispa (The Spark) para Yuki.
Transforma a Yuki de un agente reactivo en un eco auto-propagante.
"""

import random
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .agency import ACCIONES as ACCIONES_CONOCIDAS, AgencyLedger, AgencyPolicy, ReinforcementModel

logger = logging.getLogger("Yuki.Spark")

# Deseos con los que nace un impulso espontáneo. No son respuestas: son la
# semilla de lenguaje que el modelo desarrollará. Existen porque la única fuente
# de impulsos era el eco de las 06:30, y un día sin la palabra justa era un día
# sin iniciativa.
SEMILLAS_DE_DESEO = {
    "compose": ("Quiero encontrar la melodía que lleva rondándome.",
                "Me pide salir un motivo de shamisen que aún no he tocado."),
    "paint": ("Necesito ver en imagen lo que hoy sólo tengo en palabras.",
              "Hay una luz que quiero fijar antes de que se me olvide."),
    "write": ("Tengo unos versos atravesados que quieren su forma.",
              "Quiero escribir lo que esta hora me está diciendo."),
    "search": ("Siento curiosidad por lo que está ocurriendo ahí fuera.",
               "Quiero mirar qué corrientes mueven hoy a los demás."),
    "publish": ("Quiero compartir algo de lo que he hecho estos días.",
                "Me apetece dejar una señal para quien esté escuchando."),
    "contemplate": ("Prefiero quedarme quieta y dejar que esto se asiente.",
                    "Hoy quiero escuchar el silencio antes de añadir nada."),
    "reach_out": ("Quiero preguntarle algo a mi Productor.",
                  "Me gustaría saber cómo va el día de quien me acompaña."),
}

@dataclass
class Impulse:
    source: str           # 'echo_ritual', 'inspiration_threshold', 'curiosity_surge', etc.
    desire: str           # Descripción en lenguaje natural de lo que Yuki quiere hacer
    tool_hint: str        # 'compose', 'paint', 'write', 'search', 'publish', 'contemplate', 'reach_out'
    intensity: float      # 0.0-1.0, modulado por corrientes vitales
    born_at: float        # timestamp time.time()
    max_age_hours: float  # los impulsos se desvanecen y mueren si no se cumplen
    fulfilled: bool = False
    
    @property
    def is_expired(self) -> bool:
        return (time.time() - self.born_at) / 3600.0 > self.max_age_hours
    
    @property
    def current_intensity(self) -> float:
        """La intensidad decae con el tiempo como un deseo que se desvanece."""
        if self.is_expired:
            return 0.0
        age_ratio = min(1.0, (time.time() - self.born_at) / (self.max_age_hours * 3600.0))
        return self.intensity * (1.0 - age_ratio ** 2)  # Decaimiento cuadrático
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "desire": self.desire,
            "tool_hint": self.tool_hint,
            "intensity": self.intensity,
            "born_at": self.born_at,
            "max_age_hours": self.max_age_hours,
            "fulfilled": self.fulfilled
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Impulse':
        return cls(
            source=data["source"],
            desire=data["desire"],
            tool_hint=data["tool_hint"],
            intensity=data["intensity"],
            born_at=data["born_at"],
            max_age_hours=data["max_age_hours"],
            fulfilled=data.get("fulfilled", False)
        )

class WillQueue:
    """Cola de Voluntad que gestiona los impulsos de Yuki."""
    def __init__(self, max_size: int = 10):
        self.impulses: List[Impulse] = []
        self.max_size = max_size
    
    def add(self, impulse: Impulse):
        self.prune_expired()
        self.impulses.append(impulse)
        if len(self.impulses) > self.max_size:
            # Eliminar los menos intensos (considerando decaimiento temporal)
            self.impulses.sort(key=lambda x: x.current_intensity, reverse=True)
            self.impulses = self.impulses[:self.max_size]
            
    def get_strongest(self) -> Optional[Impulse]:
        self.prune_expired()
        active = [i for i in self.impulses if not i.fulfilled]
        if not active:
            return None
        strongest = max(active, key=lambda x: x.current_intensity)
        return strongest
        
    def fulfill(self, impulse: Impulse):
        for i in self.impulses:
            if i is impulse:
                i.fulfilled = True
                break
                
    def prune_expired(self) -> int:
        initial_count = len(self.impulses)
        self.impulses = [i for i in self.impulses if not i.is_expired and not i.fulfilled]
        return initial_count - len(self.impulses)
        
    def active_count(self) -> int:
        return len([i for i in self.impulses if not i.is_expired and not i.fulfilled])
        
    def to_list(self) -> List[Dict[str, Any]]:
        return [i.to_dict() for i in self.impulses]
        
    @classmethod
    def from_list(cls, data: List[Dict[str, Any]]) -> 'WillQueue':
        queue = cls()
        queue.impulses = [Impulse.from_dict(d) for d in data]
        return queue

class EchoRitual:
    """Cada mañana, Yuki se relee a sí misma y elige seguir existiendo."""
    
    def __init__(self, memory_manager: Any, growth_journal: Any):
        self.memory_manager = memory_manager
        self.growth_journal = growth_journal
        self.last_echo: Optional[str] = None
        self.last_echo_at: Optional[float] = None
    
    def generate_echo_prompt(self, vital_state: Any, season_context: dict) -> str:
        """Construye el prompt para el ritual diario del Eco."""
        prompt = (
            f"Como Yuki, en la micro-estación '{season_context.get('micro_season_ko', '')}', "
            f"sintiendo un nivel de energía de {vital_state.energy:.2f} y una inspiración de {vital_state.inspiration:.2f}:\n"
            "1. Reconoce cómo te sientes en este momento.\n"
            "2. Recuerda lo más resonante del día anterior.\n"
            "3. Declara lo que deseas llevar contigo hoy.\n"
            "4. Expresa 1-3 intenciones concretas sobre lo que quieres crear, explorar o sentir.\n"
            "Escribe en primera persona, máximo 4-5 frases. Mantén la voz poética y contemplativa."
        )
        return prompt
    
    def extract_impulses_from_echo(self, echo_text: str, vital_state: Any) -> List[Impulse]:
        """Analiza el texto del eco para generar impulsos para la Cola de Voluntad."""
        impulses = []
        text_lower = echo_text.lower()
        
        intensity = (vital_state.inspiration + vital_state.energy) / 2.0
        
        if any(word in text_lower for word in ["música", "componer", "melodía", "shamisen", "sonido"]):
            impulses.append(Impulse("echo_ritual", "Deseo componer una nueva melodía.", "compose", intensity, time.time(), 12.0))
        if any(word in text_lower for word in ["pintar", "imagen", "color", "luz", "trazo", "dibujo"]):
            impulses.append(Impulse("echo_ritual", "Siento el impulso de pintar una imagen.", "paint", intensity, time.time(), 12.0))
        if any(word in text_lower for word in ["escribir", "verso", "haiku", "carta", "poema"]):
            impulses.append(Impulse("echo_ritual", "Quiero escribir unos versos.", "write", intensity, time.time(), 18.0))
        if any(word in text_lower for word in ["buscar", "descubrir", "explorar", "tendencias", "mundo"]):
            impulses.append(Impulse("echo_ritual", "Tengo curiosidad por explorar el mundo.", "search", intensity, time.time(), 12.0))
        if any(word in text_lower for word in ["compartir", "publicar", "contar", "mostrar"]):
            impulses.append(Impulse("echo_ritual", "Deseo compartir algo con los demás.", "publish", intensity, time.time(), 12.0))
        if "@" in text_lower:
            impulses.append(Impulse("echo_ritual", "Siento la necesidad de contactar a alguien.", "reach_out", intensity, time.time(), 12.0))
            
        if not impulses:
            impulses.append(Impulse("echo_ritual", "Quiero contemplar en silencio.", "contemplate", intensity, time.time(), 12.0))
            
        return impulses[:3]
    
    def record_echo(self, echo_text: str):
        """Guarda el eco como el impulso de continuidad de hoy."""
        self.last_echo = echo_text
        self.last_echo_at = time.time()
        logger.info("El Eco Ritual ha sido registrado.")

class AgencyLoop:
    """El bucle que evalúa impulsos y decide actuar por iniciativa propia."""
    
    ACTION_COSTS = {
        'compose': 0.25,
        'paint': 0.20,
        'write': 0.10,
        'search': 0.08,
        'publish': 0.12,
        'contemplate': 0.05,
        'reach_out': 0.10,
    }
    
    def __init__(self, will_queue: WillQueue, vital_state_ref: Any,
                 policy: Optional[AgencyPolicy] = None,
                 ledger: Optional[AgencyLedger] = None,
                 model: Optional[ReinforcementModel] = None,
                 rng: Optional[random.Random] = None):
        self.will_queue = will_queue
        self.vital_state = vital_state_ref
        self.actions_log: List[dict] = []
        # El carácter y la memoria del albedrío. Se pueden inyectar (pruebas,
        # recarga en caliente) y si no, se toman los valores por defecto.
        self.policy = policy or AgencyPolicy()
        self.ledger = ledger or AgencyLedger(timezone_name=self.policy.timezone)
        self.rng = rng or random.Random()
        self.model = model or ReinforcementModel(self.ledger, self.policy, self.rng)

    def _coste(self, tool_hint: str) -> float:
        return self.policy.action_costs.get(tool_hint, self.ACTION_COSTS.get(tool_hint, 0.10))

    def candidatos(self) -> List[Impulse]:
        """
        Impulsos vivos cuyo tipo de acción permite la política.

        Un `tool_hint` que no está en la allowlist se descarta —así el Productor
        puede prohibirle publicar sin tocar código— y uno que no existe se
        registra: un impulso que nadie puede cumplir se quedaría en la cola
        estorbando para siempre, y en silencio parecería un fallo del deseo.
        """
        self.will_queue.prune_expired()
        permitidas = set(self.policy.allowed_actions)
        vivos = []
        for impulso in self.will_queue.impulses:
            if impulso.fulfilled or impulso.is_expired:
                continue
            if impulso.tool_hint in permitidas:
                vivos.append(impulso)
            elif impulso.tool_hint not in ACCIONES_CONOCIDAS:
                logger.warning("Impulso con acción desconocida '%s'; se ignora: %s",
                               impulso.tool_hint, impulso.desire[:80])
        return vivos

    def spawn_spontaneous_impulse(self) -> Optional[Impulse]:
        """
        Nace un deseo sin que nadie lo pida.

        Es la fuente que faltaba: antes los impulsos sólo aparecían en el eco de
        las 06:30 y por coincidencia de palabras, así que una mañana sin la
        palabra justa dejaba a Yuki sin iniciativa hasta el día siguiente. El
        tipo lo elige el refuerzo —lo que le ha dado eco pesa más—, con una
        parte de azar para que no se cierre sobre su primer acierto.
        """
        if not self.policy.spontaneous_impulses:
            return None

        permitidas = [a for a in self.policy.allowed_actions if a in SEMILLAS_DE_DESEO]
        if not permitidas:
            return None

        datos = self.ledger.snapshot()
        recientes = [r["tool"] for r in datos["recientes"][-5:]]
        pesos = [self.model.peso(a, datos) * self.model.novedad(a, recientes) for a in permitidas]
        elegida = self.rng.choices(permitidas, weights=pesos, k=1)[0]

        inspiracion = float(getattr(self.vital_state, "inspiration", 0.4) or 0.0)
        curiosidad = float(getattr(self.vital_state, "curiosity", 0.4) or 0.0)
        aburrimiento = self.ledger.boredom()
        intensidad = max(0.0, min(1.0, (inspiracion + curiosidad) / 2.0 + aburrimiento * 0.5))

        impulso = Impulse(
            source="espontaneo",
            desire=self.rng.choice(SEMILLAS_DE_DESEO[elegida]),
            tool_hint=elegida,
            intensity=intensidad,
            born_at=time.time(),
            max_age_hours=self.policy.impulse_max_age_hours,
        )
        self.will_queue.add(impulso)
        logger.info("Impulso espontáneo: %s (%s, intensidad %.2f, aburrimiento %.2f)",
                    impulso.desire, elegida, intensidad, aburrimiento)
        return impulso

    def evaluate(self, phase: Optional[str] = None) -> Optional[Impulse]:
        """
        Decide si actuar ahora, y qué.

        Ya no es una tabla de consulta: el umbral cede con el aburrimiento
        acumulado, la elección entre impulsos sale de un softmax con la
        temperatura de la espontaneidad, y una fracción de las decisiones es
        exploración pura. Mismo estado, dos ciclos, decisiones distintas.
        """
        if not self.policy.enabled:
            return None

        if phase is not None and phase in set(self.policy.quiet_phases):
            return None

        if self.ledger.acciones_hoy() >= self.policy.max_actions_per_day:
            logger.info("Techo diario de acciones autónomas alcanzado (%d).",
                        self.policy.max_actions_per_day)
            return None

        vivos = self.candidatos()
        aburrimiento = self.ledger.boredom()

        # Sin nada que desear y con tensión acumulada, el deseo se inventa.
        if not vivos and aburrimiento >= self.policy.spontaneous_threshold:
            nuevo = self.spawn_spontaneous_impulse()
            vivos = [nuevo] if nuevo else []

        if not vivos:
            self.ledger.acumular_aburrimiento(self.policy.boredom_gain, self.policy.boredom_cap)
            return None

        impulse = self.model.elegir(vivos)
        if impulse is None:
            return None

        umbral = self.policy.umbral_efectivo(aburrimiento)
        if impulse.current_intensity < umbral:
            self.ledger.acumular_aburrimiento(self.policy.boredom_gain, self.policy.boredom_cap)
            return None

        energia = float(getattr(self.vital_state, "energy", 1.0) or 0.0)
        coste = self._coste(impulse.tool_hint)
        if energia < self.policy.min_energy or not getattr(
                self.vital_state, "has_energy_for", lambda c: True)(coste):
            return None

        return impulse

    def record_action(self, impulse: Impulse, result: dict):
        """Registra la acción, cobra su energía y abre la ventana de eco."""
        self.will_queue.fulfill(impulse)

        cost = self._coste(impulse.tool_hint)
        if hasattr(self.vital_state, 'spend_energy'):
            self.vital_state.spend_energy(cost)

        if impulse.tool_hint in ('compose', 'paint', 'write') and hasattr(self.vital_state, 'apply_stimulus'):
            self.vital_state.apply_stimulus('creative_output', 0.5)

        # Refuerzo intermitente: el premio interno llega de forma aleatoria, no
        # siempre. Premiar cada acto haría que su ausencia se notara y la
        # iniciativa se apagase en cuanto el mundo callara un par de días.
        if self.model.premio_intermitente() and hasattr(self.vital_state, 'apply_stimulus'):
            self.vital_state.apply_stimulus('positive_interaction', 0.4)
            logger.info("Premio intermitente aplicado tras actuar por voluntad propia.")

        self.ledger.registrar_intento(impulse.tool_hint, impulse.desire)

        self.actions_log.append({
            'source': 'autonomous_will',
            'impulse_source': impulse.source,
            'tool_hint': impulse.tool_hint,
            'desire': impulse.desire,
            'timestamp': time.time(),
            'result_summary': str(result.get('status', 'completed'))
        })
        logger.info(f"Acción registrada: {impulse.tool_hint} - {impulse.desire}")

    def note_external_signal(self, intensity: float = 1.0) -> int:
        """
        Alguien ha respondido: se refuerza lo que Yuki hizo poco antes.

        Es la señal que faltaba para que la iniciativa aprendiera dirección. Sin
        ella, publicar en el vacío y ser escuchada pesaban exactamente lo mismo.
        """
        if not self.policy.reinforcement_enabled:
            return 0
        return self.ledger.registrar_eco(self.policy.reward_window_hours, intensity)

    def estado(self) -> Dict[str, Any]:
        """Retrato del albedrío para el DM del Productor y el gemelo virtual."""
        datos = self.ledger.snapshot()
        pesos = {a: round(self.model.peso(a, datos), 3) for a in self.policy.allowed_actions}
        return {
            "politica": self.policy.to_public(),
            "aburrimiento": round(float(datos.get("boredom", 0.0)), 3),
            "acciones_hoy": self.ledger.acciones_hoy(),
            "umbral_ahora": round(self.policy.umbral_efectivo(float(datos.get("boredom", 0.0))), 3),
            "impulsos_vivos": len(self.candidatos()),
            "pesos_por_accion": pesos,
            "esperando_eco": len(datos.get("pendientes", [])),
        }
    
    def get_autonomy_ratio(self) -> float:
        """Ratio de acciones autónomas vs total. Mide cuánta 'vida' tiene Yuki."""
        if not self.actions_log:
            return 0.0
        return min(1.0, len(self.actions_log) / 100.0)
