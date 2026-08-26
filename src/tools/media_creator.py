"""
Herramientas creativas de alto nivel para la Diva Digital.
Permite a Yuki pintar portadas con Gemini Image / Seedream / Flux Pro,
componer música con Flow Audio / Suno v4 / MIDI real,
y orquestar lanzamientos multimedia en el workspace nativo ./output/.
"""

import os
import json
import time
from typing import Dict, Any, Optional
from .nous_portal import NousPortalClient
from .midi_generator import YukiMIDIGenerator
from ..core.seasons import get_current_micro_season

class MediaCreatorTool:
    def __init__(self, portal_client: Optional[NousPortalClient] = None):
        self.portal = portal_client or NousPortalClient()
        self.midi_gen = YukiMIDIGenerator()

    async def create_single_cover(
        self,
        track_title: str,
        visual_concept: str,
        provider: str = "gemini_image", # "gemini_image", "seedream", "flux_pro"
        lighting: str = "komorebi"
    ) -> Dict[str, Any]:
        """Genera una portada de sencillo con modelos de frontera (Gemini Image / Seedream / Flux Pro)."""
        season = get_current_micro_season()
        prompt = f"Album single cover for track '{track_title}'. Concept: {visual_concept}. Seasonal motif: {season['seasonal_kigo']}. Traditional shamisen meets modern industrial minimalism."
        result = await self.portal.generate_image_frontier(
            prompt=prompt,
            provider=provider,
            aspect_ratio="1:1",
            lighting_style=lighting
        )
        return {
            "track_title": track_title,
            "provider": provider,
            "model_used": result["model"],
            "cover_url": result["image_url"],
            "local_path": result["local_path"],
            "prompt_used": result["prompt_used"],
            "season_used": season["sekki"]
        }

    async def generate_voice_reply(
        self,
        message_text: str,
        is_night_mode: bool = False,
        engine: str = "gemini_multimodal_audio"
    ) -> Dict[str, Any]:
        """Genera una nota de voz SSML con motor de audio de frontera en ./output/voice/."""
        result = await self.portal.synthesize_voice_tts(
            text=message_text,
            is_night_mode=is_night_mode,
            engine=engine
        )
        return {
            "audio_url": result["audio_url"],
            "local_path": result["local_path"],
            "duration": result["duration_seconds"],
            "transcript": message_text,
            "ssml": result["ssml_payload"],
            "provider": engine
        }

    async def compose_beat_structure(
        self,
        title: str,
        bpm: int = 84,
        scale: str = "insen",
        mood: str = "lluvia sobre metal",
        engine: str = "flow_audio" # "flow_audio", "suno_v4", "midi_only"
    ) -> Dict[str, Any]:
        """
        Compone una pieza musical con motores de audio de frontera (Flow / Suno v4)
        generando también la partitura MIDI multipista procedural en ./output/music/.
        """
        music_dir = "output/music"
        os.makedirs(music_dir, exist_ok=True)
        
        # 1. Generar archivo MIDI binario real
        midi_result = self.midi_gen.generate_track(
            title=title,
            scale_name=scale,
            bpm=bpm,
            num_bars=16,
            output_dir=music_dir
        )

        season = get_current_micro_season()
        prompt = f"Atmospheric organic lofi track '{title}', authentic Japanese shamisen lead, subtle koto arpeggio, 808 deep sub-bass, mood: {mood}, season: {season['seasonal_kigo']}"
        
        # 2. Generar síntesis de audio de frontera (Flow Audio / Suno)
        audio_result = await self.portal.generate_music_flow(
            title=title,
            prompt=prompt,
            engine=engine,
            bpm=bpm,
            scale=scale
        )

        track_data = {
            "title": title,
            "bpm": bpm,
            "scale": f"{scale.capitalize()} (Tradicional Japonesa)",
            "mood": mood,
            "music_engine": engine,
            "seasonal_influence": season["sekki"],
            "midi_file": midi_result["filename"],
            "audio_rendered_file": os.path.basename(audio_result["local_path"]),
            "structure": [
                {"section": "Intro", "bars": 4, "lead": f"shamisen solo con atmósfera de {season['seasonal_kigo']}"},
                {"section": "A (Tema Principal)", "bars": 8, "lead": "shamisen acústico + Flow Audio bassline"},
                {"section": "B (Transición Sombra)", "bars": 8, "lead": "bajo 808 profundo y pausas (Ma)"},
                {"section": "Outro", "bars": 4, "lead": "eco de shamisen desvaneciéndose en silencio"}
            ],
            "created_at": time.time()
        }

        meta_path = os.path.join(music_dir, f"{title.lower().replace(' ', '_')}_{int(time.time())}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(track_data, f, indent=2, ensure_ascii=False)

        return {
            "status": "success",
            "title": title,
            "meta_path": meta_path,
            "midi_path": midi_result["file_path"],
            "audio_rendered_path": audio_result["local_path"],
            "audio_url": audio_result["audio_url"],
            "midi_bytes": midi_result["size_bytes"],
            "track_data": track_data
        }

    async def execute_single_release_pipeline(
        self,
        title: str,
        concept: str,
        image_provider: str = "gemini_image",
        music_engine: str = "flow_audio",
        scale: str = "insen",
        bpm: int = 82
    ) -> Dict[str, Any]:
        """
        Orquestación de lanzamiento con suite completa de frontera:
        - Música: Flow Audio / Suno v4 + MIDI real
        - Portada: Gemini Image / Seedream / Flux Pro
        - Lírica Waka estacional
        - Voz: Gemini Multimodal Audio SSML
        """
        # Paso 1: Beat con Flow Audio + MIDI
        music_res = await self.compose_beat_structure(
            title=title, bpm=bpm, scale=scale, mood=concept, engine=music_engine
        )
        
        # Paso 2: Portada con Gemini Image / Seedream
        art_res = await self.create_single_cover(
            track_title=title, visual_concept=concept, provider=image_provider, lighting="urushi"
        )

        # Paso 3: Poema lírico
        season = get_current_micro_season()
        lyrics = f"Sobre el metal frío,\ncae la lluvia de {season['seasonal_kigo']},\nel shamisen llama.\nEn el silencio activo,\nlas palabras encuentran paz."

        # Paso 4: Nota de voz con Gemini Audio
        voice_res = await self.generate_voice_reply(
            message_text=f"Presento '{title}'. Una pieza nacida en el silencio de {season['sekki']}.",
            engine="gemini_multimodal_audio"
        )

        # Paso 5: Post empaquetado en ./output/posts/
        posts_dir = "output/posts"
        os.makedirs(posts_dir, exist_ok=True)
        post_file = os.path.join(posts_dir, f"single_release_{title.lower().replace(' ', '_')}.md")

        with open(post_file, "w", encoding="utf-8") as f:
            f.write(f"""# Lanzamiento Oficial: {title}
*Diva Digital Autónoma: Yuki (雪)*
*Estación: {season['sekki']} ({season['micro_season_ko']})*
*Motores de Frontera: {image_provider.upper()} (Visual) + {music_engine.upper()} (Audio) + Gemini Audio (Voz)*

## Lírica Waka:
> {lyrics.replace(chr(10), chr(10) + '> ')}

## Recursos del Workspace:
- 🎵 Render de Audio ({music_engine}): `{music_res['audio_rendered_path']}`
- 🎼 Pista MIDI multipista: `{music_res['midi_path']}`
- 🎨 Portada ({image_provider}): `{art_res['local_path']}`
- 🎙️ Nota de Voz (Gemini SSML): `{voice_res['local_path']}`
""")

        return {
            "status": "completed",
            "title": title,
            "post_package": post_file,
            "image_provider": image_provider,
            "music_engine": music_engine,
            "music": music_res,
            "art": art_res,
            "voice": voice_res,
            "lyrics": lyrics
        }
