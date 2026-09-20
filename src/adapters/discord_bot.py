"""
Adaptador de Discord para Yuki (Hermes Agent).
Soporta presencia en canales públicos de servidores autorizados y DMs privadas
exclusivas para el Productor emparejado con herramientas explícitas del arnés.

Aquí queda sólo el trato con el gateway: quién puede hablar, por dónde entra
cada mensaje y cómo sale un texto o un adjunto. Lo que se hace con esa entrada
vive en tres módulos aparte —comandos de gobierno, producción multimedia y el
Salón— porque el fichero llegó a 1775 líneas y tocar un comando obligaba a
leerlas todas.
"""

import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Set

import discord
from .discord_comandos import ComandosDelProductor
from .discord_intents import (
    looks_like_discord_production_request as _looks_like_discord_production_request,
    looks_like_media_delivery_request as _looks_like_media_delivery_request,
)
from .discord_produccion import MEDIA_STORYBOARD, ProduccionMultimedia
from .discord_salon import IMAGINARIO_POR_DEFECTO, SalonDeDiscord, TEMA_POR_DEFECTO
from .discord_text import split_discord_text
from ..core.brake import Brake
from ..core.transparency import MediaMarker
from ..tools.media_jobs import MediaJobStore

logger = logging.getLogger("Yuki.DiscordAdapter")

# El guion y los dos valores por defecto se reexportan porque se nombran desde
# fuera por este módulo desde antes del corte.
__all__ = [
    "DiscordAdapter",
    "DEFAULT_PAIRED_PRODUCER_ID",
    "MEDIA_STORYBOARD",
    "TEMA_POR_DEFECTO",
    "IMAGINARIO_POR_DEFECTO",
]

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


