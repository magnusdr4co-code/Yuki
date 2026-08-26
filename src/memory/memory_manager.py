"""
Gestor de Ciclos y Síntesis de Memoria para Yuki.
Organiza la memoria en 3 capas:
1. Flujo Reciente (Aguas recientes de las últimas interacciones)
2. Memoria Diaria Consolidada (El fluir del día)
3. Vínculos con Visitantes y Productor
"""

import time
import os
from typing import Dict, Any, List, Optional
from .fts5_memory import FTS5MemoryEngine

class MemoryManager:
    def __init__(self, db_path: str = "data/yuki_memory.db", memory_md_path: str = "MEMORY.md"):
        self.engine = FTS5MemoryEngine(db_path=db_path)
        self.memory_md_path = memory_md_path
        self._bootstrap_if_empty()

    def _bootstrap_if_empty(self):
        # Si la base de datos está recién creada, cargar MEMORY.md
        results = self.engine.search("Yuki", limit=1)
        if not results and os.path.exists(self.memory_md_path):
            self.engine.load_from_markdown(self.memory_md_path)

    def retrieve_context_for_query(
        self,
        query: str,
        user_id: str = "general",
        limit: int = 4
    ) -> Dict[str, Any]:
        """
        Recupera de forma selectiva y ultrarrápida (<113ms) los recuerdos más relevantes
        sin saturar la ventana de contexto (evita Context Rot).
        """
        memories = self.engine.search(query=query, user_id=user_id, limit=limit)
        
        formatted_blocks = []
        for mem in memories:
            formatted_blocks.append(f"[{mem['category'].upper()} - {mem['title']}]\n{mem['content']}")

        return {
            "retrieved_count": len(memories),
            "latency_ms": memories[0]["search_latency_ms"] if memories else 0.0,
            "context_block": "\n\n".join(formatted_blocks) if formatted_blocks else "No hay recuerdos específicos activados."
        }

    def record_interaction(
        self,
        user_id: str,
        user_name: str,
        user_message: str,
        agent_response: str,
        notable_fact: Optional[str] = None
    ):
        """Registra una interacción significativa en la memoria episódica."""
        content = f"Intercambio con {user_name} (@{user_id}):\n- Dijo: {user_message}\n- Yuki respondió: {agent_response}"
        if notable_fact:
            content += f"\n- Eco destilado: {notable_fact}"

        self.engine.add_memory(
            category="visitor",
            title=f"Encuentro con {user_name}",
            content=content,
            tags=f"{user_id} {user_name} conversacion",
            user_id=user_id,
            importance=1.2 if notable_fact else 0.8
        )

    def save_daily_synthesis(self, date_str: str, summary_text: str):
        """Guarda la síntesis nocturna de la jornada."""
        self.engine.add_memory(
            category="daily_synthesis",
            title=f"Memoria del Día — {date_str}",
            content=summary_text,
            tags="sintesis diaria reflexiones",
            user_id="general",
            importance=2.0
        )
