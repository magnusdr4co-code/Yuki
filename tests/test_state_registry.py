"""
Pruebas del gobierno del estado durable.

La revisión de arquitecturas always-on de 2026 lo dice así: el campo es fluido
metiendo estado y casi mudo sacándolo, revocándolo o deshaciendo lo que hizo.
Lo que se prueba aquí es la mitad muda: que se pueda inventariar, exportar y
—sobre todo— **borrar de verdad**, con recibo y sin fantasmas en el índice.
"""

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.state_registry import StateRegistry, build_registry  # noqa: E402
from src.memory.fts5_memory import FTS5MemoryEngine  # noqa: E402


@pytest.fixture
def memoria(tmp_path, monkeypatch):
    """Una memoria real con recuerdos de dos personas y del canon."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "yuki.db"))
    motor = FTS5MemoryEngine(db_path=str(tmp_path / "yuki.db"))
    motor.add_memory("visitor", "Una confidencia", "Me contó que dejó la música a los veinte.",
                     tags="confidencia", user_id="seguidor_1")
    motor.add_memory("visitor", "Otra tarde", "Volvió a hablarme del puerto.",
                     tags="charla", user_id="seguidor_1")
    motor.add_memory("visitor", "Alguien más", "Preguntó por la portada.",
                     tags="charla", user_id="seguidor_2")
    motor.add_memory("core", "Canon", "El agua encuentra su camino.", tags="canon")
    return motor


# --- Inventario ---

def test_el_inventario_declara_los_seis_ejes():
    for pieza in build_registry():
        assert pieza.authority and pieza.scope and pieza.mutability
        assert pieza.provenance and pieza.recoverability and pieza.actionability


def test_la_auditoria_señala_lo_que_acciona_y_lo_que_guarda_datos_personales():
    auditoria = StateRegistry().audit()

    assert "memoria" in auditoria["con_datos_personales"]
    assert "emparejamiento" in auditoria["con_datos_personales"]
    # Un ritmo aprobado y un trabajo pendiente ejecutan solos al arrancar.
    assert "ritmos_propios" in auditoria["accionables"]
    assert "trabajos_multimedia" in auditoria["accionables"]


def test_la_auditoria_no_se_rompe_con_piezas_ausentes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "vacio" / "yuki.db"))
    auditoria = StateRegistry().audit()

    assert auditoria["presentes"] == 0
    assert all(pieza["bytes"] == 0 for pieza in auditoria["piezas"])


# --- Derecho de acceso ---

def test_exportar_devuelve_datos_y_no_una_descripcion_de_los_datos(memoria, tmp_path):
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"))

    exportado = registro.subject_export("seguidor_1")

    assert exportado["recuerdos_total"] == 2
    contenidos = " ".join(r["content"] for r in exportado["recuerdos"])
    assert "dejó la música" in contenidos


def test_exportar_no_filtra_lo_de_otra_persona(memoria, tmp_path):
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"))

    exportado = registro.subject_export("seguidor_1")

    assert all(r["title"] != "Alguien más" for r in exportado["recuerdos"])


def test_exportar_a_alguien_desconocido_no_falla(memoria, tmp_path):
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"))

    assert registro.subject_export("nadie")["recuerdos_total"] == 0


# --- Derecho de supresión ---

def test_el_olvido_borra_de_verdad_y_emite_recibo(memoria, tmp_path):
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"),
                             audit_path=str(tmp_path / "auditoria.log"))

    recibo = registro.subject_forget("seguidor_1", actor="Productor", reason="lo pidió")

    assert recibo["recuerdos_borrados"] == 2
    assert registro.subject_export("seguidor_1")["recuerdos_total"] == 0
    with sqlite3.connect(tmp_path / "yuki.db") as conexion:
        filas = conexion.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?",
                                 ("seguidor_1",)).fetchone()[0]
    assert filas == 0


def test_tras_el_olvido_no_queda_fantasma_en_el_indice(memoria, tmp_path):
    """Los disparadores de FTS5 deben limpiar el índice, no sólo la tabla."""
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"),
                             audit_path=str(tmp_path / "auditoria.log"))
    registro.subject_forget("seguidor_1")

    motor = FTS5MemoryEngine(db_path=str(tmp_path / "yuki.db"))
    resultados = motor.search(query="música", limit=10)

    assert all("dejó la música" not in r.get("content", "") for r in resultados)


def test_el_olvido_no_toca_a_los_demas_ni_al_canon(memoria, tmp_path):
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"),
                             audit_path=str(tmp_path / "auditoria.log"))
    registro.subject_forget("seguidor_1")

    assert registro.subject_export("seguidor_2")["recuerdos_total"] == 1
    with sqlite3.connect(tmp_path / "yuki.db") as conexion:
        canon = conexion.execute("SELECT COUNT(*) FROM memories WHERE user_id = 'general'").fetchone()[0]
    assert canon == 1


def test_no_se_puede_vaciarle_la_cabeza_por_esta_puerta(memoria, tmp_path):
    """'general' es su memoria no atribuida: canon, síntesis y pensamientos."""
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"))

    for identificador in ("general", "", "yuki_internal"):
        with pytest.raises(ValueError, match="no designa a una persona"):
            registro.subject_forget(identificador)


def test_el_olvido_deja_constancia_sin_conservar_lo_olvidado(memoria, tmp_path):
    ruta_auditoria = tmp_path / "auditoria.log"
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"), audit_path=str(ruta_auditoria))

    registro.subject_forget("seguidor_1", actor="Productor", reason="ejercicio de supresión")

    contenido = ruta_auditoria.read_text(encoding="utf-8")
    assert "seguidor_1" in contenido and "ejercicio de supresión" in contenido
    assert "dejó la música" not in contenido, "el registro no puede guardar lo que se borró"
    entradas = registro.audit_log()
    assert entradas[-1]["op"] == "olvido" and entradas[-1]["recuerdos_borrados"] == 2


def test_tambien_se_borra_el_registro_de_haberle_declarado(memoria, tmp_path, monkeypatch):
    ruta = tmp_path / "transparency.json"
    ruta.write_text(json.dumps({"declaraciones": {
        "direct_message:seguidor_1": {"at": 1, "iso": "x"},
        "direct_message:seguidor_2": {"at": 1, "iso": "x"},
    }}), encoding="utf-8")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "yuki.db"))
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"),
                             audit_path=str(tmp_path / "auditoria.log"))

    recibo = registro.subject_forget("seguidor_1")

    quedan = json.loads(ruta.read_text(encoding="utf-8"))["declaraciones"]
    assert recibo["declaraciones_borradas"] == 1
    assert list(quedan) == ["direct_message:seguidor_2"]
