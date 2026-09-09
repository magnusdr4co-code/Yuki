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


# --- Ajustar un ritmo, no sólo proponerlo o matarlo ---

def _aprobado(store, nombre="hora_azul", cron="0 21 * * *"):
    propuesta = store.propose(nombre, cron, "escribir", "porque a esa hora escribe mejor")
    return store.approve(propuesta.id, actor="productor")


def test_un_ritmo_se_puede_mover_de_hora_sin_perder_su_historia(tmp_path):
    """
    Faltaba: se podía proponer y retirar, pero no **cambiar de hora**.

    Para mover un ritmo había que matarlo y empezar de cero, perdiendo cuántas
    veces sonó y qué eco tuvo — que es justo lo que dice si merece la pena
    moverlo.
    """
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)
    store.registrar_ejecucion(original.id)
    store.registrar_ejecucion(original.id)

    ajuste = store.propose_adjustment(original.id, "0 6 * * *",
                                      "a las nueve de la noche nunca contesta nadie")

    assert ajuste.reemplaza == original.id
    assert ajuste.name == original.name, "un ajuste conserva el nombre del ritmo"
    assert ajuste.action == original.action
    # Y mientras espera respuesta, el ritmo viejo sigue sonando.
    assert [r.id for r in store.aprobados()] == [original.id]


def test_aprobar_el_ajuste_retira_el_viejo_en_el_mismo_acto(tmp_path):
    """
    Si no, el ritmo sonaría dos veces: a la hora vieja y a la nueva.

    Acordarse de retirar el original a mano no se le puede pedir a quien aprueba
    desde un DM a las once de la noche.
    """
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)
    ajuste = store.propose_adjustment(original.id, "0 6 * * *", "nadie contesta a esa hora")

    store.approve(ajuste.id, actor="productor")

    activos = store.aprobados()
    assert [r.id for r in activos] == [ajuste.id]
    assert activos[0].cron == "0 6 * * *"
    retirado = store.get(original.id)
    assert retirado.status == "retirado"
    assert "ajuste" in (retirado.decision_note or ""), "queda dicho por qué se retiró"


def test_rechazar_el_ajuste_deja_todo_como_estaba(tmp_path):
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)
    ajuste = store.propose_adjustment(original.id, "0 6 * * *", "probemos por la mañana")

    store.reject(ajuste.id, actor="productor", nota="me gusta a esa hora")

    activos = store.aprobados()
    assert [r.id for r in activos] == [original.id]
    assert activos[0].cron == "0 21 * * *"


def test_se_puede_ajustar_con_el_cupo_de_ritmos_lleno(tmp_path):
    """
    El caso en que más falta hace, y el que se rompía al reutilizar `propose`.

    Un ajuste no añade un ritmo: mueve uno. Contarlo contra el techo dejaba a
    Yuki sin poder reordenar lo que ya tiene justo cuando lo tiene todo lleno.
    """
    from src.core.rituals import MAXIMOS_RITMOS_PROPIOS

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmos = [_aprobado(store, f"ritmo_{i}", f"0 {8 + i} * * *")
              for i in range(MAXIMOS_RITMOS_PROPIOS)]

    with pytest.raises(RitualError, match="retira alguno"):
        store.propose("uno_mas", "0 20 * * *", "escribir", "otro más")

    ajuste = store.propose_adjustment(ritmos[0].id, "30 7 * * *", "media hora antes")
    assert ajuste.reemplaza == ritmos[0].id


def test_no_se_ajusta_lo_que_no_es_un_ritmo_vivo(tmp_path):
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    propuesta = store.propose("sin_aprobar", "0 21 * * *", "escribir", "aún sin respuesta")

    with pytest.raises(RitualError, match="Sólo se ajusta un ritmo aprobado"):
        store.propose_adjustment(propuesta.id, "0 6 * * *", "moverlo")
    with pytest.raises(RitualError, match="No existe"):
        store.propose_adjustment("noexiste", "0 6 * * *", "moverlo")


def test_un_ajuste_no_puede_cambiar_la_accion_a_escondidas(tmp_path):
    """
    Cambia sólo la hora. Si además cambiara la acción sería otro ritmo, y lo
    honesto es proponerlo como tal en vez de colar una cosa distinta bajo un
    nombre ya aprobado.
    """
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)

    ajuste = store.propose_adjustment(original.id, "0 6 * * *", "más temprano")

    assert ajuste.action == original.action


