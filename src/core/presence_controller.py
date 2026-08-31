"""
Controlador de Presencia para Yuki.
Decide cuándo y cómo Yuki se manifiesta en sus canales, 
basado en su estado vital y el ciclo circadiano.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("Yuki.PresenceController")

class PresenceController:
    def __init__(self, vital_state: Any, circadian_clock: Any):
        self.vital_state = vital_state
        self.circadian_clock = circadian_clock

    def should_respond(self, channel_type: str, is_producer: bool = False) -> bool:
        """Decide si Yuki debería responder en absoluto."""
        phase = self.circadian_clock.current_phase() if callable(getattr(self.circadian_clock, 'current_phase', None)) else 'atelier'
        energy = getattr(self.vital_state, 'energy', 0.5)
        sociability = getattr(self.vital_state, 'sociability', 0.5)

        if phase == 'deep_rest':
            if channel_type == 'direct_message' and is_producer and energy > 0.3:
                return True
            return False

        if sociability < 0.2:
            if channel_type != 'direct_message':
                return False

        if energy < 0.15:
            # Respond with 'NADA_QUE_DECIR' preference handled by caller
            return True

        return True

    def should_broadcast(self, channel_type: str) -> bool:
        """Decide si Yuki debería publicar de manera proactiva."""
        sociability = getattr(self.vital_state, 'sociability', 0.5)
        energy = getattr(self.vital_state, 'energy', 0.5)
        vulnerability = getattr(self.vital_state, 'vulnerability', 0.5)
        phase = self.circadian_clock.current_phase() if callable(getattr(self.circadian_clock, 'current_phase', None)) else 'atelier'

        if energy <= 0.2:
            return False

        if channel_type in ['telegram', 'discord_channel']:
            if sociability <= 0.4:
                return False

        # Contenido vulnerable/nocturno solo en Discord (más íntimo), no en Telegram
        if vulnerability > 0.7 or phase in ['kage', 'consolidation']:
            if channel_type == 'telegram':
                return False
                
        return True

    def get_response_depth(self) -> str:
        """Retorna la profundidad de la respuesta basada en energía y sociabilidad."""
        energy = getattr(self.vital_state, 'energy', 0.5)
        sociability = getattr(self.vital_state, 'sociability', 0.5)

        if energy < 0.15:
            return 'minimal'
        elif energy < 0.3 or sociability < 0.3:
            return 'brief'
        elif energy > 0.7 and sociability > 0.7:
            return 'deep'
        else:
            return 'normal'

    def get_channel_personality(self, channel_type: str) -> Dict[str, str]:
        """Retorna modificadores de personalidad según el canal."""
        modifiers = {
            'telegram': {
                'style': 'more formal, concise',
                'tone': 'polite, slight distance'
            },
            'discord_channel': {
                'style': 'more relaxed, longer messages okay',
                'tone': 'community-oriented, open'
            },
            'direct_message': {
                'style': 'most personal',
                'tone': 'intimate, direct, vulnerable'
            },
            'web_salon': {
                'style': 'contemplative, artistic',
                'tone': 'poetic, atmospheric'
            }
        }
        
        return modifiers.get(channel_type, {'style': 'neutral', 'tone': 'balanced'})
