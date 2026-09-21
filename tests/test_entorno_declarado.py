"""
Pruebas de que `.env.example` dice la verdad sobre el entorno.

Es la misma familia que los diales muertos de `config.yaml`, en el fichero que
todo el mundo copia el primer día. Iba diecinueve variables por detrás del
código, y las que faltaban no eran accesorias:

- `DISCORD_ALLOWED_GUILD_ID` y `DISCORD_ALLOWED_CHANNEL_ID` son la lista de
  acceso del adaptador. `config.yaml` marca sus claves con «manda
  DISCORD_ALLOWED_GUILD_ID» y esa variable no estaba en el ejemplo: quien
  desplegara copiándolo rellenaba `DISCORD_ANNOUNCE_CHANNEL_ID` —que no la lee
  nadie— y dejaba la lista vacía.
- `DISCORD_PAIRED_PRODUCER_ID` decide quién puede hablarle como Productor, y
  al no estar declarada corría un identificador escrito en el fuente.
- `YUKI_FRENO` es el freno de mano que manda sobre el DM.
- Las once `YUKI_*_PATH` son las que la regla de estado durable exige para
  poder reubicar cada pieza.

Y al revés: el ejemplo invitaba a rellenar cuatro claves que no lee nadie.

Se comprueba la propiedad —lo que el código lee está declarado, y lo declarado
se lee— en vez de una lista, para que la próxima variable no dependa de que
alguien se acuerde.
"""

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

LECTURA = re.compile(
    r'(?:os\.getenv|_env|os\.environ\.get|environ\.setdefault)\(\s*["\']([A-Z][A-Z0-9_]+)["\']')
LECTURA_INDICE = re.compile(r'os\.environ\[\s*["\']([A-Z][A-Z0-9_]+)["\']')
DECLARADA = re.compile(r'^#?\s*([A-Z][A-Z0-9_]+)=')

# Variables del sistema o consumidas por una biblioteca de terceros, no por
# código de este repositorio. No son promesas rotas en ninguna dirección.
AJENAS = {
    "PATH",
    # La lee `google-auth`, no nosotros; declararla sigue siendo correcto.
    "GOOGLE_APPLICATION_CREDENTIALS",
}


@pytest.fixture(scope="module")
def leidas():
    codigo = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list(RAIZ.glob("src/**/*.py")) + list(RAIZ.glob("scripts/*.py")) + [RAIZ / "cli.py"]
    )
    return (set(LECTURA.findall(codigo)) | set(LECTURA_INDICE.findall(codigo))) - AJENAS


@pytest.fixture(scope="module")
def declaradas():
    encontradas = set()
    for linea in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        hallazgo = DECLARADA.match(linea.strip())
        if hallazgo:
            encontradas.add(hallazgo.group(1))
    return encontradas - AJENAS


@pytest.fixture(scope="module")
def lineas_marcadas():
    """
    Las declaradas que avisan de que nadie las lee, como en `config.yaml`.

    La marca vale para el bloque: desde el comentario `# no se lee:` hasta la
    siguiente línea en blanco. Así una explicación sirve para las dos o tres
    claves que comparten motivo, sin repetirla en cada línea.
    """
    marcadas, en_bloque = set(), False
    for linea in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        desnuda = linea.strip()
        if not desnuda:
            en_bloque = False
            continue
        if "no se lee" in desnuda:
            en_bloque = True
        hallazgo = DECLARADA.match(desnuda)
        if hallazgo and en_bloque:
            marcadas.add(hallazgo.group(1))
    return marcadas


def test_toda_variable_que_el_codigo_lee_esta_en_el_ejemplo(leidas, declaradas):
    """
    Quien despliega copia este fichero. Lo que no esté aquí no se pone.

    Y lo que no se pone se queda en su valor por defecto, que en el caso de una
    lista de acceso significa vacía, y en el de un identificador escrito en el
    fuente significaba el de otra persona.
    """
    faltan = sorted(leidas - declaradas)
    assert not faltan, (
        f"el código lee estas variables y `.env.example` no las declara: {faltan}")


def test_toda_variable_declarada_la_lee_alguien_o_lo_dice(declaradas, leidas, lineas_marcadas):
    """
    El contrapeso: una clave de ejemplo que no gobierna nada engaña igual.

    No se borran —documentan una intención, y `HONCHO_API_KEY` explica por qué
    existe— pero tienen que decir que no se leen, como hace `config.yaml`.
    """
    mudas = sorted(declaradas - leidas - lineas_marcadas)
    assert not mudas, (
        "estas variables están en `.env.example` y no las lee nadie; márcalas en "
        f"su bloque con `# no se lee: <por qué sigue aquí>` o impleméntalas: {mudas}")


def test_ningun_identificador_de_persona_vive_en_el_codigo():
    """
    El fuente es público. Un ID de Discord es un dato personal.

    `DEFAULT_PAIRED_PRODUCER_ID` llevaba uno real, con el nombre de su dueño en
    el comentario de al lado, y además concedía por defecto Biblioteca, terminal
    y producción multimedia a esa identidad. Se comprueba la forma —diecisiete
    a diecinueve dígitos seguidos, que es un *snowflake*— porque el siguiente no
    se va a llamar igual.
    """
    snowflake = re.compile(r'["\'](\d{17,19})["\']')
    encontrados = {}
    for fichero in sorted(RAIZ.glob("src/**/*.py")):
        for hallazgo in snowflake.findall(fichero.read_text(encoding="utf-8")):
            encontrados.setdefault(str(fichero.relative_to(RAIZ)), []).append(hallazgo)

    assert not encontrados, (
        f"identificadores que parecen de una persona, en el código: {encontrados}. "
        "Van en una variable de entorno, no en el fuente.")


def test_el_arranque_no_lleva_el_id_personal_en_claro():
    """El script público obtiene la identidad del Productor desde Secret Manager."""
    arranque = (RAIZ / "deploy/gce-startup.sh").read_text(encoding="utf-8")
    assert not re.search(r"DISCORD_PAIRED_PRODUCER_ID\s*=\s*\d{17,19}", arranque)
    assert "yuki-discord-paired-producer-id/versions/latest" in arranque
