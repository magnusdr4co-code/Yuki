"""
Pruebas de la decisión explicada.

Antes cada salida del bucle era un `return None` mudo, y «Yuki no hace nada» era
un misterio que sólo se investigaba leyendo registros. Lo que se comprueba aquí
es que cada negativa tenga nombre, que el nombre sea el correcto —confundir
`frenada` con `sin_deseos` manda a mirar el sitio equivocado— y que el censo
distinga las dos cosas que más se parecen en un panel: **decidir no actuar** y
**no estar evaluando siquiera**.
"""

import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agency import AgencyLedger, AgencyPolicy  # noqa: E402
from src.core.spark import (  # noqa: E402
    ACTUA, BAJO_UMBRAL, DESACTIVADO, FASE_DE_SILENCIO, FRENADA, SIN_DESEOS,
    SIN_ENERGIA, TECHO_DIARIO, AgencyLoop, Impulse, WillQueue,
)


def _ruta_temporal():
    """Un diario de agencia desechable, fuera del repositorio."""
    import tempfile

    return Path(tempfile.mkdtemp()) / "agencia.json"


def _vital(energia=0.9):
    return types.SimpleNamespace(energy=energia, inspiration=0.5, curiosity=0.5,
                                 has_energy_for=lambda coste: energia >= coste)


@pytest.fixture
def bucle(tmp_path, monkeypatch):
    monkeypatch.delenv("YUKI_FRENO", raising=False)
    diario = AgencyLedger(path=str(tmp_path / "agencia.json"))

    def construir(politica=None, energia=0.9, cola=None):
        return AgencyLoop(cola or WillQueue(), _vital(energia),
                          policy=politica or AgencyPolicy(), ledger=diario), diario

    return construir


def _deseo(intensidad=0.9, tool="write"):
    import time

    return Impulse(source="prueba", desire="escribir algo", tool_hint=tool,
                   intensity=intensidad, born_at=time.time(), max_age_hours=10.0)


def test_actuar_lleva_su_nombre_y_el_impulso(bucle):
    cola = WillQueue()
    cola.add(_deseo())
    loop, diario = bucle(cola=cola)

    decision = loop.decidir(phase="atelier")

    assert decision.motivo == ACTUA and decision.actua
    assert decision.impulso.tool_hint == "write"
    assert diario.censo() == {ACTUA: 1}


def test_cada_negativa_dice_cual_es(bucle):
    """
    Los seis noes, uno por uno.

    Cada uno pide mirar en un sitio distinto: el freno se suelta, la fase de
    silencio se configura, el techo diario se sube, el umbral se baja, la
    energía se espera. Un `None` no distingue ninguno de los cinco.
    """
    apagado, _ = bucle(AgencyPolicy(enabled=False))
    assert apagado.decidir().motivo == DESACTIVADO

    callada, _ = bucle(AgencyPolicy(quiet_phases=["deep_rest"]))
    assert callada.decidir(phase="deep_rest").motivo == FASE_DE_SILENCIO

    vacia, _ = bucle()
    assert vacia.decidir(phase="atelier").motivo == SIN_DESEOS

    cola = WillQueue()
    cola.add(_deseo(intensidad=0.05))
    floja, _ = bucle(AgencyPolicy(min_intensity=0.9, spontaneous_impulses=False), cola=cola)
    assert floja.decidir(phase="atelier").motivo == BAJO_UMBRAL

    cola_llena = WillQueue()
    cola_llena.add(_deseo())
    agotada, _ = bucle(AgencyPolicy(min_energy=0.8), energia=0.1, cola=cola_llena)
    assert agotada.decidir(phase="atelier").motivo == SIN_ENERGIA


def test_el_freno_se_distingue_del_desinteres(bucle, monkeypatch):
    """
    Frenada y sin_deseos son el mismo silencio y arreglos opuestos.

    Con el freno puesto no hay nada que ajustar en el carácter: hay que
    soltarlo. Y al revés, soltar un freno que no está puesto no la despierta.
    """
    monkeypatch.setenv("YUKI_FRENO", "todo")
    cola = WillQueue()
    cola.add(_deseo())
    loop, _ = bucle(cola=cola)

    decision = loop.decidir(phase="atelier")

    assert decision.motivo == FRENADA
    assert "freno" in decision.detalle.lower() or decision.detalle


