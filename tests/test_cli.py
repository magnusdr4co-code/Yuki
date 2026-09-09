"""
Pruebas de la superficie de la línea de órdenes.

Veinte comandos, mil doscientas líneas, y ni una prueba: `cli.py` sólo se
comprobaba ejecutándolo a mano. Un renombrado, un argumento que cambia de sitio
o una importación que se queda atrás no fallaban hasta que alguien lo escribía
en una terminal — normalmente el día que algo iba mal y había prisa.

Se prueban dos cosas y no más. Que **todos los comandos declarados existan y
acepten sus argumentos**, que es lo que rompe un refactor; y que los que sólo
leen —los que no gastan crédito, no salen a la red y no arrancan un servidor—
**se ejecuten de verdad y emitan JSON válido**. Los que conversan, sirven o
generan medios no se ejecutan aquí: una prueba que gaste crédito se deja de
ejecutar a la tercera semana.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

# Sólo lectura: ni red, ni proveedores, ni servidor, ni un céntimo.
INOFENSIVOS = ["spend", "albedrio", "pulso", "estado", "bitacora", "freno",
               "persona", "transparency", "virtualize"]


def _correr(*argumentos, entorno=None):
    completo = dict(os.environ)
    completo.update(entorno or {})
    return subprocess.run([sys.executable, "cli.py", *argumentos], cwd=RAIZ,
                          capture_output=True, text=True, timeout=180, env=completo)


@pytest.fixture(scope="module")
def declarados():
    ayuda = _correr("--help").stdout
    dentro = re.search(r"\{([a-z0-9,_-]+)\}", ayuda)
    assert dentro, f"no pude leer los subcomandos: {ayuda[:300]}"
    return dentro.group(1).split(",")


@pytest.fixture
def aislado(tmp_path):
    """La instancia real no se toca: ni su memoria ni lo que crea."""
    return {"DATABASE_PATH": str(tmp_path / "data" / "memoria.db"),
            "YUKI_OUTPUT_DIR": str(tmp_path / "output"),
            "YUKI_BLACKBOX_PATH": str(tmp_path / "data" / "bitacora.jsonl")}


def test_todos_los_comandos_declarados_aceptan_sus_argumentos(declarados):
    """
    Lo que rompe un refactor: un comando que deja de existir o de aceptar lo
    suyo. `--help` por subcomando lo comprueba sin ejecutar nada.
    """
    rotos = {}
    for comando in declarados:
        resultado = _correr(comando, "--help")
        if resultado.returncode != 0:
            rotos[comando] = resultado.stderr.strip()[-200:]

    assert not rotos, f"comandos que no responden a --help: {rotos}"


def test_hay_los_comandos_que_documenta_el_mapa(declarados):
    """Un aviso si alguno desaparece sin querer al reorganizar."""
    imprescindibles = {"chat", "web", "backup", "pulso", "estado", "freno",
                       "bitacora", "albedrio", "sueno", "spend", "virtualize",
                       "transparency", "persona"}

    assert imprescindibles <= set(declarados), imprescindibles - set(declarados)


@pytest.mark.parametrize("comando", INOFENSIVOS)
def test_los_comandos_de_lectura_se_ejecutan_y_emiten_json(comando, aislado):
    """
    Que respondan a `--help` no dice que funcionen: dice que el analizador está
    bien. Esto los ejecuta de verdad contra una instancia vacía y comprueba que
    lo que sale se puede leer con una máquina.
    """
    resultado = _correr(comando, "--json", entorno=aislado)

    assert resultado.returncode in (0, 1), (
        f"`{comando} --json` reventó:\n{resultado.stderr[-600:]}")
    assert "Traceback" not in resultado.stderr, resultado.stderr[-600:]

    salida = resultado.stdout.strip()
    assert salida, f"`{comando} --json` no emitió nada"
    json.loads(salida)


def test_un_comando_que_no_existe_no_finge_que_si(aislado):
    resultado = _correr("inventado", entorno=aislado)

    assert resultado.returncode != 0
    assert "invalid choice" in resultado.stderr or "error" in resultado.stderr.lower()


def test_sin_comando_muestra_la_ayuda(aislado):
    resultado = _correr(entorno=aislado)

    assert "usage" in (resultado.stdout + resultado.stderr).lower()
