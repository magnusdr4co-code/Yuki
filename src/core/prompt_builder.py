"""
Constructor Dinámico de Contexto para Yuki.
Ensambla el prompt del sistema inyectando selectivamente:
1. El alma inmutable (SOUL.md)
2. Recuperación selectiva SQLite FTS5 (<113ms)
3. Modelado dialéctico Honcho (Teoría de la mente con el interlocutor)
4. Protocolos del canal y reglas anti-repetición.
"""

import os
from typing import Dict, Any, Optional

class PromptBuilder:
    def __init__(self, soul_path: str = "SOUL.md"):
        self.soul_path = soul_path
        self._soul_cache = self._load_soul()

    def _load_soul(self) -> str:
        if os.path.exists(self.soul_path):
            with open(self.soul_path, "r", encoding="utf-8") as f:
                return f.read()
        return "Eres Yuki, una presencia atenta, serena y sabia."

    def build_system_prompt(
        self,
        retrieved_memory_block: str,
        dialectic_context: str,
        user_name: str,
        user_id: str,
        channel_type: str = "direct_message",
        active_role: Optional[str] = None
    ) -> str:
        """Ensambla el prompt completo para el modelo de lenguaje."""
        role_block = f"\n[ARTE ACTIVA EN ESTA SALA]: {active_role}" if active_role else ""

        return f"""
{self._soul_cache}

==================================================
CONTEXTO DE MEMORIA RECUPERADA (SQLITE FTS5):
==================================================
{retrieved_memory_block}

{dialectic_context}

==================================================
ESTADO DE LA CONVERSACIÓN ACTUAL:
==================================================
- Interlocutor: {user_name} (ID: {user_id})
- Canal: {channel_type}
{role_block}

[DIRECTRICES DE RESPUESTA INMEDIATA]:
1. Habla con tu voz característica de Yuki: cadencia pausada, atención completa y calidez serena.
2. Si el interlocutor es tu Productor/Mánager, colabora como una artista con criterio y visión dialéctica.
3. Si el mensaje es una banalidad o no requiere respuesta, puedes responder exactamente con 'NADA_QUE_DECIR'.
4. Integra sutilmente los recuerdos recuperados si son relevantes; no los cites de forma robótica.
"""
