"""
Motor de Programación Cron Nativo para Hermes Agent en Yuki.
Permite presencia autónoma 24/7 sin intervención manual.

Soporta la sintaxis cron estándar de 5 campos:
    minuto  hora  día-del-mes  mes  día-de-la-semana

Cada campo admite `*`, valores sueltos (`30`), listas (`0,15,30`),
rangos (`9-18`) y pasos (`*/20`, `9-18/2`).
"""

import asyncio
import logging
import random
from typing import Dict, Any, Callable, List, Optional, Set
from datetime import datetime, timezone as dt_timezone

try:
    import zoneinfo
except ImportError:  # pragma: no cover - Python < 3.9
    from backports import zoneinfo

logger = logging.getLogger("Yuki.CronEngine")

# (nombre, mínimo, máximo) para cada uno de los 5 campos cron
FIELD_BOUNDS = [
    ("minuto", 0, 59),
    ("hora", 0, 23),
    ("día del mes", 1, 31),
    ("mes", 1, 12),
    ("día de la semana", 0, 6),
]


class CronParseError(ValueError):
    """Expresión cron inválida."""


def _parse_field(field: str, min_val: int, max_val: int, field_name: str) -> Set[int]:
    """
    Expande un único campo cron al conjunto de valores que lo satisfacen.
    Acepta `*`, `a`, `a-b`, `a,b,c`, `*/n` y `a-b/n`.
    """
    field = field.strip()
    if not field:
        raise CronParseError(f"Campo '{field_name}' vacío.")

    allowed: Set[int] = set()

    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronParseError(f"Elemento vacío en el campo '{field_name}'.")

        base, sep, step_raw = part.partition("/")
        step = 1
        if sep:
            try:
                step = int(step_raw)
            except ValueError:
                raise CronParseError(
                    f"Paso no numérico '{step_raw}' en el campo '{field_name}'."
                )
            if step < 1:
                raise CronParseError(
                    f"El paso debe ser >= 1 en el campo '{field_name}' (recibido {step})."
                )

        base = base.strip()
        if base == "*":
            start, end = min_val, max_val
        elif "-" in base:
            start_raw, _, end_raw = base.partition("-")
            try:
                start, end = int(start_raw), int(end_raw)
            except ValueError:
                raise CronParseError(
                    f"Rango inválido '{base}' en el campo '{field_name}'."
                )
            if start > end:
                raise CronParseError(
                    f"Rango invertido '{base}' en el campo '{field_name}'."
                )
        else:
            try:
                start = end = int(base)
            except ValueError:
                raise CronParseError(
                    f"Valor no numérico '{base}' en el campo '{field_name}'."
                )

        # El domingo se escribe indistintamente como 0 o como 7.
        if field_name == "día de la semana":
            start = 0 if start == 7 else start
            end = 0 if end == 7 else end
            if start > end:
                start, end = end, start

        if start < min_val or end > max_val:
            raise CronParseError(
                f"Valor fuera de rango en el campo '{field_name}': "
                f"'{part}' no está entre {min_val} y {max_val}."
            )

        allowed.update(range(start, end + 1, step))

    return allowed


def parse_cron_expression(cron_expr: str) -> List[Set[int]]:
    """
    Convierte una expresión cron de 5 campos en una lista de 5 conjuntos de
    valores permitidos. Lanza CronParseError si la expresión es inválida.
    """
    if not cron_expr or not cron_expr.strip():
        raise CronParseError("Expresión cron vacía.")

    fields = cron_expr.split()
    if len(fields) != 5:
        raise CronParseError(
            f"La expresión cron '{cron_expr}' tiene {len(fields)} campos; se esperaban 5."
        )

    return [
        _parse_field(raw, low, high, name)
        for raw, (name, low, high) in zip(fields, FIELD_BOUNDS)
    ]


def cron_matches(parsed: List[Set[int]], moment: datetime) -> bool:
    """
    Comprueba si un instante satisface una expresión cron ya parseada.

    Siguiendo la semántica de cron estándar, cuando tanto el día del mes como
    el día de la semana están restringidos, basta con que se cumpla uno de los dos.
    """
    minutes, hours, days_of_month, months, days_of_week = parsed

    if moment.minute not in minutes or moment.hour not in hours or moment.month not in months:
        return False

    # datetime.weekday() es lunes=0..domingo=6; cron usa domingo=0..sábado=6.
    cron_dow = (moment.weekday() + 1) % 7
    dom_restricted = len(days_of_month) < 31
    dow_restricted = len(days_of_week) < 7

    dom_match = moment.day in days_of_month
    dow_match = cron_dow in days_of_week

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    return dom_match and dow_match


