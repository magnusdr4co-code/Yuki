"""
Diario de Evolución Semanal para Yuki.
Analiza y registra desplazamientos en los gustos y opiniones a lo largo del tiempo.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import json
import re

class GrowthJournal:
    def __init__(self, memory_engine: Any):
        """Recibe directamente la instancia de FTS5MemoryEngine."""
        self.engine = memory_engine

    def generate_review_prompt(self, days_back: int = 7) -> str:
        """Construye un prompt para que el LLM analice la evolución reciente."""
        time_limit = datetime.now() - timedelta(days=days_back)
        timestamp_limit = time_limit.timestamp()
        
        with self.engine._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT content, category, created_at 
                FROM memories 
                WHERE created_at >= ? AND category IN ('visitor', 'inner_thought', 'daily_synthesis')
                ORDER BY created_at ASC
            ''', (timestamp_limit,))
            rows = cursor.fetchall()
            
        history = ""
        for row in rows:
            dt = datetime.fromtimestamp(row["created_at"]).strftime("%Y-%m-%d %H:%M")
            history += f"[{dt}] ({row['category']}) {row['content']}\n"
            
        prompt = f"""
Analiza las interacciones, pensamientos internos y síntesis de la última semana de Yuki:

<historial>
{history}
</historial>

Identifica si ha habido desplazamientos o evoluciones graduales en los gustos, opiniones o posiciones de Yuki en los siguientes 4 dominios: music, aesthetics, philosophy, relationships.

Tu respuesta debe estar estrictamente formateada de la siguiente manera para cada desplazamiento identificado (si no hay, omite el dominio):

DOMAIN: [music | aesthetics | philosophy | relationships]
FROM: [Posición anterior breve, ej: "Inseguridad en su identidad musical"]
TO: [Nueva posición breve, ej: "Aceptación de sus fallos como parte de su estilo"]
CONFIDENCE: [0.0 a 1.0, nivel de certeza en la evolución]

Solo incluye desplazamientos genuinos.
"""
        return prompt.strip()

    def record_growth_event(self, domain: str, from_position: str, to_position: str, trigger_memory_ids: List[int], confidence: float):
        """Registra el evento de crecimiento en la base de datos."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        trigger_ids_str = json.dumps(trigger_memory_ids)
        self.engine.add_growth_event(
            date=date_str,
            domain=domain,
            from_pos=from_position,
            to_pos=to_position,
            trigger_ids=trigger_ids_str,
            confidence=confidence
        )

    def get_evolution_context(self, limit: int = 3) -> str:
        """Devuelve un bloque en lenguaje natural con los eventos de evolución recientes."""
        events = self.engine.get_recent_growth(limit=limit)
        if not events:
            return "No hay evolución reciente registrada."
            
        context = "Evolución reciente de Yuki:\n"
        for ev in events:
            domain_es = {
                "music": "Música",
                "aesthetics": "Estética",
                "philosophy": "Filosofía",
                "relationships": "Vínculos"
            }.get(ev["domain"], ev["domain"])
            
            context += f"- [{domain_es}] Antes: \"{ev['from_position']}\" → Ahora: \"{ev['to_position']}\" (confianza: {ev['confidence']})\n"
            
        return context

    def parse_llm_growth_response(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parsea la salida estructurada del LLM y la convierte en una lista de diccionarios."""
        events = []
        blocks = re.split(r'DOMAIN:\s*', llm_response)
        
        for block in blocks:
            if not block.strip():
                continue
            
            domain_match = re.match(r'([^\n]+)', block)
            from_match = re.search(r'FROM:\s*([^\n]+)', block)
            to_match = re.search(r'TO:\s*([^\n]+)', block)
            conf_match = re.search(r'CONFIDENCE:\s*([0-9.]+)', block)
            
            if domain_match and from_match and to_match and conf_match:
                try:
                    conf = float(conf_match.group(1))
                    events.append({
                        "domain": domain_match.group(1).strip().lower(),
                        "from_position": from_match.group(1).strip(),
                        "to_position": to_match.group(1).strip(),
                        "confidence": conf
                    })
                except ValueError:
                    pass
                    
        return events
