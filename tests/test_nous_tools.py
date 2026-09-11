"""
Tests de la pasarela de medios: Vertex real, marcador honesto sin Vertex.

Lo que se protege aquí, además del flujo, es la regla de `AGENTS.md` §5.4: un
medio simulado nunca puede presentarse como real. La versión anterior de este
fichero afirmaba lo contrario —comprobaba que el resultado trajera una URL de
`https://nousportal.media/cdn/`, un dominio que no aloja nada— y por tanto
sostenía el fallo en vez de detectarlo.
"""

import asyncio
import base64
import contextlib
import os
import shutil
import sys
import tempfile
import types as types_mod
import unittest
from unittest import mock

from src.tools.nous_portal import NousPortalClient, local_uri
from src.tools.media_creator import MediaCreatorTool
from src.tools.vertex_media import VertexMediaClient


def test_vertex_media_can_use_a_regional_image_endpoint():
    motor = VertexMediaClient.from_config({
        "vertex_ai": {
            "project_id": "yuki-diva",
            "location": "global",
            "media": {
                "location": "us-central1",
                "video_location": "us-central1",
                "music_location": "global",
                "image_model": "imagen-3.0-generate-002",
                "music_model": "lyria-3-pro-preview",
            },
        }
    })
    assert motor.location == "us-central1"
    assert motor.image_model == "imagen-3.0-generate-002"
    assert motor.video_location == "us-central1"
    assert motor.music_location == "global"
    assert motor.music_model == "lyria-3-pro-preview"


def test_empty_config_project_inherits_environment():
    """El vacío documental de config.yaml no debe apagar Vertex en la VM."""
    with mock.patch.dict(os.environ, {"VERTEX_PROJECT_ID": "yuki-env"}, clear=False):
        motor = VertexMediaClient.from_config({
            "vertex_ai": {"project_id": "", "enabled": True},
        })

    assert motor.project_id == "yuki-env"
    assert motor.is_available()


def portal_sin_vertex() -> NousPortalClient:
    """Pasarela con el motor real desactivado: la ruta del marcador."""
    return NousPortalClient(vertex=VertexMediaClient(project_id="", enabled=False))


