"""
Un avatar de Yuki se pinta con su cara, no con la palabra «silueta».

El 22 de septiembre el Productor lo pidió así: «si pones "mi silueta",
descríbele al generador de imágenes cómo eres, o pásale una imagen de
contexto». `generate_named_avatar` mandaba el concepto a secas —los rasgos
canónicos vivían dentro del ritual del cron y sólo los leía él— y en la misma
conversación Yuki se describió con un pelo que no es el suyo.
"""

import asyncio
import contextlib
import json
import sys
import types

from src.core.self_characterization import RASGOS, SelfCharacterization
from src.tools.vertex_media import VertexMediaClient


class PortalQueAnota:
    """Doble del portal: guarda con qué se le llamó y devuelve un fichero real."""

    def __init__(self, tmp_path, nota=None):
        self.tmp_path = tmp_path
        self.llamadas = []
        self.nota = nota

    async def generate_image_frontier(self, **kwargs):
        self.llamadas.append(kwargs)
        ruta = self.tmp_path / f"retrato_{len(self.llamadas)}.png"
        ruta.write_bytes(b"\x89PNG")
        return {"status": "success", "local_path": str(ruta), "reference_note": self.nota}


def _con_manifiesto(tmp_path, avatar_atelier):
    motor = SelfCharacterization.__new__(SelfCharacterization)
    motor._manifest = {"visual_identity": {"avatars": {"atelier": {
        "status": "success", "local_path": str(avatar_atelier)}}}}
    motor.avatars_dir = str(tmp_path)
    return motor


def test_el_avatar_bajo_demanda_lleva_sus_rasgos_canonicos(tmp_path):
    motor = SelfCharacterization.__new__(SelfCharacterization)
    motor._manifest = None
    motor.manifest_path = str(tmp_path / "no-existe.json")
    motor._load_existing_manifest = lambda: None
    motor.nous_portal = PortalQueAnota(tmp_path)

    avatar = asyncio.run(motor.generate_named_avatar(
        "Tinta sumi-e: mi silueta apenas insinuada con aguada gris ceniza"))

    prompt = motor.nous_portal.llamadas[0]["prompt"]
    assert prompt.startswith(RASGOS), "el generador recibió «mi silueta» sin saber de quién"
    assert "sumi-e" in prompt
    assert avatar["status"] == "success"
    assert "reference_image" not in motor.nous_portal.llamadas[0]


def test_con_un_avatar_canonico_en_disco_se_manda_como_referencia(tmp_path):
    atelier = tmp_path / "atelier.png"
    atelier.write_bytes(b"\x89PNG")
    motor = _con_manifiesto(tmp_path, atelier)
    motor.nous_portal = PortalQueAnota(tmp_path)

    avatar = asyncio.run(motor.generate_named_avatar("Mokuhanga industrial, retrato frontal"))

    assert motor.nous_portal.llamadas[0]["reference_image"] == str(atelier)
    assert avatar["reference_image"] == str(atelier)


def test_una_referencia_que_el_modelo_no_admite_no_se_da_por_usada(tmp_path):
    atelier = tmp_path / "atelier.png"
    atelier.write_bytes(b"\x89PNG")
    motor = _con_manifiesto(tmp_path, atelier)
    motor.nous_portal = PortalQueAnota(tmp_path, nota="imagen-3 no admite imagen de referencia")

    avatar = asyncio.run(motor.generate_named_avatar("Plumilla técnica"))

    assert avatar["reference_image"] is None
    assert "no admite" in avatar["reference_note"]


def test_identity_get_devuelve_los_rasgos_para_que_no_invente_otros(tmp_path):
    motor = SelfCharacterization.__new__(SelfCharacterization)
    motor._manifest = None
    motor._load_existing_manifest = lambda: None
    assert motor.identity_summary()["rasgos"] == RASGOS


# --- Vertex: la referencia llega al modelo, o se dice que no -----------------

