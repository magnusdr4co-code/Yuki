"""
Pruebas del libre albedrío: política, refuerzo y espontaneidad.

Lo que se protege no es que Yuki actúe, sino *cómo* decide: que el carácter sea
configurable de verdad, que la misma situación no produzca siempre la misma
decisión, que lo que obtuvo respuesta pese más la próxima vez y que los límites
—acciones por día, tipos permitidos, fases de silencio— no se puedan saltar.
"""

import os
import random
import sys
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agency import (  # noqa: E402
    ACCIONES, AgencyLedger, AgencyPolicy, ReinforcementModel,
)
from src.core.spark import AgencyLoop, Impulse, WillQueue  # noqa: E402


@pytest.fixture
def libro(tmp_path):
    return AgencyLedger(path=str(tmp_path / "agencia.json"))


def _estado(energy=0.9):
    estado = MagicMock()
    estado.energy = energy
    estado.inspiration = 0.6
    estado.curiosity = 0.6
    estado.has_energy_for.return_value = True
    return estado


def _bucle(libro, politica=None, semilla=7, estado=None):
    politica = politica or AgencyPolicy()
    cola = WillQueue()
    return AgencyLoop(cola, estado or _estado(), policy=politica, ledger=libro,
                      rng=random.Random(semilla))


# --- Política configurable ---

def test_el_caracter_se_declara_en_config_y_no_en_el_codigo():
    politica = AgencyPolicy.from_config({"agency": {
        "spontaneity": 0.9, "audacity": 0.8, "max_actions_per_day": 2,
        "allowed_actions": ["write", "contemplate"], "quiet_phases": ["kage", "deep_rest"],
    }})

    assert politica.spontaneity == 0.9
    assert politica.max_actions_per_day == 2
    assert set(politica.allowed_actions) == {"write", "contemplate"}
    assert "kage" in politica.quiet_phases


def test_los_valores_fuera_de_rango_se_acotan_en_vez_de_romper():
    politica = AgencyPolicy.from_config({"agency": {"spontaneity": 5, "audacity": -3}})

    assert politica.spontaneity == 1.0 and politica.audacity == 0.0


def test_una_accion_inventada_en_la_allowlist_se_descarta():
    politica = AgencyPolicy.from_config({"agency": {"allowed_actions": ["write", "hackear"]}})

    assert set(politica.allowed_actions) == {"write"}


def test_el_aburrimiento_rebaja_el_umbral_pero_con_techo():
    politica = AgencyPolicy()

    sin_tension = politica.umbral_efectivo(0.0)
    con_tension = politica.umbral_efectivo(0.35)
    desbordado = politica.umbral_efectivo(10.0)

    assert con_tension < sin_tension
    assert desbordado == con_tension, "el techo impide que el umbral caiga sin fondo"
    assert desbordado >= 0.05


# --- Límites duros ---

def test_la_politica_apagada_deja_a_yuki_sin_iniciativa(libro):
    bucle = _bucle(libro, AgencyPolicy(enabled=False))
    bucle.will_queue.add(Impulse("s", "d", "write", 0.9, time.time(), 5.0))

    assert bucle.evaluate() is None


def test_las_fases_de_silencio_se_respetan(libro):
    bucle = _bucle(libro, AgencyPolicy(quiet_phases=["deep_rest"]))
    bucle.will_queue.add(Impulse("s", "d", "write", 0.9, time.time(), 5.0))

    assert bucle.evaluate(phase="deep_rest") is None
    assert bucle.evaluate(phase="kage") is not None, "la hora de sombra ya no la silencia"


def test_el_techo_diario_sobrevive_al_reinicio(libro, tmp_path):
    politica = AgencyPolicy(max_actions_per_day=2)
    bucle = _bucle(libro, politica)
    for _ in range(2):
        impulso = Impulse("s", "d", "write", 0.9, time.time(), 5.0)
        bucle.will_queue.add(impulso)
        bucle.record_action(impulso, {"status": "ok"})

    # Proceso nuevo, mismo disco: el techo no se reinicia con el daemon.
    otro = _bucle(AgencyLedger(path=str(libro.path)), politica)
    otro.will_queue.add(Impulse("s", "d", "write", 0.9, time.time(), 5.0))

    assert otro.evaluate() is None


def test_una_accion_no_permitida_nunca_se_elige(libro):
    bucle = _bucle(libro, AgencyPolicy(allowed_actions=["contemplate"]))
    bucle.will_queue.add(Impulse("s", "quiero publicar", "publish", 0.95, time.time(), 5.0))

    assert bucle.evaluate() is None


