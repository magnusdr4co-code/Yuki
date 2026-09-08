"""
Pruebas de la bitácora encadenada.

Lo que se protege no es que se escriba —eso lo hace cualquier log— sino que
**mentir sobre el pasado deje marca**. Un diario que se puede reescribir sin
rastro no es un diario, es un borrador; las tres formas de romperlo tienen que
detectarse, y el contenido de lo registrado no puede quedarse dentro.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.blackbox import GENESIS, BlackBox, Entrada  # noqa: E402


@pytest.fixture
def bitacora(tmp_path):
    return BlackBox(path=str(tmp_path / "bitacora.jsonl"))


def _reescribir(bitacora, indice, mutacion):
    lineas = bitacora.path.read_text(encoding="utf-8").splitlines()
    datos = json.loads(lineas[indice])
    mutacion(datos)
    lineas[indice] = json.dumps(datos, ensure_ascii=False, sort_keys=True)
    bitacora.path.write_text("\n".join(lineas) + "\n", encoding="utf-8")


# --- Cadena sana ---

def test_una_bitacora_vacia_es_integra(bitacora):
    informe = bitacora.verify()

    assert informe["integra"] and informe["entradas"] == 0
    assert bitacora.head() == GENESIS


def test_cada_anotacion_engancha_con_la_anterior(bitacora):
    primera = bitacora.record("olvido", {"sujeto": "u1"}, actor="productor")
    segunda = bitacora.record("gasto", {"unidad": "video_segundos"})

    assert primera.prev == GENESIS
    assert segunda.prev == primera.hash
    assert bitacora.verify()["integra"]
    assert bitacora.head() == segunda.hash


def test_la_numeracion_es_continua(bitacora):
    for indice in range(5):
        bitacora.record("acto", {"n": indice})

    assert [e.seq for e in bitacora.entries()] == [1, 2, 3, 4, 5]


# --- Las tres formas de romperla ---

def test_editar_una_anotacion_del_pasado_se_ve(bitacora):
    bitacora.record("olvido", {"sujeto": "u1", "recuerdos_borrados": 2})
    bitacora.record("olvido", {"sujeto": "u2", "recuerdos_borrados": 3})
    bitacora.record("gasto", {"unidad": "imagenes"})

    _reescribir(bitacora, 1, lambda datos: datos["detail"].update({"recuerdos_borrados": 0}))

    informe = bitacora.verify()
    assert not informe["integra"]
    assert informe["problemas"][0]["fallo"] == "contenido alterado"
    assert informe["problemas"][0]["seq"] == 2


def test_quitar_una_anotacion_del_medio_se_ve(bitacora):
    bitacora.record("uno", {})
    bitacora.record("dos", {})
    bitacora.record("tres", {})
    lineas = bitacora.path.read_text(encoding="utf-8").splitlines()
    bitacora.path.write_text(lineas[0] + "\n" + lineas[2] + "\n", encoding="utf-8")

    informe = bitacora.verify()

    assert not informe["integra"]
    assert any(p["fallo"] == "cadena rota" for p in informe["problemas"])
    assert any(p["fallo"] == "salto de numeración" for p in informe["problemas"])


def test_cortar_por_detras_solo_se_ve_con_precinto(bitacora):
    """
    Una cadena truncada sigue siendo internamente coherente.

    Por eso el precinto sale de la instancia con la copia diaria: dentro no
    prueba nada, porque quien corta la cadena también podría corregir el
    precinto guardado a su lado.
    """
    for indice in range(4):
        bitacora.record("acto", {"n": indice})
    precinto = bitacora.seal()

    lineas = bitacora.path.read_text(encoding="utf-8").splitlines()
    bitacora.path.write_text("\n".join(lineas[:2]) + "\n", encoding="utf-8")

    sin_precinto = bitacora.verify()
    con_precinto = bitacora.verify(seal=precinto)

    assert sin_precinto["integra"], "por dentro, una cadena cortada parece sana"
    assert not con_precinto["integra"] and con_precinto["truncada"]
    assert any("cortó por detrás" in p["detalle"] for p in con_precinto["problemas"])


def test_una_linea_ilegible_se_denuncia(bitacora):
    bitacora.record("acto", {})
    with open(bitacora.path, "a", encoding="utf-8") as fichero:
        fichero.write("esto no es json\n")

    informe = bitacora.verify()

    assert not informe["integra"]
    assert any(p["fallo"] == "líneas ilegibles" for p in informe["problemas"])


def test_un_precinto_que_sigue_en_la_cadena_no_alarma(bitacora):
    bitacora.record("acto", {"n": 1})
    precinto = bitacora.seal()
    bitacora.record("acto", {"n": 2})

    assert bitacora.verify(seal=precinto)["integra"]


# --- Lo que no puede guardar ---

def test_el_contenido_nunca_entra_en_la_bitacora(bitacora):
    """
    Una bitácora inmutable con contenido dentro sería lo contrario de un olvido:
    borrar un recuerdo y dejar su texto en el registro que prueba que se borró.
    """
    bitacora.record("olvido", {"sujeto": "u1", "content": "el secreto que pidió borrar",
                               "mensaje": "otra cosa privada"})

    crudo = bitacora.path.read_text(encoding="utf-8")

    assert "el secreto que pidió borrar" not in crudo
    assert "otra cosa privada" not in crudo
    assert "omitido" in crudo
    assert "u1" in crudo, "el hecho sí se registra"


def test_los_valores_largos_se_recortan(bitacora):
    bitacora.record("acto", {"motivo": "x" * 5000})

    entrada = bitacora.entries()[-1]

    assert len(entrada.detail["motivo"]) <= 300


# --- Robustez ---

def test_perder_la_bitacora_no_tumba_a_yuki(tmp_path, monkeypatch):
    """Escribir el registro nunca puede ser lo que impida ejecutar un acto."""
    caja = BlackBox(path=str(tmp_path / "sub" / "bitacora.jsonl"))

    def fallar(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("builtins.open", fallar)
    entrada = caja.record("acto", {"n": 1})

    assert entrada.hash, "la entrada se calcula aunque no se pueda escribir"


def test_el_registro_de_estado_alimenta_la_cadena(tmp_path, monkeypatch):
    from src.core.state_registry import StateRegistry

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "yuki.db"))
    caja = BlackBox(path=str(tmp_path / "bitacora.jsonl"))
    registro = StateRegistry(db_path=str(tmp_path / "yuki.db"),
                             audit_path=str(tmp_path / "auditoria.log"), blackbox=caja)

    registro.record("prueba", {"sujeto": "u1", "actor": "productor"})

    entradas = caja.entries()
    assert entradas and entradas[-1].op == "prueba" and entradas[-1].actor == "productor"
    assert caja.verify()["integra"]


def test_la_serializacion_es_canonica_y_estable():
    """El orden de las claves no puede cambiar el hash: la firma sería inútil."""
    una = Entrada(seq=1, at=1.5, op="x", actor="y", detail={"b": 2, "a": 1}, prev=GENESIS, hash="")
    otra = Entrada(seq=1, at=1.5, op="x", actor="y", detail={"a": 1, "b": 2}, prev=GENESIS, hash="")

    assert una.calcular_hash() == otra.calcular_hash()
