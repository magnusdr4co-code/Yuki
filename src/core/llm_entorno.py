"""
Lo que hay que saber antes de elegir pasarela: entorno, nombres y rutas.

Son las respuestas que no dependen de ningún proveedor —si una clave es de
verdad o un marcador, cómo se nombra un modelo en Vertex, qué permite la cuenta
de servicio de la instancia, qué temperatura pide cada tarea— y que por eso
necesitan tanto las pasarelas como el enrutador. Vivían en `llm_router.py`, que
llegó a 801 líneas con cuatro integraciones dentro; tenerlas aquí es lo que
permite partirlo sin un ciclo de importación.
"""

import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Yuki.LLMRouter")

logger = logging.getLogger("Yuki.LLMRouter")

PLACEHOLDER_MARKERS = ("your_", "_here", "changeme")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NOUS_PORTAL_BASE_URL = "https://api.nousportal.com/v1"

# Vertex expone un endpoint compatible con el protocolo de OpenAI, así que el
# SDK `openai` que ya está en requirements.txt sirve también para esta ruta.
VERTEX_ENDPOINT_TEMPLATE = (
    "https://{host}/v1/projects/{project_id}/locations/{location}/endpoints/openapi"
)
VERTEX_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
DEFAULT_VERTEX_LOCATION = "global"
VERTEX_GLOBAL_LOCATION = "global"
VERTEX_GLOBAL_HOST = "aiplatform.googleapis.com"
DEFAULT_VERTEX_PRIMARY_MODEL = "google/gemini-3.8-flash"
DEFAULT_VERTEX_FALLBACK_MODEL = "google/gemini-3.7-flash"

# Clave de AI Studio. No se usa para nada aquí: sólo se mira para poder avisar,
# porque tenerla puesta es la vía más fácil de facturar fuera del crédito.
AI_STUDIO_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def vertex_host(location: str) -> str:
    """
    Host de Vertex para una región.

    `global` es el caso especial y **no lleva prefijo**: el host es
    `aiplatform.googleapis.com` a secas. Componer `global-aiplatform.
    googleapis.com` devuelve un 404 de Google —el nombre resuelve por el
    comodín `*.googleapis.com`, pero ahí no hay API que responda—, y como
    `generate` traga el fallo y devuelve `None`, la cadena caía calladamente
    a OpenRouter: el crédito de Google Cloud no se consumía nunca. Es la
    misma regla que aplica el SDK `google-genai` en la ruta de medios.
    """
    normalized = (location or DEFAULT_VERTEX_LOCATION).strip() or DEFAULT_VERTEX_LOCATION
    if normalized == VERTEX_GLOBAL_LOCATION:
        return VERTEX_GLOBAL_HOST
    return f"{normalized}-aiplatform.googleapis.com"


# Servidor de metadatos de Google Cloud. Sólo responde dentro de una VM de
# Compute Engine (o de Cloud Run); fuera, la conexión falla y basta con
# ignorarlo.
GCE_METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default"
)
GCE_METADATA_TIMEOUT = 1.0
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def gce_service_account_scopes() -> Optional[List[str]]:
    """
    Ámbitos de acceso de la VM, leídos del servidor de metadatos.

    Existe por un fallo que no se ve desde el código y cuesta horas: dentro de
    una VM de Compute Engine, `google.auth.default(scopes=...)` **no manda**.
    Las credenciales salen del servidor de metadatos y el token lleva los
    ámbitos que se le fijaron a la máquina al crearla, no los que pide el
    programa. Una VM creada sin `--scopes` recibe los de por defecto, que **no
    incluyen `cloud-platform`**, y entonces Vertex responde 403 por ámbitos
    insuficientes aunque el rol de IAM sea el correcto.

    Devuelve `None` si no estamos en una VM (o el metadato no responde).
    """
    try:
        import urllib.request

        peticion = urllib.request.Request(
            f"{GCE_METADATA_URL}/scopes", headers={"Metadata-Flavor": "Google"}
        )
        with urllib.request.urlopen(peticion, timeout=GCE_METADATA_TIMEOUT) as respuesta:
            cuerpo = respuesta.read().decode("utf-8")
        return [linea.strip() for linea in cuerpo.splitlines() if linea.strip()]
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        # No estamos en una VM, o el metadato no contesta. No es un error:
        # este diagnóstico es opcional.
        return None


