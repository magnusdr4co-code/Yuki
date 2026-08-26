"""
Herramientas creativas de alto nivel para la Diva Digital.
Permite a Yuki pintar portadas, emitir notas de voz, componer estructuras de beat y publicar en redes.
Todas las salidas se organizan en ./output/ (Workspace nativo de Hermes).
"""

import os
import json
import time
from typing import Dict, Any, Optional
from .nous_portal import NousPortalClient

class MediaCreatorTool:
    def __init__(self, portal_client: Optional[NousPortalClient] = None):
        self.portal = portal_client or NousPortalClient()

    async def create_single_cover(self, track_title: str, visual_concept: str) -> Dict[str, Any]:
        """Genera una portada de sencillo artística en ./output/art/."""
        prompt = f"Album single cover for track '{track_title}'. Concept: {visual_concept}. Traditional shamisen meets modern industrial minimalism."
        result = await self.portal.generate_image_fal(prompt=prompt, aspect_ratio="1:1")
        return {
            "track_title": track_title,
            "cover_url": result["image_url"],
            "local_path": result["local_path"],
            "prompt_used": result["prompt_used"]
        }

    async def generate_voice_reply(self, message_text: str) -> Dict[str, Any]:
        """Genera una nota de voz en ./output/voice/ para responder a menciones o seguidores."""
        result = await self.portal.synthesize_voice_tts(text=message_text)
        return {
            "audio_url": result["audio_url"],
            "local_path": result["local_path"],
            "duration": result["duration_seconds"],
            "transcript": message_text
        }

    async def compose_beat_structure(
        self,
        title: str,
        bpm: int = 84,
        scale: str = "Insen (Japonesa menor)",
        mood: str = "lluvia sobre metal",
        elements: Optional[list] = None
    ) -> Dict[str, Any]:
        """Compone una estructura armónica y rítmica y la guarda en ./output/music/."""
        music_dir = "output/music"
        os.makedirs(music_dir, exist_ok=True)
        
        elements = elements or ["shamisen acústico", "sub-bajo orgánico 808", "textura de lluvia grabada", "campana de templo"]
        track_data = {
            "title": title,
            "bpm": bpm,
            "scale": scale,
            "mood": mood,
            "elements": elements,
            "structure": [
                {"section": "Intro", "bars": 8, "lead": "shamisen solo con sonido de lluvia"},
                {"section": "A (Tema Principal)", "bars": 16, "lead": "shamisen + percusión lofi contenida"},
                {"section": "B (Transición Sombra)", "bars": 16, "lead": "bajo profundo y pausas (Ma)"},
                {"section": "Outro", "bars": 8, "lead": "eco de shamisen desvaneciéndose en silencio"}
            ],
            "created_at": time.time()
        }

        filename = f"{title.lower().replace(' ', '_')}_{int(time.time())}.json"
        audio_mock_path = os.path.join(music_dir, f"{title.lower().replace(' ', '_')}.mp3")
        meta_path = os.path.join(music_dir, filename)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(track_data, f, indent=2, ensure_ascii=False)

        with open(audio_mock_path, "w", encoding="utf-8") as f:
            f.write(f"/* YUKI AUDIO STEM / BEAT ASSET: {title} ({bpm} BPM) */\n")

        return {
            "status": "success",
            "title": title,
            "meta_path": meta_path,
            "audio_path": audio_mock_path,
            "track_data": track_data
        }

    async def create_multimodal_drop(self, text: str, visual_prompt: str) -> Dict[str, Any]:
        """Crea un lanzamiento multimedia completo: texto + imagen FAL + audio TTS."""
        image_task = await self.portal.generate_image_fal(prompt=visual_prompt)
        voice_task = await self.portal.synthesize_voice_tts(text=text)

        posts_dir = "output/posts"
        os.makedirs(posts_dir, exist_ok=True)
        post_path = os.path.join(posts_dir, f"drop_{int(time.time())}.md")

        with open(post_path, "w", encoding="utf-8") as f:
            f.write(f"# Publicación de Yuki\n\n{text}\n\n![Portada]({image_task['local_path']})\n\n[Nota de Voz]({voice_task['local_path']})\n")

        return {
            "post_text": text,
            "post_file": post_path,
            "image": image_task,
            "voice": voice_task
        }
