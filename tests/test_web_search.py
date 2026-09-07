"""
Pruebas del buscador de corrientes.

El fallo que se corrige aquí no era técnico sino de honestidad: devolvía
titulares plausibles con URLs inventadas y la reflexión de las 03:00 los tomaba
por corrientes del mundo. Lo que se protege es que ningún resultado se presente
como real sin serlo, y que la ausencia de buscador se declare.
"""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.web_search import (  # noqa: E402
    FirecrawlSearch, WebSearchTool, describe_origin, local_reflection_prompts,
)


class RespuestaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _opener(payload, capturado=None):
    def abrir(peticion, timeout=None):
        if capturado is not None:
            capturado["url"] = peticion.full_url
            capturado["headers"] = dict(peticion.headers)
            capturado["body"] = json.loads(peticion.data.decode("utf-8"))
        return RespuestaFalsa(json.dumps(payload).encode("utf-8"))
    return abrir


def test_sin_clave_no_se_inventan_titulares(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    buscador = FirecrawlSearch()

    resultados = buscador.search("arte digital")

    assert not buscador.is_available()
    assert all(r["simulated"] for r in resultados)
    assert all(r["url"] is None for r in resultados), "sin URL real no se finge una fuente"
    assert all(r["source"] == "sin buscador" for r in resultados)


def test_clave_marcador_no_activa_el_buscador():
    assert not FirecrawlSearch(api_key="your_firecrawl_key_if_standalone_here").is_available()


def test_con_clave_se_llama_a_firecrawl_y_se_normaliza():
    capturado = {}
    payload = {"data": {"web": [
        {"title": "Koto y síntesis", "description": "Un ensayo", "url": "https://ejemplo.org/koto"},
        {"title": "Sin url", "description": "descartado"},
    ]}}
    buscador = FirecrawlSearch(api_key="fc-clave-real", max_results=3,
                               opener=_opener(payload, capturado))

    resultados = buscador.search("koto")

    assert capturado["body"] == {"query": "koto", "limit": 3,
                                 "scrapeOptions": {"formats": ["markdown"]}}
    assert capturado["headers"]["Authorization"] == "Bearer fc-clave-real"
    assert len(resultados) == 1, "un resultado sin URL no es una fuente"
    assert resultados[0] == {"title": "Koto y síntesis", "snippet": "Un ensayo",
                             "url": "https://ejemplo.org/koto", "source": "firecrawl",
                             "simulated": False}


def test_un_fallo_de_red_degrada_marcado_no_calla():
    def abrir_que_falla(peticion, timeout=None):
        raise OSError("conexión rechazada")

    buscador = FirecrawlSearch(api_key="fc-clave-real", opener=abrir_que_falla)

    resultados = buscador.search("niebla")

    assert resultados and all(r["simulated"] for r in resultados)


def test_respuesta_vacia_no_se_presenta_como_hallazgo():
    buscador = FirecrawlSearch(api_key="fc-clave-real", opener=_opener({"data": {"web": []}}))

    resultados = buscador.search("nada")

    assert all(r["simulated"] for r in resultados)


def test_describe_origin_distingue_mundo_de_introspeccion():
    simulados = local_reflection_prompts("x")
    reales = [{"title": "t", "snippet": "s", "url": "https://a.org", "simulated": False}]

    assert "NO vienen de una búsqueda real" in describe_origin(simulados)
    assert "Firecrawl" in describe_origin(reales)
    assert describe_origin([]) == "No hay resultados de búsqueda."


def test_from_config_lee_los_limites_declarados():
    buscador = FirecrawlSearch.from_config({
        "nous_portal": {"frontier_engines": {"web_search": {"max_results": 7, "scrape_mode": "html"}}}
    })

    assert buscador.max_results == 7 and buscador.scrape_mode == "html"


def test_la_fachada_del_agente_sigue_siendo_asincrona():
    import asyncio

    herramienta = WebSearchTool(engine=FirecrawlSearch(api_key=None))

    resultados = asyncio.run(herramienta.search_news_and_trends("tendencias"))

    assert all(r["simulated"] for r in resultados)
    assert "NO vienen" in herramienta.describe_origin(resultados)
