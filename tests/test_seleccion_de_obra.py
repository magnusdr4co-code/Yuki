"""
Pruebas de qué obra usa un encargo multimedia.

Reconstruyen un incidente real: cuatro peticiones seguidas, tres generaciones
idénticas, y un Productor repitiendo «me has devuelto exactamente lo mismo»
mientras Yuki reescribía la letra una y otra vez. No era terquedad del modelo.
`_library_entry` devolvía la **primera** obra que casara por palabra clave, que
en orden de archivo es la **más vieja**, y no había forma de decir «usa ésta».

Así que reescribir la letra no podía servir de nada, por muchas veces que se
pidiera.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.adapters.discord_bot import DiscordAdapter  # noqa: E402
from src.tools.creation_library import CreationLibrary  # noqa: E402


@pytest.fixture
def adaptador(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_OUTPUT_DIR", str(tmp_path / "output"))
    biblioteca = CreationLibrary()
    adaptador = DiscordAdapter.__new__(DiscordAdapter)
    adaptador.agent = types.SimpleNamespace(creation_library=biblioteca)
    return adaptador, biblioteca


def test_gana_la_letra_mas_reciente(adaptador):
    """
    El fallo exacto del incidente.

    Se archiva una letra, luego otra mejor, y el encargo tiene que coger la
    segunda. Antes cogía la primera y el Productor no tenía manera de saber por
    qué su corrección no surtía efecto.
    """
    adaptador, biblioteca = adaptador
    vieja = biblioteca.save_text("Herrumbre y Escarcha — poema", "El óxido no duerme. " * 20)
    nueva = biblioteca.save_text("Herrumbre y Escarcha — versión vocal",
                                 "[Verse 1] El óxido no duerme. " * 20)

    elegida = adaptador._library_entry("palabra", ("letra", "poema", "herrumbre"))

    assert elegida["id"] == nueva["id"], "cogió la vieja: reescribir la letra no serviría de nada"
    assert elegida["id"] != vieja["id"]


def test_se_puede_designar_una_obra_en_el_pedido(adaptador):
    """
    «Usa ésta» tiene que existir como orden.

    Sin ella, la única forma de cambiar la obra fuente era esperar a que el
    heurístico de palabras clave acertara.
    """
    adaptador, biblioteca = adaptador
    primera = biblioteca.save_text("Herrumbre y Escarcha — poema", "El óxido no duerme. " * 20)
    biblioteca.save_text("Herrumbre y Escarcha — versión vocal", "[Verse 1] " * 40)

    elegida = adaptador._library_entry(
        "palabra", ("letra", "poema"),
        pedido=f"genera la canción usando {primera['id']}, la del poema original")

    assert elegida["id"] == primera["id"], "ignoró la obra designada explícitamente"


def test_una_designacion_que_no_existe_no_calla_ni_inventa(adaptador):
    """Si el identificador no está, se sigue por el camino normal, no se falla en silencio."""
    adaptador, biblioteca = adaptador
    real = biblioteca.save_text("Herrumbre — letra", "El óxido no duerme. " * 20)

    elegida = adaptador._library_entry("palabra", ("letra",),
                                       pedido="usa palabra-000000000000 que no existe")

    assert elegida["id"] == real["id"]


def test_sin_obras_no_se_inventa_una(adaptador):
    adaptador, _ = adaptador

    assert adaptador._library_entry("palabra", ("letra",)) is None


def test_el_inventario_ordena_por_recencia(adaptador):
    """
    Importa por el recorte a cien: en orden de inserción, pasadas cien obras el
    recorte se comía justo las nuevas — las que alguien acaba de guardar.
    """
    adaptador, biblioteca = adaptador
    primera = biblioteca.save_text("Primera", "contenido uno " * 20)
    ultima = biblioteca.save_text("Última", "contenido dos " * 20)

    ids = [e["id"] for e in biblioteca.list_entries()["entries"]]

    assert ids.index(ultima["id"]) < ids.index(primera["id"])


def test_las_obras_archivadas_llevan_su_hora(adaptador):
    """
    Sin `created_at` no existe «la más reciente». Las entradas anteriores no lo
    tienen, y para ésas vale la fecha del fichero.
    """
    adaptador, biblioteca = adaptador
    obra = biblioteca.save_text("Con hora", "contenido " * 30)

    assert obra["created_at"] > 0

    sin_hora = dict(obra)
    sin_hora.pop("created_at")
    assert biblioteca._cuando(sin_hora) > 0, "una entrada vieja sin hora debe caer al fichero"


# --- Lo que no se puede hacer, dicho antes de gastar ---

def test_el_aviso_dice_que_motor_atiende_antes_de_gastar(adaptador):
    """
    El aviso llegaba **después** de gastar. Por eso el Productor pidió la misma
    canción cantada cuatro veces, y por eso Yuki acabó inventando una
    explicación técnica para justificar un resultado que no dependía del prompt.

    Con Lyria disponible, lo honesto es decir **quién atiende y qué significa
    cada salida**, no adelantar el resultado: hasta que el proveedor responde no
    se sabe si tocó Lyria —que canta— o el respaldo local —que no—.
    """
    adaptador, biblioteca = adaptador
    letra = biblioteca.save_text("Herrumbre — letra", "El óxido no duerme. " * 20)
    adaptador.agent.media_creator = types.SimpleNamespace(
        portal=types.SimpleNamespace(vertex=types.SimpleNamespace(is_available=lambda: True)))

    aviso = adaptador._aviso_de_canto(letra)

    assert "Lyria" in aviso
    assert "respaldo local" in aviso
    assert "Herrumbre" in aviso, "el aviso debe decir de qué obra parte"


def test_el_aviso_no_niega_que_lyria_cante(adaptador):
    """
    Esto es lo que falló en producción el 11 de septiembre, y lo que esta misma
    prueba **exigía** en su versión anterior: el aviso afirmaba «ningún motor
    contratado sirve voz» y Lyria entregó una canción cantada acto seguido.

    `nous_portal` marca su resultado con `sung: True` precisamente porque canta.
    Negar una capacidad que existe es tan falso como prometer una que no.
    """
    adaptador, biblioteca = adaptador
    letra = biblioteca.save_text("Herrumbre — letra", "El óxido no duerme. " * 20)
    adaptador.agent.media_creator = types.SimpleNamespace(
        portal=types.SimpleNamespace(vertex=types.SimpleNamespace(is_available=lambda: True)))

    aviso = adaptador._aviso_de_canto(letra).lower()

    assert "saldrá instrumental" not in aviso
    assert "ningún motor" not in aviso
    assert "no cantada" not in aviso


def test_el_aviso_no_promete_lo_que_el_entorno_no_tiene(adaptador):
    """
    Sin Vertex no hay motor que cante, y ahí sí es honesto decirlo: no es negar
    una capacidad, es que no está configurada. La diferencia entre esta prueba y
    la anterior es toda la diferencia entre declarar un límite e inventarlo.
    """
    adaptador, biblioteca = adaptador
    letra = biblioteca.save_text("Herrumbre — letra", "El óxido no duerme. " * 20)
    adaptador.agent.media_creator = types.SimpleNamespace(portal=None)

    aviso = adaptador._aviso_de_canto(letra)

    assert "instrumental" in aviso.lower()
    assert "local" in aviso.lower() or "partitura propia" in aviso.lower()
    assert "Lyria" not in aviso, "sin Vertex no hay Lyria a la que nombrar"