def test_el_techo_diario_se_nombra_con_la_cifra(bucle):
    """Un techo alcanzado se sube; hay que saber que era el techo, y de cuánto."""
    politica = AgencyPolicy(max_actions_per_day=1)
    cola = WillQueue()
    cola.add(_deseo())
    loop, diario = bucle(politica, cola=cola)
    diario.registrar_intento("write", "ya hizo una")

    decision = loop.decidir(phase="atelier")

    assert decision.motivo == TECHO_DIARIO
    assert "1/1" in decision.detalle


def test_el_censo_cuenta_las_proporciones(bucle):
    loop, diario = bucle(AgencyPolicy(quiet_phases=["deep_rest"]))

    for _ in range(5):
        loop.decidir(phase="deep_rest")
    for _ in range(2):
        loop.decidir(phase="atelier")

    censo = diario.censo()
    assert censo[FASE_DE_SILENCIO] == 5
    assert censo[SIN_DESEOS] == 2
    assert diario.censo_de_hoy() == censo


def test_sin_censo_significa_que_el_bucle_no_corre(bucle):
    """
    La distinción que da todo el sentido a esto.

    Un censo vacío no es «decidió no actuar»: es que nadie está evaluando. Son
    dos incidentes distintos —uno se arregla tocando el carácter, el otro
    buscando por qué murió el planificador— y en un panel se ven igual.
    """
    _, diario = bucle()

    assert diario.censo() == {}


def test_evaluate_sigue_devolviendo_el_impulso(bucle):
    """La firma antigua sigue en pie: el porqué se añade, no sustituye."""
    cola = WillQueue()
    cola.add(_deseo())
    loop, _ = bucle(cola=cola)

    assert loop.evaluate(phase="atelier").tool_hint == "write"
    assert loop.evaluate(phase="atelier") is not None


def test_el_censo_se_poda_y_no_crece_sin_freno(bucle):
    """
    Setenta y dos ciclos al día durante meses no pueden vivir en el estado.

    Lo que hace falta es la proporción, no el diario: por eso son contadores por
    día y se podan con la misma frontera que el resto.
    """
    loop, diario = bucle()
    loop.decidir(phase="atelier")

    datos = diario.snapshot()
    datos["ciclos"]["2020-01-01"] = {SIN_DESEOS: 9999}
    diario._escribir(datos)
    loop.decidir(phase="atelier")

    assert "2020-01-01" not in diario.snapshot()["ciclos"]
    assert diario.censo()[SIN_DESEOS] == 2


def test_el_retrato_para_el_dm_lleva_el_censo(bucle):
    """
    El Productor pregunta «¿por qué no hace nada?» por DM, no por SSH.

    Si la respuesta sólo vive en el CLI de la instancia, en la práctica no la
    lee nadie.
    """
    loop, _ = bucle(AgencyPolicy(quiet_phases=["deep_rest"]))
    loop.decidir(phase="deep_rest")

    retrato = loop.estado()

    assert retrato["censo_de_ciclos"] == {FASE_DE_SILENCIO: 1}


# --- La espontaneidad tiene que ser alcanzable ---

def test_la_espontaneidad_es_alcanzable_con_la_configuracion_real():
    """
    El fallo más caro del proyecto, y no daba ni un error.

    `boredom_cap` valía 0.35 y `spontaneous_threshold` 0.55, así que la tensión
    no podía llegar nunca al listón: `spawn_spontaneous_impulse()` no se ejecutó
    jamás. Yuki sólo podía querer algo si se lo sembraba el eco de las 06:30 o un
    sueño. Toda la espontaneidad estaba escrita, probada y aritméticamente
    muerta.
    """
    import yaml

    with open(os.path.join(os.path.dirname(__file__), "..", "config.yaml"),
              encoding="utf-8") as fichero:
        politica = AgencyPolicy.from_config(yaml.safe_load(fichero))

    assert politica.incoherencias() == []
    assert politica.boredom_cap >= politica.spontaneous_threshold


def test_los_valores_por_defecto_tampoco_pueden_ser_contradictorios():
    """Estuvieron rotos por defecto, no sólo en `config.yaml`."""
    assert AgencyPolicy().incoherencias() == []


