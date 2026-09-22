"""
Un encargo que falla dice por qué, y lo ya pagado no se pierde por contabilidad.

El 22 de septiembre dos encargos de portada acabaron en «La producción
multimedia falló; no doy por generados ni entregados archivos…» sin una palabra
sobre la causa, y el presupuesto del segundo ya contaba la imagen del primero:
se pagó y no llegó. La reproducción local con las clases reales da exactamente
esos síntomas cuando la Biblioteca tiene una copia huérfana —un fichero escrito
cuyo índice no llegó a confirmarse—: `inventory()` lanzaba `FileExistsError`
entre «generada» y «adjuntada», y el `except` general se tragaba el motivo.
"""

import asyncio
import hashlib
import os
from pathlib import Path

from src.tools.creation_library import CreationLibrary

from tests.test_alcance_del_encargo import CanalDoble, CreadorDoble, _adaptador, _correr

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _huerfana(biblioteca: CreationLibrary, original) -> None:
    """La copia que dejó un proceso muerto entre escribir el fichero y el índice."""
    biblioteca.initialize()
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    (biblioteca.root / "visual" / "en-desarrollo" / f"visual-{digest[:20]}.png").write_bytes(
        original.read_bytes())


# --- La Biblioteca ----------------------------------------------------------

def test_una_copia_huerfana_identica_se_adopta_en_el_indice(tmp_path):
    arte = tmp_path / "art"
    arte.mkdir()
    original = arte / "vieja.png"
    original.write_bytes(PNG)
    biblioteca = CreationLibrary(tmp_path)
    _huerfana(biblioteca, original)

    informe = biblioteca.inventory()

    assert informe["errors"] == []
    assert informe["total"] == 1


def test_un_fichero_que_no_se_puede_archivar_no_tumba_el_inventario(tmp_path):
    """Un conflicto es un error de ese fichero: va a `errors` y el resto se archiva."""
    arte = tmp_path / "art"
    arte.mkdir()
    conflictiva = arte / "a_conflicto.png"
    conflictiva.write_bytes(PNG + b"uno")
    (arte / "b_buena.png").write_bytes(PNG + b"dos")
    biblioteca = CreationLibrary(tmp_path)
    biblioteca.initialize()
    digest = hashlib.sha256(conflictiva.read_bytes()).hexdigest()
    (biblioteca.root / "visual" / "en-desarrollo" / f"visual-{digest[:20]}.png").write_bytes(b"otra")

    informe = biblioteca.inventory()

    assert informe["total"] == 1, "la buena no se archivó por culpa de la conflictiva"
    assert any("a_conflicto.png" in error and "Conflicto" in error for error in informe["errors"])


# --- El encargo, por su camino ------------------------------------------------

class CreadorEnOutput(CreadorDoble):
    """Escribe la portada donde la escribe Vertex: en `output/art`, que el inventario recorre."""

    async def create_single_cover(self, track_title, visual_concept, **kwargs):
        self.conceptos.append(visual_concept)
        destino = tmp_output() / "art" / f"portada_{len(self.conceptos)}.png"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(PNG + str(len(self.conceptos)).encode())
        return {"status": "success", "local_path": str(destino), "simulated": False}


def tmp_output():
    return Path(os.environ["YUKI_OUTPUT_DIR"])


def test_la_portada_pagada_se_entrega_aunque_la_biblioteca_tenga_una_huerfana(tmp_path, monkeypatch):
    """
    Camino del producto con la Biblioteca real. Sin el arreglo, esta prueba
    reproduce el 22 de septiembre: portada generada, `FileExistsError` en el
    inventario, nada adjunto y un fallo sin motivo.
    """
    biblioteca = CreationLibrary()
    vieja = tmp_output() / "art" / "aaa_vieja.png"
    vieja.parent.mkdir(parents=True, exist_ok=True)
    vieja.write_bytes(PNG + b"vieja")
    _huerfana(biblioteca, vieja)
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch, biblioteca=biblioteca)
    adaptador.agent.media_creator = CreadorEnOutput(tmp_path)

    canal = _correr(adaptador, "hazme sólo la portada del sencillo")

    assert canal.adjuntos == ["portada_1.png"], canal.textos
    assert not any("falló" in texto for texto in canal.textos)


def test_si_archivar_falla_la_obra_sale_igual_y_se_dice(tmp_path, monkeypatch):
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)

    def _inventario_roto():
        raise OSError("disco lleno")
    adaptador.agent.creation_library.inventory = _inventario_roto

    canal = _correr(adaptador, "hazme sólo la portada del sencillo")

    assert any(nombre.startswith("portada_") for nombre in canal.adjuntos)
    assert any("no pude archivarla" in texto and "disco lleno" in texto for texto in canal.textos)


