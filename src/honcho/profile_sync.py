"""
Sincronización y persistencia de perfiles dialécticos de Honcho.
"""

from typing import Dict, Any
from .dialectic import HonchoDialecticClient

class HonchoProfileSync:
    def __init__(self, client: HonchoDialecticClient):
        self.client = client

    def update_aesthetic_preference(self, category: str, item: str):
        prof = self.client._local_profile
        if category in prof["aesthetic_preferences"]:
            if item not in prof["aesthetic_preferences"][category]:
                prof["aesthetic_preferences"][category].append(item)
                self.client.save_local_profile()

    def record_synthesis(self, topic: str, thesis: str, antithesis: str, synthesis: str):
        prof = self.client._local_profile
        prof["dialectic_cards"].append({
            "topic": topic,
            "thesis": thesis,
            "antithesis": antithesis,
            "synthesis": synthesis
        })
        self.client.save_local_profile()
