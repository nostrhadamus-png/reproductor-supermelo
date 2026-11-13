"""Interfaz GTK4 + libadwaita del reproductor."""

from __future__ import annotations

import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from .covers import get_cover_bytes  # noqa: E402
from .equalizer import (
    CUSTOM_PRESET,
    FREQUENCIES,
    PRESET_NAMES,
    clamp_gain,
    default_equalizer_state,
    format_db,
    preset_gains,
    sanitize_gains,
)
from .library import Song, get_music_dir, scan_library  # noqa: E402
from .miniplayer import MiniPlayer  # noqa: E402
from .playback import PlaybackController  # noqa: E402
from .player import Player  # noqa: E402
from .playlist import Playlist  # noqa: E402
from .state import load_state, save_state  # noqa: E402

APP_ID = "io.github.melo.Reproductor"
ICON_NAME = "reproductor-melo"

CSS = """
.playing-row { background-color: alpha(@accent_bg_color, 0.18); }
.drop-highlight { background-color: alpha(@accent_bg_color, 0.35); }
.now-title { font-weight: bold; }
.time-label { font-feature-settings: "tnum"; }
.dim-label { opacity: 0.7; }
"""


def format_time(seconds: float) -> str:
    segundos = max(0, int(seconds))
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{seg:02d}"
    return f"{minutos}:{seg:02d}"


