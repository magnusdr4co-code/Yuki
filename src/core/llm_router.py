"""
Enrutador de proveedores de lenguaje para Yuki.

La arquitectura declarada en `hermes_config.yaml` y `config.yaml` es:

  1. Nous Portal — pasarela unificada de herramientas (`gateway: nous_portal`)
  2. OpenRouter  — agregador de modelos (`default_aggregator: openrouter`)

Se recorren en ese orden: si una pasarela no está disponible, se cae a la
siguiente. El último recurso es la voz local de Yuki, que no necesita red y
mantiene su cadencia aunque no haya ninguna clave configurada.

Los modelos se nombran siempre a través del agregador
(`anthropic/claude-3.5-sonnet`, `google/gemini-2.0-flash`), de modo que no
hace falta contratar cuenta directa con ningún proveedor.
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


def is_usable_key(value: Optional[str]) -> bool:
    """Descarta claves vacías y los marcadores de posición de `.env.example`."""
    if not value or not value.strip():
        return False
    lowered = value.strip().lower()
    return not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


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


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str = ""
    simulated: bool = False


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
                return LLMResponse(text=resp.choices[0].message.content, provider=self.name, model=model)
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

        self.providers = providers if providers is not None else [
            NousPortalProvider(base_url=nous_cfg.get("base_url", NOUS_PORTAL_BASE_URL)),
            OpenRouterProvider(
                primary_model=model_cfg.get("primary_model", "anthropic/claude-3.5-sonnet"),
                fallback_model=model_cfg.get("fallback_model", "google/gemini-2.0-flash"),
                temperature=model_cfg.get("temperature", 0.72),
                max_tokens=model_cfg.get("max_tokens", 1024),
            ),
            LocalVoiceProvider(),
        ]

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
