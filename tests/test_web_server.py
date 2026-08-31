"""
Tests para los endpoints y lógica del servidor Web Dashboard.
Incluye el contrato que exigen las plataformas gestionadas: puerto por
variable de entorno PORT y sonda de vida en /health.
"""

import unittest
import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from src.web.server import SalonHTTPHandler, resolve_port, DEFAULT_PORT


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


class TestPortResolution(unittest.TestCase):
    def setUp(self):
        self._original = os.environ.pop("PORT", None)

    def tearDown(self):
        os.environ.pop("PORT", None)
        if self._original is not None:
            os.environ["PORT"] = self._original

    def test_default_port_when_env_absent(self):
        self.assertEqual(resolve_port(), DEFAULT_PORT)

    def test_explicit_port_when_env_absent(self):
        self.assertEqual(resolve_port(9999), 9999)

    def test_env_port_wins(self):
        """Cloud Run inyecta PORT y espera que el proceso lo obedezca."""
        os.environ["PORT"] = "8081"
        self.assertEqual(resolve_port(), 8081)
        self.assertEqual(resolve_port(9999), 8081)

    def test_invalid_env_port_falls_back(self):
        os.environ["PORT"] = "no-soy-un-puerto"
        self.assertEqual(resolve_port(), DEFAULT_PORT)


class TestHealthEndpoint(unittest.TestCase):
    """Arranca el servidor real y comprueba la sonda de arranque."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SalonHTTPHandler)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_health_returns_ok(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "yuki-salon")

    def test_healthz_alias(self):
        status, body = self._get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_unknown_route_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/no-existe")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
