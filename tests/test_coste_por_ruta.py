"""
Saber si separar las tareas por modelo sirve de algo.

M5 de `docs/VIRTUALIZACION_Y_MEJORAS.md`. El enrutado ya mandaba un resumen de
feed a un modelo barato y una síntesis dialéctica a uno caro, pero el gasto de
texto se sumaba en un **único montón**: no había forma de comprobar si la
separación estaba ahorrando algo, ni de ver qué tarea se está comiendo el día.

Y dos rutas declaradas no las leía nadie: el arnés del Productor —el único sitio
donde Yuki ejecuta de verdad— salía siempre con `agent.model`, y
`music_composition` llevaba en `config.yaml` desde el principio sin un solo
lector. Un dial que no gira engaña a quien lo ajusta y no falla nunca.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.llm_router import LLMRouter, RouteOptions  # noqa: E402
from src.core.spend_budget import PREFIJO_RUTA, SpendLedger  # noqa: E402


@pytest.fixture()
def libro(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_SPEND_LEDGER_PATH", str(tmp_path / "gasto.json"))
    return SpendLedger()


def test_el_gasto_de_texto_se_desglosa_por_tarea(libro):
    libro.record_llm(1200, 400, route="feed_summary")
    libro.record_llm(9000, 3000, route="dialectic_synthesis")

    desglose = libro.por_ruta()

    assert desglose["feed_summary"]["entrada"] == 1200
    assert desglose["dialectic_synthesis"]["salida"] == 3000
    assert desglose["dialectic_synthesis"]["usd"] > desglose["feed_summary"]["usd"], \
        "si la cara no sale más cara que la barata, el enrutado no está sirviendo"


def test_el_total_sigue_siendo_el_total(libro):
    """El desglose se suma aparte: contarlo dos veces inflaría el coste del día."""
    libro.record_llm(1000, 500, route="feed_summary")

    esperado = 1000 / 1_000_000 * 0.75 + 500 / 1_000_000 * 3.75

    assert libro.today()["tokens_entrada"] == 1000
    assert round(libro.usd_today(), 6) == round(esperado, 6)


def test_sin_ruta_se_anota_igual_en_el_total(libro):
    """Una llamada sin ruta declarada no puede dejar de contarse."""
    libro.record_llm(800, 200)

    assert libro.today()["tokens_entrada"] == 800
    assert libro.por_ruta() == {}


def test_el_desglose_no_ensucia_la_linea_del_dm(libro):
    """`describe()` es una línea, no un informe: con una ruta por fila, ilegible."""
    libro.record_llm(1000, 500, route="feed_summary")

    resumen = libro.describe()

    assert "tokens_entrada" in resumen
    assert PREFIJO_RUTA not in resumen


def test_una_ruta_no_lleva_limite_propio(libro):
    """
    Un techo diario se pone al total. Acotar una tarea sola dejaría a Yuki sin
    poder resumir un feed mientras le sobra presupuesto para todo lo demás.
    """
    libro.record_llm(1000, 500, route="feed_summary")

    assert not any(unidad.startswith(PREFIJO_RUTA) for unidad in libro.limits)


def test_el_turno_de_herramientas_honra_su_ruta():
    """El arnés salía siempre con `agent.model`: el enrutado no llegaba ahí."""
    router = LLMRouter(providers=[], config={
        "provider_routing": {"enabled": True, "routes": {
            "producer_tools": {"tier": "creative_and_deep", "max_tokens": 6000,
                               "temperature": 0.5},
        }},
    })

    opciones = router.resolve_route("producer_tools")

    assert isinstance(opciones, RouteOptions)
    assert opciones.max_tokens == 6000


def test_una_ruta_sin_declarar_no_deja_muda_a_yuki():
    """Abortar por una errata en un YAML sería peor que salir con lo general."""
    router = LLMRouter(providers=[], config={"provider_routing": {"enabled": True, "routes": {}}})

    assert router.resolve_route("inventada") is None


def test_el_arnes_sale_por_una_ruta_declarada_de_verdad():
    """
    Los dobles del arnés comprueban `route == RUTA`, que es cierto por
    construcción y no dice nada: con `RUTA = None` seguirían pasando. Aquí se
    fija el nombre literal y que exista en la configuración.
    """
    from pathlib import Path

    import yaml

    from src.core.producer_harness import RUTA

    assert RUTA == "producer_tools"
    raiz = Path(__file__).resolve().parents[1]
    with open(raiz / "config.yaml", "r", encoding="utf-8") as fichero:
        config = yaml.safe_load(fichero) or {}
    declaradas = ((config.get("provider_routing", {}) or {}).get("routes", {}) or {})

    assert RUTA in declaradas, "el arnés pide una ruta que nadie declara"


def test_el_agente_anota_el_gasto_con_su_ruta(tmp_path, monkeypatch):
    """
    Camino del producto: de `_call_llm_inference` al libro. Sin esto, la ruta
    podía quedarse por el camino y el desglose salir siempre vacío en producción
    mientras las pruebas del libro pasaban.
    """
    from types import SimpleNamespace

    from src.core.agent import YukiAgent
    from src.core.llm_router import LLMResponse

    monkeypatch.setenv("YUKI_SPEND_LEDGER_PATH", str(tmp_path / "gasto.json"))
    agente = YukiAgent()
    agente.spend_ledger = SpendLedger()
    agente.llm_router = SimpleNamespace(generate=lambda sistema, mensaje, route=None: LLMResponse(
        text="dicho", provider="doble", input_tokens=700, output_tokens=300))

    agente._call_llm_inference("sistema", "mensaje", route="feed_summary")

    assert agente.spend_ledger.por_ruta()["feed_summary"]["entrada"] == 700


def test_toda_ruta_declarada_tiene_quien_la_lea():
    """
    El guardián de la regla 6 de CLAUDE.md, aplicado al enrutado: un dial que no
    gira engaña a quien lo ajusta y no falla nunca. `music_composition` llevaba
    declarada desde el principio sin un solo lector.
    """
    import subprocess
    from pathlib import Path

    import yaml

    raiz = Path(__file__).resolve().parents[1]
    with open(raiz / "config.yaml", "r", encoding="utf-8") as fichero:
        config = yaml.safe_load(fichero) or {}
    declaradas = ((config.get("provider_routing", {}) or {}).get("routes", {}) or {})

    sin_lector = []
    for nombre in declaradas:
        encontrado = subprocess.run(
            ["grep", "-rl", nombre, "src/", "scripts/"],
            cwd=raiz, capture_output=True, text=True, timeout=60).stdout
        if not encontrado.strip():
            sin_lector.append(nombre)

    assert not sin_lector, f"rutas declaradas que no lee nadie: {sin_lector}"
