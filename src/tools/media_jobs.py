"""
Cola durable de trabajos multimedia.

El límite documentado en `docs/PRODUCTION_STATUS.md` era éste: la producción de
canción y vídeo vivía sólo en memoria del daemon, así que un reinicio —un
despliegue, un OOM, el mantenimiento de la VM— cortaba el trabajo y no dejaba
forma de reanudarlo. El Productor veía un acuse de inicio y después nada.

Aquí el trabajo se escribe en disco antes de gastar un solo segundo de vídeo, y
cada paso guarda su resultado en cuanto existe. Reanudar es volver a recorrer
los pasos: los que ya tienen fichero verificado no se regeneran, y eso importa
en dinero, porque Veo se factura por segundo. Nada de esto promete trabajo
futuro: si un paso falló, queda registrado como fallo con su motivo.

No se guardan secretos ni contenido de usuario: sólo identificadores, rutas
dentro de `output/` y el texto de la orden ya recortado, que es lo que permite
reanudar sin volver a preguntar.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Yuki.MediaJobs")

# Estados de un paso. Se nombran en español como el resto del canon.
PENDIENTE = "pendiente"
HECHO = "hecho"
FALLIDO = "fallido"

# Estados del trabajo completo.
EN_CURSO = "en-curso"
TERMINADO = "terminado"
ABANDONADO = "abandonado"

# Un paso que ha fallado esto muchas veces no se reintenta al reanudar: si Veo
# devuelve el mismo error tras tres arranques, insistir sólo quema crédito.
MAX_INTENTOS_POR_PASO = 3

# Recorte de la orden original. Sirve para reanudar y para el registro; no es
# un archivo de conversación.
MAX_ORDEN_CARACTERES = 2000


def _ahora() -> int:
    return int(time.time())


@dataclass
class MediaStep:
    """Un paso facturable e idempotente del trabajo."""

    id: str
    kind: str                      # cancion | clip | montaje | entrega
    status: str = PENDIENTE
    path: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    delivered: bool = False
    # Qué es exactamente el fichero producido. Importa cuando un paso puede
    # resolverse por dos caminos distintos —Lyria canta; el respaldo local no—,
    # porque la entrega no debe llamar canción a una maqueta instrumental.
    note: Optional[str] = None
    updated_at: int = field(default_factory=_ahora)

    def is_done(self) -> bool:
        """Hecho **y** con el fichero todavía presente; si no, hay que rehacerlo."""
        if self.status != HECHO:
            return False
        if self.kind == "entrega":
            return True
        return bool(self.path) and Path(self.path).is_file()

    def exhausted(self) -> bool:
        return self.attempts >= MAX_INTENTOS_POR_PASO and not self.is_done()

    def mark_done(self, path: Optional[str] = None, note: Optional[str] = None) -> None:
        self.status = HECHO
        self.path = path or self.path
        self.note = note or self.note
        self.error = None
        self.updated_at = _ahora()

    def mark_failed(self, error: str) -> None:
        self.status = FALLIDO
        self.error = (error or "sin detalle")[:400]
        self.updated_at = _ahora()


@dataclass
class MediaJob:
    """Un encargo de producción multimedia del Productor emparejado."""

    id: str
    requester_id: str
    channel_id: Optional[str]
    order: str
    steps: List[MediaStep] = field(default_factory=list)
    status: str = EN_CURSO
    created_at: int = field(default_factory=_ahora)
    updated_at: int = field(default_factory=_ahora)
    resumed: int = 0

    def step(self, step_id: str) -> Optional[MediaStep]:
        return next((s for s in self.steps if s.id == step_id), None)

    def ensure_step(self, step_id: str, kind: str) -> MediaStep:
        existing = self.step(step_id)
        if existing is not None:
            return existing
        created = MediaStep(id=step_id, kind=kind)
        self.steps.append(created)
        return created

    def pending_steps(self) -> List[MediaStep]:
        return [s for s in self.steps if not s.is_done() and not s.exhausted()]

    def done_steps(self) -> List[MediaStep]:
        return [s for s in self.steps if s.is_done()]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(s) for s in self.steps]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaJob":
        campos_paso = set(MediaStep.__dataclass_fields__)
        steps = [MediaStep(**{k: v for k, v in s.items() if k in campos_paso})
                 for s in data.get("steps", []) if isinstance(s, dict)]
        campos = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "steps"}
        campos.setdefault("id", uuid.uuid4().hex[:12])
        campos.setdefault("requester_id", "")
        campos.setdefault("channel_id", None)
        campos.setdefault("order", "")
        return cls(steps=steps, **campos)


class MediaJobStore:
    """
    Persistencia atómica de trabajos multimedia.

    Un fichero JSON por trabajo bajo `data/media_jobs/`, que en producción es el
    disco persistente de la VM: sobrevive al contenedor y al despliegue. La
    escritura es `tmp` + `os.replace`, así que un corte a mitad no deja un
    trabajo ilegible.
    """

    def __init__(self, root: Optional[str] = None):
        if root:
            base = Path(root)
        else:
            db_path = os.getenv("DATABASE_PATH", "data/yuki_memory.db")
            base = Path(db_path).parent / "media_jobs"
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def create(self, requester_id: str, order: str, channel_id: Optional[str] = None,
               steps: Optional[List[tuple]] = None) -> MediaJob:
        job = MediaJob(
            id=uuid.uuid4().hex[:12],
            requester_id=str(requester_id),
            channel_id=str(channel_id) if channel_id is not None else None,
            order=(order or "")[:MAX_ORDEN_CARACTERES],
        )
        for step_id, kind in (steps or []):
            job.ensure_step(step_id, kind)
        self.save(job)
        logger.info("Trabajo multimedia %s registrado con %d pasos", job.id, len(job.steps))
        return job

    def save(self, job: MediaJob) -> None:
        job.updated_at = _ahora()
        destino = self._path(job.id)
        temporal = destino.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, destino)

    def get(self, job_id: str) -> Optional[MediaJob]:
        ruta = self._path(job_id)
        if not ruta.is_file():
            return None
        try:
            return MediaJob.from_dict(json.loads(ruta.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Trabajo %s ilegible (%s); se ignora.", job_id, type(exc).__name__)
            return None

    def list_jobs(self) -> List[MediaJob]:
        trabajos = []
        for ruta in sorted(self.root.glob("*.json")):
            trabajo = self.get(ruta.stem)
            if trabajo is not None:
                trabajos.append(trabajo)
        return trabajos

    def resumable(self, requester_id: Optional[str] = None) -> List[MediaJob]:
        """Trabajos que un reinicio dejó a medias y todavía pueden avanzar."""
        pendientes = []
        for trabajo in self.list_jobs():
            if trabajo.status != EN_CURSO:
                continue
            if requester_id is not None and trabajo.requester_id != str(requester_id):
                continue
            if not trabajo.pending_steps():
                # Nada que hacer: se cierra al vuelo para no reaparecer.
                self.finish(trabajo)
                continue
            pendientes.append(trabajo)
        return pendientes

    def finish(self, job: MediaJob, status: str = TERMINADO) -> MediaJob:
        job.status = status
        self.save(job)
        return job

    def abandon(self, job: MediaJob, reason: str) -> MediaJob:
        logger.warning("Trabajo multimedia %s abandonado: %s", job.id, reason)
        for paso in job.steps:
            if not paso.is_done() and paso.status == PENDIENTE:
                paso.mark_failed(reason)
        return self.finish(job, ABANDONADO)

    def purge(self, older_than_days: int = 14) -> int:
        """Limpia trabajos cerrados y antiguos; el disco de la VM es pequeño."""
        limite = _ahora() - older_than_days * 86400
        borrados = 0
        for trabajo in self.list_jobs():
            if trabajo.status != EN_CURSO and trabajo.updated_at < limite:
                self._path(trabajo.id).unlink(missing_ok=True)
                borrados += 1
        return borrados


def describe_job(job: MediaJob) -> str:
    """Resumen determinista para el DM: qué hay hecho y qué falta, sin promesas."""
    hechos = [s for s in job.steps if s.is_done()]
    fallidos = [s for s in job.steps if s.status == FALLIDO]
    pendientes = job.pending_steps()
    partes = [f"trabajo `{job.id}`", f"{len(hechos)}/{len(job.steps)} pasos verificados"]
    if fallidos:
        partes.append(f"{len(fallidos)} con fallo registrado")
    if pendientes:
        partes.append(f"{len(pendientes)} por ejecutar")
    return " · ".join(partes)
