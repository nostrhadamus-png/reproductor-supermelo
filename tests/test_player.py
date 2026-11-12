import tempfile
import time
import unittest
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib  # noqa: E402

from reproductor.library import Song
from reproductor.playback import PlaybackController
from reproductor.player import Player
from reproductor.playlist import Playlist
from tests.fixtures import make_audio


def pump(segundos: float) -> None:
    contexto = GLib.MainContext.default()
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        while contexto.pending():
            contexto.iteration(False)
        time.sleep(0.005)


def esperar(condicion, timeout: float = 8.0) -> bool:
    contexto = GLib.MainContext.default()
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        while contexto.pending():
            contexto.iteration(False)
        if condicion():
            return True
        time.sleep(0.01)
    return False


class PlayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.wav = make_audio(cls.root / "tono.wav", duracion=1.5)
        cls.wav_largo = make_audio(cls.root / "largo.wav", duracion=4.0)
        cls.corrupto = cls.root / "corrupto.mp3"
        cls.corrupto.write_bytes(b"no es audio")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _player(self, sync: bool = False) -> Player:
        player = Player(audio_sink="fakesink")
        player._player.get_property("audio-sink").set_property("sync", sync)
        return player

    def test_duracion_volumen_y_fin_de_pista(self):
        player = self._player()
        eos, errores = [], []
        player.connect("eos", lambda *_: eos.append(True))
        player.connect("error", lambda _p, m: errores.append(m))
        player.load(str(self.wav), play=True)
        self.assertTrue(esperar(lambda: eos, 8), "no llegó EOS")
        self.assertEqual(errores, [])
        self.assertTrue(esperar(lambda: player.duration() > 0.5, 2))
        player.set_volume(0.30)
        self.assertAlmostEqual(player.get_volume(), 0.30, places=2)
        player.shutdown()

    def test_pausa_reanudacion_y_busqueda(self):
        player = self._player(sync=True)
        cambios = []
        player.connect("state-changed", lambda _p, e: cambios.append(e))
        player.load(str(self.wav_largo), play=True)
        self.assertTrue(esperar(lambda: "playing" in cambios, 8), "no arrancó")
        self.assertTrue(esperar(lambda: player.duration() > 1.0, 5))
        pump(0.4)
        player.pause()
        self.assertTrue(esperar(lambda: player.is_paused(), 5))
        p1 = player.position()
        pump(0.5)
        p2 = player.position()
        self.assertLess(abs(p2 - p1), 0.4, f"la posición avanzó en pausa: {p1} -> {p2}")

        player.play()
        self.assertTrue(esperar(lambda: player.is_playing(), 5))
        player.seek(3.0)
        self.assertTrue(esperar(lambda: player.position() > 2.0, 5), "seek no funcionó")
        player.toggle()
        self.assertTrue(esperar(lambda: player.is_paused(), 5), "toggle no pausó")
        player.shutdown()

    def test_archivo_corrupto_emite_error_sin_romper(self):
        player = self._player()
        errores = []
        player.connect("error", lambda _p, m: errores.append(m))
        player.load(str(self.corrupto), play=True)
        self.assertTrue(esperar(lambda: errores, 8), "no se emitió error")
        player.shutdown()


class PlaybackControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.a = make_audio(cls.root / "a.wav", duracion=1.0, frecuencia=440)
        cls.b = make_audio(cls.root / "b.wav", duracion=1.0, frecuencia=660)
        cls.c = make_audio(cls.root / "c.wav", duracion=1.0, frecuencia=880)
        cls.corrupto = cls.root / "aa_corrupto.mp3"
        cls.corrupto.write_bytes(b"basura")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _song(self, path: Path) -> Song:
        return Song(id=str(path), path=str(path), title=path.stem)

    def test_autoavance_y_parada_limpia(self):
        canciones = [self._song(self.a), self._song(self.b)]
        playlist = Playlist(canciones)
        player = Player(audio_sink="fakesink")
        control = PlaybackController(playlist, player)
        pistas, paradas = [], []
        control.on_track_changed = lambda sid: pistas.append(sid)
        control.on_stopped = lambda: paradas.append(True)

        self.assertTrue(control.play_song(canciones[0].id))
        self.assertTrue(esperar(lambda: control.current_id == canciones[1].id, 8), "no autoavanzó")
        self.assertTrue(esperar(lambda: paradas, 8), "no se detuvo al final")
        self.assertEqual(pistas, [canciones[0].id, canciones[1].id])
        self.assertIsNone(playlist.next_id(control.current_id))
        player.shutdown()

    def test_siguiente_y_anterior_respetan_nuevo_orden(self):
        canciones = [self._song(self.a), self._song(self.b), self._song(self.c)]
        playlist = Playlist(canciones)
        player = Player(audio_sink="fakesink")
        player._player.get_property("audio-sink").set_property("sync", True)
        control = PlaybackController(playlist, player)

        control.play_song(canciones[0].id)
        self.assertTrue(esperar(lambda: player.is_playing(), 8))
        self.assertTrue(control.next())
        self.assertEqual(control.current_id, canciones[1].id)
        self.assertTrue(esperar(lambda: player.is_playing(), 8))

        playlist.move(0, 2)  # el orden pasa a ser b, c, a
        self.assertEqual(playlist.ids, [canciones[1].id, canciones[2].id, canciones[0].id])
        self.assertTrue(player.is_playing(), "reordenar no debe interrumpir la pista actual")
        self.assertTrue(control.next())
        self.assertEqual(control.current_id, canciones[2].id)
        self.assertTrue(control.previous())
        self.assertEqual(control.current_id, canciones[1].id)
        player.shutdown()

    def test_error_salta_a_la_siguiente(self):
        corrupta = self._song(self.corrupto)
        buena = self._song(self.a)
        playlist = Playlist([corrupta, buena], [corrupta.id, buena.id])
        player = Player(audio_sink="fakesink")
        control = PlaybackController(playlist, player)
        errores, paradas = [], []
        control.on_error = lambda song, msg: errores.append((song.id, msg))
        control.on_stopped = lambda: paradas.append(True)

        control.play_song(corrupta.id)
        self.assertTrue(esperar(lambda: errores, 8), "no avisó del error")
        self.assertTrue(esperar(lambda: control.current_id == buena.id, 8), "no saltó a la siguiente")
        self.assertTrue(esperar(lambda: paradas, 8), "no terminó")
        self.assertEqual(errores[0][0], corrupta.id)
        player.shutdown()


if __name__ == "__main__":
    unittest.main()


class FormatosTest(unittest.TestCase):
    """Comprueba que GStreamer decodifica realmente todos los formatos pedidos."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.archivos = [
            make_audio(cls.root / f"pista{ext}", duracion=1.0, frecuencia=440 + i * 40)
            for i, ext in enumerate([".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a"])
        ]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_decodifica_mp3_flac_wav_ogg_opus_m4a(self):
        for archivo in self.archivos:
            with self.subTest(formato=archivo.suffix):
                player = Player(audio_sink="fakesink")
                errores, eos = [], []
                player.connect("eos", lambda *_: eos.append(True))
                player.connect("error", lambda _p, m: errores.append(m))
                player.load(str(archivo), play=True)
                self.assertTrue(esperar(lambda: eos or errores, 8), f"{archivo.suffix}: sin respuesta")
                self.assertEqual(errores, [], f"{archivo.suffix}: {errores}")
                self.assertTrue(esperar(lambda: player.duration() > 0.5, 3), f"{archivo.suffix}: duración")
                player.shutdown()


class EcualizadorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.wav = make_audio(cls.root / "eq.wav", duracion=4.0)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_bandas_disponibles_y_limites(self):
        player = Player(audio_sink="fakesink")
        self.assertTrue(player.has_equalizer())
        player.set_equalizer_gains([7.0, 6.0, 5.0, 3.0, 1.0, 0.0, -1.0, 1.0, 3.0, 5.0])
        self.assertEqual(player.get_equalizer_gains(), [7.0, 6.0, 5.0, 3.0, 1.0, 0.0, -1.0, 1.0, 3.0, 5.0])
        player.set_equalizer_band(0, 99)
        self.assertEqual(player.get_equalizer_band(0), 12.0)
        player.set_equalizer_band(0, -99)
        self.assertEqual(player.get_equalizer_band(0), -12.0)
        player.shutdown()

    def test_cambio_en_tiempo_real_sin_cortar_la_reproduccion(self):
        player = Player(audio_sink="fakesink")
        player._player.get_property("audio-sink").set_property("sync", True)
        errores = []
        player.connect("error", lambda _p, m: errores.append(m))
        player.load(str(self.wav), play=True)
        self.assertTrue(esperar(lambda: player.is_playing(), 8))
        pump(0.3)
        posicion_antes = player.position()
        player.set_equalizer_band(2, 6.0)
        pump(0.4)
        self.assertEqual(errores, [])
        self.assertTrue(player.is_playing(), "el cambio de EQ no debe cortar la pista")
        self.assertGreater(player.position(), posicion_antes)
        self.assertEqual(player.get_equalizer_band(2), 6.0)

        # El filtro sigue aplicado al cargar otra pista.
        player.load(str(self.wav), play=True)
        self.assertTrue(esperar(lambda: player.is_playing(), 8))
        self.assertEqual(player.get_equalizer_band(2), 6.0)
        player.shutdown()
