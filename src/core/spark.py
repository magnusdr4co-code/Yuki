"""
Módulo La Chispa (The Spark) para Yuki.
Transforma a Yuki de un agente reactivo en un eco auto-propagante.
"""

import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger("Yuki.Spark")

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
    
    def __init__(self, will_queue: WillQueue, vital_state_ref: Any):
        self.will_queue = will_queue
        self.vital_state = vital_state_ref
        self.actions_log: List[dict] = []
    
    def evaluate(self) -> Optional[Impulse]:
        """Evalúa la cola de voluntad y decide si actuar."""
        self.will_queue.prune_expired()
        impulse = self.will_queue.get_strongest()
        
        if impulse is None:
            return None
            
        if impulse.current_intensity < 0.3:
            return None
            
        cost = self.ACTION_COSTS.get(impulse.tool_hint, 0.10)
        
        if not getattr(self.vital_state, 'has_energy_for', lambda c: True)(cost):
            return None
            
        return impulse
    
    def record_action(self, impulse: Impulse, result: dict):
        """Registra que una acción autónoma fue tomada."""
        self.will_queue.fulfill(impulse)
        
        cost = self.ACTION_COSTS.get(impulse.tool_hint, 0.10)
        if hasattr(self.vital_state, 'spend_energy'):
            self.vital_state.spend_energy(cost)
            
        if impulse.tool_hint in ('compose', 'paint', 'write') and hasattr(self.vital_state, 'apply_stimulus'):
            self.vital_state.apply_stimulus('creative_output', 0.5)
            
        self.actions_log.append({
            'source': 'autonomous_will',
            'impulse_source': impulse.source,
            'tool_hint': impulse.tool_hint,
            'desire': impulse.desire,
            'timestamp': time.time(),
            'result_summary': str(result.get('status', 'completed'))
        })
        logger.info(f"Acción registrada: {impulse.tool_hint} - {impulse.desire}")
    
    def get_autonomy_ratio(self) -> float:
        """Ratio de acciones autónomas vs total. Mide cuánta 'vida' tiene Yuki."""
        if not self.actions_log:
            return 0.0
        return min(1.0, len(self.actions_log) / 100.0)
