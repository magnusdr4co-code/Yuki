"""
Medios de frontera sobre Vertex AI (Gemini Enterprise Agent Platform).

Es la contraparte de `src/core/llm_router.py` para lo que no es texto: imagen,
vídeo y voz servidos por Google Cloud y facturados contra el mismo crédito.

Tres motores, cada uno con su SDK oficial:

  · Imagen        — portadas e ilustración.       `google-genai`
  · Veo 3.1       — vídeo con sonido nativo.       `google-genai` (models)
  · Lyria 3       — canciones MP3 con letra.       `google-genai` (interactions)
  · Gemini TTS    — notas de voz en OGG Opus.      `google-cloud-texttospeech`

Sobre Omni conviene ser explícito, porque su nombre invita a confundirlo con un
modelo de propósito general: **genera y edita vídeo**, y se factura por segundo
de vídeo producido, no por token. No sirve para el cerebro de Yuki —de eso se
ocupa `llm_router`— sino para su obra visual.

Reglas heredadas de `AGENTS.md` §5.4 y `skills/HERRAMIENTAS.md` §7:
ninguna función de este módulo inventa un resultado. Si la llamada falla, se
devuelve `status: "error"` con el motivo, para que la habilidad aborte y lo
explique. Nunca una URL de un fichero que no existe.
"""

import os
import time
import base64
import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..core.spend_budget import (
    IMAGENES, MUSICA_PISTAS, MUSICA_SEGUNDOS, VIDEO_SEGUNDOS, VOZ_CARACTERES,
    SpendLedger,
)
from ..core.transparency import MediaMarker

logger = logging.getLogger("Yuki.VertexMedia")

# Identificadores por defecto. Confírmalos contra el proyecto antes de fijarlos:
#   gcloud ai models list --region=<region>
# Las publisher models Imagen no están habilitadas para este proyecto. La ruta
# Gemini Image sí respondió en Vertex durante la prueba real del despliegue.
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
DEFAULT_VIDEO_MODEL = "veo-3.1-fast-generate-001"
DEFAULT_MUSIC_MODEL = "lyria-3-pro-preview"
DEFAULT_TTS_MODEL = "gemini-2.5-flash-tts"

# Voz y lengua de Yuki. El catálogo de voces con nombre de Gemini TTS sustituye
# al identificador ficticio `yuki_serene_alto` de la documentación antigua.
DEFAULT_VOICE = "Aoede"
DEFAULT_LANGUAGE_CODE = "es-es"

# Precios de referencia para avisar antes de gastar. Orientativos: la cifra que
# manda es la del panel de facturación de Google Cloud.
PRECIO_VIDEO_POR_SEGUNDO = 0.10
PRECIO_IMAGEN = 0.04

# Vídeo: el modelo acepta duraciones enteras de 3 a 10 segundos.
DURACION_VIDEO_MIN = 3
DURACION_VIDEO_MAX = 10


class VertexMediaError(RuntimeError):
    """Fallo al producir un medio. Se propaga como `status: error`, nunca como éxito."""


def _resultado_error(motivo: str, **extra: Any) -> Dict[str, Any]:
    """
    Forma canónica de un fallo.

    Se devuelve en lugar de lanzar para que la habilidad decida si aborta o cae
    al respaldo, pero jamás se confunde con un éxito: `status` es `error` y no
    hay ninguna ruta ni URL que aparente un fichero real.
    """
    logger.error(motivo)
    return {"status": "error", "error": motivo, "simulated": False, **extra}


