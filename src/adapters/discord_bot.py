"""
Adaptador de Discord para Yuki (Hermes Agent).
Soporta presencia en canales públicos de servidores autorizados y DMs privadas
exclusivas para el Productor emparejado con herramientas explícitas del arnés.
"""

import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Set

import discord
from .discord_intents import (
    channel_slug as _channel_slug,
    extract_production_target as _extract_production_target,
    fold as _fold,
    looks_like_discord_production_request as _looks_like_discord_production_request,
)
from .discord_text import split_discord_text

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
        self._workflow_tasks: Set[object] = set()
        self._producer_lock = asyncio.Lock()

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
                async with self._producer_lock:
                    try:
                        async with message.channel.typing():
                            reply = await self.handle_producer_dm(
                                author_id=author_id, author_name=message.author.display_name,
                                content=content, origin_channel=message.channel,
                            )
                        if reply and reply != "NADA_QUE_DECIR":
                            await self._send_long(message.channel, reply)
                    except Exception:
                        logger.exception("Fallo atendiendo DM de productor")
                        await self._send_long(message.channel, "❌ No pude completar el turno. No doy la tarea por realizada; revisa el registro de ejecución.")
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

            if (
                author_id in self.paired_producer_ids
                and self._is_paired(author_id)
                and _looks_like_discord_production_request(content)
            ):
                reply = "🔒 Envíame la orden por DM emparejado para ejecutar herramientas de producción."
                await message.channel.send(
                    reply,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

            reply = await self.handle_public_message(
                channel_id=str(message.channel.id),
                author_id=author_id,
                author_name=message.author.display_name,
                content=content,
            )
            if reply and reply != "NADA_QUE_DECIR":
                logger.info("Discord respondiendo: %d chars a canal %s", len(reply), getattr(message.channel, "id", "?"))
                await self._send_long(message.channel, reply)
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

    async def handle_producer_dm(
        self,
        author_id: str,
        author_name: str,
        content: str,
        origin_channel=None,
    ) -> str:
        """
        DM autenticado: comandos concretos, producción y Biblioteca con herramientas.
        """
        if author_id not in self.paired_producer_ids or not self._is_paired(author_id):
            return "🔒 Se requiere DM del productor emparejado."
        if _looks_like_discord_production_request(content):
            return self._launch_discord_production(
                author_id=author_id,
                author_name=author_name,
                content=content,
                origin_channel=origin_channel,
            )

        # Comandos Hermes
        if content.startswith("!status") or content.startswith("!state") or content.startswith("!pair") or content.startswith("!pairing"):
            phase = self.agent.circadian.current_phase() if hasattr(self.agent, "circadian") else "desconocida"
            vital = self.agent.vital_state.to_natural_language() if hasattr(self.agent, "vital_state") else "N/A"
            return (
                f"⛩️ **Estado de Yuki (Hermes Agent)**\n"
                f"• **Emparejamiento:** Productor Autenticado (`{author_name}` / ID `{author_id}`)\n"
                f"• **Fase Circadiana:** {phase}\n"
                f"• **Estado Vital:** {vital}\n"
                f"• **Canal:** DM privada con herramientas de Biblioteca y producción.\n"
                f"• **Tareas de producción activas:** {len(self._workflow_tasks)}\n"
                "• No hay shell ni auto-configuración general habilitados."
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
            active_role="producer",
            producer_tools=True,
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

    # --- Acciones Discord del productor --------------------------------------

    def _launch_discord_production(
        self,
        author_id: str,
        author_name: str,
        content: str,
        origin_channel,
    ) -> str:
        """Lanza la producción en segundo plano y devuelve un acuse inmediato."""
        task = asyncio.create_task(
            self._run_discord_production(
                author_id=author_id,
                author_name=author_name,
                content=content,
                origin_channel=origin_channel,
            )
        )
        self._workflow_tasks.add(task)
        task.add_done_callback(self._workflow_tasks.discard)
        return (
            "⚡ He iniciado la producción en el canal de Discord. "
            "Iré publicando allí cada resultado y dejaré explícitos los medios "
            "que el proyecto todavía no pueda generar."
        )

    def _find_guild(self, requested_name: str):
        wanted = _fold(requested_name)
        exact = next((g for g in self.client.guilds if _fold(g.name) == wanted), None)
        if exact and str(exact.id) in self.allowed_guild_ids:
            return exact
        return next((g for g in self.client.guilds if str(g.id) in self.allowed_guild_ids and wanted in _fold(g.name)), None)

    @staticmethod
    def _permission_names(guild) -> Set[str]:
        member = getattr(guild, "me", None)
        if member is None:
            return set()
        permissions = getattr(member, "guild_permissions", None)
        if permissions is None:
            return set()
        return {
            name for name in ("manage_channels", "send_messages", "attach_files")
            if bool(getattr(permissions, name, False))
        }

    async def _send_long(self, channel, content: str) -> None:
        for chunk in split_discord_text(content):
            await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    async def _send_file(self, channel, path: Optional[str], caption: str) -> bool:
        if not path or not Path(path).is_file():
            return False
        await channel.send(
            caption,
            file=discord.File(path, filename=Path(path).name),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    async def _run_discord_production(
        self,
        author_id: str,
        author_name: str,
        content: str,
        origin_channel,
    ) -> None:
        """Ejecuta el encargo multimodal sólo para el productor emparejado."""
        guild_name, requested_channel_name = _extract_production_target(content)
        guild = self._find_guild(guild_name)

        async def report_origin(text: str) -> None:
            if origin_channel is not None:
                await self._send_long(origin_channel, text)

        if guild is None:
            await report_origin(f"❌ No encuentro el servidor autorizado `{guild_name}`.")
            return

        permissions = self._permission_names(guild)
        missing = {"manage_channels", "send_messages"} - permissions
        if missing:
            faltan = ", ".join(sorted(missing))
            await report_origin(
                f"🔒 No puedo abrir el Salón en `{guild.name}`: al bot le faltan "
                f"los permisos `{faltan}`. Concede `Manage Channels` y `Send Messages` "
                "al rol de Yuki y vuelve a intentarlo."
            )
            return

        # Una pausa temporal evita que el cron interrumpa la sesión sin detener
        # el daemon ni perder las tareas registradas.
        paused_until = self.agent.cron.pause_for(3 * 60 * 60)
        try:
            wanted_slug = _channel_slug(requested_channel_name)
            channel = next(
                (
                    candidate for candidate in guild.text_channels
                    if _channel_slug(candidate.name) == wanted_slug
                ),
                None,
            )
            created = False
            if channel is None:
                try:
                    channel = await guild.create_text_channel(
                        wanted_slug,
                        topic="Salón de producción de Yuki — poema, música, arte y vídeo.",
                        reason=f"Producción solicitada por {author_name} ({author_id})",
                    )
                    created = True
                except discord.Forbidden:
                    await report_origin(
                        f"🔒 Discord rechazó la creación de `{requested_channel_name}` en `{guild.name}`. "
                        "El permiso efectivo `Manage Channels` no está concedido al bot."
                    )
                    return
                except discord.HTTPException as exc:
                    await report_origin(f"❌ Discord no pudo crear el canal: {exc}")
                    return

            await self._send_long(
                channel,
                "⛩️ **Salón de Yuki**\n"
                "Este es el espacio de producción: cada pieza se publica aquí en orden, "
                "sin confundir un marcador con una obra real.\n"
                f"Cron temporalmente pausado hasta `{paused_until.isoformat()}`.",
            )
            if created:
                await report_origin(f"✅ Canal `{channel.name}` creado en `{guild.name}`. La producción continúa allí.")
            else:
                await report_origin(f"✅ Ya existía `{channel.name}` en `{guild.name}`. Continúo allí.")

            member = getattr(guild, "me", None)
            effective = channel.permissions_for(member) if member is not None else None
            if effective is not None:
                if not getattr(effective, "send_messages", False):
                    await report_origin(
                        f"🔒 El canal `{channel.name}` se creó, pero un override de permisos impide enviar mensajes."
                    )
                    return
                if not getattr(effective, "attach_files", False):
                    permissions.discard("attach_files")

            can_attach = "attach_files" in permissions
            if not can_attach:
                await self._send_long(
                    channel,
                    "⚠️ El bot puede escribir, pero no tiene `Attach Files`; no consumiré generación "
                    "multimedia que luego no podría publicar.",
                )

            presentation = await self.agent.generate_response(
                user_id=author_id,
                user_name=author_name,
                message=(
                    "Escribe una presentación breve y concreta del Salón de Yuki, "
                    "un espacio de té y acero para producir poema, partitura, imagen y vídeo. "
                    "No afirmes haber creado archivos ni ejecutado acciones."
                ),
                channel_type="discord_channel",
                active_role="producer",
            )
            await self._send_long(channel, f"### Presentación\n{presentation}")
            await asyncio.to_thread(self.agent.creation_library.save_text, "Presentación del Salón", presentation,
                                    source=f"discord:{guild.id}/{channel.id}")

            poem = await self.agent.generate_response(
                user_id=author_id,
                user_name=author_name,
                message=(
                    "Escribe la letra original de una canción de 1-2 minutos titulada "
                    "Herrumbre y Escarcha: 3 estrofas, estribillo repetido y puente. "
                    "Imágenes de agua, hierro, muelle, invierno y una esperanza contenida."
                ),
                channel_type="discord_channel",
                active_role="producer",
            )
            await self._send_long(channel, f"### Poema / letra — Herrumbre y Escarcha\n{poem}")
            await asyncio.to_thread(self.agent.creation_library.save_text, "Herrumbre y Escarcha", poem,
                                    source=f"discord:{guild.id}/{channel.id}")

            music_engine = "midi_only"
            media_creator = getattr(self.agent, "media_creator", None)
            portal = getattr(media_creator, "portal", None)
            vertex = getattr(portal, "vertex", None)
            if getattr(vertex, "is_available", lambda: False)():
                music_engine = getattr(vertex, "music_model", "lyria-3-pro-preview")

            music = await self.agent.media_creator.compose_beat_structure(
                title="Herrumbre y Escarcha",
                bpm=82,
                scale="insen",
                mood="agua, hierro, invierno y esperanza contenida",
                engine=music_engine,
            )
            await self._send_long(
                channel,
                "### Partitura\n"
                f"Estructura: {music['track_data']['structure']}\n"
                "Adjunto la partitura MIDI multipista real.",
            )
            if can_attach:
                await self._send_file(channel, music.get("midi_path"), "🎼 Partitura MIDI")
            else:
                await self._send_long(channel, "⚠️ Falta `Attach Files`; no puedo adjuntar el MIDI.")

            visual_paths = []
            visual_prompts = [
                "el exterior del Salón bajo lluvia y metal oxidado",
                "el interior del Salón con té, acero y escarcha",
                "la letra Herrumbre y Escarcha convertida en paisaje abstracto",
            ]
            if can_attach:
                for index, visual_prompt in enumerate(visual_prompts, 1):
                    art = await self.agent.media_creator.create_single_cover(
                        track_title=f"Herrumbre y Escarcha {index}",
                        visual_concept=visual_prompt,
                        lighting="industrial_rain" if index == 1 else "urushi",
                    )
                    if art.get("status") == "success" and art.get("local_path"):
                        visual_paths.append(art["local_path"])
                        await self._send_file(channel, art["local_path"], f"🎨 Representación {index}")
                    else:
                        await self._send_long(
                            channel,
                            f"⚠️ Representación {index} no generada: {art.get('error') or art.get('note') or 'sin detalle'}",
                        )
            else:
                await self._send_long(channel, "⏭️ Representaciones visuales omitidas hasta conceder `Attach Files`.")

            if music.get("audio_status") == "success" and music.get("audio_path"):
                await self._send_file(channel, music["audio_path"], "🎵 Canción")
            else:
                await self._send_long(
                    channel,
                    "⚠️ La canción no se pudo generar; la partitura MIDI sí es real. "
                    f"Detalle: {music.get('audio_note') or 'sin detalle'}",
                )

            if can_attach:
                video = await self.agent.nous_portal.generate_video_frontier(
                    prompt="La cámara recorre el Salón de té y acero mientras la lluvia se convierte en escarcha.",
                    duration_seconds=6,
                    image_path=visual_paths[0] if visual_paths else None,
                )
                if video.get("status") == "success" and video.get("local_path"):
                    await self._send_file(channel, video["local_path"], "🎬 Vídeo final")
                else:
                    await self._send_long(
                        channel,
                        f"⚠️ Vídeo no generado: {video.get('error') or video.get('note') or 'sin detalle'}",
                    )
            else:
                await self._send_long(channel, "⏭️ Vídeo omitido hasta conceder `Attach Files`.")
            await self._send_long(channel, "✅ Secuencia de producción terminada.")
            inventory = await asyncio.to_thread(self.agent.creation_library.inventory)
            await report_origin(f"✅ Producción finalizada en `{channel.name}`. Biblioteca: {inventory['total']} piezas indexadas; los fallos parciales están detallados en el canal.")
        except Exception as exc:
            logger.exception("Fallo en producción Discord de Yuki")
            await report_origin(f"❌ La producción se detuvo con un error: {exc}")
