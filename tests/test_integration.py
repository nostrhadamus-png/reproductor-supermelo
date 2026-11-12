import hashlib
import tempfile
import unittest
from pathlib import Path

from reproductor.library import scan_library
from reproductor.playlist import Playlist
from reproductor.state import load_state, save_state
from tests.fixtures import make_audio


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


class IntegrationTest(unittest.TestCase):
    """Ciclo completo: escaneo -> reordenar -> guardar -> reiniciar -> reescanear."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "Música"
        (self.root / "A").mkdir(parents=True)
        (self.root / "B").mkdir()
        self.f1 = make_audio(self.root / "A" / "1.mp3", titulo="Uno")
        self.f2 = make_audio(self.root / "A" / "2.flac", titulo="Dos")
        self.f3 = make_audio(self.root / "B" / "3.ogg", titulo="Tres")
        self.state_path = Path(self._tmp.name) / "data" / "state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_ciclo_completo_con_orden_persistente_y_archivos_intactos(self):
        archivos = [self.f1, self.f2, self.f3]
        hashes_antes = {p: _sha256(p) for p in archivos}

        canciones = scan_library(self.root)
        playlist = Playlist(canciones)
        self.assertEqual([s.title for s in playlist], ["Uno", "Dos", "Tres"])

        # Mover la última al principio y guardar.
        self.assertTrue(playlist.move_id_to_id(playlist[-1].id, playlist[0].id))
        self.assertEqual([s.title for s in playlist], ["Tres", "Uno", "Dos"])
        estado = load_state(self.state_path)
        estado["order"] = playlist.ids
        estado["last_song"] = playlist[1].id
        estado["selected_song"] = playlist[1].id
        estado["position"] = 9.5
        estado["volume"] = 0.4
        self.assertTrue(save_state(estado, self.state_path))

        # Reordenar no modificó ningún archivo.
        self.assertEqual(hashes_antes, {p: _sha256(p) for p in archivos})

        # Simular reinicio: releer estado y reconciliar con un escaneo nuevo.
        recuperado = load_state(self.state_path)
        playlist2 = Playlist(scan_library(self.root), recuperado["order"])
        self.assertEqual([s.title for s in playlist2], ["Tres", "Uno", "Dos"])
        self.assertEqual(recuperado["position"], 9.5)
        self.assertEqual(recuperado["volume"], 0.4)

        # Canción nueva: se añade al final sin alterar el orden personalizado.
        make_audio(self.root / "B" / "4.mp3", titulo="Cuatro")
        playlist3 = Playlist(scan_library(self.root), playlist2.ids)
        self.assertEqual([s.title for s in playlist3], ["Tres", "Uno", "Dos", "Cuatro"])

        # Canción eliminada: se retira conservando el resto del orden.
        self.f2.unlink()
        playlist4 = Playlist(scan_library(self.root), playlist3.ids)
        self.assertEqual([s.title for s in playlist4], ["Tres", "Uno", "Cuatro"])
        self.assertEqual(
            hashes_antes[self.f1], _sha256(self.f1), "el archivo existente cambió"
        )


if __name__ == "__main__":
    unittest.main()
