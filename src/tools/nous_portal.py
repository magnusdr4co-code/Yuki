"""
Pasarela de medios de Yuki (Hermes Agent Harness).

Dos rutas, y sólo una produce ficheros de verdad:

1. **Vertex AI** (`src/tools/vertex_media.py`) — imagen con Imagen, vídeo con
   Gemini Omni Flash y voz con Gemini TTS. Se activa en cuanto hay proyecto de
   Google Cloud declarado, y es la que consume el crédito.
2. **Marcador local** — cuando no hay Vertex configurado. Escribe un fichero de
   texto en su sitio para no romper el flujo de una demo.

La distinción importa y por eso viaja en cada resultado: todo lo que devuelve
este módulo lleva `simulated`, y la ruta del marcador **nunca** se presenta como
un medio real ni se acompaña de una URL de CDN inventada. Es la regla de
`AGENTS.md` §5.4 y `skills/HERRAMIENTAS.md` §7: un resultado fingido contamina
la memoria y engaña al productor.

El endpoint de Nous Portal sigue sin existir; cuando exista, se añade aquí como
una tercera ruta por delante de Vertex.
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.tools.vertex_media import VertexMediaClient
from src.tools.web_search import FirecrawlSearch

logger = logging.getLogger("Yuki.NousPortal")


def local_uri(path: str) -> str:
    """
    URI del fichero realmente escrito en disco.

    Sustituye a las URLs de `https://nousportal.media/cdn/...` que devolvía este
    módulo: apuntaban a un dominio que no aloja nada, y llegaban acompañadas de
    `status: success`. Cualquiera que siguiera una de ellas encontraba un 404
    creyendo que Yuki había publicado algo.
    """
    return Path(path).resolve().as_uri()

class NousPortalClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.nousportal.com/v1",
        vertex: Optional[VertexMediaClient] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.api_key = api_key or os.getenv("NOUS_PORTAL_API_KEY") or os.getenv("FAL_KEY", "demo_portal_key")
        self.base_url = base_url

        # Rutas nativas del workspace de Hermes
        self.art_dir = "output/art"
        self.voice_dir = "output/voice"
        self.music_dir = "output/music"
        self.video_dir = "output/video"
        self.posts_dir = "output/posts"

        for d in [self.art_dir, self.voice_dir, self.music_dir, self.video_dir, self.posts_dir]:
            os.makedirs(d, exist_ok=True)

        # Buscador real. Sin clave devuelve pistas declaradas como simuladas,
        # nunca titulares inventados con URL verosímil.
        self.web_search = FirecrawlSearch.from_config(config)

        # Motor real de medios. Inerte mientras no haya proyecto de Google
        # Cloud: entonces esta clase cae a sus marcadores, marcados como tales.
        self.vertex = vertex or VertexMediaClient.from_config(
            config,
            art_dir=self.art_dir,
            voice_dir=self.voice_dir,
            music_dir=self.music_dir,
            video_dir=self.video_dir,
        )

    def _marcador(self, path: str, descripcion: str, **extra: Any) -> Dict[str, Any]:
        """
        Escribe un marcador y lo devuelve **declarado como simulado**.

        No lleva `image_url`/`audio_url` de un CDN inventado: la única
        referencia es el fichero de texto que existe de verdad en disco.
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"/* {descripcion} */\n")

        logger.warning(
            f"Medio simulado (Vertex no configurado): {path}. "
            "Declara VERTEX_PROJECT_ID para generar medios reales."
        )
        return {
            "status": "simulated",
            "simulated": True,
            "local_path": path,
            "local_uri": local_uri(path),
            "note": ("Marcador de texto, no un medio real. Configura VERTEX_PROJECT_ID "
                     "para que Yuki genere imagen, vídeo y voz de verdad."),
            "created_at": time.time(),
            **extra,
        }

    async def generate_image_frontier(
        self,
        prompt: str,
        provider: str = "gemini_image", # "gemini_image", "seedream", "flux_pro"
        aspect_ratio: str = "1:1",
        lighting_style: str = "komorebi",
        mood_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Genera portadas y arte visual consumiendo modelos de frontera:
        - gemini_image: Google Imagen 3 / Gemini 2.0/3.0 Image Generation (fotorrealismo y texturas puras)
        - seedream: Seedream 2.0 (estética conceptual y trazo kintsugi refinado)
        - flux_pro: FAL Flux 1.1 Pro Ultra (iluminación cinematográfica 8K)
        """
        if mood_params:
            lighting_style = mood_params.get('lighting', lighting_style)
            texture_hint = mood_params.get('texture_hint', '')
            if texture_hint:
                prompt = f"{texture_hint}, {prompt}"
            color_bias = mood_params.get('color_bias', '')
            if color_bias:
                prompt = f"{prompt}, {color_bias}"
        lighting_descriptors = {
            "komorebi": "sunlight filtering through bamboo leaves, gentle natural hazes",
            "urushi": "warm candlelight reflections on Urushi black lacquer and gold leaf",
            "industrial_rain": "cinematic neon reflections on wet asphalt, mist, moody ambient"
        }
        light_desc = lighting_descriptors.get(lighting_style, lighting_descriptors["komorebi"])

        model_identifiers = {
            "gemini_image": "google/imagen-3-generate-002",
            "seedream": "bytedance/seedream-v2.5-hd",
            "flux_pro": "fal-ai/flux-pro/v1.1-ultra"
        }
        selected_model = model_identifiers.get(provider, model_identifiers["gemini_image"])

        refined_prompt = (
            f"masterpiece, ethereal composition, cinematic lighting, japanese aesthetic, "
            f"subtle elegance, soft haze, {light_desc}, industrial metallic undertone: {prompt}"
        )

        image_filename = f"yuki_{provider}_{int(time.time())}.png"
        image_path = os.path.join(self.art_dir, image_filename)

        logger.info(f"🎨 Pintando lienzo visual [{provider}]: '{refined_prompt[:60]}...'")

        if self.vertex.is_available():
            resultado = await self.vertex.generate_image(refined_prompt, aspect_ratio=aspect_ratio)
            if resultado["status"] == "success":
                resultado["lighting"] = lighting_style
                # `image_url` apunta al fichero que existe, no a un CDN ficticio.
                resultado["image_url"] = local_uri(resultado["local_path"])
                return resultado
            # Fallo real: se propaga tal cual. Nunca se disfraza de éxito ni se
            # cae al marcador, que sería devolver un invento como si fuera arte.
            resultado["provider"] = provider
            resultado["image_url"] = None
            return resultado

        marcador = self._marcador(
            image_path,
            f"YUKI ART ASSET (SIMULADO - {provider}): {refined_prompt}",
            provider=provider,
            model=selected_model,
            prompt_used=refined_prompt,
            aspect_ratio=aspect_ratio,
            lighting=lighting_style,
        )
        marcador["image_url"] = marcador["local_uri"]
        return marcador

    async def generate_music_flow(
        self,
        title: str,
        prompt: str,
        engine: str = "flow_audio", # "lyria-3-pro-preview", "lyria-3-clip-preview", "midi_only"
        duration_seconds: int = 90,
        bpm: int = 84,
        scale: str = "Insen",
        mood_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sintetiza música completa y stems mediante motores de difusión de audio de frontera:
        - flow_audio: Flow / DeepMind AudioCraft (renderizado acústico de shamisen, koto y sub-bajo)
        - suno_v4: Suno v4 / Udio v1.5 (canción completa con lírica y voz cantada de Yuki)
        """
        if mood_params:
            bpm = mood_params.get('bpm', bpm)
            scale = mood_params.get('scale', scale)
            atmosphere = mood_params.get('atmosphere', '')
            if atmosphere:
                prompt = f"{prompt}, atmosphere: {atmosphere}"

        # Lyria se consume como publisher model por Interactions API: no hay
        # endpoint que desplegar ni GPU que mantener en la VM.
        if self.vertex.is_available() and (
            engine.startswith("lyria-") or engine in {"lyria", "vertex_lyria"}
        ):
            modelo = engine if engine.startswith("lyria-") else None
            resultado = await self.vertex.generate_music(
                prompt,
                duration_seconds=duration_seconds,
                model=modelo,
            )
            if resultado.get("status") == "success":
                resultado["audio_url"] = local_uri(resultado["local_path"])
            else:
                resultado["audio_url"] = None
            return resultado

        audio_filename = f"{title.lower().replace(' ', '_')}_{engine}_{int(time.time())}.mp3"
        audio_path = os.path.join(self.music_dir, audio_filename)

        # Vertex no sirve música cantada ni render acústico, y
        # `skills/HERRAMIENTAS.md` §1 ya declara que `suno_v4` y `flow_audio` no
        # existen en ninguna pasarela contratada. Mientras no se contrate un
        # motor musical, esto es un marcador y se dice: la música real de Yuki
        # sale hoy de `local.midi` (`src/tools/midi_generator.py`).
        logger.info(f"🎵 Marcador de pista [{engine}]: '{title}' ({bpm} BPM, escala {scale})")

        marcador = self._marcador(
            audio_path,
            f"YUKI MUSIC TRACK (SIMULADO - {engine}): {title} | Prompt: {prompt} | BPM: {bpm} | Scale: {scale}",
            engine=engine,
            title=title,
            duration_seconds=duration_seconds,
            bpm=bpm,
            scale=scale,
            prompt_used=prompt,
        )
        marcador["note"] = ("Ningún motor de música contratado: ni Vertex ni el Portal sirven "
                            "audio musical. Para partituras reales usa local.midi.")
        marcador["audio_url"] = marcador["local_uri"]
        return marcador

    async def synthesize_voice_tts(
        self,
        text: str,
        voice_id: str = "yuki_serene_alto",
        cadence_pause_ms: int = 350,
        is_night_mode: bool = False,
        engine: str = "gemini_multimodal_audio", # "gemini_multimodal_audio", "nous_tts_v2"
        mood_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sintetiza una nota de voz en formato OGG Opus con marcado SSML y prosodia de frontera.
        """
        if mood_params:
            cadence_pause_ms = mood_params.get('pause_ms', cadence_pause_ms)

        audio_filename = f"yuki_voice_{int(time.time())}.ogg"
        audio_path = os.path.join(self.voice_dir, audio_filename)

        pause_tag = f'<break time="{cadence_pause_ms}ms"/>'
        prosody_rate = "88%" if is_night_mode else "94%"
        prosody_pitch = "-2st" if is_night_mode else "-1st"

        if mood_params:
            prosody_rate = mood_params.get('rate', prosody_rate)
            prosody_pitch = mood_params.get('pitch', prosody_pitch)

        ssml_body = text.replace(". ", f". {pause_tag} ").replace(", ", f", {pause_tag} ")
        ssml_text = f"""<speak>
  <prosody rate="{prosody_rate}" pitch="{prosody_pitch}">
    {ssml_body}
  </prosody>
</speak>"""

        logger.info(f"🎙️ Sintetizando voz [{engine}]: '{text[:50]}...'")

        if self.vertex.is_available():
            # Gemini TTS toma la cadencia como una indicación en lenguaje
            # natural, no como marcado SSML. Se le describe la "pausa elegida"
            # de SOUL.md, que es más fiel que un <break> mecánico, y emite OGG
            # Opus nativo: no hace falta transcodificar con ffmpeg.
            registro = "más grave y lenta, casi un susurro" if is_night_mode else "serena y cálida"
            indicacion = (
                f"Habla en un registro {registro}, con pausas deliberadas de unos "
                f"{cadence_pause_ms} milisegundos en comas y puntos. Elige cada palabra "
                "antes de decirla; nunca suenes apresurada ni mecánica."
            )
            resultado = await self.vertex.synthesize_voice(text, style_prompt=indicacion)
            if resultado["status"] == "success":
                resultado["voice_id"] = resultado.get("voice", voice_id)
                resultado["is_night_mode"] = is_night_mode
                resultado["cadence_pause_ms"] = cadence_pause_ms
                resultado["duration_seconds"] = max(2.5, len(text) * 0.085)
                resultado["audio_url"] = local_uri(resultado["local_path"])
                return resultado
            resultado["provider"] = engine
            resultado["audio_url"] = None
            return resultado

        marcador = self._marcador(
            audio_path,
            f"YUKI VOICE ASSET (SIMULADO - {engine}): {ssml_text}",
            provider=engine,
            voice_id=voice_id,
            duration_seconds=max(2.5, len(text) * 0.085),
            ssml_payload=ssml_text,
            is_night_mode=is_night_mode,
        )
        marcador["audio_url"] = marcador["local_uri"]
        return marcador

    async def generate_video_frontier(
        self,
        prompt: str,
        duration_seconds: int = 6,
        aspect_ratio: str = "16:9",
        image_path: Optional[str] = None,
        mood_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Anima una portada o genera un teaser con Gemini Omni Flash.

        Con `image_path` parte de una portada ya pintada, que es lo que suele
        querer Yuki: primero el arte, luego el movimiento.

        **Es la herramienta más cara del catálogo.** Se factura por segundo de
        vídeo (≈0,10 USD/s), así que un teaser de diez segundos cuesta más que
        miles de respuestas de texto. No la invoques en tareas automáticas del
        cron sin que el productor lo haya pedido.
        """
        if mood_params:
            atmosfera = mood_params.get("atmosphere", "")
            if atmosfera:
                prompt = f"{prompt}, atmósfera: {atmosfera}"

        if self.vertex.is_available():
            return await self.vertex.generate_video(
                prompt,
                duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio,
                image_path=image_path,
            )

        video_path = os.path.join(self.video_dir, f"yuki_omni_{int(time.time())}.mp4")
        marcador = self._marcador(
            video_path,
            f"YUKI VIDEO ASSET (SIMULADO - gemini-omni): {prompt}",
            prompt_used=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
        )
        marcador["video_url"] = marcador["local_uri"]
        return marcador

    async def search_trends_firecrawl(
        self,
        query: str,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Inspecciona noticias y tendencias reales mediante Firecrawl.

        Antes esto devolvía dos resultados fijos con URLs inventadas y la
        etiqueta de un rastreador que nunca se llamó; la reflexión nocturna los
        tomaba por corrientes del mundo. Ahora la búsqueda es real cuando hay
        clave y, cuando no la hay, devuelve pistas marcadas `simulated: True`
        sin URL. La honestidad del resultado la comprueba quien lo use con
        `describe_origin`.
        """
        import asyncio

        logger.info(f"Buscando corrientes del mundo: '{query}' (buscador "
                    f"{'activo' if self.web_search.is_available() else 'no configurado'})")
        return await asyncio.to_thread(self.web_search.search, query, limit)
