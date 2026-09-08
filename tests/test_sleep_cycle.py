"""
Pruebas del ciclo de sueño.

Dos invariantes gobiernan este módulo y son lo que más se prueba aquí:

1. **Un sueño nunca es un recuerdo.** Queda marcado, fuera de la recuperación
   normal y con la advertencia escrita en el propio contenido. Lo contrario
   sería fabricar falsos recuerdos.
2. **El olvido exige las tres condiciones a la vez** —vieja, poco importante y
   nunca recuperada— y jamás toca el canon. Una memoria que se poda mal no se
   recupera con un parche.
"""

import asyncio
import os
import sqlite3
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.memory.fts5_memory import FTS5MemoryEngine  # noqa: E402
from src.memory.sleep_cycle import (  # noqa: E402
    BASE_POR_CATEGORIA, MARCA_DE_SUENO, SleepCycle, SleepPolicy, similitud, trigramas,
    trigramas_de_plantilla,
)

# Formato real con el que `MemoryManager.record_interaction` guarda un encuentro.
# La plantilla es idéntica en todos; lo único que cambia es lo que se dijo.
PLANTILLA = ("Intercambio con Productor (@producer_manager):\n"
             "- Dijo: {pregunta}\n"
             "- Yuki respondió: El agua siempre encuentra su camino hacia el mar. "
             "Qué grato tener tu presencia en esta sala hoy.")


@pytest.fixture
def motor(tmp_path):
    return FTS5MemoryEngine(db_path=str(tmp_path / "yuki.db"))


def _ciclo(motor, narrator=None, **kwargs):
    import random

    return SleepCycle(motor, SleepPolicy(**kwargs) if kwargs else SleepPolicy(),
                      narrator=narrator, rng=random.Random(7))


def _envejecer(motor, memory_id, dias):
    with sqlite3.connect(motor.db_path) as conexion:
        conexion.execute("UPDATE memories SET created_at = ?, updated_at = ? WHERE id = ?",
                         (time.time() - dias * 86400, time.time() - dias * 86400, memory_id))
        conexion.commit()


# --- Cimiento: vector de importancia y huellas ---

def test_la_migracion_es_segura_de_repetir(tmp_path):
    ruta = str(tmp_path / "yuki.db")
    primero = FTS5MemoryEngine(db_path=ruta)
    primero.add_memory("core", "t", "contenido")

    segundo = FTS5MemoryEngine(db_path=ruta)  # vuelve a arrancar sobre la misma base

    assert segundo.search("contenido", limit=1)


def test_recuperar_un_recuerdo_deja_huella(motor):
    identificador = motor.add_memory("visitor", "Encuentro", "Hablamos del puerto y del hierro.",
                                     user_id="u1")

    motor.search("puerto", user_id="u1", limit=3)

    with sqlite3.connect(motor.db_path) as conexion:
        fila = conexion.execute("SELECT recall_count, last_recalled FROM memories WHERE id = ?",
                                (identificador,)).fetchone()
    assert fila[0] == 1 and fila[1] is not None


def test_la_recurrencia_sube_la_importancia(motor):
    olvidado = motor.add_memory("visitor", "Uno", "Preguntó por el precio de las entradas.",
                                user_id="u1")
    recordado = motor.add_memory("visitor", "Dos", "Me contó lo del astillero de su abuelo.",
                                 user_id="u2")
    for _ in range(4):
        motor.search("astillero abuelo", user_id="u2", limit=3)

    _ciclo(motor).recompute_importance()

    with sqlite3.connect(motor.db_path) as conexion:
        importancias = dict(conexion.execute(
            "SELECT id, importance FROM memories WHERE id IN (?, ?)", (olvidado, recordado)))
    assert importancias[recordado] > importancias[olvidado]


def test_recalcular_dos_veces_no_infla_nada(motor):
    """Si el cálculo se alimentara de su resultado, en un mes todo sería vital."""
    motor.add_memory("visitor", "Encuentro", "Me habló del mar y del metal.", user_id="u1")
    ciclo = _ciclo(motor)
    ciclo.recompute_importance()

    with sqlite3.connect(motor.db_path) as conexion:
        primera = conexion.execute("SELECT importance FROM memories").fetchone()[0]
    ciclo.recompute_importance()
    with sqlite3.connect(motor.db_path) as conexion:
        segunda = conexion.execute("SELECT importance FROM memories").fetchone()[0]

    assert primera == pytest.approx(segunda)


# --- NREM: fusión y esquemas ---

