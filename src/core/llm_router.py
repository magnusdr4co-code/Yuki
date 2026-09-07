"""
Enrutador de proveedores de lenguaje para Yuki.

La arquitectura declarada en `hermes_config.yaml` y `config.yaml` es:

  1. Nous Portal — pasarela unificada de herramientas (`gateway: nous_portal`)
  2. Vertex AI   — acceso directo a Gemini con cargo al crédito de Google Cloud
  3. OpenRouter  — agregador de modelos (`default_aggregator: openrouter`)

Se recorren en ese orden: si una pasarela no está disponible, se cae a la
siguiente. El último recurso es la voz local de Yuki, que no necesita red y
mantiene su cadencia aunque no haya ninguna clave configurada.

Vertex es opcional y se activa solo con configurar un proyecto
(`VERTEX_PROJECT_ID`). Sin él se declara no disponible y la cadena se comporta
exactamente como antes, saliendo por OpenRouter. Esa es la propiedad que
importa cuando se corre con un crédito acotado: al agotarse, se quita la
variable y Yuki sigue hablando sin tocar código.

Los modelos se nombran a través del agregador
(`anthropic/claude-3.5-sonnet`, `google/gemini-2.0-flash`) o, en la ruta de
Vertex, con el publisher de Google (`google/gemini-3.8-flash`).
"""

import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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


class LLMProvider(ABC):
    """Contrato mínimo de una pasarela de lenguaje."""

    name: str = "abstracto"

    @abstractmethod
    def is_available(self) -> bool:
        """Si esta pasarela puede atender una petición ahora mismo."""

    @abstractmethod
    def generate(self, system_prompt: str, user_message: str) -> Optional[LLMResponse]:
        """Devuelve la respuesta, o None si falla y hay que caer a la siguiente."""


