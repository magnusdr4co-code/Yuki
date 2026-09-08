"""
Pruebas de los signos vitales.

Lo que se comprueba aquí no es que el módulo lea ficheros: es que sepa
**distinguir cuatro silencios que se parecen mucho** y significan cosas
distintas. Un proceso caído, una instancia nueva, una instancia frenada a
propósito y una Yuki catatónica producen todos el mismo panel en blanco, y
confundirlos es la diferencia entre una llamada a las tres de la mañana y
dejar de mirar la pantalla para siempre.
"""

import json
import os
import sqlite3
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.pulse import (  # noqa: E402
    ALETARGADA, AUSENTE, CATATONICA, FRENADA, RECIEN_NACIDA, VIVA,
    VOLITIVO, Pulse, Signo,
)

HORA = 3600.0


def _instancia(tmp_path, *, latido=0.0, actos=None, albedrio=None, sueno=None,
               recuerdos=0, con_bitacora=True):
    """Fabrica el estado durable de una instancia con la edad que se le pida."""
    datos = tmp_path / "data"
    datos.mkdir(exist_ok=True)
    ahora = time.time()

    vital = {"energy": 0.6, "last_updated": ahora - latido}
    if sueno is not None:
        vital["last_sleep_cycle"] = ahora - sueno
    (datos / "vital_state.json").write_text(json.dumps(vital), encoding="utf-8")

    ledger = {"acciones": {}, "franjas": {}, "dias": {}, "pendientes": [],
              "boredom": 0.0, "recientes": []}
    if albedrio is not None:
        ledger["recientes"] = [{"tool": "write", "at": ahora - albedrio}]
    (datos / "agency_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    if con_bitacora and actos is not None:
        from src.core.blackbox import BlackBox

        caja = BlackBox(path=str(datos / "bitacora.jsonl"))
        caja.record("acto_propio", {})
        # La bitácora sella la hora al escribir: para envejecerla hay que
        # reescribir la marca, que es justamente lo que el precinto detectaría.
        lineas = []
        for linea in caja.path.read_text(encoding="utf-8").splitlines():
            entrada = json.loads(linea)
            entrada["at"] = ahora - actos
            lineas.append(json.dumps(entrada, ensure_ascii=False, sort_keys=True))
        caja.path.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    base = datos / "yuki_memory.db"
    with sqlite3.connect(base) as conexion:
        conexion.execute("CREATE TABLE IF NOT EXISTS memories "
                         "(id INTEGER PRIMARY KEY, category TEXT, created_at REAL)")
        for _ in range(recuerdos):
            conexion.execute("INSERT INTO memories (category, created_at) VALUES (?, ?)",
                             ("conversation", ahora - 60))
    return datos


@pytest.fixture(autouse=True)
def sin_bitacora_real(monkeypatch, tmp_path):
    """Ninguna prueba escribe en la cadena de actos de la instancia real."""
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(tmp_path / "data" / "bitacora.jsonl"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "yuki_memory.db"))


def _pulso(datos):
    return Pulse({}, data_dir=str(datos)).read()


def test_todo_al_dia_es_estar_viva(tmp_path):
    datos = _instancia(tmp_path, latido=60, actos=HORA, albedrio=2 * HORA,
                       sueno=8 * HORA, recuerdos=5)

    lectura = _pulso(datos)

    assert lectura.estado == VIVA
    assert lectura.sana and lectura.gravedad == 0


def test_sin_latido_la_instancia_esta_ausente(tmp_path):
    """El proceso no escribe: da igual lo bien que estuviera todo lo demás."""
    datos = _instancia(tmp_path, latido=48 * HORA, actos=HORA, albedrio=HORA,
                       sueno=HORA, recuerdos=5)

    lectura = _pulso(datos)

    assert lectura.estado == AUSENTE
    assert lectura.gravedad == 3
    assert "no está escribiendo" in lectura.motivo


def test_el_proceso_respira_y_ella_no_hace_nada_es_catatonia(tmp_path):
    """
    El fallo que `/health` nunca ve.

    Latido fresco, memoria llena, conversaciones recientes —el contenedor está
    perfecto— y ni un solo acto propio en días. Una sonda de infraestructura
    daría verde.
    """
    datos = _instancia(tmp_path, latido=60, actos=5 * 24 * HORA,
                       albedrio=5 * 24 * HORA, sueno=5 * 24 * HORA, recuerdos=200)

    lectura = _pulso(datos)

    assert lectura.estado == CATATONICA
    assert not lectura.sana and lectura.gravedad == 2
    assert lectura.signo("latido").fresco
    assert lectura.signo("conversacion").fresco
    assert not any(s.fresco for s in lectura.de_tipo(VOLITIVO))


