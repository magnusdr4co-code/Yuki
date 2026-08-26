"""
Tests para los endpoints y lógica del servidor Web Dashboard.
"""

import unittest
import json
import os
from src.web.server import SalonHTTPHandler

class TestWebServerLogic(unittest.TestCase):
    def test_get_agent_instance(self):
        agent = SalonHTTPHandler.get_agent()
        self.assertIsNotNone(agent)
        self.assertIsNotNone(agent.memory_manager)

    def test_salon_template_exists(self):
        tmpl = os.path.join("src", "web", "templates", "salon.html")
        self.assertTrue(os.path.exists(tmpl), "La plantilla salon.html debe existir")
        with open(tmpl, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Salón de Yuki", content)
        self.assertIn("Canvas de la Sala", content)

if __name__ == "__main__":
    unittest.main()
