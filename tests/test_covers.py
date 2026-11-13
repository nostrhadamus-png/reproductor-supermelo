import subprocess
import tempfile
import unittest
from pathlib import Path

from reproductor.covers import (
    decode_cover,
    find_cover_file,
    get_cover_bytes,
    load_cover_pixbuf,
    read_embedded_cover,
)
from tests.fixtures import FFMPEG, make_audio


def _make_png(path: Path, color: str = "red", size: int = 32) -> Path:
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}x{size}",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _make_mp3_with_cover(path: Path, cover: Path) -> Path:
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "96k",
            "-c:v",
            "mjpeg",
            "-id3v2_version",
            "3",
            "-disposition:v",
            "attached_pic",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@unittest.skipIf(FFMPEG is None, "ffmpeg no está disponible")
class CoversTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.song = self.root / "cancion.mp3"
        self.song.write_bytes(b"audio de mentira")

    def tearDown(self):
        self._tmp.cleanup()

    def test_busca_cover_y_folder_sin_distinguir_mayusculas(self):
        cover = self.root / "COVER.JPG"
        cover.write_bytes(b"imagen")
        folder = self.root / "folder.PNG"
        folder.write_bytes(b"otra")
        self.assertEqual(find_cover_file(self.song), cover)

        cover.unlink()
        self.assertEqual(find_cover_file(self.song), folder)

    def test_busca_front_y_albumart(self):
        front = self.root / "Front.jpeg"
        front.write_bytes(b"imagen")
        self.assertEqual(find_cover_file(self.song), front)

        front.unlink()
        albumart = self.root / "AlbumArt.png"
        albumart.write_bytes(b"imagen")
        self.assertEqual(find_cover_file(self.song), albumart)

    def test_sin_caratula(self):
        self.assertIsNone(find_cover_file(self.song))
        datos, origen = get_cover_bytes(self.song)
        self.assertIsNone(datos)
        self.assertEqual(origen, "none")
        self.assertIsNone(load_cover_pixbuf(self.song))

    def test_cover_en_carpeta(self):
        cover = _make_png(self.root / "cover.png")
        datos, origen = get_cover_bytes(self.song)
        self.assertEqual(origen, "folder")
        self.assertEqual(datos, cover.read_bytes())
        pixbuf = load_cover_pixbuf(self.song)
        self.assertIsNotNone(pixbuf)
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (32, 32))

    def test_cover_incrustada_tiene_prioridad(self):
        cover = _make_png(self.root / "cover.png", color="blue")
        incrustado = self.root / "incrustado.png"
        _make_png(incrustado, color="green")
        _make_mp3_with_cover(self.song, incrustado)

        datos_incrustados = read_embedded_cover(self.song)
        self.assertIsNotNone(datos_incrustados)

        # La carpeta también tiene una carátula, pero debe ganar la incrustada.
        cover.write_bytes(b"no es una imagen valida")
        datos, origen = get_cover_bytes(self.song)
        self.assertEqual(origen, "embedded")
        self.assertEqual(datos, datos_incrustados)

    def test_imagen_corrupta_cae_a_icono_generico(self):
        (self.root / "cover.jpg").write_bytes(b"esto no es una imagen")
        datos, origen = get_cover_bytes(self.song)
        self.assertEqual(origen, "folder")
        self.assertEqual(datos, b"esto no es una imagen")
        self.assertIsNone(decode_cover(datos))
        self.assertIsNone(load_cover_pixbuf(self.song))

    def test_decodifica_png_valido(self):
        png = _make_png(self.root / "portada.png")
        pixbuf = decode_cover(png.read_bytes())
        self.assertIsNotNone(pixbuf)
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (32, 32))

    def test_limita_el_tamano_de_la_caratula(self):
        png = _make_png(self.root / "grande.png", size=800)
        pixbuf = decode_cover(png.read_bytes(), max_side=128)
        self.assertIsNotNone(pixbuf)
        self.assertEqual(max(pixbuf.get_width(), pixbuf.get_height()), 128)


if __name__ == "__main__":
    unittest.main()
