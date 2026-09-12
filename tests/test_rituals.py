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
    ACCIONES_DE_RITMO, APROBADO, MAXIMOS_RITMOS_PROPIOS,
    PROPUESTO, RETIRADO, RitualError, RitualStore, disparos_diarios,
    proponer_desde_experiencia,
)


@pytest.fixture
def store(tmp_path):
    return RitualStore(path=str(tmp_path / "ritmos.json"))


def _propuesta(store, nombre="escribir_de_noche", cron="0 23 * * *", accion="escribir"):
    return store.propose(nombre, cron, accion, "porque a esa hora me leen")


# --- Validación al proponer ---

def test_un_ritmo_adoptado_nace_activo(store):
    """
    Había un trámite de aprobación y se ha quitado: decidir a qué hora escribe
    no es concederse un permiso. La seguridad la dan los límites de abajo, no el
    visto bueno de nadie.
    """
    ritmo = _propuesta(store)

    assert ritmo.status == APROBADO
    assert ritmo.origin == "yuki"
    assert [r.id for r in store.aprobados()] == [ritmo.id]
    assert store.pendientes() == [], "ya no hay cola de espera"


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


def test_ya_no_hay_cola_de_espera_pero_si_techo_de_ritmos(store):
    """
    El cupo de «propuestas esperando respuesta» no gobierna nada cuando nadie
    tiene que responder. El que sigue vivo es el de ritmos activos: un
    calendario que se llena solo deja de ser un ritmo.
    """
    for indice in range(MAXIMOS_RITMOS_PROPIOS):
        _propuesta(store, nombre=f"ritmo_{indice}", cron=f"0 {10 + indice} * * *")

    with pytest.raises(RitualError, match="ritmos propios activos"):
        _propuesta(store, nombre="uno_mas", cron="0 21 * * *")


def test_hay_un_techo_de_ritmos_propios_activos(store):
    for indice in range(MAXIMOS_RITMOS_PROPIOS):
        _propuesta(store, nombre=f"ritmo_{indice}", cron=f"0 {10 + indice} * * *")

    with pytest.raises(RitualError, match="ritmos propios activos"):
        _propuesta(store, nombre="excedente", cron="0 21 * * *")


def test_no_se_duplica_un_nombre_vivo(store):
    _propuesta(store)

    with pytest.raises(RitualError, match="Ya existe"):
        _propuesta(store)


# --- Veto del Productor: lo que le queda, y es lo que le corresponde ---

def test_el_productor_veta_retirando_no_aprobando(store):
    """
    Su papel ya no es dar permiso: es poder quitar lo que no quiera. Retirar deja
    constancia de quién y por qué, igual que antes lo dejaba aprobar.
    """
    ritmo = _propuesta(store, nombre="uno", cron="0 20 * * *")

    store.retire(ritmo.id, actor="Dextrure", nota="a esa hora no")

    assert store.get(ritmo.id).status == RETIRADO
    assert store.get(ritmo.id).decided_by == "Dextrure"
    assert store.get(ritmo.id).decision_note == "a esa hora no"
    assert store.aprobados() == []


def test_un_ritmo_ya_adoptado_no_se_adopta_dos_veces(store):
    """Activar lo que ya está activo no es un no-op silencioso: se dice."""
    ritmo = _propuesta(store)

    with pytest.raises(RitualError, match="ya está en estado"):
        store.activar(ritmo.id)


def test_una_propuesta_de_antes_del_cambio_se_puede_activar(store):
    """
    Las que quedaron esperando un visto bueno que ya no se pide no pueden
    quedarse atrapadas en un trámite retirado.
    """
    ritmo = _propuesta(store, nombre="heredado", cron="0 3 * * *")
    # Se fuerza al estado en que quedaron las de antes del cambio.
    pendiente = store.get(ritmo.id)
    pendiente.status = PROPUESTO
    pendiente.decided_at = None
    pendiente.decided_by = None
    store._guardar([pendiente])

    activado = store.activar(ritmo.id)

    assert activado.status == APROBADO
    assert [r.id for r in store.aprobados()] == [ritmo.id]


def test_retirar_conserva_la_historia(store):
    propuesta = _propuesta(store)
    store.retire(propuesta.id, actor="Productor", nota="ya no encaja")

    assert store.get(propuesta.id).status == RETIRADO
    assert store.aprobados() == []
    assert any(p.id == propuesta.id for p in store.historial())


def test_un_ritmo_inexistente_se_dice(store):
    with pytest.raises(RitualError, match="No existe"):
        store.retire("00000000", actor="Productor")


