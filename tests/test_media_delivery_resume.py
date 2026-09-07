"""
Reanudación real de un encargo multimedia interrumpido.

Reproduce el limitador que documentaba `docs/PRODUCTION_STATUS.md`: el trabajo
se corta a mitad (un reinicio del daemon) y hay que comprobar dos cosas al
volver — que el encargo no se pierde y que **no se vuelve a pagar** lo ya
generado, porque Veo se factura por segundo.
"""

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("discord")

from src.adapters.discord_bot import DiscordAdapter, MEDIA_STORYBOARD  # noqa: E402
from src.tools.media_jobs import MediaJobStore  # noqa: E402


class LibraryDoble:
    """Biblioteca con una letra, un guion y una imagen ya archivados."""

    def __init__(self, root):
        self.root = root
        self.inventarios = 0
        (root / "letra.md").write_text("verso " * 40, encoding="utf-8")
        (root / "portada.png").write_bytes(b"png")

    def list_entries(self):
        return {"entries": [
            {"id": "1", "kind": "palabra", "title": "Letra de herrumbre", "source": "letra", "path": "letra.md"},
            {"id": "2", "kind": "visual", "title": "Portada herrumbre", "source": "arte", "path": "portada.png"},
        ]}

    def read_entry(self, entry_id):
        return {"content": "verso largo de la canción " * 20}

    def inventory(self):
        self.inventarios += 1
        return {}


class PortalDoble:
    """Proveedor multimedia programable: cuenta cada generación facturable."""

    def __init__(self, tmp_path, fallar_desde_clip=None, presupuesto_desde_clip=None):
        self.tmp_path = tmp_path
        self.fallar_desde_clip = fallar_desde_clip
        self.presupuesto_desde_clip = presupuesto_desde_clip
        self.canciones = 0
        self.clips = 0

    async def generate_music_flow(self, **kwargs):
        self.canciones += 1
        destino = self.tmp_path / f"cancion_{self.canciones}.mp3"
        destino.write_bytes(b"audio")
        return {"status": "success", "local_path": str(destino)}

    async def generate_video_frontier(self, **kwargs):
        self.clips += 1
        if self.presupuesto_desde_clip is not None and self.clips >= self.presupuesto_desde_clip:
            return {"status": "error", "budget_exceeded": True,
                    "error": "presupuesto diario agotado para video_segundos: llevas 16 de 16"}
        if self.fallar_desde_clip is not None and self.clips >= self.fallar_desde_clip:
            return {"status": "error", "error": "Veo devolvió 503"}
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


def _adaptador(tmp_path, portal, monkeypatch):
    monkeypatch.setenv("DISCORD_PAIRED_PRODUCER_ID", "42")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    agente = types.SimpleNamespace(
        nous_portal=portal,
        creation_library=LibraryDoble(tmp_path),
        discord_adapter=None,
    )
    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = agente
    adaptador.paired_producer_ids = {"42"}
    adaptador._workflow_tasks = set()
    adaptador.media_jobs = MediaJobStore(str(tmp_path / "jobs"))
    # El montaje real invoca ffmpeg; aquí sólo interesa el estado del trabajo.
    adaptador._concat_videos = staticmethod(
        lambda paths: str(tmp_path / "final.mp4") if _escribir(tmp_path / "final.mp4") else None
    )
    return adaptador


def _escribir(path):
    path.write_bytes(b"final")
    return True


