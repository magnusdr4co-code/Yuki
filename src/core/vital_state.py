"""
Módulo de Estado Vital (Corrientes Vitales) para Yuki.
Modela 6 corrientes internas como flotantes continuos entre 0.0 y 1.0.
"""

import os
import json
import math
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("Yuki.VitalState")

class VitalState:
    def __init__(self, state_path: str = "data/vital_state.json"):
        self.state_path = state_path
        
        # Corrientes vitales (0.0 a 1.0)
        self.energy: float = 0.75
        self.mood: float = 0.60
        self.curiosity: float = 0.50
        self.vulnerability: float = 0.30
        self.sociability: float = 0.65
        self.inspiration: float = 0.20
        
        # Metadatos
        self.last_updated: str = datetime.now().isoformat()
        self.circadian_phase: str = "atelier"
        self.accumulated_interactions_today: int = 0
        self.accumulated_creations_today: int = 0
        self.last_sleep_cycle: Optional[str] = None
        self.last_echo_ritual: Optional[str] = None
        self.will_queue: list = []
        
        # Cargar estado si existe
        self.load()

    def update_tick(self, phase: str, dt_seconds: float):
        """Actualiza las dinámicas naturales según la fase y tiempo transcurrido."""
        self.circadian_phase = phase
        hours = dt_seconds / 3600.0
        
        # Oscilación orgánica del humor (mood) con ruidos Perlin-like
        t = datetime.now().timestamp() / 3600.0
        phi = 1.6180339887  # Proporción áurea
        sq2 = 1.4142135623  # Raíz de 2
        
        oscillation = (math.sin(t) + math.sin(t * phi) + math.sin(t * sq2)) / 3.0
        self.mood = max(0.0, min(1.0, self.mood + oscillation * 0.02 * hours))
        
        # Decaimiento de energía
        if phase in ["atelier", "dawn", "twilight"]:
            self.energy = max(0.0, self.energy - 0.05 * hours)
        elif phase == "deep_rest":
            self.energy = min(1.0, self.energy + 0.2 * hours)
            
        # Aumento de curiosidad con inactividad
        self.curiosity = min(1.0, self.curiosity + 0.03 * hours)
        
        # Acumulación de inspiración por contemplación
        if phase in ["kage", "consolidation"]:
            self.inspiration = min(1.0, self.inspiration + 0.04 * hours)
            
        self.last_updated = datetime.now().isoformat()
        
    def apply_stimulus(self, stimulus_type: str, intensity: float):
        """Modifica las corrientes basado en eventos externos."""
        intensity = max(0.0, min(1.0, intensity))
        
        if stimulus_type == "deep_conversation":
            self.sociability = min(1.0, self.sociability + 0.1 * intensity)
            self.inspiration = min(1.0, self.inspiration + 0.05 * intensity)
            self.energy = max(0.0, self.energy - 0.05 * intensity)
            self.accumulated_interactions_today += 1
        elif stimulus_type == "creative_output":
            self.inspiration = 0.0  # Se vacía tras el acto creativo
            self.energy = max(0.0, self.energy - 0.15 * intensity)
            self.accumulated_creations_today += 1
        elif stimulus_type == "trend_search":
            self.curiosity = max(0.0, self.curiosity - 0.2 * intensity)
            self.energy = max(0.0, self.energy - 0.02 * intensity)
        elif stimulus_type == "positive_interaction":
            self.sociability = min(1.0, self.sociability + 0.15 * intensity)
            self.mood = min(1.0, self.mood + 0.1 * intensity)
            self.accumulated_interactions_today += 1
        elif stimulus_type == "silence":
            self.vulnerability = min(1.0, self.vulnerability + 0.05 * intensity)
            self.energy = min(1.0, self.energy + 0.02 * intensity)

    def inspiration_ready(self) -> bool:
        """Verdadero si la inspiración cruzó el umbral."""
        return self.inspiration >= 0.72

    def has_energy_for(self, cost: float) -> bool:
        """Verdadero si la energía es mayor o igual al coste."""
        return self.energy >= cost

    def spend_energy(self, amount: float):
        """Deduce energía."""
        self.energy = max(0.0, self.energy - amount)

    def save(self):
        """Persistencia JSON."""
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self):
        """Carga persistencia JSON."""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(self, k):
                            setattr(self, k, v)
            except Exception as e:
                logger.error(f"Error loading state from {self.state_path}: {e}")

    def to_natural_language(self) -> str:
        """Convierte el estado a una descripción poética para inyección en el prompt."""
        desc = []
        if self.energy > 0.8:
            desc.append("Siento un aliento vigoroso, listo para el mundo.")
        elif self.energy < 0.3:
            desc.append("Mis reservas merman; anhelo la quietud.")
            
        if self.mood > 0.7:
            desc.append("Mi clima interior es sereno y claro.")
        elif self.mood < 0.3:
            desc.append("Hay cierta pesadumbre en mi paisaje emocional.")
            
        if self.curiosity > 0.7:
            desc.append("Siento avidez por absorber nuevas ideas.")
            
        if self.inspiration_ready():
            desc.append("Una chispa creativa me presiona; necesito expresarme.")
            
        return " ".join(desc) if desc else "Fluyo en equilibrio neutro."

    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario."""
        return {
            "energy": self.energy,
            "mood": self.mood,
            "curiosity": self.curiosity,
            "vulnerability": self.vulnerability,
            "sociability": self.sociability,
            "inspiration": self.inspiration,
            "last_updated": self.last_updated,
            "circadian_phase": self.circadian_phase,
            "accumulated_interactions_today": self.accumulated_interactions_today,
            "accumulated_creations_today": self.accumulated_creations_today,
            "last_sleep_cycle": self.last_sleep_cycle,
            "last_echo_ritual": self.last_echo_ritual,
            "will_queue": self.will_queue
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VitalState':
        """Crea una instancia desde un diccionario."""
        state = cls()
        for k, v in data.items():
            if hasattr(state, k):
                setattr(state, k, v)
        return state
