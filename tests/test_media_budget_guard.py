"""
El presupuesto frena al cliente de medios antes de llamar al proveedor.

Es la diferencia entre acotar el gasto y contarlo: si la comprobación ocurriera
después, el segundo de vídeo ya estaría facturado. Aquí el doble del SDK cuenta
sus invocaciones, así que «no se llamó» es verificable, no una promesa.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.spend_budget import IMAGENES, MUSICA_PISTAS, VIDEO_SEGUNDOS, SpendLedger  # noqa: E402
from src.tools.vertex_media import VertexMediaClient  # noqa: E402
from tests.test_nous_tools import (  # noqa: E402
    ClienteGenaiFalso, ClienteMusicaFalso, sdk_de_google_simulado,
)


def _motor(tmp_path, libro, cliente):
    return VertexMediaClient(
        project_id="yuki-diva", client=cliente, budget=libro,
        art_dir=str(tmp_path), music_dir=str(tmp_path), video_dir=str(tmp_path),
        music_location="global",
    )


def test_video_agotado_no_llega_al_proveedor(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"), limits={VIDEO_SEGUNDOS: 8})
    cliente = ClienteGenaiFalso()
    motor = _motor(tmp_path, libro, cliente)

    with sdk_de_google_simulado():
        primero = asyncio.run(motor.generate_video("muelle bajo la lluvia", duration_seconds=8))
        segundo = asyncio.run(motor.generate_video("niebla sobre el metal", duration_seconds=8))

    assert primero["status"] == "success"
    assert segundo["status"] == "error"
    assert segundo["budget_exceeded"] is True
    assert "8" in segundo["error"]
    # El doble sólo registra la última llamada: si hubiera habido una segunda,
    # el prompt sería el del segundo clip.
    assert cliente.recibido["prompt"] == "muelle bajo la lluvia"
    assert libro.today()[VIDEO_SEGUNDOS] == 8


class ClienteVideoQueFalla(ClienteGenaiFalso):
    """Veo devolviendo 503: el gasto no debe anotarse por haberlo intentado."""

    def generate_videos(self, model, prompt=None, image=None, config=None, **kwargs):
        raise RuntimeError("Veo devolvió 503")


def test_un_fallo_del_proveedor_no_se_cobra(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"), limits={VIDEO_SEGUNDOS: 24})
    motor = _motor(tmp_path, libro, ClienteVideoQueFalla())

    with sdk_de_google_simulado():
        resultado = asyncio.run(motor.generate_video("muelle", duration_seconds=8))

    assert resultado["status"] == "error"
    assert libro.today().get(VIDEO_SEGUNDOS, 0) == 0


def test_musica_e_imagen_tambien_se_acotan(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"),
                        limits={MUSICA_PISTAS: 1, IMAGENES: 0})
    motor_musica = _motor(tmp_path, libro, ClienteMusicaFalso())

    with sdk_de_google_simulado():
        primera = asyncio.run(motor_musica.generate_music("koto y escarcha", duration_seconds=90))
        segunda = asyncio.run(motor_musica.generate_music("otra pista", duration_seconds=90))
        imagen = asyncio.run(_motor(tmp_path, libro, ClienteGenaiFalso()).generate_image("portada"))

    assert primera["status"] == "success"
    assert segunda["status"] == "error" and segunda["budget_exceeded"]
    assert imagen["status"] == "error" and imagen["budget_exceeded"]


def test_el_presupuesto_del_dia_se_comparte_entre_procesos(tmp_path):
    """Daemon y Salón usan el mismo libro: lo gastado por uno acota al otro."""
    ruta = str(tmp_path / "l.json")
    daemon = _motor(tmp_path, SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 8}), ClienteGenaiFalso())
    salon = _motor(tmp_path, SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 8}), ClienteGenaiFalso())

    with sdk_de_google_simulado():
        assert asyncio.run(daemon.generate_video("uno", duration_seconds=8))["status"] == "success"
        segundo = asyncio.run(salon.generate_video("dos", duration_seconds=8))

    assert segundo["status"] == "error" and segundo["budget_exceeded"]