@contextlib.contextmanager
def _sdk_con_partes():
    """`google.genai.types` mínimo: lo que usa la rama Gemini de `generate_image`."""
    tipos = types.ModuleType("google.genai.types")

    class Part:
        @staticmethod
        def from_bytes(data, mime_type):
            return {"bytes": data, "mime_type": mime_type}

    tipos.Part = Part
    tipos.GenerateContentConfig = lambda **kwargs: kwargs
    tipos.GenerateImagesConfig = lambda **kwargs: kwargs
    genai = types.ModuleType("google.genai")
    genai.types = tipos
    google = sys.modules.get("google") or types.ModuleType("google")
    previos = {nombre: sys.modules.get(nombre) for nombre in ("google", "google.genai", "google.genai.types")}
    sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": tipos})
    anterior_genai = getattr(google, "genai", None)
    google.genai = genai
    try:
        yield
    finally:
        for nombre, modulo in previos.items():
            if modulo is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = modulo
        if anterior_genai is None:
            with contextlib.suppress(AttributeError):
                delattr(google, "genai")
        else:
            google.genai = anterior_genai


class GeminiQueAnota:
    def __init__(self):
        self.models = self
        self.contenidos = []

    def generate_content(self, model, contents, config):
        self.contenidos.append(contents)
        parte = types.SimpleNamespace(inline_data=types.SimpleNamespace(data=b"\x89PNG-generada"))
        return types.SimpleNamespace(candidates=[types.SimpleNamespace(
            content=types.SimpleNamespace(parts=[parte]))])

    def generate_images(self, model, prompt, config):
        self.contenidos.append(prompt)
        imagen = types.SimpleNamespace(image=types.SimpleNamespace(image_bytes=b"\x89PNG-imagen"))
        return types.SimpleNamespace(generated_images=[imagen])


def test_gemini_recibe_la_imagen_de_referencia_junto_al_texto(tmp_path):
    referencia = tmp_path / "atelier.png"
    referencia.write_bytes(b"\x89PNG-atelier")
    cliente = GeminiQueAnota()
    motor = VertexMediaClient(project_id="yuki", client=cliente, art_dir=str(tmp_path),
                              image_model="gemini-2.5-flash-image")
    with _sdk_con_partes():
        resultado = asyncio.run(motor.generate_image("retrato", reference_image=str(referencia)))

    parte, texto = cliente.contenidos[0]
    assert parte == {"bytes": b"\x89PNG-atelier", "mime_type": "image/png"}
    assert texto == "retrato"
    assert resultado["reference_image"] == str(referencia)
    receta = json.loads((tmp_path / (resultado["local_path"].split("/")[-1] + ".receta.json")).read_text())
    assert receta["parametros"]["imagen_de_partida"] == str(referencia)


def test_imagen_no_admite_referencia_y_el_resultado_lo_dice(tmp_path):
    referencia = tmp_path / "atelier.png"
    referencia.write_bytes(b"\x89PNG-atelier")
    cliente = GeminiQueAnota()
    motor = VertexMediaClient(project_id="yuki", client=cliente, art_dir=str(tmp_path),
                              image_model="imagen-3.0-generate-002")
    with _sdk_con_partes():
        resultado = asyncio.run(motor.generate_image("retrato", reference_image=str(referencia)))

    assert cliente.contenidos == ["retrato"]
    assert resultado["reference_image"] is None
    assert "no admite imagen de referencia" in resultado["reference_note"]


def test_camino_completo_el_avatar_llega_a_gemini_con_sus_rasgos_y_su_referencia(tmp_path):
    """
    Del `avatar_generate` del arnés al modelo, sin dobles en medio: el ritual,
    el portal real y el cliente de Vertex real. Una referencia que se quedara
    por el camino haría pasar las pruebas de cada pieza suelta.
    """
    from src.tools.nous_portal import NousPortalClient

    atelier = tmp_path / "atelier.png"
    atelier.write_bytes(b"\x89PNG-atelier")
    cliente = GeminiQueAnota()
    vertex = VertexMediaClient(project_id="yuki", client=cliente, art_dir=str(tmp_path),
                               image_model="gemini-2.5-flash-image")
    motor = _con_manifiesto(tmp_path, atelier)
    motor.nous_portal = NousPortalClient(vertex=vertex)

    with _sdk_con_partes():
        avatar = asyncio.run(motor.generate_named_avatar("Tinta sumi-e y hierro lavado"))

    parte, texto = cliente.contenidos[0]
    assert parte["bytes"] == b"\x89PNG-atelier"
    assert RASGOS in texto and "sumi-e" in texto
    assert avatar["status"] == "success"
