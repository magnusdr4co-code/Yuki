"""
Tests unitarios para el motor de memoria SQLite FTS5.
"""

import os
import unittest
from src.memory.fts5_memory import FTS5MemoryEngine

TEST_DB = "data/test_memory.db"

class TestFTS5Memory(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        self.engine = FTS5MemoryEngine(db_path=TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def test_add_and_search_memory(self):
        mem_id = self.engine.add_memory(
            category="core",
            title="Origen de Yuki",
            content="Yuki nació en una ciudad industrial del sur de Corea donde el mar huele a metal.",
            tags="origen corea mar",
            user_id="general",
            importance=2.0
        )
        self.assertIsNotNone(mem_id)

        # Búsqueda por palabra clave en FTS5
        results = self.engine.search("metal corea", limit=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("mar huele a metal", results[0]["content"])
        self.assertGreater(results[0]["score"], 0)
        self.assertLess(results[0]["search_latency_ms"], 100.0)

    def test_markdown_loader(self):
        md_content = """# MEMORY.md
## NÚCLEO INMUTABLE
Identidad de Yuki, 42 años.

## PROYECTOS CREATIVOS
Sencillo 'Memoria de Metal y Sal'.
"""
        test_md = "data/test_memory.md"
        with open(test_md, "w", encoding="utf-8") as f:
            f.write(md_content)

        self.engine.load_from_markdown(test_md)
        results = self.engine.search("Memoria de Metal", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("Sencillo", results[0]["content"])

        if os.path.exists(test_md):
            os.remove(test_md)

if __name__ == "__main__":
    unittest.main()
