"""
Producción multimedia por DM: el encargo durable, paso a paso, hasta el adjunto.

Es lo más caro que hace Yuki —Veo se factura por segundo— y por eso lo que más
salvaguardas acumula: el pedido gobierna el plan, un paso verificado no se
regenera, un reinicio reanuda por donde iba y nada se da por entregado sin que
conste el adjunto. Estaba dentro del adaptador de Discord, mezclado con el
gateway y con los comandos de gobierno; separarlo deja a la vista que esto no
depende de Discord más que para adjuntar.
"""

import asyncio
import hashlib
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord

from .discord_intents import fold as _fold
from .encargo import leer_encargo
from ..core.spend_budget import SpendLedger
from ..tools import (criterio_audiovisual, criterio_musical, criterio_visual, cuaderno,
                     receta)
from ..tools.media_jobs import TERMINADO, describe_job as describe_media_job

logger = logging.getLogger("Yuki.DiscordAdapter")

# Guion del encargo audiovisual. Vive aquí y no dentro del bucle porque el
# número de segmentos define los pasos del trabajo durable: cambiarlo cambia
# lo que un reinicio considera "ya hecho".
MEDIA_STORYBOARD = (
    "Exterior del muelle: lluvia sobre acero oxidado, la escarcha empieza a aparecer.",
    "Entrada al Salón: vapor de té, seda oscura y reflejos de urushi sobre hierro.",
    "Interior: la intérprete respira y el poema encuentra su estribillo entre cuerdas tensas.",
    "Salida: agua, niebla y una luz contenida sobre el metal; final pausado, sin corte brusco.",
)


# Pasos facturables del encargo, ya no fijos: los deriva `encargo.leer_encargo`
# del texto del pedido, porque una tupla constante era la razón de que pedir una
# portada no produjera portada y de que «esta vez con X» devolviera lo mismo.
def _plan_del_encargo(pedido: str):
    """Plan del pedido. Determinista sobre el mismo texto: reanudar lo recompone."""
    return leer_encargo(pedido, len(MEDIA_STORYBOARD))

def _mismo_contenido(uno: str, otro: str) -> bool:
    """
    Si dos ficheros entregados son el mismo. Tamaño primero: leer un vídeo
    entero para descubrir que pesa distinto es tiempo tirado en una e2-small.
    """
    try:
        primero, segundo = Path(uno), Path(otro)
        if not (primero.is_file() and segundo.is_file()):
            return False
        if primero.stat().st_size != segundo.stat().st_size:
            return False
        digest = [hashlib.sha256(ruta.read_bytes()).hexdigest() for ruta in (primero, segundo)]
        return digest[0] == digest[1]
    except OSError:
        # No poder comparar no es haber comprobado que son distintos: se calla,
        # que es lo único honesto sin la lectura hecha.
        return False


