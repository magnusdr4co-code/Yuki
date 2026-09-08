"""
Bitácora: la caja negra de Yuki, encadenada por hash.

Todo el estado que Yuki acumula tiene ya su registro —olvidos, fusiones, gasto,
ritmos aprobados, ajustes de carácter—, pero ese registro es un fichero de texto
en el mismo disco que todo lo demás. Cualquiera con acceso a la instancia puede
abrirlo y quitar una línea: la constancia de un olvido que no debió ejecutarse,
la de un gasto que nadie autorizó, la de un cambio de configuración. Un diario
que se puede reescribir sin dejar marca no es un diario, es un borrador.

Esto lo cierra con el mecanismo más viejo y más barato que existe para eso: cada
anotación incluye el hash de la anterior. Cambiar una línea del pasado obliga a
recalcular todas las siguientes, y quien mire la cadena lo ve en el primer
eslabón roto. No impide la manipulación —nada en el propio disco puede
impedirla—, pero la vuelve **evidente**, que es lo que se puede prometer y
cumplir.

Contra el truco obvio —borrar el final de la cadena en vez de editar el medio—
existe el **precinto**: el hash de la cabeza en un momento dado, que sale de la
instancia con la copia diaria. Si mañana la cadena no contiene ese precinto,
alguien cortó por detrás.

Deliberadamente NO es una cadena de bloques: no hay consenso, ni red, ni prueba
de trabajo, ni nada que justifique esas palabras. Es un fichero append-only con
hashes encadenados, y decirlo así es más honesto que adornarlo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("Yuki.Bitácora")

# Hash de partida de la cadena. Cualquier valor fijo sirve; éste dice de dónde
# viene, que es más útil que treinta ceros.
GENESIS = hashlib.sha256(b"yuki-bitacora-genesis").hexdigest()

# Campos que jamás se anotan aunque lleguen en el detalle de una operación: la
# bitácora es un registro de actos, no un archivo de lo que esos actos tocaron.
CAMPOS_PROHIBIDOS = frozenset({
    "content", "contenido", "texto", "prompt", "token", "secret", "password",
    "api_key", "authorization", "message", "mensaje",
})

MAX_VALOR = 300


def _limpiar(detalle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recorta el detalle a lo que puede vivir para siempre en un fichero.

    Una bitácora inmutable con contenido dentro sería lo contrario de un olvido:
    borrar un recuerdo y dejar su texto en el registro que prueba que se borró.
    """
    limpio: Dict[str, Any] = {}
    for clave, valor in (detalle or {}).items():
        if clave.lower() in CAMPOS_PROHIBIDOS:
            limpio[clave] = f"<omitido: {len(str(valor))} caracteres>"
        elif isinstance(valor, (dict, list)):
            limpio[clave] = json.dumps(valor, ensure_ascii=False)[:MAX_VALOR]
        elif isinstance(valor, str):
            limpio[clave] = valor[:MAX_VALOR]
        else:
            limpio[clave] = valor
    return limpio


