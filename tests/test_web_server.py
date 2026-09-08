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


# --- Puerta de entrada del Salón ---

class _PeticionFalsa:
    """Handler mínimo para ejercitar la autorización sin abrir un socket."""

    def __init__(self, path, headers=None, cliente="10.0.0.1"):
        self.path = path
        self.headers = headers or {}
        self.client_address = (cliente, 5000)

    def get(self, clave, defecto=None):
        return self.headers.get(clave, defecto)


def _handler(path, headers=None, cliente="10.0.0.1"):
    from src.web.server import SalonHTTPHandler

    handler = SalonHTTPHandler.__new__(SalonHTTPHandler)
    handler.path = path
    handler.headers = headers or {}
    handler.client_address = (cliente, 5000)
    return handler


def test_sin_token_declarado_todo_sigue_abierto(monkeypatch):
    monkeypatch.delenv("SALON_API_TOKEN", raising=False)

    assert _handler("/api/chat")._autorizado("/api/chat")


def test_con_token_las_rutas_de_datos_exigen_credencial(monkeypatch):
    monkeypatch.setenv("SALON_API_TOKEN", "secreto-del-salon")

    assert not _handler("/api/chat")._autorizado("/api/chat")
    assert not _handler("/api/memories")._autorizado("/api/memories")
    assert not _handler("/api/honcho")._autorizado("/api/honcho")


def test_la_sonda_y_la_pagina_nunca_piden_credencial(monkeypatch):
    """Si /health pidiera token, la plataforma daría la instancia por muerta."""
    monkeypatch.setenv("SALON_API_TOKEN", "secreto-del-salon")

    assert _handler("/health")._autorizado("/health")
    assert _handler("/")._autorizado("/")


def test_se_admite_bearer_y_parametro(monkeypatch):
    monkeypatch.setenv("SALON_API_TOKEN", "secreto-del-salon")

    con_cabecera = _handler("/api/chat", {"Authorization": "Bearer secreto-del-salon"})
    con_parametro = _handler("/api/chat?token=secreto-del-salon")
    equivocado = _handler("/api/chat", {"Authorization": "Bearer otro"})

    assert con_cabecera._autorizado("/api/chat")
    assert con_parametro._autorizado("/api/chat")
    assert not equivocado._autorizado("/api/chat")


def test_el_techo_de_peticiones_protege_memoria_y_credito(monkeypatch):
    from src.web.server import LIMITE_PETICIONES, SalonHTTPHandler

    SalonHTTPHandler._historial_peticiones.clear()
    handler = _handler("/api/chat", cliente="203.0.113.7")

    permitidas = sum(1 for _ in range(LIMITE_PETICIONES + 5) if handler._dentro_del_limite())

    assert permitidas == LIMITE_PETICIONES
    # Otro cliente no hereda el castigo del primero.
    assert _handler("/api/chat", cliente="203.0.113.8")._dentro_del_limite()
    SalonHTTPHandler._historial_peticiones.clear()


# --- Métricas para la sonda externa ---

def _metricas(monkeypatch=None):
    from src.web.server import SalonHTTPHandler

    handler = SalonHTTPHandler.__new__(SalonHTTPHandler)
    return handler._metricas()


def test_las_metricas_declaran_cada_familia_una_sola_vez():
    """
    El formato de exposición lo exige, y repetirlo por muestra —lo natural al
    escribir el bucle— hace que un parser estricto rechace la página entera.
    """
    salida = _metricas()

    ayudas = [linea.split()[2] for linea in salida.splitlines() if linea.startswith("# HELP")]
    tipos = [linea.split()[2] for linea in salida.splitlines() if linea.startswith("# TYPE")]

    assert ayudas, "debe exponer algo"
    assert len(ayudas) == len(set(ayudas)), f"familias repetidas: {ayudas}"
    assert sorted(ayudas) == sorted(tipos)


def test_cada_muestra_va_despues_de_su_familia():
    salida = _metricas()

    familia_actual = None
    for linea in salida.splitlines():
        if linea.startswith("# HELP"):
            familia_actual = linea.split()[2]
        elif linea and not linea.startswith("#"):
            assert familia_actual and linea.startswith(familia_actual), linea


def test_las_metricas_cubren_lo_que_puede_doler():
    """Gasto, iniciativa, deriva, cumplimiento e integridad de la bitácora."""
    salida = _metricas()

    for esperada in ("yuki_gasto_hoy", "yuki_agencia_actos_hoy", "yuki_persona_reanclajes",
                     "yuki_material_sin_marcar", "yuki_bitacora_integra"):
        assert esperada in salida, f"falta {esperada}"


def test_los_valores_son_numeros_parseables():
    salida = _metricas()

    for linea in salida.splitlines():
        if linea and not linea.startswith("#"):
            valor = linea.rsplit(" ", 1)[1]
            float(valor)  # levanta si no es un número


def test_las_metricas_no_estan_abiertas(monkeypatch):
    """Consumo, deriva y ritmos dicen bastante de la instancia."""
    monkeypatch.setenv("SALON_API_TOKEN", "secreto-del-salon")

    assert not _handler("/metrics")._autorizado("/metrics")
    assert _handler("/health")._autorizado("/health")
