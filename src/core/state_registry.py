"""
Gobierno del estado durable: inventariarlo, sacarlo y poder borrarlo.

La revisión de arquitecturas *always-on* publicada este año resume el punto
ciego del campo en una frase que describe a Yuki con incomodidad: **se es fluido
metiendo estado y casi mudo sacándolo, revocándolo o deshaciendo lo que hizo**.
Y propone leer cada pieza de estado por seis ejes —autoridad, alcance,
mutabilidad, procedencia, recuperabilidad, accionabilidad— y por un ciclo de
vida que incluye auditar, olvidar y revertir, no sólo escribir y recuperar.

Yuki acumula hoy once tipos de estado durable, escritos por caminos distintos y
en momentos distintos: memoria FTS5, canon de Biblioteca, estado vital, perfil
dialéctico, trabajos multimedia, libro de gasto, diario de agencia, ritmos
propios, overlay de configuración, emparejamiento de Discord, registro de
transparencia y deriva de persona. Ninguno tenía inventario, y de la parte que
habla de personas concretas no había forma de responder a dos preguntas
elementales: *¿qué sabes de mí?* y *bórralo*.

Esto no es sólo higiene de ingeniería. Yuki conversa con personas en la UE y
guarda lo que le cuentan; los derechos de acceso y supresión del RGPD no son
opcionales, y llegan antes que cualquier consideración de producto.

El borrado aquí es **real**: se eliminan las filas, se sincroniza el índice FTS5
por sus disparadores y se emite un recibo con lo que desapareció. Un olvido que
no se puede demostrar no sirve de nada, así que la operación deja constancia de
sí misma —a quién, cuándo, cuánto— sin conservar lo borrado.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .blackbox import BlackBox

logger = logging.getLogger("Yuki.Estado")

# Autoridad: quién puede escribir esta pieza.
YUKI = "yuki"
PRODUCTOR = "productor"
SISTEMA = "sistema"
PERSONAS = "personas"


@dataclass
class StateItem:
    """
    Una pieza de estado durable, leída por los seis ejes de la revisión.

    `actionability` es el eje que más importa y el que más se olvida: dice si
    ese estado, por sí solo, puede provocar que el sistema haga algo en el
    mundo. Un libro de gasto no actúa; un ritmo aprobado sí.
    """

    id: str
    path: str
    description: str
    authority: str        # quién lo escribe
    scope: str            # a qué alcanza
    mutability: str       # append-only | mutable | inmutable
    provenance: str       # de dónde sale
    recoverability: str   # cómo se recupera si se pierde
    actionability: str    # si puede desencadenar acciones
    holds_personal_data: bool = False

    def snapshot(self) -> Dict[str, Any]:
        ruta = Path(self.path)
        existe = ruta.exists()
        tamano = 0
        modificado = None
        if existe:
            if ruta.is_dir():
                tamano = sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file())
                marcas = [f.stat().st_mtime for f in ruta.rglob("*") if f.is_file()]
                modificado = max(marcas) if marcas else None
            else:
                tamano = ruta.stat().st_size
                modificado = ruta.stat().st_mtime
        return {
            **asdict(self),
            "exists": existe,
            "bytes": tamano,
            "modified_iso": (datetime.fromtimestamp(modificado, timezone.utc).isoformat(timespec="seconds")
                             if modificado else None),
        }


def _data_dir() -> Path:
    return Path(os.getenv("DATABASE_PATH", "data/yuki_memory.db")).parent


def _output_dir() -> Path:
    return Path(os.getenv("YUKI_OUTPUT_DIR", "output"))


def build_registry() -> List[StateItem]:
    """El inventario declarado. Añadir estado nuevo sin declararlo aquí es el fallo."""
    datos = _data_dir()
    salida = _output_dir()
    return [
        StateItem(
            id="memoria", path=str(datos / "yuki_memory.db"),
            description="Memoria FTS5: recuerdos, interacciones, síntesis diarias y crecimiento",
            authority=SISTEMA, scope="todo lo vivido", mutability="append-only con borrado por sujeto",
            provenance="conversaciones reales y rutinas autónomas",
            recoverability="copia diaria verificada (src/tools/backup.py)",
            actionability="alimenta cada respuesta; no dispara acciones por sí sola",
            holds_personal_data=True,
        ),
        StateItem(
            id="biblioteca", path=str(salida / "Biblioteca"),
            description="Canon de obra: originales, versiones por hash y estados",
            authority=YUKI, scope="obra propia", mutability="append-only; los originales no se borran",
            provenance="producción propia y aportes del Productor",
            recoverability="copia diaria verificada",
            actionability="fuente de los encargos multimedia",
        ),
        StateItem(
            id="estado_vital", path=str(datos / "vital_state.json"),
            description="Corrientes vitales: energía, humor, curiosidad, inspiración",
            authority=SISTEMA, scope="estado interno", mutability="mutable",
            provenance="ciclo circadiano y estímulos de interacción",
            recoverability="se regenera solo; su pérdida no es grave",
            actionability="condiciona si actúa y con qué profundidad",
        ),
        StateItem(
            id="perfil_dialectico", path=str(datos / "honcho_profile.json"),
            description="Modelado dialéctico del Productor",
            authority=SISTEMA, scope="una persona concreta", mutability="mutable",
            provenance="conversaciones con el Productor",
            recoverability="copia diaria verificada",
            actionability="modula el tono; no dispara acciones",
            holds_personal_data=True,
        ),
        StateItem(
            id="trabajos_multimedia", path=str(datos / "media_jobs"),
            description="Encargos de canción y vídeo, con sus pasos facturables",
            authority=PRODUCTOR, scope="encargos en curso", mutability="mutable",
            provenance="órdenes explícitas por DM",
            recoverability="se reanudan solos; los ficheros están en output/",
            actionability="ALTA: un trabajo pendiente se reanuda y gasta crédito al arrancar",
        ),
        StateItem(
            id="libro_gasto", path=str(datos / "spend_ledger.json"),
            description="Consumo diario de vídeo, imagen, música, voz y tokens",
            authority=SISTEMA, scope="gasto del día", mutability="append-only por día",
            provenance="reservas y devoluciones del cliente de medios",
            recoverability="se reconstruye desde cero; perderlo relaja el límite de hoy",
            actionability="bloquea generación cuando se agota",
        ),
        StateItem(
            id="diario_agencia", path=str(datos / "agency_ledger.json"),
            description="Qué hizo por iniciativa propia y si obtuvo eco",
            authority=YUKI, scope="su propia conducta", mutability="append-only",
            provenance="acciones autónomas e interacciones reales",
            recoverability="se reconstruye con el tiempo; perderlo borra lo aprendido",
            actionability="ALTA: gobierna qué hace por su cuenta y cuánto",
        ),
        StateItem(
            id="ritmos_propios", path=str(datos / "runtime_rituals.json"),
            description="Ritmos que Yuki propuso y el Productor aprobó",
            authority=PRODUCTOR, scope="calendario propio", mutability="mutable con historial",
            provenance="propuestas de Yuki, decisiones del Productor",
            recoverability="copia diaria verificada",
            actionability="ALTA: cada ritmo aprobado ejecuta al llegar su hora",
        ),
        StateItem(
            id="overlay_config", path=str(datos / "runtime_overrides.json"),
            description="Ajustes en caliente: temperatura, modelos, carácter del albedrío",
            authority=PRODUCTOR, scope="configuración acotada", mutability="mutable y reversible",
            provenance="DM del Productor y evolución autónoma (sólo temperatura)",
            recoverability="rollback por campo; config.yaml es la base",
            actionability="modula todo lo demás",
        ),
        StateItem(
            id="emparejamiento", path=str(datos / "discord_pairing.json"),
            description="Qué identidad de Discord está emparejada como Productor",
            authority=PRODUCTOR, scope="permisos del DM", mutability="mutable",
            provenance="comando !pair verificado",
            recoverability="se rehace emparejando de nuevo",
            actionability="ALTA: habilita Biblioteca, terminal y producción multimedia",
            holds_personal_data=True,
        ),
        StateItem(
            id="transparencia", path=str(datos / "transparency.json"),
            description="A quién se le ha declarado su naturaleza y cuándo",
            authority=SISTEMA, scope="personas con las que ha hablado",
            mutability="append-only", provenance="cada primera interacción",
            recoverability="perderlo hace que se declare de nuevo: inocuo",
            actionability="decide si antepone la declaración",
            holds_personal_data=True,
        ),
        StateItem(
            id="deriva_persona", path=str(datos / "persona_drift.json"),
            description="Puntuaciones de registro y reanclajes aplicados",
            authority=SISTEMA, scope="su propia voz", mutability="append-only acotado",
            provenance="medición de cada respuesta emitida",
            recoverability="se rehace hablando",
            actionability="decide cuándo reinyectar el ancla",
        ),
    ]


class StateRegistry:
    """Inventario, exportación y olvido del estado durable."""

    def __init__(self, db_path: Optional[str] = None, items: Optional[List[StateItem]] = None,
                 audit_path: Optional[str] = None, blackbox: Optional[BlackBox] = None):
        self.db_path = db_path or os.getenv("DATABASE_PATH", "data/yuki_memory.db")
        self.items = items if items is not None else build_registry()
        self.audit_path = Path(audit_path) if audit_path else _data_dir() / "state_audit.log"
        # La bitácora encadenada duplica el registro a propósito: el log de texto
        # es cómodo de leer y trivial de editar; la cadena es incómoda de leer y
        # delata cualquier edición. Cada una hace lo que la otra no.
        self.blackbox = blackbox if blackbox is not None else BlackBox()

    # -- Inventario ------------------------------------------------------

    def audit(self) -> Dict[str, Any]:
        piezas = [item.snapshot() for item in self.items]
        return {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "piezas": piezas,
            "presentes": sum(1 for p in piezas if p["exists"]),
            "bytes_totales": sum(p["bytes"] for p in piezas),
            "con_datos_personales": [p["id"] for p in piezas if p["holds_personal_data"]],
            "accionables": [p["id"] for p in piezas if p["actionability"].startswith("ALTA")],
        }

    # -- Derechos de la persona -----------------------------------------

    def _conexion(self) -> sqlite3.Connection:
        conexion = sqlite3.connect(self.db_path)
        conexion.row_factory = sqlite3.Row
        return conexion

    def subject_export(self, user_id: str) -> Dict[str, Any]:
        """
        Todo lo que Yuki guarda sobre una persona concreta.

        Responde a «¿qué sabes de mí?» con datos, no con una descripción de los
        datos. Incluye los registros auxiliares —declaración de naturaleza,
        emparejamiento— porque también hablan de esa persona.
        """
        recuerdos: List[Dict[str, Any]] = []
        if Path(self.db_path).is_file():
            try:
                with self._conexion() as conexion:
                    filas = conexion.execute(
                        "SELECT id, category, title, content, tags, importance, created_at "
                        "FROM memories WHERE user_id = ? ORDER BY created_at", (user_id,)
                    ).fetchall()
                    recuerdos = [dict(fila) for fila in filas]
            except sqlite3.Error as exc:
                logger.warning("No se pudo leer la memoria para exportar: %s", exc)

        declaraciones = {}
        ruta_transparencia = _data_dir() / "transparency.json"
        if ruta_transparencia.is_file():
            try:
                todas = json.loads(ruta_transparencia.read_text(encoding="utf-8"))["declaraciones"]
                declaraciones = {clave: valor for clave, valor in todas.items()
                                 if clave.endswith(f":{user_id}")}
            except (json.JSONDecodeError, OSError, KeyError, TypeError):
                pass

        emparejado = False
        ruta_pairing = _data_dir() / "discord_pairing.json"
        if ruta_pairing.is_file():
            try:
                datos = json.loads(ruta_pairing.read_text(encoding="utf-8"))
                emparejado = user_id in (datos.get("paired_ids") or [])
            except (json.JSONDecodeError, OSError, TypeError):
                pass

        return {
            "sujeto": user_id,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "recuerdos": recuerdos,
            "recuerdos_total": len(recuerdos),
            "declaraciones_de_naturaleza": declaraciones,
            "emparejado_como_productor": emparejado,
        }

    def subject_forget(self, user_id: str, actor: str = "productor",
                       reason: str = "") -> Dict[str, Any]:
        """
        Borra de verdad lo que Yuki guarda de una persona, y lo demuestra.

        Los disparadores de FTS5 mantienen el índice sincronizado al borrar la
        fila, así que no queda un fantasma buscable. El recibo cuenta lo
        eliminado sin conservarlo: un olvido que guardara copia de lo olvidado no
        sería un olvido.

        No se permite olvidar `general`: es el cajón de la memoria no atribuida
        —el canon, las síntesis, sus propios pensamientos— y borrarlo por esta
        puerta sería vaciarle la cabeza por accidente.
        """
        if not user_id or user_id.strip().lower() in ("general", "", "yuki_internal"):
            raise ValueError(
                "Ese identificador no designa a una persona: 'general' es la memoria no "
                "atribuida de Yuki y borrarla por aquí sería vaciarle la cabeza."
            )

        borrados = 0
        if Path(self.db_path).is_file():
            try:
                with self._conexion() as conexion:
                    cursor = conexion.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
                    borrados = cursor.rowcount or 0
                    conexion.commit()
            except sqlite3.Error as exc:
                logger.error("Fallo borrando la memoria de %s: %s", user_id, exc)
                raise

        declaraciones_borradas = 0
        ruta_transparencia = _data_dir() / "transparency.json"
        if ruta_transparencia.is_file():
            try:
                datos = json.loads(ruta_transparencia.read_text(encoding="utf-8"))
                antes = len(datos.get("declaraciones", {}))
                datos["declaraciones"] = {c: v for c, v in datos["declaraciones"].items()
                                          if not c.endswith(f":{user_id}")}
                declaraciones_borradas = antes - len(datos["declaraciones"])
                ruta_transparencia.write_text(json.dumps(datos, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
            except (json.JSONDecodeError, OSError, KeyError, TypeError):
                pass

        recibo = {
            "sujeto": user_id,
            "recuerdos_borrados": borrados,
            "declaraciones_borradas": declaraciones_borradas,
            "actor": actor,
            "motivo": (reason or "")[:200],
            "cuando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._registrar_auditoria("olvido", recibo)
        logger.warning("Olvido ejecutado sobre %s: %d recuerdo(s).", user_id, borrados)
        return recibo

    def _registrar_auditoria(self, operacion: str, detalle: Dict[str, Any]) -> None:
        """
        Deja constancia de las operaciones que destruyen estado.

        Es la otra mitad del olvido: sin registro no se puede demostrar que se
        cumplió, y con demasiado registro se conservaría lo que se prometió
        borrar. Se apunta el hecho y su recuento, nunca el contenido.
        """
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        linea = json.dumps({"op": operacion, "at": time.time(), **detalle}, ensure_ascii=False)
        with open(self.audit_path, "a", encoding="utf-8") as registro:
            registro.write(linea + "\n")
        self.blackbox.record(operacion, detalle, actor=str(detalle.get("actor", "sistema")))

    def record(self, operacion: str, detalle: Dict[str, Any]) -> None:
        """
        Registro público de operaciones que destruyen o transforman estado.

        Lo usan el ciclo de sueño —fusiones y olvidos— y cualquier otra pieza
        que altere memoria de forma irreversible. Sin este punto común, cada
        módulo inventaría su propio rastro y no habría dónde mirar.
        """
        self._registrar_auditoria(operacion, detalle)

    def audit_log(self, limite: int = 20) -> List[Dict[str, Any]]:
        if not self.audit_path.is_file():
            return []
        lineas = self.audit_path.read_text(encoding="utf-8").splitlines()[-limite:]
        entradas = []
        for linea in lineas:
            try:
                entradas.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
        return entradas