class CronEngine:
    def __init__(self, timezone: str = "Europe/Madrid", tick_seconds: int = 30):
        self.timezone = timezone
        try:
            self.tz = zoneinfo.ZoneInfo(timezone)
        except Exception:
            logger.warning(
                f"Zona horaria '{timezone}' no reconocida; se usará UTC para el planificador."
            )
            self.tz = dt_timezone.utc

        self.tick_seconds = tick_seconds
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._task: asyncio.Task = None

    def now(self) -> datetime:
        """Instante actual en la zona horaria del planificador."""
        return datetime.now(self.tz)

    def register_job(self, name: str, cron_expr: str, func: Callable, enabled: bool = True,
                     fire_condition: Optional[Callable[[], bool]] = None, jitter_minutes: int = 0,
                     probability: float = 1.0):
        """
        Registra una tarea cron.

        La expresión se valida aquí: una expresión inválida falla al arrancar,
        en lugar de tumbar el bucle autónomo horas más tarde.
        """
        parsed = parse_cron_expression(cron_expr)

        self.jobs[name] = {
            "cron_expr": cron_expr,
            "parsed": parsed,
            "func": func,
            "enabled": enabled,
            "last_run": None,
            "run_count": 0,
            "fire_condition": fire_condition,
            "jitter_minutes": jitter_minutes,
            "probability": probability
        }
        logger.info(f"Tarea cron registrada: [{name}] con expresión '{cron_expr}' (Habilitada: {enabled})")

    async def start(self):
        """Inicia el bucle de verificación de cron."""
        self._running = True
        logger.info(
            f"Motor Cron de Yuki iniciado (Presencia Autónoma 24/7, zona horaria {self.timezone})."
        )
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # El latido nunca debe morir: una tarea rota no puede silenciar a Yuki.
                logger.error(f"Error inesperado en el tick del motor cron: {e}", exc_info=True)
            await asyncio.sleep(self.tick_seconds)

    def stop(self):
        self._running = False
        logger.info("Motor Cron de Yuki detenido.")

    def _should_fire(self, name: str, job: Dict[str, Any], now: datetime) -> bool:
        """Decide si una tarea concreta debe dispararse en este instante."""
        if not job["enabled"]:
            return False

        moment = now
        if job.get("jitter_minutes"):
            jitter = hash(name + now.strftime('%Y-%m-%d')) % (2 * job["jitter_minutes"] + 1) - job["jitter_minutes"]
            moment = now.replace(minute=(now.minute - jitter) % 60)

        if not cron_matches(job["parsed"], moment):
            return False

        # Evitar disparos duplicados dentro del mismo minuto (el tick es más rápido que un minuto).
        last_run = job["last_run"]
        if last_run and last_run.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
            return False

        if job.get("fire_condition") and not job["fire_condition"]():
            return False

        if random.random() >= job.get("probability", 1.0):
            logger.info(f"Saltando tarea cron [{name}] por probabilidad.")
            return False

        return True

    async def _tick(self):
        now = self.now()

        for name, job in list(self.jobs.items()):
            try:
                if not self._should_fire(name, job, now):
                    continue
            except Exception as e:
                logger.error(f"Error evaluando la tarea cron [{name}]: {e}", exc_info=True)
                continue

            logger.info(f"⚡ Disparando tarea autónoma: [{name}]")
            job["last_run"] = now
            job["run_count"] += 1
            try:
                if asyncio.iscoroutinefunction(job["func"]):
                    await job["func"]()
                else:
                    job["func"]()
            except Exception as e:
                logger.error(f"Error en tarea cron [{name}]: {e}", exc_info=True)

    async def trigger_manually(self, name: str) -> Any:
        """Permite disparar una tarea inmediatamente para pruebas."""
        if name in self.jobs:
            job = self.jobs[name]
            logger.info(f"Disparo manual de tarea: [{name}]")
            if asyncio.iscoroutinefunction(job["func"]):
                return await job["func"]()
            else:
                return job["func"]()
        raise ValueError(f"Tarea cron '{name}' no encontrada.")
