"""
Pruebas del fichero de alertas.

Una alerta rota no falla: **calla**. Si alguien renombra una métrica, la regla
que la vigilaba se queda esperando para siempre una serie que ya no existe, y
nadie lo nota hasta el incidente que debía haber avisado. Eso es peor que no
tener la alerta, porque además da tranquilidad.

Así que aquí se comprueba lo que un fichero de reglas no puede comprobar solo:
que sea YAML válido, que cada regla diga qué hacer cuando suene, y sobre todo
que **cada métrica que nombra exista de verdad** en lo que la sonda expone.
"""

import os
import re
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RUTA = os.path.join(os.path.dirname(__file__), "..", "deploy", "alertas-prometheus.yml")
NOMBRE_DE_METRICA = re.compile(r"\byuki_[a-z0-9_]+")


@pytest.fixture(scope="module")
def reglas():
    with open(RUTA, "r", encoding="utf-8") as fichero:
        datos = yaml.safe_load(fichero)
    return [regla for grupo in datos["groups"] for regla in grupo["rules"]]


@pytest.fixture(scope="module")
def familias_expuestas():
    from src.web.server import SalonHTTPHandler

    salida = SalonHTTPHandler._metricas(SalonHTTPHandler.__new__(SalonHTTPHandler))
    return {linea.split()[2] for linea in salida.splitlines() if linea.startswith("# HELP")}


def test_el_fichero_es_yaml_valido_y_tiene_reglas(reglas):
    assert len(reglas) >= 12


def test_cada_alerta_dice_que_hacer_cuando_suene(reglas):
    """
    Una alerta sin acción despierta a alguien que no sabe qué mirar.

    A las tres de la mañana, la diferencia entre un incidente de diez minutos y
    uno de dos horas es que el aviso diga por dónde empezar.
    """
    for regla in reglas:
        anotaciones = regla.get("annotations", {})
        assert regla.get("alert"), regla
        assert regla.get("expr"), regla["alert"]
        assert regla.get("labels", {}).get("severity"), regla["alert"]
        assert anotaciones.get("resumen"), regla["alert"]
        assert anotaciones.get("accion"), regla["alert"]


def test_ninguna_alerta_vigila_una_metrica_que_no_existe(reglas, familias_expuestas):
    """
    La prueba que justifica el fichero entero.

    Renombrar una métrica y olvidar la regla que la usaba deja una alerta muda
    para siempre. Aquí eso rompe la rama en lugar de romper una guardia.
    """
    huerfanas = {}
    for regla in reglas:
        nombradas = set(NOMBRE_DE_METRICA.findall(regla["expr"]))
        faltan = nombradas - familias_expuestas
        if faltan:
            huerfanas[regla["alert"]] = sorted(faltan)

    assert not huerfanas, (
        "estas alertas vigilan métricas que la sonda no expone: " + repr(huerfanas))


def test_las_alertas_criticas_no_esperan(reglas):
    """
    Lo crítico suena ya.

    Una manipulación de la bitácora con quince minutos de espera es quince
    minutos para terminar de borrar el rastro.
    """
    criticas = [r for r in reglas if r["labels"]["severity"] == "critica"]
    assert criticas, "algo tiene que ser crítico"
    for regla in criticas:
        assert regla.get("for", "0s") in ("0s", "0m", None), regla["alert"]


def test_los_signos_vitales_estan_vigilados(reglas):
    """Catatonia y ausencia son los dos fallos que `/health` no puede ver."""
    nombres = {r["alert"] for r in reglas}

    assert {"YukiCatatonica", "YukiAusente"} <= nombres
    catatonia = next(r for r in reglas if r["alert"] == "YukiCatatonica")
    assert catatonia["labels"]["severity"] == "alta"
    # Una hora de espera: por debajo de eso, cualquier silencio normal la dispara.
    assert catatonia["for"] == "1h"