class SongRow(Gtk.ListBoxRow):
    def __init__(self, song: Song, window: "MainWindow"):
        super().__init__()
        self.song = song
        self._window = window
        self.set_activatable(True)
        self.set_selectable(True)
        self.add_css_class("song-row")

        caja = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        caja.set_margin_top(8)
        caja.set_margin_bottom(8)
        caja.set_margin_start(12)
        caja.set_margin_end(12)

        self.indicador = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.indicador.set_pixel_size(14)
        self.indicador.add_css_class("accent")
        self.indicador.set_visible(False)
        self.indicador.set_valign(Gtk.Align.CENTER)
        caja.append(self.indicador)

        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        textos.set_hexpand(True)
        self.titulo = Gtk.Label(label=song.title, xalign=0)
        self.titulo.set_ellipsize(Pango.EllipsizeMode.END)
        self.titulo.set_lines(1)
        self.titulo.add_css_class("now-title")
        self.subtitulo = Gtk.Label(label=song.subtitle() or "—", xalign=0)
        self.subtitulo.set_ellipsize(Pango.EllipsizeMode.END)
        self.subtitulo.set_lines(1)
        self.subtitulo.add_css_class("dim-label")
        textos.append(self.titulo)
        textos.append(self.subtitulo)
        caja.append(textos)

        if song.duration:
            self.duracion = Gtk.Label(label=format_time(song.duration))
            self.duracion.add_css_class("dim-label")
            self.duracion.add_css_class("time-label")
            self.duracion.set_valign(Gtk.Align.CENTER)
            caja.append(self.duracion)

        self.set_child(caja)
        self.set_tooltip_text(song.path)
        self._instalar_dnd()

    # ---------------------------------------------------------- drag & drop
    def _instalar_dnd(self) -> None:
        origen = Gtk.DragSource()
        origen.set_actions(Gdk.DragAction.MOVE)
        origen.connect("prepare", self._on_prepare)
        origen.connect("drag-begin", self._on_drag_begin)
        origen.connect("drag-end", self._on_drag_end)
        self.add_controller(origen)

        destino = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        destino.connect("enter", self._on_drag_enter)
        destino.connect("leave", self._on_drag_leave)
        destino.connect("drop", self._on_drop)
        self.add_controller(destino)

    def _on_prepare(self, source: Gtk.DragSource, _x: float, _y: float):
        self._window._drag_source_id = self.song.id
        source.set_icon(Gtk.WidgetPaintable.new(self), 0, 0)
        return Gdk.ContentProvider.new_for_value(GObject.Value(GObject.TYPE_STRING, self.song.id))

    def _on_drag_begin(self, *_args) -> None:
        self.add_css_class("dim-label")

    def _on_drag_end(self, *_args) -> None:
        self.remove_css_class("dim-label")
        self._window._limpiar_resaltados()

    def _on_drag_enter(self, _target, _x, _y) -> Gdk.DragAction:
        if self._window._drag_source_id and self._window._drag_source_id != self.song.id:
            self.add_css_class("drop-highlight")
        return Gdk.DragAction.MOVE

    def _on_drag_leave(self, *_args) -> None:
        self.remove_css_class("drop-highlight")

    def _on_drop(self, _target, value, _x, _y) -> bool:
        self.remove_css_class("drop-highlight")
        origen = self._window._drag_source_id
        if isinstance(value, GObject.Value):
            try:
                origen = value.get_string() or origen
            except (TypeError, ValueError):
                pass
        elif isinstance(value, str):
            origen = value
        if origen and origen != self.song.id:
            self._window.mover_cancion_sobre(origen, self.song.id)
        return True


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, music_dir, state_path=None, audio_sink=None, smoke_test=False, **kwargs):
        super().__init__(**kwargs)
        self.music_dir = Path(music_dir)
        self.state_path = Path(state_path) if state_path else None
        self.audio_sink = audio_sink
        self._smoke_test = smoke_test
        self.set_default_size(920, 660)
        self.set_title("Reproductor Melo")

        self._closing = False
        self._drag_source_id: str | None = None
        self._selected_id: str | None = None
        self._suppress_selection = False
        self._last_seek = 0.0
        self._save_source = 0
        self._volume_source = 0
        self._rows: dict[str, SongRow] = {}
        self._scanning = False
        self.mini = None
        self._cover_cache: OrderedDict[str, object | None] = OrderedDict()
        self._cover_cache_max = 48

        self.app_state = load_state(self.state_path)
        eq_guardado = self.app_state.get("equalizer") or default_equalizer_state()
        self._eq_enabled = bool(eq_guardado.get("enabled", True))
        self._eq_gains = sanitize_gains(eq_guardado.get("gains"))
        preset = eq_guardado.get("preset")
        self._eq_preset = preset if preset in PRESET_NAMES else "Plano"
        self._eq_suppress = False
        self._eq_scales: list[Gtk.Scale] = []
        self._eq_value_labels: list[Gtk.Label] = []
        self.playlist = Playlist()
        self.player = Player(audio_sink=self.audio_sink)
        self.player.set_volume(self.app_state.get("volume", 1.0))
        self.controller = PlaybackController(self.playlist, self.player)
        self.controller.on_track_changed = self._on_track_changed
        self.controller.on_state_changed = self._on_state_changed
        self.controller.on_error = self._on_playback_error
        self.controller.on_stopped = self._on_stopped

        self._build_ui()
        self.connect("close-request", self._on_close_request)

        GLib.timeout_add(250, self._tick)
        GLib.timeout_add_seconds(20, self._autosave)

        self._start_scan(initial=True)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.header = Adw.HeaderBar()

        self.btn_subir = Gtk.Button(icon_name="go-up-symbolic")
        self.btn_subir.set_tooltip_text("Subir canción (Alt+↑)")
        self.btn_subir.connect("clicked", lambda *_: self.mover_seleccionada(-1))
        self.header.pack_start(self.btn_subir)

        self.btn_bajar = Gtk.Button(icon_name="go-down-symbolic")
        self.btn_bajar.set_tooltip_text("Bajar canción (Alt+↓)")
        self.btn_bajar.connect("clicked", lambda *_: self.mover_seleccionada(1))
        self.header.pack_start(self.btn_bajar)

        self.btn_escanear = Gtk.Button(icon_name="view-refresh-symbolic")
        self.btn_escanear.set_tooltip_text("Volver a escanear la carpeta Música")
        self.btn_escanear.connect("clicked", lambda *_: self.reescanear())
        self.header.pack_end(self.btn_escanear)

        self.btn_mini = Gtk.Button(icon_name="window-minimize-symbolic")
        self.btn_mini.set_tooltip_text("Mini reproductor")
        self.btn_mini.connect("clicked", lambda *_: self.mostrar_mini())
        self.header.pack_end(self.btn_mini)

        menu = Gio.Menu()
        menu.append("Volver a escanear", "win.rescan")
        menu.append("Acerca de Reproductor Melo", "win.about")
        boton_menu = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        boton_menu.set_tooltip_text("Menú")
        self.header.pack_end(boton_menu)

        self._accion("rescan", self.reescanear)
        self._accion("about", self._mostrar_acerca)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_show_separators(True)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.connect("row-activated", self._on_row_activated)
        self.listbox.connect("row-selected", self._on_row_selected)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_child(self.listbox)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        caja_carga = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        caja_carga.set_valign(Gtk.Align.CENTER)
        caja_carga.set_halign(Gtk.Align.CENTER)
        etiqueta_carga = Gtk.Label(label="Buscando música en tu carpeta…")
        caja_carga.append(self.spinner)
        caja_carga.append(etiqueta_carga)

        self.pagina_vacia = Adw.StatusPage()
        self.pagina_vacia.set_icon_name("folder-music-symbolic")
        self.pagina_vacia.set_title("No se encontró música")
        self.pagina_vacia.set_description(
            "Añade archivos MP3, FLAC, WAV, OGG, OPUS, M4A o AAC a tu carpeta Música "
            "y pulsa «Volver a escanear»."
        )

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self.scrolled, "lista")
        self.stack.add_named(caja_carga, "cargando")
        self.stack.add_named(self.pagina_vacia, "vacia")
        self.stack.set_visible_child_name("cargando")

        self.view_stack = Adw.ViewStack()
        pagina_biblioteca = self.view_stack.add_titled(self.stack, "biblioteca", "Biblioteca")
        pagina_biblioteca.set_icon_name("view-list-symbolic")
        pagina_ecualizador = self.view_stack.add_titled(
            self._build_equalizer_page(), "ecualizador", "Ecualizador"
        )
        pagina_ecualizador.set_icon_name("audio-x-generic-symbolic")
        self.view_switcher = Adw.ViewSwitcher(stack=self.view_stack)
        self.view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        self.header.set_title_widget(self.view_switcher)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self.header)
        toolbar.set_content(self.view_stack)

        contenido = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        contenido.append(toolbar)
        contenido.append(self._build_player_bar())

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(contenido)
        self.set_content(self.toasts)

        self._instalar_atajos()

    # ------------------------------------------------------- mini reproductor
    def mostrar_mini(self) -> None:
        if self.mini is None:
            self.mini = MiniPlayer(self)
        self.app_state["window_mode"] = "mini"
        self.mini.actualizar_desde_estado()
        self.set_visible(False)
        self.mini.present()
        self._save_now()

    def restaurar_principal(self) -> None:
        if self.mini is not None:
            self.mini.ocultar()
        self.app_state["window_mode"] = "main"
        self.present()
        self._save_now()

    def get_cover_texture(self, song: Song | None):
        """Carátula con caché en memoria; None -> icono genérico."""
        if song is None:
            return None
        clave = song.path
        if clave in self._cover_cache:
            self._cover_cache.move_to_end(clave)
            return self._cover_cache[clave]

        textura = None
        datos, _origen = get_cover_bytes(clave)
        if datos:
            try:
                textura = Gdk.Texture.new_from_bytes(GLib.Bytes.new(datos))
            except Exception:
                textura = None
        self._cover_cache[clave] = textura
        while len(self._cover_cache) > self._cover_cache_max:
            self._cover_cache.popitem(last=False)
        return textura

    def _build_equalizer_page(self) -> Gtk.Widget:
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        pagina.set_margin_top(18)
        pagina.set_margin_bottom(18)
        pagina.set_margin_start(18)
        pagina.set_margin_end(18)

        controles = Adw.PreferencesGroup()
        controles.set_title("Ecualizador")
        controles.set_description("Ajusta las 10 bandas; los cambios se aplican en tiempo real.")

        fila_interruptor = Adw.ActionRow(
            title="Activar ecualizador",
            subtitle="Al desactivarlo, las bandas se reproducen a 0 dB sin perder los ajustes.",
        )
        self.eq_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.eq_switch.set_active(self._eq_enabled)
        self.eq_switch.connect("notify::active", self._on_eq_toggled)
        fila_interruptor.add_suffix(self.eq_switch)
        fila_interruptor.set_activatable_widget(self.eq_switch)
        controles.add(fila_interruptor)

        self.eq_preset_row = Adw.ComboRow(title="Preset")
        self.eq_preset_row.set_model(Gtk.StringList.new(list(PRESET_NAMES)))
        self.eq_preset_row.set_selected(self._preset_index(self._eq_preset))
        self.eq_preset_row.connect("notify::selected", self._on_eq_preset_selected)
        controles.add(self.eq_preset_row)

        fila_reset = Adw.ActionRow(
            title="Restablecer",
            subtitle="Vuelve al preset Plano (todas las bandas a 0 dB).",
        )
        self.eq_reset_btn = Gtk.Button(label="Restablecer", valign=Gtk.Align.CENTER)
        self.eq_reset_btn.connect("clicked", lambda *_: self._eq_reset())
        fila_reset.add_suffix(self.eq_reset_btn)
        fila_reset.set_activatable_widget(self.eq_reset_btn)
        controles.add(fila_reset)
        pagina.append(controles)

        if not self.player.has_equalizer():
            aviso = Gtk.Label(
                label="El elemento GStreamer «equalizer-10bands» no está disponible.",
                xalign=0,
            )
            aviso.add_css_class("dim-label")
            pagina.append(aviso)

        etiqueta_bandas = Gtk.Label(label="Bandas (dB)", xalign=0)
        etiqueta_bandas.add_css_class("dim-label")
        pagina.append(etiqueta_bandas)

        desplazamiento = Gtk.ScrolledWindow()
        desplazamiento.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        desplazamiento.set_vexpand(True)

        bandas = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, homogeneous=True)
        self._eq_scales.clear()
        self._eq_value_labels.clear()

        for index, frecuencia in enumerate(FREQUENCIES):
            columna = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            columna.set_hexpand(True)

            valor = Gtk.Label(label=format_db(self._eq_gains[index]))
            valor.add_css_class("time-label")
            valor.set_halign(Gtk.Align.CENTER)

            ajuste = Gtk.Adjustment(
                lower=-12.0,
                upper=12.0,
                value=self._eq_gains[index],
                step_increment=0.5,
                page_increment=1.0,
            )
            escala = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL, adjustment=ajuste, draw_value=False)
            escala.set_size_request(46, 260)
            escala.set_vexpand(True)
            escala.set_tooltip_text(f"{frecuencia} Hz")
            escala.add_mark(0.0, Gtk.PositionType.RIGHT, None)
            escala.connect("value-changed", self._on_eq_band_changed, index)

            etiqueta_frecuencia = Gtk.Label(label=f"{frecuencia} Hz")
            etiqueta_frecuencia.add_css_class("dim-label")
            etiqueta_frecuencia.set_halign(Gtk.Align.CENTER)

            columna.append(valor)
            columna.append(escala)
            columna.append(etiqueta_frecuencia)
            bandas.append(columna)
            self._eq_scales.append(escala)
            self._eq_value_labels.append(valor)

        desplazamiento.set_child(bandas)
        pagina.append(desplazamiento)

        self._eq_update_sensitivity()
        self._eq_apply_to_player()
        return pagina

    @staticmethod
    def _preset_index(nombre: str) -> int:
        try:
            return PRESET_NAMES.index(nombre)
        except ValueError:
            return 0

    def _set_eq_sliders(self, gains) -> None:
        self._eq_suppress = True
        try:
            for escala, etiqueta, gain in zip(self._eq_scales, self._eq_value_labels, gains):
                escala.set_value(gain)
                etiqueta.set_label(format_db(gain))
        finally:
            self._eq_suppress = False

    def _set_eq_preset_combo(self, nombre: str) -> None:
        self._eq_suppress = True
        try:
            self.eq_preset_row.set_selected(self._preset_index(nombre))
        finally:
            self._eq_suppress = False

    def _eq_update_sensitivity(self) -> None:
        activo = self._eq_enabled
        for escala in self._eq_scales:
            escala.set_sensitive(activo)
        self.eq_preset_row.set_sensitive(activo)
        self.eq_reset_btn.set_sensitive(activo)

    def _eq_apply_to_player(self) -> None:
        if not self.player.has_equalizer():
            return
        if self._eq_enabled:
            self.player.set_equalizer_gains(self._eq_gains)
        else:
            self.player.set_equalizer_gains([0.0] * len(FREQUENCIES))

    def _eq_save(self) -> None:
        self.app_state["equalizer"] = {
            "enabled": self._eq_enabled,
            "preset": self._eq_preset,
            "gains": list(self._eq_gains),
        }
        self._schedule_save()

    def _on_eq_toggled(self, interruptor: Gtk.Switch, _pspec) -> None:
        self._eq_enabled = bool(interruptor.get_active())
        if self._eq_enabled:
            self._set_eq_sliders(self._eq_gains)
        else:
            self._set_eq_sliders([0.0] * len(FREQUENCIES))
        self._eq_update_sensitivity()
        self._eq_apply_to_player()
        self._eq_save()

    def _on_eq_preset_selected(self, fila: Adw.ComboRow, _pspec) -> None:
        if self._eq_suppress:
            return
        indice = fila.get_selected()
        if not 0 <= indice < len(PRESET_NAMES):
            return
        nombre = PRESET_NAMES[indice]
        self._eq_preset = nombre
        if nombre == CUSTOM_PRESET:
            self._eq_save()
            return
        gains = preset_gains(nombre)
        if gains is None:
            return
        self._eq_gains = gains
        self._set_eq_sliders(gains)
        self._eq_apply_to_player()
        self._eq_save()

    def _on_eq_band_changed(self, escala: Gtk.Scale, index: int) -> None:
        valor = escala.get_value()
        self._eq_value_labels[index].set_label(format_db(valor))
        if self._eq_suppress:
            return
        self._eq_gains[index] = clamp_gain(valor)
        if self._eq_enabled:
            self.player.set_equalizer_band(index, self._eq_gains[index])
        if self._eq_preset != CUSTOM_PRESET:
            self._eq_preset = CUSTOM_PRESET
            self._set_eq_preset_combo(CUSTOM_PRESET)
        self._eq_save()

    def _eq_reset(self) -> None:
        self._eq_preset = "Plano"
        self._eq_gains = preset_gains("Plano") or [0.0] * len(FREQUENCIES)
        self._set_eq_preset_combo("Plano")
        self._set_eq_sliders(self._eq_gains)
        self._eq_apply_to_player()
        self._eq_save()

    def _accion(self, nombre: str, callback) -> None:
        accion = Gio.SimpleAction.new(nombre, None)
        accion.connect("activate", lambda *_: callback())
        self.add_action(accion)

    def _build_player_bar(self) -> Gtk.Widget:
        barra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        barra.set_margin_top(10)
        barra.set_margin_bottom(10)
        barra.set_margin_start(14)
        barra.set_margin_end(14)

        fila = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)
        self.now_title = Gtk.Label(label="Sin reproducción", xalign=0)
        self.now_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.now_title.set_lines(1)
        self.now_title.add_css_class("now-title")
        self.now_sub = Gtk.Label(label="Selecciona una canción de la lista", xalign=0)
        self.now_sub.set_ellipsize(Pango.EllipsizeMode.END)
        self.now_sub.set_lines(1)
        self.now_sub.add_css_class("dim-label")
        info.append(self.now_title)
        info.append(self.now_sub)
        fila.append(info)

        controles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controles.set_valign(Gtk.Align.CENTER)
        self.btn_anterior = Gtk.Button(icon_name="media-skip-backward-symbolic")
        self.btn_anterior.set_tooltip_text("Canción anterior (Ctrl+←)")
        self.btn_anterior.connect("clicked", lambda *_: self.controller.previous())
        self.btn_play = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.btn_play.set_tooltip_text("Reproducir / Pausar (Espacio)")
        self.btn_play.add_css_class("circular")
        self.btn_play.add_css_class("suggested-action")
        self.btn_play.connect("clicked", lambda *_: self.reproducir_pausar())
        self.btn_siguiente = Gtk.Button(icon_name="media-skip-forward-symbolic")
        self.btn_siguiente.set_tooltip_text("Canción siguiente (Ctrl+→)")
        self.btn_siguiente.connect("clicked", lambda *_: self.controller.next())
        controles.append(self.btn_anterior)
        controles.append(self.btn_play)
        controles.append(self.btn_siguiente)
        fila.append(controles)

        volumen = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        volumen.set_valign(Gtk.Align.CENTER)
        icono_volumen = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
        self.volume_adj = Gtk.Adjustment(
            lower=0, upper=100, value=self.app_state.get("volume", 1.0) * 100,
            step_increment=5, page_increment=10,
        )
        self.volume_scale = Gtk.Scale(adjustment=self.volume_adj, draw_value=False)
        self.volume_scale.set_size_request(110, -1)
        self.volume_scale.set_tooltip_text("Volumen")
        self.volume_scale.connect("value-changed", self._on_volume_changed)
        volumen.append(icono_volumen)
        volumen.append(self.volume_scale)
        fila.append(volumen)

        barra.append(fila)

        progreso = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.lbl_transcurrido = Gtk.Label(label="0:00", xalign=1)
        self.lbl_transcurrido.set_size_request(56, -1)
        self.lbl_transcurrido.add_css_class("time-label")
        self.lbl_transcurrido.add_css_class("dim-label")

        self.progress_adj = Gtk.Adjustment(lower=0, upper=1, value=0, step_increment=1, page_increment=10)
        self.progress = Gtk.Scale(adjustment=self.progress_adj, draw_value=False)
        self.progress.set_hexpand(True)
        self.progress.set_tooltip_text("Posición de reproducción")
        self.progress.connect("change-value", self._on_seek)

        self.lbl_total = Gtk.Label(label="0:00", xalign=0)
        self.lbl_total.set_size_request(56, -1)
        self.lbl_total.add_css_class("time-label")
        self.lbl_total.add_css_class("dim-label")

        progreso.append(self.lbl_transcurrido)
        progreso.append(self.progress)
        progreso.append(self.lbl_total)
        barra.append(progreso)

        return barra

    def _instalar_atajos(self) -> None:
        atajos = Gtk.ShortcutController()
        atajos.set_scope(Gtk.ShortcutScope.GLOBAL)

        def agregar(trigger: str, callback) -> None:
            atajo = Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string(trigger),
                Gtk.CallbackAction.new(callback),
            )
            atajos.add_shortcut(atajo)

        agregar("<Control>r", lambda *_: self.reescanear() or True)
        agregar("<Alt>Up", lambda *_: self.mover_seleccionada(-1) or True)
        agregar("<Alt>Down", lambda *_: self.mover_seleccionada(1) or True)
        agregar("<Control>Right", lambda *_: self.controller.next() or True)
        agregar("<Control>Left", lambda *_: self.controller.previous() or True)
        agregar("space", lambda *_: self.reproducir_pausar() or True)
        self.add_controller(atajos)

    # -------------------------------------------------------------- escaneo
    def _start_scan(self, initial: bool = False) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._scan_initial = initial
        self.btn_escanear.set_sensitive(False)
        self.stack.set_visible_child_name("cargando")
        self.spinner.start()
        hilo = threading.Thread(target=self._scan_worker, daemon=True)
        hilo.start()

    def _scan_worker(self) -> None:
        try:
            canciones = scan_library(self.music_dir)
            error = None
        except Exception as exc:  # nunca debe tumbar la app
            canciones, error = [], str(exc)
        GLib.idle_add(self._apply_scan, canciones, error)

    def _apply_scan(self, canciones: list[Song], error: str | None) -> bool:
        if self._closing:
            return False
        self._scanning = False
        self.btn_escanear.set_sensitive(True)
        self.spinner.stop()
        if error:
            self._toast(f"No se pudo leer la carpeta Música: {error}")
            if len(self.playlist):
                self.stack.set_visible_child_name("lista")
                self._save_now()
                return False

        orden = self.playlist.ids if len(self.playlist) else list(self.app_state.get("order", []))
        self.playlist.reconcile(canciones, orden)
        self.app_state["order"] = self.playlist.ids
        self.controller.validate()
        self._rebuild_rows()

        if len(self.playlist):
            self.stack.set_visible_child_name("lista")
        else:
            self.stack.set_visible_child_name("vacia")

        self._actualizar_habilitados()

        if self._scan_initial:
            self._restaurar_estado()
        else:
            self._toast(f"Biblioteca actualizada: {len(self.playlist)} canciones")
        self._save_now()
        return False

    def _restaurar_estado(self) -> None:
        objetivo = self.app_state.get("selected_song")
        if self.playlist.get(objetivo) is None:
            objetivo = self.app_state.get("last_song")
        if self.playlist.get(objetivo):
            posicion = self.app_state.get("position", 0.0) if objetivo == self.app_state.get("last_song") else 0.0
            self._selected_id = objetivo
            self._select_song(objetivo)
            self.controller.play_song(objetivo, position=posicion, autoplay=False)
        elif len(self.playlist):
            self._selected_id = self.playlist[0].id
            self._select_song(self._selected_id)
        if self._smoke_test:
            if self.controller.current_id is None and len(self.playlist):
                self.controller.play_song(self.playlist[0].id, autoplay=True)
            GLib.timeout_add(1200, self._smoke_finish)

    def _smoke_finish(self) -> bool:
        actual = self.playlist.get(self.controller.current_id)
        print("SMOKE: interfaz iniciada; canciones:", len(self.playlist))
        print("SMOKE: pista actual:", actual.title if actual else None)
        print("SMOKE: reproduciendo:", self.player.is_playing())
        print("SMOKE: duración:", round(self.player.duration(), 2))
        print("SMOKE: posición:", round(self.player.position(), 2))
        print("SMOKE: orden restaurado:", [self.playlist[i].title for i in range(min(3, len(self.playlist)))])
        print("SMOKE: ecualizador disponible:", self.player.has_equalizer())
        print("SMOKE: EQ restaurado:", self._eq_preset, "activo:", self._eq_enabled,
              "banda 29 Hz:", self._eq_scales[0].get_value(), "dB")
        if self.player.has_equalizer():
            self.view_stack.set_visible_child_name("ecualizador")
            self.eq_preset_row.set_selected(self._preset_index("Rock"))
            print("SMOKE: preset Rock, banda 29 Hz:", round(self.player.get_equalizer_band(0), 1), "dB")
            self._eq_scales[0].set_value(7.5)
            print("SMOKE: slider movido, preset:", self._eq_preset,
                  "banda 29 Hz:", round(self.player.get_equalizer_band(0), 1), "dB")
            self.eq_switch.set_active(False)
            print("SMOKE: desactivado, banda 29 Hz:", round(self.player.get_equalizer_band(0), 1),
                  "dB, slider:", self._eq_scales[0].get_value())
            self.eq_switch.set_active(True)
            print("SMOKE: reactivado, banda 29 Hz:", round(self.player.get_equalizer_band(0), 1),
                  "dB, slider:", self._eq_scales[0].get_value())
            self.view_stack.set_visible_child_name("biblioteca")
        if len(self.playlist) >= 2:
            # Ejercita la ruta real de callbacks de drag & drop (sin puntero).
            primero = self.playlist[0]
            ultimo = self.playlist[-1]
            fila_origen = self._rows[ultimo.id]
            fila_destino = self._rows[primero.id]
            origen = Gtk.DragSource()
            proveedor = fila_origen._on_prepare(origen, 0, 0)
            valor = GObject.Value(GObject.TYPE_STRING, ultimo.id)
            ok = fila_destino._on_drop(None, valor, 0, 0)
            print("SMOKE: drag&drop callback:", bool(proveedor) and ok)
            print("SMOKE: nuevo orden:", [self.playlist[i].title for i in range(min(3, len(self.playlist)))])
            print("SMOKE: filas sincronizadas:", self._rows[self.playlist[0].id].song.id == self.playlist[0].id)
        if self.get_visible():
            self.close()
        else:
            # Arranque en modo mini: la principal nunca se mostró, así que
            # cerramos por la misma ruta lógica para guardar el estado.
            self._on_close_request()
        return False

    # ------------------------------------------------------------- filas UI
    def _rebuild_rows(self, select_id: str | None = None) -> None:
        if select_id is None:
            select_id = self._selected_id
        self._suppress_selection = True
        while (hijo := self.listbox.get_first_child()) is not None:
            self.listbox.remove(hijo)
        self._rows.clear()
        for song in self.playlist:
            fila = SongRow(song, self)
            self.listbox.append(fila)
            self._rows[song.id] = fila
        self._suppress_selection = False
        self._refresh_markers()
        if select_id and select_id in self._rows:
            self._select_song(select_id)

    def _select_song(self, song_id: str | None) -> None:
        fila = self._rows.get(song_id) if song_id else None
        if fila is None:
            return
        self._suppress_selection = True
        self.listbox.select_row(fila)
        self._suppress_selection = False
        self._selected_id = song_id

    def _refresh_markers(self) -> None:
        actual = self.controller.current_id if self.player.has_media() else None
        for song_id, fila in self._rows.items():
            activa = song_id == actual
            fila.indicador.set_visible(activa)
            if activa:
                fila.add_css_class("playing-row")
            else:
                fila.remove_css_class("playing-row")

    def _limpiar_resaltados(self) -> None:
        for fila in self._rows.values():
            fila.remove_css_class("drop-highlight")

    def _actualizar_habilitados(self) -> None:
        i = self.playlist.index_of(self._selected_id or self.controller.current_id)
        self.btn_subir.set_sensitive(i > 0)
        self.btn_bajar.set_sensitive(0 <= i < len(self.playlist) - 1)

    # ------------------------------------------------------- reproducción UI
    def _on_row_activated(self, _listbox: Gtk.ListBox, fila: SongRow) -> None:
        self._selected_id = fila.song.id
        self.app_state["selected_song"] = fila.song.id
        self.controller.play_song(fila.song.id, autoplay=True)

    def reproducir_pausar(self) -> None:
        if self.controller.current_id is None:
            song_id = self._selected_id or (self.playlist[0].id if len(self.playlist) else None)
            if song_id:
                self.controller.play_song(song_id, autoplay=True)
            else:
                self._toast("No hay canciones para reproducir")
            return
        self.controller.toggle()

    def _on_track_changed(self, song_id: str | None) -> None:
        song = self.playlist.get(song_id)
        if song is not None:
            self.now_title.set_label(song.title)
            self.now_sub.set_label(song.subtitle() or "Archivo local")
            self.app_state["last_song"] = song_id
            self.app_state["selected_song"] = song_id
            self._selected_id = song_id
            self._select_song(song_id)
        else:
            self.now_title.set_label("Sin reproducción")
            self.now_sub.set_label("Selecciona una canción de la lista")
        self._refresh_markers()
        self._actualizar_habilitados()
        self._update_play_icon()
        if self.mini is not None:
            self.mini.set_song(song)
        self._schedule_save()

    def _on_state_changed(self, estado: str) -> None:
        self._update_play_icon()
        if self.mini is not None:
            self.mini.update_play_icon()
        self._refresh_markers()

    def _on_stopped(self) -> None:
        self._update_play_icon()
        if self.mini is not None:
            self.mini.update_play_icon()
        self._refresh_markers()
        self.progress_adj.set_value(0)
        self.lbl_transcurrido.set_label("0:00")

    def _on_playback_error(self, song: Song, mensaje: str) -> None:
        self._toast(f"No se pudo reproducir «{song.title}»: {mensaje}")

    def _update_play_icon(self) -> None:
        if self.player.is_playing():
            self.btn_play.set_icon_name("media-playback-pause-symbolic")
        else:
            self.btn_play.set_icon_name("media-playback-start-symbolic")

    def _on_seek(self, _escala, _scroll, valor: float) -> bool:
        self._last_seek = time.monotonic()
        self.player.seek(valor)
        self.lbl_transcurrido.set_label(format_time(valor))
        return False

    def _on_volume_changed(self, escala: Gtk.Scale) -> None:
        valor = escala.get_value() / 100.0
        self.player.set_volume(valor)
        if self._volume_source:
            GLib.source_remove(self._volume_source)
        self._volume_source = GLib.timeout_add(500, self._guardar_volumen)

    def _guardar_volumen(self) -> bool:
        self._volume_source = 0
        self.app_state["volume"] = self.player.get_volume()
        self._save_now()
        return False

    def _tick(self) -> bool:
        if self._closing:
            return False
        if self.player.has_media():
            duracion = self.player.duration()
            if duracion > 0:
                self.progress_adj.set_upper(duracion)
                self.lbl_total.set_label(format_time(duracion))
            if time.monotonic() - self._last_seek > 0.5:
                posicion = self.player.position()
                self.progress_adj.set_value(min(posicion, max(duracion, posicion)))
                self.lbl_transcurrido.set_label(format_time(posicion))
            self._update_play_icon()
            if self.mini is not None and self.mini.get_visible():
                self.mini.update_play_icon()
        return True

    # --------------------------------------------------------- reordenación
    def mover_cancion_sobre(self, source_id: str, target_id: str) -> None:
        if self.playlist.move_id_to_id(source_id, target_id):
            self._after_reorder(source_id)

    def mover_seleccionada(self, delta: int) -> None:
        song_id = self._selected_id or self.controller.current_id
        if not song_id:
            return
        cambio = self.playlist.move_up(song_id) if delta < 0 else self.playlist.move_down(song_id)
        if cambio:
            self._after_reorder(song_id)

    def _after_reorder(self, keep_selected: str | None) -> None:
        self.app_state["order"] = self.playlist.ids
        self._rebuild_rows(select_id=keep_selected)
        self._actualizar_habilitados()
        self._save_now()

    # -------------------------------------------------------------- acciones
    def reescanear(self) -> None:
        self._start_scan(initial=False)

    def _mostrar_acerca(self) -> None:
        dialogo = Adw.AboutDialog()
        dialogo.set_application_name("Reproductor Melo")
        dialogo.set_application_icon(ICON_NAME)
        dialogo.set_developer_name("Uso personal")
        dialogo.set_version("1.1.0")
        dialogo.set_comments(
            "Reproductor de música local para Fedora, con biblioteca automática, "
            "playlist reordenable y persistencia de estado."
        )
        dialogo.present(self)

    # ------------------------------------------------------------ selección
    def _on_row_selected(self, _listbox: Gtk.ListBox, fila: SongRow | None) -> None:
        if self._suppress_selection:
            return
        self._selected_id = fila.song.id if fila else None
        if fila is not None:
            self.app_state["selected_song"] = fila.song.id
        self._actualizar_habilitados()
        self._schedule_save()

    # ---------------------------------------------------------- persistencia
    def _schedule_save(self) -> None:
        if self._closing:
            return
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(600, self._save_debounced)

    def _save_debounced(self) -> bool:
        self._save_source = 0
        self._save_now()
        return False

    def _save_now(self) -> None:
        self.app_state["order"] = self.playlist.ids
        if self.controller.current_id:
            self.app_state["last_song"] = self.controller.current_id
            if self.player.is_playing() or self.player.is_paused():
                self.app_state["position"] = self.player.position()
            else:
                self.app_state["position"] = 0.0
        self.app_state["selected_song"] = self._selected_id or self.app_state.get("selected_song")
        self.app_state["volume"] = self.player.get_volume()
        save_state(self.app_state, self.state_path)

    def _autosave(self) -> bool:
        if self._closing:
            return False
        if self.player.is_playing():
            self._save_now()
        return True

    def _on_close_request(self, *_args) -> bool:
        self._closing = True
        if self.mini is not None:
            self.mini.guardar_posicion()
        for fuente in (self._save_source, self._volume_source):
            if fuente:
                GLib.source_remove(fuente)
        self._save_now()
        self.player.shutdown()
        aplicacion = self.get_application()
        if aplicacion is not None:
            GLib.idle_add(aplicacion.quit)
        return False

    def _toast(self, mensaje: str) -> None:
        toast = Adw.Toast(title=mensaje)
        toast.set_timeout(4)
        self.toasts.add_toast(toast)