class TestMediosSimulados(unittest.TestCase):
    """Sin Google Cloud configurado, todo debe declararse simulado."""

    def test_image_generation_is_marked_as_simulated(self):
        async def _run():
            portal = portal_sin_vertex()
            result = await portal.generate_image_frontier("Niebla sobre asfalto")

            self.assertEqual(result["status"], "simulated")
            self.assertTrue(result["simulated"])
            self.assertTrue(os.path.exists(result["local_path"]))
            self.assertIn("VERTEX_PROJECT_ID", result["note"])

        asyncio.run(_run())

    def test_no_fabricated_cdn_url_anywhere(self):
        """
        El fallo concreto que había: una URL de CDN inventada devuelta junto a
        `status: success`. Quien la siguiera encontraba un 404 creyendo que Yuki
        había publicado algo.
        """
        async def _run():
            portal = portal_sin_vertex()

            imagen = await portal.generate_image_frontier("Ramas secas")
            voz = await portal.synthesize_voice_tts("El agua encuentra su camino.")
            musica = await portal.generate_music_flow("Río", "shamisen y lluvia")
            video = await portal.generate_video_frontier("Niebla que avanza")

            for resultado in (imagen, voz, musica, video):
                serializado = repr(resultado)
                self.assertNotIn("nousportal.media", serializado)
                self.assertNotEqual(resultado["status"], "success")
                self.assertTrue(resultado["simulated"])

        asyncio.run(_run())

    def test_placeholder_urls_point_at_the_real_file(self):
        async def _run():
            portal = portal_sin_vertex()
            result = await portal.generate_image_frontier("Pan de oro")

            self.assertTrue(result["image_url"].startswith("file://"))
            self.assertEqual(result["image_url"], local_uri(result["local_path"]))

        asyncio.run(_run())

    def test_music_says_no_engine_is_contracted(self):
        """
        `skills/HERRAMIENTAS.md` §1 declara que suno_v4 y flow_audio no existen.
        El resultado debe decirlo, no fingir una pista.
        """
        async def _run():
            portal = portal_sin_vertex()
            result = await portal.generate_music_flow("El Río", "shamisen bajo la lluvia")

            self.assertTrue(result["simulated"])
            self.assertIn("local.midi", result["note"])

        asyncio.run(_run())

    def test_media_creator_still_works_on_the_placeholder_path(self):
        """La cadena de medios completa no se rompe sin Google Cloud."""
        async def _run():
            portal = portal_sin_vertex()
            creator = MediaCreatorTool(portal)

            result = await creator.create_single_cover(
                track_title="Cerezos de Acero",
                visual_concept="Niebla y ramas secas sobre asfalto"
            )
            self.assertEqual(result["track_title"], "Cerezos de Acero")
            self.assertIn("aesthetic", result["prompt_used"])
            self.assertTrue(result["cover_url"].startswith("file://"))

        asyncio.run(_run())

    def test_la_voz_simulada_no_se_hace_pasar_por_un_ogg(self):
        """
        Antes esto comprobaba que el resultado simulado terminara en `.ogg`, es
        decir: cristalizaba la mentira. Un marcador de texto con extensión de
        medio es un nombre que engaña aunque el contenido diga SIMULADO, y la
        auditoría del Artículo 50 lo contaba como material sin marcar.

        Lo que sí tiene que cumplirse es que se declare simulado, que el fichero
        exista de verdad y que diga cómo se habría llamado el medio real.
        """
        async def _run():
            portal = portal_sin_vertex()
            creator = MediaCreatorTool(portal)

            voice = await creator.generate_voice_reply("La paciencia es el espacio entre dos notas.")
            self.assertGreater(voice["duration"], 0)
            self.assertFalse(voice["audio_url"].endswith(".ogg"),
                             "un marcador no puede hacerse pasar por un audio")
            self.assertTrue(voice["audio_url"].endswith(".simulado.txt"))

        asyncio.run(_run())


# --- Motor real de Vertex --------------------------------------------------

@contextlib.contextmanager
def sdk_de_google_simulado():
    """
    Registra dobles de los SDK de Google mientras dura el bloque.

    El código de producción invoca la API tal como está documentada
    (`types.GenerateImagesConfig`, `interactions.VideoConfig`), así que esos
    módulos se importan aunque el cliente venga inyectado. Sustituirlos aquí
    permite probar la lógica —qué se escribe, qué se acota, qué se declara
    error— sin instalar `google-genai` ni salir a la red.
    """
    def _modulo(nombre, **atributos):
        m = types_mod.ModuleType(nombre)
        for k, v in atributos.items():
            setattr(m, k, v)
        return m

    def _constructor(**kwargs):
        return kwargs

    class Image:
        @classmethod
        def from_file(cls, location):
            return {"location": location}

    genai_types = _modulo(
        "google.genai.types",
        GenerateImagesConfig=_constructor,
        GenerateVideosConfig=_constructor,
        Image=Image,
    )
    genai_interactions = _modulo(
        "google.genai.interactions",
        GenerationConfig=_constructor,
        VideoConfig=_constructor,
        VideoResponseFormat=_constructor,
    )
    genai = _modulo("google.genai", types=genai_types, interactions=genai_interactions)

    # Cloud Text-to-Speech: el módulo v1beta1 es el que expone `prompt`, la
    # indicación de cadencia en lenguaje natural.
    tts = _modulo(
        "google.cloud.texttospeech_v1beta1",
        SynthesisInput=_constructor,
        VoiceSelectionParams=_constructor,
        AudioConfig=_constructor,
        AudioEncoding=type("AudioEncoding", (), {"OGG_OPUS": "OGG_OPUS"}),
    )
    google_cloud = _modulo("google.cloud", texttospeech_v1beta1=tts)
    client_options = _modulo("google.api_core.client_options", ClientOptions=_constructor)
    api_core = _modulo("google.api_core", client_options=client_options)

    previos = {}
    nuevos = {
        "google.genai": genai,
        "google.genai.types": genai_types,
        "google.genai.interactions": genai_interactions,
        "google.cloud": google_cloud,
        "google.cloud.texttospeech_v1beta1": tts,
        "google.api_core": api_core,
        "google.api_core.client_options": client_options,
    }
    for nombre, modulo in nuevos.items():
        previos[nombre] = sys.modules.get(nombre)
        sys.modules[nombre] = modulo
    try:
        yield
    finally:
        for nombre, anterior in previos.items():
            if anterior is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = anterior


