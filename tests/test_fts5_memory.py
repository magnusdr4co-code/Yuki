"""
Pruebas del motor de memoria FTS5.

Escribían en `data/test_memory.db` y `data/test_memory.md`, rutas fijas dentro
del directorio de estado de la instancia. `CLAUDE.md` lo pone entre lo que no se
hace, y aquí la consecuencia era visible: el `tearDown` borraba el `.db` pero
nunca cerraba el motor, así que cada pasada dejaba 180 KB de `-wal`/`-shm`
sueltos junto a la memoria de verdad. Ésa es exactamente la forma de residuo que
ya mató una copia nocturna —se listaba el directorio con los laterales vivos y
se empaquetaba sin ellos—.
"""

import pytest

from src.memory.fts5_memory import FTS5MemoryEngine


@pytest.fixture
def motor(tmp_path):
    """El motor sobre una base desechable. Nada toca la instancia."""
    return FTS5MemoryEngine(db_path=str(tmp_path / "memoria.db"))


def test_lo_guardado_se_encuentra_por_palabra_suelta(motor):
    """FTS5 busca por término, no por subcadena: 'metal corea' casa sin ser literal."""
    mem_id = motor.add_memory(
        category="core",
        title="Origen de Yuki",
        content="Yuki nació en una ciudad industrial del sur de Corea donde el mar huele a metal.",
        tags="origen corea mar",
        user_id="general",
        importance=2.0,
    )
    assert mem_id is not None

    resultados = motor.search("metal corea", limit=3)

    assert len(resultados) >= 1
    assert "mar huele a metal" in resultados[0]["content"]
    assert resultados[0]["score"] > 0
    assert resultados[0]["search_latency_ms"] < 100.0


def test_el_markdown_entra_troceado_por_secciones(motor, tmp_path):
    fichero = tmp_path / "MEMORY.md"
    fichero.write_text(
        "# MEMORY.md\n"
        "## NÚCLEO INMUTABLE\n"
        "Identidad de Yuki, 42 años.\n\n"
        "## PROYECTOS CREATIVOS\n"
        "Sencillo 'Memoria de Metal y Sal'.\n",
        encoding="utf-8",
    )

    motor.load_from_markdown(str(fichero))

    resultados = motor.search("Memoria de Metal", limit=2)
    assert len(resultados) >= 1
    assert "Sencillo" in resultados[0]["content"]


def test_el_motor_no_deja_conexiones_abiertas(motor, tmp_path):
    """
    Cerrar no es cosmético: los `-wal`/`-shm` de una conexión viva sobreviven al
    borrado del `.db`, y son los que se colaban en `data/`. Se comprueba sobre el
    directorio, que es donde se notaba, y no contando descriptores.
    """
    motor.add_memory(category="core", title="t", content="contenido cualquiera",
                     tags="", user_id="general", importance=1.0)
    motor.search("contenido")

    base = tmp_path / "memoria.db"
    base.unlink()

    laterales = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("memoria.db"))
    assert laterales == [], f"quedaron laterales de una conexión sin cerrar: {laterales}"
