"""
Medios de frontera sobre Vertex AI (Gemini Enterprise Agent Platform).

Es la contraparte de `src/core/llm_router.py` para lo que no es texto: imagen,
vídeo y voz servidos por Google Cloud y facturados contra el mismo crédito.

Tres motores, cada uno con su SDK oficial:

  · Imagen        — portadas e ilustración.       `google-genai`
  · Gemini Omni   — vídeo con audio nativo.       `google-genai` (interactions)
  · Gemini TTS    — notas de voz en OGG Opus.     `google-cloud-texttospeech`

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

logger = logging.getLogger("Yuki.VertexMedia")

# Identificadores por defecto. Confírmalos contra el proyecto antes de fijarlos:
#   gcloud ai models list --region=<region>
DEFAULT_IMAGE_MODEL = "imagen-4.0-generate-001"
DEFAULT_VIDEO_MODEL = "gemini-omni-flash-preview"
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
                 tts_model: str = DEFAULT_TTS_MODEL,
                 voice: str = DEFAULT_VOICE,
                 language_code: str = DEFAULT_LANGUAGE_CODE,
                 enabled: bool = True,
                 art_dir: str = "output/art",
                 voice_dir: str = "output/voice",
                 video_dir: str = "output/video",
                 client: Any = None, tts_client: Any = None):
        self.project_id = (project_id or os.getenv("VERTEX_PROJECT_ID")
                           or os.getenv("GOOGLE_CLOUD_PROJECT") or "")
        self.location = location or os.getenv("VERTEX_LOCATION") or "global"
        self.image_model = image_model
        self.video_model = video_model
        self.tts_model = tts_model
        self.voice = voice
        self.language_code = language_code
        self.enabled = enabled

        self.art_dir = art_dir
        self.voice_dir = voice_dir
        self.video_dir = video_dir

        # Inyectables en pruebas; en producción se construyen perezosamente.
        self._client = client
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
            "location": vertex_cfg.get("location"),
            "enabled": vertex_cfg.get("enabled", True),
            "image_model": media_cfg.get("image_model", DEFAULT_IMAGE_MODEL),
            "video_model": media_cfg.get("video_model", DEFAULT_VIDEO_MODEL),
            "tts_model": media_cfg.get("tts_model", DEFAULT_TTS_MODEL),
            "voice": media_cfg.get("voice", DEFAULT_VOICE),
            "language_code": media_cfg.get("language_code", DEFAULT_LANGUAGE_CODE),
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

    def _genai_client(self) -> Any:
        """
        Cliente de `google-genai` apuntando a Vertex.

        El SDK ha cambiado el nombre del interruptor con el rebautizado de la
        plataforma: los ejemplos nuevos usan `enterprise=True` y los anteriores
        `vertexai=True`. Se intenta el primero y se cae al segundo, para no
        atarse a la versión exacta que tenga instalada el despliegue.
        """
        if self._client is not None:
            return self._client

        from google import genai

        try:
            self._client = genai.Client(
                enterprise=True, project=self.project_id, location=self.location
            )
        except TypeError:
            logger.debug("El SDK no acepta `enterprise=`; se usa `vertexai=`.")
            self._client = genai.Client(
                vertexai=True, project=self.project_id, location=self.location
            )
        return self._client

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
        self._ensure_dir(self.art_dir)
        destino = os.path.join(self.art_dir, f"yuki_{model.replace('/', '_')}_{int(time.time())}.png")

        def _llamar() -> bytes:
            from google.genai import types

            cliente = self._genai_client()
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
            return _resultado_error(f"Fallo generando imagen con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(datos)

        logger.info(f"🎨 Imagen real generada con {model}: {destino}")
        return {
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

    # --- Vídeo ----------------------------------------------------------------

    async def generate_video(self, prompt: str, duration_seconds: int = 6,
                             aspect_ratio: str = "16:9",
                             image_path: Optional[str] = None,
                             model: Optional[str] = None) -> Dict[str, Any]:
        """
        Genera vídeo con audio nativo mediante Gemini Omni Flash.

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

        if image_path and not os.path.exists(image_path):
            return _resultado_error(f"No existe la imagen de partida: {image_path}")

        model = model or self.video_model
        self._ensure_dir(self.video_dir)
        destino = os.path.join(self.video_dir, f"yuki_omni_{int(time.time())}.mp4")

        def _llamar() -> bytes:
            from google.genai import interactions

            cliente = self._genai_client()

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
                raise VertexMediaError("Omni no devolvió ningún fotograma en la respuesta.")

            datos = getattr(partes[0], "data", None)
            if not datos:
                raise VertexMediaError("La respuesta de Omni no traía datos de vídeo.")
            return base64.b64decode(datos)

        try:
            datos = await asyncio.to_thread(_llamar)
        except Exception as e:
            return _resultado_error(f"Fallo generando vídeo con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(datos)

        coste = duration_seconds * PRECIO_VIDEO_POR_SEGUNDO
        logger.info(f"🎬 Vídeo real generado con {model}: {destino} (≈${coste:.2f})")
        return {
            "status": "success",
            "simulated": False,
            "provider": "vertex_ai",
            "model": model,
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
            return _resultado_error(f"Fallo sintetizando voz con Vertex ({model}): {e}")

        with open(destino, "wb") as f:
            f.write(audio)

        logger.info(f"🎙️ Nota de voz real generada con {model}: {destino}")
        return {
            "status": "success",
            "simulated": False,
            "provider": "vertex_ai",
            "model": model,
            "voice": voice,
            "language_code": language_code,
            "style_prompt": style_prompt,
            "local_path": destino,
            "encoding": "OGG_OPUS",
            "transcoding_required": False,
            "bytes": len(audio),
            "created_at": time.time(),
        }
