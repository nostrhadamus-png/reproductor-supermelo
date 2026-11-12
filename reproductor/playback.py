"""Secuenciación de reproducción (siguiente/anterior/auto-avance) sin GTK."""

from __future__ import annotations

from gi.repository import GLib

from .player import Player
from .playlist import Playlist


class PlaybackController:
    """Coordina la playlist con el motor de audio. No conoce la interfaz."""

    def __init__(self, playlist: Playlist, player: Player):
        self.playlist = playlist
        self.player = player
        self.current_id: str | None = None
        self._consecutive_errors = 0
        self._advance_scheduled = False

        # Callbacks que la interfaz puede reemplazar.
        self.on_track_changed = lambda song_id: None
        self.on_state_changed = lambda estado: None
        self.on_error = lambda song, mensaje: None
        self.on_stopped = lambda: None

        player.connect("eos", self._on_eos)
        player.connect("error", self._on_error)
        player.connect("state-changed", self._on_state_changed)

    # ----------------------------------------------------------- operaciones
    def play_song(self, song_id: str, position: float = 0.0, autoplay: bool = True) -> bool:
        song = self.playlist.get(song_id)
        if song is None:
            return False
        self.current_id = song_id
        try:
            self.player.load(song.path, play=autoplay, position=position)
        except Exception as exc:  # ruta inválida, sin códec, etc.
            self.on_error(song, str(exc))
            return False
        self.on_track_changed(song_id)
        return True

    def toggle(self) -> None:
        if self.player.is_playing():
            self.player.pause()
        elif self.player.has_media():
            self.player.play()
        elif self.current_id:
            self.play_song(self.current_id)

    def next(self, auto: bool = False) -> bool:
        if self.current_id is None:
            if len(self.playlist) == 0:
                return False
            return self.play_song(self.playlist[0].id)
        siguiente = self.playlist.next_id(self.current_id)
        if siguiente is None:
            self.player.stop()
            self.on_stopped()
            return False
        return self.play_song(siguiente)

    def previous(self) -> bool:
        anterior = self.playlist.previous_id(self.current_id)
        if anterior is None:
            if self.current_id:
                self.player.seek(0.0)
            return False
        return self.play_song(anterior)

    def stop(self) -> None:
        self.player.stop()
        self.on_stopped()

    def validate(self) -> None:
        """Tras un reescaneo: si la pista actual desapareció, detenerse."""
        if self.current_id and self.playlist.get(self.current_id) is None:
            self.player.stop()
            self.current_id = None
            self.on_track_changed(None)
            self.on_stopped()

    # -------------------------------------------------------------- señales
    def _on_state_changed(self, _player: Player, estado: str) -> None:
        if estado == "playing":
            self._consecutive_errors = 0
        self.on_state_changed(estado)

    def _on_eos(self, _player: Player) -> None:
        self.next(auto=True)

    def _on_error(self, _player: Player, mensaje: str) -> None:
        song = self.playlist.get(self.current_id)
        self._consecutive_errors += 1
        if song is not None:
            self.on_error(song, mensaje)
        if self._consecutive_errors >= max(1, len(self.playlist)):
            self.player.stop()
            self.on_stopped()
            return
        if song is not None and not self._advance_scheduled:
            self._advance_scheduled = True
            GLib.idle_add(self._advance_after_error)

    def _advance_after_error(self) -> bool:
        self._advance_scheduled = False
        self.next(auto=True)
        return False
