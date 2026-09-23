"""
El despliegue en máquina propia promete tres cosas que no fallan al romperse.

`deploy/local/` existe para poner a Yuki en un portátil que comparte máquina con
otro agente. Lo que lo hace seguro son promesas en comentarios, y una promesa en
un comentario se rompe sin que nadie se entere:

  · La plantilla sólo nombra variables que el código lee. Una que no gira
    engaña a quien la rellena, como las veintisiete claves muertas de
    `config.yaml`.
  · El Salón escucha sólo en 127.0.0.1. `docker-compose.yml` publica
    `8080:8080`, y en un portátil eso es abrirlo a la red del bar. Basta con
    copiar ese puerto aquí para perderlo sin un solo error.
  · `.env.local` y las copias no se versionan ni entran en la imagen: llevan
    claves y memoria de personas reales.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_despliegue import _variables_leidas_por_el_codigo  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = RAIZ / "deploy" / "local" / "env.local.example"
COMPOSE = RAIZ / "deploy" / "local" / "docker-compose.local.yml"


def _variables_de_la_plantilla() -> set:
    return {
        m.group(1)
        for linea in PLANTILLA.read_text(encoding="utf-8").splitlines()
        if (m := re.match(r"\s*([A-Z][A-Z0-9_]+)=", linea))
    }


def test_la_plantilla_local_solo_nombra_variables_que_alguien_lee():
    declaradas = _variables_de_la_plantilla()
    assert {"OPENROUTER_API_KEY", "DISCORD_BOT_TOKEN"} <= declaradas
    huerfanas = sorted(declaradas - _variables_leidas_por_el_codigo())
    assert not huerfanas, f"la plantilla local nombra variables que nadie lee: {huerfanas}"


def test_la_plantilla_local_no_enciende_vertex_por_descuido():
    """
    El crédito caducó: en una cuenta ya de pago, declarar el proyecto factura
    cada imagen. Encenderlo tiene que ser una decisión, no un hueco rellenado.
    """
    declaradas = _variables_de_la_plantilla()
    assert not declaradas & {"VERTEX_PROJECT_ID", "GOOGLE_CLOUD_PROJECT",
                             "GOOGLE_APPLICATION_CREDENTIALS"}


def test_el_salon_local_solo_escucha_en_la_propia_maquina():
    servicios = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for nombre, servicio in servicios.items():
        for puerto in servicio.get("ports", []):
            assert str(puerto).startswith("127.0.0.1:"), (
                f"{nombre} publica {puerto} en todas las interfaces")


def test_secretos_y_copias_locales_no_se_versionan():
    for ruta in (".env.local", "copias/yuki_backup_x.tar.gz", "migracion/yuki-disco.tgz"):
        ignorado = subprocess.run(["git", "check-ignore", "-q", ruta], cwd=RAIZ)
        assert ignorado.returncode == 0, f"{ruta} no está en .gitignore"


def test_secretos_y_copias_locales_no_entran_en_la_imagen():
    reglas = {linea.strip() for linea in
              (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    assert ".env.*" in reglas or ".env.local" in reglas
    assert {"copias/", "migracion/"} <= reglas
