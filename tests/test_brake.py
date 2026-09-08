"""
Pruebas del freno de mano.

Un freno es un mecanismo de seguridad, así que lo que se prueba es lo que se
espera de uno: que pare de verdad, que sea graduado, que no se suelte solo, que
diga por qué frena —un freno mudo parece una avería— y que **frenar no sea
enmudecer**: Yuki sigue respondiendo a quien le hable en todos los niveles.
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.brake import MEDIOS, NINGUNO, PUBLICACION, TODO, Brake  # noqa: E402


@pytest.fixture
def freno(tmp_path):
    return Brake(path=str(tmp_path / "freno.json"))


# --- Gradación ---

def test_sin_freno_todo_pasa(freno):
    assert freno.permits("publicar") and freno.permits("medios") and freno.permits("iniciativa")
    assert not freno.state().activo


def test_cada_nivel_contiene_al_anterior(freno):
    freno.engage(PUBLICACION)
    assert not freno.permits("publicar")
    assert freno.permits("medios") and freno.permits("iniciativa")

    freno.engage(MEDIOS)
    assert not freno.permits("publicar") and not freno.permits("medios")
    assert freno.permits("iniciativa")

    freno.engage(TODO)
    assert not any(freno.permits(a) for a in ("publicar", "medios", "iniciativa"))


def test_frenar_no_es_enmudecer(freno):
    """
    En ningún nivel se frena responder a quien habla.

    El freno tiene tres acciones y ninguna es «conversar»: enmudecerla no es
    frenarla, es romperla, y quien pulsa el freno en un incidente no quiere
    quedarse además sin poder preguntarle qué pasó.
    """
    freno.engage(TODO, motivo="incidente")

    assert freno.permits("conversar"), "una acción no reconocida nunca se frena"
    assert freno.blocked_reason("conversar") is None


def test_un_nivel_inventado_se_rechaza(freno):
    with pytest.raises(ValueError, match="no válido"):
        freno.engage("apocalipsis")


# --- Explicación ---

def test_el_freno_dice_por_que(freno):
    """Un freno mudo parece una avería, y se busca durante media hora."""
    freno.engage(MEDIOS, motivo="factura disparada", actor="Dextrure")

    razon = freno.blocked_reason("medios")

    assert "medios" in razon and "factura disparada" in razon and "Dextrure" in razon


def test_lo_que_no_frena_no_da_explicacion(freno):
    freno.engage(PUBLICACION)

    assert freno.blocked_reason("iniciativa") is None


# --- Caducidad ---

def test_un_freno_con_caducidad_se_suelta_solo(freno):
    freno.engage(MEDIOS, minutos=30)
    datos = json.loads(freno.path.read_text(encoding="utf-8"))
    datos["hasta"] = time.time() - 60
    freno.path.write_text(json.dumps(datos), encoding="utf-8")

    assert not freno.state().activo


def test_sin_caducidad_se_queda_puesto(freno):
    """Un freno que se olvida es peor que no tenerlo: enseña a confiar en él."""
    freno.engage(TODO, motivo="hasta que lo miremos")
    datos = json.loads(freno.path.read_text(encoding="utf-8"))

    assert datos["hasta"] is None
    assert freno.state().activo


# --- La palanca del operador ---

def test_el_entorno_manda_sobre_el_fichero(freno, monkeypatch):
    """En un incidente, la palanca más rápida no puede quedar por debajo."""
    freno.engage(PUBLICACION, actor="productor")
    monkeypatch.setenv("YUKI_FRENO", "todo")

    estado = freno.state()

    assert estado.nivel == TODO and estado.origen == "entorno"


def test_soltar_el_fichero_no_suelta_el_entorno(freno, monkeypatch):
    monkeypatch.setenv("YUKI_FRENO", "medios")
    freno.engage(TODO)

    estado = freno.release(actor="productor")

    assert estado.activo and estado.nivel == MEDIOS and estado.origen == "entorno"


def test_manda_el_mas_restrictivo_de_los_dos(freno, monkeypatch):
    monkeypatch.setenv("YUKI_FRENO", "publicacion")
    freno.engage(TODO, actor="productor")

    assert freno.state().nivel == TODO


def test_un_valor_de_entorno_absurdo_se_ignora(freno, monkeypatch, caplog):
    import logging

    monkeypatch.setenv("YUKI_FRENO", "quizás")

    with caplog.at_level(logging.WARNING):
        estado = freno.state()

    assert estado.nivel == NINGUNO
    assert any("no es un nivel" in r.getMessage() for r in caplog.records)


def test_las_formas_sueltas_de_decir_si_valen(freno, monkeypatch):
    for crudo in ("1", "si", "sí", "on", "true"):
        monkeypatch.setenv("YUKI_FRENO", crudo)
        assert freno.state().nivel == TODO, crudo


# --- Prudencia ---

def test_un_freno_ilegible_se_asume_puesto(freno):
    """Ante la duda se frena: soltarlo por un fichero corrupto sería lo peor."""
    freno.path.write_text("{ roto", encoding="utf-8")

    estado = freno.state()

    assert estado.nivel == TODO
    assert "ilegible" in estado.motivo


def test_poner_y_soltar_quedan_en_la_bitacora(tmp_path):
    from src.core.blackbox import BlackBox

    caja = BlackBox(path=str(tmp_path / "bitacora.jsonl"))
    freno = Brake(path=str(tmp_path / "freno.json"), blackbox=caja)

    freno.engage(MEDIOS, motivo="prueba", actor="Dextrure")
    freno.release(actor="Dextrure")

    operaciones = [e.op for e in caja.entries()]
    assert operaciones == ["freno_puesto", "freno_soltado"]
    assert caja.verify()["integra"]


# --- Efecto real sobre los caminos que gastan ---

def test_el_freno_para_la_iniciativa_antes_que_nada(tmp_path):
    import random

    from src.core.agency import AgencyLedger, AgencyPolicy
    from src.core.spark import AgencyLoop, Impulse, WillQueue

    freno = Brake(path=str(tmp_path / "freno.json"))
    freno.engage(TODO, motivo="incidente")

    class EstadoVital:
        energy = 0.9

        def has_energy_for(self, coste):
            return True

    cola = WillQueue()
    cola.add(Impulse("s", "quiero escribir", "write", 0.95, time.time(), 5.0))
    bucle = AgencyLoop(cola, EstadoVital(), policy=AgencyPolicy(),
                       ledger=AgencyLedger(path=str(tmp_path / "agencia.json")),
                       rng=random.Random(1), brake=freno)

    assert bucle.evaluate() is None


def test_el_freno_detiene_los_medios_antes_de_reservar_presupuesto(tmp_path):
    """
    Antes que el presupuesto, porque responde a otra pregunta: el presupuesto
    dice «hoy ya no»; el freno dice «ahora no, y lo ha decidido una persona».
    """
    import asyncio

    from src.core.spend_budget import VIDEO_SEGUNDOS, SpendLedger
    from src.tools.vertex_media import VertexMediaClient

    freno = Brake(path=str(tmp_path / "freno.json"))
    freno.engage(MEDIOS, motivo="factura")
    libro = SpendLedger(path=str(tmp_path / "gasto.json"), limits={VIDEO_SEGUNDOS: 100})
    motor = VertexMediaClient(project_id="yuki-diva", budget=libro, brake=freno,
                              video_dir=str(tmp_path))

    resultado = asyncio.run(motor.generate_video("muelle", duration_seconds=8))

    assert resultado["status"] == "error" and resultado.get("braked") is True
    assert libro.today().get(VIDEO_SEGUNDOS, 0) == 0, "no reservó nada"
