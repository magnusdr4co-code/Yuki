"""
Tests del enrutador de pasarelas de lenguaje.

Verifican el orden declarado por la arquitectura (Nous Portal → Vertex →
OpenRouter → voz local) y que ninguna clave de marcador de posición se tome
por válida.
"""

import sys
import os
import logging
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.llm_router import (
    LLMRouter,
    LLMResponse,
    LLMProvider,
    NousPortalProvider,
    VertexProvider,
    OpenRouterProvider,
    LocalVoiceProvider,
    is_usable_key,
    normalize_model,
    normalize_vertex_model,
    local_voice_response,
    vertex_host,
    ai_studio_key_in_use,
    gce_service_account_scopes,
    gce_scopes_permiten_vertex,
    CLOUD_PLATFORM_SCOPE,
)


@pytest.fixture(autouse=True)
def entorno_vertex_limpio(monkeypatch):
    """
    Aísla los tests de un Google Cloud configurado en la máquina.

    Sin esto, un `GOOGLE_CLOUD_PROJECT` real en el entorno del desarrollador
    activaría la pasarela de Vertex y cambiaría el resultado de los tests que
    comprueban la cadena por defecto.
    """
    for var in ("VERTEX_PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "VERTEX_LOCATION"):
        monkeypatch.delenv(var, raising=False)


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
    assert [p.name for p in router.providers] == [
        "nous_portal", "vertex_ai", "openrouter", "voz_local",
    ]


def test_vertex_is_inert_without_a_project():
    """
    La propiedad que sostiene todo lo demás: sin proyecto declarado, la cadena
    se comporta igual que antes de existir esta pasarela. Es lo que permite
    agotar el crédito sin que Yuki se quede muda.
    """
    router = LLMRouter(config={})
    vertex = [p for p in router.providers if p.name == "vertex_ai"][0]
    assert not vertex.is_available()
    assert vertex.generate("sistema", "hola") is None


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


# --- Vertex AI ---

def test_vertex_unavailable_without_project():
    p = VertexProvider(project_id="")
    assert not p.is_available()
    assert p.generate("sistema", "hola") is None


def test_vertex_rejects_placeholder_project():
    p = VertexProvider(project_id="your_project_id_here")
    assert not p.is_available()


def test_vertex_available_with_project():
    assert VertexProvider(project_id="yuki-diva").is_available()


def test_vertex_can_be_switched_off_while_project_remains():
    """
    Al agotarse el crédito interesa apagar la ruta sin borrar la configuración,
    para poder volver a encenderla sin recordar el identificador del proyecto.
    """
    p = VertexProvider(project_id="yuki-diva", enabled=False)
    assert not p.is_available()


def test_vertex_reads_project_from_environment(monkeypatch):
    """En Cloud Run el proyecto llega por el entorno, no por config.yaml."""
    monkeypatch.setenv("VERTEX_PROJECT_ID", "yuki-diva")
    assert VertexProvider().is_available()


def test_vertex_empty_config_value_does_not_mask_environment(monkeypatch):
    """
    `config.yaml` trae `project_id: ""`. Ese vacío no debe tapar la variable de
    entorno, que es como se declara el proyecto en despliegue.
    """
    monkeypatch.setenv("VERTEX_PROJECT_ID", "yuki-diva")
    p = VertexProvider(project_id="")
    assert p.project_id == "yuki-diva"
    assert p.is_available()


def test_vertex_prefers_explicit_project_over_environment(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJECT_ID", "del-entorno")
    assert VertexProvider(project_id="explicito").project_id == "explicito"


# --- Nombres de modelo en Vertex ---

@pytest.mark.parametrize("declarado,esperado", [
    ("gemini-3.7-flash", "google/gemini-3.7-flash"),          # sin publisher
    ("google/gemini-3.7-flash", "google/gemini-3.7-flash"),   # ya canónico
    ("vertex/gemini-3.7-flash", "google/gemini-3.7-flash"),   # prefijo de ruta
    ("vertex_ai/gemini-3.6-flash", "google/gemini-3.6-flash"),
    ("openrouter/google/gemini-2.0-flash", "google/gemini-2.0-flash"),
])
def test_vertex_model_names_are_normalized(declarado, esperado):
    assert normalize_vertex_model(declarado) == esperado


def test_vertex_normalizes_models_at_construction():
    p = VertexProvider(
        project_id="yuki-diva",
        primary_model="gemini-3.7-flash",
        fallback_model="vertex/gemini-3.6-flash",
    )
    assert p.primary_model == "google/gemini-3.7-flash"
    assert p.fallback_model == "google/gemini-3.6-flash"


# --- Endpoint compuesto ---

def test_vertex_endpoint_is_built_from_project_and_location():
    p = VertexProvider(project_id="yuki-diva", location="europe-southwest1")
    assert p.base_url == (
        "https://europe-southwest1-aiplatform.googleapis.com/v1/"
        "projects/yuki-diva/locations/europe-southwest1/endpoints/openapi"
    )


def test_vertex_location_defaults_to_global():
    assert VertexProvider(project_id="yuki-diva").location == "global"


def test_vertex_global_endpoint_has_no_region_prefix():
    """
    Regresión: la región `global` es la que traen config.yaml, .env.example y
    cloudbuild.yaml, y su host NO lleva prefijo. Con `global-aiplatform.
    googleapis.com` Google devuelve un 404, `generate` se lo traga y la cadena
    cae a OpenRouter sin decir nada: el crédito de Google Cloud no se toca.
    """
    p = VertexProvider(project_id="yuki-diva", location="global")
    assert p.base_url == (
        "https://aiplatform.googleapis.com/v1/"
        "projects/yuki-diva/locations/global/endpoints/openapi"
    )
    assert "global-aiplatform" not in p.base_url


def test_vertex_host_por_region():
    assert vertex_host("global") == "aiplatform.googleapis.com"
    assert vertex_host("") == "aiplatform.googleapis.com"
    assert vertex_host("europe-southwest1") == "europe-southwest1-aiplatform.googleapis.com"
    assert vertex_host("us-central1") == "us-central1-aiplatform.googleapis.com"


def test_vertex_default_provider_uses_global_endpoint():
    """El proveedor que arma el router por defecto también apunta al host bueno."""
    vertex = [p for p in LLMRouter(config={"vertex_ai": {"project_id": "yuki-diva"}}).providers
              if p.name == "vertex_ai"][0]
    assert vertex.base_url.startswith("https://aiplatform.googleapis.com/")


# --- Ámbitos de la VM de Compute Engine ---

def test_scopes_por_defecto_de_una_vm_no_bastan_para_vertex():
    """
    Los ámbitos que Google da a una VM creada sin `--scopes`. `cloud-platform`
    no está entre ellos, y dentro de una VM son los ámbitos de la máquina —no
    los que pide el código— los que acaban en el token. Por eso una VM así
    recibe un 403 de Vertex aunque el rol de IAM sea el correcto.
    """
    por_defecto = [
        "https://www.googleapis.com/auth/devstorage.read_only",
        "https://www.googleapis.com/auth/logging.write",
        "https://www.googleapis.com/auth/monitoring.write",
        "https://www.googleapis.com/auth/service.management.readonly",
        "https://www.googleapis.com/auth/servicecontrol",
        "https://www.googleapis.com/auth/trace.append",
    ]
    assert gce_scopes_permiten_vertex(por_defecto) is False


def test_cloud_platform_basta_para_vertex():
    assert gce_scopes_permiten_vertex([CLOUD_PLATFORM_SCOPE]) is True


def test_sin_vm_no_se_afirma_nada():
    """Fuera de una VM no hay ámbitos que juzgar: ni sí ni no."""
    assert gce_scopes_permiten_vertex(None) is None


def test_los_scopes_se_leen_del_servidor_de_metadatos(monkeypatch):
    import urllib.request

    class RespuestaFalsa:
        def read(self):
            return (CLOUD_PLATFORM_SCOPE + "\nhttps://www.googleapis.com/auth/userinfo.email\n").encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    recibido = {}

    def urlopen_falso(peticion, timeout=None):
        recibido["url"] = peticion.full_url
        recibido["headers"] = peticion.headers
        return RespuestaFalsa()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_falso)

    scopes = gce_service_account_scopes()
    assert scopes == [CLOUD_PLATFORM_SCOPE, "https://www.googleapis.com/auth/userinfo.email"]
    assert recibido["url"].endswith("/instance/service-accounts/default/scopes")
    assert recibido["headers"]["Metadata-flavor"] == "Google"


def test_fuera_de_una_vm_el_metadato_no_revienta(monkeypatch):
    """Es un diagnóstico opcional: si no hay servidor de metadatos, se calla."""
    import urllib.request

    def urlopen_que_falla(peticion, timeout=None):
        raise OSError("no such host: metadata.google.internal")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_que_falla)
    assert gce_service_account_scopes() is None


