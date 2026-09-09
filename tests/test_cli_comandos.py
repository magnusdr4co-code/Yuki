"""
Los comandos de lectura, ejecutados dentro del proceso.

`test_cli.py` los ejecuta como subproceso, que es lo fiel —comprueba el punto de
entrada de verdad, con su analizador de argumentos y su código de salida— pero
la cobertura no puede ver dentro de un subproceso: los seiscientos noventa
enunciados de `src/cli/` aparecían al 0% aunque estuvieran probados.

Aquí se llaman las funciones directamente. No sustituye a la otra prueba: la
complementa. Una comprueba que el comando existe y arranca; ésta, que su cuerpo
hace algo sin reventar y devuelve lo que dice devolver.

Sólo los que leen. Los que conversan, sirven o generan medios siguen fuera:
una prueba que gaste crédito se deja de ejecutar a la tercera semana.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cli import gobierno, mente  # noqa: E402

# `(módulo, función, argumentos)` — todos de sólo lectura.
COMANDOS = [
    (gobierno, "cmd_pulse", {}),
    (gobierno, "cmd_spend", {}),
    (gobierno, "cmd_blackbox", {}),
    (gobierno, "cmd_brake", {}),
    (gobierno, "cmd_state", {}),
    (gobierno, "cmd_virtualize", {}),
    (mente, "cmd_agency", {}),
    (mente, "cmd_persona", {}),
    (mente, "cmd_transparency", {}),
]


@pytest.fixture(autouse=True)
def instancia_vacia(tmp_path, monkeypatch):
    """Contra una instancia recién nacida: ni memoria previa ni obra."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "memoria.db"))
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.chdir(os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.parametrize("modulo,nombre,extra",
                         COMANDOS, ids=[c[1] for c in COMANDOS])
def test_el_comando_emite_json_legible(modulo, nombre, extra, capsys):
    """
    Que arranque no basta: tiene que producir algo que una máquina pueda leer.

    Es lo que consume el panel, la sonda y cualquiera que encadene `cli.py … |
    jq`. Un comando que imprime prosa donde promete JSON rompe eso en silencio.
    """
    getattr(modulo, nombre)(as_json=True, **extra)

    salida = capsys.readouterr().out.strip()
    assert salida, f"{nombre} --json no emitió nada"
    assert isinstance(json.loads(salida), (dict, list))


@pytest.mark.parametrize("modulo,nombre,extra",
                         COMANDOS, ids=[c[1] for c in COMANDOS])
def test_el_comando_tambien_habla_para_personas(modulo, nombre, extra, capsys):
    """
    El modo sin `--json` es el que se mira con prisa, y es el que nadie prueba.

    No se comprueba qué dice —eso cambiaría con cada retoque de redacción— sino
    que diga algo y no reviente por el camino.
    """
    getattr(modulo, nombre)(**extra)

    assert capsys.readouterr().out.strip()


def test_el_sueno_en_seco_no_toca_la_memoria(capsys, tmp_path):
    """
    `--seco` existe para poder mirar qué haría la noche sin que la haga.

    Si tocara la memoria, el ensayo sería el suceso.
    """
    import sqlite3
    from contextlib import closing

    mente.cmd_sleep(fase="nrem", seco=True, as_json=True)

    salida = json.loads(capsys.readouterr().out.strip())
    assert salida.get("seco") is True or "seco" in json.dumps(salida)

    base = os.environ["DATABASE_PATH"]
    if os.path.exists(base):
        with closing(sqlite3.connect(f"file:{base}?mode=ro", uri=True)) as conexion:
            filas = conexion.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        assert filas == 0, "el ensayo en seco escribió en la memoria"


def test_el_freno_se_pone_y_se_suelta_desde_la_linea_de_ordenes(capsys, monkeypatch, tmp_path):
    """La palanca que se usa con prisa: comprobada de punta a punta."""
    monkeypatch.setenv("YUKI_FRENO_PATH", str(tmp_path / "freno.json"))
    monkeypatch.delenv("YUKI_FRENO", raising=False)

    gobierno.cmd_brake(nivel="todo", motivo="prueba", as_json=True)
    puesto = json.loads(capsys.readouterr().out.strip())

    gobierno.cmd_brake(soltar=True, as_json=True)
    soltado = json.loads(capsys.readouterr().out.strip())

    assert puesto.get("nivel") == "todo" or "todo" in json.dumps(puesto)
    assert "ninguno" in json.dumps(soltado)


# --- Las rutas que hacen algo, no sólo las que leen ---

def test_la_copia_desde_la_linea_de_ordenes_se_crea_y_se_ensaya(capsys, tmp_path, monkeypatch):
    """
    `cli.py backup --ensayar` es lo que ejecuta quien quiere una copia **ahora**
    y no fiarse de que sirva. Sesenta líneas sin una prueba, incluida la que
    decide si la copia se da por buena.
    """
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "data" / "bitacora.jsonl"))
    (tmp_path / "data").mkdir(exist_ok=True)
    # Con memoria dentro: una copia de una base vacía **no** restaura, y hace
    # bien —una base íntegra y vacía es un desastre con buena salud—.
    from src.memory.fts5_memory import FTS5MemoryEngine
    FTS5MemoryEngine(os.environ["DATABASE_PATH"]).add_memory(
        category="conversation", title="algo", content="que recordar")

    resultado = gobierno.cmd_backup(as_json=True, ensayar=True)

    salida = json.loads(capsys.readouterr().out.strip())
    assert resultado.status == "success"
    assert salida["ensayo_de_restauracion"]["ok"] is True
    assert any(p["prueba"] == "memoria" for p in salida["ensayo_de_restauracion"]["resultados"])


