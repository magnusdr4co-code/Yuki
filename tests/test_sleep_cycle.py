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


# --- Deshacer una fusión: la recuperabilidad prometida ---

def test_una_fusion_se_puede_deshacer_dentro_del_plazo(motor):
    """La documentación prometía siete días de gracia; sin esta operación, era una intención."""
    canonico = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido.",
                                user_id="u1")
    motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido y frío.",
                     user_id="u1")
    ciclo = _ciclo(motor)
    ciclo.merge_duplicates()
    assert len(motor.search("astillero", limit=10)) == 1

    recibo = ciclo.undo_merge(canonico)

    assert recibo["restaurados"] == 1
    assert len(motor.search("astillero", limit=10)) == 2


def test_deshacer_devuelve_tambien_las_recuperaciones(motor):
    """
    Si se quedaran en el canónico arrastraría una recurrencia que no es suya, y
    el siguiente recálculo lo trataría como más vivo de lo que es.
    """
    canonico = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido.",
                                user_id="u1")
    absorbido = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido y frío.",
                                 user_id="u1")
    # Dos recuperaciones distintas: `note_recall` cuenta una por llamada, no una
    # por identificador repetido dentro de la misma búsqueda.
    motor.note_recall([absorbido])
    motor.note_recall([absorbido])
    ciclo = _ciclo(motor)
    ciclo.merge_duplicates()

    with sqlite3.connect(motor.db_path) as conexion:
        tras_fusion = conexion.execute("SELECT recall_count FROM memories WHERE id = ?",
                                       (canonico,)).fetchone()[0]
    ciclo.undo_merge(canonico)
    with sqlite3.connect(motor.db_path) as conexion:
        tras_deshacer = conexion.execute("SELECT recall_count FROM memories WHERE id = ?",
                                         (canonico,)).fetchone()[0]

    assert tras_fusion == 2
    assert tras_deshacer == 0


def test_las_fusiones_pendientes_se_pueden_mirar_antes_de_decidir(motor):
    canonico = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido.",
                                user_id="u1")
    motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido y frío.",
                     user_id="u1")
    ciclo = _ciclo(motor)
    ciclo.merge_duplicates()

    pendientes = ciclo.pending_merges()

    assert len(pendientes) == 1
    assert pendientes[0]["canonico"] == canonico
    assert 0 < pendientes[0]["expira_en_dias"] <= 7


def test_deshacer_lo_que_ya_se_olvido_lo_dice_en_vez_de_fingir(motor):
    recibo = _ciclo(motor).undo_merge(9999)

    assert recibo["restaurados"] == 0
    assert "gracia" in recibo["motivo"]


def test_deshacer_deja_constancia(motor):
    canonico = motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero.", user_id="u1")
    motor.add_memory("visitor", "Encuentro", "Niebla sobre el astillero dormido.", user_id="u1")
    anotaciones = []
    ciclo = SleepCycle(motor, SleepPolicy(), audit=lambda op, det: anotaciones.append(op))
    ciclo.merge_duplicates()

    ciclo.undo_merge(canonico)

    assert "sueno_fusion_deshecha" in anotaciones


# --- Corrientes: esquemas por tema, no sólo por persona ---

def _dos_corrientes(motor):
    for indice, persona in enumerate(("u1", "u2", "u3", "u4")):
        motor.add_memory("visitor", f"E{indice}",
                         f"Volvimos a hablar del astillero, del óxido y la niebla del puerto ({indice}).",
                         user_id=persona)
    for indice, persona in enumerate(("u5", "u6", "u7", "u8")):
        motor.add_memory("visitor", f"F{indice}",
                         f"Le interesaba la ceremonia del té y el silencio entre dos gestos ({indice}).",
                         user_id=persona)


def test_las_corrientes_emergen_a_traves_de_personas_distintas(motor):
    """El esquema de vínculo dice quién es alguien; la corriente, qué la ocupa."""
    _dos_corrientes(motor)

    recibo = asyncio.run(_ciclo(motor).distill_themes())

    assert recibo["temas"] == 2
    titulos = [r["title"] for r in motor.search("corriente", limit=10)]
    assert any("astillero" in t for t in titulos)
    assert any("ceremonia" in t or "gestos" in t for t in titulos)