def test_los_duplicados_se_funden_en_el_mas_antiguo(motor):
    canonico = motor.add_memory("visitor", "Encuentro", "Me habló del puerto y de la niebla.",
                                user_id="u1")
    for _ in range(3):
        motor.add_memory("visitor", "Encuentro", "Me habló del puerto y de la niebla sobre el agua.",
                         user_id="u1")

    recibo = _ciclo(motor).merge_duplicates()

    assert recibo["fusionados"] == 3
    with sqlite3.connect(motor.db_path) as conexion:
        vivos = conexion.execute("SELECT id FROM memories WHERE merged_into IS NULL").fetchall()
    assert [fila[0] for fila in vivos] == [canonico]


def test_no_se_funde_lo_de_personas_distintas(motor):
    motor.add_memory("visitor", "Encuentro", "Me habló del puerto y de la niebla.", user_id="u1")
    motor.add_memory("visitor", "Encuentro", "Me habló del puerto y de la niebla.", user_id="u2")

    assert _ciclo(motor).merge_duplicates()["fusionados"] == 0


def test_lo_fusionado_deja_de_recuperarse_pero_sigue_ahi(motor):
    """Recuperabilidad: durante unos días la fusión se puede deshacer."""
    motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido.", user_id="u1")
    motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido y frío.", user_id="u1")
    _ciclo(motor).merge_duplicates()

    resultados = motor.search("astillero", user_id="u1", limit=10)

    assert len(resultados) == 1
    with sqlite3.connect(motor.db_path) as conexion:
        total = conexion.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert total == 2, "no se borró: se marcó"


def test_el_ensayo_en_seco_no_toca_nada(motor):
    for indice in range(3):
        motor.add_memory("visitor", "Encuentro", "Me habló del puerto y de la niebla.", user_id="u1")

    recibo = _ciclo(motor).merge_duplicates(dry_run=True)

    assert recibo["fusionados"] == 2 and recibo["seco"] is True
    with sqlite3.connect(motor.db_path) as conexion:
        marcados = conexion.execute("SELECT COUNT(*) FROM memories WHERE merged_into IS NOT NULL").fetchone()[0]
    assert marcados == 0


def test_los_episodios_recurrentes_se_destilan_en_esquema(motor):
    temas = ["el astillero de su abuelo", "la banda que dejó a los veinte",
             "su mudanza a Sevilla", "el disco que no terminó"]
    for indice, tema in enumerate(temas):
        motor.add_memory("visitor", f"Encuentro {indice}", f"Me contó lo de {tema}.", user_id="u1")

    recibo = asyncio.run(_ciclo(motor).distill_schemas())

    assert recibo["esquemas_creados"] == 1
    esquemas = motor.search("esquema", user_id="u1", limit=5)
    assert any(r["kind"] == "esquema" for r in esquemas)


def test_sin_modelo_el_esquema_existe_igual_y_no_inventa(motor):
    for indice in range(4):
        motor.add_memory("visitor", f"E{indice}", f"Dato verificable número {indice}.", user_id="u1")

    asyncio.run(_ciclo(motor, narrator=None).distill_schemas())

    with sqlite3.connect(motor.db_path) as conexion:
        contenido = conexion.execute(
            "SELECT content FROM memories WHERE kind = 'esquema'").fetchone()[0]
    assert "sin destilar por el modelo" in contenido
    assert "Dato verificable número 0" in contenido


def test_el_esquema_no_se_rehace_cada_noche(motor):
    for indice in range(4):
        motor.add_memory("visitor", f"E{indice}", f"Contenido distinto {indice}.", user_id="u1")
    ciclo = _ciclo(motor)
    asyncio.run(ciclo.distill_schemas())

    segundo = asyncio.run(ciclo.distill_schemas())

    assert segundo["esquemas_creados"] == 0


# --- REM: soñar ---

def _memoria_variada(motor):
    motor.add_memory("core", "Canon", "El agua encuentra su camino hacia el mar.", tags="canon")
    motor.add_memory("visitor", "Un desconocido", "Preguntó por el precio de las entradas.",
                     user_id="u2")
    motor.add_memory("project", "Portada", "Bocetos de herrumbre y pan de oro.", tags="obra")


def test_el_sueno_une_recuerdos_lejanos(motor):
    _memoria_variada(motor)

    sueno = asyncio.run(_ciclo(motor).dream())

    assert sueno["sonado"] is True
    assert len(sueno["categorias"]) >= 2, "no puede salir de un solo rincón de la memoria"


def test_el_sueno_no_vuelve_como_recuerdo(motor):
    """La invariante del módulo: lo soñado no puede citarse como vivido."""
    _memoria_variada(motor)
    asyncio.run(_ciclo(motor).dream())

    normales = motor.search("herrumbre", limit=10)
    pedidos = motor.search("herrumbre", limit=10, include_dreams=True)

    assert all(r["kind"] != "sueno" for r in normales)
    assert any(r["kind"] == "sueno" for r in pedidos)


