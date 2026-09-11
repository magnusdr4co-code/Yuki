"""
Abrir un Salón para otra obra producía igualmente *Herrumbre y Escarcha*.

El mismo defecto que B7/B8 del incidente, en el otro camino de producción: la
letra, la partitura, las tres imágenes y el vídeo de `_run_discord_production`
estaban escritos a mano sobre un título concreto, así que la petición no podía
cambiar nada. Y gastaba en canción, tres imágenes y vídeo sin mencionar el
presupuesto ni decir qué iba a producir.
"""

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("discord")

from src.adapters.discord_bot import DiscordAdapter, TEMA_POR_DEFECTO  # noqa: E402
from src.adapters.discord_intents import extract_production_theme  # noqa: E402


class LibraryDoble:
    def __init__(self):
        self.guardados = []

    def save_text(self, title, content, source=""):
        self.guardados.append(title)
        return {"id": "palabra-1", "path": "x.md"}

    def inventory(self):
        return {"total": len(self.guardados)}


class CreadorDoble:
    def __init__(self):
        self.titulos = []
        self.conceptos = []
        self.partituras = []

    async def compose_beat_structure(self, title, bpm, scale, mood, engine):
        self.partituras.append((title, mood))
        return {"track_data": {"structure": "A-B-A"}, "midi_path": None,
                "audio_status": "error", "audio_note": "sin motor"}

    async def create_single_cover(self, track_title, visual_concept, **kwargs):
        self.titulos.append(track_title)
        self.conceptos.append(visual_concept)
        return {"status": "simulated", "simulated": True, "note": "marcador"}


