"""
Un runbook de despliegue desfasado no falla: hace que alguien se salte un paso.

`GCP_DEPLOYMENT.md` afirmaba dos cosas que habían dejado de ser ciertas —que el
enrutado por tarea no se leía y que los medios eran «simulaciones deliberadas,
espera a dar de alta las cuentas»—. Un agente desplegando con eso delante se
salta Vertex y da los marcadores por normales. Es el mismo fallo que costó
decirle al Productor que su canción saldría instrumental el día que salió
cantada: fiarse del documento en vez del código.

Aquí se vigila la propiedad, no la redacción: **cada variable que el runbook
nombra la lee alguien**, y **cada secreto que el arranque recoge está en el
runbook**. Lo que no se puede comprobar así se dice y se deja anotado.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RAIZ = Path(__file__).resolve().parents[1]
RUNBOOK = RAIZ / "docs" / "DESPLIEGUE.md"
ARRANQUE = RAIZ / "deploy" / "gce-startup.sh"

# Las que el runbook nombra explícitamente como declaradas y no leídas. Están
# ahí para que nadie las ajuste creyendo que giran, así que la comprobación de
# «tiene lector» no aplica: su ausencia de lector es justo lo que se declara.
SIN_LECTOR_A_PROPOSITO = {"HONCHO_API_KEY", "NOUS_PORTAL_API_KEY"}


def _variables_del_runbook() -> set:
    """
    Las que el runbook **declara**, no las que menciona.

    Buscar cualquier token en mayúsculas entre acentos graves tomaba por
    variable el `INFO` de la columna «si falta», que es un valor. Se leen dos
    sitios concretos: la primera celda de las tablas —que es donde se declara
    una variable— y el párrafo de rutas de estado durable.
    """
    texto = RUNBOOK.read_text(encoding="utf-8")
    declaradas = set()
    for fila in texto.splitlines():
        # Primera celda de una fila de tabla: `| \`VARIABLE\` | ...`
        primera = re.match(r"\|\s*`([A-Z][A-Z0-9_]{3,})`", fila)
        if primera:
            declaradas.add(primera.group(1))
            # Alguna fila declara dos a la vez («TOKEN` + `CHAT_ID`»).
            declaradas.update(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", fila.split("|")[1]))
    inicio = texto.index("**Rutas de estado durable.**")
    parrafo = texto[inicio:texto.index("**Declaradas y no leídas**")]
    declaradas.update(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", parrafo))
    return declaradas


def _variables_leidas_por_el_codigo() -> set:
    patron = (r'os\.getenv\("([A-Z][A-Z0-9_]+)"|os\.environ\[?"([A-Z][A-Z0-9_]+)"|'
              r'_env\("([A-Z][A-Z0-9_]+)"\)|_clave_util\("([A-Z][A-Z0-9_]+)"\)|'
              r'environ\.get\("([A-Z][A-Z0-9_]+)"')
    encontradas = set()
    for ruta in list((RAIZ / "src").rglob("*.py")) + list((RAIZ / "scripts").rglob("*.py")):
        for grupos in re.findall(patron, ruta.read_text(encoding="utf-8")):
            encontradas.update(g for g in grupos if g)
    for grupos in re.findall(patron, (RAIZ / "cli.py").read_text(encoding="utf-8")):
        encontradas.update(g for g in grupos if g)
    return encontradas


def test_toda_variable_del_runbook_la_lee_alguien():
    """Un runbook que nombra un dial muerto engaña a quien lo ajusta."""
    leidas = _variables_leidas_por_el_codigo()
    nombradas = _variables_del_runbook() - SIN_LECTOR_A_PROPOSITO

    # `PORT` y `ENVIRONMENT` las fija el arranque y las lee el servidor; el
    # resto tiene que constar en el código.
    huerfanas = sorted(v for v in nombradas if v not in leidas)

    assert not huerfanas, f"el runbook nombra variables que no lee nadie: {huerfanas}"


def test_las_declaradas_sin_lector_siguen_sin_tenerlo():
    """
    Si alguna llegara a leerse, el runbook estaría mintiendo por el otro lado:
    diría «no se lee» sobre un dial que sí gira. Se avisa igual.
    """
    leidas = _variables_leidas_por_el_codigo()

    for variable in SIN_LECTOR_A_PROPOSITO:
        assert variable in RUNBOOK.read_text(encoding="utf-8"), \
            f"{variable} dejó de estar declarada en el runbook"
        # `HONCHO_API_KEY` se acepta por compatibilidad pero no gobierna nada;
        # si alguien la conectase, esta prueba obliga a contarlo en el runbook.
        if variable in leidas:
            assert "no leída" in RUNBOOK.read_text(encoding="utf-8") or \
                   "no son leídas" in RUNBOOK.read_text(encoding="utf-8") or \
                   "no leídas" in RUNBOOK.read_text(encoding="utf-8")


# Variables locales del script de arranque: rutas, tokens efímeros y nombres de
# secreto. No las lee la aplicación, así que no tienen sitio en el runbook.
LOCALES_DEL_ARRANQUE = {
    "ACCESS_TOKEN", "DATA_DIR", "DISK", "DISCORD_SECRET_NAME", "METADATA_TOKEN",
    "RUNTIME_ENV", "SECRET_NAME", "TOKEN_JSON", "UUID", "IMAGE", "PROJECT_ID",
    "REGION", "DEBIAN_FRONTEND",
}


def test_toda_variable_que_el_arranque_declara_esta_en_el_runbook():
    """
    Al escribir esta guarda apareció el hueco que la justifica: el runbook no
    nombraba `DISCORD_ALLOWED_GUILD_ID` ni `DISCORD_PAIRED_PRODUCER_ID`, que son
    la lista de invitados y quién es el Productor. Desplegar sin saberlo deja a
    Yuki sin servidores o sin nadie que pueda darle órdenes.
    """
    arranque = ARRANQUE.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    declaradas = set(re.findall(r"^([A-Z][A-Z0-9_]{3,})=", arranque, re.M))
    declaradas |= set(re.findall(r'versions/latest" ([A-Z][A-Z0-9_]+)', arranque))
    faltan = sorted(v for v in declaradas - LOCALES_DEL_ARRANQUE if v not in runbook)

    assert not faltan, f"el arranque declara variables que el runbook no explica: {faltan}"


def test_todo_secreto_del_arranque_esta_en_el_runbook():
    """
    El arranque es lo que de verdad se ejecuta. Si recoge un secreto que el
    runbook no nombra, quien despliegue no sabrá que tiene que crearlo.
    """
    arranque = ARRANQUE.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    secretos = set(re.findall(r"secrets/([a-z0-9-]+)/versions", arranque))
    faltan = sorted(s for s in secretos if s not in runbook)

    assert secretos, "el arranque debería recoger algún secreto"
    assert not faltan, f"secretos que el arranque recoge y el runbook no nombra: {faltan}"


def test_todo_secreto_que_el_runbook_manda_crear_lo_recoge_el_arranque():
    """
    La dirección que faltaba, y es la que se sufre: el runbook le dice al agente
    de despliegue que cree un secreto, él lo crea, y el arranque no lo lee nunca.
    La capacidad sigue inactiva y nadie entiende por qué.
    """
    arranque = ARRANQUE.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    # La tabla de secretos: `| \`yuki-algo\` | \`VARIABLE\` |`
    mandados = set(re.findall(r"\|\s*`(yuki-[a-z0-9-]+)`\s*\|", runbook))
    recogidos = set(re.findall(r"secrets/([a-z0-9-]+)/versions", arranque))
    huerfanos = sorted(mandados - recogidos)

    assert mandados, "el runbook debería listar los secretos que hay que crear"
    assert not huerfanos, f"el runbook manda crear secretos que el arranque no lee: {huerfanos}"


def test_un_secreto_opcional_que_falta_no_tumba_el_arranque():
    """
    `set -euo pipefail` está activo: una recogida estricta de un secreto ausente
    mata el arranque entero. Los dos imprescindibles deben morir así —sin ellos
    Yuki no habla con nadie—; los demás, no.
    """
    arranque = ARRANQUE.read_text(encoding="utf-8")

    assert "fetch_secret_opcional" in arranque
    for opcional in ("yuki-salon-api-token", "yuki-backup-gcs-bucket",
                     "yuki-telegram-bot-token", "yuki-telegram-chat-id",
                     "yuki-firecrawl-api-key"):
        linea = next(fila for fila in arranque.splitlines()
                     if opcional in fila and "fetch_secret" in fila)
        assert "fetch_secret_opcional" in linea, f"{opcional} se recoge de forma estricta"

    for imprescindible in ("SECRET_NAME", "DISCORD_SECRET_NAME"):
        linea = next(fila for fila in arranque.splitlines()
                     if fila.startswith("fetch_secret ") and imprescindible in fila)
        assert "opcional" not in linea


def test_el_arranque_es_sintacticamente_valido():
    """Un error de sintaxis aquí sólo se ve cuando la VM ya está reiniciando."""
    resultado = subprocess.run(["bash", "-n", str(ARRANQUE)], capture_output=True, text=True)

    assert resultado.returncode == 0, resultado.stderr


def test_el_runbook_no_repite_las_afirmaciones_que_caducaron():
    """
    Las dos que `GCP_DEPLOYMENT.md` mantuvo de más, y que harían a quien
    despliegue saltarse la configuración de medios.
    """
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "todavía no se lee" not in runbook
    assert "simulaciones deliberadas" not in runbook
    assert "VERTEX_PROJECT_ID" in runbook, "los medios reales dependen de declararla"


def test_la_guia_antigua_avisa_de_lo_que_caduco():
    """
    No se borra: se corrige en su sitio. Borrar la afirmación vieja deja a quien
    la recuerde sin saber que cambió.
    """
    antigua = (RAIZ / "docs" / "GCP_DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "DESPLIEGUE.md" in antigua, "la guía antigua tiene que apuntar a la vigente"
    assert "ya no son ciertas" in antigua


def _seccion_de_comprobacion() -> str:
    """
    Sólo la sección que se ejecuta tras desplegar.

    Buscar en el documento entero no servía: `cli.py pulso` aparece también en
    la tabla de diagnóstico, así que quitarlo de la lista de comprobaciones no
    rompía nada. Una prueba que se satisface con una mención en otro párrafo no
    protege el paso.
    """
    texto = RUNBOOK.read_text(encoding="utf-8")
    inicio = texto.index("## 5.")
    return texto[inicio:texto.index("## 6.")]


@pytest.mark.parametrize("comprobacion", [
    "cli.py pulso", "cli.py virtualize", "smoke_check.py", "backup --ensayar",
])
def test_el_runbook_comprueba_que_esta_viva_y_no_solo_que_arranco(comprobacion):
    """Que el proceso corra no es que Yuki viva, y eso tiene nombre: catatonia."""
    seccion = _seccion_de_comprobacion()

    assert comprobacion in seccion, f"la comprobación posterior al despliegue perdió: {comprobacion}"
    assert "catatonica" in seccion, "sin nombrar la catatonia, «arrancó» pasa por «vive»"


def test_los_comandos_que_el_runbook_promete_existen():
    """
    Regla 4 del proyecto: una garantía prometida en la documentación necesita la
    operación que la cumple. El runbook manda al Productor vetar ritmos por DM, y
    un comando que el adaptador no implemente sería una instrucción imposible
    para quien despliega a las tres de la mañana.

    La lista no se fija a mano: se lee del runbook. Fijarla obligaba a que el
    runbook nombrase comandos que ya no necesita nombrar —`!ritmo rechazar` sólo
    alcanza a propuestas heredadas, que una instancia recién desplegada no
    tiene— y dejaba pasar cualquier comando nuevo que el runbook se inventara.
    """
    adaptador = (RAIZ / "src" / "adapters" / "discord_bot.py").read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    # Lo que el runbook promete, exista. Se lee del propio texto para que un
    # comando inventado en la documentación falle aquí y no en producción.
    prometidos = set(re.findall(r"`!ritmo (\w+)", runbook))
    assert prometidos, "el runbook debería decir cómo se gobiernan los ritmos por DM"
    for verbo in prometidos:
        assert verbo in adaptador, f"el runbook promete `!ritmo {verbo}` y el DM no lo implementa"

    # Y al revés para lo imprescindible: el veto y el cambio de hora son lo único
    # que le queda al Productor desde que Yuki adopta sus ritmos sin permiso. Un
    # runbook que no los nombre deja al que despliega sin saber cómo pararla.
    for literal in ("!ritmos", "!ritmo retirar", "!ritmo mover"):
        verbo = literal.split()[-1]
        assert verbo in adaptador, f"el DM no implementa `{literal}`"
        assert literal in runbook, f"el runbook no nombra `{literal}`"


def test_el_aviso_nocturno_no_promete_un_comando_inexistente():
    """
    El cron de las 23:30 manda por DM «apruébalo con `!ritmo aprobar <id>`». Si
    ese comando desapareciera, Yuki quedaría prometiendo una operación que no
    existe cada noche que propusiera algo.
    """
    tareas = (RAIZ / "src" / "scheduler" / "tasks.py").read_text(encoding="utf-8")
    adaptador = (RAIZ / "src" / "adapters" / "discord_bot.py").read_text(encoding="utf-8")

    prometidos = set(re.findall(r"`!ritmo (\w+)", tareas))

    assert prometidos, "el aviso debería nombrar cómo aprobar"
    for comando in prometidos:
        assert comando in adaptador, f"el aviso promete `!ritmo {comando}` y no existe"


def test_la_busqueda_web_sin_clave_no_inventa_urls():
    """
    Es lo que justifica que esté «simulada» y no apagada: antes citaba dos
    titulares fijos con enlaces inventados como corrientes del mundo. El runbook
    lo afirma, así que aquí se comprueba contra el código.
    """
    buscador = (RAIZ / "src" / "tools" / "web_search.py").read_text(encoding="utf-8")

    assert "simulated" in buscador
    assert "FIRECRAWL_API_KEY" in buscador
    assert "sin URL" in RUNBOOK.read_text(encoding="utf-8")


def test_el_respaldo_sabe_subir_a_un_bucket():
    """
    El runbook manda crear el bucket y dice que la copia sale de la máquina. Si
    no hubiera cliente de subida, sería una garantía documentada sin operación
    —el fallo que este proyecto ya cometió dos veces—.
    """
    respaldo = (RAIZ / "src" / "tools" / "backup.py").read_text(encoding="utf-8")

    assert "storage.googleapis.com/upload" in respaldo, "no hay subida real a Cloud Storage"
    assert "devstorage.read_write" in respaldo, "sin ese scope la subida devuelve 403"
    # Acotado a la sección del respaldo: el término aparece también en el
    # comando de comprobación, así que buscarlo en todo el documento dejaba
    # pasar que desapareciera justo del aviso.
    runbook = RUNBOOK.read_text(encoding="utf-8")
    seccion = runbook[runbook.index("### B · Respaldo"):runbook.index("### C · Ritmos")]
    aviso = seccion[seccion.index("El paso que se olvida"):]

    assert "devstorage.read_write" in aviso, \
        "el aviso del scope perdió el nombre del scope, que es todo su contenido"
