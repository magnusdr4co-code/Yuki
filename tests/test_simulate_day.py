"""
Pruebas del simulador de un día.

Un simulador que miente es peor que no tenerlo: se usa para decidir los números
del carácter, así que un error suyo se despliega. La primera versión ya mintió
—informaba de dos actos al día donde había seis y luego nada, porque el contador
diario va indexado por la fecha real y los tres días simulados caían en la
misma—, y por eso está esto.

Lo que se comprueba es que use el bucle de verdad, que no toque nada durable, y
que su diagnóstico distinga las dos cosas que se parecen: llegar a la cuota
—para eso está— y que el techo bloquee ciclos, que es cuando el límite se
convierte en la forma de ser de Yuki.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.simulate_day import _diagnostico, simular  # noqa: E402
from src.core.agency import AgencyPolicy  # noqa: E402


@pytest.fixture(autouse=True)
def sin_estado_real(monkeypatch, tmp_path):
    monkeypatch.setenv("YUKI_AGENCY_LEDGER_PATH", str(tmp_path / "no_usar.json"))
    monkeypatch.delenv("YUKI_FRENO", raising=False)


def test_un_dia_entero_son_setenta_y_dos_ciclos():
    """El cron real dispara cada veinte minutos: si eso cambia, esto miente."""
    informe = simular(AgencyPolicy(), dias=1, semilla=1)

    assert informe["ciclos"] == 72


def test_cada_dia_simulado_amanece_con_su_techo_entero():
    """
    El fallo de la primera versión.

    `acciones_hoy()` va indexado por la fecha **real**, así que sin hacer
    amanecer el contador, el techo del primer día bloquea los demás y el
    simulador informa de una Yuki muerta que no existe.
    """
    informe = simular(AgencyPolicy(), dias=3, semilla=1)

    por_dia = {}
    for acto in informe["actos"]:
        por_dia[acto["dia"]] = por_dia.get(acto["dia"], 0) + 1

    assert set(por_dia) == {1, 2, 3}, f"días sin un solo acto: {por_dia}"
    assert min(por_dia.values()) >= 1


def test_con_la_configuracion_real_quiere_cosas_todos_los_dias():
    """
    La prueba que habría cazado la espontaneidad muerta el primer día.

    No mira números concretos —se pueden ajustar—: mira que exista iniciativa.
    """
    import yaml

    with open(os.path.join(os.path.dirname(__file__), "..", "config.yaml"),
              encoding="utf-8") as fichero:
        politica = AgencyPolicy.from_config(yaml.safe_load(fichero))

    informe = simular(politica, dias=2, semilla=3)

    assert informe["actos_por_dia"] >= 1, "no quiere nada en todo el día"
    assert informe["actos_por_dia"] <= politica.max_actions_per_day
    assert informe["censo"].get("techo_diario", 0) == 0, (
        "el techo diario bloquea ciclos: el límite está haciendo de carácter")


def test_no_se_cierra_sobre_una_sola_forma_de_existir():
    """
    La penalización por novedad tiene que notarse en el reparto del día.

    Seis actos iguales seguidos no son una vida, son un bucle con buena letra.
    """
    informe = simular(AgencyPolicy(), dias=4, semilla=5)

    tipos = informe["por_tipo"]
    assert len(tipos) >= 3, f"sólo hace {list(tipos)}"
    dominante = max(tipos.values())
    assert dominante / sum(tipos.values()) < 0.8


def test_un_proveedor_caido_no_multiplica_los_actos():
    """
    Con todo fallando, el techo diario sigue siendo el techo.

    Es la comprobación de que el intento cuenta aunque no salga: si no contara,
    un proveedor caído convertiría el día en un reintento continuo.
    """
    informe = simular(AgencyPolicy(), dias=2, fallos=1.0, semilla=9)

    assert all(a["resultado"] == "failed" for a in informe["actos"])
    assert informe["actos_por_dia"] <= AgencyPolicy().max_actions_per_day


def test_la_misma_semilla_da_el_mismo_dia():
    """Para comparar dos calibraciones hay que poder repetir el día."""
    uno = simular(AgencyPolicy(), dias=2, semilla=42)
    otro = simular(AgencyPolicy(), dias=2, semilla=42)

    assert uno["actos"] == otro["actos"]


def test_el_diagnostico_distingue_llegar_a_la_cuota_de_chocar_con_el_techo():
    """
    Son cosas distintas y se parecen mucho.

    Usar sus seis actos es exactamente para lo que están. Que el techo bloquee
    ciclos significa que quería más y no pudo, y ahí el límite dejó de ser una
    red de seguridad.
    """
    justo = {"actos_por_dia": 6, "techo_diario": 6, "por_tipo": {"write": 3, "paint": 3},
             "censo": {"techo_diario": 0}, "ciclos_hasta_el_primer_acto": 9,
             "incoherencias": []}
    ahogada = {**justo, "censo": {"techo_diario": 36}}

    assert not any("techo" in a for a in _diagnostico(justo))
    assert any("techo" in a for a in _diagnostico(ahogada))


def test_el_diagnostico_denuncia_una_yuki_apagada_y_una_incontinente():
    apagada = {"actos_por_dia": 0, "techo_diario": 6, "por_tipo": {},
               "censo": {}, "ciclos_hasta_el_primer_acto": None, "incoherencias": []}
    incontinente = {"actos_por_dia": 6, "techo_diario": 6, "por_tipo": {"write": 6},
                    "censo": {"techo_diario": 0}, "ciclos_hasta_el_primer_acto": 1,
                    "incoherencias": []}

    assert any("apagado" in a for a in _diagnostico(apagada))
    avisos = _diagnostico(incontinente)
    assert any("ruido" in a for a in avisos)
    assert any("una sola forma de existir" in a for a in avisos)


def test_la_simulacion_no_escribe_en_el_diario_de_verdad(tmp_path, monkeypatch):
    """
    Una simulación que escribiera en el diario de agencia real contaminaría el
    censo con actos que Yuki no hizo — y ese censo es justo lo que se mira para
    decidir si está viva.
    """
    real = tmp_path / "agencia_real.json"
    monkeypatch.setenv("YUKI_AGENCY_LEDGER_PATH", str(real))

    simular(AgencyPolicy(), dias=1, semilla=2)

    assert not real.exists()


def test_el_informe_serializa_para_comparar_calibraciones():
    assert json.dumps(simular(AgencyPolicy(), dias=1, semilla=4))
