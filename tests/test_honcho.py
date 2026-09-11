"""
El perfil dialéctico es local, y el código tiene que decirlo.

M6 / L9. El diagrama dibujaba un «Honcho Client API» y aquí no hay ni ha habido
una sola llamada remota: el perfil vive en `data/honcho_profile.json` y lo
mueven dos heurísticas sobre el texto del Productor. Había además tres formas de
aparentar lo contrario, y las tres estaban activas:

- `api_key` caía a `"mock_key"`, que da a entender que hay credencial;
- se guardaba una `api_url` que nadie llamaba;
- `process_dialectic_exchange` devolvía `{"status": "synchronized"}` **siempre**,
  sincronizara o no, y **esta misma prueba lo exigía**. Un test puede fijar una
  mentira igual de bien que una garantía.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.honcho.dialectic import HonchoDialecticClient  # noqa: E402
from src.honcho.profile_sync import HonchoProfileSync  # noqa: E402


class TestHonchoDialectic(unittest.TestCase):
    def test_el_bloque_dialectico_llega_al_prompt(self):
        client = HonchoDialecticClient(app_id="test-diva")
        context = client.get_dialectic_context(user_id="producer_manager")
        self.assertIn("MODELADO DIALÉCTICO HONCHO", context)
        self.assertIn("Paleta Sonora Acordada", context)

    def test_un_ajuste_del_productor_cambia_el_perfil(self):
        client = HonchoDialecticClient(app_id="test-diva")
        HonchoProfileSync(client)

        result = client.process_dialectic_exchange(
            user_message="Hagamos la siguiente portada más minimalista y con tonos oscuros",
            agent_response="El contraste entre la sombra y la línea simple dará fuerza al trabajo.",
            user_id="producer_manager",
        )

        self.assertTrue(result["actualizado"])
        self.assertIn("minimalismo severo",
                      client._local_profile["aesthetic_preferences"]["visual_palette"])

    def test_no_se_dice_sincronizado_sin_haber_hablado_con_nadie(self):
        """
        La versión anterior devolvía `synchronized` en todos los casos, y esta
        prueba lo exigía. Es el único campo donde alguien iría a comprobarlo.
        """
        client = HonchoDialecticClient(app_id="test-diva")

        result = client.process_dialectic_exchange(
            user_message="nada que cambie el perfil", agent_response="ya",
            user_id="producer_manager",
        )

        self.assertEqual(result["status"], "local")
        self.assertFalse(result["remoto"])
        self.assertFalse(result["actualizado"], "no cambió nada y no puede decir que sí")

    def test_sin_clave_no_se_inventa_una(self):
        """`"mock_key"` por defecto daba a entender que había credencial."""
        os.environ.pop("HONCHO_API_KEY", None)
        client = HonchoDialecticClient(app_id="test-diva")

        self.assertEqual(client.api_key, "")

    def test_el_perfil_corrupto_no_tumba_la_instancia(self):
        """
        Se lee con `estado_json`, como el resto del estado: un fichero ilegible
        devuelve el perfil de base en vez de reventar al arrancar.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            os.environ["DATABASE_PATH"] = str(Path(carpeta) / "yuki.db")
            Path(carpeta, "honcho_profile.json").write_text("{roto", encoding="utf-8")
            try:
                client = HonchoDialecticClient(app_id="test-diva")
                self.assertIn("aesthetic_preferences", client._local_profile)
            finally:
                os.environ.pop("DATABASE_PATH", None)

    def test_dos_clientes_no_comparten_las_mismas_listas(self):
        """
        El perfil de base es una función y no un diccionario compartido: si lo
        fuera, lo que añadiera uno se lo encontraría el otro.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            os.environ["DATABASE_PATH"] = str(Path(carpeta) / "yuki.db")
            try:
                uno = HonchoDialecticClient()
                otro = HonchoDialecticClient()
                uno._local_profile["aesthetic_preferences"]["visual_palette"].append("prestado")
                self.assertNotIn(
                    "prestado", otro._local_profile["aesthetic_preferences"]["visual_palette"])
            finally:
                os.environ.pop("DATABASE_PATH", None)

    def test_el_perfil_se_guarda_por_el_camino_atomico_del_proyecto(self):
        """
        La atomicidad no se puede observar desde fuera después de escribir: una
        escritura corriente tampoco deja temporal. Lo que sí se comprueba —y es
        la regla que el proyecto declara— es que el guardado pasa por
        `estado_json`, donde la garantía está y tiene sus propias pruebas
        (`test_una_escritura_a_medias_no_pisa_lo_que_habia`). Este módulo era el
        octavo con su propia copia de esas dos líneas.
        """
        import json
        import tempfile

        from src.core import estado_json

        with tempfile.TemporaryDirectory() as carpeta:
            os.environ["DATABASE_PATH"] = str(Path(carpeta) / "yuki.db")
            original = estado_json.escribir
            pasos = []
            estado_json.escribir = lambda ruta, datos: pasos.append(ruta) or original(ruta, datos)
            try:
                client = HonchoDialecticClient()
                client._local_profile["relationship_stage"] = "otra cosa"
                client.save_local_profile()
                guardado = json.loads(
                    Path(carpeta, "honcho_profile.json").read_text(encoding="utf-8"))
                self.assertEqual(guardado["relationship_stage"], "otra cosa")
                self.assertEqual([ruta.name for ruta in pasos], ["honcho_profile.json"])
            finally:
                estado_json.escribir = original
                os.environ.pop("DATABASE_PATH", None)


if __name__ == "__main__":
    unittest.main()
