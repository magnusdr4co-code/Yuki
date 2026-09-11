"""
Perfil dialéctico del Productor. **Local, y eso es lo que es.**

El nombre viene de Honcho y el diagrama dibujaba un «Honcho Client API», pero en
este código no hay ni ha habido una sola llamada a ningún servicio: el perfil
vive en `data/honcho_profile.json` y lo actualizan dos heurísticas sobre el texto
del Productor. `docs/VIRTUALIZACION_Y_MEJORAS.md` (M6, limitador L9) daba dos
salidas honestas —sincronizar con el servicio o **declarar el JSON local como la
implementación real**— y ésta es la segunda.

Lo que había antes era la tercera, la que no vale: `api_key` caía a `"mock_key"`,
se guardaba una `api_url` que nadie usaba, y `process_dialectic_exchange`
devolvía `{"status": "synchronized"}` **siempre**, sincronizara o no, hubiera
servicio o no. Un campo que dice «sincronizado» sin haber hablado con nadie es
exactamente el vicio que este proyecto lleva años corrigiendo.

Que sea local no lo hace frágil: el perfil entra en la copia de seguridad
—`backup.py` lo incluye— y está declarado en `state_registry`, así que sobrevive
a la pérdida del disco igual que la memoria.
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

from ..core import estado_json
from ..core.rutas import datos

class HonchoDialecticClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = "https://api.honcho.dev/v1",
        app_id: str = "yuki-digital-diva"
    ):
        # Se siguen aceptando por compatibilidad con `config.yaml` y con el
        # agente, que los pasa. No se usan: no hay llamada remota. Sin valor
        # falso por defecto —`"mock_key"` daba a entender que había credencial—.
        self.api_key = api_key or os.getenv("HONCHO_API_KEY", "")
        self.api_url = api_url  # no se lee: no hay cliente remoto
        self.app_id = app_id    # no se lee: no hay cliente remoto
        self.local_cache_path = str(datos("honcho_profile.json"))
        self._local_profile = self._load_local_profile()

    def _load_local_profile(self) -> Dict[str, Any]:
        """
        El perfil guardado, o el de base.

        Se lee con `estado_json` como el resto del estado del proyecto: un
        fichero corrupto devuelve el esquema vacío en vez de tumbar la
        instancia, y aquí el esquema vacío es el perfil de base. Antes tenía su
        propia copia de esas dos líneas y se tragaba cualquier excepción en
        silencio, sin dejar constancia de que el perfil se había perdido.
        """
        guardado = estado_json.leer(
            Path(self.local_cache_path), self._perfil_de_base,
            valido=lambda d: isinstance(d.get("aesthetic_preferences"), dict),
            que_es="perfil dialéctico",
        )
        return guardado

    @staticmethod
    def _perfil_de_base() -> Dict[str, Any]:
        """Punto de partida. Es una función para que dos lectores no compartan listas."""
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
        """Escritura atómica: el proceso muere a mitad justo cuando se despliega."""
        estado_json.escribir(Path(self.local_cache_path), self._local_profile)

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
        Ajusta el perfil local con lo que el Productor haya dejado dicho.

        Son dos heurísticas sobre el texto, y el resultado lo dice: `remoto` es
        `False` siempre, porque no hay servicio con el que hablar. Antes esto
        devolvía `{"status": "synchronized"}` en todos los casos —también cuando
        no cambiaba nada—, que es afirmar una sincronización inexistente en el
        único campo donde alguien iría a comprobarla.
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
            "status": "local",
            "remoto": False,
            "actualizado": updated,
            "profile_version": self._local_profile.get("last_updated"),
        }
