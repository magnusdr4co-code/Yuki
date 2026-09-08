"""
Pruebas del ensayo de restauración.

`docs/VIRTUALIZACION_Y_MEJORAS.md` dice que una copia sin restaurar no está
comprobada. Estas pruebas comprueban al comprobador: que detecte una copia
corrupta, una base vacía —que es un desastre con buena salud— y un tar con rutas
que escapen del destino, porque los fallos que «no pueden pasar» son los que
nadie mira.
"""

import json
import os
import sqlite3
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.restore_drill import ciclo_completo, restaurar, ultima_copia  # noqa: E402


def _copia(tmp_path, *, recuerdos=3, con_manifiesto=True, precinto=None) -> Path:
    escenario = tmp_path / "escenario"
    escenario.mkdir(exist_ok=True)

    base = escenario / "yuki_memory.db"
    conexion = sqlite3.connect(base)
    conexion.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, category TEXT, "
                     "title TEXT, content TEXT)")
    for indice in range(recuerdos):
        conexion.execute("INSERT INTO memories (category, title, content) VALUES (?,?,?)",
                         ("visitor", f"t{indice}", "contenido"))
    conexion.commit()
    conexion.close()

    (escenario / "Biblioteca").mkdir(exist_ok=True)
    (escenario / "Biblioteca" / "CANON.md").write_text("herrumbre", encoding="utf-8")

    if con_manifiesto:
        manifiesto = {"creado": "20260908T000000", "integridad_db": "ok",
                      "incluidos": ["yuki_memory.db"], "omitidos": []}
        if precinto:
            manifiesto["precinto_bitacora"] = precinto
        (escenario / "MANIFIESTO.json").write_text(json.dumps(manifiesto), encoding="utf-8")

    destino = tmp_path / "yuki_backup_20260908T000000.tar.gz"
    with tarfile.open(destino, "w:gz") as archivo:
        for elemento in sorted(escenario.iterdir()):
            archivo.add(elemento, arcname=elemento.name)
    return destino


def _resultado(informe, nombre):
    return next(r for r in informe if r["prueba"] == nombre)


def test_una_copia_sana_restaura(tmp_path):
    informe = restaurar(_copia(tmp_path), tmp_path / "destino")

    assert all(r["ok"] for r in informe), informe
    assert "3 recuerdo(s)" in _resultado(informe, "memoria")["detalle"]
    assert "1 fichero(s) de canon" in _resultado(informe, "biblioteca")["detalle"]


def test_una_base_vacia_es_un_desastre_con_buena_salud(tmp_path):
    """Integridad ok y cero recuerdos: la copia existe y no sirve para nada."""
    informe = restaurar(_copia(tmp_path, recuerdos=0), tmp_path / "destino")

    memoria = _resultado(informe, "memoria")
    assert not memoria["ok"] and "vacía" in memoria["detalle"]


def test_una_copia_ilegible_se_detecta(tmp_path):
    rota = tmp_path / "yuki_backup_rota.tar.gz"
    rota.write_bytes(b"esto no es un tar")

    informe = restaurar(rota, tmp_path / "destino")

    assert not _resultado(informe, "apertura")["ok"]


def test_un_tar_que_escapa_del_destino_no_se_extrae(tmp_path):
    """Un `../` dentro del archivo sobrescribiría lo que quisiera al extraerlo."""
    malicioso = tmp_path / "yuki_backup_malicioso.tar.gz"
    fuera = tmp_path / "carga.txt"
    fuera.write_text("carga", encoding="utf-8")
    with tarfile.open(malicioso, "w:gz") as archivo:
        archivo.add(fuera, arcname="../../escapado.txt")

    informe = restaurar(malicioso, tmp_path / "destino")

    rutas = _resultado(informe, "rutas_del_archivo")
    assert not rutas["ok"] and "peligrosa" in rutas["detalle"]
    assert len(informe) == 1, "no se sigue extrayendo tras detectarlo"
    assert not (tmp_path / "escapado.txt").exists()


