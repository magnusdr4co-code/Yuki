"""
Noventa y siete `logger.info` que no se veían.

`deploy/gce-startup.sh` declara `LOG_LEVEL=INFO` desde el primer despliegue y no
lo leía nadie: no había una sola llamada a `logging.basicConfig` en el proyecto,
así que el nivel efectivo era el de Python por defecto —WARNING en la raíz— y
todo lo registrado con `logger.info` se perdía.

Lo que se perdía es justo lo que se mira cuando algo va mal: qué proveedor
sirvió, qué paso de un encargo se completó, si una difusión salió. `OPERACION.md`
manda leer `docker logs yuki-daemon` para diagnosticar, y la mitad del
diagnóstico no estaba. Un log vacío no falla: tranquiliza.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RAIZ = Path(__file__).resolve().parents[1]

from src.core.registro import NIVEL_POR_DEFECTO, configurar  # noqa: E402


def test_sin_declarar_nada_el_nivel_es_informativo():
    """WARNING por defecto dejaba mudo el 97% de lo que la instancia cuenta."""
    assert configurar(nivel=None) in (NIVEL_POR_DEFECTO, os.getenv("LOG_LEVEL", "").upper())


def test_un_nivel_con_errata_no_deja_la_instancia_muda(caplog):
    """Y se avisa por el propio log, que a esas alturas ya funciona."""
    with caplog.at_level(logging.WARNING, logger="Yuki"):
        aplicado = configurar(nivel="CHORIZO")

    assert aplicado == NIVEL_POR_DEFECTO
    assert any("no es un nivel conocido" in r.message for r in caplog.records)


@pytest.mark.parametrize("nivel", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_un_nivel_valido_se_respeta(nivel):
    assert configurar(nivel=nivel) == nivel


def test_el_cli_enciende_el_log_antes_de_hacer_nada(tmp_path):
    """
    Camino del producto: se ejecuta `cli.py` de verdad y, cuando termina, se
    emite un `logger.info`. Si el CLI no dejó el log configurado, esa línea no
    sale — que es exactamente lo que le pasaba a los noventa y siete que hay
    repartidos por la instancia.
    """
    guion = tmp_path / "arranca_cli.py"
    guion.write_text(
        "import logging, runpy, sys\n"
        "sys.argv = ['cli.py', 'spend']\n"
        "try:\n"
        "    runpy.run_path('cli.py', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "logging.getLogger('Yuki.Comprobacion').info('EL-LOG-ESTA-ENCENDIDO')\n",
        encoding="utf-8")

    salida = subprocess.run([sys.executable, "-B", str(guion)], cwd=RAIZ,
                            capture_output=True, text=True, timeout=120)

    assert "EL-LOG-ESTA-ENCENDIDO" in (salida.stdout + salida.stderr), (
        "el CLI no dejó el log encendido: los logger.info de producción se pierden")


def test_el_salon_tambien_lo_enciende_si_se_arranca_suelto():
    """`python -m src.web.server` no pasa por `cli.py`; ahí también o corre mudo."""
    servidor = (RAIZ / "src" / "web" / "server.py").read_text(encoding="utf-8")
    despues = servidor[servidor.index('if __name__ == "__main__":'):]

    # La importación sola no enciende nada: hay que comprobar la llamada, que es
    # lo que se puede quitar dejando el import de adorno.
    assert "registro import configurar" in despues
    assert "_configurar_log()" in despues, "se importa y no se llama: el Salón corre mudo"


def test_el_formato_dice_de_que_subsistema_viene():
    """Los loggers se llaman `Yuki.<subsistema>`; sin el nombre, el log no se lee."""
    from src.core.registro import FORMATO

    assert "%(name)s" in FORMATO
    assert "%(levelname)" in FORMATO
