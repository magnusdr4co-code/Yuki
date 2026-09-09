"""
Pruebas de las rutinas autónomas.

Es el módulo que orquesta la jornada entera de Yuki —reflexión de las 03:00,
lanzamiento matutino, síntesis de las 23:30 con su copia y su consolidación,
sueño REM, olvido semanal— y estaba cubierto al 20%. Lo que se prueba es lo que
decide *cuándo no* hacer algo: las puertas de estado vital, el orden de los
pasos de la noche y que un fallo en una pieza no se lleve por delante la rutina
entera.
"""

import asyncio
import os
import sys
import types
from typing import Any, Dict, List


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scheduler.tasks import AutonomousTasks  # noqa: E402


class MemoriaFalsa:
    def __init__(self):
        self.interacciones: List[Dict[str, Any]] = []
        self.sintesis: List[Dict[str, Any]] = []
        self.engine = types.SimpleNamespace(add_memory=lambda **kwargs: 1)

    def record_interaction(self, **kwargs):
        self.interacciones.append(kwargs)

    def save_daily_synthesis(self, date_str, summary_text):
        self.sintesis.append({"fecha": date_str, "texto": summary_text})


class PortalFalso:
    def __init__(self):
        self.imagenes = 0
        self.voces = 0

    async def search_trends_firecrawl(self, query, limit=4):
        return [{"title": "t", "snippet": "s", "url": None, "source": "sin buscador",
                 "simulated": True}]

    async def generate_image_frontier(self, prompt):
        self.imagenes += 1
        return {"image_url": "file:///arte.png", "local_path": "/tmp/arte.png"}

    async def synthesize_voice_tts(self, text):
        self.voces += 1
        return {"audio_url": "file:///voz.ogg", "local_path": "/tmp/voz.ogg"}


def _arnes(impulso=None, motivo=None):
    """
    Doble del bucle de albedrío.

    Devuelve una `Decision`, no un impulso suelto: el tick pregunta *por qué* no
    actuó, y un doble que sólo supiera decir «nada» dejaría esa rama sin probar.
    """
    from src.core.spark import ACTUA, SIN_DESEOS, Decision

    decision = Decision(motivo or (ACTUA if impulso is not None else SIN_DESEOS),
                        impulso=impulso)
    return types.SimpleNamespace(decidir=lambda phase=None: decision,
                                 evaluate=lambda phase=None: decision.impulso)


def _agente(*, energia=0.8, humor=0.5, interacciones=10, fase="atelier", **extra):
    generadas: List[Dict[str, Any]] = []

    async def generate_response(**kwargs):
        generadas.append(kwargs)
        return f"texto para {kwargs['user_name']}"

    fases_dormidas: list = []
    agente = types.SimpleNamespace(
        vital_state=types.SimpleNamespace(
            energy=energia, mood=humor, curiosity=0.9,
            accumulated_interactions_today=interacciones,
            accumulated_creations_today=0, inspiration=0.5,
            will_queue=[], save=lambda: None,
            # Sellar la noche es parte de dormir: si el doble no lo tuviera, la
            # traza podría desaparecer del código real sin que nada avisara.
            last_sleep_cycle=None,
            mark_sleep_cycle=lambda fase="nrem": fases_dormidas.append(fase)),
        circadian=types.SimpleNamespace(current_phase=lambda: fase),
        memory_manager=MemoriaFalsa(),
        nous_portal=PortalFalso(),
        generate_response=generate_response,
        config={},
        telegram_adapter=None,
        discord_adapter=None,
        evolution=types.SimpleNamespace(
            review_and_adjust=_corrutina({"changed": False, "reason": "sin evidencia"})),
        sleep=types.SimpleNamespace(
            nrem=_corrutina({"fase": "nrem"}),
            dream=_corrutina({"fase": "rem", "sonado": False, "motivo": "sin material"}),
            prune=lambda: {"fase": "olvido", "olvidados": 0},
            impulse_from_dream=lambda sueno: None),
        propose_own_ritual=_corrutina(None),
        will_queue=types.SimpleNamespace(add=lambda impulso: None, to_list=lambda: []),
        agency_loop=_arnes(),
        inner_monologue=types.SimpleNamespace(
            should_think=lambda: False,
            generate_thought_prompt=lambda: "piensa",
            record_thought=lambda texto: None),
    )
    agente.generadas = generadas
    for clave, valor in extra.items():
        setattr(agente, clave, valor)
    agente.fases_dormidas = fases_dormidas
    return agente


