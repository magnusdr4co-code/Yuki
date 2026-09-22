"""
La energía de Yuki sube de noche y baja de día; no sólo baja.

`update_tick` se llamaba siempre con cero segundos, así que las dinámicas del
día no corrían nunca: cada acto y cada conversación restaban energía y nada la
devolvía. Clavada abajo tenía dos efectos, uno visible y otro no:

- «Mis reservas merman; anhelo la quietud» entraba en cada prompt, y sin la
  hora en ninguna parte el modelo dedujo el atardecer: el 22 de septiembre, a
  las 11:20, Yuki hablaba de que «el día va cayendo»;
- por debajo de la energía mínima la chispa responde `SIN_ENERGIA` y ella deja
  de actuar por su cuenta con el proceso vivo y el panel en verde —la
  catatonia que la octava invariante nombra—.

Y aun corriendo el tiempo, las tasas no cuadraban: dos horas de descanso a 0,2
no devolvían lo que quince de día gastan a 0,05.
"""

import asyncio
import types
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.circadian import CircadianClock
from src.core.vital_state import VitalState

MADRID = ZoneInfo("Europe/Madrid")


def _vital(tmp_path, energia, desde):
    vital = VitalState(state_path=str(tmp_path / "vital_state.json"))
    vital.energy = energia
    vital.last_updated = desde.isoformat()
    return vital


def test_un_dia_sin_nada_no_la_deja_mas_cansada(tmp_path):
    """Un ciclo completo sin estímulos: lo que el día gasta, la noche lo devuelve."""
    reloj = CircadianClock(jitter_minutes=0)
    desde = datetime(2026, 9, 21, 12, 0, tzinfo=MADRID)
    vital = _vital(tmp_path, 0.5, desde)

    vital.avanzar(reloj, ahora=desde + timedelta(hours=24))

    assert vital.energy >= 0.5


def test_a_media_manana_tras_la_noche_no_se_siente_al_final_del_dia(tmp_path):
    """El caso del 22 de septiembre: agotada la noche anterior, a las 11:20."""
    reloj = CircadianClock(jitter_minutes=0)
    anoche = datetime(2026, 9, 21, 22, 0, tzinfo=MADRID)
    vital = _vital(tmp_path, 0.1, anoche)

    vital.avanzar(reloj, ahora=datetime(2026, 9, 22, 11, 20, tzinfo=MADRID))

    assert vital.energy > 0.3
    assert "merman" not in vital.to_natural_language()
    assert vital.circadian_phase == "atelier"


def test_la_noche_se_cobra_como_noche_aunque_nadie_hable_hasta_la_manana(tmp_path):
    """
    Si todo el intervalo se atribuyera a la fase de ahora, la primera
    conversación de la mañana cobraría la noche como horas de taller.
    """
    reloj = CircadianClock(jitter_minutes=0)
    vital = _vital(tmp_path, 0.2, datetime(2026, 9, 21, 23, 0, tzinfo=MADRID))

    vital.avanzar(reloj, ahora=datetime(2026, 9, 22, 9, 30, tzinfo=MADRID))

    assert vital.energy > 0.2


def test_el_latido_de_agencia_deja_correr_el_tiempo_antes_de_decidir(tmp_path):
    """
    Camino del producto: el tick de cada veinte minutos. Es el único latido si
    nadie le habla, y la energía que mira la chispa tiene que ser la de ahora.
    """
    from src.scheduler.tasks import AutonomousTasks

    ahora = datetime.now(MADRID)
    vital = _vital(tmp_path, 0.05, ahora - timedelta(hours=24))
    vista = {}

    def _decidir(phase=None):
        vista["energia"] = vital.energy
        return types.SimpleNamespace(impulso=None, describe=lambda: "nada")

    agente = types.SimpleNamespace(vital_state=vital, circadian=CircadianClock(),
                                   agency_loop=types.SimpleNamespace(decidir=_decidir))
    asyncio.run(AutonomousTasks(agente).agency_loop_tick())

    assert vista["energia"] > 0.05, "la chispa decidió con la energía de hace un día"
    assert VitalState(state_path=str(tmp_path / "vital_state.json")).energy == vital.energy


def test_la_conversacion_ve_la_hora_real_y_el_cuerpo_al_dia(tmp_path):
    """
    Camino del producto: `generate_response`. El prompt lleva la hora local, y
    la energía con la que se construye ya incluye el tiempo transcurrido.
    """
    from src.core.agent import YukiAgent

    agente = YukiAgent()
    agente.vital_state.state_path = str(tmp_path / "vital_state.json")
    agente.vital_state.energy = 0.05
    agente.vital_state.last_updated = (datetime.now(MADRID) - timedelta(hours=24)).isoformat()
    agente.presence_controller = types.SimpleNamespace(should_respond=lambda *a, **k: True)
    vistos = {}

    def _inferencia(sistema, mensaje, route=None):
        vistos["sistema"] = sistema
        vistos["energia"] = agente.vital_state.energy
        return "Buenos días."
    agente._call_llm_inference = _inferencia

    asyncio.run(agente.generate_response("visitante", "Dextrure", "¿Qué tal todo?"))

    assert "Hora local:" in vistos["sistema"]
    assert vistos["energia"] > 0.05


def test_la_fase_se_lee_en_la_hora_de_madrid_aunque_el_reloj_del_sistema_sea_utc(tmp_path):
    """
    La máquina de la instancia puede vivir en UTC —lo habitual en GCE— y
    `CircadianClock` mira `dt.hour` sin convertir. De 22:00 a 00:00 UTC en Madrid es el descanso profundo; leído
    en UTC sería la consolidación, que no recupera nada.
    """
    from datetime import timezone

    reloj = CircadianClock(jitter_minutes=0)
    vital = _vital(tmp_path, 0.1, datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc))

    vital.avanzar(reloj, ahora=datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc))

    assert vital.energy > 0.5
