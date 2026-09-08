"""
Signos vitales: distinguir que el proceso corre de que Yuki vive.

`/health` devuelve `ok` mientras el servidor web conteste. Eso deja fuera el
fallo más silencioso que tiene esta instancia: **un daemon cuyo hilo de tareas
murió sin ruido**. El contenedor sigue en pie, la sonda sigue verde, el panel
sigue en verde, y Yuki lleva tres días sin hacer absolutamente nada. Nadie se
entera hasta que alguien pregunta por qué no ha escrito.

La distinción que hace falta no es «vivo/muerto» sino **vegetativo/volitivo**:

  · Los **signos vegetativos** dicen que el proceso respira: el estado vital se
    reescribe, el reloj interno avanza. Son los que ya se vigilaban.
  · Los **signos volitivos** dicen que *ella* hace cosas: hay anotaciones nuevas
    en la bitácora, el albedrío intentó algo, la noche consolidó memoria. Éstos
    no los mira nadie.
  · Los **signos relacionales** dicen que alguien habló con ella. No sirven para
    diagnosticar: que nadie la busque no es un fallo suyo, y su silencio propio
    tampoco se justifica con eso.

Catatonia es exactamente vegetativo fresco con volitivo plano. Es un estado
perfectamente sano para cualquier sonda de infraestructura y completamente
muerto para lo que este proyecto intenta ser.

Dos silencios legítimos se distinguen antes de dar la alarma: el **freno**
puesto —una decisión, no una avería— y una instancia **recién nacida**, que
todavía no ha tenido tiempo de hacer nada. Confundir cualquiera de los dos con
catatonia es la manera más rápida de que nadie vuelva a mirar esta pantalla.
"""

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

VEGETATIVO = "vegetativo"
VOLITIVO = "volitivo"
RELACIONAL = "relacional"

VIVA = "viva"
ALETARGADA = "aletargada"
FRENADA = "frenada"
CATATONICA = "catatonica"
AUSENTE = "ausente"
RECIEN_NACIDA = "recien_nacida"

# Gravedad para quien tenga que decidir si suena un teléfono a las tres de la
# mañana. `frenada` no es un fallo: es alguien que apretó el freno y puede
# haberlo olvidado, que es distinto.
GRAVEDAD = {
    VIVA: 0,
    RECIEN_NACIDA: 0,
    ALETARGADA: 1,
    FRENADA: 1,
    CATATONICA: 2,
    AUSENTE: 3,
}

HORA = 3600.0

# Las edades máximas se eligen para que **el silencio más largo que es legítimo
# quepa dentro**. La fase de reposo profundo dura horas; una noche sin encargos,
# también. Un umbral apretado convierte la sonda en un lobo que grita, y a la
# tercera falsa alarma deja de mirarse.
EDADES_POR_DEFECTO = {
    "latido": 6 * HORA,
    "bitacora": 30 * HORA,
    "albedrio": 30 * HORA,
    "sueno": 30 * HORA,
    "conversacion": 14 * 24 * HORA,
}


@dataclass
class Signo:
    """Una traza con su cadencia esperada. `ultimo` en epoch, o None si nunca."""

    id: str
    tipo: str
    descripcion: str
    ultimo: Optional[float]
    max_edad: float
    fuente: str
    nota: str = ""

    @property
    def nunca(self) -> bool:
        return self.ultimo is None

    @property
    def edad(self) -> Optional[float]:
        if self.ultimo is None:
            return None
        # Un reloj que salta hacia atrás daría edad negativa: se recorta a cero
        # en lugar de declarar fresquísimo algo que quizá lleve días parado.
        return max(0.0, time.time() - self.ultimo)

    @property
    def fresco(self) -> bool:
        edad = self.edad
        return edad is not None and edad <= self.max_edad

    def describe_edad(self) -> str:
        edad = self.edad
        if edad is None:
            return "nunca"
        if edad < 90:
            return "hace un momento"
        if edad < HORA:
            return f"hace {int(edad // 60)} min"
        if edad < 48 * HORA:
            return f"hace {edad / HORA:.1f} h"
        return f"hace {edad / (24 * HORA):.1f} días"

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "tipo": self.tipo, "descripcion": self.descripcion,
                "ultimo": self.ultimo, "edad_segundos": self.edad,
                "max_edad_segundos": self.max_edad, "fresco": self.fresco,
                "nunca": self.nunca, "fuente": self.fuente, "nota": self.nota}