@dataclass
class Entrada:
    """Un eslabón: lo que pasó, cuándo, quién, y de qué cuelga."""

    seq: int
    at: float
    op: str
    actor: str
    detail: Dict[str, Any]
    prev: str
    hash: str

    def cuerpo(self) -> str:
        """Serialización canónica: lo que se firma. El orden importa y es fijo."""
        return json.dumps(
            {"seq": self.seq, "at": round(self.at, 3), "op": self.op,
             "actor": self.actor, "detail": self.detail, "prev": self.prev},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )

    def calcular_hash(self) -> str:
        return hashlib.sha256(self.cuerpo().encode("utf-8")).hexdigest()

    def to_line(self) -> str:
        return json.dumps({**self.__dict__}, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_line(cls, linea: str) -> Optional["Entrada"]:
        try:
            datos = json.loads(linea)
            return cls(seq=int(datos["seq"]), at=float(datos["at"]), op=str(datos["op"]),
                       actor=str(datos["actor"]), detail=dict(datos["detail"]),
                       prev=str(datos["prev"]), hash=str(datos["hash"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None


class BlackBox:
    """Registro append-only con hashes encadenados."""

    def __init__(self, path: Optional[str] = None):
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_BLACKBOX_PATH", "").strip():
            destino = Path(os.environ["YUKI_BLACKBOX_PATH"].strip())
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            destino = Path(db_path).parent / "bitacora.jsonl"
        self.path = destino
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -- Lectura ---------------------------------------------------------

    def _lineas(self) -> Iterator[str]:
        if not self.path.is_file():
            return iter(())
        return iter(self.path.read_text(encoding="utf-8").splitlines())

    def entries(self, limite: Optional[int] = None) -> List[Entrada]:
        entradas = [e for e in (Entrada.from_line(l) for l in self._lineas() if l.strip())
                    if e is not None]
        return entradas[-limite:] if limite else entradas

    def head(self) -> str:
        """Hash de la última anotación, o el génesis si la bitácora está vacía."""
        entradas = self.entries()
        return entradas[-1].hash if entradas else GENESIS

    def seal(self) -> Dict[str, Any]:
        """
        Precinto: la cabeza de la cadena en este instante.

        Se guarda **fuera** de la instancia —viaja en la copia diaria— porque es
        lo único que detecta el corte por detrás: una cadena truncada sigue
        siendo internamente coherente, y sólo un precinto anterior demuestra que
        faltan eslabones.
        """
        entradas = self.entries()
        return {
            "head": entradas[-1].hash if entradas else GENESIS,
            "seq": entradas[-1].seq if entradas else 0,
            "entradas": len(entradas),
            "sellado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    # -- Escritura -------------------------------------------------------

    def record(self, op: str, detail: Optional[Dict[str, Any]] = None,
               actor: str = "sistema") -> Entrada:
        """Anota un acto. Nunca lanza: perder la bitácora no puede tumbar a Yuki."""
        with self._lock:
            entradas = self.entries()
            anterior = entradas[-1] if entradas else None
            entrada = Entrada(
                seq=(anterior.seq + 1) if anterior else 1,
                at=time.time(),
                op=str(op)[:80],
                actor=str(actor)[:80],
                detail=_limpiar(detail or {}),
                prev=anterior.hash if anterior else GENESIS,
                hash="",
            )
            entrada.hash = entrada.calcular_hash()
            try:
                with open(self.path, "a", encoding="utf-8") as fichero:
                    fichero.write(entrada.to_line() + "\n")
            except OSError as exc:
                logger.error("No se pudo escribir en la bitácora: %s", exc)
            return entrada

    # -- Verificación ----------------------------------------------------

    def verify(self, seal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Recorre la cadena y dice si alguien la tocó, y dónde.

        Tres formas de romperla, y las tres se detectan:
        · **Editar** una anotación: su hash deja de corresponder a su cuerpo.
        · **Quitar o insertar** en medio: el `prev` del siguiente no cuadra.
        · **Cortar por detrás**: la cadena queda coherente, pero no contiene el
          precinto anterior. Por eso `verify` admite uno.
        """
        entradas = self.entries()
        problemas: List[Dict[str, Any]] = []
        anterior_hash = GENESIS
        esperado_seq = 1

        for entrada in entradas:
            if entrada.calcular_hash() != entrada.hash:
                problemas.append({"seq": entrada.seq, "fallo": "contenido alterado",
                                  "detalle": "el hash no corresponde a la anotación"})
            if entrada.prev != anterior_hash:
                problemas.append({"seq": entrada.seq, "fallo": "cadena rota",
                                  "detalle": "no engancha con la anotación anterior"})
            if entrada.seq != esperado_seq:
                problemas.append({"seq": entrada.seq, "fallo": "salto de numeración",
                                  "detalle": f"se esperaba {esperado_seq}"})
            anterior_hash = entrada.hash
            esperado_seq = entrada.seq + 1

        truncada = False
        if seal:
            sellados = {e.hash for e in entradas}
            if seal.get("head") not in sellados and seal.get("head") != GENESIS:
                truncada = True
                problemas.append({
                    "seq": seal.get("seq"), "fallo": "cadena truncada",
                    "detalle": "el precinto anterior ya no está en la cadena: "
                               "alguien cortó por detrás",
                })
            elif len(entradas) < int(seal.get("entradas", 0)):
                truncada = True
                problemas.append({"seq": seal.get("seq"), "fallo": "cadena truncada",
                                  "detalle": "hay menos anotaciones que en el precinto"})

        ilegibles = sum(1 for l in self._lineas() if l.strip() and Entrada.from_line(l) is None)
        if ilegibles:
            problemas.append({"seq": None, "fallo": "líneas ilegibles",
                              "detalle": f"{ilegibles} línea(s) no son anotaciones válidas"})

        return {
            "integra": not problemas,
            "entradas": len(entradas),
            "cabeza": anterior_hash,
            "truncada": truncada,
            "problemas": problemas,
        }
