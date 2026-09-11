"""
Poder rehacer una pista que salió bien.

M4 de `docs/VIRTUALIZACION_Y_MEJORAS.md` dejaba pendiente «archivar el prompt y
los parámetros de cada pista para poder rehacerla igual». Lo único que
sobrevivía a la generación era el manifiesto del Artículo 50, y ése no es una
receta: guarda el prompt **recortado a 500 caracteres** dentro de un campo
llamado `abstract`, porque su trabajo es declarar el origen. Con la letra de una
canción dentro, eso es perderla entera.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.transparency import MediaMarker, TransparencyPolicy  # noqa: E402
from src.tools import receta  # noqa: E402
from src.tools.creation_library import CreationLibrary  # noqa: E402

LETRA_LARGA = "verso de agua sobre hierro que no cabe en un resumen. " * 40


def test_la_receta_guarda_el_prompt_entero(tmp_path):
    """El manifiesto lo recorta a 500; la receta es la que permite rehacerla."""
    pista = tmp_path / "pista.mp3"
    pista.write_bytes(b"audio")

    receta.escribir(str(pista), motor="lyria-3-pro-preview", prompt=LETRA_LARGA,
                    duration_seconds=90)
    guardada = receta.leer(str(pista))

    assert guardada["prompt"] == LETRA_LARGA
    assert len(LETRA_LARGA) > 500, "el ejemplo tiene que superar el recorte del manifiesto"
    assert guardada["parametros"]["duration_seconds"] == 90


def test_el_manifiesto_del_articulo_50_no_sirve_como_receta(tmp_path):
    """
    No es un reproche al manifiesto: hace su trabajo, que es declarar el origen.
    Se fija aquí porque durante meses fue lo único que quedaba de cada pista.
    """
    pista = tmp_path / "pista.mp3"
    pista.write_bytes(b"audio")
    marcador = MediaMarker(TransparencyPolicy())

    manifiesto = marcador.manifest(str(pista), model="lyria", prompt=LETRA_LARGA, kind="sonora")
    abstracto = manifiesto["assertions"][1]["data"]["abstract"]

    assert abstracto != LETRA_LARGA
    assert len(abstracto) == 500


def test_una_receta_ilegible_no_devuelve_media(tmp_path):
    """Decir que no está es mejor que devolver la mitad."""
    pista = tmp_path / "pista.mp3"
    pista.write_bytes(b"audio")
    receta.ruta_de(str(pista)).write_text("{esto no es json", encoding="utf-8")

    assert receta.leer(str(pista)) == {}


def test_no_poder_escribir_la_receta_no_impide_entregar(tmp_path):
    """Una pista ya generada y pagada no puede desaparecer por un fallo de disco."""
    assert receta.escribir(str(tmp_path / "no-existe.mp3"), motor="x", prompt="y") is None


def test_las_diferencias_dicen_por_que_salio_distinto():
    una = {"motor": "lyria", "prompt": "canta esto", "parametros": {"bpm": 72}}
    otra = {"motor": "lyria", "prompt": "canta esto", "parametros": {"bpm": 96}}

    assert receta.diferencias(una, otra) == {"bpm": (72, 96)}


def test_un_prompt_distinto_es_la_diferencia_que_mas_importa():
    """
    «Vuelve a hacerlo, esta vez con más percusión» cambia el prompt y nada más.
    Si la comparación no mirase ahí, el caso del incidente entero se le escapa.
    """
    una = {"motor": "lyria", "prompt": "canta esto", "parametros": {"bpm": 72}}
    otra = {"motor": "lyria", "prompt": "canta esto, con más percusión",
            "parametros": {"bpm": 72}}

    cambios = receta.diferencias(una, otra)

    assert set(cambios) == {"prompt"}
    assert cambios["prompt"] == ("canta esto", "canta esto, con más percusión")


def test_cambiar_de_motor_tambien_cuenta():
    """La misma letra por Lyria o por el respaldo local no da la misma obra."""
    una = {"motor": "lyria-3-pro-preview", "prompt": "igual", "parametros": {}}
    otra = {"motor": "respaldo-local", "prompt": "igual", "parametros": {}}

    assert set(receta.diferencias(una, otra)) == {"motor"}


def test_dos_encargos_identicos_lo_dicen_en_la_receta():
    """
    La pregunta que nadie podía contestar cuando el Productor decía «me has
    devuelto exactamente lo mismo»: si las recetas coinciden, se pidió lo mismo.
    """
    una = {"motor": "lyria", "prompt": "canta esto", "parametros": {"bpm": 72}}

    assert receta.diferencias(una, dict(una)) == {}


def test_la_receta_se_archiva_con_la_obra(tmp_path):
    """
    Si se queda en `output/` se pierde en la primera limpieza, y con ella la
    única forma de rehacer la pista.
    """
    salida = tmp_path / "output"
    (salida / "music").mkdir(parents=True)
    pista = salida / "music" / "pista.mp3"
    pista.write_bytes(b"audio real de verdad")
    receta.escribir(str(pista), motor="lyria-3-pro-preview", prompt=LETRA_LARGA, bpm=72)

    biblioteca = CreationLibrary(salida)
    biblioteca.inventory()
    entrada = next(e for e in biblioteca.list_entries()["entries"] if e["kind"] == "sonora")
    leida = biblioteca.read_entry(entrada["id"])

    assert entrada.get("receta"), "la obra archivada no lleva su receta"
    assert (biblioteca.root / entrada["receta"]).is_file()
    assert leida["receta_datos"]["prompt"] == LETRA_LARGA
    assert leida["receta_datos"]["parametros"]["bpm"] == 72


def test_una_obra_sin_receta_se_archiva_igual(tmp_path):
    """Las obras anteriores no tienen receta y no por eso dejan de ser obra."""
    salida = tmp_path / "output"
    (salida / "music").mkdir(parents=True)
    (salida / "music" / "vieja.mp3").write_bytes(b"audio antiguo")

    biblioteca = CreationLibrary(salida)
    biblioteca.inventory()
    entrada = next(e for e in biblioteca.list_entries()["entries"] if e["kind"] == "sonora")

    assert "receta" not in entrada
    assert "receta_datos" not in biblioteca.read_entry(entrada["id"])


def test_la_receta_no_se_archiva_como_obra_aparte(tmp_path):
    """No es obra: es lo que explica una. Contarla como pieza inflaría el canon."""
    salida = tmp_path / "output"
    (salida / "music").mkdir(parents=True)
    pista = salida / "music" / "pista.mp3"
    pista.write_bytes(b"audio real")
    receta.escribir(str(pista), motor="lyria", prompt="algo")

    biblioteca = CreationLibrary(salida)
    resultado = biblioteca.inventory()

    assert resultado["checked_files"] == 1
    assert all(not e["path"].endswith(receta.SUFIJO)
               for e in biblioteca.list_entries()["entries"])


def test_la_receta_archivada_es_json_valido(tmp_path):
    salida = tmp_path / "output"
    (salida / "art").mkdir(parents=True)
    lienzo = salida / "art" / "portada.png"
    lienzo.write_bytes(b"\x89PNG imagen")
    receta.escribir(str(lienzo), motor="imagen-3", prompt="agua y acero", aspect_ratio="1:1")

    biblioteca = CreationLibrary(salida)
    biblioteca.inventory()
    entrada = next(e for e in biblioteca.list_entries()["entries"] if e["kind"] == "visual")
    contenido = json.loads((biblioteca.root / entrada["receta"]).read_text(encoding="utf-8"))

    assert contenido["parametros"]["aspect_ratio"] == "1:1"


if __name__ == "__main__":
    pytest.main([__file__])


def test_el_respaldo_musical_deja_receta_al_componer(tmp_path, monkeypatch):
    """
    Camino del producto, no la función suelta: el motor real compone y la receta
    tiene que quedar escrita sin que nadie la pida aparte.
    """
    import subprocess
    from pathlib import Path

    from src.tools.music_fallback import LocalMusicEngine

    class RunnerFalso:
        def __call__(self, argv, **kwargs):
            destino = argv[argv.index("-F") + 1] if "-F" in argv else argv[-1]
            Path(destino).write_bytes(b"audio")
            return subprocess.CompletedProcess(argv, 0, "", "")

    soundfont = tmp_path / "gm.sf2"
    soundfont.write_bytes(b"sf2")
    monkeypatch.setattr("shutil.which", lambda nombre: f"/usr/bin/{nombre}")
    motor = LocalMusicEngine(soundfont=str(soundfont), music_dir=str(tmp_path),
                             runner=RunnerFalso())

    resultado = motor.compose("Herrumbre y Escarcha", duration_seconds=45, bpm=72, scale="insen")

    assert resultado["status"] == "success"
    guardada = receta.leer(resultado["local_path"])
    assert guardada, "el motor compuso y no dejó receta"
    assert guardada["motor"] == motor.name
    assert guardada["parametros"]["bpm"] == 72
    assert guardada["parametros"]["escala"] == "insen"
    assert guardada["parametros"]["duration_seconds"] == 45


def test_la_entrega_dice_con_que_se_hizo(tmp_path, monkeypatch):
    """
    El Productor preguntó «¿qué es lo que has hecho?» y Yuki contestó con un
    relato técnico detallado en un turno con **cero herramientas ejecutadas**:
    no hizo nada de eso, el prompt de generación está escrito en el adaptador.

    La receta ya se escribía junto al audio y no la veía nadie. Enseñarla en el
    pie del adjunto quita el hueco por donde entró el relato.
    """
    import pytest as _pytest

    _pytest.importorskip("discord")
    from src.adapters.discord_bot import DiscordAdapter

    pista = tmp_path / "cancion.mp3"
    pista.write_bytes(b"audio")
    receta.escribir(str(pista), motor="lyria-3-pro-preview", prompt="canta esto",
                    duration_seconds=90)

    pie = DiscordAdapter._pie_de_receta(str(pista))

    assert "lyria-3-pro-preview" in pie
    assert "duration_seconds 90" in pie


def test_sin_receta_no_se_inventa_un_pie(tmp_path):
    """Una obra anterior no tiene receta, y callar es mejor que suponer el motor."""
    import pytest as _pytest

    _pytest.importorskip("discord")
    from src.adapters.discord_bot import DiscordAdapter

    vieja = tmp_path / "vieja.mp3"
    vieja.write_bytes(b"audio")

    assert DiscordAdapter._pie_de_receta(str(vieja)) == ""