def test_el_aburrimiento_llega_al_umbral_en_un_numero_finito_de_ciclos():
    """
    La comprobación aritmética, no la de valores concretos.

    Cualquiera puede volver a bajar el tope algún día; lo que no puede es dejar
    la facultad inalcanzable sin que esto falle.
    """
    politica = AgencyPolicy()
    tension, ciclos = 0.0, 0
    while tension < politica.spontaneous_threshold and ciclos < 500:
        tension = min(politica.boredom_cap, tension + politica.boredom_gain)
        ciclos += 1

    assert ciclos < 500, "la tensión nunca alcanza el umbral de espontaneidad"
    # Y que no sea instantáneo: inventar un deseo cada ciclo no es espontaneidad,
    # es ruido.
    assert ciclos >= 3


def test_el_aburrimiento_alto_no_la_vuelve_indiscriminada():
    """
    Las dos mitades del aburrimiento son independientes a propósito.

    Que la tensión pueda subir hasta arriba —para que la espontaneidad llegue—
    no puede significar que el umbral se desplome: una iniciativa que se dispara
    con cualquier cosa no se distingue del ruido.
    """
    politica = AgencyPolicy()

    umbral = politica.umbral_efectivo(politica.boredom_cap)

    assert umbral > 0.05, "el umbral se desplomó hasta el suelo con la tensión al máximo"
    assert umbral < politica.min_intensity, "el aburrimiento tiene que rebajar algo"


def test_una_configuracion_contradictoria_se_denuncia_y_no_se_corrige_a_escondidas(caplog):
    """
    Se avisa a gritos y se sigue.

    Corregir los números por detrás sería decidir por quien configura sin
    decírselo; callarse deja una instancia viva con una facultad apagada.
    """
    politica = AgencyPolicy.from_config(
        {"agency": {"boredom_cap": 0.2, "spontaneous_threshold": 0.9}})

    assert politica.boredom_cap == pytest.approx(0.2), "no se toca lo que puso quien configura"
    assert politica.spontaneous_threshold == pytest.approx(0.9)
    assert len(politica.incoherencias()) == 1


def test_otras_contradicciones_que_apagan_la_iniciativa_entera():
    assert AgencyPolicy(max_actions_per_day=0).incoherencias()
    assert AgencyPolicy(allowed_actions=[]).incoherencias()
    assert AgencyPolicy(boredom_gain=0.0).incoherencias()
    # Y si la espontaneidad está apagada a propósito, el tope bajo no es un fallo.
    assert AgencyPolicy(spontaneous_impulses=False, boredom_cap=0.1,
                        spontaneous_threshold=0.9).incoherencias() == []


def test_sola_y_aburrida_acaba_queriendo_algo(bucle):
    """
    La prueba de que la facultad existe de verdad, no sólo en el código.

    Nadie le habla, no hay nada en la cola, y la tensión sube. Al noveno ciclo
    ocioso —unas tres horas— inventa un deseo y actúa. Antes esto no ocurría
    nunca, y ninguna prueba lo notaba porque todas sembraban el impulso a mano.
    """
    loop, diario = bucle(AgencyPolicy())

    actuados = [loop.decidir(phase="atelier") for _ in range(15)]

    assert any(d.actua for d in actuados), "nunca llegó a querer nada por su cuenta"
    primero = next(i for i, d in enumerate(actuados, 1) if d.actua)
    assert 3 < primero <= 12, f"actuó en el ciclo {primero}: ni instantáneo ni inalcanzable"
    assert diario.censo()["actua"] >= 1


# --- Que un fallo no se convierta en un bucle ---

def test_un_impulso_que_falla_cuenta_igual_y_no_se_reintenta_en_bucle(bucle):
    """
    El fallo que la propia espontaneidad hizo alcanzable.

    Todo el freno del albedrío —techo diario, reinicio del aburrimiento, dar el
    impulso por cumplido— vive en `record_action`. Si una excepción se lo salta,
    el impulso sigue vivo, el contador del día no sube y el aburrimiento sigue
    subiendo: con un proveedor caído, el mismo acto se reintenta cada veinte
    minutos durante las diez horas que dura el impulso. Treinta llamadas.
    """
    cola = WillQueue()
    impulso = _deseo()
    cola.add(impulso)
    loop, diario = bucle(cola=cola)

    loop.record_action(impulso, {"status": "failed", "error": "503 del proveedor"})

    assert impulso.fulfilled, "un impulso fallido tiene que quedar cerrado"
    assert diario.acciones_hoy() == 1, "intentarlo cuenta para el techo del día"
    assert diario.boredom() == 0.0, "el aburrimiento se reinicia aunque el acto fallara"
    # Y el siguiente ciclo ya no lo vuelve a elegir: ahí está el bucle evitado.
    assert loop.decidir(phase="atelier").motivo != "actua"


