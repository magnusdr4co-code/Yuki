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


# --- La otra variable de reubicación: dónde acaba lo que Yuki crea ---

def test_la_salida_se_reubica_entera_o_no_sirve_de_nada(monkeypatch, tmp_path):
    """
    Cinco módulos escribían en `output/…` fijo mientras uno respetaba la
    variable, y la auditoría del Artículo 50 mira la de la variable.

    Es decir: material sintético sin marcar que el auditor **no puede ver**. Eso
    ya no es ruido en las pruebas, es un agujero de cumplimiento.
    """
    from src.tools.creation_library import CreationLibrary
    from src.tools.music_fallback import LocalMusicEngine
    from src.tools.vertex_media import VertexMediaClient

    destino = tmp_path / "otra_salida"
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(destino))

    medios = VertexMediaClient.__new__(VertexMediaClient)
    VertexMediaClient.__init__(medios, project_id="", location="global")
    motor = LocalMusicEngine()
    biblioteca = CreationLibrary()

    for ruta in (medios.art_dir, medios.voice_dir, medios.music_dir, medios.video_dir,
                 motor.music_dir, str(biblioteca.output)):
        assert str(destino) in str(ruta), f"{ruta} se quedó fuera de la reubicación"


def test_la_ruta_se_resuelve_al_llamar_y_no_al_importar(monkeypatch, tmp_path):
    """
    Un `def f(dir="output/art")` congela el valor en el momento de importar el
    módulo, que es antes de que nadie haya podido reubicar nada. El síntoma es
    desconcertante: la variable funciona o no según qué se importó primero.
    """
    from src.core.rutas import salida

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "primera"))
    assert str(tmp_path / "primera" / "art") == str(salida("art"))

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "segunda"))
    assert str(tmp_path / "segunda" / "art") == str(salida("art"))


def test_la_precedencia_es_la_misma_para_las_dos_variables(monkeypatch, tmp_path):
    """Entorno, luego configuración, luego el valor por defecto. Sin excepciones."""
    from src.core.rutas import base_de_datos, salida

    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("YUKI_OUTPUT_DIR", raising=False)
    assert str(base_de_datos()) == "data/yuki_memory.db"
    assert str(base_de_datos({"memory": {"database_path": "otra/mem.db"}})) == "otra/mem.db"
    assert str(salida()) == "output"

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "manda.db"))
    assert str(base_de_datos({"memory": {"database_path": "otra/mem.db"}})) == str(tmp_path / "manda.db")


def test_la_suite_no_deja_medios_sin_marcar_en_la_salida_del_repositorio():
    """
    Cinco ficheros de medios aparecieron en `output/` del repositorio durante una
    pasada de la suite, y la comprobación de humo los denunció como material
    sintético sin marcar. Se comprueba que la salida real queda intacta.
    """
    from src.core.transparency import audit_directory

    auditoria = audit_directory(os.path.join(os.path.dirname(__file__), "..", "output"))

    assert not auditoria["sin_marcar"], (
        f"hay material sin marcar en la salida real: {auditoria['sin_marcar'][:5]}")


def test_quien_escribe_y_quien_copia_miran_el_mismo_sitio(monkeypatch, tmp_path):
    """
    La propiedad que faltaba, y cuya ausencia no daba ningún error.

    `VitalState` y el perfil de Honcho escribían en `data/` fijo mientras la
    copia de seguridad los buscaba en el directorio reubicado, y la Biblioteca
    se guardaba donde dijera `YUKI_OUTPUT_DIR` mientras la copia miraba
    `output/`. En una instancia con esas variables puestas, **nada de eso
    entraba en ninguna copia**: el manifiesto los listaba como ausentes, que es
    donde nadie mira hasta el día de restaurar.
    """
    from src.core.agent import YukiAgent
    from src.tools.backup import BackupManager

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "datos" / "memoria.db"))
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "salida"))

    gestor = BackupManager.from_config({})
    # Por el camino que recorre el producto, no construyendo `VitalState` suelto:
    # la primera versión de esta prueba pasaba mientras el agente seguía pasándole
    # la ruta fija a mano, que anulaba el arreglo entero.
    agente = YukiAgent()

    assert agente.vital_state.state_path == str(gestor.data_dir / "vital_state.json")
    assert str(gestor.output_dir) == str(tmp_path / "salida")
    assert str(gestor.db_path) == str(tmp_path / "datos" / "memoria.db")


def test_la_auditoria_del_articulo_50_mira_donde_se_escribe(monkeypatch, tmp_path):
    """
    Si el auditor mira `output/` fijo y los medios se escriben en otro sitio, la
    conformidad que declara es sobre un directorio vacío.
    """
    from src.core.rutas import salida
    from src.core.transparency import audit_directory

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "salida"))
    (tmp_path / "salida" / "art").mkdir(parents=True)
    (tmp_path / "salida" / "art" / "sin_marca.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)

    auditoria = audit_directory()

    assert str(salida()) == str(tmp_path / "salida")
    assert auditoria["sin_marcar"], "el auditor no vio un fichero que sí está sin marcar"