class ImagenFalsa:
    def __init__(self, data=b"\x89PNG-datos-de-prueba"):
        self.image = type("Img", (), {"image_bytes": data})()


class ClienteGenaiFalso:
    """Doble del SDK google-genai."""

    def __init__(self, imagenes=None, error=None):
        self._imagenes = imagenes if imagenes is not None else [ImagenFalsa()]
        self._error = error
        self.recibido = {}
        self.models = self
        self.interactions = self
        self.operations = self

    def generate_images(self, model, prompt, config):
        if self._error:
            raise self._error
        self.recibido.update({"model": model, "prompt": prompt, "config": config})
        return type("Resp", (), {"generated_images": self._imagenes})()

    def create(self, model, input, generation_config=None, response_format=None, **kwargs):
        """Doble de `client.interactions.create` para el vídeo de Omni."""
        if self._error:
            raise self._error
        self.recibido.update({
            "model": model,
            "input": input,
            "generation_config": generation_config,
            "response_format": response_format,
        })
        paso = type("Paso", (), {
            "type": "model_output",
            "content": [type("Parte", (), {
                "data": base64.b64encode(b"datos-de-video-mp4").decode(),
                "mime_type": "video/mp4",
            })()],
        })()
        return type("Interaccion", (), {"steps": [paso]})()

    def generate_videos(self, model, prompt=None, image=None, config=None, **kwargs):
        self.recibido.update({"model": model, "prompt": prompt, "image": image, "config": config})
        video = type("Video", (), {"video_bytes": b"datos-de-video-mp4"})()
        generated = type("Generated", (), {"video": video})()
        response = type("Response", (), {"generated_videos": [generated]})()
        return type("Operation", (), {"done": True, "response": response})()

    def get(self, operation):
        return operation


class ClienteMusicaFalso:
    def __init__(self):
        self.interactions = self

    def create(self, model, input, **kwargs):
        audio = type("Audio", (), {"data": b"ID3-datos-de-lyria"})()
        return type("Interaccion", (), {"output_audio": audio})()