def test_el_sueno_lleva_la_marca_en_el_propio_contenido(motor):
    _memoria_variada(motor)

    sueno = asyncio.run(_ciclo(motor).dream())

    assert sueno["contenido"].startswith(MARCA_DE_SUENO)
    assert "no ocurrió" in MARCA_DE_SUENO


def test_sin_modelo_no_se_finge_una_imagen(motor):
    _memoria_variada(motor)

    sueno = asyncio.run(_ciclo(motor, narrator=None).dream())

    assert "sin que ninguna imagen llegara a formarse" in sueno["contenido"]


def test_con_modelo_se_teje_la_imagen(motor):
    _memoria_variada(motor)

    async def narrador(instruccion, material):
        assert "onírica" in instruccion
        return "Caminaba por un muelle hecho de partituras mojadas."

    sueno = asyncio.run(_ciclo(motor, narrator=narrador).dream())

    assert "muelle hecho de partituras" in sueno["contenido"]
    assert sueno["contenido"].startswith(MARCA_DE_SUENO)


def test_sin_material_suficiente_no_se_suena(motor):
    motor.add_memory("core", "Solo uno", "Un único recuerdo en toda la memoria.")

    sueno = asyncio.run(_ciclo(motor).dream())

    assert sueno["sonado"] is False
    assert "lejanos" in sueno["motivo"]


def test_del_sueno_nace_un_deseo(motor):
    _memoria_variada(motor)
    ciclo = _ciclo(motor)

    impulso = ciclo.impulse_from_dream(asyncio.run(ciclo.dream()))

    assert impulso["source"] == "sueno"
    assert impulso["tool_hint"] in ("write", "contemplate")


def test_los_impulsos_del_sueno_se_pueden_desactivar(motor):
    _memoria_variada(motor)
    ciclo = _ciclo(motor, dream_impulses=False)

    assert ciclo.impulse_from_dream(asyncio.run(ciclo.dream())) is None


# --- Olvido intencional ---

def test_el_olvido_exige_las_tres_condiciones(motor):
    viejo_y_leve = motor.add_memory("visitor", "Trivial", "Preguntó la hora.",
                                    user_id="u1", importance=0.4)
    viejo_pero_recordado = motor.add_memory("visitor", "Recordado", "Me contó lo de su padre.",
                                            user_id="u2", importance=0.4)
    reciente_y_leve = motor.add_memory("visitor", "Reciente", "Saludó al pasar.",
                                       user_id="u3", importance=0.4)
    _envejecer(motor, viejo_y_leve, 90)
    _envejecer(motor, viejo_pero_recordado, 90)
    motor.note_recall([viejo_pero_recordado])

    recibo = _ciclo(motor).prune()

    assert recibo["olvidados"] == 1
    with sqlite3.connect(motor.db_path) as conexion:
        vivos = {fila[0] for fila in conexion.execute("SELECT id FROM memories")}
    assert viejo_y_leve not in vivos
    assert viejo_pero_recordado in vivos and reciente_y_leve in vivos


def test_el_olvido_no_toca_el_canon_ni_las_sintesis(motor):
    for categoria in ("core", "daily_synthesis", "growth", "producer"):
        identificador = motor.add_memory(categoria, f"Pieza {categoria}", "Contenido nuclear.",
                                         importance=0.2)
        _envejecer(motor, identificador, 400)

    recibo = _ciclo(motor).prune()

    assert recibo["olvidados"] == 0


def test_lo_fijado_nunca_se_poda(motor):
    identificador = motor.add_memory("visitor", "Acuerdo", "Prometí no publicar esto.",
                                     user_id="u1", importance=0.2, pinned=True)
    _envejecer(motor, identificador, 400)

    assert _ciclo(motor).prune()["olvidados"] == 0


def test_el_olvido_emite_recibo_sin_conservar_lo_olvidado(motor):
    identificador = motor.add_memory("visitor", "Trivial", "Un secreto que hay que soltar.",
                                     user_id="u1", importance=0.3)
    _envejecer(motor, identificador, 90)
    anotaciones = []
    ciclo = SleepCycle(motor, SleepPolicy(), audit=lambda op, det: anotaciones.append((op, det)))

    recibo = ciclo.prune()

    assert recibo["olvidados"] == 1
    assert anotaciones and anotaciones[-1][0] == "sueno_olvido"
    volcado = str(anotaciones)
    assert "Trivial" in volcado, "el título permite revisar qué se soltó"
    assert "secreto que hay que soltar" not in volcado, "el contenido no se conserva"