def test_la_copia_sin_ensayar_no_afirma_que_restaure(capsys, tmp_path, monkeypatch):
    """No se da por comprobado lo que no se ha comprobado."""
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "data" / "bitacora.jsonl"))

    gobierno.cmd_backup(as_json=True)

    salida = json.loads(capsys.readouterr().out.strip())
    assert "ensayo_de_restauracion" not in salida


def test_la_bitacora_se_verifica_y_se_precinta(capsys, tmp_path, monkeypatch):
    """
    Verificar y sellar son las dos operaciones que se usan cuando hay sospecha
    de manipulación, y ninguna estaba probada desde la línea de órdenes.
    """
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "bitacora.jsonl"))
    from src.core.blackbox import BlackBox

    BlackBox().record("acto_de_prueba", {})

    gobierno.cmd_blackbox(verificar=True, as_json=True)
    verificacion = json.loads(capsys.readouterr().out.strip())
    assert verificacion["integra"] is True

    gobierno.cmd_blackbox(precinto="crear", as_json=True)
    precinto = json.loads(capsys.readouterr().out.strip())
    assert precinto["entradas"] >= 1 and precinto["head"]


def test_exportar_lo_que_guarda_de_una_persona(capsys, tmp_path, monkeypatch):
    """El derecho de acceso, por la puerta por la que se ejerce."""
    from src.memory.fts5_memory import FTS5MemoryEngine

    motor = FTS5MemoryEngine(os.environ["DATABASE_PATH"])
    motor.add_memory(category="conversation", title="Charla", content="algo dicho",
                     user_id="99887766")

    gobierno.cmd_state(exportar="99887766", as_json=True)

    exportado = json.loads(capsys.readouterr().out.strip())
    assert exportado["recuerdos_total"] == 1


def test_olvidar_de_verdad_y_dejar_recibo(capsys, tmp_path, monkeypatch):
    """
    Lo único irreversible de toda la consola: que borre, que lo diga, y que la
    memoria quede efectivamente sin esa persona.
    """
    from src.memory.fts5_memory import FTS5MemoryEngine

    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "bitacora.jsonl"))
    motor = FTS5MemoryEngine(os.environ["DATABASE_PATH"])
    motor.add_memory(category="conversation", title="Charla", content="algo dicho",
                     user_id="55443322")

    gobierno.cmd_state(olvidar="55443322", motivo="lo pidió por escrito", as_json=True)

    recibo = json.loads(capsys.readouterr().out.strip())
    assert recibo["recuerdos_borrados"] == 1

    gobierno.cmd_state(exportar="55443322", as_json=True)
    despues = json.loads(capsys.readouterr().out.strip())
    assert despues["recuerdos_total"] == 0, "dijo que borró y no borró"


def test_lo_que_no_es_una_persona_no_se_olvida_desde_el_cli(capsys):
    """`general` no es nadie: es la memoria de Yuki. Borrarla sería vaciarla."""
    gobierno.cmd_state(olvidar="general", motivo="prueba", as_json=True)

    rechazo = json.loads(capsys.readouterr().out.strip())
    assert "no designa a una persona" in rechazo["error"]
    assert rechazo["sujeto"] == "general"


def test_las_fases_del_sueno_se_pueden_mirar_sin_hacerlas(capsys):
    """Las cuatro en seco: mirar qué haría la noche sin que la haga."""
    for fase in ("nrem", "olvido", "fusiones"):
        mente.cmd_sleep(fase=fase, seco=True, as_json=True)
        assert json.loads(capsys.readouterr().out.strip()) is not None