class PortalDoble:
    def __init__(self):
        self.prompts = []

    async def generate_video_frontier(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return {"status": "error", "error": "sin motor"}


class CanalDoble:
    def __init__(self, nombre="salon"):
        self.id = 555
        self.name = nombre
        self.textos = []

    async def send(self, content=None, file=None, **kwargs):
        if content:
            self.textos.append(content)

    def permissions_for(self, member):
        return types.SimpleNamespace(send_messages=True, attach_files=True)


class GuildDoble:
    def __init__(self, canal):
        self.id = 1
        self.name = "Dev Server"
        self.text_channels = [canal]
        self.me = object()


def _adaptador(monkeypatch, tmp_path, canal):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    creador, portal, biblioteca = CreadorDoble(), PortalDoble(), LibraryDoble()
    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = types.SimpleNamespace(
        media_creator=creador, nous_portal=portal, creation_library=biblioteca,
        cron=types.SimpleNamespace(pause_for=lambda s: types.SimpleNamespace(isoformat=lambda: "luego")),
        generate_response=_respuesta, discord_adapter=None,
    )
    adaptador._find_guild = lambda nombre: GuildDoble(canal)
    adaptador._permission_names = lambda guild: {"manage_channels", "send_messages", "attach_files"}
    adaptador._send_file = _no_adjunta
    return adaptador, creador, portal, biblioteca


RUTAS_PEDIDAS = []


async def _respuesta(user_id, user_name, message, channel_type=None, active_role=None,
                     route=None):
    RUTAS_PEDIDAS.append(route)
    return f"texto sobre: {message[:120]}"


async def _no_adjunta(channel, path, caption):
    return False


def _producir(adaptador, pedido, canal):
    RUTAS_PEDIDAS.clear()
    asyncio.run(adaptador._run_discord_production(
        author_id="42", author_name="Productor", content=pedido, origin_channel=canal))


def test_el_tema_del_pedido_gobierna_la_obra(tmp_path, monkeypatch):
    """El tercer entrecomillado nombra la obra; antes no se leía."""
    canal = CanalDoble()
    adaptador, creador, portal, biblioteca = _adaptador(monkeypatch, tmp_path, canal)

    _producir(adaptador, 'crea el canal "Dev Server" "salon" "Cerezos de acero" en discord', canal)

    assert biblioteca.guardados == ["Presentación del Salón", "Cerezos de acero"]
    titulo, imaginario = creador.partituras[0]
    assert titulo == "Cerezos de acero"
    # Y el imaginario, no sólo el título: una partitura titulada como el pedido
    # pero compuesta sobre «agua, hierro e invierno» sigue siendo la de siempre.
    assert "Cerezos de acero" in imaginario
    assert all("Cerezos de acero" in titulo for titulo in creador.titulos)
    assert "Cerezos de acero" in portal.prompts[0]
    # Los conceptos visuales también: uno de los tres llevaba el título dentro.
    assert any("Cerezos de acero" in concepto for concepto in creador.conceptos)
    todo = " ".join(creador.titulos + creador.conceptos + portal.prompts
                    + [m for t in creador.partituras for m in t])
    assert TEMA_POR_DEFECTO not in todo


def test_sin_tema_nombrado_se_conserva_el_de_siempre(tmp_path, monkeypatch):
    """Quitar el comportamiento anterior en silencio rompería peticiones en curso."""
    canal = CanalDoble()
    adaptador, creador, _portal, biblioteca = _adaptador(monkeypatch, tmp_path, canal)

    _producir(adaptador, 'crea el canal "Dev Server" "salon" en discord', canal)

    assert TEMA_POR_DEFECTO in biblioteca.guardados
    assert creador.partituras[0][0] == TEMA_POR_DEFECTO


def test_una_portada_simulada_no_se_publica_como_obra(tmp_path, monkeypatch):
    """El vicio de siempre: un marcador presentado como arte."""
    canal = CanalDoble()
    adaptador, _creador, _portal, _biblioteca = _adaptador(monkeypatch, tmp_path, canal)

    _producir(adaptador, 'crea el canal "Dev Server" "salon" "Cerezos de acero" en discord', canal)

    assert any("no generada" in texto for texto in canal.textos)


def test_el_acuse_dice_la_obra_y_lo_que_cuesta(tmp_path, monkeypatch):
    """Este camino gastaba en canción, tres imágenes y vídeo sin mencionar nada."""
    canal = CanalDoble()
    adaptador, _creador, _portal, _biblioteca = _adaptador(monkeypatch, tmp_path, canal)
    adaptador.brake = types.SimpleNamespace(blocked_reason=lambda ambito: None)
    adaptador._workflow_tasks = set()

    async def _lanzar():
        acuse = adaptador._launch_discord_production(
            author_id="42", author_name="Productor",
            content='crea el canal "Dev Server" "salon" "Cerezos de acero" en discord',
            origin_channel=canal)
        for tarea in list(adaptador._workflow_tasks):
            tarea.cancel()
        return acuse

    acuse = asyncio.run(_lanzar())

    assert "Cerezos de acero" in acuse
    assert "Coste previsto" in acuse


def test_el_tema_es_el_tercer_entrecomillado_no_el_canal():
    """Confundirlo con el canal produciría una obra titulada «salon»."""
    assert extract_production_theme('"Dev Server" "salon" "Cerezos de acero"') == "Cerezos de acero"
    assert extract_production_theme('"Dev Server" "salon"') == ""
    assert extract_production_theme("sin comillas") == ""


def test_la_letra_sale_por_la_ruta_de_composicion_musical(tmp_path, monkeypatch):
    """
    `music_composition` llevaba declarada en `config.yaml` desde el principio y
    no la leía nadie: un dial que no gira engaña a quien lo ajusta y no falla
    nunca. Escribir la letra de una canción es exactamente su tarea.
    """
    canal = CanalDoble()
    adaptador, _creador, _portal, _biblioteca = _adaptador(monkeypatch, tmp_path, canal)

    _producir(adaptador, 'crea el canal "Dev Server" "salon" "Cerezos de acero" en discord', canal)

    assert "music_composition" in RUTAS_PEDIDAS, \
        "la letra salía con la configuración general, no con su ruta"
