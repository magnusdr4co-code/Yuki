"""
Freno de mano: parar a Yuki sin matarla.

Hoy, si algo va mal —un bucle de encargos, una respuesta que no debería estar
saliendo, una factura que sube sola—, la única forma de detenerla es parar el
contenedor. Eso funciona, y es pésimo: se lleva por delante el Salón, corta los
trabajos multimedia a mitad, y deja a quien lo hizo sin saber si al arrancar de
nuevo va a repetirse lo mismo.

Un agente que actúa solo necesita un freno que se pueda accionar en un segundo,
que no requiera desplegar nada y que sea **graduado**: casi nunca hace falta
apagarlo todo. Aquí hay cuatro posiciones, y cada una contiene a la anterior:

  · `ninguno`      — Yuki funciona con normalidad.
  · `publicacion`  — sigue pensando y creando, pero no publica hacia fuera.
  · `medios`       — además, no gasta un céntimo en imagen, vídeo, música ni voz.
  · `todo`         — además, no emprende nada por su cuenta. Sigue respondiendo
                     a quien le hable: enmudecerla no es frenarla, es romperla.

Dos decisiones que importan:

**La variable de entorno manda sobre el fichero.** En un incidente, la palanca
más rápida es `docker run -e YUKI_FRENO=todo` o editar el env de la VM y
reiniciar; si el fichero pudiera contradecirla, alguien podría soltar el freno
sin querer con un comando de DM. El entorno es del operador; el fichero, del
Productor.

**El freno no puede desaparecer solo.** Admite caducidad explícita —«medios
durante dos horas»— pero sin ella se queda puesto hasta que alguien lo suelte.
Un freno que se olvida es peor que no tenerlo, porque enseña a confiar en él.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("Yuki.Freno")

NINGUNO = "ninguno"
PUBLICACION = "publicacion"
MEDIOS = "medios"
TODO = "todo"

# Orden de contención: cada nivel incluye lo que frena el anterior.
NIVELES = {NINGUNO: 0, PUBLICACION: 1, MEDIOS: 2, TODO: 3}

# Qué nivel basta para frenar cada tipo de acto.
FRENA_A_PARTIR_DE = {
    "publicar": NIVELES[PUBLICACION],
    "medios": NIVELES[MEDIOS],
    "iniciativa": NIVELES[TODO],
}

VARIABLE_ENTORNO = "YUKI_FRENO"


@dataclass
class EstadoFreno:
    nivel: str = NINGUNO
    motivo: str = ""
    actor: str = ""
    desde: Optional[float] = None
    hasta: Optional[float] = None
    origen: str = "ninguno"     # entorno | fichero | ninguno

    @property
    def activo(self) -> bool:
        return NIVELES.get(self.nivel, 0) > 0

    def to_dict(self) -> Dict[str, Any]:
        datos = {"nivel": self.nivel, "motivo": self.motivo, "actor": self.actor,
                 "origen": self.origen, "activo": self.activo}
        if self.desde:
            datos["desde"] = datetime.fromtimestamp(self.desde, timezone.utc).isoformat(timespec="seconds")
        if self.hasta:
            datos["hasta"] = datetime.fromtimestamp(self.hasta, timezone.utc).isoformat(timespec="seconds")
            datos["minutos_restantes"] = max(0, round((self.hasta - time.time()) / 60, 1))
        return datos


class Brake:
    """El freno, con su estado persistente y su palanca de entorno."""

    def __init__(self, path: Optional[str] = None, blackbox: Any = None):
        if path:
            destino = Path(path)
        elif os.getenv("YUKI_FRENO_PATH", "").strip():
            destino = Path(os.environ["YUKI_FRENO_PATH"].strip())
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            destino = Path(db_path).parent / "freno.json"
        self.path = destino
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._blackbox = blackbox

    # -- Estado ----------------------------------------------------------

    def _del_entorno(self) -> Optional[EstadoFreno]:
        crudo = (os.getenv(VARIABLE_ENTORNO) or "").strip().lower()
        if not crudo or crudo in ("0", "no", "off", NINGUNO):
            return None
        if crudo in ("1", "si", "sí", "on", "true"):
            crudo = TODO
        if crudo not in NIVELES:
            logger.warning("%s='%s' no es un nivel de freno; se ignora.", VARIABLE_ENTORNO, crudo)
            return None
        return EstadoFreno(nivel=crudo, motivo="palanca de entorno", actor="operador",
                           origen="entorno")

    def _del_fichero(self) -> Optional[EstadoFreno]:
        if not self.path.is_file():
            return None
        try:
            datos = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Un freno ilegible se interpreta como puesto: ante la duda, se
            # frena. Lo contrario sería soltarlo por un fichero corrupto.
            logger.warning("Freno ilegible; se asume puesto al máximo por prudencia.")
            return EstadoFreno(nivel=TODO, motivo="fichero de freno ilegible",
                               actor="sistema", origen="fichero")
        nivel = str(datos.get("nivel", NINGUNO))
        if nivel not in NIVELES or nivel == NINGUNO:
            return None
        hasta = datos.get("hasta")
        if hasta and time.time() > float(hasta):
            return None    # caducó; el estado se limpia al siguiente cambio
        return EstadoFreno(nivel=nivel, motivo=str(datos.get("motivo", "")),
                           actor=str(datos.get("actor", "")), desde=datos.get("desde"),
                           hasta=hasta, origen="fichero")

    def state(self) -> EstadoFreno:
        """
        El freno efectivo. El entorno gana siempre.

        Si ambos están puestos, manda el más restrictivo de los dos: en un
        incidente nadie quiere descubrir que su palanca quedó por debajo de la
        que alguien había dejado en el fichero.
        """
        entorno = self._del_entorno()
        fichero = self._del_fichero()
        if entorno and fichero:
            return entorno if NIVELES[entorno.nivel] >= NIVELES[fichero.nivel] else fichero
        return entorno or fichero or EstadoFreno()

    def permits(self, accion: str) -> bool:
        """Si el freno actual deja pasar este tipo de acto."""
        umbral = FRENA_A_PARTIR_DE.get(accion)
        if umbral is None:
            return True
        return NIVELES.get(self.state().nivel, 0) < umbral

    def blocked_reason(self, accion: str) -> Optional[str]:
        """Explicación para quien reciba el «no». Un freno mudo parece una avería."""
        if self.permits(accion):
            return None
        estado = self.state()
        detalle = f" ({estado.motivo})" if estado.motivo else ""
        caducidad = ""
        if estado.hasta:
            restantes = max(0, round((estado.hasta - time.time()) / 60))
            caducidad = f"; se suelta solo en {restantes} min"
        return (f"freno de mano en «{estado.nivel}»{detalle}, puesto por "
                f"{estado.actor or 'alguien'} desde {estado.origen}{caducidad}")

    # -- Palanca ---------------------------------------------------------

    def engage(self, nivel: str, motivo: str = "", actor: str = "productor",
               minutos: Optional[float] = None) -> EstadoFreno:
        nivel = (nivel or "").strip().lower()
        if nivel not in NIVELES or nivel == NINGUNO:
            raise ValueError(f"Nivel de freno no válido: '{nivel}'. "
                             f"Usa: {', '.join(n for n in NIVELES if n != NINGUNO)}.")
        ahora = time.time()
        estado = {
            "nivel": nivel, "motivo": (motivo or "")[:240], "actor": actor,
            "desde": ahora, "hasta": (ahora + minutos * 60) if minutos else None,
        }
        temporal = self.path.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self.path)
        self._anotar("freno_puesto", estado)
        logger.warning("FRENO puesto en '%s' por %s: %s", nivel, actor, motivo or "sin motivo")
        return self.state()

    def release(self, actor: str = "productor", motivo: str = "") -> EstadoFreno:
        anterior = self._del_fichero()
        estado = {"nivel": NINGUNO, "motivo": (motivo or "")[:240], "actor": actor,
                  "desde": time.time(), "hasta": None}
        temporal = self.path.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self.path)
        self._anotar("freno_soltado", {**estado, "nivel_anterior": anterior.nivel if anterior else NINGUNO})
        logger.warning("FRENO soltado por %s", actor)
        # El entorno puede seguir frenando aunque el fichero se suelte, y eso
        # tiene que verse: soltar y que no pase nada desconcierta a quien lo hace.
        return self.state()

    def _anotar(self, operacion: str, detalle: Dict[str, Any]) -> None:
        try:
            caja = self._blackbox
            if caja is None:
                from .blackbox import BlackBox

                caja = BlackBox()
            caja.record(operacion, detalle, actor=str(detalle.get("actor", "sistema")))
        except Exception:
            logger.warning("No se pudo anotar el freno en la bitácora")

    # -- Informe ---------------------------------------------------------

    def describe(self) -> str:
        estado = self.state()
        if not estado.activo:
            return "Sin freno: Yuki funciona con normalidad."
        permisos = ", ".join(
            f"{accion}: {'sí' if self.permits(accion) else 'NO'}"
            for accion in ("publicar", "medios", "iniciativa"))
        return (f"Freno en «{estado.nivel}» desde {estado.origen}"
                + (f" ({estado.motivo})" if estado.motivo else "")
                + f". Puede → {permisos}.")
