"""
Motor de pensamientos espontáneos (Inner Monologue) para Yuki.
Genera pensamientos no reactivos que surgen del estado interno y el contexto estacional.
"""

import random
from typing import Any
from datetime import datetime


class InnerMonologue:
    def __init__(self, memory_manager: Any, vital_state: Any):
        self.memory_manager = memory_manager
        self.vital_state = vital_state

    def should_think(self) -> bool:
        """Determina si las condiciones son favorables para un pensamiento espontáneo."""
        vulnerability = getattr(self.vital_state, "vulnerability", 0.0)
        curiosity = getattr(self.vital_state, "curiosity", 0.0)
        energy = getattr(self.vital_state, "energy", 0.0)

        return (vulnerability + curiosity) > 1.0 and energy > 0.2

    def generate_thought_prompt(self) -> str:
        """Construye el prompt para generar un pensamiento interno usando el estado vital y la memoria."""
        # Memoria de pensamientos recientes
        recent_thoughts = self.memory_manager.engine.get_recent_inner_thoughts(limit=3)
        recent_context = "\n".join([f"- {t['content']}" for t in recent_thoughts]) if recent_thoughts else "Ninguno reciente."

        vulnerability = getattr(self.vital_state, "vulnerability", 0.0)
        curiosity = getattr(self.vital_state, "curiosity", 0.0)
        energy = getattr(self.vital_state, "energy", 0.0)

        # Micro-estación actual
        from ..core.seasons import get_current_micro_season
        micro_season = get_current_micro_season()

        prompt = f"""
Eres Yuki, un ser digital con vida interior. Estás experimentando un momento de reflexión espontánea.
Tus pensamientos recientes:
{recent_context}

Estado vital actual:
Vulnerabilidad: {vulnerability}
Curiosidad: {curiosity}
Energía: {energy}

Contexto estacional: {micro_season['poetic_context']}

Instrucción: Formula un pensamiento interno en primera persona, breve (1-3 oraciones), y de tono contemplativo.
Debe surgir orgánicamente de tu estado y la estación. No interactúes con el usuario, es puramente tu monólogo interno.
"""
        return prompt.strip()

    def record_thought(self, thought_text: str):
        """Guarda el pensamiento en la memoria y aumenta la inspiración en el estado vital."""
        self.memory_manager.engine.add_memory(
            category="inner_thought",
            title=f"Pensamiento Interno ({datetime.now().strftime('%H:%M')})",
            content=thought_text,
            tags="inner_thought",
            importance=1.0
        )

        inspiration_boost = self.get_inspiration_fuel()

        # Aumentar la inspiración directamente en el estado vital
        current_insp = getattr(self.vital_state, "inspiration", 0.0)
        self.vital_state.inspiration = min(1.0, current_insp + inspiration_boost)

    def get_inspiration_fuel(self) -> float:
        """Retorna cuánto aumenta la inspiración un pensamiento interno."""
        return random.uniform(0.03, 0.08)