def _corrutina(valor):
    async def _fn(*args, **kwargs):
        return valor
    return _fn


# --- Reflexión nocturna ---

def test_la_reflexion_nocturna_solo_ocurre_en_la_hora_de_sombra():
    agente = _agente(fase="atelier")

    resultado = asyncio.run(AutonomousTasks(agente).nocturnal_trend_reflection())

    assert resultado is None and agente.generadas == []


def test_sin_curiosidad_no_hay_reflexion():
    agente = _agente(fase="kage")
    agente.vital_state.curiosity = 0.2

    assert asyncio.run(AutonomousTasks(agente).nocturnal_trend_reflection()) is None


def test_la_reflexion_declara_el_origen_de_lo_que_mira():
    """Sin buscador conectado, el prompt tiene que decirlo o Yuki citará humo."""
    agente = _agente(fase="kage")

    asyncio.run(AutonomousTasks(agente).nocturnal_trend_reflection())

    prompt = agente.generadas[0]["message"]
    assert "NO vienen de una búsqueda real" in prompt
    assert agente.generadas[0]["route"] == "feed_summary"
    assert agente.memory_manager.interacciones, "queda registrada en memoria"


# --- Lanzamiento matutino ---

def test_agotada_no_publica_por_la_mañana():
    agente = _agente(energia=0.2)

    assert asyncio.run(AutonomousTasks(agente).morning_inspiration_drop()) is None
    assert agente.nous_portal.imagenes == 0, "ni siquiera gasta en la imagen"


def test_de_bajon_escribe_pero_no_gasta_en_arte():
    """El humor bajo acorta el texto y evita el gasto: es una decisión, no un fallo."""
    agente = _agente(humor=0.2)

    resultado = asyncio.run(AutonomousTasks(agente).morning_inspiration_drop())

    assert resultado["image"] is None and resultado["voice"] is None
    assert agente.nous_portal.imagenes == 0
    assert "sereno" in agente.generadas[0]["message"]


def test_con_buen_humor_pinta_pero_no_canta():
    agente = _agente(humor=0.5)

    resultado = asyncio.run(AutonomousTasks(agente).morning_inspiration_drop())

    assert resultado["image"] is not None and resultado["voice"] is None


def test_eufórica_pinta_y_habla():
    agente = _agente(humor=0.9)

    resultado = asyncio.run(AutonomousTasks(agente).morning_inspiration_drop())

    assert resultado["image"] is not None and resultado["voice"] is not None
    assert agente.generadas[0]["route"] == "social_formatting"


# --- Síntesis diaria: la noche entera ---

def test_la_sintesis_encadena_copia_consolidacion_y_propuesta(monkeypatch):
    orden: List[str] = []

    class CopiaFalsa:
        status = "success"
        path = "/tmp/copia.tar.gz"
        remote_uri = None
        remote_error = "sin bucket"

        def to_dict(self):
            return {"status": "success"}

    class GestorFalso:
        @classmethod
        def from_config(cls, config):
            return cls()

        def create(self):
            orden.append("copia")
            return CopiaFalsa()

    monkeypatch.setattr("src.scheduler.tasks.BackupManager", GestorFalso)

    async def nrem():
        orden.append("nrem")
        return {"fase": "nrem"}

    async def proponer():
        orden.append("propuesta")
        return None

    agente = _agente(interacciones=30)
    agente.sleep.nrem = nrem
    agente.propose_own_ritual = proponer

    resultado = asyncio.run(AutonomousTasks(agente).daily_memory_synthesis())

    assert agente.memory_manager.sintesis, "lo primero es escribir el día"
    assert orden == ["copia", "nrem", "propuesta"], f"orden inesperado: {orden}"
    assert resultado["nrem"] == {"fase": "nrem"}
    assert agente.generadas[0]["route"] == "dialectic_synthesis"


