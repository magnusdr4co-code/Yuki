"""
Una imagen pedida en el DM la pinta Yuki en el turno, no el encargo de portada.

Reconstruye el incidente del 22 de septiembre. Yuki escribió tres composiciones
en prosa para sus avatares y el Productor pidió «genera tres imágenes con esas
composiciones». El pedido entró por el encargo durable —`imagen` acababa de
sumarse al vocabulario de portada—, que no ve la conversación: salió el acuse
de **una** portada, con el concepto sacado de la letra de *Herrumbre y
Escarcha*, y después un fallo sin motivo. Dos veces. Mientras tanto, el arnés
tenía `avatar_generate` e `image_generate` y nadie le llegó a pasar la orden.
"""

import asyncio
import json
import types

import pytest

from src.adapters.encargo import pedido_de_imagen
from src.core.producer_harness import MAX_IMAGENES_POR_TURNO, ProducerHarness

from tests.test_producer_harness import _async_result, agent_for, call


# --- Qué es una imagen suelta y qué es la portada de una obra ----------------

@pytest.mark.parametrize("pedido,cantidad", [
    ("Prueba ahoora aa generar tres imagenes con esas coomposiciones", 3),
    ("Perfecto, genera las imagenes de las tres composiciones.", 3),
    ("genera la imagen del retrato en tinta sumi-e", 1),
    ("genera la imagen y pasamela por aqui de Tinta sumi-e", 1),
    ("genera la portada de Tinta sumi-e y pásamela", 1),
    ("Píntame un retrato", 1),
    ("Vuelve intentar generar laas imagenes sobre :I. Tinta sumi-e...II. Mokuhanga", None),
])
def test_las_frases_del_incidente_son_imagenes_sueltas(pedido, cantidad):
    """Todas las del 22 de septiembre, incluidas las que Yuki sugirió repetir."""
    leido = pedido_de_imagen(pedido)
    assert leido is not None, f"«{pedido}» no se reconoce como orden de imagen"
    assert leido.cantidad == cantidad


@pytest.mark.parametrize("pedido", [
    "Genera la portada del sencillo",
    "hazme sólo la portada del sencillo",
    "genera la canción y su portada",
    "Genera la portada de palabra-8443c227ab",
    "¿Podrías generar una imagen algún día?",
    "Me ha gustado la imagen",
])
def test_la_portada_de_una_obra_o_una_pregunta_no_son_imagen_suelta(pedido):
    """La portada de una canción sigue saliendo de su letra, por el encargo durable."""
    assert pedido_de_imagen(pedido) is None


# --- El camino del producto: el DM del Productor ------------------------------

class AgenteDoble:
    """Anota con qué se llamó al turno del arnés y deja un adjunto real."""

    def __init__(self, adjunto=None):
        self.llamadas = []
        self.adjunto = adjunto
        self.last_producer_media = []

    async def generate_response(self, **kwargs):
        self.llamadas.append(kwargs)
        self.last_producer_media = ([{"path": self.adjunto, "caption": "🎨 Avatar «custom»"}]
                                    if self.adjunto else [])
        return "Pintadas."


class CanalDoble:
    id = 555

    def __init__(self):
        self.textos, self.adjuntos = [], []

    async def send(self, content=None, file=None, **kwargs):
        if file is not None:
            self.adjuntos.append(file.filename)
        elif content:
            self.textos.append(content)


def _adaptador(tmp_path, agente):
    pytest.importorskip("discord")
    from src.adapters.discord_bot import DiscordAdapter
    from src.core.brake import Brake
    from src.tools.media_jobs import MediaJobStore

    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = agente
    adaptador.paired_producer_ids = {"42"}
    adaptador.pairing_path = tmp_path / "pairing.json"
    adaptador.pairing_path.write_text(json.dumps({"paired_ids": ["42"]}), encoding="utf-8")
    adaptador._workflow_tasks, adaptador._active_job_ids = set(), set()
    adaptador.media_jobs = MediaJobStore(str(tmp_path / "jobs"))
    adaptador.brake = Brake()
    return adaptador


