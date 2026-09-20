"""
La cara y los colores que Yuki elige, puestos donde se ven.

El ritual de autocaracterización decidía cuatro avatares y quince colores, y
nadie los usaba: se generaban, se marcaban y se quedaban en el disco. Una
decisión suya sin consecuencia es lo mismo que no haberla tomado, y esta prueba
recorre el camino del producto —la página servida por el Salón, no el módulo
suelto— para que no vuelva a quedarse en un fichero.

Lo que se vigila, además de que aparezca:

- **Que no aparezca lo que no existe.** Sin manifiesto, la página es la de
  siempre. Con un avatar fallido o simulado, tampoco hay retrato: enseñar un
  marcador de texto como su cara sería aparentar una capacidad.
- **Que se declare lo que es.** Un retrato sintético que sale hacia una persona
  lleva su origen dicho, en la página y en la cabecera de la respuesta.
- **Que la ruta no sirva otra cosa.** Está abierta, así que sólo puede servir el
  fichero que el manifiesto declara, nunca un nombre que venga de fuera.
"""

import asyncio
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.self_characterization import SelfCharacterization  # noqa: E402
from src.web.server import SalonHTTPHandler  # noqa: E402

ESTACION = {"sekki": "Hakuro (Rocío Blanco)", "seasonal_kigo": "rocío blanco",
            "tea_element": "té de otoño", "micro_season_ko": "Las golondrinas parten"}

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
       + (1024).to_bytes(4, "big") + (1024).to_bytes(4, "big"))


@pytest.fixture()
def salon(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki.db"))
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.delenv("SALON_API_TOKEN", raising=False)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SalonHTTPHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


class PortalQueEntrega:
    """Doble del portal: escribe un PNG de verdad, como el camino de imagen."""

    def __init__(self, resultado=None):
        self.resultado = resultado

    async def generate_image_frontier(self, **kwargs):
        if self.resultado is not None:
            return self.resultado
        ruta = Path(os.environ["YUKI_OUTPUT_DIR"]) / "art" / "retrato.png"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(PNG)
        return {"status": "success", "simulated": False, "local_path": str(ruta),
                "provider": "vertex_ai", "image_url": f"file://{ruta}",
                "marking": {"marked": True}}


def _caracterizar(portal=None):
    motor = SelfCharacterization(nous_portal=portal or PortalQueEntrega())
    return asyncio.run(motor.synthesize_identity(ESTACION))


def _pagina(salon: str) -> str:
    with urllib.request.urlopen(f"{salon}/") as respuesta:
        return respuesta.read().decode("utf-8")


def test_sin_haberse_caracterizado_el_salon_es_el_de_siempre(salon):
    """Una instancia recién desplegada no tiene cara, y eso no es un fallo."""
    pagina = _pagina(salon)

    assert "/identidad/avatar" not in pagina
    assert "--yuki-" not in pagina
    # Y la página sigue en pie, con su flor.
    assert "Salón de Yuki" in pagina or "Yuki" in pagina

    with pytest.raises(urllib.error.HTTPError) as fallo:
        urllib.request.urlopen(f"{salon}/identidad/avatar")
    assert fallo.value.code == 404
    assert "retrato" in json.loads(fallo.value.read())["error"].lower()


def test_su_cara_y_sus_colores_llegan_a_la_pagina(salon):
    manifiesto = _caracterizar()

    pagina = _pagina(salon)

    assert '<img src="/identidad/avatar"' in pagina, "el Salón no enseña su cara"
    # Los colores son los suyos, no unos cualquiera.
    acento = manifiesto["visual_identity"]["color_palette"]["accent"]["accent_gold"]
    assert f"--yuki-accent-gold: {acento};" in pagina
    assert "--yuki-background-dark:" in pagina


def test_el_retrato_se_sirve_y_se_declara_generado_por_ia(salon):
    _caracterizar()

    with urllib.request.urlopen(f"{salon}/identidad/avatar") as respuesta:
        cuerpo = respuesta.read()
        assert respuesta.headers["Content-Type"] == "image/png"
        assert respuesta.headers["X-Generated-By-AI"] == "true"
    assert cuerpo == PNG

    # Y en la propia página, donde lo lee una persona.
    pagina = _pagina(salon)
    assert "Retrato generado por IA" in pagina
    assert "generados por ella misma" in pagina


def test_un_avatar_simulado_no_se_enseña_como_su_cara(salon, tmp_path):
    """
    El marcador es un fichero de texto. Servirlo como retrato sería exactamente
    lo que este proyecto llama aparentar una capacidad.
    """
    marcador = tmp_path / "output" / "art" / "retrato.png.simulado.txt"
    marcador.parent.mkdir(parents=True, exist_ok=True)
    marcador.write_text("SIMULADO", encoding="utf-8")
    _caracterizar(PortalQueEntrega({"status": "simulated", "simulated": True,
                                    "local_path": str(marcador),
                                    "note": "Marcador de texto, no un medio real."}))

    assert "/identidad/avatar" not in _pagina(salon)
    with pytest.raises(urllib.error.HTTPError) as fallo:
        urllib.request.urlopen(f"{salon}/identidad/avatar")
    assert fallo.value.code == 404


def test_un_avatar_fallido_no_deja_un_hueco_roto(salon):
    """Con el retrato fallado, la página vuelve a la flor en vez de a un 404."""
    _caracterizar(PortalQueEntrega({"status": "error", "simulated": False,
                                    "error": "Gemini no devolvió datos de imagen."}))

    pagina = _pagina(salon)

    assert "/identidad/avatar" not in pagina
    assert "🌸" in pagina


def test_la_ruta_del_retrato_no_sirve_nada_mas(salon, tmp_path):
    """
    Está abierta, así que sólo puede servir el fichero que el manifiesto declara.

    Si alguien edita el manifiesto —es un JSON en disco— para apuntar fuera del
    directorio de obra, no se sirve. `/api/outputs` acota por categoría y
    nombre; esto acota por no aceptar ningún nombre en absoluto.
    """
    _caracterizar()
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("no soy una cara", encoding="utf-8")

    manifiesto_path = Path(os.environ["DATABASE_PATH"]).parent / "identity_manifest.json"
    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    manifiesto["visual_identity"]["avatars"]["atelier"]["local_path"] = str(secreto)
    manifiesto_path.write_text(json.dumps(manifiesto), encoding="utf-8")

    with pytest.raises(urllib.error.HTTPError) as fallo:
        urllib.request.urlopen(f"{salon}/identidad/avatar")
    assert fallo.value.code == 404

    # Y tampoco por el nombre: la ruta no acepta ninguno.
    for intento in ("/identidad/avatar/../../etc/passwd", "/identidad/avatar?f=/etc/passwd"):
        try:
            with urllib.request.urlopen(f"{salon}{intento}") as respuesta:
                assert respuesta.read() != b"no soy una cara"
        except urllib.error.HTTPError as exc:
            assert exc.code in (404, 401)
