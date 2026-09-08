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
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Set, List, Dict, Any

import discord
from .discord_intents import (
    channel_slug as _channel_slug,
    extract_production_target as _extract_production_target,
    fold as _fold,
    looks_like_discord_production_request as _looks_like_discord_production_request,
    looks_like_media_delivery_request as _looks_like_media_delivery_request,
)
from .discord_text import split_discord_text
from ..core.brake import Brake
from ..core.transparency import MediaMarker
from ..tools.media_jobs import MediaJobStore, describe_job as describe_media_job

logger = logging.getLogger("Yuki.DiscordAdapter")

# ID por defecto de Dextrure (Juanlu)
DEFAULT_PAIRED_PRODUCER_ID = "235796491988369408"

# Guion del encargo audiovisual. Vive aquí y no dentro del bucle porque el
# número de segmentos define los pasos del trabajo durable: cambiarlo cambia
# lo que un reinicio considera "ya hecho".
MEDIA_STORYBOARD = (
    "Exterior del muelle: lluvia sobre acero oxidado, la escarcha empieza a aparecer.",
    "Entrada al Salón: vapor de té, seda oscura y reflejos de urushi sobre hierro.",
    "Interior: la intérprete respira y el poema encuentra su estribillo entre cuerdas tensas.",
    "Salida: agua, niebla y una luz contenida sobre el metal; final pausado, sin corte brusco.",
)

