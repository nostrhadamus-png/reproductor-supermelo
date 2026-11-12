import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from reproductor.library import AUDIO_EXTENSIONS, get_music_dir, scan_library
from tests.fixtures import make_audio


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "Música"
        self.root.mkdir()
        (self.root / "Artista A").mkdir()
        (self.root / "Rock").mkdir()
        (self.root / "Rock" / "Sub").mkdir()
        (self.root / "notas.txt").write_text("no es audio")

        self.mp3 = make_audio(
            self.root / "Artista A" / "tema.mp3",
            titulo="Título Real",
            artista="Artista A",
            album="Álbum A",
        )
        self.flac = make_audio(self.root / "Rock" / "sin_metadatos.flac")
        self.wav = make_audio(self.root / "Rock" / "Sub" / "tono.wav")
        self.ogg = make_audio(self.root / "Rock" / "Sub" / "tono.ogg")
        self.opus = make_audio(self.root / "Rock" / "Sub" / "Tono.OPUS")
        self.m4a = make_audio(self.root / "Rock" / "Sub" / "tono.m4a")
        # Duplicado por enlace simbólico al mismo archivo real
        os.symlink(self.mp3, self.root / "Rock" / "duplicado.mp3")

    def tearDown(self):
        self._tmp.cleanup()

    def test_detecta_todos_los_formatos_y_subcarpetas(self):
        canciones = scan_library(self.root)
        rutas = {Path(s.path).name for s in canciones}
        self.assertEqual(
            rutas,
            {"tema.mp3", "sin_metadatos.flac", "tono.wav", "tono.ogg", "Tono.OPUS", "tono.m4a"},
        )
        self.assertTrue(AUDIO_EXTENSIONS >= {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac"})

    def test_metadatos_y_fallback_al_nombre(self):
        canciones = {Path(s.path).name: s for s in scan_library(self.root)}
        mp3 = canciones["tema.mp3"]
        self.assertEqual(mp3.title, "Título Real")
        self.assertEqual(mp3.artist, "Artista A")
        self.assertEqual(mp3.album, "Álbum A")
        flac = canciones["sin_metadatos.flac"]
        self.assertEqual(flac.title, "sin_metadatos")
        self.assertIsNone(flac.artist)
        self.assertIsNotNone(flac.duration)
        self.assertGreater(flac.duration, 0.5)

    def test_deduplica_enlaces_simbolicos(self):
        canciones = scan_library(self.root)
        ids = [s.id for s in canciones]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(canciones), 6)

    def test_archivo_corrupto_no_rompe_el_escaneo(self):
        corrupto = self.root / "corrupto.mp3"
        corrupto.write_bytes(b"esto no es un mp3 valido")
        canciones = scan_library(self.root)
        self.assertEqual(len(canciones), 7)
        entrada = next(s for s in canciones if Path(s.path).name == "corrupto.mp3")
        self.assertEqual(entrada.title, "corrupto")

    def test_carpeta_inexistente_devuelve_lista_vacia(self):
        self.assertEqual(scan_library(self.root / "no-existe"), [])

    def test_escaneo_no_modifica_archivos(self):
        antes = {p: _sha256(p) for p in (self.mp3, self.flac, self.wav, self.ogg, self.opus, self.m4a)}
        scan_library(self.root)
        despues = {p: _sha256(p) for p in antes}
        self.assertEqual(antes, despues)

    def test_get_music_dir_usa_xdg(self):
        ruta = get_music_dir()
        self.assertIsInstance(ruta, Path)
        self.assertTrue(str(ruta).startswith(os.path.expanduser("~")))


if __name__ == "__main__":
    unittest.main()
