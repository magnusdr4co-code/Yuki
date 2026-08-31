"""
Adaptador de Discord para Yuki.
Permite presencia en canales públicos, DMs, roles/artes y mensajes de Canvas.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("Yuki.DiscordAdapter")

class DiscordAdapter:
    def __init__(self, agent_instance, token: Optional[str] = None):
        self.agent = agent_instance
        self.token = token or os.getenv("DISCORD_BOT_TOKEN")
        self.agent.discord_adapter = self

    async def start(self):
        if not self.token or self.token == "your_discord_bot_token_here":
            logger.warning("Token de Discord no configurado. Modo simulado activado.")
            return

        logger.info("Bot de Discord de Yuki conectado a la sala.")

    async def handle_message(self, channel_id: str, author_id: str, author_name: str, content: str) -> str:
        """Procesa menciones o DMs en Discord."""
        if hasattr(self.agent, 'presence_controller'):
            if not self.agent.presence_controller.should_respond('discord_channel'):
                return 'NADA_QUE_DECIR'
        return await self.agent.generate_response(
            user_id=author_id,
            user_name=author_name,
            message=content,
            channel_type="discord_channel"
        )
