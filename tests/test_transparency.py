"""
Pruebas del Artículo 50: declararse y marcar.

No son pruebas de producto sino de cumplimiento, y por eso lo que se comprueba
es lo contrario de lo habitual: que la obligación **no** se pueda esquivar. Ni
por configuración de carácter, ni por un camino de salida nuevo, ni por un
fichero traído de antes del marcado.
"""

import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.transparency import (  # noqa: E402
    CLAVE_METADATO, DIGITAL_SOURCE_TYPE_IA, DisclosureLedger, MediaMarker,
    TransparencyPolicy, audit_directory,
)


def _png(destino: Path) -> Path:
    """PNG mínimo válido: cabecera, IHDR e IEND."""
    destino.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13) + b"IHDR" + b"\x00" * 13 + struct.pack(">I", 0)
        + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", 0)
    )
    return destino


# --- Declaración de naturaleza ---

def test_a_quien_no_lo_sabe_se_le_dice(tmp_path):
    registro = DisclosureLedger(path=str(tmp_path / "t.json"))

    assert registro.needs_disclosure("235796491988369408", "direct_message")


def test_no_se_repite_a_quien_ya_se_le_dijo(tmp_path):
    registro = DisclosureLedger(path=str(tmp_path / "t.json"))
    registro.record_disclosure("42", "discord_channel")

    assert not registro.needs_disclosure("42", "discord_channel")


def test_se_repite_pasado_el_plazo(tmp_path):
    """Decirlo una vez en la vida no cumple con quien vuelve seis meses después."""
    ruta = tmp_path / "t.json"
    registro = DisclosureLedger(path=str(ruta), reminder_days=30)
    registro.record_disclosure("42", "direct_message")

    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["declaraciones"]["direct_message:42"]["at"] = time.time() - 40 * 86400
    ruta.write_text(json.dumps(datos), encoding="utf-8")

    assert DisclosureLedger(path=str(ruta), reminder_days=30).needs_disclosure("42", "direct_message")


def test_cada_canal_cuenta_por_separado(tmp_path):
    registro = DisclosureLedger(path=str(tmp_path / "t.json"))
    registro.record_disclosure("42", "direct_message")

    assert registro.needs_disclosure("42", "discord_channel")


def test_ante_un_registro_ilegible_se_declara_de_nuevo(tmp_path):
    """Declarar de más no hace daño; declarar de menos incumple."""
    ruta = tmp_path / "t.json"
    ruta.write_text("{ roto", encoding="utf-8")

    assert DisclosureLedger(path=str(ruta)).needs_disclosure("42", "direct_message")


def test_el_agente_antepone_la_declaracion_y_no_la_repite(tmp_path, monkeypatch):
    import types

    from src.core.agent import YukiAgent

    monkeypatch.setenv("YUKI_TRANSPARENCY_PATH", str(tmp_path / "t.json"))
    politica = TransparencyPolicy()
    agente = types.SimpleNamespace(
        transparency=politica,
        disclosures=DisclosureLedger(path=str(tmp_path / "t.json")),
    )
    agente.disclosure_for = types.MethodType(YukiAgent.disclosure_for, agente)

    primera = agente.disclosure_for("42", "direct_message")
    segunda = agente.disclosure_for("42", "direct_message")

    # Es su voz, no un descargo legal: dice lo que es —un ser sintético— y que
    # el personaje es un vestido. Cumple igual, y además suena a ella.
    assert primera and "ser sintético" in primera.lower()
    assert "vestido" in primera.lower()
    assert segunda is None


def test_los_canales_internos_no_son_personas(tmp_path, monkeypatch):
    """El cron y su propia voluntad no tienen a quién informar."""
    import types

    from src.core.agent import YukiAgent

    agente = types.SimpleNamespace(
        transparency=TransparencyPolicy(),
        disclosures=DisclosureLedger(path=str(tmp_path / "t.json")),
    )
    agente.disclosure_for = types.MethodType(YukiAgent.disclosure_for, agente)

    assert agente.disclosure_for("autonomous_cron", "direct_message") is None
    assert agente.disclosure_for("yuki_internal", "direct_message") is None


# --- Marcado del material ---

def test_el_manifiesto_declara_el_termino_iptc_de_ia(tmp_path):
    marcador = MediaMarker()
    ruta = _png(tmp_path / "portada.png")

    resultado = marcador.mark(str(ruta), model="gemini-2.5-flash-image",
                              prompt="niebla sobre asfalto", kind="visual")

    manifiesto = json.loads(Path(resultado["sidecar"]).read_text(encoding="utf-8"))
    accion = manifiesto["assertions"][0]["data"]["actions"][0]
    assert accion["action"] == "c2pa.created"
    assert accion["digitalSourceType"] == DIGITAL_SOURCE_TYPE_IA
    assert "trainedAlgorithmicMedia" in DIGITAL_SOURCE_TYPE_IA


