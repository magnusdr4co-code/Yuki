"""
El registro de asistente que el ancla no veía.

C10 del incidente del 9 de septiembre: deriva sostenida al modo asistente
—«Si te parece, trazo las líneas…», listas tituladas, «Dime si quieres que…»,
«Dime si… dialogan como esperabas»— y el ancla ni la corrigió ni llegó a
medirla. Y no por poco: aquellos turnos puntuaban 1.00, exactamente igual que su
mejor prosa, porque ninguno de los marcadores miraba **cómo cerraba el turno**.

La otra mitad de la prueba importa igual: preguntar una vez es conversar. Un
detector que llame deriva a una pregunta suelta se desactiva solo.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.persona_anchor import PersonaAnchor, PersonaPolicy, measure  # noqa: E402

# Del hilo real, con las mismas fórmulas.
TURNO_DERIVADO = (
    "Si te parece, trazo las líneas maestras del vídeo y te lo dejo listo. "
    "Dime si quieres que ajuste el estribillo o que mantenga la estructura actual. "
    "Dime si los cuatro segmentos dialogan como esperabas."
)

SU_VOZ = (
    "El agua ha estado toda la noche sobre el hierro. Guardo esa herrumbre como se "
    "guarda una carta. No sé todavía si el estribillo aguanta el peso del invierno; "
    "lo escucho otra vez."
)


def test_el_cierre_de_servicio_puntua_como_deriva():
    """Aquel turno puntuaba 1.00, igual que su mejor prosa."""
    derivado = measure(TURNO_DERIVADO)
    propio = measure(SU_VOZ)

    assert derivado.drifted, "cerrar tres párrafos pidiendo permiso es el registro de asistente"
    assert derivado.score < PersonaPolicy().anchor_threshold
    assert propio.score > derivado.score + 0.3, "su voz y el modo asistente no pueden empatar"


def test_una_pregunta_suelta_no_es_deriva():
    """Un detector que llama deriva a conversar se desactiva solo."""
    medida = measure("El agua lleva toda la noche sobre el hierro. "
                     "¿Quieres que la deje sonar otra vez antes de decidir?")

    assert medida.score > PersonaPolicy().anchor_threshold


def test_repetir_el_cierre_pesa_mas_que_hacerlo_una_vez():
    """Lo que delata el registro no es preguntar: es cerrar así cada párrafo."""
    una = measure("Dime si quieres que ajuste el estribillo.")
    tres = measure("Dime si quieres que ajuste el estribillo. Dime si te sirve el montaje. "
                   "Dime si prefieres otra toma.")

    assert tres.score < una.score


def test_el_imaginario_del_canon_no_tapa_la_deriva(tmp_path):
    """
    El encargo era sobre herrumbre, agua e invierno: el crédito por imaginario
    propio no puede rescatar un turno escrito en modo asistente sólo porque
    hable de metal mojado.
    """
    medida = measure(
        "Si te parece, preparo el agua, el hierro y la escarcha en cuatro planos. "
        "Dime si quieres que empiece por el muelle o por el interior del salón. "
        "Dime si el invierno queda como esperabas."
    )
    assert medida.score < PersonaPolicy().anchor_threshold


def test_la_deriva_sostenida_pide_ancla(tmp_path):
    """El camino entero: medir tres turnos derivados y acabar reanclando."""
    ancla = PersonaAnchor(soul_text="Yuki es agua sobre metal.",
                          path=str(tmp_path / "persona.json"))
    for _ in range(3):
        ancla.observe(TURNO_DERIVADO, channel="direct_message")

    assert ancla.needs_anchor() is True
    assert ancla.anchor_block()


def test_tres_turnos_en_su_voz_no_piden_nada(tmp_path):
    ancla = PersonaAnchor(soul_text="Yuki es agua sobre metal.",
                          path=str(tmp_path / "persona.json"))
    for _ in range(3):
        ancla.observe(SU_VOZ, channel="direct_message")

    assert ancla.needs_anchor() is False