class DiscordAdapter(ComandosDelProductor, ProduccionMultimedia, SalonDeDiscord):
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
        # Los encargos multimedia se persisten antes de gastar crédito, así que
        # un reinicio los reanuda en vez de perderlos.
        self.media_jobs = MediaJobStore()
        # Trabajos con una tarea viva ahora mismo. `on_ready` no se dispara sólo
        # al arrancar: Discord lo vuelve a emitir en cada reconexión del gateway,
        # y sin este registro una caída de red relanzaría un encargo en curso y
        # pagaría dos veces el mismo clip.
        self._active_job_ids: Set[str] = set()
        # Freno de mano: lo consulta el adaptador antes de emprender nada que
        # salga hacia fuera o gaste crédito, para poder decir que no con motivo
        # en vez de fallar a mitad.
        self.brake = Brake()

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
            try:
                reanudados = await self.resume_pending_media_jobs()
                if reanudados:
                    logger.warning("Reanudados %d trabajos multimedia tras el arranque.", reanudados)
            except Exception:
                logger.exception("Fallo reanudando trabajos multimedia")

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

    async def notify_producer(self, texto: str) -> bool:
        """
        Abre el DM del Productor para decirle algo que Yuki ha decidido sola.

        Es lo que permite que una propuesta de ritmo llegue sin que él pregunte:
        una iniciativa que sólo se ve si alguien la busca no es iniciativa.
        """
        for producer_id in sorted(self.paired_producer_ids):
            if not self._is_paired(producer_id):
                continue
            try:
                usuario = (self.client.get_user(int(producer_id))
                           or await self.client.fetch_user(int(producer_id)))
                canal = usuario.dm_channel or await usuario.create_dm()
                await self._send_long(canal, texto)
                return True
            except (ValueError, AttributeError, discord.HTTPException) as exc:
                logger.warning("No pude avisar al Productor %s: %s", producer_id, type(exc).__name__)
        return False

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
        channel_production = _looks_like_discord_production_request(content)
        media_delivery = _looks_like_media_delivery_request(content)
        logger.info("Ruta DM productor: canal_produccion=%s media_entrega=%s", channel_production, media_delivery)
        if channel_production:
            return self._launch_discord_production(
                author_id=author_id,
                author_name=author_name,
                content=content,
                origin_channel=origin_channel,
            )
        if media_delivery:
            return self._launch_dm_media_delivery(
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
                f"• **Trabajos multimedia reanudables:** {len(self.media_jobs.resumable(author_id))}\n"
                "• No hay shell ni auto-configuración general habilitados."
            )

        if content.startswith("!ritmos") or content.startswith("!ritmo "):
            return self._handle_rituals_command(content, author_id, author_name)

        if content.startswith("!freno"):
            return self._handle_brake_command(content, author_name)

        if content.startswith("!bitacora") or content.startswith("!bitácora"):
            from ..core.blackbox import BlackBox

            caja = BlackBox()
            informe = caja.verify()
            ultimas = caja.entries(limite=5)
            estado = "✅ íntegra" if informe["integra"] else "🚨 **MANIPULADA**"
            lineas = [f"⛓️ **Bitácora** — {estado}",
                      f"{informe['entradas']} anotación(es) · cabeza `{informe['cabeza'][:16]}…`"]
            for problema in informe["problemas"][:3]:
                lineas.append(f"• 🚨 seq {problema['seq']}: {problema['fallo']} — {problema['detalle']}")
            if ultimas:
                lineas.append("\n**Últimos actos:**")
                lineas += [f"• `{e.seq}` {e.op} _(por {e.actor})_" for e in reversed(ultimas)]
            return "\n".join(lineas)

        if content.startswith("!estado ") or content.strip() == "!estado":
            return self._handle_state_command(content, author_name)

        if content.startswith("!olvidar"):
            return self._handle_forget_command(content, author_name)

        if content.startswith("!sueno") or content.startswith("!sueños") or content.startswith("!suenos"):
            serie = self.agent.sleep.dream_series(limite=3)
            if not serie:
                return "🌙 Todavía no he soñado nada que merezca contarse."
            piezas = "\n\n".join(
                f"**{s['titulo']}**"
                + (f" _(sigue al {s['sigue_a']})_" if s["sigue_a"] else "")
                + f"\n{s['contenido'][:600]}"
                for s in serie)
            return ("🌙 **Lo que he soñado**\n_Ninguno de estos ocurrió; no vuelven en mis "
                    "recuerdos salvo que los pidas._\n\n" + piezas)

        if content.startswith("!deriva") or content.startswith("!persona"):
            informe = self.agent.persona.report()
            if not informe["muestras"]:
                return "🪞 Aún no hay muestras de deriva: hace falta que hable un poco."
            marcadores = "\n".join(f"  • {veces}× `{marcador}`"
                                    for marcador, veces in informe["marcadores_frecuentes"])
            return (
                "🪞 **Deriva de persona**\n"
                f"• **Media reciente:** {informe['media_reciente']} (umbral {informe['umbral']})\n"
                f"• **Mínimo:** {informe['minimo_reciente']} · "
                f"**turnos bajo umbral:** {informe['por_debajo_del_umbral']}\n"
                f"• **Reanclajes aplicados:** {informe['anclajes']} sobre {informe['muestras']} muestras\n"
                + (f"• **Por dónde se va:**\n{marcadores}" if marcadores else
                   "• Sin marcadores de deriva registrados.")
            )

        if content.startswith("!albedrio") or content.startswith("!albedrío"):
            return self._handle_agency_command(content, author_id)

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
    async def _send_long(self, channel, content: str) -> None:
        for chunk in split_discord_text(content):
            await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    async def _send_file(self, channel, path: Optional[str], caption: str) -> bool:
        """
        Adjunta un fichero, con su origen sintético marcado y declarado.

        La marca se pone al generarlo, pero esta es la puerta por la que el
        material sale hacia una persona: comprobarla aquí es lo que impide que
        un camino nuevo —o un fichero traído de la Biblioteca antes del marcado—
        entregue una obra sin declarar lo que es.
        """
        if not path or not Path(path).is_file():
            return False
        # El marcador se toma del agente, pero si faltara se construye uno: la
        # obligación de declarar el origen no puede depender de un cableado.
        marcador = getattr(self.agent, "marker", None) or MediaMarker()
        if not marcador.is_marked(path):
            marca = await asyncio.to_thread(marcador.mark, path, "", "", "entrega")
            logger.info("Fichero marcado en la entrega: %s (%s)", path, marca.get("marked"))
        caption = f"{caption}\n-# 🤖 Contenido generado por IA"
        try:
            await channel.send(
                caption,
                file=discord.File(path, filename=Path(path).name),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True
        except discord.HTTPException as exc:
            logger.warning("Discord no pudo adjuntar %s: %s", path, type(exc).__name__)
            return False
