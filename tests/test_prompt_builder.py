"""
Tests para el constructor dinámico de contexto (PromptBuilder).
"""

import unittest
from src.core.prompt_builder import PromptBuilder

class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = PromptBuilder()

    def test_prompt_assembly(self):
        prompt = self.builder.build_system_prompt(
            retrieved_memory_block="[CORE - Origen]\nNacida donde el mar huele a metal.",
            dialectic_context="[HONCHO]\nPaleta Sonora: shamisen",
            user_name="Productor",
            user_id="producer_manager",
            channel_type="direct_message",
            active_role="news_watcher"
        )

        self.assertIn("Yuki", prompt)
        self.assertIn("Nacida donde el mar huele a metal", prompt)
        self.assertIn("shamisen", prompt)
        self.assertIn("Productor", prompt)
        self.assertIn("news_watcher", prompt)

if __name__ == "__main__":
    unittest.main()