def test_tres_imagenes_de_esas_composiciones_van_al_turno_que_ve_la_conversacion(tmp_path):
    """
    El pedido exacto del incidente no abre un encargo durable: llega al arnés
    con la cantidad pedida, y el adjunto real sale en el mismo DM.
    """
    adjunto = tmp_path / "avatar.png"
    adjunto.write_bytes(b"\x89PNG\r\n\x1a\n")
    agente = AgenteDoble(adjunto=str(adjunto))
    adaptador = _adaptador(tmp_path, agente)
    canal = CanalDoble()

    respuesta = asyncio.run(adaptador.handle_producer_dm(
        "42", "Dextrure", "Prueba ahoora aa generar tres imagenes con esas coomposiciones", canal))

    assert adaptador.media_jobs.list_jobs() == [], "la imagen abrió un encargo durable de portada"
    assert "Producción multimedia iniciada" not in respuesta
    assert agente.llamadas and agente.llamadas[0]["producer_tools"] is True
    assert agente.llamadas[0]["pedido_de_imagen"].cantidad == 3
    assert canal.adjuntos == ["avatar.png"]


def test_la_portada_del_sencillo_sigue_siendo_un_encargo_durable(tmp_path):
    agente = AgenteDoble()
    adaptador = _adaptador(tmp_path, agente)

    async def _sin_lanzar(*args, **kwargs):
        return None
    adaptador._run_dm_media_delivery = _sin_lanzar

    async def _correr():
        respuesta = await adaptador.handle_producer_dm(
            "42", "Dextrure", "Genera la portada del sencillo y pásamela", CanalDoble())
        await asyncio.gather(*adaptador._workflow_tasks)
        return respuesta

    respuesta = asyncio.run(_correr())
    assert "Producción multimedia iniciada" in respuesta
    assert agente.llamadas == []
    assert len(adaptador.media_jobs.list_jobs()) == 1


# --- Lo que el arnés dice por su cuenta, sin depender del modelo ------------

def _turno_sin_herramientas():
    return [{"role": "assistant", "content": "Te propongo antes una composición en prosa."}]


def test_una_orden_de_imagen_sin_herramienta_llamada_se_dice_en_la_respuesta(tmp_path):
    """
    El 22 de septiembre Yuki explicó que tenía `avatar_generate` e
    `image_generate` y no llamó a ninguna. Si vuelve a pasar, lo escribe el
    ejecutor, no la prosa.
    """
    agente = agent_for(tmp_path, _turno_sin_herramientas())
    harness = ProducerHarness(agente, pedido_de_imagen=pedido_de_imagen(
        "genera tres imagenes con esas composiciones"))
    respuesta = asyncio.run(harness.run("Yuki", "genera tres imagenes con esas composiciones"))

    assert "no se llamó a ninguna herramienta de imagen" in respuesta
    assert "3 imágenes" in respuesta


def test_la_orden_llega_al_prompt_con_la_cantidad(tmp_path):
    vistos = []
    agente = agent_for(tmp_path, _turno_sin_herramientas())
    original = agente.llm_router.generate_with_tools

    def _mirar(messages, tools, route=None):
        vistos.append(messages[0]["content"])
        return original(messages, tools, route)
    agente.llm_router.generate_with_tools = _mirar

    harness = ProducerHarness(agente, pedido_de_imagen=pedido_de_imagen("genera tres imagenes"))
    asyncio.run(harness.run("Yuki", "genera tres imagenes"))
    assert "ENCARGO DE ESTE TURNO — IMAGEN" in vistos[0]
    assert "3 imágenes" in vistos[0]


def test_menos_imagenes_de_las_pedidas_se_dice(tmp_path):
    (tmp_path / "avatar.png").write_bytes(b"png")
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [call("avatar_generate", {"concept": "I"})]},
        {"role": "assistant", "content": "Aquí están las tres."},
    ]
    agente = agent_for(tmp_path, turnos)
    harness = ProducerHarness(agente, pedido_de_imagen=pedido_de_imagen("genera tres imagenes"))
    respuesta = asyncio.run(harness.run("Yuki", "genera tres imagenes"))
    assert "Se pidieron 3 y salieron 1" in respuesta


def test_una_imagen_fallida_no_lleva_recibo_de_exito(tmp_path):
    """
    Vertex devuelve el fallo como diccionario, no como excepción. El recibo
    —lo único del turno que no escribe el modelo— decía «✓ image_generate».
    """
    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [call("image_generate", {"prompt": "x"})]},
        {"role": "assistant", "content": "No salió."},
    ]
    agente = agent_for(tmp_path, turnos)
    agente.nous_portal.generate_image_frontier = _async_result(
        {"status": "error", "error": "Fallo generando imagen con Vertex: 429"})
    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "genera una imagen"))
    assert "✓ image_generate" not in respuesta
    assert "⚠️ image_generate: error — Fallo generando imagen con Vertex: 429" in respuesta


