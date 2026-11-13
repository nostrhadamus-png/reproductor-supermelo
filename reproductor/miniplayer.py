"""Ventana mini reproductora: misma instancia de Player y Playlist que la principal."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import windowing  # noqa: E402
from .state import validate_mini_position  # noqa: E402

MINI_WIDTH = 340
MINI_HEIGHT = 100
MINI_MARGIN = 8


class MiniPlayer(Gtk.Window):
    """Ventana compacta que comparte motor, playlist y estado con la principal."""

    def __init__(self, main):
        super().__init__(application=main.get_application(), title="Mini reproductor")
        self.main = main
        self._song = None
        self._x11 = windowing.x11_available()
        self._posicion_viable = windowing.positioning_supported()
        self._above = bool(main.app_state.get("mini", {}).get("always_on_top", True))
        self._posicion_restaurada = False
        self._pos_source = 0

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(MINI_WIDTH, MINI_HEIGHT)
        self.set_size_request(MINI_WIDTH, MINI_HEIGHT)
        self.set_title("Reproductor Melo — mini")
        self.add_css_class("mini-player")

        self._build_ui()
        self.connect("map", self._on_map)
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", self._on_destroy)

        self._pos_source = GLib.timeout_add_seconds(1, self._seguir_posicion)
        self.actualizar_desde_estado()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        manejador = Gtk.WindowHandle()
        caja = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        caja.set_margin_top(8)
        caja.set_margin_bottom(8)
        caja.set_margin_start(8)
        caja.set_margin_end(8)

        self.cover_stack = Gtk.Stack()
        self.cover_stack.set_size_request(64, 64)
        self.cover_stack.set_valign(Gtk.Align.CENTER)
        self.cover_stack.set_halign(Gtk.Align.CENTER)
        self.cover_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        self.cover_picture = Gtk.Picture()
        self.cover_picture.set_size_request(64, 64)
        self.cover_picture.set_can_shrink(True)
        self.cover_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.cover_picture.add_css_class("mini-cover")

        self.cover_generic = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        self.cover_generic.set_pixel_size(48)
        self.cover_generic.add_css_class("dim-label")

        self.cover_stack.add_named(self.cover_picture, "cover")
        self.cover_stack.add_named(self.cover_generic, "generic")
        self.cover_stack.set_visible_child_name("generic")
        caja.append(self.cover_stack)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)
        self.title_label = Gtk.Label(label="Sin reproducción", xalign=0)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_lines(1)
        self.title_label.add_css_class("now-title")
        self.sub_label = Gtk.Label(label="Selecciona una canción", xalign=0)
        self.sub_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub_label.set_lines(1)
        self.sub_label.add_css_class("dim-label")
        info.append(self.title_label)
        info.append(self.sub_label)
        caja.append(info)

        derecha = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        derecha.set_valign(Gtk.Align.CENTER)

        superior = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        superior.set_halign(Gtk.Align.END)

        self.btn_restaurar = Gtk.Button(icon_name="view-restore-symbolic")
        self.btn_restaurar.set_tooltip_text("Restaurar ventana principal")
        self.btn_restaurar.add_css_class("flat")
        self.btn_restaurar.connect("clicked", lambda *_: self.main.restaurar_principal())
        superior.append(self.btn_restaurar)

        self._switch_arriba = Gtk.Switch()
        self._switch_arriba.set_active(self._above)
        self._switch_arriba.set_valign(Gtk.Align.CENTER)
        if self._x11:
            self._switch_arriba.set_tooltip_text("Mantener el mini reproductor siempre encima")
        else:
            self._switch_arriba.set_sensitive(False)
            self._switch_arriba.set_tooltip_text(
                "No disponible en Wayland. Ejecuta con GDK_BACKEND=x11 "
                "o usa Alt+Espacio → Siempre encima."
            )
        self._switch_arriba.connect("notify::active", self._on_above_toggled)

        self.btn_menu = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.btn_menu.set_tooltip_text("Opciones del mini reproductor")
        self.btn_menu.add_css_class("flat")
        self.btn_menu.set_popover(self._build_popover())
        superior.append(self.btn_menu)

        self.btn_cerrar = Gtk.Button(icon_name="window-close-symbolic")
        self.btn_cerrar.set_tooltip_text("Restaurar la ventana principal y cerrar el mini")
        self.btn_cerrar.add_css_class("flat")
        self.btn_cerrar.connect("clicked", lambda *_: self.main.restaurar_principal())
        superior.append(self.btn_cerrar)
        derecha.append(superior)

        controles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        controles.set_halign(Gtk.Align.END)

        self.btn_anterior = Gtk.Button(icon_name="media-skip-backward-symbolic")
        self.btn_anterior.set_tooltip_text("Canción anterior")
        self.btn_anterior.add_css_class("flat")
        self.btn_anterior.connect("clicked", lambda *_: self.main.controller.previous())
        controles.append(self.btn_anterior)

        self.btn_play = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.btn_play.set_tooltip_text("Reproducir")
        self.btn_play.add_css_class("circular")
        self.btn_play.add_css_class("suggested-action")
        self.btn_play.connect("clicked", self._on_play_clicked)
        controles.append(self.btn_play)

        self.btn_siguiente = Gtk.Button(icon_name="media-skip-forward-symbolic")
        self.btn_siguiente.set_tooltip_text("Canción siguiente")
        self.btn_siguiente.add_css_class("flat")
        self.btn_siguiente.connect("clicked", lambda *_: self.main.controller.next())
        controles.append(self.btn_siguiente)
        derecha.append(controles)

        caja.append(derecha)
        manejador.set_child(caja)
        self.set_child(manejador)

    def _build_popover(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caja.set_margin_top(10)
        caja.set_margin_bottom(10)
        caja.set_margin_start(12)
        caja.set_margin_end(12)

        fila = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        etiqueta = Gtk.Label(label="Siempre encima", xalign=0)
        etiqueta.set_hexpand(True)
        fila.append(etiqueta)
        fila.append(self._switch_arriba)
        caja.append(fila)

        if not self._x11:
            aviso = Gtk.Label(
                label="Wayland no permite fijar ventanas. Usa Alt+Espacio → Siempre encima\n"
                "o ejecuta la app con GDK_BACKEND=x11.",
                xalign=0,
            )
            aviso.set_wrap(True)
            aviso.set_max_width_chars(38)
            aviso.add_css_class("dim-label")
            caja.append(aviso)

        popover.set_child(caja)
        return popover

    # ------------------------------------------------------------- estado
    def actualizar_desde_estado(self) -> None:
        cancion = self.main.playlist.get(self.main.controller.current_id)
        self.set_song(cancion)
        self.update_play_icon()

    def set_song(self, song) -> None:
        self._song = song
        if song is None:
            self.title_label.set_label("Sin reproducción")
            self.sub_label.set_label("Selecciona una canción")
            self.cover_stack.set_visible_child_name("generic")
            return
        self.title_label.set_label(song.title)
        self.sub_label.set_label(song.subtitle() or "Archivo local")
        textura = self.main.get_cover_texture(song)
        if textura is not None:
            self.cover_picture.set_paintable(textura)
            self.cover_stack.set_visible_child_name("cover")
        else:
            self.cover_stack.set_visible_child_name("generic")

    def update_play_icon(self) -> None:
        if self.main.player.is_playing():
            self.btn_play.set_icon_name("media-playback-pause-symbolic")
            self.btn_play.set_tooltip_text("Pausar")
        else:
            self.btn_play.set_icon_name("media-playback-start-symbolic")
            self.btn_play.set_tooltip_text("Reproducir")

    # ------------------------------------------------------------ acciones
    def _on_play_clicked(self, *_args) -> None:
        self.main.reproducir_pausar()
        GLib.idle_add(self.update_play_icon)

    def _on_above_toggled(self, interruptor: Gtk.Switch, _pspec) -> None:
        self._above = bool(interruptor.get_active())
        self.main.app_state.setdefault("mini", {})["always_on_top"] = self._above
        if self._x11:
            windowing.set_above(self, self._above)
        self.main._schedule_save()

    # -------------------------------------------------- siempre encima / pos
    def _on_map(self, *_args) -> None:
        GLib.timeout_add(120, self._aplicar_estado_ventana)

    def _aplicar_estado_ventana(self) -> bool:
        if not self._x11:
            return False
        windowing.set_above(self, self._above)
        if not self._posicion_restaurada:
            self._posicion_restaurada = True
            self._restaurar_posicion()
        return False

    def _restaurar_posicion(self) -> None:
        if not self._posicion_viable:
            return
        guardada = self.main.app_state.get("mini", {}).get("position")
        if not guardada:
            return
        pantalla = Gdk.Display.get_default()
        if pantalla is None:
            return
        try:
            x, y = int(guardada[0]), int(guardada[1])
            monitor = pantalla.get_monitor_at_point(x, y)
            if monitor is None:
                monitor = pantalla.get_primary_monitor()
            if monitor is None:
                return
            geometria = monitor.get_geometry()
            destino = validate_mini_position(
                (x, y),
                (geometria.x, geometria.y, geometria.width, geometria.height),
                (self.get_width() or MINI_WIDTH, self.get_height() or MINI_HEIGHT),
                margin=MINI_MARGIN,
            )
        except Exception:
            return
        if destino is not None:
            windowing.move_window(self, *destino)

    def guardar_posicion(self) -> None:
        if not self._posicion_viable or not self.get_visible():
            return
        posicion = windowing.get_window_position(self)
        if posicion is None:
            return
        actual = self.main.app_state.setdefault("mini", {}).get("position")
        if actual != [posicion[0], posicion[1]]:
            self.main.app_state["mini"]["position"] = [posicion[0], posicion[1]]
            self.main._schedule_save()

    def _seguir_posicion(self) -> bool:
        if self._posicion_viable and self.get_visible():
            self.guardar_posicion()
        return True

    def _on_destroy(self, *_args) -> None:
        if self._pos_source:
            GLib.source_remove(self._pos_source)
            self._pos_source = 0

    def _on_close_request(self, *_args) -> bool:
        self.guardar_posicion()
        self.main.restaurar_principal()
        return True

    def ocultar(self) -> None:
        self.guardar_posicion()
        self.set_visible(False)