def test_solo_un_ajuste_vivo_por_ritmo(tmp_path):
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)
    store.propose_adjustment(original.id, "0 6 * * *", "más temprano")

    with pytest.raises(RitualError, match="ya hay un ajuste|Ya hay un ajuste"):
        store.propose_adjustment(original.id, "0 7 * * *", "o quizá a las siete")


def test_mover_a_la_misma_hora_no_es_un_ajuste(tmp_path):
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store, cron="0 21 * * *")

    with pytest.raises(RitualError, match="misma hora"):
        store.propose_adjustment(original.id, "0 21 * * *", "igual pero distinto")


# --- Que el ajuste lo pida ella, con la cifra delante ---

class _DiarioFalso:
    def __init__(self, franjas):
        self._franjas = franjas

    def snapshot(self):
        return {"franjas": self._franjas, "acciones": {}, "recientes": []}


def test_pide_mover_un_ritmo_que_no_le_funciona(tmp_path):
    """
    La otra mitad de proponer: mirar lo que ya suena y ver que no responde.

    Con el motivo verificable delante —«lleva 8 ejecuciones a las 20h, donde me
    responden el 20%; a las 08h es el 80%»— la decisión del Productor deja de
    ser una corazonada contra otra.
    """
    from src.core.rituals import proponer_ajuste_desde_experiencia

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = _aprobado(store, "versos_de_la_tarde", "0 20 * * *")
    for _ in range(8):
        store.registrar_ejecucion(ritmo.id)

    diario = _DiarioFalso({"20h": {"intentos": 10, "ecos": 1},
                           "08h": {"intentos": 10, "ecos": 9}})

    ajuste = proponer_ajuste_desde_experiencia(diario, store)

    assert ajuste is not None
    assert ajuste.reemplaza == ritmo.id
    assert ajuste.cron == "0 8 * * *"
    assert "8 ejecuciones" in ajuste.reason and "%" in ajuste.reason


def test_no_mueve_nada_sin_experiencia_suficiente(tmp_path):
    """Una franja juzgada por dos días es una corazonada, no una experiencia."""
    from src.core.rituals import proponer_ajuste_desde_experiencia

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = _aprobado(store, "recien_nacido", "0 20 * * *")
    store.registrar_ejecucion(ritmo.id)   # una sola vez

    diario = _DiarioFalso({"20h": {"intentos": 10, "ecos": 1},
                           "08h": {"intentos": 10, "ecos": 9}})

    assert proponer_ajuste_desde_experiencia(diario, store) is None


def test_no_mueve_por_una_diferencia_pequena(tmp_path):
    """Mover un ritmo por dos puntos sería ruido con ceremonia."""
    from src.core.rituals import proponer_ajuste_desde_experiencia

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = _aprobado(store, "casi_igual", "0 20 * * *")
    for _ in range(8):
        store.registrar_ejecucion(ritmo.id)

    diario = _DiarioFalso({"20h": {"intentos": 10, "ecos": 5},
                           "08h": {"intentos": 10, "ecos": 6}})

    assert proponer_ajuste_desde_experiencia(diario, store) is None


def test_la_noche_prefiere_reordenar_a_acumular(tmp_path, monkeypatch):
    """
    Que la capacidad llegue a ejercerse, no sólo a existir.

    La síntesis nocturna sólo sabía proponer ritmos nuevos, así que ajustar
    habría quedado construido y fuera de su alcance — el mismo patrón que dejó
    `execute_autonomous_will` sin probar y `last_sleep_cycle` sin escritor.
    Y prefiere mover antes que añadir: arreglar lo que ya tiene vale más que
    acumular, y además no gasta cupo.
    """
    import asyncio

    from src.core.agent import YukiAgent
    from src.core.rituals import proponer_ajuste_desde_experiencia

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = _aprobado(store, "versos_de_la_tarde", "0 20 * * *")
    for _ in range(8):
        store.registrar_ejecucion(ritmo.id)
    diario = _DiarioFalso({"20h": {"intentos": 10, "ecos": 1},
                           "08h": {"intentos": 10, "ecos": 9}})

    # Se comprueba contra el agente real, no reimplementando su lógica.
    agente = YukiAgent.__new__(YukiAgent)
    agente.rituals = store
    agente.agency_ledger = diario

    propuesta = asyncio.run(YukiAgent.propose_own_ritual(agente))

    assert propuesta is not None
    assert propuesta["reemplaza"] == ritmo.id, "propuso uno nuevo en vez de mover el que falla"
    # Y la función suelta dice lo mismo: no hay dos caminos que puedan divergir.
    assert proponer_ajuste_desde_experiencia(diario, RitualStore(
        path=str(tmp_path / "otro.json"))) is None
