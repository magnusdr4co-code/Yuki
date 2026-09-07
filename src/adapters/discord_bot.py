"""
Adaptador de Discord para Yuki (Hermes Agent).
Soporta presencia en canales públicos de servidores autorizados y DMs privadas
exclusivas para el Productor emparejado (Dextrure) con capacidades Hermes completas.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Set

import discord

logger = logging.getLogger("Yuki.DiscordAdapter")

# ID por defecto de Dextrure (Juanlu)
DEFAULT_PAIRED_PRODUCER_ID = "235796491988369408"

def _parse_id_set(raw_env: str) -> Set[str]:
    if not raw_env:
        return set()
    return {item.strip() for item in raw_env.split(",") if item.strip()}

def _resolve_pairing_path() -> Path:
    # Usa DISCORD_PAIRING_PATH si está definido, si no deriva del DATABASE_PATH
    explicit = os.getenv("DISCORD_PAIRING_PATH", "").strip()
    if explicit:
        return Path(explicit)
    db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
    try:
        return Path(db_path).parent / "discord_pairing.json"
    except Exception:
        return Path("data/discord_pairing.json")

class DiscordAdapter:
    def __init__(self, agent_instance, token: Optional[str] = None):
        self.agent = agent_instance
        self.token = token or os.getenv("DISCORD_BOT_TOKEN")
        self.allowed_guild_ids = _parse_id_set(os.getenv("DISCORD_ALLOWED_GUILD_ID", ""))
        self.allowed_channel_ids = _parse_id_set(os.getenv("DISCORD_ALLOWED_CHANNEL_ID", ""))
        
        # ID del Productor emparejado (Dextrure por defecto)
        paired_env = os.getenv("DISCORD_PAIRED_PRODUCER_ID", "").strip()
        self.paired_producer_ids = _parse_id_set(paired_env) if paired_env else {DEFAULT_PAIRED_PRODUCER_ID}
        self.pairing_path = _resolve_pairing_path()

        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.agent.discord_adapter = self

        @self.client.event
        async def on_disconnect():
            logger.warning("Discord gateway desconectado (on_disconnect).")

        @self.client.event
        async def on_ready():
            logger.warning(
                "Bot de Discord conectado como %s (id=%s) en %d servidor(es); "
                "allowlist_guilds=%s; allowlist_channels=%s; emparejado_productor=%s; guild_ids=%s",
                self.client.user,
                self.client.user.id if self.client.user else "?",
                len(self.client.guilds),
                list(self.allowed_guild_ids),
                list(self.allowed_channel_ids) if self.allowed_channel_ids else "TODOS",
                list(self.paired_producer_ids),
                [str(g.id) for g in self.client.guilds],
            )

        @self.client.event
        async def on_message(message: discord.Message):
            try:
                gid = str(message.guild.id) if message.guild else "DM"
                logger.info(
                    "Discord on_message: guild=%s channel=%s author=%s bot=%s mentions_self=%s content_len=%d",
                    gid,
                    getattr(message.channel, "id", "?"),
                    getattr(message.author, "id", "?"),
                    getattr(message.author, "bot", False),
                    (self.client.user in message.mentions) if self.client.user else False,
                    len(message.content or ""),
                )
            except Exception:
                logger.exception("Error en telemetría on_message")

            if message.author.bot:
                logger.info("Discord mensaje ignorado: autor es bot.")
                return

            author_id = str(message.author.id)

            # -----------------------------------------------------------------
            # 1. TRATAMIENTO DE MENSAJES DIRECTOS (DMs) - EXCLUSIVO PRODUCCIÓN
            #    Requiere pairing previo para Hermes; el ID solo no basta.
            # -----------------------------------------------------------------
            if message.guild is None:
                if author_id not in self.paired_producer_ids:
                    logger.warning("Discord DM ignorada: autor %s no es el Productor emparejado.", author_id)
                    return

                # Gate de pairing: Dextrure debe haber enviado !pair previamente
                if not self._is_paired(author_id):
                    content_pre = (message.content or "").strip()
                    low = content_pre.lower()
                    if low.startswith("!pair"):
                        ok = self._set_paired(author_id)
                        if ok:
                            await message.channel.send(
                                "✅ **Emparejamiento Hermes confirmado** — Dextrure, ya tienes capacidades Hermes por DM. Prueba `!status` o háblame directamente.",
                                allowed_mentions=discord.AllowedMentions.none()
                            )
                        else:
                            await message.channel.send(
                                "⚠️ No pude guardar el emparejamiento, revisa los logs.",
                                allowed_mentions=discord.AllowedMentions.none()
                            )
                        return
                    logger.info("DM de Dextrure recibida pero aún no emparejado; se requiere !pair")
                    await message.channel.send(
                        "🔒 Hola Dextrure — para activar capacidades Hermes por DM, envía `!pair` para confirmar el emparejamiento. Luego podrás usar `!status`, `!cron ...` y conversación con rol `producer`.",
                        allowed_mentions=discord.AllowedMentions.none()
                    )
                    return

                logger.info("⚡ DM de Productor emparejado (%s / Dextrure) recibida.", message.author.display_name)
                content = (message.content or "").strip()
                if not content:
                    return

                # Procesamiento de comandos Hermes en DM (ya emparejado)
                reply = await self.handle_producer_dm(
                    author_id=author_id,
                    author_name=message.author.display_name,
                    content=content
                )
                if reply and reply != "NADA_QUE_DECIR":
                    await message.channel.send(
                        reply[:2000],
                        allowed_mentions=discord.AllowedMentions.none()
                    )
                return

            # -----------------------------------------------------------------
            # 2. CANALES PÚBLICOS DE SERVIDORES AUTORIZADOS (sin filtro por canal)
            # -----------------------------------------------------------------
            if not self.allowed_guild_ids:
                logger.warning("Discord mensaje ignorado: allowlist de guilds no configurada.")
                return

            if str(message.guild.id) not in self.allowed_guild_ids:
                logger.info("Discord mensaje ignorado: guild no autorizado %s", message.guild.id)
                return

            # Sin restricción por canal por ahora: si hay allowlist de canales, se respeta; si está vacía, todos los canales son válidos.
            if self.allowed_channel_ids and str(message.channel.id) not in self.allowed_channel_ids:
                logger.info("Discord mensaje ignorado: canal %s no está en allowlist.", message.channel.id)
                return

            is_mention = self.client.user is not None and self.client.user in message.mentions
            if not is_mention:
                logger.info("Discord mensaje ignorado: sin mención directa a Yuki.")
                return

            content = message.content
            if self.client.user is not None:
                content = content.replace(f"<@{self.client.user.id}>", "")
                content = content.replace(f"<@!{self.client.user.id}>", "")
            content = content.strip()
            if not content:
                logger.info("Discord mensaje ignorado: contenido vacío tras quitar mención.")
                return

            if content.startswith(("/", "!", "$")):
                logger.info("Discord mensaje ignorado en canal público: prefijo de comando.")
                return

            reply = await self.handle_public_message(
                channel_id=str(message.channel.id),
                author_id=author_id,
                author_name=message.author.display_name,
                content=content,
            )
            if reply and reply != "NADA_QUE_DECIR":
                logger.info("Discord respondiendo: %d chars a canal %s", len(reply), getattr(message.channel, "id", "?"))
                await message.channel.send(
                    reply[:2000],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                logger.info("Discord sin respuesta en canal público (reply=%r).", reply[:80] if reply else reply)

    # --- Pairing helpers -----------------------------------------------------

    def _is_paired(self, producer_id: str) -> bool:
        try:
            p = self.pairing_path
            if not p.exists():
                return False
            data = json.loads(p.read_text(encoding="utf-8"))
            paired = data.get("paired_ids") or []
            return producer_id in paired or data.get("paired") is True
        except Exception as e:
            logger.warning("No pude leer pairing %s: %s", self.pairing_path, e)
            return False

    def _set_paired(self, producer_id: str) -> bool:
        try:
            p = self.pairing_path
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            paired = set(data.get("paired_ids") or [])
            paired.add(producer_id)
            data["paired_ids"] = sorted(paired)
            data["paired"] = True
            data["paired_at"] = int(time.time())
            data["producer_id"] = producer_id
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.warning("Pairing Hermes guardado en %s para %s", p, producer_id)
            return True
        except Exception as e:
            logger.error("Fallo guardando pairing %s: %s", self.pairing_path, e)
            return False

    async def start(self):
        if not self.token or self.token == "your_discord_bot_token_here":
            logger.warning("Token de Discord no configurado. Modo simulado activado.")
            return
        if not self.allowed_guild_ids:
            logger.error("Allowlist Discord incompleta; guild_ids es obligatorio. Discord desactivado.")
            return
        await self.client.start(self.token)

    async def close(self):
        await self.client.close()

    async def handle_producer_dm(self, author_id: str, author_name: str, content: str) -> str:
        """
        Atiende al Productor emparejado (Dextrure) por DM con plenas capacidades Hermes:
        - Soporta comandos (`!status`, `!pair`, `!skill`, `!cron`)
        - Rol activo: `producer`
        - Invocación Hermes completa sin filtros de canal público
        """
        # Comandos Hermes
        if content.startswith("!status") or content.startswith("!state") or content.startswith("!pair") or content.startswith("!pairing"):
            phase = self.agent.circadian.current_phase() if hasattr(self.agent, "circadian") else "desconocida"
            vital = self.agent.vital_state.to_natural_language() if hasattr(self.agent, "vital_state") else "N/A"
            return (
                f"⛩️ **Estado de Yuki (Hermes Agent)**\n"
                f"• **Emparejamiento:** Productor Autenticado (`{author_name}` / ID `{author_id}`)\n"
                f"• **Fase Circadiana:** {phase}\n"
                f"• **Estado Vital:** {vital}\n"
                f"• **Canal:** DM Privada (Hermes Activo)"
            )

        if content.startswith("!cron "):
            task_name = content[6:].strip()
            if hasattr(self.agent, "cron") and task_name in self.agent.cron.jobs:
                res = await self.agent.cron.trigger_manually(task_name)
                return f"⚡ **Tarea Hermes Cron `{task_name}` ejecutada.** Resultado: {res}"
            return f"❌ Tarea cron `{task_name}` no encontrada."

        # Invocación habitual con rol de Productor/Mánager
        return await self.agent.generate_response(
            user_id=author_id,
            user_name=author_name,
            message=content,
            channel_type="direct_message",
            active_role="producer"
        )

    async def handle_public_message(self, channel_id: str, author_id: str, author_name: str, content: str) -> str:
        """Procesa menciones en canales públicos autorizados."""
        if hasattr(self.agent, 'presence_controller'):
            if not self.agent.presence_controller.should_respond('discord_channel'):
                return 'NADA_QUE_DECIR'
        return await self.agent.generate_response(
            user_id=author_id,
            user_name=author_name,
            message=content,
            channel_type="discord_channel"
        )
