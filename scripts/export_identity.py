#!/usr/bin/env python3
"""
Script de Exportación de Identidad de Yuki en archivo ZIP portable.
Empaqueta SOUL.md, MEMORY.md, perfiles Honcho, skills y bases de datos.
"""

import os
import sys
import zipfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def export_identity(output_zip: str = None):
    if not output_zip:
        os.makedirs("output/posts", exist_ok=True)
        output_zip = f"output/yuki_identity_export_{int(time.time())}.zip"

    files_to_pack = [
        "SOUL.md",
        "MEMORY.md",
        "AGENTS.md",
        ".cursorrules",
        "config.yaml",
        "data/honcho_profile.json",
        "data/yuki_memory.db"
    ]

    print(f"📦 Exportando identidad de Yuki a: {output_zip}...")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in files_to_pack:
            if os.path.exists(f):
                zipf.write(f, arcname=f)
                print(f"  ✓ Añadido: {f}")

        # Añadir skills
        if os.path.exists("skills"):
            for root, dirs, files in os.walk("skills"):
                for file in files:
                    full_path = os.path.join(root, file)
                    zipf.write(full_path, arcname=full_path)
            print("  ✓ Añadido catálogo de skills.")

    print(f"\n✅ Identidad exportada correctamente ({os.path.getsize(output_zip)} bytes).")
    return output_zip

if __name__ == "__main__":
    export_identity()
