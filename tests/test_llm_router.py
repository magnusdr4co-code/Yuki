"""
Tests del enrutador de pasarelas de lenguaje.

Verifican el orden declarado por la arquitectura (Nous Portal → OpenRouter →
voz local) y que ninguna clave de marcador de posición se tome por válida.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.llm_router import (
    LLMRouter,
    LLMResponse,
    LLMProvider,
    NousPortalProvider,
    OpenRouterProvider,
    LocalVoiceProvider,
    is_usable_key,
    normalize_model,
    local_voice_response,
)


# --- Validación de claves ---

@pytest.mark.parametrize("key", [
    None, "", "   ",
    "your_openrouter_api_key_here",   # marcador de .env.example
    "your_nous_portal_token_here",
    "changeme",
])
def test_placeholder_keys_are_rejected(key):
    assert not is_usable_key(key)


def test_real_looking_key_is_accepted():
    assert is_usable_key("sk-or-v1-abc123def456")


# --- Nombres de modelo ---

def test_aggregator_prefix_is_stripped():
    """hermes_config.yaml usa `openrouter/...`; la API de OpenRouter no."""
    assert normalize_model("openrouter/anthropic/claude-3.5-sonnet") == "anthropic/claude-3.5-sonnet"
    assert normalize_model("openrouter/google/gemini-2.0-flash") == "google/gemini-2.0-flash"


def test_model_without_prefix_is_untouched():
    assert normalize_model("anthropic/claude-3.5-sonnet") == "anthropic/claude-3.5-sonnet"


# --- Nous Portal ---

def test_nous_portal_disabled_by_default(monkeypatch):
    """El endpoint no existe todavía: no debe fingir que sirve tráfico real."""
    monkeypatch.delenv("NOUS_PORTAL_MODE", raising=False)
    p = NousPortalProvider(api_key="cualquiera")
    assert not p.is_available()
    assert p.generate("sistema", "hola") is None


def test_nous_portal_mode_read_from_environment(monkeypatch):
    monkeypatch.setenv("NOUS_PORTAL_MODE", "mock")
    p = NousPortalProvider(api_key="cualquiera")
    assert p.is_available()


def test_nous_portal_mock_mode_responds_marked_as_simulated():
    p = NousPortalProvider(api_key="cualquiera", mode="mock")
    assert p.is_available()
    resp = p.generate("sistema", "hola")
    assert resp is not None
    assert resp.provider == "nous_portal"
    assert resp.simulated is True
    assert resp.text


# --- OpenRouter ---

def test_openrouter_unavailable_without_key():
    p = OpenRouterProvider(api_key="")
    assert not p.is_available()
    assert p.generate("sistema", "hola") is None


def test_openrouter_rejects_placeholder_key():
    p = OpenRouterProvider(api_key="your_openrouter_api_key_here")
    assert not p.is_available()


def test_openrouter_available_with_real_key():
    p = OpenRouterProvider(api_key="sk-or-v1-abc123")
    assert p.is_available()


def test_openrouter_normalizes_models_at_construction():
    p = OpenRouterProvider(
        api_key="sk-or-v1-abc",
        primary_model="openrouter/anthropic/claude-3.5-sonnet",
        fallback_model="openrouter/google/gemini-2.0-flash",
    )
    assert p.primary_model == "anthropic/claude-3.5-sonnet"
    assert p.fallback_model == "google/gemini-2.0-flash"


# --- Voz local ---

def test_local_voice_always_available():
    p = LocalVoiceProvider()
    assert p.is_available()
    resp = p.generate("sistema", "cualquier cosa")
    assert resp.simulated is True
    assert resp.text


def test_local_voice_keeps_yuki_cadence():
    assert "mar" in local_voice_response("hola")
    assert "shamisen" in local_voice_response("háblame de música")
    assert "Río" in local_voice_response("¿recuerdas el álbum?")


# --- Cadena de enrutado ---

class ProveedorFalso(LLMProvider):
    def __init__(self, name, available, text=None):
        self.name = name
        self._available = available
        self._text = text
        self.llamado = False

    def is_available(self):
        return self._available

    def generate(self, system_prompt, user_message):
        self.llamado = True
        if self._text is None:
            return None
        return LLMResponse(text=self._text, provider=self.name)


def test_first_available_provider_wins():
    primero = ProveedorFalso("nous_portal", True, "desde la pasarela")
    segundo = ProveedorFalso("openrouter", True, "desde el agregador")
    router = LLMRouter(providers=[primero, segundo])

    resp = router.generate("sistema", "hola")

    assert resp.text == "desde la pasarela"
    assert resp.provider == "nous_portal"
    assert not segundo.llamado


def test_falls_through_to_next_when_unavailable():
    """Es el caso real hoy: Nous Portal no existe, responde OpenRouter."""
    primero = ProveedorFalso("nous_portal", False)
    segundo = ProveedorFalso("openrouter", True, "desde el agregador")
    router = LLMRouter(providers=[primero, segundo])

    resp = router.generate("sistema", "hola")

    assert resp.provider == "openrouter"
    assert not primero.llamado


def test_falls_through_when_provider_errors():
    primero = ProveedorFalso("nous_portal", True, None)   # disponible pero falla
    segundo = ProveedorFalso("openrouter", True, "rescate")
    router = LLMRouter(providers=[primero, segundo])

    resp = router.generate("sistema", "hola")

    assert primero.llamado
    assert resp.provider == "openrouter"


def test_local_voice_is_last_resort():
    router = LLMRouter(providers=[
        ProveedorFalso("nous_portal", False),
        ProveedorFalso("openrouter", False),
        LocalVoiceProvider(),
    ])
    resp = router.generate("sistema", "hola")
    assert resp.provider == "voz_local"
    assert resp.simulated is True


def test_router_never_returns_empty_text():
    router = LLMRouter(providers=[ProveedorFalso("roto", False)])
    resp = router.generate("sistema", "hola")
    assert resp.text


# --- Orden por defecto y lectura de configuración ---

def test_default_chain_follows_declared_architecture():
    router = LLMRouter(config={})
    assert [p.name for p in router.providers] == ["nous_portal", "openrouter", "voz_local"]


def test_router_reads_model_from_agent_section():
    """
    El modelo se declara bajo `agent.model` en config.yaml.
    Antes se leía `config["model"]`, que no existe, y se ignoraban los ajustes.
    """
    config = {
        "agent": {
            "model": {
                "primary_model": "anthropic/claude-3.5-sonnet",
                "fallback_model": "google/gemini-2.0-flash",
                "temperature": 0.72,
                "max_tokens": 1024,
            }
        }
    }
    router = LLMRouter(config=config)
    openrouter = [p for p in router.providers if p.name == "openrouter"][0]

    assert openrouter.primary_model == "anthropic/claude-3.5-sonnet"
    assert openrouter.fallback_model == "google/gemini-2.0-flash"
    assert openrouter.temperature == 0.72
    assert openrouter.max_tokens == 1024


def test_real_config_yaml_is_read_correctly():
    import yaml
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    router = LLMRouter(config=config)
    openrouter = [p for p in router.providers if p.name == "openrouter"][0]

    declarado = config["agent"]["model"]
    assert openrouter.primary_model == normalize_model(declarado["primary_model"])
    assert openrouter.temperature == declarado["temperature"]


# --- Integración real de la ruta de OpenRouter ---

def test_openrouter_emits_a_correct_request():
    """
    Levanta un servidor que imita a OpenRouter y comprueba que la petición
    sale bien formada: ruta, cabecera de autorización, modelo sin el prefijo
    del agregador y los ajustes declarados en config.yaml.
    """
    pytest.importorskip("openai", reason="El SDK openai no está instalado")

    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    recibido = {}

    class FalsoOpenRouter(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            recibido.update(json.loads(self.rfile.read(n)))
            recibido["_ruta"] = self.path
            recibido["_auth"] = self.headers.get("Authorization")
            body = json.dumps({
                "id": "gen-1",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "La lluvia sobre el metal también canta."},
                    "finish_reason": "stop",
                }],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), FalsoOpenRouter)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    try:
        proveedor = OpenRouterProvider(
            api_key="sk-or-v1-prueba",
            primary_model="openrouter/anthropic/claude-3.5-sonnet",
            temperature=0.72,
            max_tokens=1024,
            base_url=f"http://127.0.0.1:{servidor.server_address[1]}",
        )
        resp = proveedor.generate("Eres Yuki.", "Háblame de la lluvia")
    finally:
        servidor.shutdown()
        servidor.server_close()

    assert recibido["_ruta"] == "/chat/completions"
    assert recibido["_auth"] == "Bearer sk-or-v1-prueba"
    assert recibido["model"] == "anthropic/claude-3.5-sonnet"   # prefijo eliminado
    assert recibido["temperature"] == 0.72
    assert recibido["max_tokens"] == 1024
    assert [m["role"] for m in recibido["messages"]] == ["system", "user"]

    assert resp is not None
    assert resp.provider == "openrouter"
    assert resp.simulated is False
    assert resp.text == "La lluvia sobre el metal también canta."