def test_una_pendiente_heredada_caduca_y_no_revive(store):
    """
    Ya no se crean pendientes, pero las de antes del cambio siguen en disco. Una
    de hace un mes no puede activarse sola al arrancar: caducó sin que nadie la
    atendiera y eso es lo que queda dicho.
    """
    propuesta = _propuesta(store)
    datos = json.loads(store.path.read_text(encoding="utf-8"))
    datos["propuestas"][0]["status"] = "propuesto"
    datos["propuestas"][0]["created_at"] = time.time() - 30 * 86400
    store.path.write_text(json.dumps(datos), encoding="utf-8")

    assert store.pendientes() == []
    assert store.get(propuesta.id).caducada
    assert store.aprobados() == []


def test_las_ejecuciones_se_cuentan(store):
    propuesta = _propuesta(store)
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

def test_la_sintesis_diaria_adopta_y_avisa_por_dm(tmp_path, monkeypatch):
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
    assert propuesta["id"] in avisos[0], "el aviso lleva el id con el que retirarlo si estorba"
    assert [r.id for r in store.aprobados()] == [propuesta["id"]], \
        "el ritmo queda activo, no esperando permiso"


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
    # Sin Discord el aviso no sale, pero el ritmo sigue activo: que nadie lo lea
    # no puede deshacer una decisión que ya no necesita lector.
    assert [r.id for r in store.aprobados()] == [propuesta.id]


# --- Ajustar un ritmo, no sólo proponerlo o matarlo ---

def _aprobado(store, nombre="hora_azul", cron="0 21 * * *"):
    """Un ritmo activo. Nace así: ya no hay trámite que atravesar."""
    return store.propose(nombre, cron, "escribir", "porque a esa hora escribe mejor")


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
    # El ajuste se aplica al pedirlo: el viejo ya no suena, y su historia consta.
    assert [r.id for r in store.aprobados()] == [ajuste.id]
    assert store.get(original.id).runs == 2, "moverlo no borra cuántas veces sonó"


def test_mover_un_ritmo_retira_el_viejo_en_el_mismo_acto(tmp_path):
    """
    Si no, el ritmo sonaría dos veces: a la hora vieja y a la nueva. Y ése es el
    fallo que nadie ve hasta oírlo dos veces.
    """
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)
    ajuste = store.propose_adjustment(original.id, "0 6 * * *", "nadie contesta a esa hora")

    activos = store.aprobados()
    assert [r.id for r in activos] == [ajuste.id]
    assert activos[0].cron == "0 6 * * *"
    retirado = store.get(original.id)
    assert retirado.status == "retirado"
    assert "ajuste" in (retirado.decision_note or ""), "queda dicho por qué se retiró"


def test_el_productor_puede_deshacer_un_movimiento_retirandolo(tmp_path):
    """
    Ya no hay «rechazar el ajuste» porque no hay ajuste esperando. Lo que le
    queda es el veto: retirar el ritmo que no quiera, aunque sea el nuevo.
    """
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)
    ajuste = store.propose_adjustment(original.id, "0 6 * * *", "probemos por la mañana")

    store.retire(ajuste.id, actor="productor", nota="me gustaba a esa hora")

    assert store.aprobados() == [], "retirado el movido, no vuelve solo el viejo"
    assert store.get(original.id).status == "retirado"


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
    """Mover un ritmo retirado no es moverlo: es resucitarlo por la puerta de atrás."""
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    retirado = _aprobado(store, "ya_no", "0 21 * * *")
    store.retire(retirado.id, actor="productor")

    with pytest.raises(RitualError, match="Sólo se ajusta un ritmo aprobado"):
        store.propose_adjustment(retirado.id, "0 6 * * *", "moverlo")
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


def test_mover_dos_veces_seguidas_no_deja_ritmos_de_sobra(tmp_path):
    """
    Ya no hay «un ajuste vivo por ritmo» porque no hay ajustes esperando: cada
    movimiento se aplica y retira el anterior. Lo que importa es que moverlo dos
    veces deje **uno** activo, no tres.
    """
    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    original = _aprobado(store)

    primero = store.propose_adjustment(original.id, "0 6 * * *", "más temprano")
    segundo = store.propose_adjustment(primero.id, "0 7 * * *", "o quizá a las siete")

    activos = store.aprobados()
    assert [r.id for r in activos] == [segundo.id]
    assert activos[0].cron == "0 7 * * *"


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
