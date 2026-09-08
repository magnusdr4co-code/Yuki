"""
Pruebas del armazón compartido por los guiones de operación.

Cuatro guiones repetían la misma paleta, la misma fila con marca y detalle, el
mismo sobre de `--json` y el mismo código de salida. Cuatro copias no son cuatro
veces más trabajo: son cuatro sitios donde la próxima corrección se aplica en
tres.

Lo que se protege aquí es el contrato del que dependen los cinco guiones y la
integración continua: **cero si todo pasa, distinto de cero si algo falla**, y
que una comprobación que revienta cuente como fallo con su nombre y no se lleve
por delante el informe entero — el día que algo va mal es cuando más falta hacen
las otras cinco.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts._consola import ejecutar, filtrar, fila, informar  # noqa: E402


def test_el_codigo_de_salida_es_el_contrato_con_la_ci(capsys):
    todo_bien = [{"prueba": "a", "ok": True, "detalle": ""}]
    algo_mal = [{"prueba": "a", "ok": True, "detalle": ""},
                {"prueba": "b", "ok": False, "detalle": "se rompió"}]

    assert informar(todo_bien) == 0
    assert informar(algo_mal) == 1


def test_una_comprobacion_que_revienta_es_un_fallo_con_nombre():
    """
    No una excepción que se lleva el informe entero.

    El día que algo va mal es justo cuando hacen falta las demás comprobaciones.
    """
    def explota():
        raise RuntimeError("el disco no está")

    resultados = ejecutar([("buena", lambda: (True, "bien")), ("rota", explota)])

    assert [r["ok"] for r in resultados] == [True, False]
    assert "RuntimeError" in resultados[1]["detalle"]
    assert "el disco no está" in resultados[1]["detalle"]


def test_el_json_lleva_el_veredicto_y_lo_que_se_le_añada(capsys):
    resultados = [{"prueba": "a", "ok": False, "detalle": "no"}]

    codigo = informar(resultados, como_json=True, extra={"copia": "/tmp/x.tar.gz"})
    datos = json.loads(capsys.readouterr().out)

    assert codigo == 1
    assert datos["ok"] is False
    assert datos["copia"] == "/tmp/x.tar.gz"
    assert datos["resultados"] == resultados


def test_pedir_una_comprobacion_que_no_existe_es_ruidoso():
    """
    Un nombre mal escrito no puede dar un informe vacío que parece aprobado.

    Es la diferencia entre «no falló nada» y «no se comprobó nada».
    """
    pruebas = [("memoria", None), ("bitacora", None)]

    elegidas, desconocidas = filtrar(pruebas, "memoria,bitacoraa")

    assert [n for n, _ in elegidas] == ["memoria"]
    assert desconocidas == ["bitacoraa"]


def test_la_fila_dice_el_porque_y_no_solo_la_marca():
    con_detalle = fila("memoria", True, "209 recuerdos")
    sin_detalle = fila("memoria", False)

    assert "✓" in con_detalle and "209 recuerdos" in con_detalle
    assert "✗" in sin_detalle


@pytest.mark.parametrize("resultados,esperado", [
    ([], 0),
    ([{"prueba": "x", "ok": True, "detalle": ""}], 0),
    ([{"prueba": "x", "ok": False, "detalle": ""}], 1),
])
def test_sin_comprobaciones_no_se_declara_nada_roto(resultados, esperado, capsys):
    """Un informe vacío devuelve 0: no ha fallado nada porque no se miró nada."""
    assert informar(resultados) == esperado
