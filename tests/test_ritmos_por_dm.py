"""
«Apúntate tareas y crons» tiene que poder ejecutarse, y sin pedir permiso.

D13 del incidente del 9 de septiembre: el Productor se lo pidió y el turno
terminó con cero herramientas ejecutadas y un «no puedo» que era falso —Yuki
propone ritmos propios y los ajusta desde hace meses—. La causa no era el
modelo: en el arnés del DM no había ninguna herramienta que llamar.

Hubo un trámite de aprobación y se ha quitado: decidir a qué hora escribe no es
concederse un permiso. La sexta invariante le prohíbe tocar **su iniciativa, la
transparencia y el freno** —y un ritmo no es ninguna de las tres—. Eso es lo que
estas pruebas fijan ahora: que los ritmos son suyos y que esas tres no.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.producer_harness import RUTA, TOOLS, ProducerHarness  # noqa: E402
from src.core.rituals import RitualStore  # noqa: E402
from src.core.runtime_config import RuntimeConfigStore  # noqa: E402
from src.tools.creation_library import CreationLibrary  # noqa: E402
from src.tools.producer_terminal import ProducerTerminal  # noqa: E402


def _llamada(name, arguments=None):
    return {"id": "call-1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments or {})}}


def _agente(tmp_path, turnos):
    class Router:
        def generate_with_tools(self, messages, tools, route=None):
            # `route` no es opcional en el arnés: sale siempre con la
            # ruta declarada. Un doble más estrecho que la firma real
            # deja pasar el cambio que rompe producción.
            assert route == RUTA
            return turnos.pop(0)

    armor = SimpleNamespace(sanitize_user_prompt=lambda text: SimpleNamespace(allowed=True, text=text))
    base = {"agent": {"model": {"temperature": 0.72, "max_tokens": 2048}},
            "vertex_ai": {"temperature": 0.72, "max_tokens": 2048,
                          "primary_model": "m", "fallback_model": "f"}}
    store = RuntimeConfigStore(base, tmp_path / "runtime_overrides.json")
    agente = SimpleNamespace(creation_library=CreationLibrary(tmp_path), llm_router=Router(),
                             model_armor=armor, producer_terminal=ProducerTerminal(),
                             runtime_config_get=store.get_public,
                             rituals=RitualStore(str(tmp_path / "runtime_rituals.json")))
    registrados = []
    agente.register_own_rituals = lambda: registrados.append(1) or len(registrados)
    agente.reconfigure_runtime = lambda path, value, actor, reason="": store.set(path, value, actor=actor, reason=reason)
    agente.rollback_runtime = lambda path, actor, reason="": store.rollback(path, actor=actor, reason=reason)
    agente._call_llm_inference = lambda system, message: "Cierre."
    return agente


def test_apuntarse_un_ritmo_ejecuta_una_herramienta(tmp_path):
    """El turno terminó con cero herramientas porque no había ninguna que llamar."""
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_adopt", {
            "name": "vigilia-de-agua", "cron": "0 7 * * *", "action": "escribir",
            "reason": "quiero escribir antes de que amanezca del todo"})]},
        {"role": "assistant", "content": "Adoptado."},
    ]
    agente = _agente(tmp_path, turnos)
    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "apúntate tareas y crons"))

    assert "✓ ritual_adopt" in respuesta
    assert "Sin herramientas ejecutadas" not in respuesta
    assert len(agente.rituals.aprobados()) == 1, "el ritmo queda activo, no esperando"


def test_un_ritmo_adoptado_queda_activo_sin_pedir_permiso(tmp_path):
    """
    Lo contrario de lo que esta prueba exigía antes. El trámite no protegía nada:
    lo que protege es que la acción salga de una lista cerrada, que la frecuencia
    esté acotada y que cumplirlo pase por el freno y por el techo diario.
    """
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_adopt", {
            "name": "vigilia-de-agua", "cron": "0 7 * * *", "action": "escribir",
            "reason": "porque a esa hora lo que escribo encuentra respuesta"})]},
        {"role": "assistant", "content": "Adoptado."},
    ]
    agente = _agente(tmp_path, turnos)
    asyncio.run(ProducerHarness(agente).run("Yuki", "apúntate un ritmo"))

    activos = agente.rituals.aprobados()
    assert [r.name for r in activos] == ["vigilia_de_agua"], "el nombre se normaliza"
    assert agente.rituals.pendientes() == [], "no queda nada esperando a nadie"


def test_puede_retirar_un_ritmo_suyo(tmp_path):
    """Quitarse un ritmo que no le sirve tampoco necesita permiso, y libera cupo."""
    from src.core.rituals import RitualStore

    tienda = RitualStore(str(tmp_path / "runtime_rituals.json"))
    ritmo = tienda.propose("hora_muerta", "0 4 * * *", "contemplar", "probemos")
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_retire", {
            "ritual_id": ritmo.id, "reason": "a esa hora no me sale nada"})]},
        {"role": "assistant", "content": "Retirado."},
    ]
    agente = _agente(tmp_path, turnos)
    agente.rituals = tienda
    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "quítate ese ritmo"))

    assert "✓ ritual_retire" in respuesta
    assert agente.rituals.aprobados() == []


def test_los_ritmos_son_suyos():
    """Adoptar, mover, retirar y activar: sin trámite y sin intermediario."""
    nombres = {herramienta["function"]["name"] for herramienta in TOOLS}

    assert {"ritual_list", "ritual_adopt", "ritual_move",
            "ritual_retire", "ritual_activate"} <= nombres


def test_lo_que_sigue_fuera_de_su_alcance_es_lo_que_importa():
    """
    El límite real de la sexta invariante: **su iniciativa, la transparencia y el
    freno**. Un ritmo no es ninguna de las tres; subirse el techo de actos,
    apagar el marcado o soltar el freno, sí. Se fija sobre la lista blanca de
    `runtime_config_set`, que es la única puerta que tiene a la configuración.
    """
    from src.core.producer_harness import RUNTIME_PATH

    permitidos = RUNTIME_PATH["enum"]

    assert permitidos, "debería haber algo ajustable: la temperatura sí es suya"
    for prohibido in ("agency", "transparency", "brake", "freno", "max_actions_per_day",
                      "spontaneity", "budget", "discord", "pairing"):
        assert not any(prohibido in ruta for ruta in permitidos), \
            f"la lista blanca deja tocar «{prohibido}», que sí sería concederse permisos"

    nombres = {herramienta["function"]["name"] for herramienta in TOOLS}
    assert not nombres & {"brake_release", "freno_soltar", "transparency_set",
                          "agency_set", "budget_set"}


def test_una_propuesta_invalida_es_un_fallo_visible(tmp_path):
    """Un cron cada diez minutos no es un ritmo; y un fallo no puede leerse como éxito."""
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_propose", {
            "name": "tic", "cron": "*/10 * * * *", "action": "escribir", "reason": "quiero"})]},
        {"role": "assistant", "content": "No ha salido."},
    ]
    agente = _agente(tmp_path, turnos)
    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "apúntate un ritmo cada diez minutos"))

    assert "✗ ritual_propose" in respuesta
    assert agente.rituals.pendientes() == []


def test_consultar_los_ritmos_dice_que_acciones_caben(tmp_path):
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_list")]},
        {"role": "assistant", "content": "Esto es lo que tengo."},
    ]
    agente = _agente(tmp_path, turnos)
    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "¿qué ritmos tienes?"))

    assert "✓ ritual_list" in respuesta
    assert ProducerHarness(agente)._ritual_list()["acciones_admitidas"]