def test_una_instancia_nueva_no_esta_catatonica_solo_es_nueva(tmp_path):
    datos = _instancia(tmp_path, latido=30, recuerdos=0)

    lectura = _pulso(datos)

    assert lectura.estado == RECIEN_NACIDA
    assert lectura.sana


def test_el_freno_puesto_explica_el_silencio_y_se_dice_en_voz_alta(tmp_path, monkeypatch):
    """
    Frenada no es catatónica: es alguien que apretó el freno, quizá y lo olvidó.

    Confundirlos manda a operaciones a buscar una avería que no existe.
    """
    monkeypatch.setenv("YUKI_FRENO", "todo")
    datos = _instancia(tmp_path, latido=60, actos=5 * 24 * HORA,
                       albedrio=5 * 24 * HORA, sueno=5 * 24 * HORA, recuerdos=200)

    lectura = _pulso(datos)

    assert lectura.estado == FRENADA
    assert lectura.sana, "el freno es una decisión, no una avería"
    assert "freno" in lectura.motivo


def test_un_freno_que_no_impide_la_iniciativa_no_justifica_el_silencio(tmp_path, monkeypatch):
    """Frenar la publicación no explica que no piense: eso sigue siendo catatonia."""
    monkeypatch.setenv("YUKI_FRENO", "publicacion")
    datos = _instancia(tmp_path, latido=60, actos=5 * 24 * HORA,
                       albedrio=5 * 24 * HORA, sueno=5 * 24 * HORA, recuerdos=200)

    assert _pulso(datos).estado == CATATONICA


def test_algunos_signos_apagados_es_letargo_y_dice_cuales(tmp_path):
    datos = _instancia(tmp_path, latido=60, actos=HORA, albedrio=5 * 24 * HORA,
                       sueno=5 * 24 * HORA, recuerdos=50)

    lectura = _pulso(datos)

    assert lectura.estado == ALETARGADA
    assert "albedrio" in lectura.motivo and "sueno" in lectura.motivo
    assert lectura.sana


def test_que_nadie_le_hable_no_la_diagnostica(tmp_path):
    """
    El signo relacional no decide.

    Que no la busquen no es un fallo suyo; y su silencio propio tampoco queda
    justificado porque no la busquen. Por eso `conversacion` informa y no vota.
    """
    datos = _instancia(tmp_path, latido=60, actos=HORA, albedrio=HORA,
                       sueno=2 * HORA, recuerdos=1)
    with sqlite3.connect(datos / "yuki_memory.db") as conexion:
        conexion.execute("UPDATE memories SET created_at = ?", (time.time() - 90 * 24 * HORA,))

    lectura = _pulso(datos)

    assert lectura.estado == VIVA
    assert not lectura.signo("conversacion").fresco


def test_el_estado_ilegible_no_revienta_la_sonda(tmp_path):
    """
    Un disco a medio corromper es cuando más falta hace el diagnóstico.

    Una sonda que lanza excepción justo entonces es peor que no tenerla.
    """
    datos = _instancia(tmp_path, latido=60, actos=HORA, albedrio=HORA, recuerdos=5)
    (datos / "vital_state.json").write_text("{esto no es json", encoding="utf-8")
    (datos / "agency_ledger.json").write_text("", encoding="utf-8")

    lectura = _pulso(datos)

    assert lectura.estado == AUSENTE
    assert lectura.to_dict()["signos"]


def test_un_reloj_que_salta_no_declara_fresco_lo_que_esta_parado(tmp_path):
    """Marca en el futuro: la edad se recorta a cero, nunca se vuelve negativa."""
    signo = Signo(id="x", tipo=VOLITIVO, descripcion="", ultimo=time.time() + 10 * HORA,
                  max_edad=HORA, fuente="")

    assert signo.edad == 0.0
    assert signo.fresco