def test_sin_manifiesto_se_dice(tmp_path):
    informe = restaurar(_copia(tmp_path, con_manifiesto=False), tmp_path / "destino")

    assert not _resultado(informe, "manifiesto")["ok"]


def test_un_precinto_que_ya_no_esta_en_la_cadena_delata_un_corte(tmp_path, monkeypatch):
    from src.core.blackbox import BlackBox

    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "bitacora.jsonl"))
    caja = BlackBox(path=str(tmp_path / "bitacora.jsonl"))
    caja.record("acto", {})
    precinto_viejo = caja.seal()
    # La cadena se rehace desde cero: el precinto de la copia ya no está en ella.
    caja.path.write_text("", encoding="utf-8")
    caja.record("acto_nuevo", {})

    informe = restaurar(_copia(tmp_path, precinto=precinto_viejo), tmp_path / "destino")

    resultado = _resultado(informe, "precinto")
    assert not resultado["ok"] and "cortó" in resultado["detalle"]


def test_se_elige_la_copia_mas_reciente(tmp_path):
    for marca in ("20260901T010000", "20260907T010000", "20260903T010000"):
        (tmp_path / f"yuki_backup_{marca}.tar.gz").write_bytes(b"x")

    assert ultima_copia(str(tmp_path)).name == "yuki_backup_20260907T010000.tar.gz"


def test_sin_copias_no_hay_ensayo(tmp_path):
    assert ultima_copia(str(tmp_path)) is None


def test_el_circuito_completo_copia_y_restaura_de_verdad(tmp_path):
    """
    El modo `--ciclo`: fabricar, copiar, restaurar, sin copia previa.

    Es la prueba que delataría el día que `BackupManager` dejase de incluir la
    base en el tar — un fallo que en el modo normal no se ve, porque allí la
    copia ya venía hecha.
    """
    copia, informe = ciclo_completo(tmp_path)

    assert copia is not None and copia.is_file()
    assert [r["prueba"] for r in informe][:2] == ["copia", "rutas_del_archivo"]
    assert all(r["ok"] for r in informe), [r for r in informe if not r["ok"]]
    assert "3 recuerdo(s)" in _resultado(informe, "memoria")["detalle"]
    assert "1 fichero(s)" in _resultado(informe, "biblioteca")["detalle"]


def test_el_circuito_completo_no_toca_la_bitacora_de_la_instancia(tmp_path, monkeypatch):
    """
    El ensayo se hace en su propio mundo.

    Si el sandbox escribiera en la bitácora real, cada ejecución en la CI dejaría
    huella en la cadena de actos de Yuki: un registro de lo que ella hizo,
    contaminado con lo que hizo su simulacro.
    """
    real = tmp_path / "real" / "bitacora.jsonl"
    real.parent.mkdir(parents=True)
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(real))

    ciclo_completo(tmp_path / "ensayo")

    assert not real.exists()
    assert os.environ["YUKI_BLACKBOX_PATH"] == str(real)


def test_el_circuito_no_depende_del_entorno_heredado(tmp_path, monkeypatch):
    """
    Una variable heredada no puede vaciar la copia en silencio.

    `BackupManager` deduce el nombre del fichero de base de `DATABASE_PATH`. Con
    una apuntando a otro nombre, la copia saldría **sin base dentro** y el
    ensayo daría por buena una copia vacía: exactamente el fallo que este guion
    existe para detectar. Apareció como una prueba que fallaba una vez de cada
    muchas, según qué otra prueba corriera antes.
    """
    monkeypatch.setenv("DATABASE_PATH", "/ruta/que/no/existe/otro_nombre.db")
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", "/ruta/que/no/existe/bitacora.jsonl")

    copia, informe = ciclo_completo(tmp_path)

    assert copia is not None
    assert all(r["ok"] for r in informe), [r for r in informe if not r["ok"]]
    assert "3 recuerdo(s)" in _resultado(informe, "memoria")["detalle"]
    # Y el entorno queda como estaba: el ensayo no deja rastro en quien lo llama.
    assert os.environ["DATABASE_PATH"] == "/ruta/que/no/existe/otro_nombre.db"
