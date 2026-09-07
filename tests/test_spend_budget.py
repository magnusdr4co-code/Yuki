"""
Pruebas del presupuesto de gasto.

Lo que se protege: que la comprobación ocurra **antes** de llamar al proveedor
—después el segundo de vídeo ya está facturado—, que el rechazo lleve la cifra
concreta y que un fallo del proveedor no se cobre en el libro.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.spend_budget import (  # noqa: E402
    IMAGENES, MUSICA_PISTAS, MUSICA_SEGUNDOS, TOKENS_ENTRADA, TOKENS_SALIDA,
    VIDEO_SEGUNDOS, VOZ_CARACTERES, SpendLedger, coste_estimado,
)


@pytest.fixture
def libro(tmp_path):
    return SpendLedger(path=str(tmp_path / "ledger.json"),
                       limits={VIDEO_SEGUNDOS: 24, IMAGENES: 2})


def test_autoriza_mientras_quede_presupuesto(libro):
    assert libro.check(VIDEO_SEGUNDOS, 8).allowed
    libro.record(VIDEO_SEGUNDOS, 8)
    assert libro.check(VIDEO_SEGUNDOS, 16).allowed


def test_rechaza_con_la_cifra_concreta(libro):
    libro.record(VIDEO_SEGUNDOS, 24)

    decision = libro.check(VIDEO_SEGUNDOS, 8)

    assert not decision.allowed
    assert not decision          # __bool__ para usarlo como guarda
    assert "24" in decision.reason and "8" in decision.reason
    assert decision.used == 24 and decision.limit == 24


def test_la_operacion_que_desbordaria_se_rechaza_entera(libro):
    """No se autoriza a medias: 20 + 8 pasa de 24, así que no se llama al proveedor."""
    libro.record(VIDEO_SEGUNDOS, 20)

    assert not libro.check(VIDEO_SEGUNDOS, 8).allowed
    assert libro.check(VIDEO_SEGUNDOS, 4).allowed


def test_unidad_sin_limite_declarado_no_bloquea(libro):
    assert libro.check(VOZ_CARACTERES, 100_000).allowed


def test_presupuesto_deshabilitado_autoriza_todo(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"), limits={VIDEO_SEGUNDOS: 1}, enabled=False)
    assert libro.check(VIDEO_SEGUNDOS, 999).allowed


def test_techo_en_dolares_suma_las_unidades_cotizadas(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"), limits={}, usd_per_day=1.0)
    libro.record(VIDEO_SEGUNDOS, 8)      # 0,80 USD

    assert libro.usd_today() == pytest.approx(0.80)
    assert not libro.check(VIDEO_SEGUNDOS, 8).allowed
    assert libro.check(IMAGENES, 1).allowed   # 0,04 USD: cabe


def test_la_musica_no_se_cotiza_pero_se_cuenta(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"), limits={MUSICA_PISTAS: 2})
    libro.record(MUSICA_PISTAS, 1)
    libro.record(MUSICA_SEGUNDOS, 90)

    assert coste_estimado(MUSICA_PISTAS, 1) == 0.0
    assert libro.usd_today() == 0.0
    assert libro.today()[MUSICA_SEGUNDOS] == 90
    assert "no cotizada" in libro.describe()


def test_el_apunte_sobrevive_a_un_proceso_nuevo(tmp_path):
    ruta = str(tmp_path / "l.json")
    SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 24}).record(VIDEO_SEGUNDOS, 16)

    otro = SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 24})

    assert otro.today()[VIDEO_SEGUNDOS] == 16
    assert not otro.check(VIDEO_SEGUNDOS, 16).allowed


def test_dos_procesos_suman_en_vez_de_pisarse(tmp_path):
    """El daemon y el Salón comparten disco: cada apunte relee antes de sumar."""
    ruta = str(tmp_path / "l.json")
    daemon = SpendLedger(path=ruta)
    salon = SpendLedger(path=ruta)

    daemon.record(IMAGENES, 1)
    salon.record(IMAGENES, 1)

    assert SpendLedger(path=ruta).today()[IMAGENES] == 2


def test_libro_corrupto_no_impide_arrancar(tmp_path):
    ruta = tmp_path / "l.json"
    ruta.write_text("{ roto", encoding="utf-8")
    libro = SpendLedger(path=str(ruta), limits={VIDEO_SEGUNDOS: 24})

    assert libro.today() == {}
    assert libro.check(VIDEO_SEGUNDOS, 8).allowed


def test_escritura_atomica(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"))
    for _ in range(3):
        libro.record(IMAGENES, 1)

    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads((tmp_path / "l.json").read_text(encoding="utf-8"))["dias"]


def test_tokens_de_texto_se_anotan_por_separado(tmp_path):
    libro = SpendLedger(path=str(tmp_path / "l.json"))
    libro.record_llm(1000, 500)

    consumo = libro.today()
    assert consumo[TOKENS_ENTRADA] == 1000 and consumo[TOKENS_SALIDA] == 500
    assert libro.usd_today() == pytest.approx(1000 / 1e6 * 0.75 + 500 / 1e6 * 3.75)


def test_from_config_lee_limites_y_zona_horaria():
    libro = SpendLedger.from_config({
        "budget": {"enabled": True, "daily_limits": {VIDEO_SEGUNDOS: 64}, "usd_per_day": 5},
        "scheduler": {"timezone": "Europe/Madrid"},
    })

    assert libro.limits[VIDEO_SEGUNDOS] == 64
    assert libro.usd_per_day == 5
    assert libro.timezone_name == "Europe/Madrid"


def test_sin_seccion_budget_hay_limites_por_defecto():
    libro = SpendLedger.from_config({})

    assert libro.enabled
    assert libro.limits[VIDEO_SEGUNDOS] > 0


# --- Reserva atómica ---

def test_reservar_comprueba_y_anota_en_el_mismo_tramo(libro):
    """Comprobar y anotar por separado deja en medio toda la llamada al proveedor."""
    primera = libro.reserve(VIDEO_SEGUNDOS, 24)
    segunda = libro.reserve(VIDEO_SEGUNDOS, 8)

    assert primera.allowed and not segunda.allowed
    assert libro.today()[VIDEO_SEGUNDOS] == 24, "sólo se anota lo autorizado"


def test_una_reserva_denegada_no_anota_nada(libro):
    libro.reserve(VIDEO_SEGUNDOS, 24)
    antes = libro.today()[VIDEO_SEGUNDOS]

    libro.reserve(VIDEO_SEGUNDOS, 8)

    assert libro.today()[VIDEO_SEGUNDOS] == antes


def test_la_devolucion_restituye_lo_no_gastado(libro):
    libro.reserve(VIDEO_SEGUNDOS, 16)
    libro.refund(VIDEO_SEGUNDOS, 16)

    assert libro.today()[VIDEO_SEGUNDOS] == 0
    assert libro.check(VIDEO_SEGUNDOS, 24).allowed


def test_una_devolucion_no_deja_el_consumo_en_negativo(libro):
    libro.reserve(VIDEO_SEGUNDOS, 8)
    libro.refund(VIDEO_SEGUNDOS, 24)

    assert libro.today()[VIDEO_SEGUNDOS] == 0


def test_dos_procesos_no_se_cuelan_por_el_hueco_de_la_llamada(tmp_path):
    """El daemon y el Salón reservan contra el mismo fichero, con flock."""
    ruta = str(tmp_path / "l.json")
    daemon = SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 8})
    salon = SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 8})

    assert daemon.reserve(VIDEO_SEGUNDOS, 8).allowed
    assert not salon.reserve(VIDEO_SEGUNDOS, 8).allowed
    assert SpendLedger(path=ruta).today()[VIDEO_SEGUNDOS] == 8


def test_reservas_concurrentes_no_superan_el_limite(tmp_path):
    """Ocho hilos pidiendo a la vez: el límite manda, no el orden de llegada."""
    import threading

    ruta = str(tmp_path / "l.json")
    autorizadas = []
    barrera = threading.Barrier(8)

    def pedir():
        libro = SpendLedger(path=ruta, limits={VIDEO_SEGUNDOS: 24})
        barrera.wait()
        if libro.reserve(VIDEO_SEGUNDOS, 8).allowed:
            autorizadas.append(1)

    hilos = [threading.Thread(target=pedir) for _ in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(autorizadas) == 3, "24 segundos dan para exactamente tres clips de 8"
    assert SpendLedger(path=ruta).today()[VIDEO_SEGUNDOS] == 24