def gce_scopes_permiten_vertex(scopes: Optional[List[str]]) -> Optional[bool]:
    """
    Si los ámbitos de la VM bastan para llamar a Vertex.

    `None` cuando no hay VM que examinar y no se puede afirmar nada.
    """
    if scopes is None:
        return None
    return CLOUD_PLATFORM_SCOPE in scopes


def is_usable_key(value: Optional[str]) -> bool:
    """Descarta claves vacías y los marcadores de posición de `.env.example`."""
    if not value or not value.strip():
        return False
    lowered = value.strip().lower()
    return not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def ai_studio_key_in_use() -> Optional[str]:
    """
    Nombre de la variable de AI Studio que esté puesta, si la hay.

    El Gemini API de AI Studio se factura como producto propio («Gemini API»
    en el panel), no como Vertex AI, y queda fuera del crédito. Si aparece en
    el entorno, alguien está gastando por esa vía.
    """
    for var in AI_STUDIO_KEY_VARS:
        if is_usable_key(os.getenv(var)):
            return var
    return None


def normalize_model(model: str) -> str:
    """
    Quita el prefijo del agregador. `hermes_config.yaml` nombra los modelos
    como `openrouter/anthropic/claude-3.5-sonnet`, pero la API de OpenRouter
    espera `anthropic/claude-3.5-sonnet`.
    """
    if not model:
        return model
    prefix = "openrouter/"
    return model[len(prefix):] if model.startswith(prefix) else model


def normalize_vertex_model(model: str) -> str:
    """
    Deja el nombre como lo espera el endpoint OpenAI de Vertex.

    Vertex nombra los modelos de Google con el prefijo del publisher
    (`google/gemini-3.8-flash`). Se admite escribirlos con o sin él, y con el
    prefijo del agregador delante, para poder copiar valores de
    `hermes_config.yaml` sin retocarlos:

        vertex/gemini-3.8-flash        -> google/gemini-3.8-flash
        openrouter/google/gemini-2.0-flash -> google/gemini-2.0-flash
        gemini-3.8-flash               -> google/gemini-3.8-flash
    """
    if not model:
        return model

    normalized = model.strip()
    for prefix in ("vertex_ai/", "vertex/", "openrouter/"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    # Sin publisher, se asume Google: es el único que sirve Gemini.
    if "/" not in normalized:
        normalized = f"google/{normalized}"

    return normalized


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str = ""
    simulated: bool = False
    # Consumo declarado por el proveedor. Sirve para vigilar el gasto contra
    # un crédito acotado; queda a cero cuando la pasarela no lo informa.
    input_tokens: int = 0
    output_tokens: int = 0
    # `length`/`max_tokens` permite distinguir un corte del modelo de un
    # problema de transporte. Yuki no usa streaming en esta ruta.
    finish_reason: str = ""


@dataclass
class RouteOptions:
    """
    Ajustes de una tarea concreta, declarados en `provider_routing.routes`.

    Estaban en `config.yaml` desde el principio y no los leía nadie: toda
    petición salía con el modelo y la temperatura de `agent.model`, así que un
    resumen de feed costaba lo mismo que una síntesis dialéctica. Esto los
    aplica.

    `preferred_model` se nombra a través del agregador (`upstage/solar-pro4`),
    así que **sólo** se pasa a la pasarela agregadora declarada en
    `provider_routing.aggregator`. Vertex nombra sus modelos con el publisher de
    Google y rechazaría ese identificador; ahí se aplican únicamente temperatura
    y `max_tokens`, que sí son agnósticos.
    """

    name: str
    tier: str = ""
    preferred_model: str = ""
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None

    def model_for(self, provider_name: str, aggregator: str) -> str:
        if not self.preferred_model:
            return ""
        return self.preferred_model if provider_name == aggregator else ""


def build_routes(config: Optional[Dict[str, Any]]) -> Dict[str, RouteOptions]:
    """Lee `provider_routing.routes`; devuelve vacío si está deshabilitado."""
    routing = (config or {}).get("provider_routing", {}) or {}
    if not routing.get("enabled", False):
        return {}
    rutas: Dict[str, RouteOptions] = {}
    for nombre, datos in (routing.get("routes") or {}).items():
        if not isinstance(datos, dict):
            continue
        rutas[str(nombre)] = RouteOptions(
            name=str(nombre),
            tier=str(datos.get("tier", "") or ""),
            preferred_model=normalize_model(str(datos.get("preferred_model", "") or "")),
            max_tokens=datos.get("max_tokens"),
            temperature=datos.get("temperature"),
        )
    return rutas
