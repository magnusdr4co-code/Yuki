"""
El panel del Salón mostraba datos escritos a mano bajo el rótulo «en Vivo».

Dos cosas distintas, encontradas al implementar M7 —el Salón como panel de
estado— y arregladas juntas:

- La «Memoria FTS5 en Vivo» eran dos entradas fijas en el HTML, con una insignia
  verde que decía `BM25 INDEX` igual con la memoria leída que con la consulta
  caída. `/api/memories` existía y no lo llamaba nadie. Un panel que inventa
  datos es peor que uno vacío: el vacío se nota y la invención no.
- El estado de un encargo sólo se veía en la DM del Productor. Ahora hay
  `/api/trabajos`, leído del disco para que conteste **también con el daemon
  caído**, que es justo cuando interesa saber dónde se quedó algo.
"""

import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.media_jobs import MediaJobStore  # noqa: E402
from src.web.server import SalonHTTPHandler  # noqa: E402

PLANTILLA = Path(__file__).resolve().parent.parent / "src" / "web" / "templates" / "salon.html"


def _sin_comentarios() -> str:
    """
    La plantilla sin sus comentarios HTML.

    Lo que se vigila es lo que el panel **muestra**. Un comentario que cite el
    dato viejo para explicar por qué se quitó no lo muestra, y una prueba que
    no distinga las dos cosas obliga a escribir mal el comentario.
    """
    return re.sub(r"<!--.*?-->", "", PLANTILLA.read_text(encoding="utf-8"), flags=re.DOTALL)


@pytest.fixture()
def salon(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SalonHTTPHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _pedir(url, token="clave-de-prueba"):
    peticion = urllib.request.Request(url)
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(peticion, timeout=5) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def test_el_panel_publica_el_estado_de_un_encargo(salon, tmp_path):
    tienda = MediaJobStore()
    trabajo = tienda.create(requester_id="42", order="pedido",
                            steps=[("cancion", "cancion"), ("entrega", "entrega")])
    fichero = tmp_path / "cancion.mp3"
    fichero.write_bytes(b"audio")
    trabajo.step("cancion").mark_done(str(fichero), note="🎼 Maqueta local")
    tienda.save(trabajo)

    datos = _pedir(f"{salon}/api/trabajos")

    assert datos["total"] == 1 and datos["en_curso"] == 1
    publicado = datos["trabajos"][0]
    assert publicado["id"] == trabajo.id
    pasos = {p["id"]: p for p in publicado["pasos"]}
    assert pasos["cancion"]["verificado"] is True
    assert pasos["entrega"]["verificado"] is False


def test_un_paso_sin_fichero_no_cuenta_como_hecho(salon, tmp_path):
    """
    El panel no puede decir «verificado» donde la entrega dice que no. Un paso
    marcado hecho cuyo fichero desapareció hay que rehacerlo, y ésa es la única
    lectura honesta.
    """
    tienda = MediaJobStore()
    trabajo = tienda.create(requester_id="42", order="pedido", steps=[("cancion", "cancion")])
    fichero = tmp_path / "se_borra.mp3"
    fichero.write_bytes(b"audio")
    trabajo.step("cancion").mark_done(str(fichero))
    tienda.save(trabajo)
    fichero.unlink()

    datos = _pedir(f"{salon}/api/trabajos")

    assert datos["trabajos"][0]["pasos"][0]["verificado"] is False


def test_el_motivo_de_un_fallo_se_publica(salon):
    tienda = MediaJobStore()
    trabajo = tienda.create(requester_id="42", order="pedido", steps=[("clip_1", "clip")])
    trabajo.step("clip_1").mark_failed("Veo devolvió 503")
    tienda.save(trabajo)

    paso = _pedir(f"{salon}/api/trabajos")["trabajos"][0]["pasos"][0]

    assert paso["error"] == "Veo devolvió 503"
    assert paso["verificado"] is False


def test_el_estado_de_los_trabajos_pide_credencial(salon):
    """Los identificadores y los motivos de fallo dicen bastante de la instancia."""
    with pytest.raises(urllib.error.HTTPError) as fallo:
        _pedir(f"{salon}/api/trabajos", token=None)

    assert fallo.value.code == 401


def test_el_panel_no_lleva_recuerdos_escritos_a_mano():
    """Eran dos entradas fijas en el HTML bajo un rótulo que decía «en Vivo»."""
    plantilla = _sin_comentarios()

    assert "Nacida en el puerto industrial" not in plantilla
    assert "El Río Antes de Tener Nombre" not in plantilla
    assert "/api/memories" in plantilla, "el panel tiene que leer la memoria de verdad"


def test_la_insignia_no_afirma_un_indice_sano_sin_haberlo_leido():
    """El verde y el `BM25 INDEX` eran fijos: iguales con la consulta caída."""
    plantilla = _sin_comentarios()

    assert ">BM25 INDEX<" not in plantilla
    assert "sin lectura" in plantilla


def test_el_panel_de_trabajos_esta_en_la_plantilla():
    plantilla = _sin_comentarios()

    assert "/api/trabajos" in plantilla
    assert 'id="jobs-list"' in plantilla


def test_las_rutinas_del_panel_son_las_que_hay(salon):
    """
    Decía «03:00 / 07:30 / 23:30» en verde: tres de las ocho. Es la misma
    afirmación falsa que Yuki le dio al Productor, pero escrita en el HTML.
    """
    datos = _pedir(f"{salon}/api/instancia")

    assert datos["rutinas_activas"] == len([r for r in datos["rutinas"] if r["activa"]])
    assert datos["rutinas_activas"] > 3, "hay más rutinas que las tres que el panel enseñaba"
    assert all(r["cron"] for r in datos["rutinas"])


def test_el_panel_no_lleva_horarios_de_cron_escritos_a_mano():
    plantilla = _sin_comentarios()

    assert "03:00 / 07:30" not in plantilla
    assert "/api/instancia" in plantilla, "las rutinas tienen que leerse de la instancia"


def test_el_pulso_del_panel_distingue_respirar_de_vivir():
    """
    Un panel verde con Yuki parada es el fallo más silencioso del proyecto, y
    tiene nombre. El verde del panel sólo puede salir con `viva`.
    """
    plantilla = _sin_comentarios()

    assert "estado === 'viva'" in plantilla
    assert "canvas-pulso" in plantilla


def test_sin_configuracion_legible_no_se_inventan_rutinas(tmp_path, monkeypatch):
    """Inventar rutinas es exactamente el fallo que este endpoint corrige."""
    from src.web.server import SalonHTTPHandler as Handler

    monkeypatch.chdir(tmp_path)
    datos = Handler._estado_de_la_instancia(object())

    assert datos["rutinas"] == []
    assert "config.yaml" in datos["error"]
