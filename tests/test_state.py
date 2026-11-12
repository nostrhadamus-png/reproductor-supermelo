import json
import tempfile
import unittest
from pathlib import Path

from reproductor.state import DEFAULT_STATE, load_state, save_state


class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "sub" / "state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_guarda_y_recupera(self):
        estado = {
            "order": ["/a.mp3", "/b.mp3"],
            "last_song": "/b.mp3",
            "selected_song": "/a.mp3",
            "volume": 0.42,
            "position": 31.5,
            "equalizer": {
                "enabled": True,
                "preset": "Plano",
                "gains": [0.0] * 10,
            },
        }
        self.assertTrue(save_state(estado, self.path))
        self.assertTrue(self.path.exists())
        self.assertEqual(load_state(self.path), estado)

    def test_escritura_atomica_no_deja_temporales(self):
        save_state(DEFAULT_STATE, self.path)
        sobrantes = list(self.path.parent.glob(".state-*.tmp"))
        self.assertEqual(sobrantes, [])

    def test_archivo_corrupto_usa_valores_por_defecto(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ esto no es json", encoding="utf-8")
        estado = load_state(self.path)
        self.assertEqual(estado, DEFAULT_STATE)

    def test_archivo_ausente_usa_valores_por_defecto(self):
        self.assertEqual(load_state(self.path), DEFAULT_STATE)

    def test_sanitiza_tipos_y_rangos(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "order": ["/a.mp3", "/a.mp3", 7, "", "/b.mp3"],
                    "volume": 9,
                    "position": -4,
                    "last_song": 123,
                }
            ),
            encoding="utf-8",
        )
        estado = load_state(self.path)
        self.assertEqual(estado["order"], ["/a.mp3", "/b.mp3"])
        self.assertEqual(estado["volume"], 1.0)
        self.assertEqual(estado["position"], 0.0)
        self.assertIsNone(estado["last_song"])

    def test_persiste_ecualizador(self):
        estado = {
            "equalizer": {
                "enabled": False,
                "preset": "Rock",
                "gains": [5.0, 4.0, 3.5, 1.0, 0.0, -1.0, -1.5, 1.0, 3.0, 5.0],
            }
        }
        self.assertTrue(save_state(estado, self.path))
        recuperado = load_state(self.path)
        self.assertEqual(recuperado["equalizer"], estado["equalizer"])

    def test_sanitiza_ecualizador(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "equalizer": {
                        "enabled": "sí",
                        "preset": "Inventado",
                        "gains": [99, -99, 2.3, "x", 0.25, None, 1.26],
                    }
                }
            ),
            encoding="utf-8",
        )
        estado = load_state(self.path)["equalizer"]
        self.assertEqual(estado["enabled"], True)
        self.assertEqual(estado["preset"], "Plano")
        self.assertEqual(len(estado["gains"]), 10)
        self.assertEqual(estado["gains"][:4], [12.0, -12.0, 2.5, 0.0])
        self.assertEqual(estado["gains"][5:], [0.0, 1.5, 0.0, 0.0, 0.0])

    def test_faltante_no_comparte_el_diccionario_por_defecto(self):
        estado = load_state(self.path)
        estado["equalizer"]["gains"][0] = 7.0
        estado["equalizer"]["enabled"] = False
        self.assertEqual(DEFAULT_STATE["equalizer"]["gains"][0], 0.0)
        self.assertEqual(DEFAULT_STATE["equalizer"]["enabled"], True)

    def test_ciclo_de_reinicio_conserva_orden(self):
        guardado = dict(DEFAULT_STATE)
        guardado["order"] = ["/c.mp3", "/a.mp3", "/b.mp3"]
        guardado["last_song"] = "/a.mp3"
        guardado["position"] = 12.0
        save_state(guardado, self.path)
        recuperado = load_state(self.path)
        self.assertEqual(recuperado["order"], guardado["order"])
        self.assertEqual(recuperado["last_song"], "/a.mp3")
        self.assertEqual(recuperado["position"], 12.0)


if __name__ == "__main__":
    unittest.main()