def test_las_edades_maximas_se_pueden_ajustar_por_configuracion(tmp_path):
    datos = _instancia(tmp_path, latido=60, actos=40 * HORA, albedrio=40 * HORA,
                       sueno=40 * HORA, recuerdos=5)

    estricto = Pulse({"pulse": {"max_edad_horas": {"bitacora": 1, "albedrio": 1, "sueno": 1}}},
                     data_dir=str(datos)).read()
    laxo = Pulse({"pulse": {"max_edad_horas": {"bitacora": 100, "albedrio": 100, "sueno": 100}}},
                 data_dir=str(datos)).read()

    assert estricto.estado == CATATONICA
    assert laxo.estado == VIVA


def test_la_lectura_serializa_entera(tmp_path):
    datos = _instancia(tmp_path, latido=60, actos=HORA, albedrio=HORA, sueno=HORA,
                       recuerdos=3)

    salida = _pulso(datos).to_dict()

    assert set(salida) == {"estado", "motivo", "gravedad", "sana", "signos"}
    assert {s["id"] for s in salida["signos"]} == {
        "latido", "bitacora", "albedrio", "sueno", "conversacion"}
    assert json.dumps(salida)  # nada dentro es inserializable


def test_la_noche_deja_traza_al_correr(tmp_path):
    """
    `last_sleep_cycle` estuvo declarado y sin escritor desde el principio.

    Un signo vital que nadie sella no avisa de nada: alarma para siempre, y a la
    semana alguien lo silencia. Esta prueba existe para que no vuelva a quedarse
    huérfano.
    """
    from src.core.vital_state import VitalState

    estado = VitalState(state_path=str(tmp_path / "vital_state.json"))
    assert estado.last_sleep_cycle is None

    estado.mark_sleep_cycle("rem")

    guardado = json.loads((tmp_path / "vital_state.json").read_text(encoding="utf-8"))
    assert guardado["last_sleep_cycle"] and guardado["last_sleep_phase"] == "rem"
    signo = Pulse({}, data_dir=str(tmp_path)).read().signo("sueno")
    assert signo.fresco


def test_un_repositorio_recien_clonado_no_es_una_caida(tmp_path):
    """
    El fallo que casi se cuela: la CI corre sobre un checkout sin `data/`.

    Sin estado vital, sin bitácora y sin memoria, la lectura ingenua es
    «el proceso no escribe» — y habría teñido de rojo todas las ramas hasta que
    alguien quitara la comprobación. Nada de rastro no es una parada: es que
    aquí no ha corrido nunca.
    """
    vacio = tmp_path / "sin_nada"
    vacio.mkdir()

    lectura = Pulse({}, data_dir=str(vacio)).read()

    assert lectura.estado == RECIEN_NACIDA
    assert lectura.sana
    assert "nunca" in lectura.motivo


def test_con_historia_pero_sin_latido_sigue_siendo_una_caida(tmp_path):
    """La excepción anterior no puede tapar una parada de verdad."""
    datos = _instancia(tmp_path, latido=0, actos=2 * HORA, albedrio=2 * HORA,
                       recuerdos=50)
    (datos / "vital_state.json").unlink()

    lectura = Pulse({}, data_dir=str(datos)).read()

    assert lectura.estado == AUSENTE
    assert "no está escribiendo" in lectura.motivo


def test_leer_el_pulso_no_deja_conexiones_abiertas(tmp_path):
    """
    La sonda se lee en cada raspado de métricas.

    `with sqlite3.connect(...)` confirma la transacción pero **no cierra**: una
    conexión filtrada por raspado es un descriptor menos cada minuto en una
    máquina con 2 GB para todo. Se cuenta lo abierto antes y después.
    """
    import gc

    datos = _instancia(tmp_path, latido=60, actos=HORA, albedrio=HORA, sueno=HORA,
                       recuerdos=20)
    sonda = Pulse({}, data_dir=str(datos))
    sonda.read()
    gc.collect()

    abiertas = len([o for o in gc.get_objects() if isinstance(o, sqlite3.Connection)])
    for _ in range(15):
        sonda.read()

    # Sin `gc.collect()` a propósito: lo que se comprueba es que se cierren
    # solas, no que el recolector las barra después.
    despues = len([o for o in gc.get_objects() if isinstance(o, sqlite3.Connection)])
    assert despues <= abiertas, f"quedaron {despues - abiertas} conexión(es) por raspado"
