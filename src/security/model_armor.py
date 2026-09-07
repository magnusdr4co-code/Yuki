"""Cliente pequeño y tolerante para Model Armor.

Model Armor no devuelve una versión transformada del texto cuando la plantilla
solo inspecciona: devuelve el resultado de los filtros. Por eso este módulo
mantiene el texto original si pasa y corta el flujo si hay una coincidencia.
La política de disponibilidad es configurable: por defecto un fallo de red o
de credenciales no tumba a Yuki, pero nunca se ignora una coincidencia real.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import quote

logger = logging.getLogger("Yuki.ModelArmor")

DEFAULT_LOCATION = "us-central1"
DEFAULT_TEMPLATE_ID = "yuki-hermes-runtime-v1"
DEFAULT_ENDPOINT = "https://modelarmor.us-central1.rep.googleapis.com"
MATCH_FOUND = "MATCH_FOUND"
SUCCESS = "SUCCESS"


@dataclass(frozen=True)
class SanitizationDecision:
    """Resultado seguro para que el arnés decida si continúa."""

    allowed: bool
    text: str
    reason: str = ""
    matched: bool = False
    invocation_result: str = ""


class ModelArmorClient:
    """Sanitiza prompts y respuestas usando una plantilla de Model Armor."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str = DEFAULT_LOCATION,
        template_id: str = DEFAULT_TEMPLATE_ID,
        enabled: bool = True,
        fail_closed: bool = False,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 10.0,
        session: Any = None,
    ) -> None:
        self.project_id = (project_id or "").strip()
        self.location = (location or DEFAULT_LOCATION).strip()
        self.template_id = (template_id or DEFAULT_TEMPLATE_ID).strip()
        self.enabled = bool(enabled and self.project_id and self.template_id)
        self.fail_closed = bool(fail_closed)
        self.endpoint = (endpoint or DEFAULT_ENDPOINT).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session = session
        self._auth_error: Optional[str] = None

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "ModelArmorClient":
        cfg = config or {}
        vertex_cfg = cfg.get("vertex_ai", {}) or {}
        armor_cfg = cfg.get("model_armor", {}) or {}

        def env_or_config(env_name: str, key: str, default: str = "") -> str:
            return os.getenv(env_name, armor_cfg.get(key, default))

        enabled_raw = env_or_config("MODEL_ARMOR_ENABLED", "enabled", "true")
        fail_closed_raw = env_or_config("MODEL_ARMOR_FAIL_CLOSED", "fail_closed", "false")
        # Un valor vacío en YAML significa "hereda del entorno"; no debe
        # ocultar VERTEX_PROJECT_ID dentro de la VM.
        project_id = (
            os.getenv("MODEL_ARMOR_PROJECT_ID")
            or armor_cfg.get("project_id")
            or os.getenv("VERTEX_PROJECT_ID")
            or vertex_cfg.get("project_id", "")
        )
        location = env_or_config("MODEL_ARMOR_LOCATION", "location", DEFAULT_LOCATION)
        template_id = env_or_config(
            "MODEL_ARMOR_TEMPLATE_ID", "template_id", DEFAULT_TEMPLATE_ID
        )
        endpoint = env_or_config("MODEL_ARMOR_ENDPOINT", "endpoint", "")
        timeout_raw = env_or_config(
            "MODEL_ARMOR_TIMEOUT_SECONDS", "timeout_seconds", "10"
        )

        try:
            timeout = max(1.0, float(timeout_raw))
        except (TypeError, ValueError):
            timeout = 10.0

        return cls(
            project_id=project_id,
            location=location,
            template_id=template_id,
            enabled=_as_bool(enabled_raw, default=True),
            fail_closed=_as_bool(fail_closed_raw, default=False),
            endpoint=endpoint,
            timeout_seconds=timeout,
        )

    @property
    def template_name(self) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}/templates/"
            f"{self.template_id}"
        )

    def sanitize_user_prompt(self, text: str) -> SanitizationDecision:
        if not self.enabled:
            return SanitizationDecision(True, text)
        payload = {"userPromptData": {"text": text}}
        return self._sanitize("sanitizeUserPrompt", payload, text)

    def sanitize_model_response(
        self, text: str, *, user_prompt: str = ""
    ) -> SanitizationDecision:
        if not self.enabled:
            return SanitizationDecision(True, text)
        payload: Dict[str, Any] = {"modelResponseData": {"text": text}}
        if user_prompt:
            payload["userPrompt"] = user_prompt
        return self._sanitize("sanitizeModelResponse", payload, text)

    def _sanitize(
        self, operation: str, payload: Dict[str, Any], original_text: str
    ) -> SanitizationDecision:
        try:
            response = self._get_session().post(
                self._operation_url(operation),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            result = body.get("sanitizationResult") or {}
        except Exception as exc:  # network/auth/API failures are policy-controlled
            logger.warning(
                "Model Armor %s no disponible (%s); fail_closed=%s",
                operation,
                type(exc).__name__,
                self.fail_closed,
            )
            return self._failure_decision(original_text, f"{operation}:{type(exc).__name__}")

        invocation_result = str(result.get("invocationResult") or "")
        match_state = str(result.get("filterMatchState") or "")
        if match_state == MATCH_FOUND:
            logger.warning("Model Armor bloqueó una operación %s por coincidencia de filtros", operation)
            return SanitizationDecision(
                allowed=False,
                text="",
                reason="model_armor_match",
                matched=True,
                invocation_result=invocation_result,
            )

        if invocation_result and invocation_result != SUCCESS:
            logger.warning(
                "Model Armor %s terminó con invocation_result=%s; fail_closed=%s",
                operation,
                invocation_result,
                self.fail_closed,
            )
            return self._failure_decision(original_text, f"{operation}:{invocation_result}")

        return SanitizationDecision(
            allowed=True,
            text=original_text,
            reason="model_armor_clear",
            invocation_result=invocation_result,
        )

    def _failure_decision(self, original_text: str, reason: str) -> SanitizationDecision:
        if self.fail_closed:
            return SanitizationDecision(False, "", reason=reason)
        return SanitizationDecision(True, original_text, reason=reason)

    def _operation_url(self, operation: str) -> str:
        return (
            f"{self.endpoint}/v1/{quote(self.template_name, safe='/')}:{operation}"
        )

    def _get_session(self) -> Any:
        if self._session is not None:
            return self._session
        if self._auth_error:
            raise RuntimeError(self._auth_error)
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._session = AuthorizedSession(credentials)
            return self._session
        except Exception as exc:
            self._auth_error = type(exc).__name__
            raise


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default
