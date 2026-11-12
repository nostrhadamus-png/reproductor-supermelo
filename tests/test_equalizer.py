import unittest

from reproductor.equalizer import (
    CUSTOM_PRESET,
    FREQUENCIES,
    MAX_GAIN,
    MIN_GAIN,
    PRESET_NAMES,
    PRESETS,
    clamp_gain,
    format_db,
    preset_gains,
    sanitize_gains,
)


class EqualizerTest(unittest.TestCase):
    def test_bandas_y_presets(self):
        self.assertEqual(len(FREQUENCIES), 10)
        self.assertEqual(list(FREQUENCIES), [29, 59, 119, 237, 474, 947, 1889, 3758, 7526, 15056])
        self.assertEqual(list(PRESET_NAMES), ["Plano", "Graves", "Agudos", "Rock", "Pop", "Clásica", "Voz", "Personalizado"])
        self.assertEqual(len(PRESETS), 7)
        self.assertNotIn(CUSTOM_PRESET, PRESETS)
        for nombre, gains in PRESETS.items():
            with self.subTest(preset=nombre):
                self.assertEqual(len(gains), 10)
                for gain in gains:
                    self.assertGreaterEqual(gain, MIN_GAIN)
                    self.assertLessEqual(gain, MAX_GAIN)
                    self.assertEqual(gain % 0.5, 0.0)
        self.assertEqual(list(PRESETS["Plano"]), [0.0] * 10)

    def test_preset_personalizado_no_cambia_bandas(self):
        self.assertIsNone(preset_gains(CUSTOM_PRESET))
        self.assertIsNone(preset_gains("No existe"))

    def test_sanitiza_ganancias(self):
        self.assertEqual(sanitize_gains(None), [0.0] * 10)
        self.assertEqual(sanitize_gains([99, -99]), [12.0, -12.0] + [0.0] * 8)
        self.assertEqual(
            sanitize_gains([2.3, "x", 0.25, 0.75, 1.26, -1.25]),
            [2.5, 0.0, 0.5, 1.0, 1.5, -1.5] + [0.0] * 4,
        )
        self.assertEqual(len(sanitize_gains(list(range(20)))), 10)

    def test_limites_y_paso(self):
        self.assertEqual(clamp_gain(-100), -12.0)
        self.assertEqual(clamp_gain(100), 12.0)
        self.assertEqual(clamp_gain(0.26), 0.5)
        self.assertEqual(clamp_gain(0.24), 0.0)
        self.assertEqual(clamp_gain(float("nan")), 0.0)
        self.assertEqual(clamp_gain(float("inf")), 0.0)
        self.assertEqual(clamp_gain("2"), 2.0)

    def test_formato_db(self):
        self.assertEqual(format_db(0), "0,0 dB")
        self.assertEqual(format_db(3), "+3,0 dB")
        self.assertEqual(format_db(-4.5), "-4,5 dB")
        self.assertEqual(format_db(0.25), "+0,5 dB")


if __name__ == "__main__":
    unittest.main()
