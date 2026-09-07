"""
Búsqueda de corrientes culturales y noticias.

El limitador L6: esto devolvía dos resultados fijos con títulos verosímiles,
URLs que no existen y `source: "Firecrawl Web Crawler"`. La reflexión nocturna
de las 03:00 los tomaba por corrientes del mundo y Yuki construía su pensamiento
—y a veces su publicación de la mañana— sobre tendencias inventadas. Un
marcador que se presenta como real es peor que no tener buscador.

Ahora hay dos caminos y ninguno miente:

  · Con `FIRECRAWL_API_KEY` utilizable, se llama a la API de Firecrawl de
    verdad. Los resultados llevan `simulated: False` y su URL real.
  · Sin clave, se devuelven *pistas de introspección* explícitamente marcadas
    `simulated: True`, sin URL y con `source: "sin buscador"`. Quien las use
    debe decir que no vienen del mundo; para eso está `describe_origin`.

Se usa `urllib` de la biblioteca estándar: la petición es una sola, y así el
módulo no depende de que un cliente HTTP esté instalado para poder importarse.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Yuki.WebSearch")

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_TIMEOUT = 20.0

# Mismos marcadores que el resto del proyecto: una clave de ejemplo no es clave.
PLACEHOLDER_MARKERS = ("your_", "_here", "changeme")


def is_usable_key(value: Optional[str]) -> bool:
    if not value or not value.strip():
        return False
    minuscula = value.strip().lower()
    return not any(marca in minuscula for marca in PLACEHOLDER_MARKERS)


def local_reflection_prompts(query: str) -> List[Dict[str, Any]]:
    """
    Sustituto honesto cuando no hay buscador.

    No son tendencias: son preguntas que Yuki puede hacerse sobre el tema. Van
    marcadas como simuladas y sin URL, para que nadie las cite como noticia.
    """
    return [
        {
            "title": f"Sin buscador: introspección sobre «{query}»",
            "snippet": ("No hay acceso a corrientes reales del mundo. Piensa desde tu propia "
                        "memoria y tu taller, y dilo si lo publicas."),
            "url": None,
            "source": "sin buscador",
            "simulated": True,
        }
    ]


class FirecrawlSearch:
    """Cliente mínimo de Firecrawl. Inerte y honesto mientras no haya clave."""

    def __init__(self, api_key: Optional[str] = None, max_results: int = 5,
                 scrape_mode: str = "markdown", timeout: float = FIRECRAWL_TIMEOUT,
                 base_url: str = FIRECRAWL_SEARCH_URL, opener: Any = None):
        self.api_key = api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY")
        self.max_results = max_results
        self.scrape_mode = scrape_mode
        self.timeout = timeout
        self.base_url = base_url
        # Inyectable en pruebas: nada de red en la suite.
        self._opener = opener

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None, **overrides: Any) -> "FirecrawlSearch":
        busqueda = (((config or {}).get("nous_portal", {}) or {})
                    .get("frontier_engines", {}) or {}).get("web_search", {}) or {}
        parametros: Dict[str, Any] = {
            "max_results": busqueda.get("max_results", 5),
            "scrape_mode": busqueda.get("scrape_mode", "markdown"),
        }
        parametros.update(overrides)
        return cls(**parametros)

    def is_available(self) -> bool:
        return is_usable_key(self.api_key)

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cuerpo = json.dumps(payload).encode("utf-8")
        peticion = urllib.request.Request(
            self.base_url, data=cuerpo, method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        abrir = self._opener or urllib.request.urlopen
        with abrir(peticion, timeout=self.timeout) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))

    def search(self, query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Resultados reales, o las pistas locales marcadas si no hay buscador.

        Un fallo de red no deja a Yuki sin reflexión nocturna: se registra el
        error concreto y se cae a las pistas locales, que van marcadas como
        simuladas, así que la degradación se ve en el resultado y no se disfraza.
        """
        if not self.is_available():
            logger.info("Firecrawl sin clave utilizable: se devuelven pistas locales marcadas.")
            return local_reflection_prompts(query)

        payload = {
            "query": query,
            "limit": limit or self.max_results,
            "scrapeOptions": {"formats": [self.scrape_mode]},
        }
        try:
            datos = self._post(payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
                json.JSONDecodeError, ValueError) as exc:
            logger.warning("Firecrawl no respondió (%s): se cae a pistas locales marcadas.",
                           type(exc).__name__)
            return local_reflection_prompts(query)

        return self._normalizar(datos, query)

    @staticmethod
    def _normalizar(datos: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
        """Aplana la respuesta y descarta lo que no traiga URL: sin URL no hay fuente."""
        crudos = datos.get("data")
        if isinstance(crudos, dict):
            crudos = crudos.get("web") or crudos.get("results") or []
        if not isinstance(crudos, list):
            crudos = []

        resultados = []
        for elemento in crudos:
            if not isinstance(elemento, dict):
                continue
            url = elemento.get("url")
            if not url:
                continue
            resultados.append({
                "title": elemento.get("title") or url,
                "snippet": (elemento.get("description") or elemento.get("markdown") or "")[:500],
                "url": url,
                "source": "firecrawl",
                "simulated": False,
            })
        if not resultados:
            logger.info("Firecrawl no devolvió resultados utilizables para '%s'.", query)
            return local_reflection_prompts(query)
        return resultados


def describe_origin(resultados: List[Dict[str, Any]]) -> str:
    """
    Una línea que dice de dónde salen los resultados.

    Va al prompt de la reflexión nocturna: es lo que impide que Yuki presente
    como corriente del mundo algo que no ha salido de ninguna parte.
    """
    if not resultados:
        return "No hay resultados de búsqueda."
    if all(r.get("simulated") for r in resultados):
        return ("Estas notas NO vienen de una búsqueda real: no hay buscador conectado. "
                "No las cites como noticias ni las atribuyas al mundo exterior.")
    fuentes = sorted({r.get("url", "") for r in resultados if r.get("url")})
    return f"Resultados reales de Firecrawl ({len(fuentes)} fuentes con URL verificable)."


class WebSearchTool:
    """Fachada estable para el agente; el motor puede cambiar debajo."""

    def __init__(self, portal_client: Any = None, engine: Optional[FirecrawlSearch] = None,
                 config: Optional[Dict[str, Any]] = None):
        self.portal = portal_client
        self.engine = engine or FirecrawlSearch.from_config(config)

    async def search_news_and_trends(self, topic: str) -> List[Dict[str, Any]]:
        """Corrientes reales si hay buscador; pistas marcadas si no lo hay."""
        return await asyncio.to_thread(self.engine.search, topic)

    def describe_origin(self, resultados: List[Dict[str, Any]]) -> str:
        return describe_origin(resultados)