def test_un_tool_hint_desconocido_se_ignora_y_se_registra(libro, caplog):
    import logging

    bucle = _bucle(libro)
    bucle.will_queue.add(Impulse("s", "d", "invocar_demonios", 0.9, time.time(), 5.0))

    with caplog.at_level(logging.WARNING):
        assert bucle.evaluate() is None

    assert any("desconocida" in registro.getMessage() for registro in caplog.records)


def test_sin_energia_no_hay_acto(libro):
    estado = _estado(energy=0.05)
    estado.has_energy_for.return_value = False
    bucle = _bucle(libro, estado=estado)
    bucle.will_queue.add(Impulse("s", "d", "compose", 0.9, time.time(), 5.0))

    assert bucle.evaluate() is None


# --- Espontaneidad ---

def test_la_misma_situacion_no_siempre_da_la_misma_decision(libro):
    """Determinismo era el problema: una tabla de consulta no es albedrío."""
    politica = AgencyPolicy(spontaneity=0.9, exploration=0.2, max_actions_per_day=99)
    elegidos = set()
    for semilla in range(12):
        bucle = _bucle(AgencyLedger(path=str(libro.path)), politica, semilla=semilla)
        for accion in ("write", "paint", "search"):
            bucle.will_queue.add(Impulse("s", accion, accion, 0.8, time.time(), 5.0))
        elegido = bucle.evaluate()
        if elegido:
            elegidos.add(elegido.tool_hint)

    assert len(elegidos) > 1, "con espontaneidad alta debe variar la elección"


def test_con_espontaneidad_minima_manda_la_intensidad(libro):
    politica = AgencyPolicy(spontaneity=0.0, exploration=0.0)
    bucle = _bucle(libro, politica)
    bucle.will_queue.add(Impulse("s", "tibio", "write", 0.35, time.time(), 5.0))
    fuerte = Impulse("s", "urgente", "search", 0.95, time.time(), 5.0)
    bucle.will_queue.add(fuerte)

    assert bucle.evaluate() is fuerte


def test_el_aburrimiento_crece_cuando_no_actua_y_se_reinicia_al_actuar(libro):
    bucle = _bucle(libro, AgencyPolicy(spontaneous_impulses=False))

    for _ in range(3):
        bucle.evaluate()
    acumulado = libro.boredom()

    impulso = Impulse("s", "d", "write", 0.9, time.time(), 5.0)
    bucle.will_queue.add(impulso)
    bucle.record_action(impulso, {"status": "ok"})

    assert acumulado > 0
    assert libro.boredom() == 0.0


def test_sin_impulsos_y_con_tension_nace_un_deseo_propio(libro):
    """La fuente que faltaba: antes sólo nacían impulsos a las 06:30."""
    politica = AgencyPolicy(spontaneous_threshold=0.1, boredom_gain=0.2)
    bucle = _bucle(libro, politica)

    for _ in range(3):
        decision = bucle.evaluate()

    assert decision is not None
    assert decision.source == "espontaneo"
    assert decision.tool_hint in ACCIONES
    assert decision.desire


def test_los_impulsos_espontaneos_se_pueden_desactivar(libro):
    politica = AgencyPolicy(spontaneous_impulses=False, spontaneous_threshold=0.0)
    bucle = _bucle(libro, politica)

    assert bucle.evaluate() is None
    assert bucle.spawn_spontaneous_impulse() is None


# --- Refuerzo ---

def test_lo_que_obtuvo_eco_pesa_mas_la_proxima_vez(libro):
    politica = AgencyPolicy()
    modelo = ReinforcementModel(libro, politica, random.Random(1))

    libro.registrar_intento("write", "unos versos")
    libro.registrar_eco(politica.reward_window_hours)
    libro.registrar_intento("search", "curioseo")
    # Al 'search' no le responde nadie: su ventana caduca sin eco.

    assert modelo.peso("write") > modelo.peso("search")


def test_el_eco_solo_premia_lo_reciente(libro):
    politica = AgencyPolicy(reward_window_hours=1.0)
    libro.registrar_intento("write", "versos de hace mucho")

    datos = libro.snapshot()
    datos["pendientes"][0]["at"] = time.time() - 5 * 3600
    libro._escribir(datos)

    assert libro.registrar_eco(politica.reward_window_hours) == 0


def test_una_interaccion_real_refuerza_lo_hecho_poco_antes(libro):
    bucle = _bucle(libro)
    impulso = Impulse("s", "d", "publish", 0.9, time.time(), 5.0)
    bucle.will_queue.add(impulso)
    bucle.record_action(impulso, {"status": "ok"})

    premiadas = bucle.note_external_signal()

    assert premiadas == 1
    assert bucle.model.peso("publish") > 0.5