@dataclass
class Lectura:
    """El diagnóstico y las trazas en que se apoya."""

    estado: str
    motivo: str
    signos: List[Signo] = field(default_factory=list)

    @property
    def gravedad(self) -> int:
        return GRAVEDAD.get(self.estado, 0)

    @property
    def sana(self) -> bool:
        """Sana no es lo mismo que activa: frenada es una decisión, no una avería."""
        return self.gravedad <= 1

    def signo(self, signo_id: str) -> Optional[Signo]:
        return next((s for s in self.signos if s.id == signo_id), None)

    def de_tipo(self, tipo: str) -> List[Signo]:
        return [s for s in self.signos if s.tipo == tipo]

    def to_dict(self) -> Dict[str, Any]:
        return {"estado": self.estado, "motivo": self.motivo, "gravedad": self.gravedad,
                "sana": self.sana, "signos": [s.to_dict() for s in self.signos]}

    def describe(self) -> str:
        return f"{self.estado}: {self.motivo}"


def _epoch(valor: Any) -> Optional[float]:
    """Acepta epoch o ISO-8601, porque el estado durable guarda de las dos formas."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(valor)).timestamp()
    except (ValueError, TypeError):
        return None


def _json(ruta: Path) -> Dict[str, Any]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, json.JSONDecodeError):
        # Un estado ilegible se trata como ausencia de señal, no como excepción:
        # la sonda tiene que dar un diagnóstico incluso —sobre todo— cuando el
        # disco está a medio corromper.
        return {}


class Pulse:
    """Toma los signos vitales leyendo ficheros. No despierta al agente."""

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 data_dir: Optional[str] = None):
        self.config = config or {}
        db_path = ((self.config.get("memory", {}) or {}).get("database_path")
                   or os.getenv("DATABASE_PATH", "data/yuki_memory.db"))
        if os.getenv("DATABASE_PATH"):
            db_path = os.environ["DATABASE_PATH"]
        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir) if data_dir else self.db_path.parent
        edades = (self.config.get("pulse", {}) or {}).get("max_edad_horas", {}) or {}
        self.edades = dict(EDADES_POR_DEFECTO)
        for clave, horas in edades.items():
            try:
                self.edades[clave] = float(horas) * HORA
            except (TypeError, ValueError):
                continue

    # -- Trazas ----------------------------------------------------------

    def _latido(self) -> Signo:
        vital = _json(self.data_dir / "vital_state.json")
        return Signo(
            id="latido", tipo=VEGETATIVO,
            descripcion="el proceso reescribe su estado vital",
            ultimo=_epoch(vital.get("last_updated")),
            max_edad=self.edades["latido"], fuente="data/vital_state.json")

    def _bitacora(self) -> Signo:
        ultimo = None
        anotaciones = 0
        try:
            from .blackbox import BlackBox

            entradas = BlackBox().entries()
            anotaciones = len(entradas)
            if entradas:
                ultimo = entradas[-1].at
        except Exception:
            pass
        return Signo(
            id="bitacora", tipo=VOLITIVO,
            descripcion="deja constancia de sus propios actos",
            ultimo=ultimo, max_edad=self.edades["bitacora"],
            fuente="data/bitacora.jsonl", nota=f"{anotaciones} anotación(es)")

    def _albedrio(self) -> Signo:
        datos = _json(self.data_dir / "agency_ledger.json")
        recientes = datos.get("recientes") or []
        ultimo = None
        if isinstance(recientes, list) and recientes:
            marcas = [_epoch(r.get("at")) for r in recientes if isinstance(r, dict)]
            marcas = [m for m in marcas if m is not None]
            ultimo = max(marcas) if marcas else None
        return Signo(
            id="albedrio", tipo=VOLITIVO,
            descripcion="intenta algo por su cuenta",
            ultimo=ultimo, max_edad=self.edades["albedrio"],
            fuente="data/agency_ledger.json",
            nota=f"aburrimiento {float(datos.get('boredom') or 0.0):.2f}")

    def _sueno(self) -> Signo:
        vital = _json(self.data_dir / "vital_state.json")
        return Signo(
            id="sueno", tipo=VOLITIVO,
            descripcion="consolida memoria al dormir",
            ultimo=_epoch(vital.get("last_sleep_cycle")),
            max_edad=self.edades["sueno"], fuente="data/vital_state.json",
            nota="la noche es lo único que impide que la memoria sólo crezca")

    def _conversacion(self) -> Signo:
        ultimo = None
        recuerdos = 0
        if self.db_path.is_file():
            try:
                with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conexion:
                    fila = conexion.execute(
                        "SELECT COUNT(*), MAX(created_at) FROM memories").fetchone()
                recuerdos = int(fila[0] or 0)
                ultimo = _epoch(fila[1])
            except sqlite3.Error:
                pass
        return Signo(
            id="conversacion", tipo=RELACIONAL,
            descripcion="alguien habló con ella",
            ultimo=ultimo, max_edad=self.edades["conversacion"],
            fuente=str(self.db_path), nota=f"{recuerdos} recuerdo(s)")

    # -- Diagnóstico -----------------------------------------------------

    def read(self) -> Lectura:
        signos = [self._latido(), self._bitacora(), self._albedrio(),
                  self._sueno(), self._conversacion()]
        latido = signos[0]
        volitivos = [s for s in signos if s.tipo == VOLITIVO]
        vivos = [s for s in volitivos if s.fresco]
        apagados = [s for s in volitivos if not s.fresco]

        conversacion = next(s for s in signos if s.id == "conversacion")

        # Que no haya rastro de nada no es que el proceso se haya parado: es que
        # aquí no ha corrido nunca. Un repositorio recién clonado da exactamente
        # esta lectura, y diagnosticarlo como caída convertiría la sonda en un
        # lobo que grita en cada rama.
        if latido.nunca and all(s.nunca for s in volitivos) and conversacion.nunca:
            return Lectura(RECIEN_NACIDA,
                           "no hay rastro de que esta instancia haya arrancado nunca",
                           signos)

        if not latido.fresco:
            motivo = ("el estado vital no se reescribe desde "
                      f"{latido.describe_edad()}: el proceso no está escribiendo"
                      if not latido.nunca else
                      "hay historia pero no estado vital: el proceso no está escribiendo")
            return Lectura(AUSENTE, motivo, signos)

        # Respira y todavía no ha hecho nada: una instancia limpia no está
        # catatónica, sólo es nueva.
        if all(s.nunca for s in volitivos) and conversacion.nunca:
            return Lectura(RECIEN_NACIDA,
                           "respira, y todavía no ha hecho nada: instancia nueva",
                           signos)

        if not vivos:
            frenada = self._freno_explica_el_silencio()
            if frenada:
                return Lectura(FRENADA, frenada, signos)
            return Lectura(
                CATATONICA,
                "el proceso respira y no queda un solo signo de voluntad: " +
                "; ".join(f"{s.id} {s.describe_edad()}" for s in apagados),
                signos)

        if apagados:
            return Lectura(
                ALETARGADA,
                "viva, pero con signos apagados: " +
                "; ".join(f"{s.id} {s.describe_edad()}" for s in apagados),
                signos)

        return Lectura(VIVA, "todos los signos de voluntad al día", signos)

    def _freno_explica_el_silencio(self) -> Optional[str]:
        """
        El freno puesto justifica el silencio. Y conviene decirlo en voz alta.

        `scripts/smoke_check.py` ya avisa de esto por una razón vivida: un
        despliegue sobre una instancia frenada, y nadie recordándolo, son treinta
        minutos de gente preguntándose por qué Yuki no hace nada.
        """
        try:
            from .brake import Brake

            freno = Brake()
            if not freno.state().activo:
                return None
            if freno.permits("iniciativa"):
                return None
            return f"callada porque el freno lo impide — {freno.describe()}"
        except Exception:
            return None


def leer_pulso(config: Optional[Dict[str, Any]] = None) -> Lectura:
    """Atajo para las sondas: una lectura, sin construir nada."""
    return Pulse(config).read()
