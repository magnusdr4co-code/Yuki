"""
Tests de integración para el agente central de Yuki.

Estos tests fijan la fase circadiana a mano. No es una comodidad: sin fijarla,
`generate_response` depende de la hora de la máquina, porque el controlador de
presencia calla a Yuki durante `deep_rest` (00:00–02:00 en Europe/Madrid). El
test de tabú pasaba de día y fallaba de madrugada, y como `cloudbuild.yaml`
corre la suite como primer paso del pipeline, ese fallo bloqueaba el despliegue
a horas concretas y no a otras.
"""

import asyncio
import os
import unittest
from src.core.agent import YukiAgent


class RelojFijo:
    """Reloj circadiano con la fase clavada, para tests deterministas."""

    def __init__(self, phase: str):
        self.phase = phase

    def current_phase(self, dt=None) -> str:
        return self.phase

    def is_responsive(self, dt=None) -> bool:
        return self.phase != "deep_rest"


def _agente_en_fase(phase: str) -> YukiAgent:
    agent = YukiAgent()
    reloj = RelojFijo(phase)
    agent.circadian = reloj
    agent.presence_controller.circadian_clock = reloj
    return agent


class TestYukiAgent(unittest.TestCase):
    def test_agent_fast_response_and_taboo(self):
        async def _run():
            agent = _agente_en_fase("atelier")

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

    def test_el_productor_alcanza_a_yuki_en_deep_rest(self):
        """
        `PresenceController` reserva una excepción para que el productor llegue
        por privado durante el descanso profundo. Era código muerto: nadie
        pasaba `is_producer`, así que el productor se quedaba sin respuesta
        entre medianoche y las dos.
        """
        async def _run():
            agent = _agente_en_fase("deep_rest")
            agent.vital_state.energy = 0.6      # por encima del umbral de 0.3

            reply = await agent.generate_response(
                user_id="producer_manager",
                user_name="Productor",
                message="Hola Yuki, ¿sigues despierta?",
                channel_type="direct_message"
            )
            self.assertNotEqual(reply, "NADA_QUE_DECIR")
            self.assertGreater(len(reply), 10)

        asyncio.run(_run())

    def test_un_visitante_no_despierta_a_yuki_en_deep_rest(self):
        """El descanso sigue siendo descanso para todos los demás."""
        async def _run():
            agent = _agente_en_fase("deep_rest")
            agent.vital_state.energy = 0.6

            reply = await agent.generate_response(
                user_id="visitor_test",
                user_name="Visitante",
                message="¿Hola?",
                channel_type="direct_message"
            )
            self.assertEqual(reply, "NADA_QUE_DECIR")

        asyncio.run(_run())

    def test_discord_paired_id_is_recognized_as_producer(self):
        previous = os.environ.get("DISCORD_PAIRED_PRODUCER_ID")
        os.environ["DISCORD_PAIRED_PRODUCER_ID"] = "235796491988369408"
        try:
            agent = _agente_en_fase("deep_rest")
            self.assertTrue(agent.is_producer("235796491988369408"))
        finally:
            if previous is None:
                os.environ.pop("DISCORD_PAIRED_PRODUCER_ID", None)
            else:
                os.environ["DISCORD_PAIRED_PRODUCER_ID"] = previous

    def test_el_productor_se_identifica_desde_la_configuracion(self):
        agent = YukiAgent()
        self.assertTrue(agent.is_producer(agent.producer_user_id))
        self.assertFalse(agent.is_producer("visitor_test"))


if __name__ == "__main__":
    unittest.main()