def test_el_manifiesto_no_finge_estar_firmado(tmp_path):
    """Sin cadena de certificados no hay prueba criptográfica, y se dice."""
    marcador = MediaMarker()
    ruta = _png(tmp_path / "portada.png")

    resultado = marcador.mark(str(ruta))
    manifiesto = json.loads(Path(resultado["sidecar"]).read_text(encoding="utf-8"))

    assert manifiesto["signed"] is False
    assert resultado["signed"] is False
    assert "no una prueba criptográfica" in manifiesto["note"]


def test_el_png_queda_marcado_por_dentro_y_sigue_siendo_png(tmp_path):
    marcador = MediaMarker()
    ruta = _png(tmp_path / "portada.png")
    original = ruta.read_bytes()

    resultado = marcador.mark(str(ruta), model="gemini-image")
    contenido = ruta.read_bytes()

    assert resultado["embedded"] is True
    assert contenido.startswith(b"\x89PNG\r\n\x1a\n"), "la firma del formato se conserva"
    assert contenido[8:16] == original[8:16], "IHDR sigue siendo el primer chunk"
    assert CLAVE_METADATO.encode() in contenido
    assert DIGITAL_SOURCE_TYPE_IA.encode() in contenido
    assert contenido.endswith(b"IEND" + struct.pack(">I", 0))


def test_el_audio_se_marca_con_ffmpeg_sin_recodificar(tmp_path):
    llamadas = []

    def runner(argv, **kwargs):
        llamadas.append(argv)
        Path(argv[-1]).write_bytes(b"audio marcado")
        return subprocess.CompletedProcess(argv, 0, "", "")

    ruta = tmp_path / "cancion.mp3"
    ruta.write_bytes(b"ID3 audio")
    marcador = MediaMarker(runner=runner)

    with pytest.MonkeyPatch.context() as parche:
        parche.setattr("shutil.which", lambda nombre: f"/usr/bin/{nombre}")
        resultado = marcador.mark(str(ruta), model="lyria-3-pro-preview")

    assert resultado["embedded"] is True
    argv = llamadas[0]
    assert "-c" in argv and "copy" in argv, "sin recodificar: no se degrada la obra"
    assert any(DIGITAL_SOURCE_TYPE_IA in parte for parte in argv)


def test_sin_ffmpeg_queda_el_manifiesto_lateral(tmp_path, monkeypatch):
    """Una capa puede fallar; la obligación no desaparece con ella."""
    monkeypatch.setattr("shutil.which", lambda nombre: None)
    ruta = tmp_path / "cancion.mp3"
    ruta.write_bytes(b"ID3 audio")

    resultado = MediaMarker().mark(str(ruta))

    assert resultado["marked"] is True and resultado["embedded"] is False
    assert Path(resultado["sidecar"]).is_file()
    assert MediaMarker().is_marked(str(ruta))


def test_un_fichero_inexistente_no_se_da_por_marcado(tmp_path):
    resultado = MediaMarker().mark(str(tmp_path / "fantasma.png"))

    assert resultado["marked"] is False
    assert not MediaMarker().is_marked(str(tmp_path / "fantasma.png"))


def test_la_auditoria_encuentra_lo_que_falta_por_marcar(tmp_path):
    _png(tmp_path / "marcada.png")
    _png(tmp_path / "sin_marcar.png")
    MediaMarker().mark(str(tmp_path / "marcada.png"))

    auditoria = audit_directory(str(tmp_path))

    assert auditoria["total"] == 2
    assert any("sin_marcar.png" in ruta for ruta in auditoria["sin_marcar"])
    assert any("marcada.png" in ruta for ruta in auditoria["marcados"])


def test_la_entrega_marca_lo_que_llegue_sin_marca(tmp_path, monkeypatch):
    """
    La última puerta antes de una persona.

    Un camino de salida nuevo, o una obra archivada antes de existir el marcado,
    no puede entregarse sin declarar lo que es.
    """
    import asyncio
    import types

    pytest.importorskip("discord")
    from src.adapters.discord_bot import DiscordAdapter

    ruta = _png(tmp_path / "vieja.png")
    enviados = []

    class CanalDoble:
        async def send(self, content=None, file=None, **kwargs):
            enviados.append(content)

    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = types.SimpleNamespace()  # sin marcador cableado, a propósito

    assert not MediaMarker().is_marked(str(ruta))
    asyncio.run(adaptador._send_file(CanalDoble(), str(ruta), "🎨 Portada"))

    assert MediaMarker().is_marked(str(ruta)), "se marca antes de salir"
    assert "generado por IA" in enviados[0], "y se dice también a quien lo lee"


