"""
El Salón: abrir un canal en un servidor autorizado y producir la obra allí.

Es el otro camino de producción, el que publica en público en vez de adjuntar
en el DM, y el que gastaba sin decir el título ni el presupuesto. Vive aparte
porque su trabajo no es el encargo durable sino Discord mismo: encontrar el
servidor, comprobar permisos efectivos y no consumir generación que después no
podría publicar.
"""

import asyncio
import logging
from typing import Set

import discord

from .discord_intents import (
    channel_slug as _channel_slug,
    extract_production_target as _extract_production_target,
    extract_production_theme as _extract_production_theme,
    fold as _fold,
)

logger = logging.getLogger("Yuki.DiscordAdapter")

# El encargo por defecto del Salón, cuando la petición no nombra otro. Es un
# valor por defecto y no una constante escondida: antes la letra, la partitura,
# las tres imágenes y el vídeo estaban escritos a mano sobre este título, así
# que abrir un Salón para otra cosa producía igualmente ésta.
TEMA_POR_DEFECTO = "Herrumbre y Escarcha"
IMAGINARIO_POR_DEFECTO = "agua, hierro, muelle, invierno y una esperanza contenida"


class SalonDeDiscord:
    """
    Abrir el Salón y publicar la secuencia de producción en él.

    Mixin de `DiscordAdapter`: necesita el cliente de Discord (`self.client`),
    la allowlist de servidores y los envíos del adaptador. El presupuesto lo
    dice con la misma línea que el encargo por DM, para que los dos caminos no
    puedan divergir en lo que prometen.
    """

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
        tema = _extract_production_theme(content) or TEMA_POR_DEFECTO
        # Qué obra y a cuánto sale, antes de empezar. Este camino gastaba en
        # canción, tres imágenes y vídeo sin mencionar el presupuesto ni el
        # título, que además estaba escrito a mano.
        return (
            f"⚡ He iniciado la producción de «{tema}» en el canal de Discord. "
            + self._linea_de_presupuesto("1 pista, 3 imágenes y 6 s de vídeo", segundos_de_video=6)
            + " Iré publicando allí cada resultado y dejaré explícitos los medios "
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

    async def _run_discord_production(
        self,
        author_id: str,
        author_name: str,
        content: str,
        origin_channel,
    ) -> None:
        """Ejecuta el encargo multimodal sólo para el productor emparejado."""
        guild_name, requested_channel_name = _extract_production_target(content)
        # El tercer entrecomillado nombra la obra. Sin él se produce la de
        # siempre, que es el comportamiento anterior; con él, deja de estarlo.
        tema = _extract_production_theme(content) or TEMA_POR_DEFECTO
        imaginario = (IMAGINARIO_POR_DEFECTO if tema == TEMA_POR_DEFECTO
                      else f"el imaginario que evoca «{tema}»")
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
                    f"{tema}: 3 estrofas, estribillo repetido y puente. "
                    f"Imágenes de {imaginario}."
                ),
                channel_type="discord_channel",
                active_role="producer",
                # `music_composition` estaba declarada en `config.yaml` desde el
                # principio y no la leía nadie: un dial que no gira. Escribir la
                # letra de una canción es exactamente su tarea.
                route="music_composition",
            )
            await self._send_long(channel, f"### Poema / letra — {tema}\n{poem}")
            await asyncio.to_thread(self.agent.creation_library.save_text, tema, poem,
                                    source=f"discord:{guild.id}/{channel.id}")

            music_engine = "midi_only"
            media_creator = getattr(self.agent, "media_creator", None)
            portal = getattr(media_creator, "portal", None)
            vertex = getattr(portal, "vertex", None)
            if getattr(vertex, "is_available", lambda: False)():
                music_engine = getattr(vertex, "music_model", "lyria-3-pro-preview")

            music = await self.agent.media_creator.compose_beat_structure(
                title=tema,
                bpm=82,
                scale="insen",
                mood=imaginario,
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
                f"el exterior del Salón, con {imaginario}",
                "el interior del Salón: té, acero y la luz contenida de la estación",
                f"la letra de «{tema}» convertida en paisaje abstracto",
            ]
            if can_attach:
                for index, visual_prompt in enumerate(visual_prompts, 1):
                    art = await self.agent.media_creator.create_single_cover(
                        track_title=f"{tema} {index}",
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
                    prompt=("La cámara recorre el Salón de té y acero, despacio y sin cortes bruscos, "
                            f"con el imaginario de «{tema}»: {imaginario}."),
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
