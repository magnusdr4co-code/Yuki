"""
El pedido decide qué se produce, y llega hasta el prompt.

Reconstruye dos fallos del incidente del 9 de septiembre
(`docs/INCIDENTE_ENCARGO_MULTIMEDIA.md`, B7 y B8): los pasos del trabajo eran
una tupla fija, así que una portada pedida **no podía** salir —y nadie lo
decía—, y «vuelve a hacerlo, esta vez con X» devolvía lo mismo por
construcción, porque el texto del pedido no entraba en ningún prompt.
"""

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("discord")

from src.adapters.discord_bot import DiscordAdapter  # noqa: E402
from src.adapters.encargo import leer_encargo  # noqa: E402
from src.tools.media_jobs import MediaJobStore  # noqa: E402


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


class PortalDoble:
    """Anota cada prompt facturado: es lo que permite ver si el pedido llegó."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.prompts_cancion = []
        self.prompts_clip = []

    async def generate_music_flow(self, **kwargs):
        self.prompts_cancion.append(kwargs.get("prompt", ""))
        destino = self.tmp_path / f"cancion_{len(self.prompts_cancion)}.mp3"
        destino.write_bytes(b"audio")
        return {"status": "success", "local_path": str(destino)}

    async def generate_video_frontier(self, **kwargs):
        self.prompts_clip.append(kwargs.get("prompt", ""))
        destino = self.tmp_path / f"clip_{len(self.prompts_clip)}.mp4"
        destino.write_bytes(b"video")
        return {"status": "success", "local_path": str(destino)}


class CreadorDoble:
    """`create_single_cover` programable: puede devolver marcador simulado."""

    def __init__(self, tmp_path, simulada=False):
        self.tmp_path = tmp_path
        self.simulada = simulada
        self.conceptos = []

    async def create_single_cover(self, track_title, visual_concept, **kwargs):
        self.conceptos.append(visual_concept)
        destino = self.tmp_path / f"portada_{len(self.conceptos)}.png"
        destino.write_bytes(b"png")
        return {"status": "success", "local_path": str(destino),
                "simulated": self.simulada, "track_title": track_title,
                "note": "marcador" if self.simulada else None}


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


def _adaptador(tmp_path, monkeypatch, simulada=False):
    monkeypatch.setenv("DISCORD_PAIRED_PRODUCER_ID", "42")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    portal = PortalDoble(tmp_path)
    creador = CreadorDoble(tmp_path, simulada=simulada)
    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = types.SimpleNamespace(
        nous_portal=portal, media_creator=creador,
        creation_library=LibraryDoble(tmp_path), discord_adapter=None,
    )
    adaptador.paired_producer_ids = {"42"}
    adaptador._workflow_tasks = set()
    adaptador._active_job_ids = set()
    adaptador.media_jobs = MediaJobStore(str(tmp_path / "jobs"))
    adaptador._concat_videos = staticmethod(lambda paths: _final(tmp_path))
    return adaptador, portal, creador


def _final(tmp_path):
    destino = tmp_path / "final.mp4"
    destino.write_bytes(b"final")
    return str(destino)


def _correr(adaptador, pedido):
    canal = CanalDoble()
    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", pedido, canal))
    return canal


def test_la_portada_pedida_se_produce_y_se_adjunta(tmp_path, monkeypatch):
    """`create_single_cover` existía y no había paso que lo llamara: se pedía y no salía."""
    adaptador, _portal, creador = _adaptador(tmp_path, monkeypatch)
    canal = _correr(adaptador, "hazme sólo la portada del sencillo")

    assert creador.conceptos, "el pedido nombraba una portada y ningún paso la generó"
    assert any(nombre.startswith("portada_") for nombre in canal.adjuntos)


def test_lo_que_el_pedido_no_nombra_no_se_factura(tmp_path, monkeypatch):
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    _correr(adaptador, "hazme sólo la portada del sencillo")

    assert portal.prompts_cancion == [], "no se pidió canción y se pagó una"
    assert portal.prompts_clip == [], "no se pidió vídeo y se pagaron segundos de Veo"


def test_negar_una_pieza_no_la_encarga(tmp_path, monkeypatch):
    """«sin vídeo» nombra el vídeo; la regla de alcance no puede confundir eso con pedirlo."""
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    _correr(adaptador, "la canción y la portada, sin vídeo")

    assert len(portal.prompts_cancion) == 1
    assert portal.prompts_clip == []


def test_el_pedido_viaja_al_prompt(tmp_path, monkeypatch):
    """«esta vez con más percusión» devolvía lo mismo porque el prompt era constante."""
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    _correr(adaptador, "vuelve a hacer la canción y el vídeo, esta vez con más percusión")

    assert "más percusión" in portal.prompts_cancion[0]
    assert all("más percusión" in prompt for prompt in portal.prompts_clip)


def test_pedir_dos_segmentos_no_paga_cuatro(tmp_path, monkeypatch):
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    canal = _correr(adaptador, "dame dos segmentos de vídeo")

    assert len(portal.prompts_clip) == 2
    assert "final.mp4" in canal.adjuntos, "dos segmentos también se montan y se entregan"
    assert adaptador.media_jobs.resumable() == [], "el trabajo se cierra con los pasos que pedía"


def test_reanudar_recompone_los_mismos_pasos(tmp_path, monkeypatch):
    """
    El plan sale del texto del pedido, y al reanudar el texto es `job.order`.

    Si los identificadores de paso cambiasen entre arranques, la reanudación
    daría por «no hecho» lo ya pagado y volvería a facturarlo.
    """
    pedido = "hazme la canción y dos segmentos de vídeo, esta vez con más percusión"
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    _correr(adaptador, pedido)
    hechos = {p.id for p in adaptador.media_jobs.list_jobs()[0].steps}

    plan = leer_encargo(pedido, 4)
    assert {identificador for identificador, _ in plan.steps()} == hechos
    assert len(portal.prompts_clip) == 2


def test_una_portada_simulada_no_se_da_por_portada(tmp_path, monkeypatch):
    """Un marcador con `simulated` no es obra: darlo por bueno es el vicio de siempre."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch, simulada=True)
    canal = _correr(adaptador, "sólo la portada")

    assert not any(nombre.startswith("portada_") for nombre in canal.adjuntos)
    assert any("No se generó portada" in texto for texto in canal.textos)


def test_el_alcance_se_acusa_antes_de_gastar(tmp_path, monkeypatch):
    """El Productor tiene que saber qué no va a salir antes, no por su ausencia al final."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)

    async def _lanzar():
        acuse = adaptador._launch_dm_media_delivery("42", "Productor", "sólo la portada", CanalDoble())
        for tarea in list(adaptador._workflow_tasks):
            tarea.cancel()
        return acuse

    acuse = asyncio.run(_lanzar())
    assert "una portada" in acuse
    assert "segmento" not in acuse
