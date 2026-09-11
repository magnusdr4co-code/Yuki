"""
«Envíamelo por el Salón» tenía que poder significar algo.

D14 del incidente del 9 de septiembre: el Productor ofreció el Salón como canal
de entrega y el Salón ni se usó ni se mencionó. No fue un descuido de redacción:
`/api/outputs` enumeraba nombres de ficheros y **no había forma de traerse
ninguno**, así que la petición no llevaba a ninguna parte y nadie lo dijo.

La descarga exige credencial siempre, aunque el resto de `/api` esté abierto.
Enumerar nombres es una fuga menor; servir los bytes de la obra a quien alcance
el puerto es otra cosa, y encenderla en silencio cambiaría la exposición de una
instancia en marcha.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.web.server import SalonHTTPHandler  # noqa: E402


@pytest.fixture()
def salon(tmp_path, monkeypatch):
    """Salón real sobre un puerto efímero, con un directorio de obra propio."""
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "output" / "music").mkdir(parents=True)
    (tmp_path / "output" / "music" / "herrumbre.mp3").write_bytes(b"audio real")
    (tmp_path / "secreto.txt").write_text("no es obra", encoding="utf-8")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SalonHTTPHandler)
    httpd.daemon_threads = True
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _pedir(url, token=None):
    peticion = urllib.request.Request(url)
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(peticion, timeout=5) as respuesta:
        return respuesta.status, respuesta.read(), dict(respuesta.headers)


def test_con_credencial_el_salon_entrega_la_obra(salon, monkeypatch):
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")

    estado, cuerpo, cabeceras = _pedir(f"{salon}/api/outputs/music/herrumbre.mp3", "clave-de-prueba")

    assert estado == 200
    assert cuerpo == b"audio real"
    assert "IA (Yuki)" in cabeceras.get("X-Generated-By", ""), \
        "quien se lleve el fichero se lleva la declaración de origen con él"


def test_sin_token_declarado_la_descarga_no_se_enciende_sola(salon, monkeypatch):
    """Encenderla en silencio cambiaría la exposición de una instancia en marcha."""
    monkeypatch.delenv("SALON_API_TOKEN", raising=False)

    with pytest.raises(urllib.error.HTTPError) as fallo:
        _pedir(f"{salon}/api/outputs/music/herrumbre.mp3")

    assert fallo.value.code == 403


def test_la_credencial_no_es_opcional_para_bajarse_la_obra(salon, monkeypatch):
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")

    with pytest.raises(urllib.error.HTTPError) as fallo:
        _pedir(f"{salon}/api/outputs/music/herrumbre.mp3")

    assert fallo.value.code == 401


class _Recogida:
    """Handler mínimo: recoge lo que `_servir_obra` decide, sin abrir un socket."""

    def __init__(self):
        self.json = []
        self.cuerpo = b""
        self.estado = None

    def _send_json(self, datos, status_code=200):
        self.json.append((status_code, datos))

    def send_response(self, code):
        self.estado = code

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass

    @property
    def wfile(self):
        recogida = self

        class _W:
            def write(self, datos):
                recogida.cuerpo = datos

        return _W()


def _servir(resto):
    """Llama al servidor de obra directamente: por HTTP el cliente normaliza la ruta."""
    recogida = _Recogida()
    SalonHTTPHandler._servir_obra(recogida, resto)
    return recogida


def test_un_enlace_que_apunta_fuera_no_se_sirve(tmp_path, monkeypatch):
    """
    Un `..` en la ruta lo para la comprobación de segmentos, pero un enlace
    dentro de `output/` no: sólo la ruta **ya resuelta** dice a dónde apunta de
    verdad, y es sobre ella sobre la que se comprueba.
    """
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")
    (tmp_path / "output" / "music").mkdir(parents=True)
    (tmp_path / "secreto.txt").write_text("no es obra", encoding="utf-8")
    (tmp_path / "output" / "music" / "atajo.txt").symlink_to(tmp_path / "secreto.txt")

    recogida = _servir("music/atajo.txt")

    assert recogida.json and recogida.json[0][0] == 404
    assert recogida.cuerpo == b"", "servir el destino de un enlace es salir del directorio de obra"


def test_una_categoria_que_no_es_obra_no_se_sirve(tmp_path, monkeypatch):
    """
    `salida()` acepta cualquier nombre, y `salida("..")` sale de `output/`. La
    lista cerrada de categorías es lo que impide que un segmento así convierta
    la raíz de obra en el directorio de arriba.
    """
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")
    (tmp_path / "output").mkdir(parents=True)
    (tmp_path / "yuki_memory.db").write_bytes(b"memoria")

    recogida = _servir("../yuki_memory.db")

    assert recogida.json and recogida.json[0][0] == 404
    assert recogida.cuerpo == b""


def test_por_http_una_ruta_con_saltos_tampoco_entrega(salon, monkeypatch):
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")

    with pytest.raises(urllib.error.HTTPError) as fallo:
        _pedir(f"{salon}/api/outputs/music/..%2F..%2Fsecreto.txt", "clave-de-prueba")

    assert fallo.value.code == 404


def test_el_listado_dice_como_traerse_el_fichero(salon, monkeypatch):
    """Enumerar sin decir cómo bajarlo es lo que había."""
    monkeypatch.setenv("SALON_API_TOKEN", "clave-de-prueba")

    _estado, cuerpo, _cabeceras = _pedir(f"{salon}/api/outputs", "clave-de-prueba")
    datos = json.loads(cuerpo.decode("utf-8"))

    assert "herrumbre.mp3" in datos["music"]
    assert datos["descarga"] == "/api/outputs/<categoria>/<nombre>"


def test_sin_token_el_listado_lo_dice_en_vez_de_callarlo(salon, monkeypatch):
    monkeypatch.delenv("SALON_API_TOKEN", raising=False)

    _estado, cuerpo, _cabeceras = _pedir(f"{salon}/api/outputs")
    datos = json.loads(cuerpo.decode("utf-8"))

    assert datos["descarga"] is None
    assert "SALON_API_TOKEN" in datos["nota"]