class VertexMediaClient:
    """
    Cliente de medios de Vertex.

    Inerte mientras no haya proyecto declarado, igual que la pasarela de texto:
    `is_available()` es falso y quien llame debe caer a su respaldo. Así el
    repositorio sigue funcionando sin cuenta de Google Cloud.
    """

    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None,
                 image_model: str = DEFAULT_IMAGE_MODEL,
                 video_model: str = DEFAULT_VIDEO_MODEL,
                 music_model: str = DEFAULT_MUSIC_MODEL,
                 video_location: Optional[str] = None,
                 music_location: Optional[str] = None,
                 tts_model: str = DEFAULT_TTS_MODEL,
                 voice: str = DEFAULT_VOICE,
                 language_code: str = DEFAULT_LANGUAGE_CODE,
                 enabled: bool = True,
                 art_dir: str = "output/art",
                 voice_dir: str = "output/voice",
                 music_dir: str = "output/music",
                 video_dir: str = "output/video",
                 client: Any = None, tts_client: Any = None,
                 budget: Optional[SpendLedger] = None,
                 marker: Optional[MediaMarker] = None):
        self.project_id = (project_id or os.getenv("VERTEX_PROJECT_ID")
                           or os.getenv("GOOGLE_CLOUD_PROJECT") or "")
        self.location = location or os.getenv("VERTEX_LOCATION") or "global"
        self.video_location = video_location or self.location
        self.music_location = music_location or "global"
        self.image_model = image_model
        self.video_model = video_model
        self.music_model = music_model
        self.tts_model = tts_model
        self.voice = voice
        self.language_code = language_code
        self.enabled = enabled

        self.art_dir = art_dir
        self.voice_dir = voice_dir
        self.music_dir = music_dir
        self.video_dir = video_dir

        # Presupuesto diario. Se comprueba antes de llamar al proveedor: el
        # vídeo se factura por segundo y avisar después no devuelve el crédito.
        self.budget = budget if budget is not None else SpendLedger()

        # Marcado de origen sintético (Artículo 50). Se aplica al escribir el
        # fichero, no al entregarlo: así ningún camino de salida —Discord, el
        # Salón, la Biblioteca, una copia manual— puede sacar material sin marca.
        self.marker = marker if marker is not None else MediaMarker()

        # Inyectables en pruebas; en producción se construyen perezosamente.
        self._client = client
        self._clients: Dict[str, Any] = {}
        self._tts_client = tts_client

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None, **overrides: Any) -> "VertexMediaClient":
        """
        Construye el motor desde la sección `vertex_ai` de `config.yaml`.

        Comparte proyecto, región e interruptor con la pasarela de texto: un
        único sitio donde declarar el proyecto, y los modelos de medios bajo
        `vertex_ai.media`.
        """
        vertex_cfg = (config or {}).get("vertex_ai", {}) or {}
        media_cfg = vertex_cfg.get("media", {}) or {}

        parametros: Dict[str, Any] = {
            "project_id": vertex_cfg.get("project_id"),
            # Los medios pueden necesitar una región distinta del endpoint de
            # texto. Si no se declara, conserva la región global del texto.
            "location": media_cfg.get("location", vertex_cfg.get("location")),
            "video_location": media_cfg.get("video_location", media_cfg.get("location", vertex_cfg.get("location"))),
            "music_location": media_cfg.get("music_location", "global"),
            "enabled": vertex_cfg.get("enabled", True),
            "image_model": media_cfg.get("image_model", DEFAULT_IMAGE_MODEL),
            "video_model": media_cfg.get("video_model", DEFAULT_VIDEO_MODEL),
            "music_model": media_cfg.get("music_model", DEFAULT_MUSIC_MODEL),
            "tts_model": media_cfg.get("tts_model", DEFAULT_TTS_MODEL),
            "voice": media_cfg.get("voice", DEFAULT_VOICE),
            "language_code": media_cfg.get("language_code", DEFAULT_LANGUAGE_CODE),
            # El presupuesto vive en su propia sección y comparte la zona horaria
            # del planificador, para que el día del gasto sea el de las rutinas.
            "budget": SpendLedger.from_config(config),
        }
        parametros.update(overrides)
        return cls(**parametros)

    # --- Disponibilidad y clientes -------------------------------------------

    def is_available(self) -> bool:
        """Comprobación barata y sin red: sólo mira la configuración."""
        if not self.enabled:
            return False
        valor = (self.project_id or "").strip().lower()
        if not valor:
            return False
        return not any(marca in valor for marca in ("your_", "_here", "changeme"))

    def _ensure_dir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def _genai_client(self, location: Optional[str] = None) -> Any:
        """
        Cliente de `google-genai` apuntando a Vertex.

        El SDK ha cambiado el nombre del interruptor con el rebautizado de la
        plataforma: los ejemplos nuevos usan `enterprise=True` y los anteriores
        `vertexai=True`. Se intenta el primero y se cae al segundo, para no
        atarse a la versión exacta que tenga instalada el despliegue.
        """
        location = location or self.location
        if self._client is not None and location == self.location:
            return self._client

        if location in self._clients:
            return self._clients[location]

        from google import genai

        try:
            cliente = genai.Client(
                enterprise=True, project=self.project_id, location=location
            )
        except TypeError:
            logger.debug("El SDK no acepta `enterprise=`; se usa `vertexai=`.")
            cliente = genai.Client(
                vertexai=True, project=self.project_id, location=location
            )
        self._clients[location] = cliente
        return cliente

    def _texttospeech_client(self) -> Any:
        if self._tts_client is not None:
            return self._tts_client

        from google.api_core.client_options import ClientOptions
        from google.cloud import texttospeech_v1beta1 as texttospeech

        endpoint = ("texttospeech.googleapis.com" if self.location == "global"
                    else f"{self.location}-texttospeech.googleapis.com")
        self._tts_client = texttospeech.TextToSpeechClient(
            client_options=ClientOptions(api_endpoint=endpoint)
        )
        return self._tts_client

    # --- Imagen ---------------------------------------------------------------

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1",
                             model: Optional[str] = None) -> Dict[str, Any]:
        """
        Pinta una imagen con Imagen y la guarda en `output/art/`.

        Una sola imagen por petición, como manda `skills/HERRAMIENTAS.md` §3:
        generar variantes "para elegir" sin que el productor lo pida es gasto.
        """
        if not self.is_available():
            return _resultado_error("Vertex no está configurado: falta VERTEX_PROJECT_ID.")

        model = model or self.image_model

        permiso = self.budget.reserve(IMAGENES, 1)
        if not permiso.allowed:
            logger.warning("Imagen rechazada por presupuesto: %s", permiso.reason)
            return _resultado_error(permiso.reason, budget_exceeded=True, unit=permiso.unit)

        self._ensure_dir(self.art_dir)
        destino = os.path.join(self.art_dir, f"yuki_{model.replace('/', '_')}_{int(time.time())}.png")

        def _llamar() -> bytes:
            from google.genai import types

            cliente = self._genai_client(self.location)
            if model.startswith("gemini-") or model.startswith("nano-banana"):
                respuesta = cliente.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
                )
                for candidato in getattr(respuesta, "candidates", None) or []:
                    contenido = getattr(candidato, "content", None)
                    for parte in getattr(contenido, "parts", None) or []:
                        inline = getattr(parte, "inline_data", None)
                        datos = getattr(inline, "data", None) if inline else None
                        if datos:
                            if isinstance(datos, str):
                                return base64.b64decode(datos)
                            return datos
                raise VertexMediaError("Gemini Image no devolvió datos de imagen.")

            respuesta = cliente.models.generate_images(
                model=model,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=aspect_ratio,
                    output_mime_type="image/png",
                ),
            )
            imagenes = getattr(respuesta, "generated_images", None) or []
            if not imagenes:
                # Suele ser el filtro de seguridad. Es un fallo, no una imagen.
                raise VertexMediaError(
                    "Imagen no devolvió ninguna imagen (posible filtro de seguridad)."
                )
            datos = getattr(imagenes[0].image, "image_bytes", None)
            if not datos:
                raise VertexMediaError("La respuesta de Imagen no traía bytes de imagen.")
            return datos

        try:
            # El SDK es síncrono: fuera del hilo del bucle para no congelar el
            # daemon mientras se pinta.
            datos = await asyncio.to_thread(_llamar)
        except Exception as e:
            self.budget.refund(IMAGENES, 1)
            return _resultado_error(f"Fallo generando imagen con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(datos)

        logger.info(f"🎨 Imagen real generada con {model}: {destino}")
        marca = self.marker.mark(destino, model=model, prompt=prompt, kind="visual")
        return {
            "marking": marca,
            "status": "success",
            "simulated": False,
            "provider": "vertex_ai",
            "model": model,
            "prompt_used": prompt,
            "local_path": destino,
            "aspect_ratio": aspect_ratio,
            "bytes": len(datos),
            "estimated_cost_usd": PRECIO_IMAGEN,
            "created_at": time.time(),
        }

    # --- Música --------------------------------------------------------------

    async def generate_music(self, prompt: str, duration_seconds: int = 90,
                             model: Optional[str] = None) -> Dict[str, Any]:
        """Genera una canción MP3 real con Lyria 3 mediante Interactions API."""
        if not self.is_available():
            return _resultado_error("Vertex no está configurado: falta VERTEX_PROJECT_ID.")

        model = model or self.music_model
        if not model.startswith("lyria-"):
            return _resultado_error(
                f"Modelo musical no compatible con la ruta Lyria: {model}."
            )
        max_duration = 184 if model == "lyria-3-pro-preview" else 30
        if not 1 <= duration_seconds <= max_duration:
            return _resultado_error(
                f"Duración musical fuera de rango: {duration_seconds}s; máximo {max_duration}s."
            )

        permiso = self.budget.reserve(MUSICA_PISTAS, 1)
        if not permiso.allowed:
            logger.warning("Música rechazada por presupuesto: %s", permiso.reason)
            return _resultado_error(permiso.reason, budget_exceeded=True, unit=permiso.unit)

        self._ensure_dir(self.music_dir)
        destino = os.path.join(self.music_dir, f"yuki_lyria_{int(time.time())}.mp3")

        def _llamar() -> bytes:
            cliente = self._genai_client(self.music_location)
            interaccion = cliente.interactions.create(
                model=model,
                input=[{"type": "text", "text": prompt}],
            )
            audio = getattr(interaccion, "output_audio", None)
            datos = getattr(audio, "data", None) if audio is not None else None
            if isinstance(datos, str):
                datos = base64.b64decode(datos)
            if not datos:
                raise VertexMediaError("Lyria no devolvió audio en output_audio.")
            return datos

        try:
            datos = await asyncio.to_thread(_llamar)
        except Exception as e:
            self.budget.refund(MUSICA_PISTAS, 1)
            return _resultado_error(f"Fallo generando música con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(datos)

        logger.info("🎵 Canción real generada con %s: %s", model, destino)
        # La pista ya está reservada; los segundos se anotan al confirmarse, y
        # dejan constancia del volumen aunque no haya precio que aplicarles.
        self.budget.record(MUSICA_SEGUNDOS, duration_seconds)
        marca = self.marker.mark(destino, model=model, prompt=prompt, kind="sonora")
        return {
            "marking": marca,
            "status": "success",
            "simulated": False,
            "provider": "vertex_ai",
            "model": model,
            "local_path": destino,
            "mime_type": "audio/mpeg",
            "duration_seconds": duration_seconds,
            "bytes": len(datos),
            "created_at": time.time(),
        }

    # --- Vídeo ----------------------------------------------------------------

    async def generate_video(self, prompt: str, duration_seconds: int = 6,
                             aspect_ratio: str = "16:9",
                             image_path: Optional[str] = None,
                             model: Optional[str] = None) -> Dict[str, Any]:
        """
        Genera vídeo con sonido nativo mediante Veo 3.1.

        Con `image_path` anima una portada ya existente (`image_to_video`); sin
        ella parte del texto (`text_to_video`).

        **Es la herramienta más cara del catálogo**: se factura por segundo de
        vídeo, no por token. Diez segundos cuestan más que cientos de respuestas
        de texto, así que la duración se acota y el coste estimado se devuelve
        siempre para que quede registrado.
        """
        if not self.is_available():
            return _resultado_error("Vertex no está configurado: falta VERTEX_PROJECT_ID.")

        if not DURACION_VIDEO_MIN <= duration_seconds <= DURACION_VIDEO_MAX:
            return _resultado_error(
                f"Duración fuera de rango: {duration_seconds}s. "
                f"El modelo admite de {DURACION_VIDEO_MIN} a {DURACION_VIDEO_MAX} segundos."
            )

        model = model or self.video_model
        if model.startswith("veo-") and duration_seconds not in (4, 6, 8):
            return _resultado_error(
                f"Duración fuera de rango para Veo: {duration_seconds}s; usa 4, 6 u 8 segundos."
            )

        if image_path and not os.path.exists(image_path):
            return _resultado_error(f"No existe la imagen de partida: {image_path}")

        # El presupuesto se reserva aquí, antes del proveedor: pasado este punto
        # el segundo de vídeo ya está facturado. Reservar —en vez de comprobar y
        # anotar después— cierra el hueco en el que dos encargos simultáneos
        # superarían ambos el mismo límite. Si Veo falla, se devuelve.
        permiso = self.budget.reserve(VIDEO_SEGUNDOS, duration_seconds)
        if not permiso.allowed:
            logger.warning("Vídeo rechazado por presupuesto: %s", permiso.reason)
            return _resultado_error(permiso.reason, budget_exceeded=True, unit=permiso.unit)

        self._ensure_dir(self.video_dir)
        destino = os.path.join(self.video_dir, f"yuki_veo_{int(time.time())}.mp4")

        def _llamar() -> bytes:
            cliente = self._genai_client(self.video_location)

            if model.startswith("veo-"):
                from google.genai import types

                argumentos: Dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "config": types.GenerateVideosConfig(
                        aspect_ratio=aspect_ratio,
                        duration_seconds=str(duration_seconds),
                        generate_audio=True,
                        number_of_videos=1,
                    ),
                }
                if image_path:
                    argumentos["image"] = types.Image.from_file(location=image_path)
                operacion = cliente.models.generate_videos(**argumentos)
                while not operacion.done:
                    time.sleep(10)
                    operacion = cliente.operations.get(operacion)
                respuesta = getattr(operacion, "response", None)
                videos = getattr(respuesta, "generated_videos", None) or []
                if not videos:
                    raise VertexMediaError("Veo no devolvió ningún vídeo.")
                video = getattr(videos[0], "video", None)
                datos = getattr(video, "video_bytes", None) if video else None
                if not datos:
                    raise VertexMediaError(
                        "Veo devolvió una URI remota sin bytes locales; no adjunto un fichero inexistente."
                    )
                return datos

            if image_path:
                with open(image_path, "rb") as f:
                    imagen_b64 = base64.b64encode(f.read()).decode("utf-8")
                mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
                entrada: Any = [
                    {"type": "text", "text": prompt},
                    {"type": "image", "mime_type": mime, "data": imagen_b64},
                ]
                tarea = "image_to_video"
            else:
                entrada = prompt
                tarea = "text_to_video"

            interaccion = cliente.interactions.create(
                model=model,
                input=entrada,
                generation_config=interactions.GenerationConfig(
                    video_config=interactions.VideoConfig(task=tarea)
                ),
                response_format=interactions.VideoResponseFormat(
                    aspect_ratio=aspect_ratio,
                    duration=f"{duration_seconds}s",
                ),
            )

            partes: List[Any] = []
            for paso in getattr(interaccion, "steps", []) or []:
                if getattr(paso, "type", None) == "model_output":
                    partes.extend(paso.content)

            if not partes:
                raise VertexMediaError("El motor de vídeo no devolvió ningún fotograma en la respuesta.")

            datos = getattr(partes[0], "data", None)
            if not datos:
                raise VertexMediaError("La respuesta de vídeo no traía datos.")
            return base64.b64decode(datos) if isinstance(datos, str) else datos

        try:
            datos = await asyncio.to_thread(_llamar)
        except Exception as e:
            # La reserva no se gastó: devolverla evita que un 503 consuma el
            # presupuesto del día sin haber producido un solo fotograma.
            self.budget.refund(VIDEO_SEGUNDOS, duration_seconds)
            return _resultado_error(f"Fallo generando vídeo con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(datos)

        # Ya está anotado por la reserva; aquí sólo se informa.
        coste = duration_seconds * PRECIO_VIDEO_POR_SEGUNDO
        marca = self.marker.mark(destino, model=model, prompt=prompt, kind="audiovisual")
        logger.info(f"🎬 Vídeo real generado con {model}: {destino} (≈${coste:.2f}); "
                    f"presupuesto de hoy → {self.budget.describe()}")
        return {
            "status": "success",
            "simulated": False,
            "provider": "vertex_ai",
            "model": model,
            "marking": marca,
            "task": "image_to_video" if image_path else "text_to_video",
            "prompt_used": prompt,
            "local_path": destino,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "bytes": len(datos),
            "estimated_cost_usd": coste,
            "created_at": time.time(),
        }

    # --- Voz ------------------------------------------------------------------

    async def synthesize_voice(self, text: str, style_prompt: Optional[str] = None,
                               voice: Optional[str] = None,
                               language_code: Optional[str] = None,
                               model: Optional[str] = None) -> Dict[str, Any]:
        """
        Sintetiza una nota de voz en OGG Opus.

        Dos cosas cambian respecto de la ruta antigua:

        1. **No hace falta transcodificar.** Gemini TTS emite OGG Opus de forma
           nativa, que es lo que Telegram reproduce como nota de voz. El paso de
           `local.ffmpeg` sobra en esta ruta.
        2. **La cadencia se pide en lenguaje natural**, no con marcado SSML. El
           `prompt` del modelo describe cómo hablar; es más fiel a la "pausa
           elegida" de `SOUL.md` que un `<break time="350ms"/>` mecánico.
        """
        if not self.is_available():
            return _resultado_error("Vertex no está configurado: falta VERTEX_PROJECT_ID.")

        if not text or not text.strip():
            return _resultado_error("No hay texto que sintetizar.")

        model = model or self.tts_model
        voice = voice or self.voice
        language_code = language_code or self.language_code
        style_prompt = style_prompt or (
            "Habla con calidez contenida y pausas deliberadas, como quien elige "
            "cada palabra antes de decirla. Ritmo sereno, nunca apresurado."
        )

        permiso = self.budget.reserve(VOZ_CARACTERES, len(text))
        if not permiso.allowed:
            logger.warning("Voz rechazada por presupuesto: %s", permiso.reason)
            return _resultado_error(permiso.reason, budget_exceeded=True, unit=permiso.unit)

        self._ensure_dir(self.voice_dir)
        destino = os.path.join(self.voice_dir, f"yuki_voice_{int(time.time())}.ogg")

        def _llamar() -> bytes:
            from google.cloud import texttospeech_v1beta1 as texttospeech

            cliente = self._texttospeech_client()
            respuesta = cliente.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text, prompt=style_prompt),
                voice=texttospeech.VoiceSelectionParams(
                    name=voice, language_code=language_code, model_name=model
                ),
                audio_config=texttospeech.AudioConfig(
                    # Nativo: Telegram sólo reproduce notas de voz en OGG Opus.
                    audio_encoding=texttospeech.AudioEncoding.OGG_OPUS
                ),
            )
            if not respuesta.audio_content:
                raise VertexMediaError("Gemini TTS devolvió una respuesta sin audio.")
            return respuesta.audio_content

        try:
            audio = await asyncio.to_thread(_llamar)
        except Exception as e:
            self.budget.refund(VOZ_CARACTERES, len(text))
            return _resultado_error(f"Fallo sintetizando voz con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(audio)

        marca = self.marker.mark(destino, model=model, prompt=text[:200], kind="voz")
        logger.info(f"🎙️ Nota de voz real generada con {model}: {destino}")
        return {
            "status": "success",
            "simulated": False,
            "provider": "vertex_ai",
            "model": model,
            "marking": marca,
            "voice": voice,
            "language_code": language_code,
            "style_prompt": style_prompt,
            "local_path": destino,
            "encoding": "OGG_OPUS",
            "transcoding_required": False,
            "bytes": len(audio),
            "created_at": time.time(),
        }
