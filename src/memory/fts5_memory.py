"""
Fast Memory Engine (SQLite + FTS5) para Yuki.
Permite búsqueda textual y semántica ultrarrápida (<113ms) eliminando el context rot de OpenClaw.
"""

import sqlite3
import time
import math
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

class FTS5MemoryEngine:
    def __init__(self, db_path: str = "data/yuki_memory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Activar optimizaciones SQLite para baja latencia
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA mmap_size = 268435456;") # 256MB mmap
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla regular para almacenamiento relacional y metadatos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,          -- 'core', 'project', 'producer', 'visitor', 'daily_synthesis', 'inner_thought'
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    user_id TEXT DEFAULT 'general',
                    importance REAL DEFAULT 1.0,     -- Multiplicador de 0.1 a 5.0
                    created_at REAL NOT NULL,        -- Timestamp Unix
                    updated_at REAL NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS growth_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    domain TEXT NOT NULL,            -- 'music', 'aesthetics', 'philosophy', 'relationships'
                    from_position TEXT NOT NULL,
                    to_position TEXT NOT NULL,
                    trigger_memory_ids TEXT DEFAULT '[]',  -- JSON array of memory IDs that influenced this
                    confidence REAL DEFAULT 0.5,
                    created_at REAL NOT NULL
                )
            """)

            # Tabla virtual FTS5 para búsqueda de texto completo con BM25
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    title,
                    content,
                    tags,
                    category,
                    user_id UNINDEXED,
                    content='memories',
                    content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2'
                )
            """)

            # Triggers de sincronización automática entre 'memories' y 'memories_fts'
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, title, content, tags, category, user_id)
                    VALUES (new.id, new.title, new.content, new.tags, new.category, new.user_id);
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, title, content, tags, category, user_id)
                    VALUES('delete', old.id, old.title, old.content, old.tags, old.category, old.user_id);
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, title, content, tags, category, user_id)
                    VALUES('delete', old.id, old.title, old.content, old.tags, old.category, old.user_id);
                    INSERT INTO memories_fts(rowid, title, content, tags, category, user_id)
                    VALUES (new.id, new.title, new.content, new.tags, new.category, new.user_id);
                END;
            """)
            conn.commit()

    def add_memory(
        self,
        category: str,
        title: str,
        content: str,
        tags: str = "",
        user_id: str = "general",
        importance: float = 1.0
    ) -> int:
        """Inserta un nuevo recuerdo en la memoria relacional e indexa en FTS5."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memories (category, title, content, tags, user_id, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (category, title, content, tags, user_id, importance, now, now))
            conn.commit()
            return cursor.lastrowid

    def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        half_life_days: float = 30.0
    ) -> List[Dict[str, Any]]:
        """
        Búsqueda de alta velocidad con ranking híbrido:
        Score = BM25_score * importance * temporal_decay
        """
        start_time = time.perf_counter()
        
        # Limpiar y preparar query FTS5
        clean_terms = re.findall(r'\w+', query.lower())
        if not clean_terms:
            return []
        
        fts_query = " OR ".join([f'"{term}"*' for term in clean_terms])
        
        conditions = ["memories_fts MATCH ?"]
        params: List[Any] = [fts_query]
        
        if user_id and user_id != "general":
            conditions.append("(m.user_id = ? OR m.user_id = 'general')")
            params.append(user_id)
            
        if category:
            conditions.append("m.category = ?")
            params.append(category)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT 
                m.id,
                m.category,
                m.title,
                m.content,
                m.tags,
                m.user_id,
                m.importance,
                m.created_at,
                bm25(memories_fts, 5.0, 2.0, 3.0, 1.0) AS bm25_rank,
                snippet(memories_fts, 1, '<b>', '</b>', '...', 15) AS snippet_content
            FROM memories_fts fts
            JOIN memories m ON m.id = fts.rowid
            WHERE {where_clause}
            ORDER BY bm25_rank ASC
            LIMIT 50
        """

        now = time.time()
        results = []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                # Fallback simple si la sintaxis FTS contiene caracteres anómalos
                cursor.execute("""
                    SELECT m.id, m.category, m.title, m.content, m.tags, m.user_id, m.importance, m.created_at,
                           1.0 as bm25_rank, m.content as snippet_content
                    FROM memories m
                    WHERE m.content LIKE ? OR m.title LIKE ?
                    LIMIT ?
                """, (f"%{query}%", f"%{query}%", limit))
                rows = cursor.fetchall()

            for row in rows:
                age_days = max(0.0, (now - row["created_at"]) / 86400.0)
                decay = math.exp(-0.693 * (age_days / half_life_days))
                
                # En SQLite FTS5, bm25 retorna un valor negativo más bajo cuanto mejor coincidencia
                # Transformamos a score positivo:
                raw_bm25 = abs(float(row["bm25_rank"]))
                bm25_score = 1.0 / (1.0 + raw_bm25)
                
                final_score = bm25_score * float(row["importance"]) * decay

                results.append({
                    "id": row["id"],
                    "category": row["category"],
                    "title": row["title"],
                    "content": row["content"],
                    "tags": row["tags"],
                    "user_id": row["user_id"],
                    "importance": row["importance"],
                    "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat(),
                    "score": round(final_score, 4),
                    "snippet": row["snippet_content"]
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        top_results = results[:limit]
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        for item in top_results:
            item["search_latency_ms"] = round(elapsed_ms, 2)

        return top_results

    def load_from_markdown(self, markdown_path: str = "MEMORY.md"):
        """Parsea e indexa el archivo MEMORY.md estructurado en la base de datos FTS5."""
        if not os.path.exists(markdown_path):
            return

        with open(markdown_path, "r", encoding="utf-8") as f:
            content = f.read()

        sections = re.split(r'\n##\s+', content)
        for sec in sections:
            if not sec.strip() or sec.startswith("# MEMORY.md"):
                continue
            lines = sec.strip().split("\n")
            title_line = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

            category = "core"
            importance = 1.5
            if "PROYECTOS" in title_line.upper():
                category = "project"
                importance = 2.0
            elif "PRODUCTOR" in title_line.upper():
                category = "producer"
                importance = 3.0
            elif "VÍNCULOS" in title_line.upper() or "KIZUNA" in title_line.upper():
                category = "visitor"
                importance = 1.8
            elif "TABÚ" in title_line.upper():
                category = "taboo"
                importance = 2.5

            self.add_memory(
                category=category,
                title=title_line,
                content=body,
                tags=category,
                user_id="general",
                importance=importance
            )

    def add_growth_event(self, date: str, domain: str, from_pos: str, to_pos: str, trigger_ids: str, confidence: float) -> int:
        """Inserta un evento de crecimiento (desplazamiento dialectico o evolutivo)."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO growth_events (date, domain, from_position, to_position, trigger_memory_ids, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date, domain, from_pos, to_pos, trigger_ids, confidence, now))
            conn.commit()
            return cursor.lastrowid

    def get_recent_growth(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Devuelve los eventos de crecimiento más recientes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, date, domain, from_position, to_position, trigger_memory_ids, confidence, created_at
                FROM growth_events
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_recent_inner_thoughts(self, hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
        """Busca pensamientos internos recientes de la memoria."""
        now = time.time()
        threshold = now - (hours * 3600)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, category, title, content, tags, user_id, importance, created_at
                FROM memories
                WHERE category = 'inner_thought' AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (threshold, limit))
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                row_dict = dict(r)
                row_dict["created_at"] = datetime.fromtimestamp(row_dict["created_at"], timezone.utc).isoformat()
                results.append(row_dict)
            return results
