"""
Un encargo que se corta no puede quedarse callado.

B9 del incidente del 9 de septiembre: el trabajo de las 5:24 arrancó los cuatro
segmentos y nunca emitió «Vídeo final» —ni eso ni un error—. Dos silencios lo
explican y aquí se vigilan los dos: una cancelación (`CancelledError` hereda de
`BaseException`, así que el `except Exception` del bucle no la ve) y una
reanudación que no se anunciaba al Productor. Y un tercero de la misma familia:
un fallo pasajero de Discord abandonaba un encargo con clips ya pagados.
"""

import asyncio
import logging
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("discord")

import discord  # noqa: E402

from src.adapters.discord_bot import DiscordAdapter  # noqa: E402
from src.tools.media_jobs import MediaJobStore, EN_CURSO, ABANDONADO  # noqa: E402


class LibraryDoble:
    def __init__(self, root):
        self.root = root
        (root / "letra.md").write_text("verso " * 40, encoding="utf-8")

    def list_entries(self):
        return {"entries": [
            {"id": "palabra-aa11bb", "kind": "palabra", "title": "Herrumbre y Escarcha",
             "source": "letra", "path": "letra.md"},
        ]}

    def read_entry(self, entry_id):
        return {"content": "verso largo de la canción " * 20}

    def inventory(self):
        return {}


class PortalQueMuereAMitad:
    """El proveedor no falla: es el proceso el que se apaga durante el clip 2."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.clips = 0

    async def generate_music_flow(self, **kwargs):
        destino = self.tmp_path / "cancion.mp3"
        destino.write_bytes(b"audio")
        return {"status": "success", "local_path": str(destino)}

    async def generate_video_frontier(self, **kwargs):
        self.clips += 1
        if self.clips == 2:
            raise asyncio.CancelledError()
        destino = self.tmp_path / f"clip_{self.clips}.mp4"
        destino.write_bytes(b"video")
        return {"status": "success", "local_path": str(destino)}


class CanalDoble:
    def __init__(self):
        self.id = 555
        self.textos = []
        self.adjuntos = []

    async def send(self, content=None, file=None, **kwargs):
        if file is not None:
            self.adjuntos.append(getattr(file, "filename", "?"))
        elif content:
            self.textos.append(content)


class ClienteDoble:
    """Cliente de Discord que responde lo que pida cada prueba al buscar al Productor."""

    def __init__(self, canal=None, excepcion=None):
        self.canal = canal
        self.excepcion = excepcion

    def get_user(self, _id):
        return None

    async def fetch_user(self, _id):
        if self.excepcion is not None:
            raise self.excepcion
        return types.SimpleNamespace(dm_channel=self.canal)


def _adaptador(tmp_path, monkeypatch, portal=None):
    monkeypatch.setenv("DISCORD_PAIRED_PRODUCER_ID", "42")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = types.SimpleNamespace(
        nous_portal=portal, media_creator=None,
        creation_library=LibraryDoble(tmp_path), discord_adapter=None,
    )
    adaptador.paired_producer_ids = {"42"}
    adaptador._workflow_tasks = set()
    adaptador._active_job_ids = set()
    adaptador.media_jobs = MediaJobStore(str(tmp_path / "jobs"))
    adaptador._concat_videos = staticmethod(lambda paths: None)
    return adaptador


def test_una_cancelacion_a_mitad_deja_rastro(tmp_path, monkeypatch, caplog):
    """
    El proceso se apaga durante un clip: el trabajo tiene que quedar guardado,
    reanudable y anotado. Antes no quedaba ni una línea en el log.
    """
    portal = PortalQueMuereAMitad(tmp_path)
    adaptador = _adaptador(tmp_path, monkeypatch, portal)
    canal = CanalDoble()

    with caplog.at_level(logging.WARNING, logger="Yuki.DiscordAdapter"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", "la canción y el vídeo", canal))

    assert any("cancelada a mitad" in registro.message for registro in caplog.records), \
        "una cancelación sin rastro es exactamente el silencio de B9"
    reanudables = adaptador.media_jobs.resumable()
    assert len(reanudables) == 1, "el trabajo cortado tiene que seguir siendo reanudable"
    assert reanudables[0].step("cancion").is_done()
    assert reanudables[0].step("clip_1").is_done()


def test_un_fallo_pasajero_de_discord_no_tira_el_encargo(tmp_path, monkeypatch):
    """Un 500 es de este minuto; el encargo lleva clips pagados y se reintenta."""
    adaptador = _adaptador(tmp_path, monkeypatch)
    job = adaptador.media_jobs.create(requester_id="42", order="pedido",
                                      steps=[("cancion", "cancion"), ("entrega", "entrega")])
    adaptador.client = ClienteDoble(excepcion=discord.HTTPException(
        types.SimpleNamespace(status=500, reason="Internal Server Error"), "Discord de bajón"))

    assert asyncio.run(adaptador.resume_pending_media_jobs()) == 0
    assert adaptador.media_jobs.get(job.id).status == EN_CURSO
    assert [t.id for t in adaptador.media_jobs.resumable()] == [job.id]


def test_una_cuenta_borrada_si_cierra_el_encargo(tmp_path, monkeypatch):
    """Sin destinatario no hay entrega posible: eso sí es definitivo."""
    adaptador = _adaptador(tmp_path, monkeypatch)
    job = adaptador.media_jobs.create(requester_id="42", order="pedido",
                                      steps=[("cancion", "cancion"), ("entrega", "entrega")])
    adaptador.client = ClienteDoble(excepcion=discord.NotFound(
        types.SimpleNamespace(status=404, reason="Not Found"), "esa cuenta ya no existe"))

    assert asyncio.run(adaptador.resume_pending_media_jobs()) == 0
    assert adaptador.media_jobs.get(job.id).status == ABANDONADO


def test_retomar_un_encargo_se_dice_en_el_dm(tmp_path, monkeypatch):
    """El Productor vio cuatro segmentos y después nada; enterarse no puede exigir preguntar."""
    adaptador = _adaptador(tmp_path, monkeypatch)
    job = adaptador.media_jobs.create(requester_id="42", order="pedido",
                                      steps=[("cancion", "cancion"), ("entrega", "entrega")])
    canal = CanalDoble()
    adaptador.client = ClienteDoble(canal=canal)
    lanzados = []
    adaptador._spawn_media_job = lambda *args, **kwargs: bool(lanzados.append(args[0].id)) or True

    assert asyncio.run(adaptador.resume_pending_media_jobs()) == 1
    assert lanzados == [job.id]
    assert any(f"Retomo el trabajo `{job.id}`" in texto for texto in canal.textos)