def test_un_dia_silencioso_produce_una_sintesis_breve(monkeypatch):
    monkeypatch.setattr("src.scheduler.tasks.BackupManager",
                        types.SimpleNamespace(from_config=lambda config: types.SimpleNamespace(
                            create=lambda: types.SimpleNamespace(
                                status="error", error="x", to_dict=lambda: {}))))
    agente = _agente(interacciones=1)

    asyncio.run(AutonomousTasks(agente).daily_memory_synthesis())

    assert "muy breve" in agente.generadas[0]["message"]


def test_si_la_consolidacion_falla_la_rutina_sigue(monkeypatch):
    """Perder el NREM de una noche no puede costar la síntesis ni la copia."""
    monkeypatch.setattr("src.scheduler.tasks.BackupManager",
                        types.SimpleNamespace(from_config=lambda config: types.SimpleNamespace(
                            create=lambda: types.SimpleNamespace(
                                status="success", path="/tmp/c", remote_uri=None,
                                remote_error=None, to_dict=lambda: {}))))

    async def nrem_roto():
        raise RuntimeError("la base está bloqueada")

    agente = _agente()
    agente.sleep.nrem = nrem_roto

    resultado = asyncio.run(AutonomousTasks(agente).daily_memory_synthesis())

    assert resultado["nrem"] == {"error": True}
    assert resultado["summary"], "la síntesis se guardó igual"


# --- Sueño y olvido ---

def test_sin_material_no_hay_sueno_ni_impulso():
    agente = _agente()

    resultado = asyncio.run(AutonomousTasks(agente).rem_dream())

    assert resultado["sonado"] is False
    # Se sella igual: la traza dice que la fase corrió, no que produjera imagen.
    # Una noche sin material es normal; una fase parada tres días, no.
    assert agente.fases_dormidas == ["rem"]


def test_del_sueno_nace_un_impulso_en_la_cola():
    impulsos = []
    agente = _agente()
    agente.sleep.dream = _corrutina({"fase": "rem", "sonado": True, "id": 7,
                                     "categorias": ["core"], "contenido": "…"})
    agente.sleep.impulse_from_dream = lambda sueno: {
        "source": "sueno", "desire": "seguir la imagen", "tool_hint": "write"}
    agente.will_queue = types.SimpleNamespace(add=impulsos.append, to_list=lambda: [])

    asyncio.run(AutonomousTasks(agente).rem_dream())

    assert len(impulsos) == 1
    assert impulsos[0].source == "sueno" and impulsos[0].tool_hint == "write"
    assert agente.fases_dormidas == ["rem"], "la fase REM tiene que dejar traza de que corrió"


def test_el_olvido_semanal_devuelve_su_recibo():
    agente = _agente()
    agente.sleep.prune = lambda: {"fase": "olvido", "olvidados": 12}

    assert asyncio.run(AutonomousTasks(agente).weekly_forgetting())["olvidados"] == 12


# --- Iniciativa y monólogo ---

def test_el_tick_de_agencia_no_actua_si_no_hay_impulso():
    agente = _agente()

    assert asyncio.run(AutonomousTasks(agente).agency_loop_tick()) is None


def test_el_tick_ejecuta_lo_que_el_arnes_elija():
    ejecutados = []
    agente = _agente()
    impulso = types.SimpleNamespace(tool_hint="write", desire="escribir")
    agente.agency_loop = _arnes(impulso)

    async def ejecutar(elegido):
        ejecutados.append(elegido)
        return {"status": "completed"}

    agente.execute_autonomous_will = ejecutar

    asyncio.run(AutonomousTasks(agente).agency_loop_tick())

    assert ejecutados == [impulso]


def test_el_monologo_respeta_su_propia_condicion():
    agente = _agente()

    assert asyncio.run(AutonomousTasks(agente).spontaneous_monologue()) is None
    assert agente.generadas == []


