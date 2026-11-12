import unittest

from reproductor.library import Song
from reproductor.playlist import Playlist


def cancion(n: int) -> Song:
    return Song(
        id=f"/tmp/real/{n}.mp3",
        path=f"/tmp/musica/{n}.mp3",
        title=f"Canción {n}",
        artist="Artista",
        album="Álbum",
    )


class PlaylistTest(unittest.TestCase):
    def setUp(self):
        self.songs = [cancion(i) for i in range(1, 6)]
        self.playlist = Playlist(self.songs)

    def ids(self):
        return [s.title for s in self.playlist]

    def test_orden_inicial_por_ruta(self):
        self.assertEqual(self.ids(), [f"Canción {i}" for i in range(1, 6)])

    def test_reconcile_conserva_orden_y_anade_nuevas_al_final(self):
        guardado = [cancion(3).id, cancion(1).id, "/vieja/borrada.mp3"]
        nuevas = [cancion(5), cancion(4), cancion(3), cancion(1), cancion(2)]
        playlist = Playlist(nuevas, guardado)
        self.assertEqual(playlist.ids, [cancion(3).id, cancion(1).id, cancion(2).id, cancion(4).id, cancion(5).id])

    def test_elimina_canciones_ausentes(self):
        restantes = [cancion(2), cancion(4)]
        self.playlist.set_songs(restantes)
        self.assertEqual(self.playlist.ids, [cancion(2).id, cancion(4).id])

    def test_move_y_reordenamiento(self):
        self.assertTrue(self.playlist.move(0, 2))
        self.assertEqual(self.playlist.ids[0], cancion(2).id)
        self.assertEqual(self.playlist.ids[2], cancion(1).id)

    def test_move_id_to_id(self):
        self.assertTrue(self.playlist.move_id_to_id(cancion(5).id, cancion(1).id))
        self.assertEqual(self.playlist[0].id, cancion(5).id)
        self.assertFalse(self.playlist.move_id_to_id(cancion(5).id, cancion(5).id))

    def test_subir_y_bajar(self):
        self.assertTrue(self.playlist.move_down(cancion(1).id))
        self.assertEqual(self.ids()[:2], ["Canción 2", "Canción 1"])
        self.assertTrue(self.playlist.move_up(cancion(1).id))
        self.assertEqual(self.ids()[:2], ["Canción 1", "Canción 2"])
        self.assertFalse(self.playlist.move_up(cancion(1).id))
        self.assertFalse(self.playlist.move_down(cancion(5).id))

    def test_siguiente_y_anterior_siguen_el_orden(self):
        self.assertEqual(self.playlist.next_id(cancion(1).id), cancion(2).id)
        self.assertEqual(self.playlist.previous_id(cancion(2).id), cancion(1).id)
        self.assertIsNone(self.playlist.previous_id(cancion(1).id))
        self.assertIsNone(self.playlist.next_id(cancion(5).id))
        self.playlist.move(0, 4)
        self.assertEqual(self.playlist.ids[-1], cancion(1).id)
        self.assertIsNone(self.playlist.next_id(cancion(1).id))
        self.assertEqual(self.playlist.previous_id(cancion(1).id), cancion(5).id)

    def test_reordenar_no_toca_los_archivos(self):
        originales = [s.path for s in self.playlist]
        self.playlist.move(0, 4)
        self.assertEqual(sorted(s.path for s in self.playlist), sorted(originales))
        self.assertEqual({s.id for s in self.playlist}, {s.id for s in self.songs})


if __name__ == "__main__":
    unittest.main()
