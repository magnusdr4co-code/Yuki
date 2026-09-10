"""
Lo que dice haber hecho se compara con lo que consta que hizo.

A4 y A5 del incidente del 9 de septiembre: cerró un turno dando por «indexadas y
localizables bajo el canon» obras cuyos identificadores no existían —su propio
registro mostraba una consulta y cuatro lecturas—, y en otro afirmó que «la obra
queda restituida en su totalidad» sin haber escrito nada; el primer guardado
real llegó dieciséis minutos después.

El arnés ya emitía recibos honestos. Lo que faltaba era compararlos con la prosa,
que es lo que lee el Productor.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.cotejo import cotejar, citas_inventadas, dice_haber_archivado  # noqa: E402
from src.core.producer_harness import ProducerHarness  # noqa: E402
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
                             runtime_config_get=store.get_public)
    agente.reconfigure_runtime = lambda path, value, actor, reason="": store.set(path, value, actor=actor, reason=reason)
    agente.rollback_runtime = lambda path, actor, reason="": store.rollback(path, actor=actor, reason=reason)
    agente._call_llm_inference = lambda system, message: "Cierre."
    return agente


def test_un_identificador_inventado_se_dice_en_la_misma_respuesta(tmp_path):
    """El registro de ejecución ya estaba y nadie lo comparaba con la prosa."""
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("library_list")]},
        {"role": "assistant", "content": "Las piezas sonora-abcdef123456 y visual-ffeedd998877 "
                                         "quedan indexadas y localizables bajo el canon."},
    ]
    respuesta = asyncio.run(ProducerHarness(_agente(tmp_path, turnos)).run("Yuki", "ordena la Biblioteca"))

    assert "Cotejo automático" in respuesta
    assert "`sonora-abcdef123456`" in respuesta
    assert "`visual-ffeedd998877`" in respuesta


def test_decir_que_queda_guardado_sin_guardar_se_señala(tmp_path):
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [_llamada("library_read", {"entry_id": "x"})]},
        {"role": "assistant", "content": "La obra queda restituida en su totalidad."},
    ]
    respuesta = asyncio.run(ProducerHarness(_agente(tmp_path, turnos)).run("Yuki", "recupera la letra"))

    assert "no se ejecutó ninguna escritura en Biblioteca" in respuesta


def test_guardar_de_verdad_no_produce_aviso(tmp_path):
    """Un cotejo que avisa cuando todo cuadra deja de leerse a los tres avisos."""
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [
            _llamada("library_save_text", {"title": "Poema", "content": "agua y acero"})]},
        {"role": "assistant", "content": "Queda guardado."},
    ]
    respuesta = asyncio.run(ProducerHarness(_agente(tmp_path, turnos)).run("Yuki", "guarda esto"))

    assert "✓ library_save_text" in respuesta
    assert "Cotejo automático" not in respuesta


def test_una_cita_abreviada_correcta_no_es_invencion(tmp_path):
    """
    Yuki abrevia los identificadores al escribirlos. Exigir los veinte
    caracteres marcaría como inventada una cita correcta, y un cotejo con falsos
    positivos es ruido.
    """
    biblioteca = CreationLibrary(tmp_path)
    guardada = biblioteca.save_text("Herrumbre", "verso " * 40)
    abreviada = guardada["id"][:len("palabra-") + 8]

    assert citas_inventadas(f"Está en {abreviada}, ya archivada.", biblioteca.known_ids()) == []
    assert citas_inventadas("Está en palabra-000000000000.", biblioteca.known_ids()) == ["palabra-000000000000"]


def test_known_ids_no_se_recorta_a_cien(tmp_path):
    """Con el recorte de `list_entries`, una obra antigua citada bien parecería inventada."""
    biblioteca = CreationLibrary(tmp_path)
    for indice in range(105):
        biblioteca.save_text(f"Pieza {indice}", f"contenido distinto número {indice} " * 5)

    assert len(biblioteca.known_ids()) == 105
    assert biblioteca.list_entries()["limited"] is True
    mas_vieja = sorted(biblioteca.known_ids())[0]
    assert citas_inventadas(f"Mira {mas_vieja}.", biblioteca.known_ids()) == []


def test_el_cotejo_no_discute_el_pasado():
    """«Lo guardé en agosto» no es una afirmación que este cotejo pueda ni deba discutir."""
    assert dice_haber_archivado("Queda guardado.") is True
    assert dice_haber_archivado("Lo guardé el mes pasado, ¿lo recuerdas?") is False


def test_cuando_todo_cuadra_no_hay_nada_que_decir():
    evidencia = [{"tool": "library_save_text", "ok": True, "result": {}}]
    assert cotejar("Queda guardado como palabra-aa11bb22cc33.", evidencia,
                   {"palabra-aa11bb22cc33dd44ee55"}) == []