# Pasos facturables del encargo multimedia, en orden de ejecución.
MEDIA_JOB_STEPS = (
    [("cancion", "cancion")]
    + [(f"clip_{i}", "clip") for i in range(1, len(MEDIA_STORYBOARD) + 1)]
    + [("montaje", "montaje"), ("entrega", "entrega")]
)

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

    def _handle_brake_command(self, content: str, author_name: str) -> str:
        """
        Freno de mano desde el DM: la palanca que no exige desplegar nada.

        Se acepta con una sola palabra porque el momento de usarlo es el momento
        de menos paciencia que hay. La palanca de entorno del operador sigue
        mandando por encima de esto, y se dice cuando ocurre.
        """
        partes = content.split()
        estado = self.brake.state()

        if len(partes) == 1:
            lineas = [f"🛑 **Freno de mano** — {self.brake.describe()}"]
            if estado.activo:
                detalles = estado.to_dict()
                if detalles.get("minutos_restantes") is not None:
                    lineas.append(f"Se suelta solo en {detalles['minutos_restantes']} min.")
            lineas.append("`!freno publicacion|medios|todo [minutos] [motivo]` · `!freno soltar`")
            return "\n".join(lineas)

        orden = partes[1].lower()
        if orden in ("soltar", "quitar", "off"):
            nuevo = self.brake.release(actor=author_name)
            if nuevo.activo:
                return (f"🛑 Solté mi freno, pero sigue puesto desde {nuevo.origen} "
                        f"en «{nuevo.nivel}»: eso no lo controlo yo.")
            return "✅ Freno soltado. Vuelvo a funcionar con normalidad."

        minutos = None
        resto = partes[2:]
        if resto and resto[0].isdigit():
            minutos = float(resto[0])
            resto = resto[1:]
        try:
            nuevo = self.brake.engage(orden, motivo=" ".join(resto), actor=author_name,
                                      minutos=minutos)
        except ValueError as exc:
            return f"❌ {exc}"
        caducidad = f" durante {minutos:g} min" if minutos else " hasta que lo sueltes"
        return (f"🛑 Freno puesto en «{nuevo.nivel}»{caducidad}. {self.brake.describe()}\n"
                "_Sigo respondiendo a quien me hable: enmudecerme no es frenarme._")

    def _handle_state_command(self, content: str, author_name: str) -> str:
        """Inventario del estado durable: qué guarda, quién lo escribe y qué acciona."""
        from ..core.state_registry import StateRegistry

        auditoria = StateRegistry().audit()
        lineas = [
            "🗄️ **Estado durable de Yuki**",
            f"{auditoria['presentes']}/{len(auditoria['piezas'])} piezas presentes · "
            f"{auditoria['bytes_totales'] / 1024:.1f} KiB",
            "",
        ]
        for pieza in auditoria["piezas"]:
            if not pieza["exists"]:
                continue
            etiquetas = []
            if pieza["holds_personal_data"]:
                etiquetas.append("datos personales")
            if pieza["actionability"].startswith("ALTA"):
                etiquetas.append("acciona sola")
            sufijo = f" _({', '.join(etiquetas)})_" if etiquetas else ""
            lineas.append(f"• `{pieza['id']}` — {pieza['bytes'] / 1024:.1f} KiB{sufijo}")
        lineas += ["", "Derechos de una persona: `!olvidar <user_id> confirmar [motivo]`. "
                       "Exportación completa desde la terminal: `python3 cli.py estado --exportar <id>`."]
        return "\n".join(lineas)

    def _handle_forget_command(self, content: str, author_name: str) -> str:
        """
        Ejercita el derecho de supresión sobre una persona concreta.

        Pide confirmación explícita en el propio comando: es irreversible por
        definición —un olvido que se pueda deshacer no es un olvido— y la
        autenticación del DM no basta para un dedo que resbala.
        """
        from ..core.state_registry import StateRegistry

        partes = content.split()
        if len(partes) < 2:
            return ("Uso: `!olvidar <user_id> confirmar [motivo]`. Sin `confirmar` sólo te "
                    "digo qué se borraría.")

        sujeto = partes[1]
        registro = StateRegistry()

        if "confirmar" not in [p.lower() for p in partes[2:]]:
            try:
                previo = registro.subject_export(sujeto)
            except Exception as exc:
                return f"❌ No pude consultar el estado de `{sujeto}`: {type(exc).__name__}"
            return (f"🗑️ De `{sujeto}` guardo **{previo['recuerdos_total']} recuerdo(s)**"
                    + (" y el registro de haberle declarado mi naturaleza"
                       if previo["declaraciones_de_naturaleza"] else "")
                    + ".\nEsto es irreversible. Para ejecutarlo: "
                    f"`!olvidar {sujeto} confirmar [motivo]`.")

        motivo = " ".join(p for p in partes[2:] if p.lower() != "confirmar")
        try:
            recibo = registro.subject_forget(sujeto, actor=author_name, reason=motivo)
        except ValueError as exc:
            return f"❌ {exc}"
        except Exception as exc:
            return f"❌ El olvido falló: {type(exc).__name__}. No doy por borrado lo que no consta."
        return (f"🗑️ Olvidado `{sujeto}`: {recibo['recuerdos_borrados']} recuerdo(s) y "
                f"{recibo['declaraciones_borradas']} declaración(es). "
                "Queda constancia de la operación, no de lo borrado.")

    def _handle_rituals_command(self, content: str, author_id: str, author_name: str) -> str:
        """
        Ritmos: los del proyecto, los propios de Yuki y lo que espera respuesta.

        `!ritmos` los lista; `!ritmo aprobar|rechazar|retirar <id>` decide. La
        decisión es siempre del Productor: Yuki propone y aquí se le contesta.
        """
        from ..core.rituals import RitualError

        partes = content.split()
        if partes[0] in ("!ritmos",) and len(partes) == 1:
            lineas = ["🎏 **Ritmos de Yuki**", "", "**Del proyecto** (config.yaml):"]
            for nombre, job in self.agent.cron.jobs.items():
                if nombre.startswith("propio_"):
                    continue
                estado = "activo" if job["enabled"] else "en pausa"
                lineas.append(f"• `{nombre}` — `{job['cron_expr']}` ({estado})")

            propios = self.agent.rituals.aprobados()
            lineas += ["", "**Propios** (propuestos por ella, aprobados por ti):"]
            lineas += [f"• {r.describe()}   ·  {r.runs} ejecución(es)" for r in propios] or ["• Ninguno todavía."]

            pendientes = self.agent.rituals.pendientes()
            lineas += ["", "**Esperando tu respuesta:**"]
            lineas += [p.describe() for p in pendientes] or ["• Nada pendiente."]
            return "\n".join(lineas)

        if len(partes) >= 3 and partes[0] == "!ritmo":
            accion, ritual_id = partes[1].lower(), partes[2]
            nota = " ".join(partes[3:])
            try:
                if accion in ("aprobar", "aprueba", "si", "sí"):
                    ritmo = self.agent.rituals.approve(ritual_id, actor=author_name, nota=nota)
                    registrados = self.agent.register_own_rituals()
                    return (f"✅ Ritmo **{ritmo.name}** aprobado y en el planificador "
                            f"(`{ritmo.cron}`). Ritmos propios activos: {registrados}.")
                if accion in ("rechazar", "rechaza", "no"):
                    ritmo = self.agent.rituals.reject(ritual_id, actor=author_name, nota=nota)
                    return f"🚫 Ritmo **{ritmo.name}** rechazado. Queda constancia del motivo."
                if accion in ("retirar", "retira", "pausar"):
                    ritmo = self.agent.rituals.retire(ritual_id, actor=author_name, nota=nota)
                    self.agent.cron.jobs.pop(f"propio_{ritmo.name}", None)
                    return f"📴 Ritmo **{ritmo.name}** retirado del planificador."
            except RitualError as exc:
                return f"❌ {exc}"

        return ("Uso: `!ritmos` para verlos · "
                "`!ritmo aprobar|rechazar|retirar <id> [motivo]` para decidir.")

    def _handle_agency_command(self, content: str, author_id: str) -> str:
        """
        Libre albedrío: verlo y afinarlo en caliente.

        `!albedrio` muestra el carácter y lo aprendido; `!albedrio <clave>
        <valor>` ajusta espontaneidad, audacia, constancia, umbral, energía
        mínima o acciones por día sin desplegar nada.
        """
        partes = content.split()
        if len(partes) == 1:
            estado = self.agent.agency_loop.estado()
            politica = estado["politica"]
            pesos = " · ".join(f"{a}:{v}" for a, v in sorted(estado["pesos_por_accion"].items()))
            # El censo contesta la pregunta que el Productor hace de verdad —«¿por
            # qué no hace nada?»—, y su ausencia contesta una distinta y más
            # urgente: que el bucle ni siquiera está evaluando.
            censo = estado.get("censo_de_ciclos") or {}
            porque = (" · ".join(f"{motivo} {veces}"
                                 for motivo, veces in sorted(censo.items(), key=lambda p: -p[1]))
                      if censo else "todavía no ha evaluado ni un ciclo (el bucle no corre)")
            return (
                "🌱 **Libre albedrío de Yuki**\n"
                f"• **Iniciativa:** {'activa' if politica['enabled'] else 'apagada'}\n"
                f"• **Espontaneidad:** {politica['espontaneidad']} · "
                f"**audacia:** {politica['audacia']} · **constancia:** {politica['constancia']}\n"
                f"• **Umbral ahora:** {estado['umbral_ahora']} (base {politica['umbral_base']}, "
                f"aburrimiento {estado['aburrimiento']})\n"
                f"• **Acciones hoy:** {estado['acciones_hoy']}/{politica['acciones_por_dia']} · "
                f"**impulsos vivos:** {estado['impulsos_vivos']} · "
                f"**esperando eco:** {estado['esperando_eco']}\n"
                f"• **Lo que le funciona:** {pesos}\n"
                f"• **Por qué no actúa:** {porque}\n"
                f"• **Fases en silencio:** {', '.join(politica['fases_en_silencio'])}\n"
                "Ajusta con `!albedrio espontaneidad 0.7` · claves: espontaneidad, audacia, "
                "constancia, umbral, energia_minima, acciones_por_dia."
            )

        claves = {
            "espontaneidad": "agency.spontaneity",
            "audacia": "agency.audacity",
            "constancia": "agency.constancy",
            "umbral": "agency.min_intensity",
            "energia_minima": "agency.min_energy",
            "acciones_por_dia": "agency.max_actions_per_day",
        }
        if len(partes) >= 3 and partes[1].lower() in claves:
            ruta = claves[partes[1].lower()]
            crudo = partes[2].replace(",", ".")
            try:
                valor = int(crudo) if ruta.endswith("max_actions_per_day") else float(crudo)
                resultado = self.agent.reconfigure_runtime(
                    ruta, valor, actor="producer",
                    reason=" ".join(partes[3:])[:200] or "ajuste por DM",
                )
            except (ValueError, TypeError) as exc:
                return f"❌ Valor no válido: {exc}"
            return (f"🌱 `{partes[1].lower()}` → **{resultado['value']}**. "
                    "Tiene efecto en el próximo ciclo de agencia, sin desplegar nada.")

        return ("Uso: `!albedrio` para verlo · `!albedrio <clave> <valor>` para ajustarlo. "
                f"Claves: {', '.join(sorted(claves))}.")

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
        frenada = self.brake.blocked_reason("publicar")
        if frenada:
            return (f"🛑 No abro el Salón ahora mismo: {frenada}. "
                    "Suéltalo con `!freno soltar` cuando quieras que siga.")
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

    def _launch_dm_media_delivery(self, author_id: str, author_name: str, content: str, origin_channel) -> str:
        """El trabajo pesado no bloquea el gateway; los binarios se entregan en el mismo DM."""
        if origin_channel is None:
            return "❌ No tengo un canal de DM para entregar los archivos."
        frenada = self.brake.blocked_reason("medios")
        if frenada:
            return (f"🛑 No genero medios ahora mismo: {frenada}. "
                    "Suéltalo con `!freno soltar` cuando quieras que siga.")
        job = self.media_jobs.create(
            requester_id=author_id,
            order=content,
            channel_id=getattr(origin_channel, "id", None),
            steps=MEDIA_JOB_STEPS,
        )
        self._spawn_media_job(job, author_id, author_name, content, origin_channel)
        return (
            "⚡ Producción multimedia iniciada como trabajo `" + job.id + "`. Generaré primero la canción "
            "y después los segmentos de vídeo; sólo confirmaré y adjuntaré archivos reales en este DM. "
            "Si el proceso se reinicia, el trabajo se reanuda desde el último paso verificado."
        )

    def _spawn_media_job(self, job, author_id: str, author_name: str, content: str, channel) -> bool:
        """Lanza el trabajo si no hay ya una tarea viva para él. Devuelve si lo lanzó."""
        if job.id in self._active_job_ids:
            logger.info("Trabajo multimedia %s ya está en curso; no se relanza.", job.id)
            return False

        self._active_job_ids.add(job.id)
        task = asyncio.create_task(
            self._run_dm_media_delivery(author_id, author_name, content, channel, job=job)
        )
        self._workflow_tasks.add(task)

        def _al_terminar(finalizada) -> None:
            self._workflow_tasks.discard(finalizada)
            self._active_job_ids.discard(job.id)

        task.add_done_callback(_al_terminar)
        return True

    async def resume_pending_media_jobs(self) -> int:
        """
        Reanuda tras un reinicio los trabajos multimedia que quedaron a medias.

        Se llama al conectar el gateway. Los pasos ya verificados no se vuelven a
        generar —Veo se factura por segundo—, así que reanudar cuesta sólo lo que
        falta. Un trabajo sin canal recuperable se cierra como abandonado en vez
        de quedarse colgado prometiendo una entrega que nadie hará.
        """
        reanudados = 0
        for job in self.media_jobs.resumable():
            if job.id in self._active_job_ids:
                # Reconexión del gateway con el trabajo todavía corriendo.
                continue
            if job.requester_id not in self.paired_producer_ids:
                self.media_jobs.abandon(job, "el solicitante ya no es un Productor emparejado")
                continue
            channel = await self._recover_dm_channel(job)
            if channel is None:
                self.media_jobs.abandon(job, "no se pudo recuperar el DM de entrega")
                continue
            job.resumed += 1
            self.media_jobs.save(job)
            logger.warning(
                "Reanudando trabajo multimedia %s (%s), reanudación nº %d",
                job.id, describe_media_job(job), job.resumed,
            )
            if self._spawn_media_job(job, job.requester_id, "productor", job.order, channel):
                reanudados += 1
        return reanudados

    async def _recover_dm_channel(self, job):
        """Recupera el DM del Productor; sin canal no hay entrega que reanudar."""
        try:
            user = self.client.get_user(int(job.requester_id)) or await self.client.fetch_user(int(job.requester_id))
            if user is None:
                return None
            return user.dm_channel or await user.create_dm()
        except (ValueError, AttributeError, discord.HTTPException) as exc:
            logger.warning("No pude recuperar el DM del trabajo %s: %s", job.id, type(exc).__name__)
            return None

    def _library_entry(self, kind: str, keywords: tuple[str, ...]) -> Optional[Dict[str, Any]]:
        """Selecciona una obra existente por metadatos, sin interpretar rutas del usuario."""
        library = self.agent.creation_library
        entries = library.list_entries().get("entries", [])
        candidates = [entry for entry in entries if entry.get("kind") == kind]
        for entry in candidates:
            haystack = f"{entry.get('title', '')} {entry.get('source', '')}".casefold()
            if any(word in haystack for word in keywords):
                return entry
        return candidates[-1] if candidates else None

    def _library_file(self, entry: Optional[Dict[str, Any]]) -> Optional[str]:
        if not entry:
            return None
        path = (self.agent.creation_library.root / entry["path"]).resolve()
        root = self.agent.creation_library.root.resolve()
        return str(path) if path.is_relative_to(root) and path.is_file() else None

    @staticmethod
    def _concat_videos(paths: List[str]) -> Optional[str]:
        """Une clips de Veo ya verificados; no ejecuta shell ni acepta rutas externas."""
        if not paths or not all(Path(path).is_file() for path in paths):
            return None
        output_dir = Path(paths[0]).parent
        destination = output_dir / f"yuki_salon_final_{int(time.time())}.mp4"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", dir=output_dir, delete=False, encoding="utf-8") as listing:
            for path in paths:
                listing.write("file '" + str(Path(path).resolve()).replace("'", "'\\''") + "'\n")
            listing_path = listing.name
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing_path,
                 "-c", "copy", str(destination)],
                capture_output=True, text=True, timeout=90, check=False,
            )
            return str(destination) if result.returncode == 0 and destination.is_file() else None
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            Path(listing_path).unlink(missing_ok=True)

    async def _run_dm_media_delivery(self, author_id: str, author_name: str, content: str, channel,
                                     job=None) -> None:
        """
        Genera canción cantada y vídeo desde obras existentes; entrega sólo adjuntos reales.

        El trabajo es durable: cada paso se persiste en cuanto tiene fichero
        verificado, así que un reinicio a mitad no repite lo ya generado ni deja
        el encargo perdido. Reanudar cuesta únicamente los pasos que faltan.
        """
        async def report(text: str) -> None:
            await self._send_long(channel, text)

        if job is None:
            job = self.media_jobs.create(
                requester_id=author_id, order=content,
                channel_id=getattr(channel, "id", None), steps=MEDIA_JOB_STEPS,
            )
        job.channel_id = str(getattr(channel, "id", "")) or job.channel_id

        try:
            lyrics_entry = self._library_entry("palabra", ("letra", "lirica", "poema", "herrumbre"))
            lyrics_path = self._library_file(lyrics_entry)
            if not lyrics_entry or not lyrics_path:
                self.media_jobs.abandon(job, "sin letra verificable en Biblioteca")
                await report("❌ No encuentro una letra verificable en la Biblioteca; no generaré una canción sin texto fuente.")
                return
            lyrics = self.agent.creation_library.read_entry(lyrics_entry["id"]).get("content", "")
            if len(lyrics.strip()) < 80:
                self.media_jobs.abandon(job, "letra demasiado breve")
                await report("❌ La letra recuperada es demasiado breve para una canción; no la presentaré como canto completo.")
                return

            # --- Paso 1: canción -------------------------------------------------
            song_step = job.ensure_step("cancion", "cancion")
            if song_step.is_done():
                await report(f"🎵 Reanudo el trabajo `{job.id}`: la canción ya estaba generada y verificada; no la regenero.")
            elif song_step.exhausted():
                await report(f"⚠️ No repito la canción: ya falló {song_step.attempts} veces ({song_step.error}).")
            else:
                await report("🎵 Generando canción con la letra archivada. El adjunto sólo saldrá si Lyria devuelve audio real.")
                song_prompt = (
                    "Create a 90-second Spanish sung song, not an instrumental. Female mature serene voice, "
                    "72 BPM, restrained vibrato, Japanese/Korean neo-traditional palette with shamisen and koto, "
                    "industrial cold water and rust atmosphere. Sing these exact lyrics in Spanish, preserving stanza "
                    "and chorus structure:\n" + lyrics[:12000]
                )
                song_step.attempts += 1
                self.media_jobs.save(job)
                song = await self.agent.nous_portal.generate_music_flow(
                    title="Herrumbre y Escarcha — voz", prompt=song_prompt,
                    engine="lyria-3-pro-preview", duration_seconds=90, bpm=72, scale="Insen",
                )
                song_path = song.get("local_path") if song.get("status") == "success" else None
                if song_path and Path(song_path).is_file():
                    # Lyria canta; el respaldo local no. La nota viaja con el paso
                    # para que la entrega —incluso tras un reinicio— no llame
                    # canción a una maqueta instrumental.
                    song_step.mark_done(song_path, note=(
                        "🎵 Canción con letra — archivo generado" if song.get("sung")
                        else "🎼 " + (song.get("note") or "Maqueta local: no es una canción cantada.")
                    ))
                    self.media_jobs.save(job)
                    await asyncio.to_thread(self.agent.creation_library.inventory)
                elif song.get("budget_exceeded"):
                    # Un tope de presupuesto no es un fallo del paso: mañana el
                    # mismo trabajo cabe. No gasta intento ni marca fallo.
                    song_step.attempts -= 1
                    self.media_jobs.save(job)
                    await report(f"💳 Canción aplazada por presupuesto: {song.get('error')}")
                else:
                    detalle = song.get("error") or song.get("note") or "sin detalle"
                    song_step.mark_failed(detalle)
                    self.media_jobs.save(job)
                    await report(f"⚠️ No se generó canción: {detalle}")
            if song_step.is_done() and not song_step.delivered:
                if await self._send_file(channel, song_step.path,
                                         song_step.note or "🎵 Pista de audio generada"):
                    song_step.delivered = True
                    self.media_jobs.save(job)
                else:
                    await report("⚠️ La canción se generó, pero Discord rechazó el adjunto; no la doy por entregada.")

            # --- Paso 2: segmentos de vídeo --------------------------------------
            script_entry = self._library_entry("palabra", ("guion", "audiovisual", "video"))
            script = ""
            if script_entry:
                script = self.agent.creation_library.read_entry(script_entry["id"]).get("content", "")
            visual_entry = self._library_entry("visual", ("herrumbre", "salon", "escarcha"))
            visual_path = self._library_file(visual_entry)
            hechos = sum(1 for i in range(1, len(MEDIA_STORYBOARD) + 1)
                         if job.ensure_step(f"clip_{i}", "clip").is_done())
            if hechos:
                await report(f"🎬 {hechos} de {len(MEDIA_STORYBOARD)} segmentos ya estaban verificados; sólo genero los que faltan.")
            else:
                await report("🎬 Generando cuatro segmentos de 8 s y ensamblándolos; no sustituiré el vídeo por un marcador.")
            clips: List[str] = []
            for index, beat in enumerate(MEDIA_STORYBOARD, 1):
                clip_step = job.ensure_step(f"clip_{index}", "clip")
                if clip_step.is_done():
                    clips.append(clip_step.path)
                    continue
                if clip_step.exhausted():
                    await report(f"⚠️ Segmento {index} descartado tras {clip_step.attempts} intentos: {clip_step.error}")
                    break
                prompt = (
                    "Cinematic 16:9, 24 fps, slow meditative camera, no fast cuts. " + beat +
                    " Guion de referencia: " + (script[:2500] or "Herrumbre y Escarcha, agua, hierro e invierno.")
                )
                clip_step.attempts += 1
                self.media_jobs.save(job)
                video = await self.agent.nous_portal.generate_video_frontier(
                    prompt=prompt, duration_seconds=8, aspect_ratio="16:9", image_path=visual_path,
                )
                path = video.get("local_path") if video.get("status") == "success" else None
                if path and Path(path).is_file():
                    clip_step.mark_done(path)
                    self.media_jobs.save(job)
                    clips.append(path)
                elif video.get("budget_exceeded"):
                    clip_step.attempts -= 1
                    self.media_jobs.save(job)
                    await report(
                        f"💳 Segmento {index} aplazado por presupuesto: {video.get('error')}. "
                        "El trabajo queda pendiente; no se pierde lo generado."
                    )
                    break
                else:
                    detalle = video.get("error") or video.get("note") or "sin detalle"
                    clip_step.mark_failed(detalle)
                    self.media_jobs.save(job)
                    await report(f"⚠️ Segmento {index} no generado: {detalle}")
                    break

            # --- Paso 3: montaje y entrega ---------------------------------------
            montaje = job.ensure_step("montaje", "montaje")
            final_video = montaje.path if montaje.is_done() else None
            if final_video is None and len(clips) == len(MEDIA_STORYBOARD):
                final_video = await asyncio.to_thread(self._concat_videos, clips)
                if final_video:
                    montaje.mark_done(final_video)
                else:
                    montaje.mark_failed("ffmpeg no produjo el vídeo final")
                self.media_jobs.save(job)
            if final_video:
                await asyncio.to_thread(self.agent.creation_library.inventory)
                if not montaje.delivered:
                    if await self._send_file(channel, final_video, "🎬 Vídeo final — 32 s, cuatro segmentos ensamblados"):
                        montaje.delivered = True
                        self.media_jobs.save(job)
                    else:
                        await report("⚠️ El vídeo se generó, pero Discord rechazó el adjunto; no lo doy por entregado.")
            elif clips:
                await report("⚠️ No pude ensamblar el vídeo final; adjunto sólo los segmentos reales disponibles.")
                for index, path in enumerate(clips, 1):
                    clip_step = job.ensure_step(f"clip_{index}", "clip")
                    if clip_step.delivered:
                        continue
                    if await self._send_file(channel, path, f"🎬 Segmento {index}"):
                        clip_step.delivered = True
                        self.media_jobs.save(job)
            else:
                await report("⚠️ No se generó ningún segmento de vídeo; no hay vídeo que adjuntar.")

            # El trabajo sólo se cierra cuando no queda nada por hacer. Cerrarlo
            # con pasos pendientes sería dar por entregado lo que no existe, y
            # además impediría reanudarlo tras el siguiente arranque.
            entrega = job.ensure_step("entrega", "entrega")
            restantes = [p for p in job.pending_steps() if p.id != "entrega"]
            agotados = [p for p in job.steps if p.exhausted()]
            if agotados:
                # Un paso agotado bloquea el encargo entero: seguir reanudándolo
                # sólo quemaría crédito en los pasos que sí funcionan. Se cierra
                # diciendo cuál falló, y hace falta una orden nueva.
                motivo = f"paso {agotados[0].id} agotado tras {agotados[0].attempts} intentos"
                self.media_jobs.abandon(job, motivo)
                await report(
                    f"⛔ Trabajo `{job.id}` cerrado sin completar: {motivo} "
                    f"({agotados[0].error}). Lo entregado consta adjunto; para retomarlo hace falta "
                    "una orden nueva."
                )
            elif restantes:
                self.media_jobs.save(job)
                await report(
                    f"⏸️ Trabajo `{job.id}` incompleto: quedan "
                    f"{', '.join(p.id for p in restantes)}. No los doy por entregados; "
                    "el trabajo queda registrado y se reanuda en el próximo arranque."
                )
                logger.warning("Trabajo multimedia incompleto: %s", describe_media_job(job))
            else:
                entrega.mark_done()
                entrega.delivered = True
                self.media_jobs.finish(job)
                logger.info("Trabajo multimedia cerrado: %s", describe_media_job(job))
        except Exception:
            logger.exception("Fallo en producción multimedia por DM")
            self.media_jobs.save(job)
            await report(
                "❌ La producción multimedia falló; no doy por generados ni entregados archivos que no consten "
                f"adjuntos. El trabajo `{job.id}` queda registrado y reanudable desde el último paso verificado."
            )

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
