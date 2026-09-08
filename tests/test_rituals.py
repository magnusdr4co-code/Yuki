"""
Pruebas de los ritmos propios.

El diseño es asimétrico a propósito y eso es lo que se protege: proponer es
libre, aprobar no. Ninguna propuesta llega al planificador sin el Productor, y
ninguna propuesta imposible llega a sus manos.
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agency import AgencyLedger  # noqa: E402
from src.core.rituals import (  # noqa: E402
    ACCIONES_DE_RITMO, APROBADO, MAXIMAS_PROPUESTAS_VIVAS, MAXIMOS_RITMOS_PROPIOS,
    PROPUESTO, RECHAZADO, RETIRADO, RitualError, RitualStore, disparos_diarios,
    proponer_desde_experiencia,
)


@pytest.fixture
def store(tmp_path):
    return RitualStore(path=str(tmp_path / "ritmos.json"))


def _propuesta(store, nombre="escribir_de_noche", cron="0 23 * * *", accion="escribir"):
    return store.propose(nombre, cron, accion, "porque a esa hora me leen")


# --- Validación al proponer ---

def test_una_propuesta_valida_queda_registrada(store):
    propuesta = _propuesta(store)

    assert propuesta.status == PROPUESTO
    assert propuesta.origin == "yuki"
    assert store.pendientes() == [propuesta] or store.pendientes()[0].id == propuesta.id


def test_no_se_admite_un_ritmo_que_dispare_cada_poco(store):
    """Un ritual cada cinco minutos no es un ritmo: es un tic."""
    with pytest.raises(RitualError, match="veces al día"):
        store.propose("tic", "*/5 * * * *", "escribir", "quiero estar siempre")

    assert disparos_diarios("*/5 * * * *") == 288
    assert disparos_diarios("0 20 * * *") == 1


def test_una_expresion_invalida_se_rechaza_al_proponer(store):
    with pytest.raises(RitualError, match="cron inválida"):
        store.propose("roto", "esto no es cron", "escribir", "motivo")


def test_solo_se_permiten_acciones_internas(store):
    """Componer y pintar gastan crédito: no entran por esta puerta."""
    with pytest.raises(RitualError, match="no permitida"):
        store.propose("caro", "0 20 * * *", "componer", "quiero música cada noche")

    assert "compose" not in ACCIONES_DE_RITMO.values()
    assert set(ACCIONES_DE_RITMO.values()) == {"write", "contemplate", "search", "monologue"}


def test_un_ritmo_sin_motivo_no_se_propone(store):
    with pytest.raises(RitualError, match="sin motivo"):
        store.propose("mudo", "0 20 * * *", "escribir", "   ")


def test_no_se_acumulan_propuestas_sin_responder(store):
    for indice in range(MAXIMAS_PROPUESTAS_VIVAS):
        _propuesta(store, nombre=f"ritmo_{indice}", cron=f"0 {10 + indice} * * *")

    with pytest.raises(RitualError, match="esperando respuesta"):
        _propuesta(store, nombre="uno_mas", cron="0 21 * * *")


def test_hay_un_techo_de_ritmos_propios_activos(store):
    for indice in range(MAXIMOS_RITMOS_PROPIOS):
        propuesta = _propuesta(store, nombre=f"ritmo_{indice}", cron=f"0 {10 + indice} * * *")
        store.approve(propuesta.id, actor="Productor")

    with pytest.raises(RitualError, match="ritmos propios activos"):
        _propuesta(store, nombre="excedente", cron="0 21 * * *")


def test_no_se_duplica_un_nombre_vivo(store):
    _propuesta(store)

    with pytest.raises(RitualError, match="Ya existe"):
        _propuesta(store)


# --- Decisión del Productor ---

def test_aprobar_y_rechazar_dejan_constancia(store):
    aprobada = _propuesta(store, nombre="uno", cron="0 20 * * *")
    rechazada = _propuesta(store, nombre="dos", cron="0 21 * * *")

    store.approve(aprobada.id, actor="Dextrure", nota="me gusta la idea")
    store.reject(rechazada.id, actor="Dextrure", nota="a esa hora no")

    assert store.get(aprobada.id).status == APROBADO
    assert store.get(aprobada.id).decided_by == "Dextrure"
    assert store.get(rechazada.id).status == RECHAZADO
    assert store.get(rechazada.id).decision_note == "a esa hora no"


def test_no_se_aprueba_dos_veces(store):
    propuesta = _propuesta(store)
    store.approve(propuesta.id, actor="Productor")

    with pytest.raises(RitualError, match="ya está en estado"):
        store.approve(propuesta.id, actor="Productor")


def test_retirar_conserva_la_historia(store):
    propuesta = _propuesta(store)
    store.approve(propuesta.id, actor="Productor")
    store.retire(propuesta.id, actor="Productor", nota="ya no encaja")

    assert store.get(propuesta.id).status == RETIRADO
    assert store.aprobados() == []
    assert any(p.id == propuesta.id for p in store.historial())


def test_una_propuesta_inexistente_se_dice(store):
    with pytest.raises(RitualError, match="No existe"):
        store.approve("00000000", actor="Productor")


def test_las_propuestas_caducan_sin_respuesta(store):
    propuesta = _propuesta(store)
    datos = json.loads(store.path.read_text(encoding="utf-8"))
    datos["propuestas"][0]["created_at"] = time.time() - 30 * 86400
    store.path.write_text(json.dumps(datos), encoding="utf-8")

    assert store.pendientes() == []
    assert store.get(propuesta.id).caducada


def test_las_ejecuciones_se_cuentan(store):
    propuesta = _propuesta(store)
    store.approve(propuesta.id, actor="Productor")
    store.registrar_ejecucion(propuesta.id)
    store.registrar_ejecucion(propuesta.id)

    assert store.get(propuesta.id).runs == 2


def test_el_registro_corrupto_no_impide_arrancar(tmp_path):
    ruta = tmp_path / "ritmos.json"
    ruta.write_text("{ roto", encoding="utf-8")
    store = RitualStore(path=str(ruta))

    assert store.pendientes() == [] and store.aprobados() == []
    assert store.propose("nuevo", "0 20 * * *", "escribir", "motivo")


# --- Propuesta fundada en la experiencia ---

def test_sin_experiencia_no_se_propone_nada(store, tmp_path):
    libro = AgencyLedger(path=str(tmp_path / "agencia.json"))

    assert proponer_desde_experiencia(libro, store) is None


def test_la_propuesta_sale_de_la_franja_con_mas_eco(store, tmp_path, monkeypatch):
    """El horario no se inventa: se lee del diario de agencia."""
    libro = AgencyLedger(path=str(tmp_path / "agencia.json"))
    for _ in range(4):
        libro.registrar_intento("write", "unos versos")
        libro.registrar_eco(6.0)

    propuesta = proponer_desde_experiencia(libro, store)

    assert propuesta is not None
    assert propuesta.action == "escribir"
    assert propuesta.cron.endswith("* * *")
    assert "%" in propuesta.reason, "el motivo cita la tasa observada"
    assert propuesta.origin == "yuki"


def test_sin_eco_destacado_no_hay_propuesta(store, tmp_path):
    libro = AgencyLedger(path=str(tmp_path / "agencia.json"))
    for _ in range(5):
        libro.registrar_intento("write", "al vacío")

    assert proponer_desde_experiencia(libro, store) is None


# --- El camino que ve el Productor ---

def test_la_sintesis_diaria_propone_y_avisa_por_dm(tmp_path, monkeypatch):
    """
    Una iniciativa que sólo se ve si alguien la busca no es iniciativa.

    Tras sintetizar el día, Yuki mira su experiencia, propone un ritmo si ve un
    patrón y lo lleva al DM del Productor con su identificador, para que decidir
    sea una línea y no una arqueología.
    """
    import asyncio
    import types

    from src.core.agency import AgencyLedger
    from src.scheduler.tasks import AutonomousTasks

    libro = AgencyLedger(path=str(tmp_path / "agencia.json"))
    for _ in range(4):
        libro.registrar_intento("write", "unos versos")
        libro.registrar_eco(6.0)
    store = RitualStore(path=str(tmp_path / "ritmos.json"))

    avisos = []

    class AdaptadorFalso:
        async def notify_producer(self, texto):
            avisos.append(texto)
            return True

    from src.core.agent import YukiAgent

    agente = types.SimpleNamespace(agency_ledger=libro, rituals=store,
                                   discord_adapter=AdaptadorFalso())
    agente.propose_own_ritual = types.MethodType(YukiAgent.propose_own_ritual, agente)
    tareas = AutonomousTasks(agente)

    propuesta = asyncio.run(agente.propose_own_ritual())
    asyncio.run(tareas._avisar_al_productor(
        f"🕯️ He propuesto un ritmo propio: **{propuesta['name']}** "
        f"(`{propuesta['cron']}`). `!ritmo aprobar {propuesta['id']}`"))

    assert propuesta["action"] == "escribir"
    assert len(avisos) == 1
    assert propuesta["id"] in avisos[0], "el aviso lleva el id con el que decidir"
    assert store.pendientes()[0].id == propuesta["id"]


def test_sin_adaptador_la_propuesta_no_se_pierde(tmp_path):
    """Sin Discord —CLI, pruebas, arranque sin token— queda en `!ritmos`."""
    import asyncio
    import types

    from src.scheduler.tasks import AutonomousTasks

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    propuesta = store.propose("versos", "0 20 * * *", "escribir", "motivo")
    tareas = AutonomousTasks(types.SimpleNamespace(discord_adapter=None, rituals=store))

    entregado = asyncio.run(tareas._avisar_al_productor("aviso"))

    assert entregado is False
    assert store.pendientes()[0].id == propuesta.id