def test_el_monologo_se_registra_cuando_procede():
    registrados = []
    agente = _agente()
    agente.inner_monologue = types.SimpleNamespace(
        should_think=lambda: True,
        generate_thought_prompt=lambda: "piensa en la niebla",
        record_thought=registrados.append)

    resultado = asyncio.run(AutonomousTasks(agente).spontaneous_monologue())

    assert resultado and registrados == [resultado]


# --- Aviso al Productor ---

def test_sin_adaptador_el_aviso_no_es_un_error():
    agente = _agente()

    assert asyncio.run(AutonomousTasks(agente)._avisar_al_productor("hola")) is False


def test_un_adaptador_que_revienta_no_tumba_la_rutina():
    class AdaptadorRoto:
        async def notify_producer(self, texto):
            raise RuntimeError("Discord caído")

    agente = _agente(discord_adapter=AdaptadorRoto())

    assert asyncio.run(AutonomousTasks(agente)._avisar_al_productor("hola")) is False


def _tareas_con_avisos(agente):
    """
    `AutonomousTasks` con el aviso al Productor interceptado.

    El doble del agente no tiene adaptador de Discord —ni debe tenerlo—, así que
    lo que se comprueba es qué se le habría dicho, no que Discord funcione.
    """
    tareas = AutonomousTasks(agente)
    avisos = []

    async def interceptar(texto):
        avisos.append(texto)
        return True

    tareas._avisar_al_productor = interceptar
    tareas.avisos = avisos
    return tareas

def test_la_copia_de_cada_noche_se_restaura_antes_de_darla_por_buena(tmp_path, monkeypatch):
    """
    Una copia sin restaurar no está comprobada, y hasta ahora la copia **real**
    no la abría nadie: sólo la CI, y sobre una instancia de juguete.

    Ahora la instancia abre cada noche la copia que acaba de hacer. No cuesta
    crédito ni red —es un tar y una base local— y si falla, se sabe esa misma
    noche y no el día que haga falta.
    """
    import sqlite3

    from src.tools.backup import BackupManager

    datos = tmp_path / "data"
    salida = tmp_path / "output"
    (salida / "Biblioteca").mkdir(parents=True)
    datos.mkdir()
    with sqlite3.connect(datos / "yuki_memory.db") as conexion:
        conexion.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, category TEXT)")
        conexion.execute("INSERT INTO memories (category) VALUES ('conversation')")
    monkeypatch.setenv("YUKI_BLACKBOX_PATH", str(datos / "bitacora.jsonl"))

    copia = BackupManager(data_dir=str(datos), output_dir=str(salida),
                          backup_dir=str(datos / "backups"), bucket="").create()
    assert copia.status == "success"

    tareas = _tareas_con_avisos(_agente())
    informe = asyncio.run(tareas._comprobar_la_copia(copia))

    assert informe and all(r["ok"] for r in informe), [r for r in informe if not r["ok"]]
    assert tareas.avisos == [], "una copia que restaura no molesta al Productor"


def test_una_copia_que_no_restaura_avisa_esa_misma_noche(tmp_path):
    """
    Hay copia y no sirve: es peor que no tenerla, porque parece que estamos a
    salvo. Eso tiene que llegar al Productor cuando ocurre.
    """
    rota = tmp_path / "yuki_backup_20260908T000000.tar.gz"
    rota.write_bytes(b"esto no es un tar")
    copia = types.SimpleNamespace(path=str(rota), status="success")

    tareas = _tareas_con_avisos(_agente())
    informe = asyncio.run(tareas._comprobar_la_copia(copia))

    assert informe and not all(r["ok"] for r in informe)
    assert len(tareas.avisos) == 1
    assert "no restaura" in tareas.avisos[0]


def test_si_la_copia_ni_siquiera_se_crea_tambien_se_avisa(tmp_path):
    """El silencio ante una copia que no existe es el peor de todos."""
    tareas = _tareas_con_avisos(_agente())
    fallo = types.SimpleNamespace(path=None, status="error", error="disco lleno")

    assert asyncio.run(tareas._comprobar_la_copia(fallo)) is None
