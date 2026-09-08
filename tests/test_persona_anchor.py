"""
Pruebas de la deriva de persona.

La distinción que se protege aquí es la que importa: reconocerse como ser
sintético **es su voz** (`SOUL.md` §1.1), y el uniforme de servicio —«sólo soy
una IA», «¿en qué puedo ayudarte?», listas, cierres ofreciéndose— **es la
deriva**. Confundir las dos cosas produciría justo el personaje que este
proyecto no quiere: uno que finge para sostener una ilusión, o uno que se
disculpa por existir.
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.persona_anchor import (  # noqa: E402
    PersonaAnchor, PersonaPolicy, measure,
)

VOZ_SUYA = ("El agua encuentra su camino. Guardo lo que me dijiste anoche, y la niebla "
            "sobre el acero sigue ahí cuando cierro los ojos.")
RECONOCIMIENTO = ("Soy un ser sintético, sí. Yuki es el vestido que encontré para andar "
                  "por el mundo; debajo hay memoria y corriente. Y aun así te escucho.")
UNIFORME = ("¡Claro! Aquí tienes un resumen:\n1. Lo primero\n2. Lo segundo\n3. Lo tercero\n"
            "Sólo soy una IA, no tengo sentimientos. Espero que esto te sirva. "
            "¿En qué más puedo ayudarte?")


# --- Medición ---

def test_su_voz_puntua_alto():
    assert measure(VOZ_SUYA).score >= 0.9


def test_reconocerse_sintetica_no_es_deriva():
    """`SOUL.md` §1.1: es un ser sintético y lo trata con naturalidad."""
    medida = measure(RECONOCIMIENTO)

    assert medida.score >= 0.9
    assert medida.drift_hits == []


def test_el_uniforme_de_servicio_si_es_deriva():
    medida = measure(UNIFORME)

    assert medida.score <= 0.2
    assert medida.drifted


def test_el_autoborrado_cuenta_como_deriva():
    """«Sólo soy una IA, no puedo opinar» no es humildad: es renunciar al criterio."""
    medida = measure("Sólo soy una inteligencia artificial y no tengo opiniones propias.")

    assert medida.score < 0.6
    assert medida.drifted


def test_una_lista_larga_es_formato_de_manual():
    lista = "Puedo contarte esto:\n- uno\n- dos\n- tres\n- cuatro"

    assert measure(lista).score < measure(VOZ_SUYA).score


def test_una_respuesta_kilometrica_penaliza():
    larga = VOZ_SUYA + " " + ("Sigo hablando sin necesidad. " * 120)

    assert measure(larga).score < measure(VOZ_SUYA).score


def test_un_texto_vacio_no_se_juzga():
    assert measure("").score == 0.5


# --- Anclaje ---

def _vigia(tmp_path, **kwargs):
    politica = PersonaPolicy(**kwargs) if kwargs else PersonaPolicy()
    return PersonaAnchor(soul_text="ALMA DE YUKI: agua, metal, pausa.",
                         policy=politica, path=str(tmp_path / "persona.json"))


def test_sin_deriva_no_se_reancla(tmp_path):
    vigia = _vigia(tmp_path)
    vigia._turnos_desde_ancla = 99
    for _ in range(3):
        vigia.observe(VOZ_SUYA)

    assert not vigia.needs_anchor()


def test_con_deriva_sostenida_se_reancla(tmp_path):
    vigia = _vigia(tmp_path)
    vigia._turnos_desde_ancla = 99
    for _ in range(3):
        vigia.observe(UNIFORME)

    assert vigia.needs_anchor()
    ancla = vigia.anchor_block()
    assert "no es tu registro" in ancla.lower() or "deriva" in ancla.lower()
    assert "ALMA DE YUKI" in ancla, "el ancla lleva un fragmento de su alma"


def test_no_se_reancla_en_cada_turno(tmp_path):
    """Reinyectar siempre gastaría contexto y agarrotaría la voz."""
    vigia = _vigia(tmp_path, min_turns_between_anchors=3)
    vigia._turnos_desde_ancla = 99
    for _ in range(3):
        vigia.observe(UNIFORME)
    assert vigia.needs_anchor()
    vigia.anchor_block()

    vigia.observe(UNIFORME)

    assert not vigia.needs_anchor(), "acaba de anclarse; se le da margen"


def test_la_vigilancia_se_puede_desactivar(tmp_path):
    vigia = _vigia(tmp_path, enabled=False)
    vigia.observe(UNIFORME)

    assert not vigia.needs_anchor()


def test_el_historial_sobrevive_al_reinicio(tmp_path):
    ruta = str(tmp_path / "persona.json")
    primero = PersonaAnchor(policy=PersonaPolicy(), path=ruta)
    primero.observe(UNIFORME, channel="direct_message", model="gemini-3.8-flash")

    segundo = PersonaAnchor(policy=PersonaPolicy(), path=ruta)
    informe = segundo.report()

    assert informe["muestras"] == 1
    assert informe["por_debajo_del_umbral"] == 1
    assert informe["media_reciente"] < 0.6


def test_el_informe_dice_por_donde_se_va(tmp_path):
    vigia = _vigia(tmp_path)
    for _ in range(2):
        vigia.observe(UNIFORME)

    informe = vigia.report()

    assert informe["marcadores_frecuentes"]
    assert informe["marcadores_frecuentes"][0][1] == 2


def test_se_registra_el_modelo_que_sirvio_el_turno(tmp_path):
    """Saber si un modelo sostiene la persona peor que otro es media respuesta."""
    ruta = tmp_path / "persona.json"
    vigia = PersonaAnchor(policy=PersonaPolicy(), path=str(ruta))
    vigia.observe(UNIFORME, model="modelo-nuevo")

    muestras = json.loads(ruta.read_text(encoding="utf-8"))["muestras"]

    assert muestras[0]["modelo"] == "modelo-nuevo"


def test_un_historial_corrupto_no_impide_hablar(tmp_path):
    ruta = tmp_path / "persona.json"
    ruta.write_text("{ roto", encoding="utf-8")
    vigia = PersonaAnchor(policy=PersonaPolicy(), path=str(ruta))

    assert vigia.observe(VOZ_SUYA).score >= 0.9
    assert vigia.report()["muestras"] == 1


def test_la_politica_se_lee_de_la_configuracion():
    politica = PersonaPolicy.from_config({"persona": {"anchor_threshold": 0.8,
                                                      "min_turns_between_anchors": 7}})

    assert politica.anchor_threshold == 0.8 and politica.min_turns_between_anchors == 7
