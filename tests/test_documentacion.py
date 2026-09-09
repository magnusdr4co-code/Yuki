"""
Pruebas de que la documentación no miente.

Este proyecto tiene una especificación de honestidad y la aplica a lo que Yuki
dice. La documentación es lo mismo: un `README` que manda ejecutar un comando
que no existe es exactamente la misma clase de fallo que una alerta muda —no
falla, engaña— y se descubre en el peor momento, que es cuando alguien la sigue
al pie de la letra porque algo se ha roto.

Ya pasó: el README mandaba ejecutar `cli.py media-test` desde hacía mucho, y ese
comando no llegó a existir nunca.

Sólo se comprueba lo verificable —que el comando, el objetivo de `make` o el
guion existan—, no lo que prometen. Comprobar que además hacen lo que dicen es
el trabajo del resto de la suite.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DOCUMENTOS = (sorted(RAIZ.glob("docs/*.md")) + sorted(RAIZ.glob("docs/historico/*.md"))
              + [RAIZ / "README.md", RAIZ / "CLAUDE.md"])

# Lo que se cita como pendiente, planificado o histórico no cuenta como promesa.
# Marcar así un criterio de diseño que nunca se cumplió es más honesto que
# borrarlo: el registro de lo que se quiso hacer también es documentación, y
# saber que algo se planificó y acabó en otro sitio vale más que el silencio.
# La convención es escribirlo en la misma línea que la cita.
PENDIENTE = re.compile(
    r"pendiente|nunca llegó a existir|histórico|se planific|se planeó|no llegó a", re.IGNORECASE)


@pytest.fixture(scope="module")
def texto_por_documento():
    return {d: d.read_text(encoding="utf-8") for d in DOCUMENTOS if d.is_file()}


def _citas(texto, patron):
    """Las citas de cada línea, saltándose las marcadas como pendientes."""
    encontradas = set()
    for linea in texto.splitlines():
        if PENDIENTE.search(linea):
            continue
        encontradas.update(re.findall(patron, linea))
    return encontradas


@pytest.fixture(scope="module")
def comandos_reales():
    ayuda = subprocess.run([sys.executable, "cli.py", "--help"], cwd=RAIZ,
                           capture_output=True, text=True, timeout=120).stdout
    dentro = re.search(r"\{([a-z0-9,_-]+)\}", ayuda)
    assert dentro, f"no pude leer los subcomandos de cli.py: {ayuda[:200]}"
    return set(dentro.group(1).split(","))


def test_todo_comando_de_cli_que_se_documenta_existe(texto_por_documento, comandos_reales):
    """
    El fallo que ya ocurrió.

    Un comando renombrado deja la documentación mintiendo en silencio, y quien
    la sigue lo descubre con la instancia rota delante.
    """
    inventados = {}
    for documento, texto in texto_por_documento.items():
        citados = _citas(texto, r"cli\.py\s+([a-z][a-z0-9_-]*)")
        faltan = sorted(c for c in citados if c not in comandos_reales)
        if faltan:
            inventados[documento.name] = faltan

    assert not inventados, f"documentan comandos que no existen: {inventados}"


def test_todo_objetivo_de_make_que_se_documenta_existe(texto_por_documento):
    objetivos = set(re.findall(r"^\.PHONY:\s*(.+)$",
                               (RAIZ / "Makefile").read_text(encoding="utf-8"),
                               re.MULTILINE)[0].split())

    inventados = {}
    for documento, texto in texto_por_documento.items():
        citados = _citas(texto, r"`make\s+([a-z][a-z0-9-]*)")
        faltan = sorted(c for c in citados if c not in objetivos)
        if faltan:
            inventados[documento.name] = faltan

    assert not inventados, f"documentan objetivos de make que no existen: {inventados}"


def test_todo_guion_que_se_documenta_existe(texto_por_documento):
    inventados = {}
    for documento, texto in texto_por_documento.items():
        citados = _citas(texto, r"scripts/([a-z_0-9]+\.py)")
        faltan = sorted(c for c in citados if not (RAIZ / "scripts" / c).is_file())
        if faltan:
            inventados[documento.name] = faltan

    assert not inventados, f"documentan guiones que no existen: {inventados}"


def test_todo_modulo_que_se_documenta_existe(texto_por_documento):
    """Los mapas de módulos envejecen igual que los comandos."""
    inventados = {}
    for documento, texto in texto_por_documento.items():
        citados = _citas(texto, r"`(src/[a-z_/]+\.py)`")
        faltan = sorted(c for c in citados if not (RAIZ / c).is_file())
        if faltan:
            inventados[documento.name] = faltan

    assert not inventados, f"documentan módulos que no existen: {inventados}"


def test_los_ficheros_de_despliegue_que_se_citan_estan_en_el_repositorio(texto_por_documento):
    """
    Un runbook que apunta a un fichero que ya no está no se puede seguir.

    Y es justo lo que alguien intenta hacer a las tres de la mañana.
    """
    inventados = {}
    for documento, texto in texto_por_documento.items():
        citados = _citas(texto, r"`(deploy/[a-zA-Z0-9_./-]+\.(?:yml|yaml))`")
        faltan = sorted(c for c in citados if not (RAIZ / c).is_file())
        if faltan:
            inventados[documento.name] = faltan

    assert not inventados, f"citan ficheros de despliegue que no existen: {inventados}"


def test_ningun_enlace_interno_apunta_a_la_nada(texto_por_documento):
    """
    El guardián que hace seguro reorganizar el directorio.

    Sin esto, mover o renombrar un documento deja enlaces rotos que nadie ve
    hasta que alguien los sigue — y en documentación operativa, quien los sigue
    lo hace con la instancia rota delante. Con esto, reorganizar falla en la CI
    en vez de fallar a las tres de la mañana.
    """
    rotos = {}
    for documento, texto in texto_por_documento.items():
        for etiqueta, destino in re.findall(r"\[([^\]]+)\]\(([^)#]+?)(?:#[^)]*)?\)", texto):
            if destino.startswith(("http://", "https://", "mailto:")):
                continue
            if not (documento.parent / destino).resolve().exists():
                rotos.setdefault(documento.name, []).append(f"[{etiqueta}]({destino})")

    assert not rotos, f"enlaces internos que no llevan a ninguna parte: {rotos}"


def test_todo_documento_esta_en_algun_indice(texto_por_documento):
    """
    Un documento que no aparece en ningún índice existe sólo para quien ya sabe
    que existe — que es justo lo contrario de para lo que se escribe.

    Los de `historico/` tienen su propio índice, y ahí además debe constar qué
    los sustituye: un histórico sin puntero al presente es un callejón.
    """
    indice = (RAIZ / "docs" / "README.md").read_text(encoding="utf-8")
    indice_historico = (RAIZ / "docs" / "historico" / "README.md").read_text(encoding="utf-8")

    huerfanos = []
    for documento in texto_por_documento:
        if documento.name in ("README.md", "CLAUDE.md"):
            continue
        donde = indice_historico if documento.parent.name == "historico" else indice
        if documento.name not in donde:
            huerfanos.append(str(documento.relative_to(RAIZ)))

    assert not huerfanos, f"documentos que no aparecen en ningún índice: {huerfanos}"


def test_lo_historico_lo_dice_en_su_cabecera(texto_por_documento):
    """
    Quien abre un documento directamente no pasa por el índice.

    Y seguir al pie de la letra un procedimiento que ya no aplica es de las
    formas más caras de perder media hora.
    """
    sin_avisar = [d.name for d, texto in texto_por_documento.items()
                  if d.parent.name == "historico" and d.name != "README.md"
                  and "**Histórico.**" not in texto[:1200]]

    assert not sin_avisar, f"documentos históricos que no lo advierten: {sin_avisar}"