def test_el_ensayo_en_seco_del_olvido_no_borra(motor):
    identificador = motor.add_memory("visitor", "Trivial", "Preguntó la hora.",
                                     user_id="u1", importance=0.3)
    _envejecer(motor, identificador, 90)

    recibo = _ciclo(motor).prune(dry_run=True)

    assert recibo["olvidados"] == 1 and recibo["seco"] is True
    with sqlite3.connect(motor.db_path) as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_los_fusionados_se_retiran_pasada_la_gracia(motor):
    primero = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero.", user_id="u1")
    segundo = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido.",
                               user_id="u1")
    _ciclo(motor).merge_duplicates()
    _envejecer(motor, segundo, 30)

    recibo = _ciclo(motor).prune()

    assert recibo["fusionados_retirados"] == 1
    with sqlite3.connect(motor.db_path) as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_el_ciclo_desactivado_no_hace_nada(motor):
    motor.add_memory("visitor", "Trivial", "Preguntó la hora.", user_id="u1", importance=0.1)
    ciclo = _ciclo(motor, enabled=False)

    assert "omitido" in ciclo.prune()
    assert "omitido" in asyncio.run(ciclo.dream())
    assert "omitido" in asyncio.run(ciclo.nrem())


# --- Noche completa ---

def test_la_noche_completa_encadena_las_fases(motor):
    _memoria_variada(motor)
    for indice in range(4):
        motor.add_memory("visitor", f"E{indice}", f"Me contó lo del tema {indice}.", user_id="u1")

    noche = asyncio.run(_ciclo(motor).full_night(with_prune=True))

    assert noche["nrem"]["fase"] == "nrem"
    assert noche["rem"]["fase"] == "rem"
    assert noche["olvido"]["fase"] == "olvido"


def test_la_similitud_distingue_lo_repetido_de_lo_distinto():
    assert similitud("me habló del puerto", "me habló del puerto y la niebla") > 0.5
    assert similitud("el agua encuentra su camino", "bocetos de herrumbre") < 0.2
    assert trigramas("ab") == set()



# --- Regresión: la plantilla no puede decidir una fusión ---

def test_dos_conversaciones_distintas_no_se_funden_por_compartir_formato(motor):
    """
    Hallado ejecutando el ensayo en seco contra la memoria real de la instancia.

    Dos encuentros con preguntas **distintas** daban 0.80 de similitud porque el
    andamiaje del registro —«Intercambio con X (@id): - Dijo: … - Yuki
    respondió: …»— pesa más que lo que se dijo. Con ese umbral, la consolidación
    habría borrado recuerdos diferentes creyendo que eran repeticiones.
    """
    preguntas = [
        "¿qué tal el progreso de la música?",
        "¿sigues despierta?",
        "¿has terminado la portada del single?",
        "¿te acuerdas de lo que hablamos del astillero?",
    ]
    for pregunta in preguntas:
        motor.add_memory("visitor", "Encuentro con Productor",
                         PLANTILLA.format(pregunta=pregunta), user_id="producer_manager")

    recibo = _ciclo(motor).merge_duplicates()

    assert recibo["fusionados"] == 0, "preguntas distintas son recuerdos distintos"


def test_la_misma_conversacion_repetida_si_se_funde(motor):
    for _ in range(3):
        motor.add_memory("visitor", "Encuentro con Productor",
                         PLANTILLA.format(pregunta="¿sigues despierta?"),
                         user_id="producer_manager")
    motor.add_memory("visitor", "Encuentro con Productor",
                     PLANTILLA.format(pregunta="¿qué tal el progreso de la música?"),
                     user_id="producer_manager")

    recibo = _ciclo(motor).merge_duplicates()

    assert recibo["fusionados"] == 2, "sólo las repeticiones exactas del mismo intercambio"


def test_la_plantilla_se_detecta_por_grupo_y_no_por_lista_fija():
    """Una lista fija de fórmulas conocidas envejece al primer cambio de formato."""
    textos = [PLANTILLA.format(pregunta=p) for p in ("uno", "dos", "tres", "cuatro")]

    plantilla = trigramas_de_plantilla(textos)

    assert plantilla, "el andamiaje compartido debe salir solo"
    assert similitud(textos[0], textos[1]) > 0.7, "en crudo parecen el mismo recuerdo"
    assert similitud(textos[0], textos[1], plantilla) < 0.5, "descontando la plantilla, no"


def test_copias_exactas_se_funden_aunque_todo_en_ellas_sea_plantilla(motor):
    """
    El caso contrario, y por eso hacen falta las dos señales.

    Cuando dos recuerdos son copias exactas, *todo* en ellos es plantilla y no
    queda parte propia: juzgar sólo por lo distintivo daría cero justo donde la
    fusión era evidente.
    """
    for _ in range(3):
        motor.add_memory("visitor", "Encuentro", "Intercambio con Productor:", user_id="u1")

    assert _ciclo(motor).merge_duplicates()["fusionados"] == 2
