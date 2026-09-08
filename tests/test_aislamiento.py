"""
Pruebas de que la suite no escribe en la instancia.

`CLAUDE.md` lo pone entre lo que no se hace, y aun así llevaba tiempo pasando:
`data/yuki_memory.db` había acumulado 887 recuerdos falsos —«Encuentro con
Productor», uno o dos por cada pasada de la suite— porque el agente resolvía la
ruta de la memoria desde `config.yaml` ignorando `DATABASE_PATH`, que es lo que
`conftest.py` redirige.

El mismo defecto tenía una cara peor fuera de las pruebas: la copia de
seguridad, la sonda de signos vitales y la comprobación de humo **sí** respetan
`DATABASE_PATH`. Una instancia con esa variable puesta habría estado escribiendo
en un sitio y respaldando y vigilando otro: una copia impecable de una base que
nadie usa.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_la_variable_de_entorno_manda_sobre_la_configuracion(monkeypatch, tmp_path):
    """
    La misma precedencia que en el resto del proyecto.

    Si el que escribe y los que leen no resuelven la ruta igual, todo lo demás
    —copias, métricas, signos vitales— habla de una base distinta.
    """
    from src.core.agent import YukiAgent

    elegida = tmp_path / "otra" / "memoria.db"
    monkeypatch.setenv("DATABASE_PATH", str(elegida))
    agente = YukiAgent()

    assert agente.memory_manager.engine.db_path == str(elegida)
    assert elegida.is_file(), "no llegó a crear la base donde dijo"


def test_todos_los_que_miran_la_memoria_miran_la_misma(monkeypatch, tmp_path):
    """
    El que escribe, el que copia y el que vigila, de acuerdo.

    Es la propiedad que faltaba, y su ausencia no da ningún error: da una copia
    perfecta de la base equivocada.
    """
    from src.core.agent import YukiAgent
    from src.core.pulse import Pulse
    from src.tools.backup import BackupManager

    elegida = tmp_path / "instancia" / "memoria.db"
    monkeypatch.setenv("DATABASE_PATH", str(elegida))
    config = {"memory": {"database_path": "data/otra_cosa.db"}}

    escribe = YukiAgent().memory_manager.engine.db_path
    copia = BackupManager.from_config(config).db_path
    vigila = Pulse(config).db_path

    assert str(escribe) == str(copia) == str(vigila) == str(elegida)


def test_la_suite_no_deja_recuerdos_en_la_base_de_la_instancia(monkeypatch, tmp_path):
    """
    Construir el agente entero no puede tocar `data/yuki_memory.db`.

    Se comprueba con la variable puesta como la pone `conftest.py`: si alguien
    vuelve a resolver la ruta ignorándola, esto lo dice.
    """
    from src.core.agent import YukiAgent

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "aislada" / "memoria.db"))
    real = os.path.join(os.path.dirname(__file__), "..", "data", "yuki_memory.db")
    antes = os.path.getsize(real) if os.path.exists(real) else None

    YukiAgent()

    if antes is not None:
        assert os.path.getsize(real) == antes, "la suite escribió en la base de la instancia"
