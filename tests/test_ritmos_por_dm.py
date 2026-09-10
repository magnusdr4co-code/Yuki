"""
«Apúntate tareas y crons» tiene que poder ejecutarse.

D13 del incidente del 9 de septiembre: el Productor se lo pidió y el turno
terminó con cero herramientas ejecutadas y un «no puedo» que era falso —Yuki
propone ritmos propios y los ajusta desde hace meses—. La causa no era el
modelo: en el arnés del DM no había ninguna herramienta que llamar.

Y la sexta invariante marca el límite: proponer no es concederse. Aprobar un
ritmo no puede estar dentro de este bucle.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.producer_harness import TOOLS, ProducerHarness  # noqa: E402
from src.core.rituals import RitualStore  # noqa: E402
from src.core.runtime_config import RuntimeConfigStore  # noqa: E402
from src.tools.creation_library import CreationLibrary  # noqa: E402
from src.tools.producer_terminal import ProducerTerminal  # noqa: E402


def _llamada(name, arguments=None):
    return {"id": "call-1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments or {})}}


def _agente(tmp_path, turnos):
    class Router:
        def generate_with_tools(self, messages, tools):
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
    agente.reconfigure_runtime = lambda path, value, actor, reason="": store.set(path, value, actor=actor, reason=reason)
    agente.rollback_runtime = lambda path, actor, reason="": store.rollback(path, actor=actor, reason=reason)
    agente._call_llm_inference = lambda system, message: "Cierre."
    return agente


def test_apuntarse_un_ritmo_ejecuta_una_herramienta(tmp_path):
    """El turno terminó con cero herramientas porque no había ninguna que llamar."""
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_propose", {
            "name": "vigilia-de-agua", "cron": "0 7 * * *", "action": "escribir",
            "reason": "quiero escribir antes de que amanezca del todo"})]},
        {"role": "assistant", "content": "Propuesto."},
    ]
    agente = _agente(tmp_path, turnos)
    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "apúntate tareas y crons"))

    assert "✓ ritual_propose" in respuesta
    assert "Sin herramientas ejecutadas" not in respuesta
    assert len(agente.rituals.pendientes()) == 1


def test_un_ritmo_propuesto_no_queda_activo(tmp_path):
    """Proponer no es concederse: la sexta invariante del proyecto."""
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("ritual_propose", {
            "name": "vigilia-de-agua", "cron": "0 7 * * *", "action": "escribir",
            "reason": "porque sí"})]},
        {"role": "assistant", "content": "Propuesto."},
    ]
    agente = _agente(tmp_path, turnos)
    asyncio.run(ProducerHarness(agente).run("Yuki", "apúntate un ritmo"))

    assert agente.rituals.aprobados() == [], "un ritmo propuesto por DM no puede activarse solo"


def test_el_arnes_no_puede_aprobar_ni_retirar_ritmos():
    """Aprobar dentro del bucle sería concederse permisos con otro nombre."""
    nombres = {herramienta["function"]["name"] for herramienta in TOOLS}

    assert {"ritual_list", "ritual_propose", "ritual_adjust"} <= nombres
    assert not nombres & {"ritual_approve", "ritual_reject", "ritual_retire"}


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
