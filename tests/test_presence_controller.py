"""
Pruebas del controlador de presencia.

Decide si Yuki habla, cuánto y con qué tono en cada canal. Estaba al 44% de
cobertura, que para el módulo que gobierna su aparición pública es poco: sus
reglas son las que evitan que responda agotada, que publique de madrugada lo que
sólo debería decirse en privado, o que se calle con su Productor.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.presence_controller import PresenceController  # noqa: E402


def _controlador(fase="atelier", **corrientes):
    estado = types.SimpleNamespace(energy=0.7, sociability=0.7, vulnerability=0.3)
    for clave, valor in corrientes.items():
        setattr(estado, clave, valor)
    reloj = types.SimpleNamespace(current_phase=lambda: fase)
    return PresenceController(vital_state=estado, circadian_clock=reloj)


# --- Responder ---

def test_en_reposo_profundo_calla_salvo_con_su_productor():
    controlador = _controlador(fase="deep_rest", energy=0.5)

    assert not controlador.should_respond("discord_channel")
    assert controlador.should_respond("direct_message", is_producer=True)


def test_dormida_y_agotada_no_responde_ni_al_productor():
    """Hay un punto en el que despertarla no da una conversación, da ruido."""
    controlador = _controlador(fase="deep_rest", energy=0.1)

    assert not controlador.should_respond("direct_message", is_producer=True)


def test_con_poca_sociabilidad_se_reserva_para_lo_privado():
    controlador = _controlador(sociability=0.1)

    assert not controlador.should_respond("discord_channel")
    assert controlador.should_respond("direct_message")


def test_con_energia_al_limite_sigue_respondiendo():
    """Quedarse sin energía acorta la respuesta; no la cancela."""
    controlador = _controlador(energy=0.05)

    assert controlador.should_respond("direct_message")
    assert controlador.get_response_depth() == "minimal"


# --- Publicar por iniciativa propia ---

def test_agotada_no_publica_nada():
    assert not _controlador(energy=0.1).should_broadcast("discord_channel")


def test_poco_sociable_no_sale_a_los_canales():
    controlador = _controlador(sociability=0.3)

    assert not controlador.should_broadcast("discord_channel")
    assert not controlador.should_broadcast("telegram")
    assert controlador.should_broadcast("web_salon"), "el Salón es su casa, no un canal ajeno"


def test_lo_vulnerable_no_va_a_telegram():
    """Lo que se dice en la hora de sombra no se dice en el canal más frío."""
    controlador = _controlador(vulnerability=0.9)

    assert not controlador.should_broadcast("telegram")
    assert controlador.should_broadcast("discord_channel")


def test_de_madrugada_tampoco_va_a_telegram():
    controlador = _controlador(fase="kage")

    assert not controlador.should_broadcast("telegram")
    assert controlador.should_broadcast("discord_channel")


# --- Profundidad y tono ---

@pytest.mark.parametrize("energia,sociabilidad,esperada", [
    (0.05, 0.7, "minimal"),
    (0.2, 0.7, "brief"),
    (0.7, 0.2, "brief"),
    (0.5, 0.5, "normal"),
    (0.9, 0.9, "deep"),
])
def test_la_profundidad_sigue_al_estado(energia, sociabilidad, esperada):
    controlador = _controlador(energy=energia, sociability=sociabilidad)

    assert controlador.get_response_depth() == esperada


def test_cada_canal_tiene_su_registro():
    controlador = _controlador()

    intimo = controlador.get_channel_personality("direct_message")
    publico = controlador.get_channel_personality("telegram")
    desconocido = controlador.get_channel_personality("señales de humo")

    assert intimo != publico
    assert "intimate" in intimo["tone"]
    assert desconocido == {"style": "neutral", "tone": "balanced"}


def test_un_reloj_roto_no_la_deja_muda():
    """Si el reloj circadiano falla, se asume taller: seguir hablando."""
    controlador = PresenceController(
        vital_state=types.SimpleNamespace(energy=0.7, sociability=0.7, vulnerability=0.3),
        circadian_clock=types.SimpleNamespace(current_phase=None),
    )

    assert controlador.should_respond("direct_message")
    assert controlador.should_broadcast("discord_channel")