def test_un_fallo_del_encargo_dice_el_error_concreto_y_lo_sella_en_el_trabajo(tmp_path, monkeypatch):
    """«La producción multimedia falló» sin motivo es la prosa que la especificación prohíbe."""
    adaptador, _portal, creador = _adaptador(tmp_path, monkeypatch)

    async def _revienta(**kwargs):
        raise RuntimeError("Vertex devolvió 500")
    creador.create_single_cover = _revienta

    canal = _correr(adaptador, "hazme sólo la portada del sencillo")

    assert any("RuntimeError — Vertex devolvió 500" in texto for texto in canal.textos)
    trabajo, = adaptador.media_jobs.list_jobs()
    assert trabajo.fallo == "RuntimeError — Vertex devolvió 500"


def test_el_acuse_de_una_portada_no_anuncia_segundos_de_video(tmp_path, monkeypatch):
    from src.adapters.encargo import leer_encargo

    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch)
    adaptador.agent.config = {}
    linea = adaptador._coste_previsto(leer_encargo("hazme sólo la portada del sencillo", 4))
    assert "1 imagen" in linea
    assert "vídeo" not in linea


# --- De qué letra sale la portada ----------------------------------------------

class BibliotecaDeDos:
    """Dos letras: la vieja de siempre y una más reciente sin palabra clave en el título."""

    def __init__(self, root):
        self.root = root
        (root / "vieja.md").write_text("verso " * 40, encoding="utf-8")
        (root / "nueva.md").write_text("verso " * 40, encoding="utf-8")

    def list_entries(self):
        return {"entries": [
            {"id": "palabra-bb22", "kind": "palabra", "title": "Cerezos de acero",
             "source": "producer_dm", "path": "nueva.md"},
            {"id": "palabra-aa11", "kind": "palabra",
             "title": "Herrumbre y Escarcha — Encargo Sonoro Revisado (Vocal)",
             "source": "producer_dm", "path": "vieja.md"},
        ]}

    def read_entry(self, entry_id):
        return {"content": "verso largo de la canción " * 20}

    def inventory(self):
        return {}


def test_la_portada_no_sale_siempre_de_herrumbre_y_escarcha(tmp_path, monkeypatch):
    """
    «herrumbre» estaba escrita a mano entre las claves de búsqueda de la letra,
    y como gana la primera que casa, esa obra se imponía a cualquier otra más
    reciente. Las dos portadas del 22 de septiembre salieron de ella.
    """
    adaptador, _portal, _creador = _adaptador(tmp_path, monkeypatch,
                                              biblioteca=BibliotecaDeDos(tmp_path))
    canal = _correr(adaptador, "hazme sólo la portada del sencillo")
    criterio = next(texto for texto in canal.textos if "Criterio visual" in texto)
    assert "Cerezos de acero" in criterio
    assert "Herrumbre" not in criterio


def test_preguntada_por_un_encargo_fallido_yuki_puede_leer_el_error_real(tmp_path, monkeypatch):
    """
    El trabajo falla por el camino del adaptador y el arnés lo lee con
    `encargos_recientes`: la misma tienda, el mismo motivo sellado.
    """
    from src.core.producer_harness import ProducerHarness
    from tests.test_producer_harness import agent_for, call

    adaptador, _portal, creador = _adaptador(tmp_path, monkeypatch)

    async def _revienta(**kwargs):
        raise RuntimeError("Vertex devolvió 500")
    creador.create_single_cover = _revienta
    _correr(adaptador, "hazme sólo la portada del sencillo")

    turnos = [
        {"role": "assistant", "content": "", "tool_calls": [call("encargos_recientes")]},
        {"role": "assistant", "content": "Falló con un 500 de Vertex."},
    ]
    agente = agent_for(tmp_path, turnos)
    agente.discord_adapter = adaptador
    vistos = []
    original = agente.llm_router.generate_with_tools

    def _mirar(messages, tools, route=None):
        vistos.extend(m.get("content", "") for m in messages if m.get("role") == "tool")
        return original(messages, tools, route)
    agente.llm_router.generate_with_tools = _mirar

    respuesta = asyncio.run(ProducerHarness(agente).run("Yuki", "¿qué problema hubo?"))

    assert "✓ encargos_recientes: 1" in respuesta
    assert any("RuntimeError — Vertex devolvió 500" in contenido for contenido in vistos)


def test_un_recorrido_que_llega_al_final_no_arrastra_el_motivo_del_anterior(tmp_path, monkeypatch):
    """Quien sella el campo es el `except`; quien lo limpia, el recorrido siguiente."""
    adaptador, _portal, creador = _adaptador(tmp_path, monkeypatch)
    original = creador.create_single_cover

    async def _revienta(**kwargs):
        raise RuntimeError("Vertex devolvió 500")
    creador.create_single_cover = _revienta
    _correr(adaptador, "hazme sólo la portada del sencillo")
    trabajo, = adaptador.media_jobs.list_jobs()
    assert trabajo.fallo

    creador.create_single_cover = original
    asyncio.run(adaptador._run_dm_media_delivery("42", "Productor", trabajo.order, CanalDoble(),
                                                 job=trabajo))
    assert adaptador.media_jobs.get(trabajo.id).fallo is None