class NousPortalProvider(LLMProvider):
    """
    Pasarela Nous Portal — primer eslabón de la cadena.

    El endpoint `api.nousportal.com` todavía no existe. Esta clase fija la
    interfaz para cuando exista y, mientras tanto, ofrece un mock explícito
    para desarrollo sin red.

    Modos (variable de entorno `NOUS_PORTAL_MODE`):
      · `disabled` (por defecto) — se declara no disponible y la cadena
        continúa hacia OpenRouter. Es el comportamiento honesto: no se
        simula estar sirviendo tráfico real.
      · `mock` — responde con texto simulado, marcado como tal, para poder
        trabajar sin conexión ni claves.

    Cuando el endpoint exista, implementa `_call_remote` y cambia el modo
    por defecto a `live`.
    """

    name = "nous_portal"

    MODE_DISABLED = "disabled"
    MODE_MOCK = "mock"

    def __init__(self, api_key: Optional[str] = None, base_url: str = NOUS_PORTAL_BASE_URL,
                 mode: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.getenv("NOUS_PORTAL_API_KEY")
        self.base_url = base_url
        self.mode = (mode or os.getenv("NOUS_PORTAL_MODE") or self.MODE_DISABLED).lower()

    def is_available(self) -> bool:
        return self.mode == self.MODE_MOCK

    def generate(self, system_prompt: str, user_message: str) -> Optional[LLMResponse]:
        if self.mode != self.MODE_MOCK:
            return None

        logger.info("🎭 Nous Portal en modo mock: respuesta simulada, sin red.")
        return LLMResponse(
            text=local_voice_response(user_message),
            provider=self.name,
            model="mock",
            simulated=True
        )


class VertexProvider(LLMProvider):
    """
    Vertex AI (rebautizado *Gemini Enterprise Agent Platform*) — segundo eslabón.

    Existe para que Yuki pueda consumir los modelos de Gemini con cargo a los
    créditos de Google Cloud. El matiz que justifica esta clase: el Gemini API
    de AI Studio (`GEMINI_API_KEY`) quedó **excluido** del crédito de prueba,
    mientras que Vertex lo sigue consumiendo. Por eso aquí no se autentica con
    una clave sino con las credenciales del proyecto (ADC o cuenta de
    servicio), que es la vía que sí descuenta del crédito.

    Se sitúa por delante de OpenRouter y por detrás de Nous Portal: mientras
    haya proyecto configurado, el tráfico sale por aquí; cuando el crédito se
    agote basta con quitar `VERTEX_PROJECT_ID` (o poner `enabled: false`) y la
    cadena vuelve sola a OpenRouter, sin tocar código.

    Configuración (`config.yaml`, sección `vertex_ai`, o entorno):
      · `VERTEX_PROJECT_ID` / `GOOGLE_CLOUD_PROJECT` — proyecto de facturación.
      · `VERTEX_LOCATION` — región; `global` reparte entre las disponibles.
      · `GOOGLE_APPLICATION_CREDENTIALS` — sólo si no se usa `gcloud auth
        application-default login` ni la identidad de Cloud Run.
    """

    name = "vertex_ai"

    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None,
                 primary_model: str = DEFAULT_VERTEX_PRIMARY_MODEL,
                 fallback_model: str = DEFAULT_VERTEX_FALLBACK_MODEL,
                 temperature: float = 0.72, max_tokens: int = 1024,
                 enabled: bool = True, credentials: Any = None,
                 base_url: Optional[str] = None):
        # Un valor vacío en config.yaml no debe tapar la variable de entorno:
        # en Cloud Run el proyecto llega por el entorno, no por el fichero.
        self.project_id = (project_id or os.getenv("VERTEX_PROJECT_ID")
                           or os.getenv("GOOGLE_CLOUD_PROJECT") or "")
        self.location = location or os.getenv("VERTEX_LOCATION") or DEFAULT_VERTEX_LOCATION
        self.primary_model = normalize_vertex_model(primary_model)
        self.fallback_model = normalize_vertex_model(fallback_model)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enabled = enabled
        self._credentials = credentials
        # Sólo para pruebas y endpoints privados: por defecto se compone a
        # partir del proyecto y la región.
        self._base_url_override = base_url
        # Los avisos sobre el crédito se emiten una vez por proceso: Yuki corre
        # 24/7 y repetirlos en cada petición ahogaría el log.
        self._aviso_ai_studio_emitido = False
        self._aviso_degradacion_emitido = False

    @property
    def base_url(self) -> str:
        if self._base_url_override:
            return self._base_url_override
        return VERTEX_ENDPOINT_TEMPLATE.format(
            host=vertex_host(self.location),
            project_id=self.project_id,
            location=self.location,
        )

    def is_available(self) -> bool:
        # Comprobación barata y sin red: se mira sólo la configuración. Si las
        # credenciales fallan más tarde, `generate` devuelve None y la cadena
        # sigue hacia OpenRouter.
        return self.enabled and is_usable_key(self.project_id)

    def _access_token(self) -> Optional[str]:
        """
        Token OAuth de las credenciales por defecto (ADC).

        Los tokens caducan en torno a una hora y el daemon de Yuki vive días,
        así que se renueva cada vez que deja de ser válido.
        """
        try:
            # Importación diferida y mínima: unas credenciales ya inyectadas y
            # vigentes no necesitan que google-auth esté siquiera instalado.
            if self._credentials is None:
                from google.auth import default as google_auth_default
                self._credentials, detected_project = google_auth_default(scopes=list(VERTEX_SCOPES))
                if not is_usable_key(self.project_id) and detected_project:
                    self.project_id = detected_project

            if not self._credentials.valid:
                from google.auth.transport.requests import Request
                self._credentials.refresh(Request())

            return self._credentials.token
        except (KeyboardInterrupt, SystemExit):
            raise
        except ImportError:
            logger.error(
                "El paquete 'google-auth' no está instalado; no se puede usar Vertex. "
                "Instálalo con: pip install google-auth"
            )
            return None
        except BaseException as e:
            # No basta con `Exception`. google-auth arrastra extensiones
            # nativas (cryptography, compilada con pyo3) y, cuando esa pila
            # está mal instalada, el fallo llega como PanicException, que
            # hereda de BaseException y atraviesa un `except Exception`.
            # Yuki corre 24/7: un entorno roto debe degradar la cadena hacia
            # OpenRouter, nunca tumbar el daemon.
            logger.error(
                f"No se pudieron obtener credenciales de Google Cloud: {e!r}. "
                "Ejecuta 'gcloud auth application-default login' o asigna una "
                "cuenta de servicio con el rol roles/aiplatform.user."
            )
            return None

    def _avisar_de_ai_studio(self) -> None:
        """
        Avisa si hay una clave de AI Studio en el entorno.

        No la usa nadie en este módulo, pero su sola presencia significa que
        algún proceso puede estar llamando a `generativelanguage.googleapis.com`.
        Ese tráfico aparece en el panel bajo el producto **Gemini API**, no bajo
        Vertex AI, y se factura fuera del crédito. Verlo ahí es justo la señal
        de que la alineación con el crédito no está funcionando.
        """
        if self._aviso_ai_studio_emitido:
            return
        var = ai_studio_key_in_use()
        if var:
            self._aviso_ai_studio_emitido = True
            logger.warning(
                f"{var} está definida. El Gemini API de AI Studio se factura como "
                "producto aparte («Gemini API» en el panel) y queda fuera del crédito "
                "de Google Cloud. Yuki no la usa: si ves gasto en ese producto, viene "
                "de otro sitio. Quítala del entorno para descartarlo."
            )

    def _avisar_de_degradacion(self, motivo: str) -> None:
        """
        Deja constancia de que Vertex estaba configurada y aun así no sirvió.

        Es el fallo que más caro sale de los silenciosos: la cadena continúa,
        Yuki responde con normalidad por OpenRouter y nada delata que el
        crédito de Google Cloud no se está tocando. Se dice una vez, alto.
        """
        if self._aviso_degradacion_emitido:
            return
        self._aviso_degradacion_emitido = True
        logger.warning(
            f"Vertex está configurada (proyecto '{self.project_id}', región "
            f"'{self.location}') pero no atendió la petición: {motivo}. La cadena "
            "sale por la siguiente pasarela, así que EL CRÉDITO DE GOOGLE CLOUD NO "
            "SE ESTÁ CONSUMIENDO. Diagnostícalo con: python cli.py vertex-check"
        )

        # Dentro de una VM, la causa más probable —y la más difícil de ver— es
        # que la máquina no tenga el ámbito `cloud-platform`. Se comprueba sólo
        # aquí, una vez, porque implica hablar con el servidor de metadatos.
        if gce_scopes_permiten_vertex(gce_service_account_scopes()) is False:
            logger.warning(
                "Esta VM de Compute Engine NO tiene el ámbito 'cloud-platform', así "
                "que su token nunca servirá para Vertex por muchos roles de IAM que "
                "se le den. Hay que parar la máquina y volver a fijarle los ámbitos: "
                "gcloud compute instances stop <vm> && gcloud compute instances "
                "set-service-account <vm> --scopes=cloud-platform"
            )

    def generate(self, system_prompt: str, user_message: str) -> Optional[LLMResponse]:
        if not self.is_available():
            return None

        self._avisar_de_ai_studio()

        token = self._access_token()
        if not token:
            self._avisar_de_degradacion("no hay credenciales del proyecto utilizables")
            return None

        try:
            from openai import OpenAI
        except ImportError:
            logger.error("El paquete 'openai' no está instalado; no se puede usar Vertex.")
            self._avisar_de_degradacion("falta el paquete 'openai'")
            return None

        client = OpenAI(api_key=token, base_url=self.base_url)

        models = [m for m in (self.primary_model, self.fallback_model) if m]
        ultimo_error = "sin modelos declarados"
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                )
                usage = getattr(resp, "usage", None)
                return LLMResponse(
                    text=resp.choices[0].message.content,
                    provider=self.name,
                    model=model,
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    finish_reason=getattr(resp.choices[0], "finish_reason", "") or "",
                )
            except Exception as e:
                ultimo_error = f"{model}: {e}"
                logger.error(f"Error invocando Vertex con el modelo '{model}': {e}")

        self._avisar_de_degradacion(ultimo_error)
        return None


