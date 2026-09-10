"""
Telegram registraba en log y no llegaba a ningún seguidor.

M6 / L6. Era peor que «simulado»: `start_polling` escribía «Bot de Telegram de
Yuki iniciado» con un token configurado y no iniciaba nada, y `broadcast_drop`
registraba `📢 [TELEGRAM BROADCAST]` con el texto del lanzamiento y devolvía
`None`, así que la tarea de las 07:30 daba el día por difundido. Nadie recibía
nada y nada fallaba.
"""

import asyncio
import logging
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.adapters.telegram_bot import DECLARACION, TelegramAdapter  # noqa: E402


class ClienteFalso:
    """Sustituye a la red: anota cada llamada y devuelve lo que se le diga."""

    def __init__(self, ok=True, descripcion="chat not found"):
        self.ok = ok
        self.descripcion = descripcion
        self.llamadas = []

    async def post(self, url, data=None, files=None):
        self.llamadas.append({"url": url, "data": data or {},
                              "ficheros": sorted((files or {}).keys())})
        cuerpo = {"ok": True, "result": {"message_id": len(self.llamadas)}} if self.ok else {
            "ok": False, "description": self.descripcion}
        return types.SimpleNamespace(json=lambda: cuerpo)


def _adaptador(monkeypatch, cliente=None, token="123:abc", chat="-100", frenada=None):
    monkeypatch.setenv("TELEGRAM_DEFAULT_CHAT_ID", chat)
    agente = types.SimpleNamespace(telegram_adapter=None)
    freno = types.SimpleNamespace(blocked_reason=lambda ambito: frenada)
    return TelegramAdapter(agente, token=token, cliente=cliente, brake=freno)


def test_una_difusion_real_se_entrega_y_consta(monkeypatch):
    cliente = ClienteFalso()
    adaptador = _adaptador(monkeypatch, cliente)

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece sobre el metal."))

    assert resultado["entregado"] is True
    assert cliente.llamadas[0]["url"].endswith("/sendMessage")
    assert cliente.llamadas[0]["data"]["chat_id"] == "-100"
    assert DECLARACION in cliente.llamadas[0]["data"]["text"], \
        "todo material sintético sale declarado (Artículo 50)"


def test_sin_token_no_se_da_por_difundido(monkeypatch):
    """Registraba una línea con aspecto de difusión y devolvía None."""
    cliente = ClienteFalso()
    adaptador = _adaptador(monkeypatch, cliente, token="")

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece."))

    assert resultado["entregado"] is False
    assert "TELEGRAM_BOT_TOKEN" in resultado["motivo"]
    assert cliente.llamadas == [], "no puede salir nada a la red sin token"


def test_sin_destino_tampoco(monkeypatch):
    adaptador = _adaptador(monkeypatch, ClienteFalso(), chat="")

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece."))

    assert resultado["entregado"] is False
    assert "TELEGRAM_DEFAULT_CHAT_ID" in resultado["motivo"]


def test_el_freno_para_la_publicacion_antes_de_la_red(monkeypatch):
    """Frenar no es enmudecer, pero la publicación sí para: la invariante 2."""
    cliente = ClienteFalso()
    adaptador = _adaptador(monkeypatch, cliente, frenada="freno de mano echado")

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece."))

    assert resultado["entregado"] is False
    assert "frenado" in resultado["motivo"]
    assert cliente.llamadas == []


def test_un_fallo_del_servidor_no_es_una_entrega(monkeypatch):
    """Nada se da por entregado si no consta la respuesta del servidor."""
    cliente = ClienteFalso(ok=False)
    adaptador = _adaptador(monkeypatch, cliente)

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece."))

    assert resultado["entregado"] is False
    assert "chat not found" in resultado["motivo"]


