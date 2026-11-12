"""Lógica pura de la playlist: orden, reordenamiento y navegación."""

from __future__ import annotations

from .library import Song


class Playlist:
    """Lista ordenada de canciones. No toca nunca los archivos del disco."""

    def __init__(self, songs: list[Song] | None = None, order: list[str] | None = None):
        self._songs: list[Song] = []
        self._by_id: dict[str, Song] = {}
        self.reconcile(songs or [], order or [])

    # ------------------------------------------------------------------ orden
    def reconcile(self, songs: list[Song], order: list[str]) -> None:
        """Conserva el orden guardado, añade nuevas al final y quita ausentes."""
        encontradas = {s.id: s for s in songs}
        vistas: set[str] = set()
        resultado: list[Song] = []
        for song_id in order:
            if song_id in encontradas and song_id not in vistas:
                resultado.append(encontradas[song_id])
                vistas.add(song_id)
        for song in sorted(encontradas.values(), key=lambda s: s.path.casefold()):
            if song.id not in vistas:
                resultado.append(song)
                vistas.add(song.id)
        self._songs = resultado
        self._by_id = {s.id: s for s in resultado}

    def set_songs(self, songs: list[Song]) -> None:
        self.reconcile(songs, self.ids)

    # --------------------------------------------------------------- consulta
    @property
    def ids(self) -> list[str]:
        return [s.id for s in self._songs]

    def __len__(self) -> int:
        return len(self._songs)

    def __iter__(self):
        return iter(self._songs)

    def __getitem__(self, index: int) -> Song:
        return self._songs[index]

    def get(self, song_id: str | None) -> Song | None:
        return self._by_id.get(song_id) if song_id else None

    def index_of(self, song_id: str | None) -> int:
        if not song_id:
            return -1
        for i, song in enumerate(self._songs):
            if song.id == song_id:
                return i
        return -1

    def index_of_path(self, path: str | None) -> int:
        if not path:
            return -1
        for i, song in enumerate(self._songs):
            if song.path == path:
                return i
        return -1

    def next_id(self, song_id: str | None) -> str | None:
        i = self.index_of(song_id)
        if i < 0 or i + 1 >= len(self._songs):
            return None
        return self._songs[i + 1].id

    def previous_id(self, song_id: str | None) -> str | None:
        i = self.index_of(song_id)
        if i <= 0:
            return None
        return self._songs[i - 1].id

    # ---------------------------------------------------------- reordenación
    def move(self, index: int, new_index: int) -> bool:
        """Mueve la posición `index` a `new_index` (ambos en la lista actual)."""
        if not self._songs:
            return False
        if index < 0 or index >= len(self._songs):
            return False
        new_index = max(0, min(new_index, len(self._songs) - 1))
        if index == new_index:
            return False
        song = self._songs.pop(index)
        self._songs.insert(new_index, song)
        return True

    def move_id(self, song_id: str, new_index: int) -> bool:
        return self.move(self.index_of(song_id), new_index)

    def move_id_to_id(self, source_id: str, target_id: str) -> bool:
        """Suelta `source_id` sobre `target_id`: acaba en la posición del destino."""
        source = self.index_of(source_id)
        target = self.index_of(target_id)
        if source < 0 or target < 0 or source == target:
            return False
        return self.move(source, target)

    def move_up(self, song_id: str) -> bool:
        i = self.index_of(song_id)
        return self.move(i, i - 1) if i > 0 else False

    def move_down(self, song_id: str) -> bool:
        i = self.index_of(song_id)
        return self.move(i, i + 1) if 0 <= i < len(self._songs) - 1 else False