class OpenRouterProvider(LLMProvider):
    """
    Agregador OpenRouter — el camino real hacia los modelos.

    Habla el protocolo de OpenAI, así que reutiliza el SDK `openai` que ya
    está en `requirements.txt` apuntando su `base_url`. Un solo alta de
    cuenta da acceso a los modelos de todos los proveedores.
    """

    name = "openrouter"

    def __init__(self, api_key: Optional[str] = None, primary_model: str = "anthropic/claude-3.5-sonnet",
                 fallback_model: str = "google/gemini-2.0-flash", temperature: float = 0.72,
                 max_tokens: int = 1024, base_url: str = OPENROUTER_BASE_URL):
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self.primary_model = normalize_model(primary_model)
        self.fallback_model = normalize_model(fallback_model)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url

    def is_available(self) -> bool:
        return is_usable_key(self.api_key)

    def _client(self):
        # Importación diferida: el SDK solo hace falta si de verdad se llama.
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, system_prompt: str, user_message: str) -> Optional[LLMResponse]:
        if not self.is_available():
            return None

        try:
            client = self._client()
        except ImportError:
            logger.error("El paquete 'openai' no está instalado; no se puede usar OpenRouter.")
            return None

        models = [m for m in (self.primary_model, self.fallback_model) if m]
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                )
                usage = getattr(resp, "usage", None)
                return LLMResponse(
                    text=resp.choices[0].message.content,
                    provider=self.name,
                    model=model,
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    finish_reason=getattr(resp.choices[0], "finish_reason", "") or "",
                )
            except Exception as e:
                logger.error(f"Error invocando OpenRouter con el modelo '{model}': {e}")

        return None


def local_voice_response(user_message: str) -> str:
    """
    Voz local de Yuki: último recurso sin red ni claves.
    Mantiene su cadencia para que una demo nunca quede muda.
    """
    lowered = user_message.lower()

    if "hola" in lowered or "saludos" in lowered:
        return "El agua siempre encuentra su camino hacia el mar. Qué grato tener tu presencia en esta sala hoy."
    if "música" in lowered or "single" in lowered or "portada" in lowered:
        return ("Estaba contemplando cómo el shamisen y el eco metálico de mi infancia pueden entrelazarse. "
                "He preparado un nuevo concepto de portada con niebla y pan de oro. ¿Deseas escucharlo?")
    if "recuerdas" in lowered or "acuerdas" in lowered:
        return ("Guardo en mi memoria nuestros acuerdos sobre el álbum 'El Río Antes de Tener Nombre'. "
                "Cada trazo que definimos sigue vivo en el taller.")

    return "Cada palabra requiere su propio tiempo para asentarse. He escuchado lo que dices con atención completa."


