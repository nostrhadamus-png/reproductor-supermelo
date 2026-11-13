"""Motor de reproducción basado en GStreamer (playbin3/playbin)."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, GObject, Gst  # noqa: E402

NS = 1_000_000_000


class Player(GObject.GObject):
    """Envoltorio simple de playbin con señales para la interfaz."""

    __gsignals__ = {
        "eos": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, audio_sink: str | None = None):
        super().__init__()
        Gst.init(None)
        elemento = Gst.ElementFactory.make("playbin3", "player")
        if elemento is None:
            elemento = Gst.ElementFactory.make("playbin", "player")
        if elemento is None:
            raise RuntimeError("GStreamer no pudo crear playbin")
        self._player = elemento
        self._player.set_property("volume", 1.0)
        self._uri: str | None = None
        self._pending_seek_ns: int | None = None
        self._duration_ns = 0
        self._failed = False

        if audio_sink:
            sink = self._crear_sink(audio_sink)
            if sink is not None:
                self._player.set_property("audio-sink", sink)

        self._equalizer = Gst.ElementFactory.make("equalizer-10bands", "equalizer")
        if self._equalizer is not None:
            self._player.set_property("audio-filter", self._equalizer)

        bus = self._player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_message)

    @staticmethod
    def _crear_sink(descripcion: str):
        """Acepta un nombre simple o una descripción con propiedades.

        Ejemplo: ``fakesink`` (vacía el buffer lo antes posible) o
        ``fakesink sync=true`` (silencio, pero a velocidad real).
        """
        try:
            if " " in descripcion or "=" in descripcion:
                return Gst.parse_bin_from_description(descripcion, True)
            return Gst.ElementFactory.make(descripcion, "sink")
        except Exception:
            return None

    # ------------------------------------------------------------- mensajes
    def _on_message(self, _bus, message: Gst.Message) -> None:
        tipo = message.type
        if tipo == Gst.MessageType.EOS:
            self._failed = False
            self.emit("eos")
        elif tipo == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            self._failed = True
            self.emit("error", error.message if error else "Error desconocido")
        elif tipo == Gst.MessageType.DURATION_CHANGED:
            ok, duracion = self._player.query_duration(Gst.Format.TIME)
            if ok and duracion > 0:
                self._duration_ns = duracion
        elif tipo == Gst.MessageType.STATE_CHANGED and message.src is self._player:
            _viejo, nuevo, _pendiente = message.parse_state_changed()
            if nuevo == Gst.State.PAUSED and self._pending_seek_ns is not None:
                ns = self._pending_seek_ns
                self._pending_seek_ns = None
                GLib.idle_add(self._apply_seek, ns)
            self.emit("state-changed", nuevo.value_nick)

    def _apply_seek(self, ns: int) -> bool:
        if self._uri:
            self._player.seek_simple(
                Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, ns
            )
        return False

    # ----------------------------------------------------------- reproducción
    def load(self, path: str, play: bool = True, position: float = 0.0) -> None:
        self._failed = False
        self._duration_ns = 0
        self._pending_seek_ns = int(max(0.0, position) * NS) if position > 0 else None
        self._player.set_state(Gst.State.READY)
        self._uri = Path(path).as_uri()
        self._player.set_property("uri", self._uri)
        self._player.set_state(Gst.State.PLAYING if play else Gst.State.PAUSED)

    def play(self) -> None:
        if self._uri:
            self._player.set_state(Gst.State.PLAYING)

    def pause(self) -> None:
        if self._uri:
            self._player.set_state(Gst.State.PAUSED)

    def toggle(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._pending_seek_ns = None
        self._player.set_state(Gst.State.READY)
        self.emit("state-changed", "ready")

    def clear(self) -> None:
        self._pending_seek_ns = None
        self._player.set_state(Gst.State.NULL)
        self._uri = None
        self._duration_ns = 0

    def seek(self, seconds: float) -> None:
        if not self._uri:
            return
        ns = int(max(0.0, seconds) * NS)
        self._player.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, ns
        )

    # --------------------------------------------------------------- estado
    def is_playing(self) -> bool:
        _ok, estado, _pendiente = self._player.get_state(0)
        return estado == Gst.State.PLAYING

    def is_paused(self) -> bool:
        _ok, estado, _pendiente = self._player.get_state(0)
        return estado == Gst.State.PAUSED

    def has_media(self) -> bool:
        return self._uri is not None and not self._failed

    def position(self) -> float:
        if self._uri is None:
            return 0.0
        ok, pos = self._player.query_position(Gst.Format.TIME)
        return (pos / NS) if ok and pos >= 0 else 0.0

    def duration(self) -> float:
        if self._uri is None:
            return 0.0
        ok, dur = self._player.query_duration(Gst.Format.TIME)
        if ok and dur > 0:
            return dur / NS
        return self._duration_ns / NS

    def set_volume(self, volume: float) -> None:
        self._player.set_property("volume", max(0.0, min(1.0, volume)))

    def get_volume(self) -> float:
        return float(self._player.get_property("volume"))

    # ------------------------------------------------------------- ecualizador
    def has_equalizer(self) -> bool:
        return self._equalizer is not None

    def set_equalizer_band(self, index: int, gain_db: float) -> None:
        if self._equalizer is None or not 0 <= index <= 9:
            return
        self._equalizer.set_property(f"band{index}", max(-12.0, min(12.0, float(gain_db))))

    def get_equalizer_band(self, index: int) -> float:
        if self._equalizer is None or not 0 <= index <= 9:
            return 0.0
        return float(self._equalizer.get_property(f"band{index}"))

    def set_equalizer_gains(self, gains) -> None:
        for index, gain_db in enumerate(list(gains)[:10]):
            self.set_equalizer_band(index, gain_db)

    def get_equalizer_gains(self) -> list[float]:
        return [self.get_equalizer_band(i) for i in range(10)]

    def shutdown(self) -> None:
        try:
            self._player.set_state(Gst.State.NULL)
        except Exception:
            pass
