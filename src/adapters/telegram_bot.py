"""
Adaptador de Telegram para Yuki.
Permite interacción por texto, notas de voz sintetizadas (Nous TTS) e imágenes (FAL).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("Yuki.TelegramAdapter")

class TelegramAdapter:
    def __init__(self, agent_instance, token: Optional[str] = None):
        self.agent = agent_instance
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = os.getenv("TELEGRAM_DEFAULT_CHAT_ID")
        self.agent.telegram_adapter = self

    async def start_polling(self):
        """Inicia el bot en modo polling para desarrollo o VPS."""
        if not self.token or self.token == "your_telegram_bot_token_here":
            logger.warning("Token de Telegram no configurado. Modo simulado activado.")
            return

        logger.info("Bot de Telegram de Yuki iniciado.")

    async def handle_message(self, user_id: str, user_name: str, text: str) -> str:
        """Procesa un mensaje recibido en Telegram."""
        return await self.agent.generate_response(
            user_id=user_id,
            user_name=user_name,
            message=text,
            channel_type="telegram_dm"
        )

    async def broadcast_drop(self, text: str, image_path: Optional[str] = None, audio_path: Optional[str] = None):
        """Difunde un lanzamiento autónomo a los seguidores."""
        logger.info(f"📢 [TELEGRAM BROADCAST] {text}")
        if image_path:
            logger.info(f"📸 Enviando foto: {image_path}")
        if audio_path:
            logger.info(f"🎙️ Enviando nota de voz OGG Opus: {audio_path}")
