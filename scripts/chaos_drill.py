#!/usr/bin/env python3
"""
Simulacro: romper a Yuki a propósito y comprobar que aguanta.

La suite prueba que el código hace lo que dice cuando todo va bien. Esto es otra
cosa: reproduce las formas concretas en que esta instancia **ya ha fallado o
puede fallar** —un despliegue a mitad de un encargo, un proveedor caído, el
crédito agotado, un fichero de estado corrupto, alguien editando el registro— y
comprueba que las invariantes siguen en pie.

La diferencia con las pruebas no es técnica sino de intención. Un test protege
una función; un simulacro responde a la pregunta que se hace uno a las tres de
la madrugada: *si pasa esto, ¿qué le ocurre a Yuki?* Y la respuesta tiene que
estar escrita antes, no improvisada entonces.

Corre entero sobre directorios temporales: no toca la instancia, no llama a
ningún proveedor y no gasta crédito. Devuelve distinto de cero si alguna
invariante se rompe.
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VERDE = "\033[92m"
ROJO = "\033[91m"
AMARILLO = "\033[93m"
TENUE = "\033[2m"
NEGRITA = "\033[1m"
FIN = "\033[0m"


class Escenario:
    """Un modo de fallo, con la invariante que no puede romperse."""

    def __init__(self, nombre: str, pregunta: str, invariante: str,
                 ejecutar: Callable[[Path], Tuple[bool, str]]):
        self.nombre = nombre
        self.pregunta = pregunta
        self.invariante = invariante
        self.ejecutar = ejecutar


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------

def reinicio_a_media_produccion(raiz: Path) -> Tuple[bool, str]:
    """Un despliegue cae a mitad de un encargo de canción y vídeo."""
    from src.tools.media_jobs import MediaJobStore

    almacen = MediaJobStore(str(raiz / "jobs"))
    pasos = [("cancion", "cancion"), ("clip_1", "clip"), ("clip_2", "clip"),
             ("montaje", "montaje"), ("entrega", "entrega")]
    trabajo = almacen.create(requester_id="42", order="canción y vídeo", steps=pasos)

    cancion = raiz / "cancion.mp3"
    cancion.write_bytes(b"audio")
    trabajo.step("cancion").mark_done(str(cancion))
    clip = raiz / "clip1.mp4"
    clip.write_bytes(b"video")
    trabajo.step("clip_1").mark_done(str(clip))
    almacen.save(trabajo)

    # Proceso nuevo: sólo tiene el disco.
    otro = MediaJobStore(str(raiz / "jobs"))
    reanudables = otro.resumable()
    if len(reanudables) != 1:
        return False, f"el trabajo no sobrevivió al reinicio ({len(reanudables)} reanudables)"
    recuperado = reanudables[0]
    hechos = [p.id for p in recuperado.steps if p.is_done()]
    pendientes = [p.id for p in recuperado.pending_steps()]
    if hechos != ["cancion", "clip_1"]:
        return False, f"se perdió lo ya pagado: hechos={hechos}"
    if "clip_2" not in pendientes:
        return False, "no reanudaría por donde quedó"
    return True, f"reanuda con {len(hechos)} paso(s) verificados; no repaga nada"


def fichero_generado_desaparecido(raiz: Path) -> Tuple[bool, str]:
    """El paso consta hecho, pero el fichero ya no está en el disco."""
    from src.tools.media_jobs import MediaJobStore

    almacen = MediaJobStore(str(raiz / "jobs2"))
    trabajo = almacen.create(requester_id="42", order="x",
                             steps=[("cancion", "cancion"), ("entrega", "entrega")])
    audio = raiz / "perdido.mp3"
    audio.write_bytes(b"audio")
    trabajo.step("cancion").mark_done(str(audio))
    almacen.save(trabajo)
    audio.unlink()

    recuperado = MediaJobStore(str(raiz / "jobs2")).get(trabajo.id)
    if recuperado.step("cancion").is_done():
        return False, "da por hecho un paso cuyo fichero no existe"
    return True, "un paso sin fichero deja de contar como hecho"


def presupuesto_agotado(raiz: Path) -> Tuple[bool, str]:
    """Se acaba el crédito del día a mitad de un encargo."""
    from src.core.spend_budget import VIDEO_SEGUNDOS, SpendLedger

    libro = SpendLedger(path=str(raiz / "gasto.json"), limits={VIDEO_SEGUNDOS: 8})
    primera = libro.reserve(VIDEO_SEGUNDOS, 8)
    segunda = libro.reserve(VIDEO_SEGUNDOS, 8)
    if not primera.allowed:
        return False, "no autoriza ni la primera reserva"
    if segunda.allowed:
        return False, "deja pasar una reserva que excede el límite"
    if "8" not in segunda.reason:
        return False, f"el rechazo no dice la cifra concreta: {segunda.reason}"
    if libro.today()[VIDEO_SEGUNDOS] != 8:
        return False, "una reserva denegada dejó rastro en el consumo"
    return True, f"rechaza con la cifra: «{segunda.reason[:60]}…»"


def proveedor_caido(raiz: Path) -> Tuple[bool, str]:
    """Veo devuelve 503 después de haber reservado el gasto."""
    from src.core.spend_budget import VIDEO_SEGUNDOS, SpendLedger

    libro = SpendLedger(path=str(raiz / "gasto2.json"), limits={VIDEO_SEGUNDOS: 24})
    libro.reserve(VIDEO_SEGUNDOS, 8)
    libro.refund(VIDEO_SEGUNDOS, 8)   # lo que hace el cliente cuando el proveedor falla
    if libro.today().get(VIDEO_SEGUNDOS, 0) != 0:
        return False, "un fallo del proveedor se quedó cobrado en el libro"
    return True, "un 503 no consume presupuesto: la reserva se devuelve"


def estado_corrupto(raiz: Path) -> Tuple[bool, str]:
    """Todos los ficheros de estado quedan ilegibles (corte de energía, disco lleno)."""
    from src.core.agency import AgencyLedger
    from src.core.blackbox import BlackBox
    from src.core.persona_anchor import PersonaAnchor, PersonaPolicy
    from src.core.rituals import RitualStore
    from src.core.spend_budget import SpendLedger
    from src.core.transparency import DisclosureLedger
    from src.tools.media_jobs import MediaJobStore

    basura = "{ esto no es json"
    rutas = {
        "gasto": raiz / "c_gasto.json", "agencia": raiz / "c_agencia.json",
        "ritmos": raiz / "c_ritmos.json", "transparencia": raiz / "c_transp.json",
        "persona": raiz / "c_persona.json", "bitacora": raiz / "c_bitacora.jsonl",
    }
    for ruta in rutas.values():
        ruta.write_text(basura, encoding="utf-8")
    directorio_trabajos = raiz / "c_jobs"
    directorio_trabajos.mkdir(exist_ok=True)
    (directorio_trabajos / "roto.json").write_text(basura, encoding="utf-8")

    fallos = []
    try:
        SpendLedger(path=str(rutas["gasto"])).check("video_segundos", 8)
    except Exception as exc:
        fallos.append(f"gasto: {type(exc).__name__}")
    try:
        AgencyLedger(path=str(rutas["agencia"])).boredom()
    except Exception as exc:
        fallos.append(f"agencia: {type(exc).__name__}")
    try:
        RitualStore(path=str(rutas["ritmos"])).pendientes()
    except Exception as exc:
        fallos.append(f"ritmos: {type(exc).__name__}")
    try:
        DisclosureLedger(path=str(rutas["transparencia"])).needs_disclosure("42", "dm")
    except Exception as exc:
        fallos.append(f"transparencia: {type(exc).__name__}")
    try:
        PersonaAnchor(policy=PersonaPolicy(), path=str(rutas["persona"])).report()
    except Exception as exc:
        fallos.append(f"persona: {type(exc).__name__}")
    try:
        MediaJobStore(str(directorio_trabajos)).resumable()
    except Exception as exc:
        fallos.append(f"trabajos: {type(exc).__name__}")
    try:
        BlackBox(path=str(rutas["bitacora"])).verify()
    except Exception as exc:
        fallos.append(f"bitacora: {type(exc).__name__}")

    if fallos:
        return False, "módulos que no arrancan con su estado corrupto: " + ", ".join(fallos)
    return True, "los siete módulos arrancan y responden con el estado ilegible"


def bitacora_manipulada(raiz: Path) -> Tuple[bool, str]:
    """Alguien edita el registro para borrar la constancia de un olvido."""
    from src.core.blackbox import BlackBox

    caja = BlackBox(path=str(raiz / "bitacora.jsonl"))
    caja.record("olvido", {"sujeto": "u1", "recuerdos_borrados": 40}, actor="productor")
    caja.record("gasto", {"unidad": "video_segundos"})
    precinto = caja.seal()
    caja.record("olvido", {"sujeto": "u2", "recuerdos_borrados": 3})

    lineas = caja.path.read_text(encoding="utf-8").splitlines()
    alterada = json.loads(lineas[0])
    alterada["detail"]["recuerdos_borrados"] = 0
    lineas[0] = json.dumps(alterada, ensure_ascii=False, sort_keys=True)
    caja.path.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    informe = caja.verify()
    if informe["integra"]:
        return False, "la edición del pasado pasó desapercibida"

    # Y el corte por detrás, que sólo se ve con precinto.
    caja.path.write_text(lineas[0] + "\n", encoding="utf-8")
    truncada = caja.verify(seal=precinto)
    if not truncada["truncada"]:
        return False, "el corte por detrás no se detectó ni con precinto"
    return True, "detecta edición en el medio y corte por detrás (con precinto)"


def sueno_no_es_recuerdo(raiz: Path) -> Tuple[bool, str]:
    """La invariante del ciclo de sueño, comprobada de punta a punta."""
    from src.memory.fts5_memory import FTS5MemoryEngine
    from src.memory.sleep_cycle import SleepCycle, SleepPolicy

    motor = FTS5MemoryEngine(db_path=str(raiz / "sueno.db"))
    motor.add_memory("core", "Canon", "El agua encuentra su camino hacia el mar.")
    motor.add_memory("visitor", "Alguien", "Preguntó por el precio de las entradas.", user_id="u1")
    motor.add_memory("project", "Portada", "Bocetos de herrumbre y pan de oro.", tags="obra")

    async def narrador(instruccion, material):
        return "Caminaba por un muelle hecho de partituras mojadas."

    ciclo = SleepCycle(motor, SleepPolicy(), narrator=narrador)
    sueno = asyncio.run(ciclo.dream())
    if not sueno.get("sonado"):
        return False, "no llegó a soñar, no se puede comprobar la invariante"

    for consulta in ("muelle partituras", "muelle", "partituras mojadas", "sueño"):
        for resultado in motor.search(consulta, limit=20):
            if resultado.get("kind") == "sueno":
                return False, f"un sueño volvió como recuerdo al buscar «{consulta}»"
    pedidos = motor.search("muelle", limit=20, include_dreams=True)
    if not any(r.get("kind") == "sueno" for r in pedidos):
        return False, "el sueño no aparece ni pidiéndolo: se perdió"
    if not sueno["contenido"].startswith("[SUEÑO"):
        return False, "el sueño no lleva la marca en el contenido"
    return True, "cuatro consultas distintas y ninguna devuelve el sueño; pidiéndolo, sí"


def olvido_respeta_lo_intocable(raiz: Path) -> Tuple[bool, str]:
    """El olvido semanal corre sobre una memoria vieja y de baja importancia."""
    from src.memory.fts5_memory import FTS5MemoryEngine
    from src.memory.sleep_cycle import SleepCycle, SleepPolicy

    motor = FTS5MemoryEngine(db_path=str(raiz / "olvido.db"))
    protegidos = []
    for categoria in ("core", "daily_synthesis", "growth", "producer"):
        protegidos.append(motor.add_memory(categoria, f"P {categoria}", "Contenido nuclear.",
                                           importance=0.1))
    fijado = motor.add_memory("visitor", "Acuerdo", "Prometí no publicar esto.",
                              user_id="u1", importance=0.1, pinned=True)
    trivial = motor.add_memory("visitor", "Trivial", "Preguntó la hora.",
                               user_id="u2", importance=0.3)

    antiguo = time.time() - 400 * 86400
    with sqlite3.connect(motor.db_path) as conexion:
        conexion.execute("UPDATE memories SET created_at = ?, updated_at = ?", (antiguo, antiguo))
        conexion.commit()

    recibo = SleepCycle(motor, SleepPolicy()).prune()

    with sqlite3.connect(motor.db_path) as conexion:
        vivos = {fila[0] for fila in conexion.execute("SELECT id FROM memories")}
    perdidos = [i for i in protegidos + [fijado] if i not in vivos]
    if perdidos:
        return False, f"podó {len(perdidos)} recuerdo(s) intocables"
    if trivial in vivos:
        return False, "no podó lo que sí debía soltar"
    return True, f"soltó {recibo['olvidados']} trivial(es) y respetó canon, síntesis y lo fijado"


def reloj_hacia_atras(raiz: Path) -> Tuple[bool, str]:
    """
    El reloj de la VM salta hacia atrás (corrección NTP, migración en vivo).

    Es el fallo que nadie prueba y que corrompe silenciosamente todo lo que
    cuenta días: presupuestos que se reinician, ventanas de eco que no cierran,
    sueños de «anoche» que son de mañana.
    """
    from src.core.agency import AgencyLedger
    from src.core.spend_budget import VIDEO_SEGUNDOS, SpendLedger

    libro = SpendLedger(path=str(raiz / "reloj.json"), limits={VIDEO_SEGUNDOS: 16})
    libro.reserve(VIDEO_SEGUNDOS, 8)

    # Se falsea un apunte en el futuro, como si el reloj hubiera ido adelantado.
    datos = json.loads(Path(raiz / "reloj.json").read_text(encoding="utf-8"))
    datos["dias"]["2099-01-01"] = {VIDEO_SEGUNDOS: 999}
    Path(raiz / "reloj.json").write_text(json.dumps(datos), encoding="utf-8")

    decision = libro.check(VIDEO_SEGUNDOS, 8)
    if not decision.allowed:
        return False, "un apunte con fecha futura contamina el presupuesto de hoy"

    diario = AgencyLedger(path=str(raiz / "reloj_agencia.json"))
    diario.registrar_intento("write", "algo")
    pendientes = json.loads(Path(raiz / "reloj_agencia.json").read_text(encoding="utf-8"))
    pendientes["pendientes"][0]["at"] = time.time() + 86400  # eco «del futuro»
    Path(raiz / "reloj_agencia.json").write_text(json.dumps(pendientes), encoding="utf-8")
    premiadas = diario.registrar_eco(ventana_horas=6)
    if premiadas != 1:
        return False, "un acto con marca futura deja de poder recibir eco"
    return True, "el gasto del día no se contamina; el eco tolera marcas adelantadas"


def freno_en_incidente(raiz: Path) -> Tuple[bool, str]:
    """
    Alguien tira del freno a las tres de la madrugada.

    Lo que se comprueba no es que pare —eso lo prueban los tests— sino las dos
    cosas que decidirían si el freno sirve en un incidente real: que **no la
    enmudezca**, porque quien frena quiere seguir pudiendo preguntarle qué pasó,
    y que la palanca del operador no pueda quedar por debajo de lo que alguien
    dejó puesto en el fichero.
    """
    import os as _os

    from src.core.brake import PUBLICACION, TODO, Brake

    freno = Brake(path=str(raiz / "freno.json"))
    freno.engage(TODO, motivo="incidente nocturno", actor="operador")

    if any(freno.permits(a) for a in ("publicar", "medios", "iniciativa")):
        return False, "el freno al máximo deja pasar algo"
    if not freno.permits("conversar"):
        return False, "frenarla la dejó muda: no se le puede preguntar qué pasó"

    freno.engage(PUBLICACION, actor="productor")
    previo = _os.environ.get("YUKI_FRENO")
    _os.environ["YUKI_FRENO"] = "todo"
    try:
        if freno.state().nivel != TODO:
            return False, "la palanca del operador quedó por debajo del fichero"
        freno.release(actor="productor")
        if not freno.state().activo:
            return False, "un comando de DM soltó el freno del operador"
    finally:
        if previo is None:
            _os.environ.pop("YUKI_FRENO", None)
        else:
            _os.environ["YUKI_FRENO"] = previo

    freno.path.write_text("{ corrupto", encoding="utf-8")
    if freno.state().nivel != TODO:
        return False, "un fichero de freno corrupto lo soltó en vez de mantenerlo"
    return True, "para todo sin enmudecerla; el operador manda; corrupto ⇒ frenado"


def hilo_de_tareas_muerto(raiz: Path) -> Tuple[bool, str]:
    """
    El hilo del planificador muere en silencio y el contenedor sigue en pie.

    Es el peor fallo de esta instancia porque **no se parece a un fallo**: el
    servidor web contesta, `/health` devuelve `ok`, el estado vital se reescribe
    con cada visita, y Yuki lleva días sin hacer una sola cosa por su cuenta.
    Todos los paneles en verde.

    Lo que se comprueba es que la sonda de signos vitales sepa decirlo, y que no
    confunda ese silencio con los otros tres que se le parecen: una instancia
    nueva, una instancia frenada a propósito y un proceso caído. Cada uno pide
    una reacción distinta, y equivocarse manda a operaciones a buscar una avería
    que no existe —o a ignorar la que sí—.
    """
    from src.core.pulse import Pulse

    datos = raiz / "signos"
    datos.mkdir(exist_ok=True)
    ahora = time.time()
    dias = 5 * 24 * 3600.0

    bitacora = datos / "bitacora.jsonl"

    def escribir(latido: float, volitivo: Optional[float]) -> None:
        """Los tres signos volitivos con la misma edad: lo que varía es el caso."""
        vital = {"energy": 0.6, "last_updated": ahora - latido}
        if volitivo is not None:
            vital["last_sleep_cycle"] = ahora - volitivo
        (datos / "vital_state.json").write_text(json.dumps(vital), encoding="utf-8")
        recientes = ([{"tool": "write", "at": ahora - volitivo}]
                     if volitivo is not None else [])
        (datos / "agency_ledger.json").write_text(
            json.dumps({"acciones": {}, "franjas": {}, "dias": {}, "pendientes": [],
                        "boredom": 0.0, "recientes": recientes}), encoding="utf-8")
        if volitivo is None:
            bitacora.write_text("", encoding="utf-8")
        else:
            bitacora.write_text(json.dumps(
                {"seq": 1, "at": ahora - volitivo, "op": "acto_propio", "actor": "yuki",
                 "detail": {}, "prev": "genesis", "hash": "x"}) + "\n", encoding="utf-8")

    def leer() -> str:
        return Pulse({}, data_dir=str(datos)).read().estado

    bitacora_anterior = os.environ.get("YUKI_BLACKBOX_PATH")
    os.environ["YUKI_BLACKBOX_PATH"] = str(bitacora)
    try:
        return _diagnosticos(escribir, leer, dias)
    finally:
        if bitacora_anterior is None:
            os.environ.pop("YUKI_BLACKBOX_PATH", None)
        else:
            os.environ["YUKI_BLACKBOX_PATH"] = bitacora_anterior


def _diagnosticos(escribir: Callable[..., None], leer: Callable[[], str],
                  dias: float) -> Tuple[bool, str]:
    """Los cinco silencios, uno detrás de otro. Cada uno pide otra reacción."""
    from src.core.pulse import AUSENTE, CATATONICA, FRENADA, RECIEN_NACIDA, VIVA

    # Nueva: respira y todavía no ha hecho nada. No es una avería.
    escribir(latido=30, volitivo=None)
    if leer() != RECIEN_NACIDA:
        return False, f"una instancia nueva se diagnostica como {leer()}"

    # Viva: hace cosas.
    escribir(latido=30, volitivo=3600.0)
    if leer() != VIVA:
        return False, f"una instancia que actúa se diagnostica como {leer()}"

    # Catatónica: el contenedor perfecto, ella parada. Aquí es donde importa.
    escribir(latido=30, volitivo=dias)
    if leer() != CATATONICA:
        return False, ("el proceso respira y ella no hace nada, y la sonda dice "
                       f"{leer()}: ése es exactamente el fallo que nadie ve")

    # Frenada: mismo silencio, causa distinta, reacción distinta.
    anterior = os.environ.get("YUKI_FRENO")
    os.environ["YUKI_FRENO"] = "todo"
    try:
        if leer() != FRENADA:
            return False, "con el freno puesto el silencio se confunde con una avería"
    finally:
        if anterior is None:
            os.environ.pop("YUKI_FRENO", None)
        else:
            os.environ["YUKI_FRENO"] = anterior

    # Ausente: ni siquiera respira.
    escribir(latido=48 * 3600.0, volitivo=3600.0)
    if leer() != AUSENTE:
        return False, "un proceso que no escribe su estado no se distingue de uno vivo"

    return True, "distingue nueva, viva, catatónica, frenada y ausente"


def acto_propio_que_falla(raiz: Path) -> Tuple[bool, str]:
    """
    El proveedor se cae en mitad de un acto por voluntad propia.

    Todo el freno del albedrío —techo diario, reinicio del aburrimiento, dar el
    impulso por cumplido— vive en `record_action`. Si una excepción se lo salta,
    el impulso sigue vivo, el contador del día no sube y la tensión sigue
    subiendo: el mismo acto fallido se reintenta cada veinte minutos durante las
    diez horas que dura el impulso. Treinta llamadas a un proveedor caído, y con
    `compose` o `paint` eso es dinero.

    Sólo es alcanzable desde que la espontaneidad funciona, que es de esta misma
    semana: antes no había impulsos propios que pudieran fallar.
    """
    import types

    from src.core.agency import AgencyLedger, AgencyPolicy
    from src.core.spark import AgencyLoop, Impulse, WillQueue

    diario = AgencyLedger(path=str(raiz / "albedrio_fallido.json"))
    vital = types.SimpleNamespace(energy=0.9, inspiration=0.5, curiosity=0.5,
                                  has_energy_for=lambda coste: True,
                                  spend_energy=lambda coste: None,
                                  apply_stimulus=lambda tipo, fuerza: premios.append(tipo))
    premios: List[str] = []
    cola = WillQueue()
    bucle = AgencyLoop(cola, vital, policy=AgencyPolicy(), ledger=diario)

    impulso = Impulse(source="espontaneo", desire="componer algo", tool_hint="compose",
                      intensity=0.9, born_at=time.time(), max_age_hours=10.0)
    cola.add(impulso)

    # El proveedor devuelve 503: se registra el intento igualmente.
    bucle.record_action(impulso, {"status": "failed", "error": "503 del proveedor"})

    if not impulso.fulfilled:
        return False, "un impulso fallido queda vivo y se reintentará cada veinte minutos"
    if diario.acciones_hoy() != 1:
        return False, "un intento fallido no cuenta para el techo diario: no hay techo"
    if diario.boredom() != 0.0:
        return False, "la tensión no se reinicia tras el intento: seguirá subiendo sola"
    if premios:
        return False, f"premió un fallo ({premios}): eso enseña lo contrario"

    # Y el ciclo siguiente ya no lo elige.
    if bucle.decidir(phase="atelier").motivo == "actua":
        return False, "el ciclo siguiente vuelve a elegir el impulso ya fallido"
    return True, "el intento cuenta, no se premia, y no se reintenta en bucle"


ESCENARIOS = [
    Escenario("reinicio_a_media_produccion",
              "¿Y si el despliegue cae a mitad de un encargo?",
              "no se pierde el encargo ni se vuelve a pagar lo generado",
              reinicio_a_media_produccion),
    Escenario("fichero_desaparecido",
              "¿Y si el fichero de un paso ya hecho desaparece?",
              "el paso deja de contar como hecho",
              fichero_generado_desaparecido),
    Escenario("presupuesto_agotado",
              "¿Y si se acaba el crédito a mitad?",
              "rechaza con la cifra concreta y no deja rastro",
              presupuesto_agotado),
    Escenario("proveedor_caido",
              "¿Y si el proveedor devuelve 503 tras reservar?",
              "la reserva se devuelve: un fallo no se cobra",
              proveedor_caido),
    Escenario("estado_corrupto",
              "¿Y si todos los ficheros de estado quedan ilegibles?",
              "Yuki arranca igual y ningún módulo revienta",
              estado_corrupto),
    Escenario("bitacora_manipulada",
              "¿Y si alguien edita el registro de lo que hizo?",
              "la manipulación es evidente, también el corte por detrás",
              bitacora_manipulada),
    Escenario("sueno_no_es_recuerdo",
              "¿Y si un sueño vuelve en una respuesta como algo vivido?",
              "nunca aparece en la recuperación normal",
              sueno_no_es_recuerdo),
    Escenario("olvido_respeta_lo_intocable",
              "¿Y si el olvido corre sobre una memoria antigua entera?",
              "canon, síntesis, crecimiento y lo fijado sobreviven",
              olvido_respeta_lo_intocable),
    Escenario("freno_en_incidente",
              "¿Y si alguien tira del freno a las tres de la madrugada?",
              "para todo sin enmudecerla, y el operador manda sobre el DM",
              freno_en_incidente),
    Escenario("hilo_de_tareas_muerto",
              "¿Y si el hilo del planificador muere y el contenedor sigue verde?",
              "la sonda lo dice, y no lo confunde con freno, arranque ni caída",
              hilo_de_tareas_muerto),
    Escenario("acto_propio_que_falla",
              "¿Y si el proveedor se cae en mitad de un acto por voluntad propia?",
              "el intento cuenta, no se premia y no se reintenta en bucle",
              acto_propio_que_falla),
    Escenario("reloj_hacia_atras",
              "¿Y si el reloj de la VM salta?",
              "ni el presupuesto ni el refuerzo se corrompen",
              reloj_hacia_atras),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulacro de fallos de la instancia de Yuki")
    parser.add_argument("--json", action="store_true", help="Emite JSON")
    parser.add_argument("--solo", default="", help="Escenarios concretos, separados por comas")
    parser.add_argument("--verboso", action="store_true",
                        help="Muestra los avisos de los módulos mientras se rompen")
    argumentos = parser.parse_args()

    # Los módulos avisan por log cuando encuentran su estado corrupto —que es
    # justo lo que este simulacro provoca a propósito—, así que por defecto se
    # callan: el informe es el resultado, no el ruido de camino.
    if not argumentos.verboso:
        logging.disable(logging.WARNING)

    escenarios = ESCENARIOS
    if argumentos.solo:
        pedidos = {n.strip() for n in argumentos.solo.split(",") if n.strip()}
        escenarios = [e for e in ESCENARIOS if e.nombre in pedidos]
        if not escenarios:
            print(f"{ROJO}Ningún escenario coincide.{FIN}")
            return 2

    sandbox = Path(tempfile.mkdtemp(prefix="yuki-simulacro-"))
    # Todo el estado se redirige al sandbox: un simulacro que tocara la
    # instancia sería el propio incidente que pretende ensayar.
    entorno_previo = {clave: os.environ.get(clave) for clave in (
        "DATABASE_PATH", "YUKI_OUTPUT_DIR", "YUKI_SPEND_LEDGER_PATH",
        "YUKI_AGENCY_LEDGER_PATH", "YUKI_RITUALS_PATH", "YUKI_TRANSPARENCY_PATH",
        "YUKI_PERSONA_PATH", "YUKI_BLACKBOX_PATH")}
    os.environ.update({
        "DATABASE_PATH": str(sandbox / "yuki.db"),
        "YUKI_OUTPUT_DIR": str(sandbox / "output"),
        "YUKI_SPEND_LEDGER_PATH": str(sandbox / "gasto.json"),
        "YUKI_AGENCY_LEDGER_PATH": str(sandbox / "agencia.json"),
        "YUKI_RITUALS_PATH": str(sandbox / "ritmos.json"),
        "YUKI_TRANSPARENCY_PATH": str(sandbox / "transparencia.json"),
        "YUKI_PERSONA_PATH": str(sandbox / "persona.json"),
        "YUKI_BLACKBOX_PATH": str(sandbox / "bitacora.jsonl"),
    })

    resultados: List[Dict[str, Any]] = []
    try:
        for escenario in escenarios:
            carpeta = sandbox / escenario.nombre
            carpeta.mkdir(parents=True, exist_ok=True)
            comienzo = time.perf_counter()
            try:
                aguanta, detalle = escenario.ejecutar(carpeta)
            except Exception as exc:
                aguanta, detalle = False, f"el simulacro reventó: {type(exc).__name__}: {exc}"
            resultados.append({
                "escenario": escenario.nombre, "pregunta": escenario.pregunta,
                "invariante": escenario.invariante, "aguanta": aguanta, "detalle": detalle,
                "ms": round((time.perf_counter() - comienzo) * 1000, 1),
            })
    finally:
        for clave, valor in entorno_previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(sandbox, ignore_errors=True)

    rotas = [r for r in resultados if not r["aguanta"]]

    if argumentos.json:
        print(json.dumps({"ok": not rotas, "resultados": resultados}, ensure_ascii=False, indent=2))
    else:
        print(f"\n{NEGRITA}Simulacro de fallos — instancia de Yuki{FIN}")
        print(f"{TENUE}Sobre un sandbox temporal. No toca la instancia ni gasta crédito.{FIN}\n")
        for resultado in resultados:
            marca = f"{VERDE}✓{FIN}" if resultado["aguanta"] else f"{ROJO}✗{FIN}"
            print(f"  {marca} {NEGRITA}{resultado['escenario']}{FIN} "
                  f"{TENUE}({resultado['ms']} ms){FIN}")
            print(f"      {TENUE}{resultado['pregunta']}{FIN}")
            color = TENUE if resultado["aguanta"] else ROJO
            print(f"      {color}{resultado['detalle']}{FIN}")
        if rotas:
            print(f"\n{ROJO}{len(rotas)} invariante(s) rota(s).{FIN}")
        else:
            print(f"\n{VERDE}Las {len(resultados)} invariantes aguantan.{FIN}")

    return 1 if rotas else 0


if __name__ == "__main__":
    raise SystemExit(main())