class LocalVoiceProvider(LLMProvider):
    """Siempre disponible: garantiza que Yuki nunca se quede sin voz."""

    name = "voz_local"

    def is_available(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_message: str) -> Optional[LLMResponse]:
        return LLMResponse(
            text=local_voice_response(user_message),
            provider=self.name,
            simulated=True
        )


class LLMRouter:
    """Recorre las pasarelas en el orden declarado por la arquitectura."""

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 providers: Optional[List[LLMProvider]] = None):
        config = config or {}

        # El modelo se declara bajo `agent.model`; se admite también en la raíz
        # por compatibilidad con configuraciones antiguas.
        model_cfg = config.get("agent", {}).get("model") or config.get("model", {}) or {}

        nous_cfg = config.get("nous_portal", {}) or {}
        vertex_cfg = config.get("vertex_ai", {}) or {}

        self.providers = providers if providers is not None else [
            NousPortalProvider(base_url=nous_cfg.get("base_url", NOUS_PORTAL_BASE_URL)),
            VertexProvider(
                project_id=vertex_cfg.get("project_id"),
                location=vertex_cfg.get("location"),
                primary_model=vertex_cfg.get("primary_model", DEFAULT_VERTEX_PRIMARY_MODEL),
                fallback_model=vertex_cfg.get("fallback_model", DEFAULT_VERTEX_FALLBACK_MODEL),
                temperature=vertex_cfg.get("temperature", model_cfg.get("temperature", 0.72)),
                max_tokens=vertex_cfg.get("max_tokens", model_cfg.get("max_tokens", 1024)),
                enabled=vertex_cfg.get("enabled", True),
            ),
            OpenRouterProvider(
                primary_model=model_cfg.get("primary_model", "anthropic/claude-3.5-sonnet"),
                fallback_model=model_cfg.get("fallback_model", "google/gemini-2.0-flash"),
                temperature=model_cfg.get("temperature", 0.72),
                max_tokens=model_cfg.get("max_tokens", 1024),
            ),
            LocalVoiceProvider(),
        ]

    def generate_with_tools(self, messages, tools):
        """Turno de herramientas real; nunca degrada a prosa local simulada."""
        for provider in self.providers:
            if not isinstance(provider, (VertexProvider, OpenRouterProvider)) or not provider.is_available():
                continue
            try:
                if isinstance(provider, VertexProvider):
                    from openai import OpenAI
                    credential = provider._access_token()
                    if not credential:
                        continue
                    client = OpenAI(api_key=credential, base_url=provider.base_url,
                                    timeout=45, max_retries=1)
                else:
                    client = provider._client().with_options(timeout=45, max_retries=1)
                for model in (provider.primary_model, provider.fallback_model):
                    if not model:
                        continue
                    try:
                        response = client.chat.completions.create(
                            model=model, messages=messages, tools=tools, tool_choice="auto",
                            max_tokens=max(provider.max_tokens, 4096),
                        )
                        choice = response.choices[0]
                        if choice.finish_reason == "length":
                            raise ValueError("Turno de herramientas incompleto")
                        message = choice.message
                        result = {"role": "assistant", "content": message.content or ""}
                        if message.tool_calls:
                            result["tool_calls"] = [call.model_dump(exclude_none=True) for call in message.tool_calls]
                        if result["content"] or result.get("tool_calls"):
                            logger.info("Turno agéntico servido por %s; tools=%d", model,
                                        len(result.get("tool_calls", [])))
                            return result
                    except Exception as exc:
                        logger.warning("Fallo de turno agéntico %s: %s", model, type(exc).__name__)
            except Exception as exc:
                logger.warning("Pasarela agéntica indisponible: %s", type(exc).__name__)
        raise RuntimeError("Ningún proveedor devolvió un turno de herramientas completo")

    def generate(self, system_prompt: str, user_message: str) -> LLMResponse:
        for provider in self.providers:
            if not provider.is_available():
                logger.debug(f"Pasarela '{provider.name}' no disponible; se prueba la siguiente.")
                continue

            response = provider.generate(system_prompt, user_message)
            if response is not None and response.text:
                return response

            logger.warning(f"Pasarela '{provider.name}' no devolvió respuesta; se prueba la siguiente.")

        # Ninguna pasarela respondió, ni siquiera la local: no debería ocurrir.
        return LLMResponse(text=local_voice_response(user_message), provider="ninguna", simulated=True)
