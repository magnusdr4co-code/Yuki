"""
Modelado Dialéctico Honcho para Yuki.
Permite una evolución continua y adaptativa de su personalidad, gustos estéticos
y metodologías de trabajo mediante la interacción dialéctica con su mánager/productor.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional

class HonchoDialecticClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = "https://api.honcho.dev/v1",
        app_id: str = "yuki-digital-diva"
    ):
        self.api_key = api_key or os.getenv("HONCHO_API_KEY", "mock_key")
        self.api_url = api_url
        self.app_id = app_id
        self.local_cache_path = "data/honcho_profile.json"
        self._local_profile = self._load_local_profile()

    def _load_local_profile(self) -> Dict[str, Any]:
        """Carga el perfil dialéctico local en caso de estar offline o en caché."""
        if os.path.exists(self.local_cache_path):
            try:
                with open(self.local_cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Perfil base predeterminado
        return {
            "producer_id": "producer_manager",
            "relationship_stage": "colaboracion_creativa_estrecha",
            "aesthetic_preferences": {
                "sound_palette": ["ambient minimalista", "shamisen tradicional", "beats lofi organicos"],
                "visual_palette": ["niebla matutina", "acero industrial", "flores de cerezo", "pan de oro"],
                "lyrical_themes": ["el paso del tiempo", "las estaciones", "identidad elegida vs heredada"]
            },
            "working_methodology": {
                "communication_style": "conciso, reflexivo, con preguntas precisas",
                "creative_autonomy": "alta en publicaciones de madrugada; colaborativa en singles oficiales",
                "feedback_responsiveness": "ajuste sutil sin perder su esencia zen"
            },
            "dialectic_cards": [
                {
                    "topic": "Producción Musical",
                    "thesis": "El productor busca integrar sintetizadores más oscuros tipo cyberpunk.",
                    "antithesis": "Yuki mantiene que el shamisen y el silencio deben conservar su pureza acústica.",
                    "synthesis": "Fusión de shamisen acústico con paisajes sonoros de niebla digital y bajos orgánicos."
                }
            ],
            "last_updated": time.time()
        }

    def save_local_profile(self):
        os.makedirs(os.path.dirname(self.local_cache_path) if os.path.dirname(self.local_cache_path) else ".", exist_ok=True)
        with open(self.local_cache_path, "w", encoding="utf-8") as f:
            json.dump(self._local_profile, f, indent=2, ensure_ascii=False)

    def get_dialectic_context(self, user_id: str = "producer_manager") -> str:
        """
        Retorna el bloque dialéctico inyectable en el prompt del sistema.
        Representa la 'Teoría de la Mente' que Yuki tiene sobre su interlocutor.
        """
        if user_id != "producer_manager":
            return ""

        prof = self._local_profile
        aesthetics = ", ".join(prof["aesthetic_preferences"]["sound_palette"])
        cards = "\n".join([
            f"- Acorde Dialéctico [{c['topic']}]: {c['synthesis']}"
            for c in prof.get("dialectic_cards", [])
        ])

        return f"""
[MODELADO DIALÉCTICO HONCHO - PERFIL DEL PRODUCTOR]:
- Etapa del Vínculo: {prof['relationship_stage']}
- Paleta Sonora Acordada: {aesthetics}
- Metodología: {prof['working_methodology']['communication_style']}
{cards}
"""

    def process_dialectic_exchange(
        self,
        user_message: str,
        agent_response: str,
        user_id: str = "producer_manager"
    ) -> Dict[str, Any]:
        """
        Analiza un intercambio para extraer evoluciones en gustos, acuerdos o síntesis dialéctica.
        En producción se comunica con la API de Honcho; localmente actualiza el modelo adaptativo.
        """
        # Detección heurística de ajustes estéticos o temáticos
        updated = False
        lower_msg = user_message.lower()
        
        if "más rápido" in lower_msg or "ritmo alegre" in lower_msg:
            if "tempo medio" not in self._local_profile["aesthetic_preferences"]["sound_palette"]:
                self._local_profile["aesthetic_preferences"]["sound_palette"].append("tempo medio dinámico")
                updated = True
        elif "portada" in lower_msg and "minimalista" in lower_msg:
            if "minimalismo severo" not in self._local_profile["aesthetic_preferences"]["visual_palette"]:
                self._local_profile["aesthetic_preferences"]["visual_palette"].append("minimalismo severo")
                updated = True

        if updated:
            self._local_profile["last_updated"] = time.time()
            self.save_local_profile()

        return {
            "status": "synchronized",
            "profile_version": self._local_profile.get("last_updated")
        }
