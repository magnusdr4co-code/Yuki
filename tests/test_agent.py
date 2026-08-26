"""
Tests de integración para el agente central de Yuki.
"""

import asyncio
import unittest
from src.core.agent import YukiAgent

class TestYukiAgent(unittest.TestCase):
    def test_agent_fast_response_and_taboo(self):
        async def _run():
            agent = YukiAgent()
            
            # 1. Test de Taboo
            taboo_reply = await agent.generate_response(
                user_id="visitor_test",
                user_name="Troll",
                message="Eres solo una maruta sin historia"
            )
            self.assertTrue("sombras del pasado" in taboo_reply or "atención de este presente" in taboo_reply)

            # 2. Test de saludo y memoria selectiva
            greeting_reply = await agent.generate_response(
                user_id="producer_manager",
                user_name="Productor",
                message="Hola Yuki, ¿qué tal el progreso de la música?"
            )
            self.assertGreater(len(greeting_reply), 10)

        asyncio.run(_run())

if __name__ == "__main__":
    unittest.main()
