"""
Escritura del perfil dialéctico local.

No sincroniza con nada: el nombre del módulo viene de cuando el diagrama
dibujaba un cliente remoto que nunca existió. Se conserva porque es API pública
en uso; lo que cambia es que aquí ya no se llama sincronización a guardar un
JSON en el disco de la instancia.
"""

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
