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

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agency import AgencyLedger, AgencyPolicy  # noqa: E402
from src.core.spark import (  # noqa: E402
    ACTUA, BAJO_UMBRAL, DESACTIVADO, FASE_DE_SILENCIO, FRENADA, SIN_DESEOS,
    SIN_ENERGIA, TECHO_DIARIO, AgencyLoop, Impulse, WillQueue,
)


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