def test_una_caida_de_red_tampoco(monkeypatch):
    def _caida(url, datos, fichero):
        raise OSError("sin ruta al host")

    monkeypatch.setattr("src.adapters.telegram_bot._publicar", _caida)
    adaptador = _adaptador(monkeypatch, cliente=None)

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece."))

    assert resultado["entregado"] is False
    assert "OSError" in resultado["motivo"]


def test_la_obra_adjunta_se_marca_antes_de_salir(tmp_path, monkeypatch):
    """Se marca antes de entregar; hay una segunda puerta por si aparece un camino nuevo."""
    cliente = ClienteFalso()
    adaptador = _adaptador(monkeypatch, cliente)
    portada = tmp_path / "portada.png"
    portada.write_bytes(b"\x89PNG imagen")
    marcados = []
    adaptador.agent.marker = types.SimpleNamespace(
        is_marked=lambda ruta: False,
        mark=lambda ruta, modelo, prompt, tipo: marcados.append(ruta) or {"marked": True})

    resultado = asyncio.run(adaptador.broadcast_drop("Amanece.", image_path=str(portada)))

    assert marcados == [str(portada)]
    assert resultado["entregado"] is True
    assert cliente.llamadas[0]["ficheros"] == ["photo"]
    assert DECLARACION in cliente.llamadas[0]["data"]["caption"]


def test_el_mismo_lanzamiento_no_sale_dos_veces(tmp_path, monkeypatch):
    """El texto ya viajó como pie del adjunto; repetirlo lo manda dos veces."""
    cliente = ClienteFalso()
    adaptador = _adaptador(monkeypatch, cliente)
    adaptador.agent.marker = types.SimpleNamespace(is_marked=lambda ruta: True, mark=lambda *a: None)
    portada = tmp_path / "portada.png"
    portada.write_bytes(b"\x89PNG")

    asyncio.run(adaptador.broadcast_drop("Amanece.", image_path=str(portada)))

    assert [llamada["url"].rsplit("/", 1)[-1] for llamada in cliente.llamadas] == ["sendPhoto"]


def test_la_entrada_no_se_anuncia_como_iniciada(monkeypatch):
    """Escribía «Bot de Telegram de Yuki iniciado» sin abrir nada."""
    adaptador = _adaptador(monkeypatch, ClienteFalso())

    estado = asyncio.run(adaptador.start_polling())

    assert estado["polling"] is False
    assert estado["salida_disponible"] is True


def test_la_tarea_matutina_no_da_por_difundido_lo_que_no_salio(monkeypatch, caplog):
    """
    El camino del producto: la tarea de las 07:30 descartaba el resultado, así
    que informaba igual con la difusión hecha y sin hacer.
    """
    from src.scheduler.tasks import AutonomousTasks

    class AdaptadorMudo:
        async def broadcast_drop(self, text, image_path=None, audio_path=None):
            return {"entregado": False, "motivo": "sin TELEGRAM_BOT_TOKEN declarado",
                    "mensajes": []}

    agente = types.SimpleNamespace(
        telegram_adapter=AdaptadorMudo(),
        nous_portal=types.SimpleNamespace(),
        # Ánimo bajo el umbral de imagen (0.4) y energía suficiente: sin medios
        # de por medio, el camino es el de la difusión, que es lo que importa.
        vital_state=types.SimpleNamespace(energy=0.9, mood=0.2),
    )
    agente.generate_response = _texto_matutino
    tareas = AutonomousTasks(agente)

    with caplog.at_level(logging.WARNING):
        resultado = asyncio.run(tareas.morning_inspiration_drop())

    assert resultado["difusion"]["entregado"] is False
    assert "TELEGRAM_BOT_TOKEN" in resultado["difusion"]["motivo"]
    # Y consta en el log: un cron que se queda callado cuando no entrega es la
    # forma más segura de que nadie se entere durante meses.
    assert any("no difundida" in registro.message for registro in caplog.records)


async def _texto_matutino(*args, **kwargs):
    return "La escarcha sobre el muelle."


if __name__ == "__main__":
    pytest.main([__file__])