class TestVertexMedia(unittest.TestCase):

    def setUp(self):
        # Fuera del repositorio: un test no debe dejar ficheros en output/.
        self.tmp = tempfile.mkdtemp(prefix="yuki-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inactive_without_a_project(self):
        self.assertFalse(VertexMediaClient(project_id="").is_available())

    def test_active_with_a_project(self):
        self.assertTrue(VertexMediaClient(project_id="yuki-diva").is_available())

    def test_lyria_writes_a_real_mp3_result(self):
        async def _run():
            motor = VertexMediaClient(
                project_id="yuki-diva",
                client=ClienteMusicaFalso(),
                music_model="lyria-3-pro-preview",
                music_dir=self.tmp,
                music_location="global",
            )
            result = await motor.generate_music("shamisen y escarcha", duration_seconds=90)
            self.assertEqual(result["status"], "success")
            self.assertFalse(result["simulated"])
            self.assertTrue(result["local_path"].endswith(".mp3"))
            with open(result["local_path"], "rb") as f:
                self.assertEqual(f.read(), b"ID3-datos-de-lyria")

        with sdk_de_google_simulado():
            asyncio.run(_run())

    def test_can_be_switched_off_while_project_remains(self):
        self.assertFalse(VertexMediaClient(project_id="yuki-diva", enabled=False).is_available())

    def test_image_is_written_to_disk_and_marked_real(self):
        async def _run():
            cliente = ClienteGenaiFalso()
            motor = VertexMediaClient(
                project_id="yuki-diva", client=cliente,
                image_model="imagen-3.0-generate-002",
                art_dir=self.tmp,
            )
            result = await motor.generate_image("lluvia sobre metal", aspect_ratio="16:9")

            self.assertEqual(result["status"], "success")
            self.assertFalse(result["simulated"])
            self.assertTrue(os.path.exists(result["local_path"]))
            with open(result["local_path"], "rb") as f:
                self.assertEqual(f.read(), b"\x89PNG-datos-de-prueba")
            os.remove(result["local_path"])

        with sdk_de_google_simulado():
            asyncio.run(_run())

    def test_image_failure_never_becomes_a_success(self):
        async def _run():
            motor = VertexMediaClient(
                project_id="yuki-diva",
                image_model="imagen-3.0-generate-002",
                client=ClienteGenaiFalso(error=RuntimeError("cuota agotada")),
            )
            result = await motor.generate_image("lo que sea")

            self.assertEqual(result["status"], "error")
            self.assertIn("cuota agotada", result["error"])
            self.assertNotIn("local_path", result)

        with sdk_de_google_simulado():
            asyncio.run(_run())

    def test_empty_image_response_is_an_error_not_a_blank_file(self):
        """Suele ser el filtro de seguridad. Es un fallo, no una imagen."""
        async def _run():
            motor = VertexMediaClient(
                project_id="yuki-diva",
                image_model="imagen-3.0-generate-002",
                client=ClienteGenaiFalso(imagenes=[]),
            )
            result = await motor.generate_image("algo que el filtro rechaza")

            self.assertEqual(result["status"], "error")
            self.assertIn("filtro de seguridad", result["error"])

        with sdk_de_google_simulado():
            asyncio.run(_run())

    def test_video_duration_is_bounded(self):
        """
        El vídeo se factura por segundo. Una duración fuera de rango debe
        detenerse antes de la llamada, no descubrirse en la factura.
        """
        async def _run():
            motor = VertexMediaClient(project_id="yuki-diva", client=ClienteGenaiFalso())

            for duracion in (0, 2, 11, 60):
                result = await motor.generate_video("teaser", duration_seconds=duracion)
                self.assertEqual(result["status"], "error")
                self.assertIn("fuera de rango", result["error"])

        asyncio.run(_run())

    def test_video_is_written_and_reports_its_cost(self):
        """
        El coste viaja en el resultado: el vídeo se factura por segundo, y el
        productor tiene que poder ver lo que acaba de gastar sin abrir la
        consola de facturación.
        """
        async def _run():
            cliente = ClienteGenaiFalso()
            motor = VertexMediaClient(
                project_id="yuki-diva", client=cliente, video_dir=self.tmp
            )
            result = await motor.generate_video("niebla que avanza", duration_seconds=8)

            self.assertEqual(result["status"], "success")
            self.assertFalse(result["simulated"])
            self.assertEqual(result["task"], "text_to_video")
            self.assertAlmostEqual(result["estimated_cost_usd"], 0.80)
            with open(result["local_path"], "rb") as f:
                self.assertEqual(f.read(), b"datos-de-video-mp4")
            os.remove(result["local_path"])

            # La duración pedida llega al modelo con el formato que espera.
            self.assertEqual(cliente.recibido["config"]["duration_seconds"], "8")

        with sdk_de_google_simulado():
            asyncio.run(_run())

    def test_video_from_an_existing_cover_uses_image_to_video(self):
        """El flujo natural de Yuki: primero la portada, después el movimiento."""
        async def _run():
            portada = os.path.join(self.tmp, "portada_de_prueba.png")
            with open(portada, "wb") as f:
                f.write(b"\x89PNG-portada")

            cliente = ClienteGenaiFalso()
            motor = VertexMediaClient(
                project_id="yuki-diva", client=cliente, video_dir=self.tmp
            )
            result = await motor.generate_video("anímala", duration_seconds=6, image_path=portada)

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["task"], "image_to_video")
            self.assertIsNotNone(cliente.recibido["image"])
            os.remove(result["local_path"])
            os.remove(portada)

        with sdk_de_google_simulado():
            asyncio.run(_run())

    def test_video_rejects_a_missing_start_image(self):
        async def _run():
            motor = VertexMediaClient(project_id="yuki-diva", client=ClienteGenaiFalso())
            result = await motor.generate_video("anima esto", image_path="output/art/no_existe.png")

            self.assertEqual(result["status"], "error")
            self.assertIn("No existe la imagen", result["error"])

        asyncio.run(_run())

    def test_voice_rejects_empty_text(self):
        async def _run():
            motor = VertexMediaClient(project_id="yuki-diva")
            result = await motor.synthesize_voice("   ")

            self.assertEqual(result["status"], "error")
            self.assertIn("No hay texto", result["error"])

        asyncio.run(_run())

    def test_everything_errors_cleanly_without_a_project(self):
        """Sin proyecto no se llama a nada: se devuelve error, no una excepción."""
        async def _run():
            motor = VertexMediaClient(project_id="")

            for corutina in (
                motor.generate_image("x"),
                motor.generate_video("x"),
                motor.synthesize_voice("x"),
            ):
                result = await corutina
                self.assertEqual(result["status"], "error")
                self.assertIn("VERTEX_PROJECT_ID", result["error"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()


class TestPropagacionDeEstado(unittest.TestCase):
    """
    `media_creator` es lo que ve el productor. Si pierde la marca de simulado o
    revienta ante un fallo, la honestidad del resto de la cadena no sirve.
    """

    def setUp(self):
        # Fuera del repositorio: un test no debe dejar ficheros en output/.
        self.tmp = tempfile.mkdtemp(prefix="yuki-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cover_carries_the_simulated_flag_upwards(self):
        async def _run():
            creator = MediaCreatorTool(portal_sin_vertex())
            result = await creator.create_single_cover("El Río", "niebla y metal")

            self.assertTrue(result["simulated"])
            self.assertEqual(result["status"], "simulated")
            self.assertIn("VERTEX_PROJECT_ID", result["note"])

        asyncio.run(_run())

    def test_cover_survives_an_engine_failure(self):
        """
        Un fallo real no trae `model` ni `local_path`. Leerlos con corchetes
        convertía un error manejable en un KeyError a mitad del pipeline.
        """
        async def _run():
            motor = VertexMediaClient(
                project_id="yuki-diva",
                image_model="imagen-3.0-generate-002",
                client=ClienteGenaiFalso(error=RuntimeError("cuota agotada")),
            )
            creator = MediaCreatorTool(NousPortalClient(vertex=motor))

            with sdk_de_google_simulado():
                result = await creator.create_single_cover("El Río", "niebla y metal")

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["local_path"])
            self.assertIn("cuota agotada", result["error"])

        asyncio.run(_run())

    def test_voice_survives_the_absence_of_ssml(self):
        """
        Gemini TTS toma la cadencia en lenguaje natural y no devuelve SSML.
        La ruta real no puede depender de una clave que sólo existe en el
        respaldo.
        """
        class TTSFalso:
            def synthesize_speech(self, input, voice, audio_config):
                return type("R", (), {"audio_content": b"OggS-datos-de-prueba"})()

        async def _run():
            motor = VertexMediaClient(
                project_id="yuki-diva", tts_client=TTSFalso(), voice_dir=self.tmp
            )
            creator = MediaCreatorTool(NousPortalClient(vertex=motor))

            with sdk_de_google_simulado():
                result = await creator.generate_voice_reply("El agua encuentra su camino.")

            self.assertEqual(result["status"], "success")
            self.assertFalse(result["simulated"])
            self.assertIsNone(result["ssml"])          # no hay SSML en esta ruta
            self.assertIsNotNone(result["style_prompt"])
            self.assertTrue(result["local_path"].endswith(".ogg"))
            os.remove(result["local_path"])

        asyncio.run(_run())

    def test_real_voice_needs_no_transcoding(self):
        """OGG Opus nativo: el paso de ffmpeg del catálogo sobra en esta ruta."""
        class TTSFalso:
            def __init__(self):
                self.recibido = {}

            def synthesize_speech(self, input, voice, audio_config):
                self.recibido.update({"input": input, "voice": voice})
                return type("R", (), {"audio_content": b"OggS-datos"})()

        async def _run():
            tts = TTSFalso()
            motor = VertexMediaClient(
                project_id="yuki-diva", tts_client=tts, voice_dir=self.tmp
            )
            result = await motor.synthesize_voice("La pausa también dice.")

            self.assertEqual(result["encoding"], "OGG_OPUS")
            self.assertFalse(result["transcoding_required"])
            os.remove(result["local_path"])

            # La cadencia viaja como indicación en lenguaje natural, no SSML.
            # Se comprueba la **propiedad** —que la indicación diga cómo
            # respirar— y no la redacción literal: la versión anterior fijaba
            # las palabras exactas de una constante, así que cualquier mejora
            # del criterio vocal la rompía sin que nada estuviera mal.
            indicacion = tts.recibido["input"]["prompt"]
            self.assertRegex(indicacion, r"aire|pausa|silencio")
            self.assertNotIn("<break", indicacion)
            self.assertNotIn("<speak", indicacion)

            # Y la cadencia del proveedor, cuando la hay, llega al prompt: es lo
            # que la constante sí garantizaba y no se puede perder al quitarla.
            conCadencia = await motor.synthesize_voice("Otra frase.", cadencia_ms=350)
            os.remove(conCadencia["local_path"])
            self.assertIn("350", tts.recibido["input"]["prompt"])

        with sdk_de_google_simulado():
            asyncio.run(_run())


def test_los_marcadores_no_ensucian_la_auditoria_del_articulo_50(tmp_path, monkeypatch):
    """
    Una comprobación de conformidad en rojo permanente es peor que no tenerla.

    Los marcadores eran ficheros de texto con extensión `.png`/`.mp3`, así que
    la auditoría los contaba como material sintético sin marcar. Cada pasada
    dejaba cinco, la comprobación de humo fallaba siempre, y la única salida
    razonable para quien la mirase era aprender a ignorar ese rojo — que es
    exactamente lo que no puede pasar con el Artículo 50.
    """
    import asyncio

    from src.core.transparency import audit_directory

    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path))
    portal = portal_sin_vertex()

    asyncio.run(portal.generate_image_frontier("Niebla"))
    asyncio.run(portal.generate_music_flow("El Río", "shamisen"))
    asyncio.run(portal.synthesize_voice_tts("Una frase."))
    asyncio.run(portal.generate_video_frontier("Niebla que avanza"))

    auditoria = audit_directory(str(tmp_path))

    assert not auditoria["sin_marcar"], (
        f"los marcadores simulados ensucian la conformidad: {auditoria['sin_marcar']}")
    # Y siguen existiendo de verdad: no se ha ganado el verde escondiéndolos.
    assert list(tmp_path.rglob("*.simulado.txt")), "no escribió ningún marcador"