def test_el_refuerzo_desactivado_deja_la_eleccion_a_la_intensidad(libro):
    politica = AgencyPolicy(reinforcement_enabled=False)
    bucle = _bucle(libro, politica)
    bucle.will_queue.add(Impulse("s", "tibio", "write", 0.4, time.time(), 5.0))
    fuerte = Impulse("s", "fuerte", "paint", 0.95, time.time(), 5.0)
    bucle.will_queue.add(fuerte)

    assert bucle.evaluate() is fuerte
    assert bucle.note_external_signal() == 0


def test_la_novedad_penaliza_repetirse(libro):
    politica = AgencyPolicy()
    modelo = ReinforcementModel(libro, politica, random.Random(3))
    for _ in range(2):
        libro.registrar_intento("write", "otra vez lo mismo")

    recientes = libro.recientes()

    assert modelo.novedad("write", recientes) < modelo.novedad("paint", recientes)


def test_el_premio_intermitente_no_llega_siempre_ni_nunca(libro):
    modelo = ReinforcementModel(libro, AgencyPolicy(intermittent_ratio=0.3), random.Random(5))

    premios = sum(1 for _ in range(200) if modelo.premio_intermitente())

    assert 0 < premios < 200, "razón variable: ni siempre, ni nunca"
    assert 30 < premios < 90


def test_la_exploracion_rompe_el_bucle_del_propio_acierto(libro):
    """Sin exploración, el refuerzo repetiría su primer acierto para siempre."""
    politica = AgencyPolicy(exploration=1.0)
    modelo = ReinforcementModel(libro, politica, random.Random(11))
    for _ in range(10):
        libro.registrar_intento("write")
        libro.registrar_eco(6.0)

    candidatos = [Impulse("s", "d", "write", 0.9, time.time(), 5.0),
                  Impulse("s", "d", "paint", 0.1, time.time(), 5.0)]
    elegidos = {modelo.elegir(candidatos).tool_hint for _ in range(20)}

    assert elegidos == {"write", "paint"}


# --- Estado observable ---

def test_el_estado_del_albedrio_es_legible(libro):
    bucle = _bucle(libro)
    impulso = Impulse("s", "d", "write", 0.9, time.time(), 5.0)
    bucle.will_queue.add(impulso)
    bucle.record_action(impulso, {"status": "ok"})

    estado = bucle.estado()

    assert estado["acciones_hoy"] == 1
    assert estado["esperando_eco"] == 1
    assert 0 <= estado["umbral_ahora"] <= 1
    assert set(estado["pesos_por_accion"]) == set(bucle.policy.allowed_actions)
    assert estado["politica"]["espontaneidad"] == bucle.policy.spontaneity


def test_el_diario_corrupto_no_impide_actuar(tmp_path):
    ruta = tmp_path / "agencia.json"
    ruta.write_text("{ roto", encoding="utf-8")
    libro = AgencyLedger(path=str(ruta))
    bucle = _bucle(libro)
    bucle.will_queue.add(Impulse("s", "d", "write", 0.9, time.time(), 5.0))

    assert bucle.evaluate() is not None


# --- Ritmos propios en el planificador ---

def _agente_con_ritmos(tmp_path, ritmos, frenada=None, actos_hoy=0, tope=6, albedrio=True):
    """Agente mínimo con lo que un ritmo necesita para cumplirse o no cumplirse."""
    import types

    from src.core.agent import YukiAgent
    from src.scheduler.cron_engine import CronEngine

    ejecutados = []
    agente = types.SimpleNamespace(
        rituals=ritmos,
        cron=CronEngine(),
        execute_autonomous_will=lambda impulso: _completar(ejecutados, impulso),
        tasks=types.SimpleNamespace(spontaneous_monologue=None),
        agency_loop=types.SimpleNamespace(
            brake=types.SimpleNamespace(blocked_reason=lambda ambito: frenada)),
        agency_policy=types.SimpleNamespace(enabled=albedrio, max_actions_per_day=tope),
        agency_ledger=types.SimpleNamespace(acciones_hoy=lambda: actos_hoy),
    )
    for metodo in ("register_own_rituals", "_make_ritual_runner", "puede_cumplir_un_ritmo"):
        setattr(agente, metodo, types.MethodType(getattr(YukiAgent, metodo), agente))
    return agente, ejecutados


