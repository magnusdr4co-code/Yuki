"""
Tests para el modelado dialéctico Honcho.
"""

import unittest
from src.honcho.dialectic import HonchoDialecticClient
from src.honcho.profile_sync import HonchoProfileSync

class TestHonchoDialectic(unittest.TestCase):
    def test_dialectic_profile_generation(self):
        client = HonchoDialecticClient(app_id="test-diva")
        context = client.get_dialectic_context(user_id="producer_manager")
        self.assertIn("MODELADO DIALÉCTICO HONCHO", context)
        self.assertIn("Paleta Sonora Acordada", context)

    def test_dialectic_exchange_update(self):
        client = HonchoDialecticClient(app_id="test-diva")
        sync = HonchoProfileSync(client)
        
        result = client.process_dialectic_exchange(
            user_message="Hagamos la siguiente portada más minimalista y con tonos oscuros",
            agent_response="Entiendo tu propuesta. El contraste entre la sombra y la línea simple dará fuerza al trabajo.",
            user_id="producer_manager"
        )
        self.assertEqual(result["status"], "synchronized")
        self.assertIn("minimalismo severo", client._local_profile["aesthetic_preferences"]["visual_palette"])

if __name__ == "__main__":
    unittest.main()
