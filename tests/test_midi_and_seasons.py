"""
Tests unitarios para el generador MIDI real y el cálculo de micro-estaciones tradicionales.
"""

import os
import unittest
from datetime import datetime
from src.core.seasons import get_current_micro_season
from src.tools.midi_generator import YukiMIDIGenerator

class TestMidiAndSeasons(unittest.TestCase):
    def test_micro_season_calculation(self):
        # Probar fecha fija
        dt_spring = datetime(2026, 4, 10)
        season = get_current_micro_season(dt_spring)
        self.assertEqual(season["sekki"], "Seimei (Claridad Pura)")
        self.assertIn("claridad", season["seasonal_kigo"])

        # Probar fecha actual
        current_season = get_current_micro_season()
        self.assertIsNotNone(current_season["sekki"])
        self.assertIsNotNone(current_season["micro_season_ko"])

    def test_real_midi_binary_generation(self):
        midi_gen = YukiMIDIGenerator()
        test_dir = "data/test_music"
        os.makedirs(test_dir, exist_ok=True)

        res = midi_gen.generate_track(
            title="Prueba Shamisen",
            scale_name="hirajoshi",
            bpm=80,
            num_bars=8,
            output_dir=test_dir
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(os.path.exists(res["file_path"]))
        self.assertGreater(res["size_bytes"], 100)

        # Validar cabecera MIDI real (MThd)
        with open(res["file_path"], "rb") as f:
            header = f.read(4)
            self.assertEqual(header, b"MThd")

        # Limpiar
        if os.path.exists(res["file_path"]):
            os.remove(res["file_path"])
        if os.path.exists(test_dir):
            os.rmdir(test_dir)

if __name__ == "__main__":
    unittest.main()
