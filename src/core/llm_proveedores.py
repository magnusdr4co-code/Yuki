"""
Las pasarelas de lenguaje, una clase por integración.

Nous Portal, Vertex, OpenRouter y la voz local de Yuki. Cada una sabe decir si
está disponible y generar un turno; el orden en que se prueban no es cosa suya
sino de `llm_router`, y separarlas de él es lo que deja ver que la única regla
compartida es el contrato: disponible o no, y nunca una prosa simulada que no
se declare `simulated`.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .llm_entorno import (
    DEFAULT_VERTEX_FALLBACK_MODEL,
    DEFAULT_VERTEX_LOCATION,
    DEFAULT_VERTEX_PRIMARY_MODEL,
    LLMResponse,
    NOUS_PORTAL_BASE_URL,
    OPENROUTER_BASE_URL,
    RouteOptions,
    VERTEX_ENDPOINT_TEMPLATE,
    VERTEX_SCOPES,
    ai_studio_key_in_use,
    gce_scopes_permiten_vertex,
    gce_service_account_scopes,
    is_usable_key,
    normalize_model,
    normalize_vertex_model,
    vertex_host,
)

logger = logging.getLogger("Yuki.LLMRouter")

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


class LLMProvider(ABC):
    """Contrato mínimo de una pasarela de lenguaje."""

    name: str = "abstracto"

    @abstractmethod
    def is_available(self) -> bool:
        """Si esta pasarela puede atender una petición ahora mismo."""

    @abstractmethod
    def generate(self, system_prompt: str, user_message: str,
                 options: Optional[RouteOptions] = None) -> Optional[LLMResponse]:
        """Devuelve la respuesta, o None si falla y hay que caer a la siguiente."""

    def _tuning(self, options: Optional[RouteOptions], aggregator: str = "") -> tuple:
        """Temperatura, `max_tokens` y modelo preferente efectivos para esta llamada."""
        temperature = getattr(self, "temperature", 0.72)
        max_tokens = getattr(self, "max_tokens", 1024)
        preferido = ""
        if options is not None:
            if options.temperature is not None:
                temperature = options.temperature
            if options.max_tokens is not None:
                max_tokens = options.max_tokens
            preferido = options.model_for(self.name, aggregator)
        return temperature, max_tokens, preferido


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

    def generate(self, system_prompt: str, user_message: str,
                 options: Optional[RouteOptions] = None) -> Optional[LLMResponse]:
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

    def generate(self, system_prompt: str, user_message: str,
                 options: Optional[RouteOptions] = None) -> Optional[LLMResponse]:
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

        # Vertex nombra sus modelos con el publisher de Google, así que una ruta
        # no puede imponerle un identificador del agregador; sí su temperatura y
        # su techo de salida.
        temperature, max_tokens, _ = self._tuning(options)

        models = [m for m in (self.primary_model, self.fallback_model) if m]
        ultimo_error = "sin modelos declarados"
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
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

    def generate(self, system_prompt: str, user_message: str,
                 options: Optional[RouteOptions] = None) -> Optional[LLMResponse]:
        if not self.is_available():
            return None

        try:
            client = self._client()
        except ImportError:
            logger.error("El paquete 'openai' no está instalado; no se puede usar OpenRouter.")
            return None

        temperature, max_tokens, preferido = self._tuning(options, aggregator=self.name)

        # El modelo de la ruta va primero; los de `agent.model` quedan detrás
        # como respaldo, para que una ruta mal escrita degrade en vez de mudar.
        models = [m for m in (preferido, self.primary_model, self.fallback_model) if m]
        models = list(dict.fromkeys(models))
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
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



class LocalVoiceProvider(LLMProvider):
    """Siempre disponible: garantiza que Yuki nunca se quede sin voz."""

    name = "voz_local"

    def is_available(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_message: str,
                 options: Optional[RouteOptions] = None) -> Optional[LLMResponse]:
        return LLMResponse(
            text=local_voice_response(user_message),
            provider=self.name,
            simulated=True
        )