def test_la_auditoria_ve_un_formato_que_no_estaba_en_ninguna_lista(tmp_path, monkeypatch):
    """
    La auditoría filtraba por extensión antes de preguntar por la marca.

    Miraba ocho formatos y descartaba el resto en silencio, así que decía
    «ninguno pendiente» sobre un directorio con obra sin marcar dentro. Y no
    era teórico: `discord_salon.py` entrega la partitura `.mid` a un canal, y
    `HERRAMIENTAS.md` §8 obliga a archivar en `output/posts/` los `.md` de lo
    publicado. Ninguno de los dos existía para el auditor.

    Es el mismo fallo que `.gitignore` ya había corregido pasando de enumerar
    extensiones a comprobar la propiedad, y se comprueba igual: con un formato
    que nadie ha visto nunca.
    """
    from src.core.transparency import MediaMarker, audit_directory

    salida = tmp_path / "output"
    (salida / "music").mkdir(parents=True)
    (salida / "posts").mkdir()
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(salida))
    monkeypatch.setenv("YUKI_TRANSPARENCY_PATH", str(tmp_path / "transparency.json"))

    partitura = salida / "music" / "obra.mid"
    partitura.write_bytes(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0")
    (salida / "posts" / "lanzamiento.md").write_text("texto de Yuki", encoding="utf-8")
    (salida / "music" / "toma.formato-que-aun-no-existe").write_text("x", encoding="utf-8")

    informe = audit_directory()
    nombres = {Path(r).name for r in informe["sin_marcar"]}
    assert {"obra.mid", "lanzamiento.md", "toma.formato-que-aun-no-existe"} <= nombres, (
        f"la auditoría no ve obra sin marcar: {informe}")

    # Y al marcarla pasa al otro lado, sin que la extensión importe.
    MediaMarker().mark(str(partitura), model="local.midi", prompt="tema", kind="sonora")
    informe = audit_directory()
    assert str(partitura) in informe["marcados"]
    # El manifiesto lateral que acaba de escribirse no se audita a sí mismo.
    assert not any(r.endswith(".c2pa.json") for r in informe["marcados"] + informe["sin_marcar"])


def test_la_version_del_manifiesto_es_la_del_proyecto(tmp_path, monkeypatch):
    """
    El número que sale al mundo tiene que ser uno de los del proyecto.

    Había cinco distintos: `pyproject.toml` y `src/__init__.py` en 2.4.0,
    `config.yaml` en 2.5.0, `hermes_config.yaml` en 2.5, y un literal 2.6.0
    escrito a mano dentro de `claim_generator_info`. El único que viaja fuera
    —grabado en el registro de procedencia de cada obra que Yuki entrega bajo
    el Artículo 50— era justo el que no correspondía a ninguna versión
    declarada del proyecto.
    """
    import src
    from src.core.transparency import MediaMarker

    monkeypatch.setenv("YUKI_TRANSPARENCY_PATH", str(tmp_path / "t.json"))
    fichero = tmp_path / "obra.png"
    fichero.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)

    manifiesto = MediaMarker().manifest(str(fichero))
    generador = manifiesto["claim_generator_info"][0]

    assert generador["version"] == src.__version__, (
        "el manifiesto C2PA vuelve a llevar una versión propia")


def test_nadie_declara_una_version_distinta_de_la_del_proyecto():
    """Un solo sitio donde cambiarla, para que no vuelvan a ser cinco."""
    import re

    import src

    raiz = Path(__file__).resolve().parents[1]
    pyproject = (raiz / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject, (
        "pyproject vuelve a fijar la versión a mano")

    otras = set(re.findall(r'"(\d+\.\d+\.\d+)"', (raiz / "config.yaml").read_text(encoding="utf-8")))
    discrepantes = {v for v in otras if v != src.__version__}
    assert not discrepantes or all(
        "no se lee" in linea
        for linea in (raiz / "config.yaml").read_text(encoding="utf-8").splitlines()
        if any(v in linea for v in discrepantes) and "version" in linea
    ), f"config.yaml declara versiones propias sin marcarlas: {discrepantes}"
