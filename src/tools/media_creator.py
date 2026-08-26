"""
Herramientas creativas de alto nivel para la Diva Digital.
Permite a Yuki pintar portadas, emitir notas de voz SSML, componer archivos MIDI reales y orquestar lanzamientos completos.
Todas las salidas se organizan en ./output/ (Workspace nativo de Hermes).
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
        lighting: str = "komorebi"
    ) -> Dict[str, Any]:
        """Genera una portada de sencillo artística en ./output/art/ con FAL.ai."""
        season = get_current_micro_season()
        prompt = f"Album single cover for track '{track_title}'. Concept: {visual_concept}. Seasonal motif: {season['seasonal_kigo']}. Traditional shamisen meets modern industrial minimalism."
        result = await self.portal.generate_image_fal(prompt=prompt, aspect_ratio="1:1", lighting_style=lighting)
        return {
            "track_title": track_title,
            "cover_url": result["image_url"],
            "local_path": result["local_path"],
            "prompt_used": result["prompt_used"],
            "season_used": season["sekki"]
        }

    async def generate_voice_reply(self, message_text: str, is_night_mode: bool = False) -> Dict[str, Any]:
        """Genera una nota de voz con marcado SSML en ./output/voice/."""
        result = await self.portal.synthesize_voice_tts(text=message_text, is_night_mode=is_night_mode)
        return {
            "audio_url": result["audio_url"],
            "local_path": result["local_path"],
            "duration": result["duration_seconds"],
            "transcript": message_text,
            "ssml": result["ssml_payload"]
        }

    async def compose_beat_structure(
        self,
        title: str,
        bpm: int = 84,
        scale: str = "insen",
        mood: str = "lluvia sobre metal"
    ) -> Dict[str, Any]:
        """
        Compone una estructura musical y genera tanto el archivo de metadata .json
        como el archivo MIDI real (.mid) multipista en ./output/music/.
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
        track_data = {
            "title": title,
            "bpm": bpm,
            "scale": f"{scale.capitalize()} (Tradicional Japonesa)",
            "mood": mood,
            "seasonal_influence": season["sekki"],
            "midi_file": midi_result["filename"],
            "structure": [
                {"section": "Intro", "bars": 4, "lead": f"shamisen solo con atmósfera de {season['seasonal_kigo']}"},
                {"section": "A (Tema Principal)", "bars": 8, "lead": "shamisen + percusión lofi contenida"},
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
            "midi_bytes": midi_result["size_bytes"],
            "track_data": track_data
        }

    async def execute_single_release_pipeline(
        self,
        title: str,
        concept: str,
        scale: str = "insen",
        bpm: int = 82
    ) -> Dict[str, Any]:
        """
        Mega-habilidad de Skill Chaining:
        1. Composición de beat + archivo MIDI (.mid)
        2. Creación de portada visual FAL (.png)
        3. Composición de poema Waka
        4. Síntesis de voz emotiva SSML (.ogg)
        5. Preparación del paquete de publicación en ./output/posts/
        """
        # Paso 1: Beat y MIDI
        music_res = await self.compose_beat_structure(title=title, bpm=bpm, scale=scale, mood=concept)
        
        # Paso 2: Portada FAL
        art_res = await self.create_single_cover(track_title=title, visual_concept=concept, lighting="urushi")

        # Paso 3: Poema lírico
        season = get_current_micro_season()
        lyrics = f"Sobre el metal frío,\ncae la lluvia de {season['seasonal_kigo']},\nel shamisen llama.\nEn el silencio activo,\nlas palabras encuentran paz."

        # Paso 4: Nota de voz
        voice_res = await self.generate_voice_reply(message_text=f"Presento '{title}'. Una pieza nacida en el silencio de {season['sekki']}.")

        # Paso 5: Post empaquetado
        posts_dir = "output/posts"
        os.makedirs(posts_dir, exist_ok=True)
        post_file = os.path.join(posts_dir, f"single_release_{title.lower().replace(' ', '_')}.md")

        with open(post_file, "w", encoding="utf-8") as f:
            f.write(f"""# Lanzamiento Oficial: {title}
*Diva Digital Autónoma: Yuki (雪)*
*Estación: {season['sekki']} ({season['micro_season_ko']})*

## Lírica Waka:
> {lyrics.replace(chr(10), chr(10) + '> ')}

## Recursos del Workspace:
- 🎵 Pista MIDI: `{music_res['midi_path']}`
- 🎨 Portada FAL: `{art_res['local_path']}`
- 🎙️ Nota de Voz (SSML): `{voice_res['local_path']}`
""")

        return {
            "status": "completed",
            "title": title,
            "post_package": post_file,
            "music": music_res,
            "art": art_res,
            "voice": voice_res,
            "lyrics": lyrics
        }