def test_reinicio_reanuda_sin_regenerar_lo_ya_pagado(tmp_path, monkeypatch):
    # --- Primer arranque: la canción sale, el tercer clip falla -------------
    portal = PortalDoble(tmp_path, fallar_desde_clip=3)
    adaptador = _adaptador(tmp_path, portal, monkeypatch)
    canal = CanalDoble()

    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", "procede con la canción y el vídeo", canal))

    trabajos = adaptador.media_jobs.resumable()
    assert len(trabajos) == 1, "un trabajo cortado a mitad debe quedar reanudable"
    interrumpido = trabajos[0]
    assert interrumpido.step("cancion").is_done()
    assert [p.id for p in interrumpido.pending_steps()] == ["clip_3", "clip_4", "montaje", "entrega"]
    assert portal.canciones == 1
    assert portal.clips == 3
    # La canción y los segmentos que sí existen se entregan; nada se anuncia sin fichero.
    assert canal.adjuntos == ["cancion_1.mp3", "clip_1.mp4", "clip_2.mp4"]

    # --- Segundo arranque: proceso nuevo, sólo el disco --------------------
    portal2 = PortalDoble(tmp_path)
    adaptador2 = _adaptador(tmp_path, portal2, monkeypatch)
    adaptador2.media_jobs = MediaJobStore(str(tmp_path / "jobs"))
    canal2 = CanalDoble()
    recuperado = adaptador2.media_jobs.resumable()[0]

    asyncio.run(adaptador2._run_dm_media_delivery("42", "Productor", recuperado.order, canal2, job=recuperado))

    assert portal2.canciones == 0, "la canción ya verificada no se regenera"
    assert portal2.clips == len(MEDIA_STORYBOARD) - 2, "sólo se pagan los clips que faltaban"
    assert "final.mp4" in canal2.adjuntos
    assert adaptador2.media_jobs.resumable() == []
    assert adaptador2.media_jobs.get(recuperado.id).status == "terminado"


def test_sin_letra_verificable_el_trabajo_se_abandona_y_se_dice(tmp_path, monkeypatch):
    portal = PortalDoble(tmp_path)
    adaptador = _adaptador(tmp_path, portal, monkeypatch)
    adaptador.agent.creation_library.list_entries = lambda: {"entries": []}
    canal = CanalDoble()

    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", "procede con la canción", canal))

    assert portal.canciones == 0 and portal.clips == 0
    assert any("Biblioteca" in t for t in canal.textos)
    assert adaptador.media_jobs.resumable() == []
    assert adaptador.media_jobs.list_jobs()[0].status == "abandonado"


def test_paso_agotado_no_vuelve_a_facturar(tmp_path, monkeypatch):
    portal = PortalDoble(tmp_path, fallar_desde_clip=1)
    adaptador = _adaptador(tmp_path, portal, monkeypatch)

    # Primera orden y después sólo reanudaciones: nadie vuelve a pedirlo.
    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", "canción y vídeo", CanalDoble()))
    for _ in range(5):
        trabajos = adaptador.media_jobs.resumable()
        if not trabajos:
            break
        asyncio.run(adaptador._run_dm_media_delivery(
            "42", "Productor", trabajos[0].order, CanalDoble(), job=trabajos[0]))

    # Tres intentos por paso: al agotarse, el trabajo se cierra en vez de
    # quedar reanudable para siempre gastando en los pasos que sí funcionan.
    assert portal.clips == 3
    assert adaptador.media_jobs.resumable() == []
    assert adaptador.media_jobs.list_jobs()[0].status == "abandonado"


def test_tope_de_presupuesto_aplaza_el_trabajo_sin_gastar_intentos(tmp_path, monkeypatch):
    """
    Un tope de presupuesto no es un fallo del paso: mañana el mismo trabajo cabe.

    Si consumiera intentos, tres días de tope cerrarían un encargo que nunca
    llegó a fallar.
    """
    portal = PortalDoble(tmp_path, presupuesto_desde_clip=3)
    adaptador = _adaptador(tmp_path, portal, monkeypatch)
    canal = CanalDoble()

    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", "canción y vídeo", canal))

    trabajos = adaptador.media_jobs.resumable()
    assert len(trabajos) == 1, "el trabajo sigue vivo, sólo aplazado"
    aplazado = trabajos[0]
    assert aplazado.step("clip_3").attempts == 0, "un tope no gasta intento"
    assert aplazado.step("clip_3").status == "pendiente"
    assert any("presupuesto" in texto for texto in canal.textos)

    # Al día siguiente, con presupuesto, el trabajo termina sin repetir lo pagado.
    portal2 = PortalDoble(tmp_path)
    adaptador2 = _adaptador(tmp_path, portal2, monkeypatch)
    recuperado = adaptador2.media_jobs.resumable()[0]
    asyncio.run(adaptador2._run_dm_media_delivery(
        "42", "Productor", recuperado.order, CanalDoble(), job=recuperado))

    assert portal2.canciones == 0
    assert portal2.clips == 2, "sólo los dos segmentos que faltaban"
    assert adaptador2.media_jobs.get(recuperado.id).status == "terminado"
