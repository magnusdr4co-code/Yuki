"""
Pruebas del guardado de estado durable.

Siete sitios escribían su JSON a mano con el mismo par de líneas. Lo que
protegen esas líneas no es cosmético, y por eso ahora viven en un solo módulo y
tienen pruebas propias:

**La escritura es atómica.** Un `write_text` directo sobre el fichero bueno deja
medio JSON si el proceso muere a la mitad, y el proceso muere a la mitad justo
cuando se está desplegando.

**Un estado ilegible no revienta la instancia.** Un disco a medio corromper es
cuando más falta hace que Yuki arranque: perder el diario de agencia cuesta lo
aprendido, que no arranque cuesta la instancia entera.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core import estado_json  # noqa: E402


def _vacio():
    return {"cosas": [], "cuenta": 0}


def test_lo_escrito_se_lee(tmp_path):
    ruta = tmp_path / "estado.json"
    estado_json.escribir(ruta, {"cosas": ["una"], "cuenta": 1})

    assert estado_json.leer(ruta, _vacio) == {"cosas": ["una"], "cuenta": 1}


def test_sin_fichero_devuelve_el_esquema_vacio(tmp_path):
    assert estado_json.leer(tmp_path / "no_existe.json", _vacio) == _vacio()


def test_un_fichero_corrupto_no_tumba_la_instancia(tmp_path):
    """Perder el diario cuesta lo aprendido; no arrancar cuesta la instancia."""
    ruta = tmp_path / "roto.json"
    ruta.write_text("{esto no es json", encoding="utf-8")

    assert estado_json.leer(ruta, _vacio) == _vacio()


def test_un_esquema_de_otra_epoca_tampoco(tmp_path):
    """
    JSON válido con la forma equivocada revienta más adelante y lejos de aquí,
    que es la peor manera de fallar. Se detecta al leer.
    """
    ruta = tmp_path / "viejo.json"
    ruta.write_text(json.dumps({"otra_cosa": 1}), encoding="utf-8")

    leido = estado_json.leer(ruta, _vacio, valido=lambda d: isinstance(d.get("cosas"), list))

    assert leido == _vacio()


def test_una_lista_json_no_pasa_por_diccionario(tmp_path):
    ruta = tmp_path / "lista.json"
    ruta.write_text("[1, 2, 3]", encoding="utf-8")

    assert estado_json.leer(ruta, _vacio) == _vacio()


def test_el_esquema_vacio_no_se_comparte_entre_lectores(tmp_path):
    """
    Por eso `por_defecto` es una función y no un diccionario: devolver siempre el
    mismo objeto haría que dos lectores compartieran las listas por dentro, y el
    primero que añadiera algo se lo encontraría el otro.
    """
    uno = estado_json.leer(tmp_path / "a.json", _vacio)
    otro = estado_json.leer(tmp_path / "b.json", _vacio)

    uno["cosas"].append("mía")

    assert otro["cosas"] == []


def test_no_queda_ningun_temporal_tras_escribir(tmp_path):
    ruta = tmp_path / "estado.json"
    estado_json.escribir(ruta, {"cosas": [], "cuenta": 3})

    assert [p.name for p in tmp_path.iterdir()] == ["estado.json"]


def test_una_escritura_a_medias_no_pisa_lo_que_habia(tmp_path, monkeypatch):
    """
    La propiedad que justifica el temporal.

    Si el proceso muere entre escribir y renombrar, lo que hay en disco sigue
    siendo el contenido anterior **entero**, no la mitad del nuevo.
    """
    ruta = tmp_path / "estado.json"
    estado_json.escribir(ruta, {"cosas": ["lo bueno"], "cuenta": 1})

    def morir(*args, **kwargs):
        raise OSError("el proceso muere justo aquí")

    monkeypatch.setattr(os, "replace", morir)
    try:
        estado_json.escribir(ruta, {"cosas": ["lo nuevo"], "cuenta": 2})
    except OSError:
        pass

    assert estado_json.leer(ruta, _vacio) == {"cosas": ["lo bueno"], "cuenta": 1}


def test_crea_el_directorio_si_no_existe(tmp_path):
    ruta = tmp_path / "aun" / "sin" / "crear" / "estado.json"

    estado_json.escribir(ruta, _vacio())

    assert ruta.is_file()
