"""
Motor musical de respaldo, sin proveedor externo.

El limitador L4: la única música real de Yuki sale de `lyria-3-pro-preview`. Una
*preview* puede cambiar de nombre, de precio o desaparecer sin aviso, y ese día
Yuki se queda sin música y sin plan B —porque `local.midi` produce partituras,
no audio: un `.mid` no se escucha en Discord—.

Esto cierra el hueco con lo que ya hay en casa: la partitura del generador MIDI,
un sintetizador de software (FluidSynth con un banco General MIDI) y el ffmpeg
que la imagen ya trae. Si además se le pasa una voz —la de Gemini TTS leyendo la
letra—, la mezcla sobre la base instrumental.

Dos límites que se declaran y no se disimulan:

  · **No canta.** Es una maqueta instrumental, y con voz es una letra *recitada*
    sobre música. El resultado lleva `sung: False` para que nadie lo presente
    como canción cantada; eso sigue siendo territorio de Lyria.
  · **Necesita binarios.** Sin `fluidsynth`, sin banco de sonidos o sin `ffmpeg`
    devuelve `status: "error"` diciendo cuál falta. No hay marcador silencioso.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .midi_generator import YukiMIDIGenerator

logger = logging.getLogger("Yuki.MusicFallback")

# Bancos General MIDI habituales en Debian, en orden de preferencia. El primero
# que exista sirve; `YUKI_SOUNDFONT` los precede a todos.
SOUNDFONTS_HABITUALES = (
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/default.sf2",
)

FRECUENCIA_MUESTREO = 44100
TIEMPO_LIMITE_SEGUNDOS = 180

# Compases por minuto aproximados a 4/4: sirve para traducir la duración pedida
# en segundos al número de compases que el generador MIDI entiende.
PULSOS_POR_COMPAS = 4


def _sin_binario(nombre: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "simulated": False,
        "engine": "local.fluidsynth",
        "error": (f"falta `{nombre}` en la imagen: el respaldo musical local no puede "
                  "renderizar audio y no voy a devolver un marcador en su lugar"),
    }


class LocalMusicEngine:
    """Partitura propia → audio real, sin salir de la instancia."""

    name = "local.fluidsynth"

    def __init__(self, soundfont: Optional[str] = None, music_dir: str = "output/music",
                 runner: Any = None, midi_generator: Optional[YukiMIDIGenerator] = None):
        self.soundfont = soundfont or self._soundfont_disponible()
        self.music_dir = music_dir
        # Inyectable en pruebas: la suite no invoca binarios del sistema.
        self._runner = runner or subprocess.run
        self.midi = midi_generator or YukiMIDIGenerator()

    @staticmethod
    def _soundfont_disponible() -> Optional[str]:
        explicito = os.getenv("YUKI_SOUNDFONT", "").strip()
        if explicito and Path(explicito).is_file():
            return explicito
        for candidato in SOUNDFONTS_HABITUALES:
            if Path(candidato).is_file():
                return candidato
        return None

    def missing_requirements(self) -> List[str]:
        """Qué falta para poder sonar. Vacío significa disponible."""
        faltan = []
        if shutil.which("fluidsynth") is None:
            faltan.append("fluidsynth")
        if not self.soundfont:
            faltan.append("banco de sonidos (.sf2)")
        if shutil.which("ffmpeg") is None:
            faltan.append("ffmpeg")
        return faltan

    def is_available(self) -> bool:
        return not self.missing_requirements()

    # -- Render ----------------------------------------------------------

    def _ejecutar(self, argv: List[str]) -> bool:
        """Invoca un binario sin shell y sin rutas del usuario en la línea."""
        try:
            resultado = self._runner(argv, capture_output=True, text=True,
                                     timeout=TIEMPO_LIMITE_SEGUNDOS, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Fallo ejecutando %s: %s", argv[0], type(exc).__name__)
            return False
        if resultado.returncode != 0:
            logger.warning("%s terminó con código %s", argv[0], resultado.returncode)
            return False
        return True

    def compose(self, title: str, duration_seconds: int = 90, bpm: int = 72,
                scale: str = "insen", voice_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Renderiza una maqueta real: partitura propia, sintetizada y mezclada.

        Con `voice_path` la voz va por delante y la base instrumental baja, que es
        lo que hace inteligible una letra recitada. Sin ella, es instrumental. En
        ningún caso se declara cantada.
        """
        faltan = self.missing_requirements()
        if faltan:
            return _sin_binario(", ".join(faltan))

        os.makedirs(self.music_dir, exist_ok=True)
        compases = max(4, round(duration_seconds * bpm / (60 * PULSOS_POR_COMPAS)))

        partitura = self.midi.generate_track(
            title=title, scale_name=scale, bpm=bpm, num_bars=compases,
            output_dir=self.music_dir,
        )
        if partitura.get("status") != "success":
            return {"status": "error", "simulated": False, "engine": self.name,
                    "error": "el generador MIDI no produjo partitura"}

        midi_path = partitura["file_path"]
        base_wav = os.path.join(self.music_dir, f"yuki_local_{int(time.time())}.wav")
        destino = os.path.join(self.music_dir, f"yuki_local_{int(time.time())}.mp3")

        if not self._ejecutar([
            "fluidsynth", "-ni", "-g", "0.8", "-r", str(FRECUENCIA_MUESTREO),
            "-F", base_wav, self.soundfont, midi_path,
        ]) or not Path(base_wav).is_file():
            return {"status": "error", "simulated": False, "engine": self.name,
                    "midi_path": midi_path,
                    "error": "fluidsynth no produjo audio a partir de la partitura"}

        if voice_path and Path(voice_path).is_file():
            mezclado = self._ejecutar([
                "ffmpeg", "-y", "-i", voice_path, "-i", base_wav,
                "-filter_complex",
                # La voz manda; la base cede 9 dB para no taparla. `duration=longest`
                # evita cortar la música si la lectura es más breve.
                "[1:a]volume=0.35[cama];[0:a][cama]amix=inputs=2:duration=longest[salida]",
                "-map", "[salida]", "-codec:a", "libmp3lame", "-q:a", "4", destino,
            ])
        else:
            mezclado = self._ejecutar([
                "ffmpeg", "-y", "-i", base_wav, "-codec:a", "libmp3lame", "-q:a", "4", destino,
            ])

        Path(base_wav).unlink(missing_ok=True)

        if not mezclado or not Path(destino).is_file():
            return {"status": "error", "simulated": False, "engine": self.name,
                    "midi_path": midi_path,
                    "error": "ffmpeg no produjo el MP3 final"}

        recitada = bool(voice_path and Path(voice_path).is_file())
        return {
            "status": "success",
            # No es un marcador: hay audio real, sintetizado aquí.
            "simulated": False,
            "engine": self.name,
            "provider": "local",
            # Lo que este motor NO es. Va en el resultado para que ninguna capa
            # de arriba pueda presentarlo como canto.
            "sung": False,
            "spoken_lyrics": recitada,
            "note": ("Maqueta local: base instrumental sintetizada desde la partitura propia"
                     + (" con la letra recitada encima." if recitada else ".")
                     + " No es una canción cantada."),
            "local_path": destino,
            "midi_path": midi_path,
            "mime_type": "audio/mpeg",
            "title": title,
            "bpm": bpm,
            "scale": scale,
            "duration_seconds": duration_seconds,
            "bytes": Path(destino).stat().st_size,
            "created_at": time.time(),
        }