def test_un_ritmo_adoptado_llega_al_planificador_y_se_cumple_como_impulso(tmp_path):
    """
    El ciclo completo, ya sin trámite: Yuki adopta y el cron lo ejecuta.

    Un ritmo que sólo existiera en memoria se perdería en el siguiente
    despliegue, y Yuki tendría un calendario que nadie cumple.
    """
    import asyncio

    from src.core.rituals import RitualStore

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = store.propose("versos_de_las_20", "0 20 * * *", "escribir", "a esa hora me responden")
    agente, ejecutados = _agente_con_ritmos(tmp_path, store)

    assert agente.register_own_rituals() == 1, "nace activo: no hay nada que aprobar"
    assert "propio_versos_de_las_20" in agente.cron.jobs
    assert agente.cron.jobs["propio_versos_de_las_20"]["cron_expr"] == "0 20 * * *"

    asyncio.run(agente.cron.jobs["propio_versos_de_las_20"]["func"]())

    assert ejecutados and ejecutados[0].tool_hint == "write"
    assert ejecutados[0].source.startswith("ritmo_propio:")
    assert store.get(ritmo.id).runs == 1


def test_frenar_para_tambien_los_ritmos_propios(tmp_path):
    """
    Esto faltaba, y era el agujero que el trámite de aprobación tapaba sin
    querer: un ritmo iba directo a `execute_autonomous_will`, saltándose el
    `_decidir` del albedrío, así que **sonaba con el freno puesto**. La segunda
    invariante dice que el freno es para la iniciativa; un ritmo es iniciativa.
    """
    import asyncio

    from src.core.rituals import RitualStore

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = store.propose("versos", "0 20 * * *", "escribir", "motivo")
    agente, ejecutados = _agente_con_ritmos(tmp_path, store, frenada="freno de mano en «todo»")
    agente.register_own_rituals()

    resultado = asyncio.run(agente.cron.jobs["propio_versos"]["func"]())

    assert ejecutados == [], "el ritmo no puede cumplirse con el freno puesto"
    assert resultado["status"] == "skipped"
    assert "freno" in resultado["reason"]
    assert store.get(ritmo.id).runs == 0, "un ritmo que no se cumplió no cuenta como cumplido"


def test_adoptar_ritmos_no_amplia_su_techo_de_actos(tmp_path):
    """
    Un ritmo decide **cuándo**, nunca **cuántos**. Si se salta el techo diario,
    adoptar calendario es concederse más iniciativa, que es justo lo que la sexta
    invariante prohíbe. Antes se lo saltaba.
    """
    import asyncio

    from src.core.rituals import RitualStore

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    ritmo = store.propose("versos", "0 20 * * *", "escribir", "motivo")
    agente, ejecutados = _agente_con_ritmos(tmp_path, store, actos_hoy=6, tope=6)
    agente.register_own_rituals()

    resultado = asyncio.run(agente.cron.jobs["propio_versos"]["func"]())

    assert ejecutados == []
    assert "techo diario" in resultado["reason"]
    assert store.get(ritmo.id).runs == 0


def test_un_ritmo_nocturno_no_lo_para_la_fase_de_silencio(tmp_path):
    """
    Y aquí **no** se comprueba la fase: un ritmo de las tres de la madrugada está
    puesto ahí a propósito. Hacerle respetar el silencio nocturno sería impedir
    la clase de ritmo que más sentido tiene para ella.
    """
    import asyncio

    from src.core.rituals import RitualStore

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    store.propose("escritura_nocturna", "0 3 * * *", "escribir", "la madrugada es mía")
    agente, ejecutados = _agente_con_ritmos(tmp_path, store)
    agente.register_own_rituals()

    asyncio.run(agente.cron.jobs["propio_escritura_nocturna"]["func"]())

    assert len(ejecutados) == 1


def test_sin_albedrio_encendido_no_se_cumple_ninguno(tmp_path):
    """Con la sección `agency` apagada Yuki sólo responde; los ritmos callan."""
    import asyncio

    from src.core.rituals import RitualStore

    store = RitualStore(path=str(tmp_path / "ritmos.json"))
    store.propose("versos", "0 20 * * *", "escribir", "motivo")
    agente, ejecutados = _agente_con_ritmos(tmp_path, store, albedrio=False)
    agente.register_own_rituals()

    resultado = asyncio.run(agente.cron.jobs["propio_versos"]["func"]())

    assert ejecutados == []
    assert "albedrío" in resultado["reason"]


async def _completar(destino, impulso):
    destino.append(impulso)
    return {"status": "completed"}
