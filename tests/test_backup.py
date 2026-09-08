"""
Pruebas de la copia de memoria y canon.

Lo que se protege: que la base se copie de forma coherente y verificada —un tar
de un SQLite vivo restaura corrupto justo cuando hace falta—, que la ausencia de
destino remoto se declare en vez de sugerir que la copia está a salvo, y que un
fallo de subida no se presente como éxito.
"""

import os
import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.backup import BackupManager  # noqa: E402


@pytest.fixture
def instancia(tmp_path):
    """Un disco de instancia con memoria, canon y estado."""
    data = tmp_path / "data"
    output = tmp_path / "output"
    (output / "Biblioteca").mkdir(parents=True)
    data.mkdir(parents=True)

    conexion = sqlite3.connect(data / "yuki_memory.db")
    conexion.execute("CREATE TABLE recuerdos (id INTEGER PRIMARY KEY, texto TEXT)")
    conexion.execute("INSERT INTO recuerdos (texto) VALUES ('el agua encuentra su camino')")
    conexion.commit()
    conexion.close()

    (output / "Biblioteca" / "CANON.md").write_text("herrumbre y escarcha", encoding="utf-8")
    (data / "vital_state.json").write_text('{"energia": 0.7}', encoding="utf-8")
    return data, output


def _gestor(tmp_path, instancia, **kwargs):
    data, output = instancia
    return BackupManager(data_dir=str(data), output_dir=str(output),
                         backup_dir=str(tmp_path / "backups"), bucket="", **kwargs)


def test_la_copia_incluye_lo_irremplazable(tmp_path, instancia):
    resultado = _gestor(tmp_path, instancia).create()

    assert resultado.status == "success"
    with tarfile.open(resultado.path) as archivo:
        nombres = archivo.getnames()
    assert "yuki_memory.db" in nombres
    assert "Biblioteca/CANON.md" in nombres
    assert "vital_state.json" in nombres
    assert "MANIFIESTO.json" in nombres


def test_la_base_se_copia_coherente_y_verificada(tmp_path, instancia):
    """`integrity_check` sobre la copia: una copia que nadie abrió no es copia."""
    data, _ = instancia
    resultado = _gestor(tmp_path, instancia).create()

    assert resultado.integrity == "ok"

    destino = tmp_path / "extraido"
    with tarfile.open(resultado.path) as archivo:
        archivo.extractall(destino)
    conexion = sqlite3.connect(destino / "yuki_memory.db")
    filas = conexion.execute("SELECT texto FROM recuerdos").fetchall()
    conexion.close()
    assert filas == [("el agua encuentra su camino",)]


def test_la_copia_funciona_con_el_escritor_en_marcha(tmp_path, instancia):
    """En producción el daemon está escribiendo mientras corre la copia."""
    data, _ = instancia
    escritor = sqlite3.connect(data / "yuki_memory.db")
    escritor.execute("PRAGMA journal_mode=WAL")
    escritor.execute("INSERT INTO recuerdos (texto) VALUES ('escrito durante la copia')")
    escritor.commit()

    resultado = _gestor(tmp_path, instancia).create()
    escritor.close()

    assert resultado.status == "success" and resultado.integrity == "ok"


def test_lo_que_no_existe_se_declara_ausente(tmp_path, instancia):
    resultado = _gestor(tmp_path, instancia).create()

    assert any("runtime_overrides" in omitido for omitido in resultado.skipped)
    assert "vital_state.json" in resultado.included


def test_sin_bucket_se_dice_que_la_copia_no_sale_del_disco(tmp_path, instancia):
    resultado = _gestor(tmp_path, instancia).create()

    assert resultado.remote_uri is None
    assert "no protege de perderlo" in resultado.remote_error


