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

    contenido = "verso largo de la canción " * 20

    def read_entry(self, entry_id):
        return {"content": self.contenido}

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
        self.ajustes = []

    async def create_single_cover(self, track_title, visual_concept, **kwargs):
        self.conceptos.append(visual_concept)
        self.ajustes.append(kwargs)
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


def test_el_criterio_de_la_letra_gobierna_el_encargo(tmp_path, monkeypatch):
    """
    El prompt musical era una constante: 72 BPM e Insen con cualquier letra
    delante. Cuando Yuki reescribió la suya fijando 68 BPM, el encargo siguiente
    la habría contradicho en silencio.
    """
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.creation_library.contenido = (
        "`[Tempo: 68 BPM, 4/4 time signature, Key: D minor, Insen scale.]`\n"
        "#### [Verse 1]\n"
        "El astillero no duerme en calma,\n"
        "huele a salitre, metal y sal.\n"
        "Llegué descalza, vestí otra alma,\n"
        "doblé el orgullo frente a este mar.\n"
    )

    canal = _correr(adaptador, "hazme la canción")

    assert "68 BPM" in portal.prompts_cancion[0], "el prompt no respeta el tempo de la letra"
    assert "72 BPM" not in portal.prompts_cancion[0]
    assert any("Criterio para" in texto for texto in canal.textos), \
        "el criterio tiene que decirse antes de gastar, no quedarse en el prompt"


def test_una_metrica_que_atropella_se_avisa_antes_de_generar(tmp_path, monkeypatch):
    """«A veces se apresuraba el poema»: eso se sabe antes, no al escucharlo."""
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.creation_library.contenido = (
        "El astillero no duerme nunca y huele a salitre y a metal oxidado de los cargueros\n"
        "Vine descalza\n"
        "Me vestí de otra alma que no era la mía pero la elegí con sus consecuencias\n"
        "El agua corre\n"
    )

    canal = _correr(adaptador, "hazme la canción")

    assert any("desigual" in texto for texto in canal.textos)


def test_la_portada_sale_de_la_obra_y_no_de_una_constante(tmp_path, monkeypatch):
    """
    El concepto visual estaba escrito a mano en el adaptador —«agua, hierro e
    invierno»— con la luz clavada en `urushi`: la portada de cualquier obra era
    la de *Herrumbre y Escarcha*.
    """
    adaptador, _portal, creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.creation_library.contenido = (
        "Bosque de bambú al sol de la mañana,\n"
        "la luz filtrada entre las hojas verdes.\n"
        "El jardín respira despacio y el rocío cae sobre la piedra clara.\n"
    )

    canal = _correr(adaptador, "hazme sólo la portada")

    concepto = creador.conceptos[0]
    assert "bambú" in concepto or "bosque" in concepto, \
        "el concepto no sale de la obra: sigue siendo el de la constante"
    assert "hierro e invierno" not in concepto
    assert creador.ajustes[0]["lighting"] == "komorebi", "la luz sigue clavada"
    assert any("Criterio visual" in texto for texto in canal.textos)


def test_el_guion_del_video_sale_de_la_obra(tmp_path, monkeypatch):
    """Eran cuatro planos del muelle con cualquier obra delante, y Veo cobra por segundo."""
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.creation_library.contenido = (
        "#### [Amanecer en el jardín]\n"
        "La luz entra despacio entre las cañas y el rocío no tiene prisa.\n"
        "#### [Lluvia sobre la piedra]\n"
        "El agua escribe sobre el granito lo que nadie se atreve a decir.\n"
    )

    canal = _correr(adaptador, "hazme dos segmentos de vídeo")

    assert "Amanecer en el jardín" in portal.prompts_clip[0]
    assert "muelle" not in portal.prompts_clip[0]
    assert "Shot 1 of 2" in portal.prompts_clip[0]
    assert any("Criterio audiovisual" in texto for texto in canal.textos)


def test_una_letra_breve_no_cancela_la_portada(tmp_path, monkeypatch):
    """
    La guarda de brevedad es sobre el **canto**. Abortaba el encargo entero, así
    que pedir sólo la portada de un poema corto no daba portada, y el motivo que
    se daba era no presentarla como canción.
    """
    adaptador, _portal, creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.creation_library.contenido = "Agua sobre hierro."

    canal = _correr(adaptador, "hazme sólo la portada")

    assert creador.conceptos, "la portada no se produjo por una guarda que no era suya"
    assert not any("demasiado breve para una canción; no la presentaré" in texto
                   for texto in canal.textos)


def test_una_letra_breve_sigue_sin_pasar_por_cancion(tmp_path, monkeypatch):
    """Lo que la guarda protege no se pierde: un poema de una línea no es un canto."""
    adaptador, portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.creation_library.contenido = "Agua sobre hierro."

    canal = _correr(adaptador, "hazme la canción")

    assert portal.prompts_cancion == []
    assert any("demasiado breve" in texto for texto in canal.textos)
