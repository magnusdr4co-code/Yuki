"""
Tests para herramientas de Nous Portal (FAL, TTS, Firecrawl).
"""

import asyncio
import unittest
from src.tools.nous_portal import NousPortalClient
from src.tools.media_creator import MediaCreatorTool

class TestNousTools(unittest.TestCase):
    def test_image_generation_fal(self):
        async def _run():
            portal = NousPortalClient()
            creator = MediaCreatorTool(portal)
            
            result = await creator.create_single_cover(
                track_title="Cerezos de Acero",
                visual_concept="Niebla y ramas secas sobre asfalto"
            )
            self.assertEqual(result["track_title"], "Cerezos de Acero")
            self.assertIn("https://nousportal.media/cdn/", result["cover_url"])
            self.assertTrue("fal-ai" in result["prompt_used"] or "aesthetic" in result["prompt_used"])

        asyncio.run(_run())

    def test_voice_synthesis_tts(self):
        async def _run():
            portal = NousPortalClient()
            creator = MediaCreatorTool(portal)
            
            voice = await creator.generate_voice_reply("La paciencia es el espacio entre dos notas.")
            self.assertGreater(voice["duration"], 0)
            self.assertTrue(voice["audio_url"].endswith(".ogg"))

        asyncio.run(_run())

if __name__ == "__main__":
    unittest.main()
