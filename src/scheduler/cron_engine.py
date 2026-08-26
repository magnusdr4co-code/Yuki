"""
Motor de Programación Cron Nativo para Hermes Agent en Yuki.
Permite presencia autónoma 24/7 sin intervención manual.
"""

import asyncio
import logging
from typing import Dict, Any, Callable, List
from datetime import datetime

logger = logging.getLogger("Yuki.CronEngine")

class CronEngine:
    def __init__(self, timezone: str = "Europe/Madrid"):
        self.timezone = timezone
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._task: asyncio.Task = None

    def register_job(self, name: str, cron_expr: str, func: Callable, enabled: bool = True):
        """Registra una tarea cron."""
        self.jobs[name] = {
            "cron_expr": cron_expr,
            "func": func,
            "enabled": enabled,
            "last_run": None,
            "run_count": 0
        }
        logger.info(f"Tarea cron registrada: [{name}] con expresión '{cron_expr}' (Habilitada: {enabled})")

    async def start(self):
        """Inicia el bucle de verificación de cron."""
        self._running = True
        logger.info("Motor Cron de Yuki iniciado (Presencia Autónoma 24/7).")
        while self._running:
            await self._tick()
            await asyncio.sleep(30) # Comprobación cada 30 segundos

    def stop(self):
        self._running = False
        logger.info("Motor Cron de Yuki detenido.")

    async def _tick(self):
        now = datetime.now()
        current_minute = now.minute
        current_hour = now.hour

        for name, job in self.jobs.items():
            if not job["enabled"]:
                continue
            
            expr = job["cron_expr"].split()
            if len(expr) == 5:
                minute_match = expr[0] == "*" or int(expr[0]) == current_minute
                hour_match = expr[1] == "*" or int(expr[1]) == current_hour
                
                # Prevenir ejecuciones múltiples en el mismo minuto
                if minute_match and hour_match:
                    last_run = job["last_run"]
                    if not last_run or (now - last_run).total_seconds() > 60:
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
