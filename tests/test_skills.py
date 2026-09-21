"""
Tests unitarios para el catálogo de skills (agentskills.io).
"""

import os
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _todas_las_habilidades():
    """
    Las que hay, no las que alguien recordó escribir en una lista.

    La lista enumeraba diez de quince. Las cinco que faltaban —`animar-portada`,
    `autocaracterizarse`, `diagnostico-ma`, `ikebana-curaduria` y
    `lanzamiento-single`— no las comprobaba nadie, y a una de ellas le faltaba
    la sección `## Herramientas` que `AGENTS.md` §4 declara obligatoria.
    """
    return sorted(d.name for d in (RAIZ / "skills").iterdir()
                  if d.is_dir() and (d / "SKILL.md").is_file())


class TestSkillsCatalog(unittest.TestCase):
    def test_skills_exist_and_have_frontmatter(self):
        expected_skills = _todas_las_habilidades()
        self.assertGreaterEqual(len(expected_skills), 15,
                                "se han perdido habilidades del catálogo")

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



class TestContratoDeHerramientas(unittest.TestCase):
    """
    `AGENTS.md` §4 dice que cada `SKILL.md` declara su contrato de herramientas
    y que ese contrato es vinculante. Una habilidad sin él no es una habilidad
    con menos documentación: es una que puede inventarse el camino, que es el
    vicio que este proyecto persigue.
    """

    def test_toda_habilidad_declara_sus_herramientas(self):
        sin_contrato = []
        for nombre in _todas_las_habilidades():
            texto = (RAIZ / "skills" / nombre / "SKILL.md").read_text(encoding="utf-8")
            if "## Herramientas" not in texto:
                sin_contrato.append(nombre)

        self.assertFalse(sin_contrato,
                         f"habilidades sin sección `## Herramientas`: {sin_contrato}")

    def test_toda_habilidad_dice_quien_la_dispara(self):
        """
        El fallo de `autocaracterizarse`: la habilidad prometía que el ritual
        corría solo al cambiar el sekki mientras el módulo no lo llamaba nadie.
        Decir quién la dispara es lo que permite comprobar que es verdad.
        """
        mudas = []
        for nombre in _todas_las_habilidades():
            texto = (RAIZ / "skills" / nombre / "SKILL.md").read_text(encoding="utf-8").lower()
            if not any(p in texto for p in ("quién la dispara", "cli.py skill", "/" + nombre)):
                mudas.append(nombre)

        self.assertFalse(mudas, f"habilidades que no dicen cómo se invocan: {mudas}")


if __name__ == "__main__":
    unittest.main()