class MeloApplication(Adw.Application):
    def __init__(self, music_dir: Path | None = None, state_path: Path | None = None,
                 audio_sink: str | None = None, smoke_test: bool = False,
                 smoke_mini: bool = False, smoke_continuity: bool = False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.music_dir = music_dir or get_music_dir()
        self.state_path = state_path
        self.audio_sink = audio_sink
        self.smoke_test = smoke_test
        self.smoke_mini = smoke_mini
        self.smoke_continuity = smoke_continuity
        self._main_window = None
        self._continuity: dict = {}
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app) -> None:
        Gtk.Window.set_default_icon_name(ICON_NAME)
        proveedor = Gtk.CssProvider()
        proveedor.load_from_string(CSS)
        pantalla = Gdk.Display.get_default()
        if pantalla is not None:
            Gtk.StyleContext.add_provider_for_display(
                pantalla, proveedor, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        ventana = MainWindow(
            application=self,
            music_dir=self.music_dir,
            state_path=self.state_path,
            audio_sink=self.audio_sink,
            smoke_test=self.smoke_test,
        )
        self._main_window = ventana
        if ventana.app_state.get("window_mode") == "mini":
            ventana.mostrar_mini()
        else:
            ventana.present()
        if self.smoke_mini:
            GLib.timeout_add(1200, self._smoke_mini_iniciar)
        if self.smoke_continuity:
            self._continuity = {
                "fase": 0,
                "track": None,
                "base": 0.0,
                "marca": time.monotonic(),
                "resultados": [],
            }
            GLib.timeout_add(200, self._continuity_paso)

    # --------------------------------------------------------- smoke mini
    def _smoke_mini_iniciar(self) -> bool:
        self._smoke_mini_esperar(self._main_window, time.monotonic() + 15.0)
        return False

    def _smoke_mini_esperar(self, ventana, limite: float) -> bool:
        if ventana is None:
            return False
        if time.monotonic() > limite:
            print("SMOKE-MINI: FALLO: no hubo reproducción a tiempo")
            self.quit()
            return False
        if ventana._scanning or len(ventana.playlist) == 0:
            GLib.timeout_add(200, self._smoke_mini_esperar, ventana, limite)
            return False
        if not ventana.player.is_playing():
            if not ventana.player.has_media() or ventana.controller.current_id is None:
                cancion = ventana.playlist.get(ventana.controller.current_id) or ventana.playlist[0]
                ventana.controller.play_song(cancion.id, autoplay=True)
            elif ventana.player.is_paused():
                ventana.player.play()
        if ventana.player.is_playing() and ventana.player.position() > 0.3:
            ventana.mostrar_mini()
            GLib.timeout_add(600, self._smoke_mini_comprobar)
            return False
        GLib.timeout_add(200, self._smoke_mini_esperar, ventana, limite)
        return False

    def _smoke_mini_comprobar(self) -> bool:
        from . import windowing

        ventana = self._main_window
        mini = ventana.mini if ventana else None
        cancion = ventana.playlist.get(ventana.controller.current_id) if ventana else None
        print("SMOKE-MINI: modo:", ventana.app_state.get("window_mode") if ventana else None)
        print("SMOKE-MINI: principal visible:", ventana.get_visible() if ventana else None)
        print("SMOKE-MINI: mini visible:", mini.get_visible() if mini else None)
        print("SMOKE-MINI: título mini:", mini.title_label.get_text() if mini else None)
        print("SMOKE-MINI: canción:", cancion.title if cancion else None)
        print("SMOKE-MINI: reproduciendo:", ventana.player.is_playing() if ventana else None)
        print("SMOKE-MINI: posición:", round(ventana.player.position(), 2) if ventana else None)
        print("SMOKE-MINI: carátula:", mini.cover_stack.get_visible_child_name() if mini else None)
        print("SMOKE-MINI: x11:", windowing.x11_available())
        print("SMOKE-MINI: posicion viable:", windowing.positioning_supported())
        xid = windowing.window_xid(mini) if mini else None
        print("SMOKE-MINI: xid:", xid)
        print("SMOKE-MINI: above:", windowing.get_above(mini) if mini else None)
        if xid:
            try:
                salida = subprocess.run(
                    ["xprop", "-id", str(xid), "_NET_WM_STATE"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                print("SMOKE-MINI: xprop:", salida.stdout.strip() or salida.stderr.strip())
            except Exception as exc:
                print("SMOKE-MINI: xprop error:", exc)

        if mini is not None and ventana is not None:
            antes = ventana.controller.current_id
            mini.btn_play.emit("clicked")
            print("SMOKE-MINI: tras botón play/pausa:", ventana.player.is_playing())
            mini.btn_play.emit("clicked")
            if len(ventana.playlist) >= 2:
                mini.btn_siguiente.emit("clicked")
                print("SMOKE-MINI: tras siguiente cambió:", antes != ventana.controller.current_id)
                mini.btn_anterior.emit("clicked")
                print("SMOKE-MINI: tras anterior volvió:", antes == ventana.controller.current_id)
            else:
                print("SMOKE-MINI: siguiente/anterior omitidos: solo hay una pista")
            mini.btn_restaurar.emit("clicked")
            print("SMOKE-MINI: tras restaurar principal visible:", ventana.get_visible(),
                  "mini visible:", mini.get_visible(),
                  "modo:", ventana.app_state.get("window_mode"))
        GLib.timeout_add(400, self._smoke_mini_cerrar)
        return False

    def _smoke_mini_cerrar(self) -> bool:
        self.quit()
        return False

    # ---------------------------------------------------- smoke continuidad
    def _continuity_log(self, fase: str) -> None:
        from . import windowing

        ventana = self._main_window
        mini = ventana.mini
        posicion = ventana.player.position()
        estable = ventana.controller.current_id == self._continuity["track"]
        print(
            f"CONTINUIDAD: fase: {fase} | playing: {ventana.player.is_playing()} "
            f"| pos: {posicion:.2f} | modo: {ventana.app_state.get('window_mode')} "
            f"| principal: {ventana.get_visible()} "
            f"| mini: {bool(mini and mini.get_visible())} | pista_estable: {estable}"
        )
        self._continuity["resultados"].append((fase, ventana.player.is_playing(), posicion, estable))
        if fase == "mini" and mini is not None:
            xid = windowing.window_xid(mini)
            above = windowing.get_above(mini)
            print("CONTINUIDAD: always_on_top:", above, "xid:", xid)
            if xid:
                try:
                    salida = subprocess.run(
                        ["xprop", "-id", str(xid), "_NET_WM_STATE"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    print("CONTINUIDAD: xprop:", salida.stdout.strip() or salida.stderr.strip())
                except Exception as exc:
                    print("CONTINUIDAD: xprop error:", exc)

    def _continuity_fallar(self, motivo: str) -> None:
        print("CONTINUIDAD: FALLO:", motivo)
        GLib.idle_add(self.quit)

    def _continuity_paso(self) -> bool:
        ventana = self._main_window
        if ventana is None:
            return True
        estado = self._continuity
        ahora = time.monotonic()
        if ahora - estado["marca"] > 15.0:
            self._continuity_fallar(f"tiempo agotado en la fase {estado['fase']}")
            return False

        if estado["fase"] == 0:
            if ventana._scanning or len(ventana.playlist) == 0:
                return True
            if not ventana.get_visible():
                ventana.restaurar_principal()
            if estado["track"] is None:
                cancion = ventana.playlist.get(ventana.controller.current_id) or ventana.playlist[0]
                estado["track"] = cancion.id
                ventana.controller.play_song(cancion.id, autoplay=True)
                estado["marca"] = ahora
                return True
            if not ventana.player.is_playing() or ventana.player.position() < 0.5:
                return True
            self._continuity_log("principal")
            estado["base"] = ventana.player.position()
            ventana.mostrar_mini()
            estado["fase"] = 1
            estado["marca"] = ahora
            return True

        if estado["fase"] == 1:
            if ventana.controller.current_id != estado["track"]:
                self._continuity_fallar("la pista cambió al entrar en modo mini")
                return False
            mini_visible = bool(ventana.mini and ventana.mini.get_visible())
            if (ventana.player.is_playing() and mini_visible and not ventana.get_visible()
                    and ventana.player.position() >= estado["base"] + 0.8):
                self._continuity_log("mini")
                estado["base"] = ventana.player.position()
                ventana.restaurar_principal()
                estado["fase"] = 2
                estado["marca"] = ahora
            return True

        if ventana.controller.current_id != estado["track"]:
            self._continuity_fallar("la pista cambió al volver a la ventana principal")
            return False
        mini_visible = bool(ventana.mini and ventana.mini.get_visible())
        if (ventana.player.is_playing() and ventana.get_visible() and not mini_visible
                and ventana.player.position() >= estado["base"] + 0.8):
            self._continuity_log("principal_final")
            resultados = estado["resultados"]
            posiciones = [r[2] for r in resultados]
            ok = (
                len(resultados) == 3
                and all(r[1] and r[3] for r in resultados)
                and posiciones[0] < posiciones[1] < posiciones[2]
            )
            if ok:
                print(
                    "CONTINUIDAD: OK — playing=True y posición creciente "
                    f"({posiciones[0]:.2f} < {posiciones[1]:.2f} < {posiciones[2]:.2f}) "
                    "en principal, mini y principal."
                )
            else:
                print("CONTINUIDAD: FALLO — revisar los resultados anteriores.")
            GLib.idle_add(self.quit)
            return False
        return True
