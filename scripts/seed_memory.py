#!/usr/bin/env python3
"""
Script de Inicialización y Seeding de Memoria para Yuki.
Indexa los textos biográficos y recursos históricos de 'recursos extra/' en la base SQLite FTS5.
"""

import os
import sys
import json
import re

# Asegurar que la raíz del proyecto está en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory.fts5_memory import FTS5MemoryEngine

def seed_database(db_path: str = "data/yuki_memory.db"):
    engine = FTS5MemoryEngine(db_path=db_path)
    print(f"🌱 Iniciando población de memoria SQLite FTS5 en: {db_path}...")

    count = 0

    # 1. Cargar MEMORY.md base
    if os.path.exists("MEMORY.md"):
        engine.load_from_markdown("MEMORY.md")
        print("  ✓ Cargado MEMORY.md base.")
        count += 5

    # 2. Cargar biografía detallada
    bio_path = "recursos extra/yuki/bibliography.txt"
    if os.path.exists(bio_path):
        with open(bio_path, "r", encoding="utf-8") as f:
            bio_text = f.read()

        sections = bio_text.split("\n\n")
        for i, sec in enumerate(sections):
            if sec.strip():
                lines = sec.strip().split("\n")
                title = lines[0][:60]
                engine.add_memory(
                    category="core",
                    title=f"Biografía — {title}",
                    content=sec.strip(),
                    tags="biografia origen geisha kado chado shamisen",
                    user_id="general",
                    importance=2.5
                )
                count += 1
        print("  ✓ Cargada bibliografía detallada desde recursos extra.")

    # 3. Cargar respuestas y personalidad en español
    personality_json = "recursos extra/yuki/es-ES/personality.json"
    if os.path.exists(personality_json):
        with open(personality_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        system_tmpl = data.get("system_prompt_template", {})
        for key, body in system_tmpl.items():
            if isinstance(body, list):
                content = "\n".join(body)
                engine.add_memory(
                    category="core",
                    title=f"Protocolo de Identidad — {key}",
                    content=content,
                    tags="identidad estilo protocolo",
                    user_id="general",
                    importance=3.0
                )
                count += 1
        print("  ✓ Cargados protocolos y ejemplos de personalidad.")

    print(f"\n✨ Población completada con éxito. Total registros añadidos/actualizados: {count}")

if __name__ == "__main__":
    seed_database()
