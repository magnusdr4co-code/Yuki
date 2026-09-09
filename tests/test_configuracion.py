"""
Pruebas de que `config.yaml` no promete diales que no giran.

Es la misma familia que el fallo de la espontaneidad: allí dos números se
contradecían y apagaban una facultad entera; aquí hay claves que un operador
ajusta esperando un efecto que no ocurre, porque nadie las lee. `half_life_days`
es el ejemplo perfecto —existe en el fichero, existe como parámetro en
`fts5_memory.py`, y el valor de uno no llega nunca al otro—.

No se borran: una clave que documenta una intención vale, y borrarla perdería el
registro de lo que se quiso. Se **marcan** en su propia línea diciendo que no se
leen y qué gobierna de verdad ese comportamiento. Lo que no puede pasar es que
nazca una clave muerta sin decirlo.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

MARCA = "no se lee"


def _hojas(rama, prefijo=""):
    """Cada clave hoja con su ruta completa. Las listas de objetos no cuentan."""
    if not isinstance(rama, dict):
        return
    for clave, valor in rama.items():
        ruta = f"{prefijo}.{clave}" if prefijo else clave
        if isinstance(valor, dict):
            yield from _hojas(valor, ruta)
        elif isinstance(valor, list) and valor and isinstance(valor[0], dict):
            continue
        else:
            yield ruta, clave


@pytest.fixture(scope="module")
def configuracion():
    with open(RAIZ / "config.yaml", encoding="utf-8") as fichero:
        return yaml.safe_load(fichero)


@pytest.fixture(scope="module")
def codigo():
    fuentes = [p.read_text(encoding="utf-8") for p in (RAIZ / "src").rglob("*.py")]
    fuentes.append((RAIZ / "cli.py").read_text(encoding="utf-8"))
    return "\n".join(fuentes)


@pytest.fixture(scope="module")
def lineas_marcadas():
    texto = (RAIZ / "config.yaml").read_text(encoding="utf-8")
    return {linea.split(":")[0].strip(): linea
            for linea in texto.splitlines() if MARCA in linea}


def test_toda_clave_o_se_lee_o_dice_que_no(configuracion, codigo, lineas_marcadas):
    """
    Un dial que no gira engaña a quien lo ajusta, y lo hace en silencio: no
    falla, simplemente no pasa nada, y el operador concluye que el número no
    servía de mucho.
    """
    mudas = []
    for ruta, clave in _hojas(configuracion):
        if re.search(rf'["\']{re.escape(clave)}["\']', codigo):
            continue
        if clave in lineas_marcadas:
            continue
        mudas.append(ruta)

    assert not mudas, (
        "estas claves no las lee nadie y no lo dicen; márcalas con "
        f"`# {MARCA}: <qué lo gobierna de verdad>` o impleméntalas: {mudas}")


def test_la_marca_explica_que_gobierna_de_verdad(lineas_marcadas):
    """
    «No se lee» a secas deja a quien lo encuentre igual de perdido.

    La marca tiene que decir dónde mirar: la variable de entorno que manda, el
    módulo que fija el valor, o que la funcionalidad no existe todavía.
    """
    assert lineas_marcadas, "debería haber claves marcadas"
    for clave, linea in lineas_marcadas.items():
        explicacion = linea.split(MARCA + ":", 1)
        assert len(explicacion) == 2, f"{clave}: la marca no explica nada"
        assert len(explicacion[1].strip()) > 10, f"{clave}: la explicación no dice nada"


def test_las_secciones_que_si_gobiernan_algo_siguen_vivas(configuracion, codigo):
    """
    El contrapeso: que la marca no se convierta en la salida fácil.

    Estas claves gobiernan comportamiento real y comprobado por otras pruebas.
    Si alguna acabara marcada como no leída, sería que se rompió algo.
    """
    vivas = ["agency.spontaneity", "agency.boredom_cap", "agency.spontaneous_threshold",
             "budget.enabled", "transparency.enabled", "persona.enabled",
             "memory.database_path", "pulse.max_edad_horas"]

    texto = (RAIZ / "config.yaml").read_text(encoding="utf-8")
    for ruta in vivas:
        hoja = ruta.split(".")[-1]
        for linea in texto.splitlines():
            if linea.strip().startswith(f"{hoja}:"):
                assert MARCA not in linea, f"{ruta} está marcada como muerta y no lo está"
