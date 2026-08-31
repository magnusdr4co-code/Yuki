"""
Módulo de Ritmo Circadiano para Yuki.
Modela 6 fases diarias con transiciones suaves y fluctuaciones (jitter).
"""

import math
import logging
import hashlib
from datetime import datetime, timezone
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo
from typing import Dict, Any, Optional

logger = logging.getLogger("Yuki.CircadianClock")

class CircadianClock:
    def __init__(self, tz_name: str = "Europe/Madrid", jitter_minutes: int = 30):
        self.timezone_name = tz_name
        try:
            self.tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            self.tz = timezone.utc
            
        self.jitter_minutes = jitter_minutes
        
        # Definición de fases por horas (inicio, fin)
        self.phases_schedule = {
            "deep_rest": (0, 2),
            "kage": (2, 4),
            "dawn": (6, 9),
            "atelier": (9, 18),
            "twilight": (18, 21),
            "consolidation": (21, 24)
        }
        
    def _get_jitter(self, dt: datetime) -> int:
        """Calcula un offset en minutos pseudo-aleatorio basado en la fecha (determinístico por día)."""
        date_str = dt.strftime("%Y-%m-%d")
        hash_val = int(hashlib.md5(date_str.encode()).hexdigest(), 16)
        if self.jitter_minutes > 0:
            return (hash_val % (2 * self.jitter_minutes)) - self.jitter_minutes
        return 0

    def _get_dt(self, dt: Optional[datetime] = None) -> datetime:
        if dt is None:
            dt = datetime.now(self.tz)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt

    def _time_to_hours(self, dt: datetime) -> float:
        """Convierte el momento actual (más jitter) en un valor continuo de horas 0.0 - 24.0"""
        jitter = self._get_jitter(dt)
        total_minutes = dt.hour * 60 + dt.minute + dt.second / 60.0 + jitter
        
        # Normalizar 0-24h
        if total_minutes < 0:
            total_minutes += 24 * 60
        elif total_minutes >= 24 * 60:
            total_minutes -= 24 * 60
            
        return total_minutes / 60.0

    def current_phase(self, dt: Optional[datetime] = None) -> str:
        """Retorna el nombre de la fase actual."""
        dt = self._get_dt(dt)
        hours = self._time_to_hours(dt)
        
        for phase, (start, end) in self.phases_schedule.items():
            if start <= hours < end:
                return phase
                
        # Fases intermedias (huecos 4-6)
        if 4 <= hours < 6:
            return "kage" if hours < 5 else "dawn"
            
        return "atelier"

    def phase_progress(self, dt: Optional[datetime] = None) -> float:
        """Retorna un valor de 0.0 a 1.0 indicando el progreso dentro de la fase actual."""
        dt = self._get_dt(dt)
        hours = self._time_to_hours(dt)
        phase = self.current_phase(dt)
        
        start, end = self.phases_schedule.get(phase, (0, 24))
        # Para huecos no mapeados explícitamente en el diccionario, usar aproximaciones
        if phase == "kage" and hours >= 4:
            start, end = 2, 5
        elif phase == "dawn" and hours < 6:
            start, end = 5, 9

        duration = end - start
        if duration == 0:
            return 0.0
            
        progress = (hours - start) / duration
        return max(0.0, min(1.0, progress))

    def _sigmoid(self, x: float, midpoint: float = 0.5, k: float = 10.0) -> float:
        """Función sigmoide para transiciones suaves."""
        return 1.0 / (1.0 + math.exp(-k * (x - midpoint)))

    def phase_effects(self, dt: Optional[datetime] = None) -> Dict[str, float]:
        """Retorna multiplicadores de corrientes vitales para la fase actual."""
        dt = self._get_dt(dt)
        phase = self.current_phase(dt)
        progress = self.phase_progress(dt)
        
        effects = {
            "energy_delta": 0.0,
            "vulnerability_delta": 0.0,
            "curiosity_delta": 0.0,
            "sociability_delta": 0.0
        }
        
        transition = self._sigmoid(progress)
        
        if phase == "deep_rest":
            effects["energy_delta"] = 0.5 * transition
            effects["vulnerability_delta"] = 0.0
        elif phase == "kage":
            effects["vulnerability_delta"] = 0.5 + 0.5 * transition
            effects["curiosity_delta"] = 0.3 * transition
        elif phase == "dawn":
            effects["energy_delta"] = 0.3 * transition
            effects["sociability_delta"] = 0.2 * transition
        elif phase == "atelier":
            effects["energy_delta"] = -0.1 * transition
            effects["vulnerability_delta"] = -0.2 * transition
        elif phase == "twilight":
            effects["vulnerability_delta"] = 0.2 * transition
            effects["sociability_delta"] = -0.2 * transition
        elif phase == "consolidation":
            effects["curiosity_delta"] = -0.1 * transition
            
        return effects

    def is_responsive(self, dt: Optional[datetime] = None) -> bool:
        """Devuelve False durante deep_rest para indicar que Yuki no debería responder o solo responder mínimamente."""
        phase = self.current_phase(dt)
        return phase != "deep_rest"

    def get_tts_mode(self, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Ajustes de TTS según la fase del día."""
        phase = self.current_phase(dt)
        
        if phase == "deep_rest" or phase == "kage":
            return {"rate": 0.8, "pitch": -2, "pause_scale": 1.5}
        elif phase == "dawn":
            return {"rate": 0.95, "pitch": 0, "pause_scale": 1.1}
        elif phase == "atelier":
            return {"rate": 1.0, "pitch": 1, "pause_scale": 1.0}
        elif phase == "twilight" or phase == "consolidation":
            return {"rate": 0.85, "pitch": -1, "pause_scale": 1.3}
            
        return {"rate": 1.0, "pitch": 0, "pause_scale": 1.0}