def test_el_tope_de_imagenes_por_turno_se_aplica_y_no_solo_se_pide(tmp_path):
    """Cada llamada reserva crédito: un bucle del modelo no puede hacer de una frase una serie."""
    (tmp_path / "imagen.png").write_bytes(b"png")
    llamadas = [dict(call("image_generate", {"prompt": f"p{i}"}), id=f"call-{i}")
                for i in range(MAX_IMAGENES_POR_TURNO + 1)]
    turnos = [{"role": "assistant", "content": "", "tool_calls": llamadas},
              {"role": "assistant", "content": "Listo."}]
    agente = agent_for(tmp_path, turnos)
    agente.llm_router.generate_with_tools = lambda messages, tools, route=None: turnos.pop(0)
    harness = ProducerHarness(agente)
    respuesta = asyncio.run(harness.run("Yuki", "genera muchas imagenes"))
    assert len(harness.pending_media) == MAX_IMAGENES_POR_TURNO
    assert "Tope de" in respuesta


def test_un_turno_que_vuelve_antes_no_reenvia_el_adjunto_del_anterior(tmp_path):
    """
    `last_producer_media` sólo se vaciaba en la rama de herramientas: un turno
    que volvía antes —presencia, Model Armor, tabú— dejaba la lista anterior, y
    el adaptador reenviaba la imagen de hace un rato como nueva.
    """
    from src.core.agent import YukiAgent

    agente = YukiAgent.__new__(YukiAgent)
    agente.last_producer_media = [{"path": "/viejo.png", "caption": "🎨"}]
    agente.presence_controller = types.SimpleNamespace(should_respond=lambda *a, **k: False)
    agente.producer_user_id = "42"
    respuesta = asyncio.run(agente.generate_response("42", "Dextrure", "hola"))
    assert respuesta == "NADA_QUE_DECIR"
    assert agente.last_producer_media == []


def test_la_orden_de_imagen_atraviesa_el_agente_hasta_el_arnes(tmp_path, monkeypatch):
    """
    Camino del producto: del `generate_response` del agente al prompt del arnés.
    Las pruebas del arnés construyen `ProducerHarness` a mano; si el agente no
    le pasara la orden, pasarían todas con el fallo dentro.
    """
    from src.core.agent import YukiAgent

    monkeypatch.setenv("DISCORD_PAIRED_PRODUCER_ID", "42")
    agente = YukiAgent()
    agente.presence_controller = types.SimpleNamespace(should_respond=lambda *a, **k: True)
    vistos = []

    def _sin_herramientas(messages, tools, route=None):
        vistos.append(messages[0]["content"])
        return {"role": "assistant", "content": "Te propongo antes otra composición."}
    agente.llm_router = types.SimpleNamespace(generate_with_tools=_sin_herramientas)

    respuesta = asyncio.run(agente.generate_response(
        "42", "Dextrure", "genera tres imagenes con esas composiciones",
        producer_tools=True, active_role="producer",
        pedido_de_imagen=pedido_de_imagen("genera tres imagenes con esas composiciones")))

    assert "ENCARGO DE ESTE TURNO — IMAGEN" in vistos[0]
    assert "no se llamó a ninguna herramienta de imagen" in respuesta


def test_la_frase_que_yuki_ofrece_para_repetir_un_encargo_lo_dispara():
    """
    La mañana del 22 de septiembre Yuki pidió cuatro veces que se lo repitieran
    con frases que no disparaban nada. La que ofrece ahora es una constante, y
    ésta es la prueba de que el adaptador la reconoce como encargo durable.
    """
    from src.adapters.discord_intents import looks_like_media_delivery_request
    from src.core.producer_harness import FRASE_DE_ENCARGO, POLICY

    assert f"«{FRASE_DE_ENCARGO}»" in POLICY
    assert looks_like_media_delivery_request(FRASE_DE_ENCARGO)
    assert pedido_de_imagen(FRASE_DE_ENCARGO) is None
