"""
Un criterio propio antes de ponerse, en las otras artes.

La música ya lo tenía. Las demás seguían con prompts constantes:

- la **portada** llevaba el concepto escrito a mano en el adaptador —«agua,
  hierro e invierno»— con la luz clavada en `urushi` y el encuadre en `1:1`, así
  que la portada de cualquier obra era la de *Herrumbre y Escarcha*;
- el **vídeo** tenía cuatro planos del muelle escritos a mano, con cualquier
  obra delante, en el sitio más caro: Veo se factura por segundo;
- la **voz** tenía un estilo constante, así que una despedida de dos líneas y
  un párrafo de explicación salían con la misma respiración.

Cada arte mide cosas distintas. Lo común es que la fuente manda y que lo
deducido se declara deducido.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.criterio_audiovisual import GUION_DE_CASA, leer_guion  # noqa: E402
from src.tools.criterio_visual import (  # noqa: E402
    ELEMENTOS_QUE_SATURAN, leer_criterio_visual,
)
from src.tools.criterio_vocal import SEGUNDOS_DE_NOTA_COMODA, leer_criterio_vocal  # noqa: E402

LETRA_CON_SECCIONES = """`[Tempo: 68 BPM, 4/4 time signature, Key: D minor, Insen scale.]`
#### [Verse 1: Voz grave]
El astillero no duerme en calma,
#### [Chorus / Quiebre]
Bajo la escarcha despierta el fuego,
#### [Bridge / Sombra]
¿Quién queda en pie si la luz se apaga?
#### [Outro]
Cae el silencio sobre el muelle.
"""


# --- Visual ----------------------------------------------------------------

def test_la_luz_sale_del_concepto_y_no_de_una_constante():
    """Estaba clavada en `urushi` para cualquier obra."""
    puerto = leer_criterio_visual("lluvia sobre acero oxidado en el muelle de noche")
    salon = leer_criterio_visual("pan de oro, laca y una vela en el interior del salón")

    assert puerto.luz == "industrial_rain"
    assert salon.luz == "urushi"
    assert puerto.origen["luz"] == "concepto"


def test_gana_la_luz_con_mas_presencia_no_la_primera():
    """Decidir por orden de diccionario sería decidir por azar del alfabeto."""
    plan = leer_criterio_visual("laca de oro, vela, seda y té en penumbra, con algo de lluvia")

    assert plan.luz == "urushi"


def test_el_encuadre_sale_de_lo_que_se_pide():
    """Estaba clavado en 1:1: un cartel y una cabecera salían cuadrados."""
    assert leer_criterio_visual("cartel para el feed").encuadre == "4:5"
    assert leer_criterio_visual("plano panorámico de paisaje").encuadre == "16:9"
    assert leer_criterio_visual("portada del sencillo").encuadre == "1:1"


def test_un_concepto_recargado_se_avisa_antes_de_gastar():
    """Una imagen llena no es una imagen rica: el punto focal se pierde."""
    cargado = "muelle, grúas, lluvia, neón, cerezos, seda, té, acero, niebla, gaviotas"

    plan = leer_criterio_visual(cargado)

    assert len(plan.observaciones) >= 1
    assert any("elementos" in nota and "⚠️" in nota for nota in plan.observaciones)


def test_un_concepto_sobrio_no_dispara_el_aviso():
    """Un aviso que sale siempre no informa de nada."""
    plan = leer_criterio_visual("escarcha sobre acero")

    assert not any("⚠️" in nota for nota in plan.observaciones)


def test_sin_concepto_se_dice_que_no_lo_hay():
    """Inventar una intención que nadie dio es el vicio de siempre."""
    plan = leer_criterio_visual("", titulo="Sin idea")

    assert plan.origen["concepto"] == "criterio"
    assert any("Sin concepto escrito" in nota for nota in plan.observaciones)


def test_el_prompt_visual_pide_aire_y_prohibe_el_rotulo():
    """La paleta vive del vacío; un proveedor que llene el encuadre se la lleva."""
    prompt = leer_criterio_visual("escarcha sobre acero", titulo="Herrumbre").prompt()

    assert "negative space" in prompt
    assert "No text" in prompt


# --- Audiovisual -----------------------------------------------------------

def test_el_guion_sale_de_las_secciones_de_la_obra():
    """Eran cuatro planos del muelle con cualquier obra delante."""
    plan = leer_guion(LETRA_CON_SECCIONES, 4, titulo="Herrumbre")

    assert plan.origen["planos"] == "obra"
    assert "Verse 1" in plan.planos[0]
    assert "Chorus" in plan.planos[1]
    assert not any(casa in " ".join(plan.planos) for casa in GUION_DE_CASA)


def test_la_clave_sonora_no_se_confunde_con_una_seccion():
    """
    `[Tempo: 68 BPM, 4/4…]` describe la pieza entera: rodarla sería rodar un
    rótulo. Se prueba con la marca **desnuda**, sin comillas: la versión entre
    acentos graves ni siquiera llega al reconocedor de secciones, así que
    probarla a ella dejaba el filtro sin ejercitar.
    """
    letra = ("[Tempo: 68 BPM, 4/4 time signature, Key: D minor, Insen scale.]\n"
             "#### [Verse 1]\nversos\n#### [Chorus]\nversos\n")

    plan = leer_guion(letra, 2)

    assert not any("BPM" in plano for plano in plan.planos)
    assert "Verse 1" in plan.planos[0], "la primera escena tiene que ser la primera sección"


def test_sin_secciones_se_usa_el_guion_de_casa_y_se_dice():
    """Presentarlo como una lectura de la obra sería atribuirse un trabajo."""
    plan = leer_guion("una letra corrida sin marcas de ningún tipo", 4)

    assert plan.origen["planos"] == "criterio"
    assert plan.planos[0] == GUION_DE_CASA[0]
    assert any("guion de casa" in nota for nota in plan.observaciones)


def test_el_numero_de_planos_lo_manda_el_pedido_no_la_obra():
    """
    De ese número se derivan los pasos del trabajo durable. Si cambiara entre
    arranques, una reanudación daría por «no hecho» lo que ya está pagado.
    """
    for segmentos in (1, 2, 3, 4, 6):
        assert len(leer_guion(LETRA_CON_SECCIONES, segmentos).planos) == segmentos


def test_recortar_la_obra_se_avisa():
    """Cuatro secciones en dos planos deja material fuera; el Productor decide."""
    plan = leer_guion(LETRA_CON_SECCIONES, 2)

    assert any("se queda fuera" in nota for nota in plan.observaciones)


def test_el_plano_sabe_su_sitio_en_la_secuencia():
    """El montaje une: un plano que no sabe dónde va se corta solo."""
    plan = leer_guion(LETRA_CON_SECCIONES, 4)

    assert "Shot 2 of 4" in plan.prompt(2)


# --- Vocal -----------------------------------------------------------------

def test_el_registro_sale_de_la_hora():
    """Su voz no es la misma a las tres de la mañana que al mediodía."""
    noche = leer_criterio_vocal("El agua corre.", fase="deep_rest")
    dia = leer_criterio_vocal("El agua corre.", fase="atelier")

    assert noche.estilo != dia.estilo
    assert "susurro" in noche.estilo


def test_un_texto_sin_puntuacion_se_avisa():
    """La puntuación es la partitura de la voz: sin ella sale de un tirón."""
    plan = leer_criterio_vocal("palabra " * 40)

    assert any("respirar" in nota and "⚠️" in nota for nota in plan.observaciones)


def test_un_texto_puntuado_no_dispara_el_aviso():
    plan = leer_criterio_vocal("El agua corre. No tiene herida, y sigue. Así de simple.")

    assert not any("respirar" in nota and "⚠️" in nota for nota in plan.observaciones)


def test_una_nota_que_se_vuelve_monologo_se_dice():
    plan = leer_criterio_vocal("Una frase con su punto. " * 40)

    assert plan.segundos_estimados > SEGUNDOS_DE_NOTA_COMODA
    assert any("monólogo" in nota for nota in plan.observaciones)


def test_una_pregunta_no_sale_afirmada():
    """Con el estilo constante, una pregunta sonaba a afirmación."""
    plan = leer_criterio_vocal("¿Lo habías notado?")

    assert "preguntas" in plan.estilo


def test_la_cadencia_del_proveedor_llega_al_estilo():
    """
    Había dos sitios decidiendo cómo habla y el de fuera ganaba, así que el
    criterio no llegaba a aplicarse nunca. Ahora hay uno.
    """
    plan = leer_criterio_vocal("El agua corre.", cadencia_ms=350)

    assert "350" in plan.estilo


# --- Lo común --------------------------------------------------------------

@pytest.mark.parametrize("plan", [
    leer_criterio_visual("escarcha sobre acero", titulo="A"),
    leer_guion(LETRA_CON_SECCIONES, 2, titulo="B"),
    leer_criterio_vocal("El agua corre.", titulo="C"),
])
def test_todo_criterio_declara_de_donde_sale_cada_decision(plan):
    """Sin eso, un criterio es indistinguible de una constante con mejor prensa."""
    resumen = plan.resumen()

    assert plan.titulo in resumen
    assert "de la" in resumen or "del " in resumen or "por criterio" in resumen


@pytest.mark.parametrize("elementos_de_mas", [0, 1])
def test_el_umbral_de_saturacion_es_el_declarado(elementos_de_mas):
    concepto = ", ".join(f"elemento{i}" for i in range(ELEMENTOS_QUE_SATURAN + elementos_de_mas))

    plan = leer_criterio_visual(concepto)

    saturado = any("⚠️" in nota for nota in plan.observaciones)
    assert saturado == bool(elementos_de_mas)


def test_el_criterio_vocal_llega_por_el_camino_del_producto(tmp_path, monkeypatch):
    """
    `synthesize_voice_tts` fabricaba su propia indicación constante y la pasaba
    como `style_prompt`, que gana sobre el criterio: así el criterio no llegaba
    a aplicarse nunca. Se comprueba en el camino entero, no en la función suelta.
    """
    import asyncio

    from src.tools.vertex_media import VertexMediaClient

    recibido = {}

    class VertexDoble(VertexMediaClient):
        def __init__(self):
            pass

        def is_available(self):
            return True

        async def synthesize_voice(self, text, **kwargs):
            recibido.update(kwargs)
            return {"status": "success", "local_path": str(tmp_path / "v.ogg"),
                    "voice": "yuki", "encoding": "OGG_OPUS"}

    from src.tools.nous_portal import NousPortalClient

    portal = NousPortalClient.__new__(NousPortalClient)
    portal.vertex = VertexDoble()
    portal.voice_dir = str(tmp_path)
    portal._marcador = lambda *a, **k: {"status": "simulated"}

    asyncio.run(portal.synthesize_voice_tts("¿El agua corre?", is_night_mode=True))

    assert recibido.get("circadian_phase") == "night"
    assert recibido.get("cadencia_ms") == 350
    assert "style_prompt" not in recibido, \
        "una indicación explícita aquí vuelve a pisar el criterio"
