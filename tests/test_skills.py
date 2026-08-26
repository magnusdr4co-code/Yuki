"""
Tests unitarios para el catálogo de skills (agentskills.io).
"""

import os
import unittest

class TestSkillsCatalog(unittest.TestCase):
    def test_skills_exist_and_have_frontmatter(self):
        expected_skills = [
            "componer-beat",
            "generar-portada",
            "sintesis-vocal",
            "publicar-redes",
            "analizar-feed",
            "lectura-runas",
            "ceremonia-te",
            "escribir-waka",
            "sintesis-diaria",
            "consultar-memoria"
        ]

        for skill_name in expected_skills:
            skill_dir = os.path.join("skills", skill_name)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            
            self.assertTrue(os.path.exists(skill_dir), f"Directorio skills/{skill_name} no existe")
            self.assertTrue(os.path.exists(skill_file), f"Archivo SKILL.md no existe en {skill_name}")

            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertTrue(content.startswith("---"), f"Frontmatter ausente en {skill_name}")
            self.assertIn(f"name: {skill_name}", content)
            self.assertIn("description:", content)

if __name__ == "__main__":
    unittest.main()