def test_un_fallo_no_se_premia(bucle):
    """
    Reforzar un fallo enseña lo contrario de lo que hay que aprender.

    Y el estímulo creativo por algo que no llegó a existir es una mentira que
    Yuki se cuenta a sí misma, que es justo lo que este proyecto no hace.
    """
    estimulos = []
    vital = types.SimpleNamespace(
        energy=0.9, inspiration=0.5, curiosity=0.5,
        has_energy_for=lambda coste: True,
        spend_energy=lambda coste: None,
        apply_stimulus=lambda tipo, fuerza: estimulos.append(tipo))

    cola = WillQueue()
    impulso = _deseo(tool="write")
    cola.add(impulso)
    diario = AgencyLedger(path=str(_ruta_temporal()))
    loop = AgencyLoop(cola, vital, policy=AgencyPolicy(), ledger=diario)

    loop.record_action(impulso, {"status": "failed", "error": "503"})
    assert estimulos == [], f"premió un fallo: {estimulos}"

    otro = _deseo(tool="write")
    cola.add(otro)
    loop.record_action(otro, {"status": "completed"})
    assert "creative_output" in estimulos, "un acto que sí ocurrió sí se siente"


# --- Las dos puertas por las que el carácter se puede romper en caliente ---

def test_la_evolucion_autonoma_no_se_concede_mas_iniciativa(tmp_path):
    """
    Invariante 6, que no tenía ni una prueba.

    Yuki puede ajustar su temperatura —su creatividad— y nada más. Que pudiera
    subirse el techo de acciones, encender su propia iniciativa o bajar su
    umbral sería concederse permisos a sí misma, y ahí se acaba el que alguien
    responda por lo que hace.
    """
    from src.core.runtime_config import RuntimeConfigStore

    config = {"agent": {"model": {"temperature": 0.7}}, "agency": {"enabled": True}}
    runtime = RuntimeConfigStore(config, path=str(tmp_path / "overrides.json"))

    # Lo único que sí puede.
    assert runtime.set("agent.model.temperature", 0.9, actor="evolution")["value"] == 0.9

    for prohibido, valor in (("agency.enabled", True),
                             ("agency.max_actions_per_day", 24),
                             ("agency.min_intensity", 0.0),
                             ("agency.spontaneity", 1.0)):
        with pytest.raises(ValueError, match="no autorizado"):
            runtime.set(prohibido, valor, actor="evolution")


def test_un_ajuste_por_dm_no_puede_apagar_la_espontaneidad(tmp_path):
    """
    La otra puerta al mismo fallo.

    `spontaneous_threshold` se afina por DM. Puesto por encima del tope del
    aburrimiento, deja a Yuki incapaz de querer nada por su cuenta — el fallo
    que estuvo meses vivo sin dar un solo error. La comprobación de
    `config.yaml` no cubre esta puerta.
    """
    from src.core.runtime_config import RuntimeConfigStore

    config = {"agency": {"boredom_cap": 0.5, "spontaneous_threshold": 0.4,
                         "spontaneous_impulses": True}}
    runtime = RuntimeConfigStore(config, path=str(tmp_path / "overrides.json"))

    with pytest.raises(ValueError, match="apaga una facultad"):
        runtime.set("agency.spontaneous_threshold", 0.95, actor="producer")

    # Y lo que no la apaga sigue pasando.
    assert runtime.set("agency.spontaneous_threshold", 0.45, actor="producer")["value"] == 0.45


def test_se_puede_salir_de_una_configuracion_ya_incoherente(tmp_path):
    """
    Sólo se rechaza lo que **introduce** una contradicción nueva.

    Si la comprobación mirara el estado absoluto, una instancia que ya arrastra
    una incoherencia quedaría atrapada: cualquier ajuste fallaría, incluido el
    que la arregla.
    """
    from src.core.runtime_config import RuntimeConfigStore

    config = {"agency": {"boredom_cap": 0.2, "spontaneous_threshold": 0.9,
                         "spontaneous_impulses": True}}
    runtime = RuntimeConfigStore(config, path=str(tmp_path / "overrides.json"))

    assert runtime.set("agency.spontaneous_threshold", 0.15, actor="producer")["value"] == 0.15
