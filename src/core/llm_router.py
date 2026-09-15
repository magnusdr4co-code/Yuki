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

Aquí queda sólo el recorrido. Cada pasarela vive en `llm_proveedores.py` y lo
que se sabe del entorno y de los nombres de modelo, en `llm_entorno.py`; se
reexportan porque este módulo es el nombre por el que se piden desde siempre.
"""

import logging
from typing import Any, Dict, List, Optional

from .llm_entorno import (
    AI_STUDIO_KEY_VARS,
    CLOUD_PLATFORM_SCOPE,
    DEFAULT_VERTEX_FALLBACK_MODEL,
    DEFAULT_VERTEX_LOCATION,
    DEFAULT_VERTEX_PRIMARY_MODEL,
    LLMResponse,
    NOUS_PORTAL_BASE_URL,
    OPENROUTER_BASE_URL,
    PLACEHOLDER_MARKERS,
    RouteOptions,
    VERTEX_ENDPOINT_TEMPLATE,
    VERTEX_GLOBAL_HOST,
    VERTEX_GLOBAL_LOCATION,
    VERTEX_SCOPES,
    ai_studio_key_in_use,
    build_routes,
    gce_scopes_permiten_vertex,
    gce_service_account_scopes,
    is_usable_key,
    normalize_model,
    normalize_vertex_model,
    vertex_host,
)
from .llm_proveedores import (
    LLMProvider,
    LocalVoiceProvider,
    NousPortalProvider,
    OpenRouterProvider,
    VertexProvider,
    local_voice_response,
)

logger = logging.getLogger("Yuki.LLMRouter")

__all__ = [
    "LLMRouter",
    "LLMProvider",
    "LLMResponse",
    "RouteOptions",
    "NousPortalProvider",
    "VertexProvider",
    "OpenRouterProvider",
    "LocalVoiceProvider",
    "local_voice_response",
    "build_routes",
    "is_usable_key",
    "ai_studio_key_in_use",
    "normalize_model",
    "normalize_vertex_model",
    "vertex_host",
    "gce_service_account_scopes",
    "gce_scopes_permiten_vertex",
    "AI_STUDIO_KEY_VARS",
    "CLOUD_PLATFORM_SCOPE",
    "PLACEHOLDER_MARKERS",
    "OPENROUTER_BASE_URL",
    "NOUS_PORTAL_BASE_URL",
    "VERTEX_ENDPOINT_TEMPLATE",
    "VERTEX_SCOPES",
    "VERTEX_GLOBAL_HOST",
    "VERTEX_GLOBAL_LOCATION",
    "DEFAULT_VERTEX_LOCATION",
    "DEFAULT_VERTEX_PRIMARY_MODEL",
    "DEFAULT_VERTEX_FALLBACK_MODEL",
]


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

        # Enrutado por tarea. `aggregator` decide a qué pasarela se le puede
        # imponer el modelo de la ruta; el resto sólo recibe temperatura y techo.
        routing_cfg = config.get("provider_routing", {}) or {}
        self.aggregator = str(routing_cfg.get("aggregator", "openrouter") or "openrouter")
        self.routes = build_routes(config)
        self._rutas_desconocidas: set = set()

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

    def generate_with_tools(self, messages, tools, route: Optional[str] = None):
        """
        Turno de herramientas real; nunca degrada a prosa local simulada.

        Honra la ruta declarada, que era lo que faltaba de M5: el arnés del
        Productor salía siempre con `agent.model`, así que el enrutado por tarea
        se aplicaba a los crons y no al camino donde Yuki ejecuta de verdad.

        Con una diferencia deliberada respecto a `generate`: el `max_tokens` de
        la ruta **sube** el techo, nunca lo baja. Un turno de herramientas que se
        corta por longitud no da una respuesta más corta, da un
        `finish_reason == "length"` y se descarta entero.
        """
        options = self.resolve_route(route)
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
                modelos = [provider.primary_model, provider.fallback_model]
                # El modelo preferente se nombra a través del agregador; Vertex
                # rechazaría ese identificador, así que allí sólo se aplican los
                # ajustes agnósticos, igual que en `generate`.
                if (options is not None and options.preferred_model
                        and isinstance(provider, OpenRouterProvider)):
                    modelos.insert(0, options.preferred_model)
                techo = max(provider.max_tokens, 4096,
                            options.max_tokens if options is not None and options.max_tokens else 0)
                extra = ({"temperature": options.temperature}
                         if options is not None and options.temperature is not None else {})
                for model in modelos:
                    if not model:
                        continue
                    try:
                        response = client.chat.completions.create(
                            model=model, messages=messages, tools=tools, tool_choice="auto",
                            max_tokens=techo, **extra,
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

    def resolve_route(self, route: Optional[str]) -> Optional[RouteOptions]:
        """
        Ajustes declarados para una tarea, o `None` si no hay ruta aplicable.

        Una ruta que no existe en la configuración no es un error fatal: se
        avisa una vez y la petición sale con los valores de `agent.model`. Callar
        aquí sería el fallo caro —el enrutado parecería activo sin serlo—, y
        abortar dejaría muda a Yuki por una errata en un YAML.
        """
        if not route:
            return None
        opciones = self.routes.get(route)
        if opciones is None:
            if route not in self._rutas_desconocidas:
                self._rutas_desconocidas.add(route)
                estado = "deshabilitado" if not self.routes else "sin esa entrada"
                logger.warning(
                    "Ruta '%s' no declarada en provider_routing (%s); se usa la configuración "
                    "de agent.model.", route, estado,
                )
            return None
        return opciones

    def generate(self, system_prompt: str, user_message: str,
                 route: Optional[str] = None) -> LLMResponse:
        options = self.resolve_route(route)
        if options is not None:
            logger.info(
                "Ruta '%s' (tier %s): modelo preferente '%s', max_tokens=%s, temperatura=%s",
                options.name, options.tier or "sin declarar",
                options.preferred_model or "el de agent.model",
                options.max_tokens, options.temperature,
            )

        for provider in self.providers:
            if not provider.is_available():
                logger.debug(f"Pasarela '{provider.name}' no disponible; se prueba la siguiente.")
                continue

            response = provider.generate(system_prompt, user_message, options)
            if response is not None and response.text:
                return response

            logger.warning(f"Pasarela '{provider.name}' no devolvió respuesta; se prueba la siguiente.")

        # Ninguna pasarela respondió, ni siquiera la local: no debería ocurrir.
        return LLMResponse(text=local_voice_response(user_message), provider="ninguna", simulated=True)
