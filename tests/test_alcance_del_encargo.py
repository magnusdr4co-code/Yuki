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


def _lanzar(adaptador, pedido):
    """Acuse del lanzamiento, con la tarea cancelada: aquí interesa lo que dice, no lo que gasta."""
    async def _correr():
        acuse = adaptador._launch_dm_media_delivery("42", "Productor", pedido, CanalDoble())
        for tarea in list(adaptador._workflow_tasks):
            tarea.cancel()
        return acuse

    return asyncio.run(_correr())


def test_el_mismo_pedido_dos_veces_no_se_paga_dos_veces(tmp_path, monkeypatch):
    """~96 s de vídeo facturados para entregar tres veces lo mismo."""
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    pedido = "hazme la canción y dos segmentos de vídeo"
    _correr(adaptador, pedido)
    gastado = len(portal.prompts_clip)

    acuse = _lanzar(adaptador, pedido)

    assert "palabra por palabra" in acuse
    assert "de todos modos" in acuse, "negarse sin decir cómo seguir es dejar al Productor atascado"
    assert len(portal.prompts_clip) == gastado, "el pedido repetido no puede volver a facturar"


def test_repetir_a_sabiendas_sigue_siendo_posible(tmp_path, monkeypatch):
    """
    La guarda avisa; no decide por él.

    Y el consejo que da tiene que seguir valiendo la segunda vez: un pedido
    forzado, repetido idéntico, no puede volver a bloquearse diciéndole que
    añada una frase que ya está escrita.
    """
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    pedido = "hazme la canción y dos segmentos de vídeo, de todos modos"
    _correr(adaptador, pedido)

    assert "Producción multimedia iniciada" in _lanzar(adaptador, pedido)


def test_un_pedido_distinto_no_se_confunde_con_una_repeticion(tmp_path, monkeypatch):
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    _correr(adaptador, "hazme la canción y dos segmentos de vídeo")

    acuse = _lanzar(adaptador, "hazme la canción y dos segmentos de vídeo, con más percusión")

    assert "Producción multimedia iniciada" in acuse


def test_el_acuse_dice_lo_que_va_a_costar(tmp_path, monkeypatch):
    """Se planificó el encargo sin mirar el presupuesto ni mencionarlo."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)

    acuse = _lanzar(adaptador, "hazme la canción y dos segmentos de vídeo")

    assert "16 s de vídeo" in acuse
    assert "Presupuesto de hoy" in acuse


def test_un_encargo_que_no_cabe_hoy_se_dice_al_empezar(tmp_path, monkeypatch):
    """Descubrir el tope a mitad cuesta lo ya generado y una explicación incómoda."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    adaptador.agent.config = {"budget": {"enabled": True, "daily_limits": {"video_segundos": 4}}}

    acuse = _lanzar(adaptador, "hazme dos segmentos de vídeo")

    assert "No cabe hoy" in acuse


def test_ofrecer_el_salon_recibe_respuesta(tmp_path, monkeypatch):
    """«Envíamelo por Salón o por aquí» quedó sin respuesta: ni se usó ni se mencionó."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    monkeypatch.setenv("SALON_API_TOKEN", "clave")

    acuse = _lanzar(adaptador, "hazme la canción y mándamela por el Salón o por aquí")

    assert "/api/outputs/" in acuse


def test_sin_credencial_el_salon_se_declara_incapaz(tmp_path, monkeypatch):
    """Prometer una entrega que el Salón no puede hacer es aparentar una capacidad."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    monkeypatch.delenv("SALON_API_TOKEN", raising=False)

    acuse = _lanzar(adaptador, "hazme la canción y mándamela por el Salón")

    assert "Por el Salón no puedo" in acuse
    assert "SALON_API_TOKEN" in acuse


def test_sin_mencionar_el_salon_no_se_habla_del_salon(tmp_path, monkeypatch):
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)

    assert "Salón" not in _lanzar(adaptador, "hazme la canción")
