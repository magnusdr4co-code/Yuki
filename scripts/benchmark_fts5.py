#!/usr/bin/env python3
"""
Benchmark automatizado de latencia y precisión para SQLite FTS5.
"""

import time
import os
import sys
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory.fts5_memory import FTS5MemoryEngine

def run_performance_test(num_records: int = 5000):
    test_db = "data/perf_test.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    print(f"🚀 Iniciando prueba de estrés FTS5 con {num_records} registros...")
    engine = FTS5MemoryEngine(db_path=test_db)

    # Inserción masiva
    t0 = time.perf_counter()
    with engine._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        now = time.time()
        for i in range(num_records):
            cursor.execute("""
                INSERT INTO memories (category, title, content, tags, user_id, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "visitor" if i % 3 == 0 else "project",
                f"Recuerdo de prueba #{i}",
                f"Conversación sobre el mar de metal, el shamisen y el arte de la flor {i}. Registro histórico.",
                "shamisen mar metal",
                f"user_{i % 100}",
                1.0,
                now,
                now
            ))
        conn.commit()
    insert_duration = time.perf_counter() - t0
    print(f"  ✓ {num_records} registros insertados e indexados en {insert_duration:.3f} s ({num_records/insert_duration:.0f} ops/sec)")

    # Búsquedas repetidas
    queries = ["shamisen metal", "flor y arte", "mar de metal", "registro historico"]
    latencies = []
    for _ in range(50):
        for q in queries:
            t_search = time.perf_counter()
            res = engine.search(q, limit=5)
            dt_ms = (time.perf_counter() - t_search) * 1000.0
            latencies.append(dt_ms)

    avg_lat = sum(latencies) / len(latencies)
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]

    print(f"\n📊 Resultados de Rendimiento en Consulta:")
    print(f"  • Latencia media de búsqueda: {avg_lat:.2f} ms")
    print(f"  • Latencia P95:                {p95_lat:.2f} ms")
    print(f"  • Cumplimiento SLA (<113ms):   {'✅ CUMPLIDO' if p95_lat < 113.0 else '❌ NO CUMPLIDO'}")

    if os.path.exists(test_db):
        os.remove(test_db)

if __name__ == "__main__":
    run_performance_test()