class ProduccionMultimedia:
    """
    El encargo multimedia del DM, desde el acuse hasta el último adjunto.

    Mixin de `DiscordAdapter`: usa `self.agent`, `self.brake`, `self.media_jobs`
    y los envíos del adaptador (`_send_long`, `_send_file`), que son lo único
    que de verdad necesita de Discord.
    """

    # --- Arranque del encargo: lo que se dice antes de gastar ---------------

    def _launch_dm_media_delivery(self, author_id: str, author_name: str, content: str, origin_channel) -> str:
        """El trabajo pesado no bloquea el gateway; los binarios se entregan en el mismo DM."""
        if origin_channel is None:
            return "❌ No tengo un canal de DM para entregar los archivos."
        frenada = self.brake.blocked_reason("medios")
        if frenada:
            return (f"🛑 No genero medios ahora mismo: {frenada}. "
                    "Suéltalo con `!freno soltar` cuando quieras que siga.")
        plan = _plan_del_encargo(content)
        repetido = self._encargo_repetido(content, author_id)
        if repetido is not None:
            return self._aviso_de_repeticion(repetido)
        job = self.media_jobs.create(
            requester_id=author_id,
            order=content,
            channel_id=getattr(origin_channel, "id", None),
            steps=plan.steps(),
        )
        self._spawn_media_job(job, author_id, author_name, content, origin_channel)
        # El alcance se acusa antes de gastar: si el pedido no incluye algo, el
        # Productor tiene que enterarse ahora y no por su ausencia al final.
        return (
            "⚡ Producción multimedia iniciada como trabajo `" + job.id + "`. Voy a producir: "
            + plan.resumen() + ". " + self._coste_previsto(plan) + " Sólo confirmaré y adjuntaré "
            "archivos reales en este DM. Si el proceso se reinicia, el trabajo se reanuda desde "
            "el último paso verificado." + self._nota_del_salon(content)
        )

    def _nota_del_salon(self, pedido: str) -> str:
        """
        Qué puede el Salón cuando lo ofrecen como canal de entrega.

        «Envíamelo por Salón o por aquí» quedó sin respuesta: el Salón ni se usó
        ni se mencionó. Ahora se contesta, y con lo que hay: sirve la obra sólo
        si la instancia tiene `SALON_API_TOKEN`, porque servir bytes a quien
        alcance el puerto no se enciende en silencio.
        """
        if "salon" not in _fold(pedido or ""):
            return ""
        if os.getenv("SALON_API_TOKEN", "").strip():
            return ("\nY sí, por el Salón también: lo que quede en `output/` se baja de "
                    "`/api/outputs/<categoría>/<nombre>` con la credencial.")
        return ("\nPor el Salón no puedo mandártelo: sin `SALON_API_TOKEN` declarado sólo "
                "enumera nombres, no sirve el fichero. Aquí sí va como adjunto.")

    # --- Guardas contra el gasto repetido -----------------------------------

    # Frases con las que el Productor manda repetir a sabiendas. Sin ellas, un
    # pedido idéntico al de hace un rato es casi siempre que lo anterior no
    # sirvió, y volver a generarlo sólo quema crédito.
    REPETIR_IGUALMENTE = ("de todos modos", "aun asi", "igualmente", "repite igual",
                          "hazlo de nuevo igual", "aunque sea lo mismo")

    # Cuánto dura la sospecha de repetición. Más allá, un pedido igual suele ser
    # un encargo nuevo de verdad.
    VENTANA_REPETICION_SEGUNDOS = 90 * 60

    def _encargo_repetido(self, content: str, author_id: str):
        """
        El mismo pedido, palabra por palabra, con la entrega anterior todavía viva.

        El 9 de septiembre se facturaron ~96 s de vídeo para entregar tres veces
        lo mismo. La causa de fondo ya está arreglada —el pedido gobierna el
        encargo—, pero un pedido idéntico sigue produciendo un resultado
        idéntico, y eso ahora se dice antes de gastar en vez de después.
        """
        texto = _fold(content or "")
        # Cualquier cambio en el texto ya libera la guarda —el pedido pasa a ser
        # otro—, así que el consejo «añade "de todos modos"» funciona solo. Esta
        # comprobación es para la vez siguiente: un pedido forzado repetido
        # idéntico no puede volver a bloquearse pidiéndole que añada una frase
        # que ya está escrita.
        if any(frase in texto for frase in self.REPETIR_IGUALMENTE):
            return None
        ahora = time.time()
        for trabajo in self.media_jobs.list_jobs():
            if trabajo.requester_id != str(author_id) or trabajo.status != TERMINADO:
                continue
            if ahora - trabajo.updated_at > self.VENTANA_REPETICION_SEGUNDOS:
                continue
            if _fold(trabajo.order) != texto:
                continue
            # Sin ficheros vivos no hay nada que reutilizar: repetir es lo
            # correcto, no un despilfarro.
            if any(paso.is_done() and paso.path for paso in trabajo.steps):
                return trabajo
        return None

    def _aviso_de_repeticion(self, trabajo) -> str:
        """Lo que ya existe, y qué hace falta para que salga distinto."""
        entregados = [Path(paso.path).name for paso in trabajo.steps
                      if paso.is_done() and paso.path]
        minutos = max(1, int((time.time() - trabajo.updated_at) // 60))
        return (
            f"↩️ Este pedido es palabra por palabra el del trabajo `{trabajo.id}`, de hace "
            f"{minutos} minuto(s): {', '.join(entregados)}. No lo repito, porque saldría lo "
            "mismo y el vídeo se factura por segundo.\n"
            "Dime **qué cambia** —otra letra, otro número de segmentos, sólo la portada— o "
            "nombra la obra por su identificador de Biblioteca. Si aun así lo quieres igual, "
            "añade «de todos modos»."
        )

    def _coste_previsto(self, plan) -> str:
        """
        Lo que va a costar y lo que queda hoy, dicho antes de empezar.

        El Productor abrió el hilo con «dispones de créditos, quince días» y el
        encargo se planificó sin mirar el presupuesto ni mencionarlo. Cuesta una
        línea y evita descubrir el tope a mitad.
        """
        segundos = plan.segmentos * 8 if plan.video else 0
        piezas = (f"{segundos} s de vídeo"
                  + (", 1 pista" if plan.cancion else "")
                  + (", 1 imagen" if plan.portada else ""))
        return self._linea_de_presupuesto(piezas, segundos_de_video=segundos)

    def _linea_de_presupuesto(self, piezas: str, segundos_de_video: int = 0) -> str:
        """
        Lo que va a costar y lo que queda hoy. La comparten los dos caminos de
        producción: el del DM y el de abrir un Salón, que gastaba sin decir nada.
        """
        try:
            libro = SpendLedger.from_config(getattr(self.agent, "config", None))
            if not libro.enabled:
                return f"💳 Coste previsto: {piezas}. Sin presupuesto declarado: nada acota este gasto."
            cabe = libro.check("video_segundos", segundos_de_video) if segundos_de_video else None
            aviso = "" if cabe is None or cabe else f" ⚠️ No cabe hoy: {cabe.reason}."
            return (f"💳 Coste previsto: {piezas}. "
                    f"Presupuesto de hoy — {libro.describe()}.{aviso}")
        except Exception as exc:
            # Nunca impedir el encargo por no poder contar el dinero, pero
            # tampoco decir que cabe cuando no se ha podido comprobar.
            logger.warning("No pude leer el presupuesto para el acuse: %s", type(exc).__name__)
            return "💳 No he podido leer el presupuesto ahora mismo; no doy por hecho que quepa."

    # --- Durabilidad: lanzar, reanudar, recuperar el DM ---------------------

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
            channel, definitivo = await self._recover_dm_channel(job)
            if channel is None:
                if definitivo:
                    self.media_jobs.abandon(job, "el Productor ya no es alcanzable en Discord")
                else:
                    # Un 500 de Discord es de este minuto, no del trabajo. Antes
                    # se abandonaba igual, y con él los clips ya pagados.
                    logger.warning(
                        "Trabajo multimedia %s en espera: Discord no devolvió el DM ahora; "
                        "se reintenta en el próximo arranque.", job.id,
                    )
                continue
            job.resumed += 1
            self.media_jobs.save(job)
            logger.warning(
                "Reanudando trabajo multimedia %s (%s), reanudación nº %d",
                job.id, describe_media_job(job), job.resumed,
            )
            # Que un encargo se interrumpiera y se retome se dice en el DM. El
            # Productor vio cuatro segmentos y después silencio: sin esto, la
            # única forma de enterarse era preguntar con `!status`.
            await self._send_long(channel, (
                f"↩️ Retomo el trabajo `{job.id}`, interrumpido por un reinicio: "
                f"{describe_media_job(job)}. Sigo por el primer paso sin verificar; "
                "lo ya generado no se vuelve a pagar."
            ))
            if self._spawn_media_job(job, job.requester_id, "productor", job.order, channel):
                reanudados += 1
        return reanudados

    async def _recover_dm_channel(self, job):
        """
        Recupera el DM del Productor, diciendo además si el fallo es definitivo.

        Devuelve `(canal, definitivo)`. La distinción no es un lujo: antes
        cualquier excepción abandonaba el trabajo para siempre, así que un 500
        de Discord —que se repite bien al arranque siguiente— tiraba un encargo
        con clips ya facturados. Definitivo es sólo que el destinatario no
        exista: una cuenta borrada o un identificador que no es un identificador.
        """
        try:
            user = self.client.get_user(int(job.requester_id)) or await self.client.fetch_user(int(job.requester_id))
        except ValueError:
            logger.warning("Trabajo %s con solicitante ilegible; no hay a quién entregar.", job.id)
            return None, True
        except discord.NotFound:
            logger.warning("Trabajo %s: la cuenta del solicitante ya no existe.", job.id)
            return None, True
        except (AttributeError, discord.HTTPException) as exc:
            logger.warning("No pude recuperar el DM del trabajo %s: %s", job.id, type(exc).__name__)
            return None, False
        if user is None:
            return None, False
        try:
            return (user.dm_channel or await user.create_dm()), False
        except (AttributeError, discord.HTTPException) as exc:
            logger.warning("No pude abrir el DM del trabajo %s: %s", job.id, type(exc).__name__)
            return None, False

    # --- Material de partida: lo que ya existe en la Biblioteca -------------

    def _library_entry(self, kind: str, keywords: tuple[str, ...],
                       pedido: str = "") -> Optional[Dict[str, Any]]:
        """
        Selecciona una obra existente por metadatos, sin interpretar rutas.

        Dos correcciones de un incidente real —cuatro encargos seguidos que
        devolvieron lo mismo mientras el Productor repetía «me has devuelto
        exactamente lo mismo»—:

        **Se puede designar una.** Si el pedido nombra un identificador de
        Biblioteca (`palabra-8443c227…`), manda ése. Antes no había forma de
        decir «usa ésta», así que reescribir la letra no servía de nada.

        **Y si no, gana la más reciente.** Antes devolvía la primera que casara
        por palabra clave, que en orden de archivo es la **más vieja**: una letra
        nueva no llegaba a usarse por más veces que se pidiera. Eso no era
        terquedad del modelo, era este bucle.
        """
        library = self.agent.creation_library
        entries = library.list_entries().get("entries", [])
        candidates = [entry for entry in entries if entry.get("kind") == kind]
        if not candidates:
            return None

        designado = re.search(rf"\b{re.escape(kind)}-[0-9a-f]{{6,}}\b", pedido or "",
                              re.IGNORECASE)
        if designado:
            elegido = next((e for e in candidates
                            if e.get("id", "").casefold() == designado.group(0).casefold()), None)
            if elegido:
                logger.info("Obra designada en el pedido: %s", elegido["id"])
                return elegido

        for entry in candidates:
            haystack = f"{entry.get('title', '')} {entry.get('source', '')}".casefold()
            if any(word in haystack for word in keywords):
                return entry
        return candidates[0]

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

    # --- Lo que se declara al entregar --------------------------------------

    def _aviso_de_canto(self, lyrics_entry) -> str:
        """
        Qué motor va a componer esto, dicho antes de que cueste dinero.

        Aquí hubo un error grave y conviene que conste: esta función afirmaba
        «ningún motor musical contratado sirve voz» y **es falso**. Lyria canta
        —`nous_portal` lo dice en su propio código y marca el resultado con
        `sung: True`—, y el 11 de septiembre entregó una canción cantada justo
        después de que este aviso dijera que no saldría. La frase venía de
        `skills/HERRAMIENTAS.md`, que es anterior a Lyria y habla de `suno_v4` y
        `flow_audio`; me fié del documento en vez del código.

        Negar una capacidad que existe es tan falso como prometer una que no, y
        aquí se hizo por intentar evitar lo segundo. Lo honesto no es afirmar
        ninguno de los dos extremos antes de generar: es decir **qué motor va a
        atender y qué significa cada salida**, porque hasta que el proveedor
        responde no se sabe cuál de los dos caminos tocó. La nota del adjunto sí
        lo sabe, y por eso viaja con el paso.
        """
        motor = getattr(self.agent, "media_creator", None)
        vertex = getattr(getattr(motor, "portal", None), "vertex", None)
        hay_vertex = bool(vertex is not None and getattr(vertex, "is_available", lambda: False)())

        titulo = (lyrics_entry or {}).get("title", "la letra archivada")
        cabecera = f"🎵 Generando desde «{titulo}»."
        if hay_vertex:
            return (f"{cabecera} Lo atiende **Lyria**, que sí canta: el prompt le manda la letra "
                    "íntegra con la orden de interpretarla. Si Lyria no responde, cae al respaldo "
                    "local, que **no canta** —es una maqueta instrumental— y en ese caso el "
                    "adjunto lo dirá en su propia nota. No doy por hecho cuál de los dos saldrá.")
        return (f"{cabecera} Sin Vertex configurado no hay motor que cante: sólo puedo darte la "
                "partitura propia sintetizada en local, que es **instrumental**.")

    def _paso_anterior(self, job, step_id: str):
        """El paso del mismo nombre en el trabajo más reciente del mismo Productor."""
        candidatos = [t for t in self.media_jobs.list_jobs()
                      if t.id != job.id and t.requester_id == job.requester_id]
        for anterior in sorted(candidatos, key=lambda t: t.updated_at, reverse=True):
            paso = anterior.step(step_id)
            if paso is not None and paso.is_done() and paso.delivered:
                return anterior, paso
        return None, None

    @staticmethod
    def _pie_de_receta(ruta: Optional[str]) -> str:
        """
        Con qué se hizo, dicho en la propia entrega.

        El 11 de septiembre el Productor preguntó «¿qué es lo que has hecho?» y
        Yuki contestó con un relato técnico detallado —incrustar la fonética en
        la partitura, fijar el tempo, gobernar los contrastes— en un turno con
        **cero herramientas ejecutadas**. No hizo nada de eso: el prompt de la
        canción está escrito en este fichero y ella no lo toca.

        La receta ya se escribía junto al audio y no la veía nadie. Enseñarla
        aquí quita el hueco: quien pregunte qué se hizo tiene la respuesta
        delante, y no hace falta que nadie se la imagine.
        """
        datos = receta.leer(ruta) if ruta else {}
        if not datos:
            return ""
        parametros = datos.get("parametros") or {}
        interesantes = [f"{clave} {valor}" for clave, valor in parametros.items()
                        if clave in ("duration_seconds", "bpm", "escala", "aspect_ratio")]
        detalle = f" · {' · '.join(interesantes)}" if interesantes else ""
        return f"\n-# 🧾 Generado con {datos.get('motor') or 'motor sin declarar'}{detalle}"

    async def _aviso_de_que_ya_salio_asi(self, job, paso) -> str:
        """
        Dice, al entregar, que esto ya salió igual la vez anterior.

        El 9 de septiembre Yuki explicó por qué la canción no salía cantada, el
        turno siguiente produjo exactamente el mismo resultado —refutando su
        diagnóstico— y no lo mencionó. Retractarse de una explicación no es algo
        que se pueda exigir con un marcador de texto; pero **que el resultado se
        repite** sí es comprobable, y decirlo cierra el hueco por donde entra la
        explicación nueva: si el fichero es el mismo, o la limitación es la
        misma, se dice en la propia entrega y no hace falta que nadie se acuerde.
        """
        anterior, paso_anterior = self._paso_anterior(job, paso.id)
        if paso_anterior is None:
            return ""
        if paso.path and paso_anterior.path:
            if await asyncio.to_thread(_mismo_contenido, paso.path, paso_anterior.path):
                return (f"\n-# ⚠️ Es el mismo archivo que ya entregué en el trabajo "
                        f"`{anterior.id}`: no ha cambiado nada.")
        if paso.note and paso.note == paso_anterior.note:
            return (f"\n-# ⚠️ Vuelve a salir con la misma limitación que en `{anterior.id}`. "
                    "No es un fallo distinto ni se arregla repitiendo el encargo.")
        return ""

    # --- Los pasos facturables, cada uno idempotente ------------------------

    async def _paso_cancion(self, job, plan, lyrics: str, lyrics_entry, report, channel) -> None:
        """Genera y entrega la canción. Idempotente: un paso verificado no se repite."""
        song_step = job.ensure_step("cancion", "cancion")
        if song_step.is_done():
            await report(f"🎵 Reanudo el trabajo `{job.id}`: la canción ya estaba generada y verificada; no la regenero.")
        elif song_step.exhausted():
            await report(f"⚠️ No repito la canción: ya falló {song_step.attempts} veces ({song_step.error}).")
        else:
            # Lo que no se puede hacer se dice **antes** de gastar, no al
            # entregar. En el incidente del 9 de septiembre esto se avisaba
            # después de generar, así que el Productor pidió la misma canción
            # cantada cuatro veces —y Yuki llegó a inventar una explicación
            # técnica falsa para justificar por qué salía instrumental—.
            # La causa es única y no depende del prompt: ningún motor
            # contratado canta.
            await report(self._aviso_de_canto(lyrics_entry))
            titulo = (lyrics_entry or {}).get("title") or "Canción sin título"
            # El prompt era una constante: 90 s, 72 BPM, Insen, voz serena, con
            # cualquier letra delante. Cuando Yuki reescribió la suya fijando 68
            # BPM y su propia estructura, el encargo siguiente la habría
            # contradicho en silencio. Ahora lo decide `criterio_musical`
            # leyendo la letra, y manda lo que la letra ya traiga.
            criterio = criterio_musical.leer_criterio(lyrics, titulo=titulo)
            # Y lo que quedó sin resolver la última vez sobre esta misma pieza.
            # Va a `observaciones` y no a los parámetros: el cuaderno recuerda,
            # no compone. Si hace tres semanas el 7/8 del puente atropellaba la
            # letra, eso se lee ahora, junto al BPM, y no se redescubre pagando.
            cuaderno.anotar_en_criterio(criterio, titulo, arte="sonora")
            # El criterio se dice **antes** de gastar: si la métrica va a
            # atropellar la voz, eso se sabe ahora y no al escuchar el adjunto.
            await report(criterio.resumen())
            song_prompt = criterio.prompt(lyrics, matices=plan.matices)
            song_step.attempts += 1
            self.media_jobs.save(job)
            song = await self.agent.nous_portal.generate_music_flow(
                title=f"{titulo} — voz", prompt=song_prompt,
                engine="lyria-3-pro-preview", duration_seconds=criterio.duracion_segundos,
                bpm=criterio.bpm, scale=criterio.escala.capitalize(),
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
            pie = (song_step.note or "🎵 Pista de audio generada")
            pie += self._pie_de_receta(song_step.path)
            pie += await self._aviso_de_que_ya_salio_asi(job, song_step)
            if await self._send_file(channel, song_step.path, pie):
                song_step.delivered = True
                self.media_jobs.save(job)
            else:
                await report("⚠️ La canción se generó, pero Discord rechazó el adjunto; no la doy por entregada.")

    @staticmethod
    def _semilla_visual(lyrics_entry, lyrics: str) -> str:
        """
        De qué parte la imagen: el título y las primeras imágenes de la letra.

        No se manda la letra entera —una portada no ilustra un poema línea a
        línea— sino su arranque, que es donde la obra declara su materia.
        """
        titulo = (lyrics_entry or {}).get("title", "")
        primeras = " ".join(
            linea.strip() for linea in (lyrics or "").splitlines()
            if linea.strip() and not linea.strip().startswith(("#", "[", "(", "`")))[:400]
        return f"portada de sencillo. {titulo}. {primeras}".strip()

    async def _paso_portada(self, job, plan, lyrics, lyrics_entry, report, channel) -> None:
        """
        Portada única del sencillo, cuando el pedido la nombra.

        `create_single_cover` existía desde hacía meses y no había paso que lo
        llamara: se pidió una portada, no se produjo, y nadie dijo que no se iba
        a producir. Eso es lo que arregla este paso.
        """
        portada = job.ensure_step("portada", "portada")
        if portada.is_done():
            await report(f"🎨 La portada del trabajo `{job.id}` ya estaba generada y verificada; no la regenero.")
        elif portada.exhausted():
            await report(f"⚠️ No repito la portada: ya falló {portada.attempts} veces ({portada.error}).")
        else:
            titulo = (lyrics_entry or {}).get("title") or "Sencillo"
            # El concepto visual estaba escrito a mano —«agua, hierro e
            # invierno»— con la luz clavada en `urushi`, así que la portada de
            # cualquier obra era la portada de *Herrumbre y Escarcha*. Ahora
            # sale de la obra y el criterio decide encuadre y luz.
            visual = criterio_visual.leer_criterio_visual(
                plan.con_matices(self._semilla_visual(lyrics_entry, lyrics)), titulo=titulo)
            cuaderno.anotar_en_criterio(visual, titulo, arte="visual")
            await report(visual.resumen())
            portada.attempts += 1
            self.media_jobs.save(job)
            arte = await self.agent.media_creator.create_single_cover(
                track_title=titulo,
                visual_concept=visual.prompt(),
                lighting=visual.luz,
                aspect_ratio=visual.encuadre,
            )
            ruta = arte.get("local_path") if arte.get("status") == "success" else None
            # Una portada simulada no es una portada. `create_single_cover`
            # devuelve `simulated` precisamente para que esto se pueda distinguir
            # sin abrir el fichero, y aquí se distingue.
            if ruta and Path(ruta).is_file() and not arte.get("simulated"):
                portada.mark_done(ruta)
                self.media_jobs.save(job)
                await asyncio.to_thread(self.agent.creation_library.inventory)
            elif arte.get("budget_exceeded"):
                portada.attempts -= 1
                self.media_jobs.save(job)
                await report(f"💳 Portada aplazada por presupuesto: {arte.get('error')}")
            else:
                detalle = arte.get("error") or arte.get("note") or (
                    "el proveedor devolvió un marcador simulado" if arte.get("simulated") else "sin detalle")
                portada.mark_failed(detalle)
                self.media_jobs.save(job)
                await report(f"⚠️ No se generó portada: {detalle}")
        if portada.is_done() and not portada.delivered:
            pie = ("🎨 Portada del sencillo" + self._pie_de_receta(portada.path)
                   + await self._aviso_de_que_ya_salio_asi(job, portada))
            if await self._send_file(channel, portada.path, pie):
                portada.delivered = True
                self.media_jobs.save(job)
            else:
                await report("⚠️ La portada se generó, pero Discord rechazó el adjunto; no la doy por entregada.")

    async def _pasos_video(self, job, plan, report, channel) -> None:
        """Segmentos de vídeo y montaje. Un segmento verificado no se vuelve a pagar."""
        script_entry = self._library_entry("palabra", ("guion", "audiovisual", "video"))
        script = ""
        if script_entry:
            script = self.agent.creation_library.read_entry(script_entry["id"]).get("content", "")
        visual_entry = self._library_entry("visual", ("herrumbre", "salon", "escarcha"))
        visual_path = self._library_file(visual_entry)
        # El guion eran cuatro planos del muelle escritos a mano, con cualquier
        # obra delante. Ahora lo lee de la obra; el **número** de planos sigue
        # saliendo del pedido, porque de él se derivan los pasos del trabajo
        # durable y cambiarlo rompería la reanudación de lo ya pagado.
        guion_visual = criterio_audiovisual.leer_guion(
            script or self._semilla_visual(None, ""), plan.segmentos,
            titulo=(script_entry or {}).get("title", ""))
        cuaderno.anotar_en_criterio(
            guion_visual, (script_entry or {}).get("title", ""), arte="audiovisual")
        hechos = sum(1 for i in range(1, plan.segmentos + 1)
                     if job.ensure_step(f"clip_{i}", "clip").is_done())
        if hechos:
            await report(f"🎬 {hechos} de {plan.segmentos} segmentos ya estaban verificados; sólo genero los que faltan.")
        else:
            await report(guion_visual.resumen())
        clips: List[str] = []
        for index in range(1, len(guion_visual.planos) + 1):
            clip_step = job.ensure_step(f"clip_{index}", "clip")
            if clip_step.is_done():
                clips.append(clip_step.path)
                continue
            if clip_step.exhausted():
                await report(f"⚠️ Segmento {index} descartado tras {clip_step.attempts} intentos: {clip_step.error}")
                break
            prompt = plan.con_matices(guion_visual.prompt(index, script))
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

        montaje = job.ensure_step("montaje", "montaje")
        final_video = montaje.path if montaje.is_done() else None
        if final_video is None and len(clips) == plan.segmentos:
            final_video = await asyncio.to_thread(self._concat_videos, clips)
            if final_video:
                montaje.mark_done(final_video)
            else:
                montaje.mark_failed("ffmpeg no produjo el vídeo final")
            self.media_jobs.save(job)
        if final_video:
            await asyncio.to_thread(self.agent.creation_library.inventory)
            if not montaje.delivered:
                pie = (f"🎬 Vídeo final — {plan.segmentos * 8} s, {plan.segmentos} segmento(s) ensamblados"
                       + await self._aviso_de_que_ya_salio_asi(job, montaje))
                if await self._send_file(channel, final_video, pie):
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

    # --- El bucle que los recorre y cierra el trabajo -----------------------

    async def _run_dm_media_delivery(self, author_id: str, author_name: str, content: str, channel,
                                     job=None) -> None:
        """
        Produce lo que el pedido nombra desde obras existentes; entrega sólo adjuntos reales.

        El trabajo es durable: cada paso se persiste en cuanto tiene fichero
        verificado, así que un reinicio a mitad no repite lo ya generado ni deja
        el encargo perdido. Reanudar cuesta únicamente los pasos que faltan.

        Qué pasos hay lo decide `encargo.leer_encargo` sobre el texto del pedido
        —antes era una tupla fija, y por eso pedir una portada no daba portada—.
        """
        async def report(text: str) -> None:
            await self._send_long(channel, text)

        # El plan sale del texto del pedido, y al reanudar `content` es
        # `job.order` —el mismo texto—, así que los identificadores de paso
        # salen idénticos. Si no lo fueran, la reanudación daría por «no hecho»
        # lo ya pagado y volvería a facturarlo.
        plan = _plan_del_encargo(content)
        if job is None:
            job = self.media_jobs.create(
                requester_id=author_id, order=content,
                channel_id=getattr(channel, "id", None), steps=plan.steps(),
            )
        job.channel_id = str(getattr(channel, "id", "")) or job.channel_id

        try:
            lyrics_entry = self._library_entry("palabra", ("letra", "lirica", "poema", "herrumbre"),
                                               pedido=content)
            lyrics_path = self._library_file(lyrics_entry)
            if not lyrics_entry or not lyrics_path:
                self.media_jobs.abandon(job, "sin letra verificable en Biblioteca")
                await report("❌ No encuentro una letra verificable en la Biblioteca; no generaré una canción sin texto fuente.")
                return
            lyrics = self.agent.creation_library.read_entry(lyrics_entry["id"]).get("content", "")
            # La brevedad sólo descarta el **canto**: una portada o un vídeo se
            # sostienen sobre un poema corto. Antes esta guarda abortaba el
            # encargo entero, así que pedir sólo la portada de una pieza breve
            # no daba portada y decía que era por no presentarla como canción.
            if plan.cancion and len(lyrics.strip()) < 80:
                if not (plan.portada or plan.video):
                    self.media_jobs.abandon(job, "letra demasiado breve")
                    await report("❌ La letra recuperada es demasiado breve para una canción; "
                                 "no la presentaré como canto completo.")
                    return
                plan = replace(plan, cancion=False)
                await report("⚠️ La letra es demasiado breve para una canción y no la presentaré "
                             "como canto completo; sigo con el resto del encargo.")

            if plan.cancion:
                await self._paso_cancion(job, plan, lyrics, lyrics_entry, report, channel)
            if plan.portada:
                await self._paso_portada(job, plan, lyrics, lyrics_entry, report, channel)
            if plan.video:
                await self._pasos_video(job, plan, report, channel)

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
        except asyncio.CancelledError:
            # `CancelledError` hereda de `BaseException`: el `except Exception`
            # de abajo **no** la ve. Un despliegue a mitad de encargo cerraba el
            # bucle, cancelaba la tarea y no dejaba ni una línea —el trabajo del
            # 9 de septiembre arrancó cuatro segmentos y nunca dijo nada más—.
            # Aquí queda constancia y el trabajo, guardado y reanudable; la
            # cancelación se propaga, porque el proceso se está apagando.
            self.media_jobs.save(job)
            logger.warning("Producción multimedia cancelada a mitad: %s", describe_media_job(job))
            raise
        except Exception:
            logger.exception("Fallo en producción multimedia por DM")
            self.media_jobs.save(job)
            await report(
                "❌ La producción multimedia falló; no doy por generados ni entregados archivos que no consten "
                f"adjuntos. El trabajo `{job.id}` queda registrado y reanudable desde el último paso verificado."
            )
