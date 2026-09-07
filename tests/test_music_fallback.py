"""
Pruebas del respaldo musical local.

Dos cosas se protegen. Que suene de verdad cuando la imagen trae sintetizador
—partitura propia, FluidSynth y ffmpeg, sin proveedor externo— y que **nunca se
presente como canto**: es una maqueta instrumental, o una letra recitada sobre
música, y el resultado tiene que decirlo.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.music_fallback import LocalMusicEngine  # noqa: E402


class RunnerFalso:
    """Sustituye a los binarios: escribe el fichero de salida que producirían."""

    def __init__(self, fallar_en=None):
        self.fallar_en = fallar_en
        self.llamadas = []

    def __call__(self, argv, **kwargs):
        self.llamadas.append(argv)
        binario = argv[0]
        if binario == self.fallar_en:
            return subprocess.CompletedProcess(argv, 1, "", "fallo simulado")
        destino = argv[argv.index("-F") + 1] if "-F" in argv else argv[-1]
        Path(destino).write_bytes(b"audio")
        return subprocess.CompletedProcess(argv, 0, "", "")


@pytest.fixture
def motor(tmp_path, monkeypatch):
    soundfont = tmp_path / "gm.sf2"
    soundfont.write_bytes(b"sf2")
    monkeypatch.setattr("shutil.which", lambda nombre: f"/usr/bin/{nombre}")
    return LocalMusicEngine(soundfont=str(soundfont), music_dir=str(tmp_path),
                            runner=RunnerFalso())


def test_sin_binarios_lo_dice_y_no_devuelve_marcador(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nombre: None)
    monkeypatch.delenv("YUKI_SOUNDFONT", raising=False)
    motor = LocalMusicEngine(soundfont=None, music_dir=str(tmp_path))

    resultado = motor.compose("herrumbre")

    assert not motor.is_available()
    assert resultado["status"] == "error"
    assert "fluidsynth" in resultado["error"]
    assert resultado["simulated"] is False, "un error no es una simulación"
    assert "local_path" not in resultado


def test_compone_audio_real_desde_la_partitura_propia(motor, tmp_path):
    resultado = motor.compose("herrumbre y escarcha", duration_seconds=60, bpm=72)

    assert resultado["status"] == "success"
    assert resultado["simulated"] is False
    assert Path(resultado["local_path"]).is_file()
    assert Path(resultado["midi_path"]).suffix == ".mid"
    assert resultado["provider"] == "local"


def test_nunca_se_declara_cantada(motor):
    resultado = motor.compose("herrumbre")

    assert resultado["sung"] is False
    assert resultado["spoken_lyrics"] is False
    assert "No es una canción cantada" in resultado["note"]


def test_con_voz_la_letra_va_recitada_y_la_base_cede(motor, tmp_path):
    voz = tmp_path / "voz.ogg"
    voz.write_bytes(b"ogg")

    resultado = motor.compose("herrumbre", voice_path=str(voz))

    mezcla = [c for c in motor._runner.llamadas if c[0] == "ffmpeg"][0]
    assert str(voz) in mezcla, "la voz entra como primera pista"
    assert any("amix" in parte for parte in mezcla)
    assert resultado["spoken_lyrics"] is True
    assert resultado["sung"] is False, "recitar no es cantar"


def test_si_el_sintetizador_falla_no_hay_pista(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nombre: f"/usr/bin/{nombre}")
    soundfont = tmp_path / "gm.sf2"
    soundfont.write_bytes(b"sf2")
    motor = LocalMusicEngine(soundfont=str(soundfont), music_dir=str(tmp_path),
                             runner=RunnerFalso(fallar_en="fluidsynth"))

    resultado = motor.compose("herrumbre")

    assert resultado["status"] == "error"
    assert "fluidsynth" in resultado["error"]
    assert Path(resultado["midi_path"]).is_file(), "la partitura sí se conserva"


def test_si_ffmpeg_falla_tampoco_se_entrega_nada(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nombre: f"/usr/bin/{nombre}")
    soundfont = tmp_path / "gm.sf2"
    soundfont.write_bytes(b"sf2")
    motor = LocalMusicEngine(soundfont=str(soundfont), music_dir=str(tmp_path),
                             runner=RunnerFalso(fallar_en="ffmpeg"))

    resultado = motor.compose("herrumbre")

    assert resultado["status"] == "error"
    assert "MP3" in resultado["error"]


def test_la_duracion_pedida_se_traduce_en_compases(motor):
    corta = motor.compose("breve", duration_seconds=30, bpm=72)
    larga = motor.compose("larga", duration_seconds=180, bpm=72)

    assert Path(corta["midi_path"]).stat().st_size < Path(larga["midi_path"]).stat().st_size


def test_el_banco_de_sonidos_se_puede_declarar_por_entorno(tmp_path, monkeypatch):
    banco = tmp_path / "propio.sf2"
    banco.write_bytes(b"sf2")
    monkeypatch.setenv("YUKI_SOUNDFONT", str(banco))

    assert LocalMusicEngine(music_dir=str(tmp_path)).soundfont == str(banco)


# --- Cadena musical completa ---

class VertexMusicaFalso:
    """Doble del motor de Vertex: disponible, pero programable para fallar."""

    def __init__(self, resultado):
        self._resultado = resultado
        self.llamado = 0

    def is_available(self):
        return True

    async def generate_music(self, prompt, duration_seconds=90, model=None):
        self.llamado += 1
        return dict(self._resultado)


def _portal(tmp_path, vertex, motor_local):
    from src.tools.nous_portal import NousPortalClient

    portal = NousPortalClient(vertex=vertex)
    portal.music_dir = str(tmp_path)
    portal.local_music = motor_local
    return portal


def test_si_lyria_falla_suena_el_respaldo_y_se_declara(tmp_path, motor):
    import asyncio

    vertex = VertexMusicaFalso({"status": "error", "error": "publisher model 404"})
    portal = _portal(tmp_path, vertex, motor)

    resultado = asyncio.run(portal.generate_music_flow(
        title="herrumbre", prompt="koto y escarcha", engine="lyria-3-pro-preview"))

    assert vertex.llamado == 1, "primero se intenta Lyria"
    assert resultado["status"] == "success"
    assert resultado["engine"] == "local.fluidsynth"
    assert resultado["sung"] is False
    assert resultado["fallback_from"] == "publisher model 404"


def test_un_tope_de_presupuesto_no_se_esquiva_con_el_respaldo(tmp_path, motor):
    """El presupuesto decide que hoy no toca; renderizar igual sería desobedecerlo."""
    import asyncio

    vertex = VertexMusicaFalso({"status": "error", "budget_exceeded": True,
                                "error": "presupuesto diario agotado para musica_pistas"})
    portal = _portal(tmp_path, vertex, motor)

    resultado = asyncio.run(portal.generate_music_flow(
        title="herrumbre", prompt="koto", engine="lyria-3-pro-preview"))

    assert resultado["status"] == "error"
    assert resultado["budget_exceeded"] is True
    assert "local_path" not in resultado


def test_lyria_cuando_responde_se_declara_cantada(tmp_path, motor):
    import asyncio

    pista = tmp_path / "lyria.mp3"
    pista.write_bytes(b"ID3")
    vertex = VertexMusicaFalso({"status": "success", "local_path": str(pista)})
    portal = _portal(tmp_path, vertex, motor)

    resultado = asyncio.run(portal.generate_music_flow(
        title="herrumbre", prompt="koto", engine="lyria-3-pro-preview"))

    assert resultado["sung"] is True
    assert resultado["local_path"] == str(pista)