def test_con_bucket_se_registra_el_destino_remoto(tmp_path, instancia):
    subidas = []

    def subir(bucket, archivo):
        subidas.append((bucket, archivo.name))
        return f"gs://{bucket}/{archivo.name}"

    data, output = instancia
    gestor = BackupManager(data_dir=str(data), output_dir=str(output),
                           backup_dir=str(tmp_path / "backups"),
                           bucket="yuki-respaldo", uploader=subir)

    resultado = gestor.create()

    assert len(subidas) == 1 and subidas[0][0] == "yuki-respaldo"
    assert resultado.remote_uri.startswith("gs://yuki-respaldo/")


def test_un_fallo_de_subida_no_se_presenta_como_exito(tmp_path, instancia):
    def subir_que_falla(bucket, archivo):
        raise OSError("403 desde Cloud Storage")

    data, output = instancia
    gestor = BackupManager(data_dir=str(data), output_dir=str(output),
                           backup_dir=str(tmp_path / "backups"),
                           bucket="yuki-respaldo", uploader=subir_que_falla)

    resultado = gestor.create()

    assert resultado.status == "success", "la copia local sí se hizo"
    assert resultado.remote_uri is None
    assert "403" in resultado.remote_error


def test_la_poda_conserva_solo_las_ultimas(tmp_path, instancia):
    """El disco de la e2-small es pequeño: una copia de hace semanas no sirve."""
    gestor = _gestor(tmp_path, instancia, retention=2)
    carpeta = tmp_path / "backups"
    carpeta.mkdir(parents=True, exist_ok=True)
    for marca in ("20260901T010000", "20260902T010000", "20260903T010000"):
        (carpeta / f"yuki_backup_{marca}.tar.gz").write_bytes(b"copia antigua")

    borradas = gestor.prune()

    nombres = [Path(c["path"]).name for c in gestor.list_backups()]
    assert borradas == 1
    assert nombres == ["yuki_backup_20260902T010000.tar.gz", "yuki_backup_20260903T010000.tar.gz"]

    # Y una copia nueva vuelve a dejar sólo dos.
    gestor.create()
    assert len(gestor.list_backups()) == 2


def test_sin_base_de_datos_la_copia_sigue_siendo_util(tmp_path, instancia):
    data, _ = instancia
    (data / "yuki_memory.db").unlink()

    resultado = _gestor(tmp_path, instancia).create()

    assert resultado.status == "success"
    assert resultado.integrity == "sin base de datos"
    assert any("yuki_memory.db" in omitido for omitido in resultado.skipped)


def test_from_config_respeta_retencion_y_bucket(monkeypatch):
    monkeypatch.delenv("BACKUP_GCS_BUCKET", raising=False)
    gestor = BackupManager.from_config({"backup": {"retention": 3, "bucket": "cubo"}})

    assert gestor.retention == 3 and gestor.bucket == "cubo"


def test_renombrar_la_base_en_la_configuracion_no_produce_copias_sin_memoria(tmp_path, monkeypatch):
    """
    El fallo que se coló durante meses: directorio de la configuración, nombre
    del valor por defecto.

    Renombrar la base en `config.yaml` bastaba para que todas las copias
    nocturnas salieran **sin memoria dentro** informando `success`. Una copia
    así no se nota hasta el día en que hay que restaurarla.
    """
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    datos = tmp_path / "data"
    datos.mkdir()
    sqlite3.connect(datos / "memoria_de_yuki.db").close()

    gestor = BackupManager.from_config(
        {"memory": {"database_path": str(datos / "memoria_de_yuki.db")}})

    assert gestor.db_path.name == "memoria_de_yuki.db"


def test_una_base_que_existe_con_otro_nombre_para_la_copia(tmp_path, instancia):
    """
    Nueva sin base es legítimo; con base y sin encontrarla, no.

    Llamar «success» a una copia que se deja fuera lo único irremplazable es
    peor que fallar: nadie va a mirar dos veces un trabajo que dijo que salió
    bien.
    """
    data, _ = instancia
    (data / "yuki_memory.db").rename(data / "otra_memoria.db")

    resultado = _gestor(tmp_path, instancia).create()

    assert resultado.status == "error"
    assert "otra_memoria.db" in resultado.error
    assert "sin memoria dentro" in resultado.error