# --- Aviso de facturación fuera del crédito ---

def test_ai_studio_key_detectada(monkeypatch):
    """
    Una clave de AI Studio en el entorno significa gasto bajo el producto
    «Gemini API», que está fuera del crédito de Google Cloud.
    """
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaClaveDePrueba")
    assert ai_studio_key_in_use() == "GEMINI_API_KEY"


def test_ai_studio_key_ignora_marcadores(monkeypatch):
    """El hueco de `.env.example` no cuenta como clave puesta."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_key_here")
    assert ai_studio_key_in_use() is None


def test_ai_studio_key_ausente(monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert ai_studio_key_in_use() is None


def test_vertex_avisa_cuando_se_degrada_a_openrouter(caplog):
    """
    Vertex configurada + fallo = el crédito no se consume. Ese hecho tiene que
    quedar escrito: es el fallo silencioso que dispara esta investigación.
    """
    class SinCredenciales(VertexProvider):
        def _access_token(self):
            return None

    p = SinCredenciales(project_id="yuki-diva", location="global")
    with caplog.at_level(logging.WARNING, logger="Yuki.LLMRouter"):
        assert p.generate("Eres Yuki.", "Hola") is None

    mensajes = " ".join(r.message for r in caplog.records)
    assert "CRÉDITO DE GOOGLE CLOUD NO SE ESTÁ CONSUMIENDO" in mensajes
    assert "vertex-check" in mensajes


def test_el_aviso_de_degradacion_no_se_repite(caplog):
    """Yuki corre 24/7: el aviso se dice una vez, no en cada petición."""
    class SinCredenciales(VertexProvider):
        def _access_token(self):
            return None

    p = SinCredenciales(project_id="yuki-diva")
    with caplog.at_level(logging.WARNING, logger="Yuki.LLMRouter"):
        for _ in range(5):
            p.generate("Eres Yuki.", "Hola")

    avisos = [r for r in caplog.records
              if "NO SE ESTÁ CONSUMIENDO" in r.message]
    assert len(avisos) == 1


# --- Configuración leída desde config.yaml ---

def test_router_reads_vertex_section():
    config = {
        "vertex_ai": {
            "enabled": True,
            "project_id": "yuki-diva",
            "location": "europe-southwest1",
            "primary_model": "google/gemini-3.7-flash",
            "fallback_model": "google/gemini-3.6-flash",
            "temperature": 0.5,
            "max_tokens": 800,
        }
    }
    vertex = [p for p in LLMRouter(config=config).providers if p.name == "vertex_ai"][0]

    assert vertex.is_available()
    assert vertex.project_id == "yuki-diva"
    assert vertex.location == "europe-southwest1"
    assert vertex.primary_model == "google/gemini-3.7-flash"
    assert vertex.temperature == 0.5
    assert vertex.max_tokens == 800


def test_vertex_falls_back_to_agent_model_settings():
    """Sin ajustes propios, hereda temperatura y longitud de `agent.model`."""
    config = {
        "agent": {"model": {"temperature": 0.9, "max_tokens": 1500}},
        "vertex_ai": {"project_id": "yuki-diva"},
    }
    vertex = [p for p in LLMRouter(config=config).providers if p.name == "vertex_ai"][0]

    assert vertex.temperature == 0.9
    assert vertex.max_tokens == 1500


def test_real_config_yaml_keeps_vertex_inert_until_configured():
    """
    El repositorio no debe traer un proyecto escrito: se declara al desplegar.
    Así, quien clone el repo sigue saliendo por OpenRouter sin sorpresas.
    """
    import yaml
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    vertex = [p for p in LLMRouter(config=config).providers if p.name == "vertex_ai"][0]
    assert not vertex.is_available()


# --- Orden de la cadena con Vertex activa ---

def test_vertex_takes_precedence_over_openrouter():
    """
    Con proyecto declarado, el tráfico sale por Vertex: es lo que hace que el
    gasto se cargue al crédito de Google Cloud y no a OpenRouter.
    """
    config = {"vertex_ai": {"project_id": "yuki-diva"}}
    nombres = [p.name for p in LLMRouter(config=config).providers]
    assert nombres.index("vertex_ai") < nombres.index("openrouter")


def test_openrouter_still_rescues_when_vertex_fails():
    """Cuando se agote el crédito, Yuki no puede quedarse muda."""
    vertex = ProveedorFalso("vertex_ai", True, None)   # disponible pero falla
    openrouter = ProveedorFalso("openrouter", True, "desde el agregador")
    router = LLMRouter(providers=[vertex, openrouter, LocalVoiceProvider()])

    resp = router.generate("sistema", "hola")

    assert vertex.llamado
    assert resp.provider == "openrouter"


# --- Integración real de la ruta de Vertex ---

class CredencialesFalsas:
    """Sustituye a las credenciales de Google Cloud en las pruebas."""

    def __init__(self, token="ya29.token-de-prueba", valid=True):
        self.token = token
        self.valid = valid
        self.refrescada = False

    def refresh(self, request):
        self.refrescada = True
        self.valid = True
        self.token = "ya29.token-renovado"


def test_vertex_emits_a_correct_request():
    """
    Comprueba que la petición sale bien formada contra el endpoint compatible
    con OpenAI de Vertex: la ruta con `/endpoints/openapi/chat/completions`, el
    token OAuth como portador (no una clave de API) y el modelo con publisher.
    """
    pytest.importorskip("openai", reason="El SDK openai no está instalado")

    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    recibido = {}

    class FalsoVertex(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            recibido.update(json.loads(self.rfile.read(n)))
            recibido["_ruta"] = self.path
            recibido["_auth"] = self.headers.get("Authorization")
            body = json.dumps({
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "La nieve cae despacio sobre el taller."},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 312, "completion_tokens": 48, "total_tokens": 360},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), FalsoVertex)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    try:
        proveedor = VertexProvider(
            project_id="yuki-diva",
            location="europe-southwest1",
            primary_model="gemini-3.7-flash",
            temperature=0.72,
            max_tokens=1024,
            credentials=CredencialesFalsas(),
            base_url=(f"http://127.0.0.1:{servidor.server_address[1]}"
                      "/v1/projects/yuki-diva/locations/europe-southwest1/endpoints/openapi"),
        )
        resp = proveedor.generate("Eres Yuki.", "Háblame de la nieve")
    finally:
        servidor.shutdown()
        servidor.server_close()

    assert recibido["_ruta"] == (
        "/v1/projects/yuki-diva/locations/europe-southwest1/endpoints/openapi/chat/completions"
    )
    assert recibido["_auth"] == "Bearer ya29.token-de-prueba"   # OAuth, no clave de API
    assert recibido["model"] == "google/gemini-3.7-flash"       # publisher añadido
    assert recibido["temperature"] == 0.72
    assert recibido["max_tokens"] == 1024
    assert [m["role"] for m in recibido["messages"]] == ["system", "user"]

    assert resp is not None
    assert resp.provider == "vertex_ai"
    assert resp.simulated is False
    assert resp.text == "La nieve cae despacio sobre el taller."
    # El consumo se propaga: es lo que permite vigilar el crédito.
    assert resp.input_tokens == 312
    assert resp.output_tokens == 48


@pytest.fixture
def transporte_de_auth_simulado(monkeypatch):
    """
    Sustituye `google.auth.transport.requests` por un doble.

    La renovación real arrastra `cryptography`, que no está garantizado en
    todos los entornos. Este stub deja el test comprobando la lógica que
    importa —que se renueve, y sólo cuando hace falta— sin depender de la
    pila de TLS instalada.
    """
    import types

    stub = types.ModuleType("google.auth.transport.requests")
    stub.Request = lambda *a, **k: object()
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", stub)
    return stub


def test_vertex_refreshes_an_expired_token(transporte_de_auth_simulado):
    """
    El daemon vive días y los tokens de Google caducan en torno a una hora:
    sin renovación, Yuki se quedaría sin voz a mitad de la primera noche.
    """
    credenciales = CredencialesFalsas(valid=False)
    proveedor = VertexProvider(project_id="yuki-diva", credentials=credenciales)

    assert proveedor._access_token() == "ya29.token-renovado"
    assert credenciales.refrescada


def test_vertex_does_not_refresh_a_valid_token():
    credenciales = CredencialesFalsas(valid=True)
    proveedor = VertexProvider(project_id="yuki-diva", credentials=credenciales)

    assert proveedor._access_token() == "ya29.token-de-prueba"
    assert not credenciales.refrescada


def test_vertex_returns_none_when_credentials_fail(monkeypatch):
    """Sin credenciales no se aborta: la cadena debe poder seguir hacia OpenRouter."""
    proveedor = VertexProvider(project_id="yuki-diva")
    monkeypatch.setattr(proveedor, "_access_token", lambda: None)
    assert proveedor.generate("sistema", "hola") is None


class CredencialesQueEstallan:
    """
    Doble de unas credenciales sobre una pila nativa rota.

    `cryptography` se compila con pyo3, y cuando su binding falla lanza
    `PanicException`, que hereda de `BaseException` y por tanto atraviesa un
    `except Exception`. Se reproduce aquí con `BaseException` a secas.
    """

    valid = False

    @property
    def token(self):
        raise BaseException("Python API call failed")

    def refresh(self, request):
        raise BaseException("Python API call failed")


def test_vertex_survives_a_broken_native_auth_stack(transporte_de_auth_simulado):
    """
    Un entorno con la pila de auth rota no puede tumbar a Yuki: el daemon
    corre 24/7 y debe poder seguir hacia la pasarela siguiente.
    """
    proveedor = VertexProvider(project_id="yuki-diva", credentials=CredencialesQueEstallan())

    assert proveedor._access_token() is None
    assert proveedor.generate("sistema", "hola") is None


def test_broken_vertex_does_not_leave_yuki_mute(transporte_de_auth_simulado):
    """La cadena completa sigue respondiendo aunque Vertex esté inservible."""
    router = LLMRouter(providers=[
        VertexProvider(project_id="yuki-diva", credentials=CredencialesQueEstallan()),
        LocalVoiceProvider(),
    ])

    resp = router.generate("sistema", "hola")

    assert resp.provider == "voz_local"
    assert resp.text


@pytest.mark.parametrize("interrupcion", [KeyboardInterrupt, SystemExit])
def test_vertex_does_not_swallow_interrupts(interrupcion, transporte_de_auth_simulado):
    """
    Blindar contra BaseException no puede llegar a tragarse un Ctrl+C: haría
    imposible parar el daemon.
    """
    class CredencialesInterrumpidas:
        valid = False

        def refresh(self, request):
            raise interrupcion()

    proveedor = VertexProvider(project_id="yuki-diva", credentials=CredencialesInterrumpidas())

    with pytest.raises(interrupcion):
        proveedor._access_token()
