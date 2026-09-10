"""
Cuando el resultado se repite, se dice al entregarlo.

A3 del incidente del 9 de septiembre: Yuki explicó por qué la canción no salía
cantada, el turno siguiente produjo exactamente el mismo resultado —refutando su
diagnóstico— y no lo mencionó.

Retractarse de una explicación no se puede exigir con un marcador de texto. Que
el resultado se repite **sí** es comprobable, y decirlo cierra el hueco por
donde entra la explicación nueva: si el fichero es el mismo, o la limitación es
la misma, consta en la entrega y no depende de que nadie se acuerde.
"""

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("discord")

from src.adapters.discord_bot import DiscordAdapter  # noqa: E402
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
    """Devuelve siempre la misma maqueta instrumental, como pasó de verdad."""

    def __init__(self, tmp_path, contenido=b"audio", nota=None):
        self.tmp_path = tmp_path
        self.contenido = contenido
        self.nota = nota
        self.veces = 0

    async def generate_music_flow(self, **kwargs):
        self.veces += 1
        destino = self.tmp_path / f"cancion_{self.veces}.mp3"
        destino.write_bytes(self.contenido)
        return {"status": "success", "local_path": str(destino),
                "sung": False, "note": self.nota or "Maqueta local: no es una canción cantada."}

    async def generate_video_frontier(self, **kwargs):
        raise AssertionError("estas pruebas no piden vídeo")


class CanalDoble:
    def __init__(self):
        self.id = 555
        self.textos = []
        self.pies = []

    async def send(self, content=None, file=None, **kwargs):
        if file is not None:
            self.pies.append(content or "")
        elif content:
            self.textos.append(content)


def _adaptador(tmp_path, monkeypatch, portal):
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


def _encargar(adaptador, pedido):
    canal = CanalDoble()
    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", pedido, canal))
    return canal


def test_el_mismo_fichero_entregado_dos_veces_se_dice(tmp_path, monkeypatch):
    """El turno siguiente produjo el mismo resultado y no se mencionó."""
    portal = PortalDoble(tmp_path)
    adaptador = _adaptador(tmp_path, monkeypatch, portal)

    primera = _encargar(adaptador, "hazme la canción")
    segunda = _encargar(adaptador, "hazme la canción, esta vez cantada de verdad")

    assert portal.veces == 2, "los dos encargos generaron; esto no va de la guarda de repetición"
    assert not any("mismo archivo" in pie for pie in primera.pies)
    assert any("Es el mismo archivo que ya entregué" in pie for pie in segunda.pies)


def test_la_misma_limitacion_se_nombra_aunque_el_fichero_cambie(tmp_path, monkeypatch):
    """
    Un archivo distinto con la misma limitación es justo el caso del incidente:
    sonaba diferente y seguía sin ser canto, y eso no lo arregla repetir.
    """
    portal = PortalDoble(tmp_path)
    adaptador = _adaptador(tmp_path, monkeypatch, portal)
    _encargar(adaptador, "hazme la canción")
    portal.contenido = b"otro audio distinto de verdad"

    segunda = _encargar(adaptador, "hazme la canción, ahora con la letra incrustada")

    assert any("misma limitación" in pie for pie in segunda.pies)
    assert not any("mismo archivo" in pie for pie in segunda.pies)


def test_un_resultado_nuevo_no_lleva_aviso(tmp_path, monkeypatch):
    """Un aviso que sale siempre no informa de nada."""
    portal = PortalDoble(tmp_path)
    adaptador = _adaptador(tmp_path, monkeypatch, portal)
    _encargar(adaptador, "hazme la canción")
    portal.contenido = b"un audio completamente distinto"
    portal.nota = "🎵 Canción con letra — archivo generado"

    segunda = _encargar(adaptador, "hazme la canción otra vez")

    assert not any("⚠️" in pie for pie in segunda.pies)


def test_el_primer_encargo_nunca_avisa(tmp_path, monkeypatch):
    adaptador = _adaptador(tmp_path, monkeypatch, PortalDoble(tmp_path))

    primera = _encargar(adaptador, "hazme la canción")

    assert primera.pies and not any("⚠️" in pie for pie in primera.pies)


def test_no_poder_comparar_no_es_haber_comparado(tmp_path):
    """Sin la lectura hecha, callar es lo único honesto."""
    from src.adapters.discord_bot import _mismo_contenido

    assert _mismo_contenido(str(tmp_path / "no-existe.mp3"), str(tmp_path / "tampoco.mp3")) is False