def test_una_corriente_no_se_rehace_cada_noche(motor):
    _dos_corrientes(motor)
    ciclo = _ciclo(motor)
    asyncio.run(ciclo.distill_themes())

    assert asyncio.run(ciclo.distill_themes())["temas"] == 0


def test_la_etiqueta_del_tema_no_sale_de_palabras_vacias(motor):
    _dos_corrientes(motor)

    asyncio.run(_ciclo(motor).distill_themes())

    for resultado in motor.search("corriente", limit=10):
        etiqueta = resultado["title"].split("—")[-1]
        assert "que" not in etiqueta.split(", ")
        assert "para" not in etiqueta.split(", ")


def test_sin_material_suficiente_no_hay_corrientes(motor):
    motor.add_memory("visitor", "Uno", "Un único encuentro suelto.", user_id="u1")

    assert asyncio.run(_ciclo(motor).distill_themes())["temas"] == 0


def test_el_umbral_de_plantilla_no_puede_comerse_el_contenido():
    """
    Regresión del segundo fallo del filtro.

    Con un umbral flojo, lo que comparten cuatro recuerdos del mismo tema se
    marcaba como plantilla y no quedaba corriente que detectar.
    """
    tema = [f"Volvimos a hablar del astillero y de la niebla del puerto ({i})." for i in range(4)]
    otros = [f"Le interesaba la ceremonia del té y el silencio ({i})." for i in range(4)]

    plantilla = trigramas_de_plantilla(tema + otros)

    assert similitud(tema[0], tema[1], plantilla) > 0.5, "el tema debe sobrevivir al filtro"
    assert similitud(tema[0], otros[0], plantilla) < 0.3


# --- Sueños encadenados ---

async def _narrador_de_serie(instruccion, material):
    return ("SIGO: el muelle otra vez, ahora con luz." if "vuelve la imagen" in instruccion
            else "Un muelle hecho de partituras mojadas.")


def test_un_sueno_puede_retomar_la_imagen_de_anoche(motor):
    _memoria_variada(motor)
    ciclo = _ciclo(motor, narrator=_narrador_de_serie)
    primero = asyncio.run(ciclo.dream(chain=False))

    segundo = asyncio.run(ciclo.dream(chain=True))

    assert primero["encadenado"] is False
    assert segundo["encadenado"] is True and segundo["anterior"] == primero["id"]
    assert "SIGO" in segundo["contenido"]


def test_el_sueno_encadenado_sigue_sin_ser_un_recuerdo(motor):
    """Lo más delicado de la serie: encadenar no puede convertirlo en vivido."""
    _memoria_variada(motor)
    ciclo = _ciclo(motor, narrator=_narrador_de_serie)
    asyncio.run(ciclo.dream(chain=False))
    segundo = asyncio.run(ciclo.dream(chain=True))

    assert segundo["contenido"].startswith(MARCA_DE_SUENO)
    assert all(r["kind"] != "sueno" for r in motor.search("muelle partituras", limit=10))


def test_la_serie_se_puede_leer_como_hilo(motor):
    _memoria_variada(motor)
    ciclo = _ciclo(motor, narrator=_narrador_de_serie)
    primero = asyncio.run(ciclo.dream(chain=False))
    segundo = asyncio.run(ciclo.dream(chain=True))

    serie = ciclo.dream_series()

    assert [s["id"] for s in serie] == [segundo["id"], primero["id"]]
    assert serie[0]["sigue_a"] == primero["id"] and serie[1]["sigue_a"] is None


def test_un_sueno_demasiado_viejo_no_se_retoma(motor):
    _memoria_variada(motor)
    ciclo = _ciclo(motor, narrator=_narrador_de_serie, chain_max_age_hours=1.0)
    primero = asyncio.run(ciclo.dream(chain=False))
    _envejecer(motor, primero["id"], 3)

    segundo = asyncio.run(ciclo.dream(chain=True))

    assert segundo["encadenado"] is False, "anoche dejó de ser anoche"
