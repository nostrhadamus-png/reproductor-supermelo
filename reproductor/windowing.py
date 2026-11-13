"""Soporte X11 opcional: siempre encima y posición de ventana.

En Wayland una aplicación normal no puede fijarse encima ni mover su ventana
desde código. Si la sesión es X11 (o la app se ejecuta bajo XWayland con
``GDK_BACKEND=x11``), usamos mensajes EWMH ``_NET_WM_STATE`` y ``XMoveWindow``
mediante ctypes + libX11. Sin dependencias nuevas.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from typing import Optional

_CLIENT_MESSAGE = 33
_SUBSTRUCTURE_REDIRECT_MASK = 1 << 20
_SUBSTRUCTURE_NOTIFY_MASK = 1 << 19

_lib: Optional[ctypes.CDLL] = None
_lib_intentada = False


class _XClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", _XClientMessageData),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_long * 24),
    ]


def _cargar_libx11() -> Optional[ctypes.CDLL]:
    global _lib, _lib_intentada
    if _lib_intentada:
        return _lib
    _lib_intentada = True
    nombre = ctypes.util.find_library("X11") or "libX11.so.6"
    try:
        lib = ctypes.CDLL(nombre)
    except OSError:
        _lib = None
        return None

    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XCloseDisplay.restype = ctypes.c_int
    lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib.XDefaultRootWindow.restype = ctypes.c_ulong
    lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.XInternAtom.restype = ctypes.c_ulong
    lib.XSendEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.POINTER(_XEvent),
    ]
    lib.XSendEvent.restype = ctypes.c_int
    lib.XFlush.argtypes = [ctypes.c_void_p]
    lib.XFlush.restype = ctypes.c_int
    lib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
    lib.XMoveWindow.restype = ctypes.c_int
    lib.XGetGeometry.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
    ]
    lib.XGetGeometry.restype = ctypes.c_int
    lib.XGetWindowProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
    ]
    lib.XGetWindowProperty.restype = ctypes.c_int
    lib.XFree.argtypes = [ctypes.c_void_p]
    lib.XFree.restype = ctypes.c_int

    _lib = lib
    return _lib


def x11_available() -> bool:
    """True si la pantalla GDK actual es X11 (incluido XWayland)."""
    try:
        import gi

        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        return display is not None and "X11" in type(display).__name__
    except Exception:
        return False


def positioning_supported() -> bool:
    """True solo si el servidor X permite posicionar ventanas de verdad.

    En una sesión Wayland con XWayland, GNOME ignora ``XMoveWindow`` y
    ``_NET_MOVERESIZE_WINDOW`` (el compositor coloca la ventana), así que no
    guardamos ni restauramos posición para no prometer algo falso.
    """
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return False
    return x11_available()


def window_xid(window) -> int | None:
    try:
        surface = window.get_surface()
        if surface is None:
            return None
        xid = surface.get_xid()
        return int(xid) if xid else None
    except Exception:
        return None


def set_above(window, above: bool) -> bool:
    """Añade o quita ``_NET_WM_STATE_ABOVE``. Devuelve True si se envió."""
    xid = window_xid(window)
    lib = _cargar_libx11()
    if xid is None or lib is None:
        return False
    display = lib.XOpenDisplay(os.environ.get("DISPLAY", "").encode() or None)
    if not display:
        return False
    try:
        root = lib.XDefaultRootWindow(display)
        estado = lib.XInternAtom(display, b"_NET_WM_STATE", False)
        encima = lib.XInternAtom(display, b"_NET_WM_STATE_ABOVE", False)
        if not estado or not encima:
            return False

        evento = _XEvent()
        evento.xclient.type = _CLIENT_MESSAGE
        evento.xclient.serial = 0
        evento.xclient.send_event = 1
        evento.xclient.display = display
        evento.xclient.window = xid
        evento.xclient.message_type = estado
        evento.xclient.format = 32
        evento.xclient.data.l[0] = 1 if above else 0
        evento.xclient.data.l[1] = encima
        evento.xclient.data.l[2] = 0
        evento.xclient.data.l[3] = 1
        evento.xclient.data.l[4] = 0

        enviado = lib.XSendEvent(
            display,
            root,
            False,
            _SUBSTRUCTURE_REDIRECT_MASK | _SUBSTRUCTURE_NOTIFY_MASK,
            ctypes.byref(evento),
        )
        lib.XFlush(display)
        return bool(enviado)
    except Exception:
        return False
    finally:
        try:
            lib.XCloseDisplay(display)
        except Exception:
            pass


def get_above(window) -> bool:
    """Lee ``_NET_WM_STATE`` y comprueba si contiene ABOVE (para pruebas)."""
    xid = window_xid(window)
    lib = _cargar_libx11()
    if xid is None or lib is None:
        return False
    display = lib.XOpenDisplay(os.environ.get("DISPLAY", "").encode() or None)
    if not display:
        return False
    try:
        estado = lib.XInternAtom(display, b"_NET_WM_STATE", False)
        encima = lib.XInternAtom(display, b"_NET_WM_STATE_ABOVE", False)
        tipo = ctypes.c_ulong()
        formato = ctypes.c_int()
        cantidad = ctypes.c_ulong()
        restante = ctypes.c_ulong()
        datos = ctypes.POINTER(ctypes.c_ulong)()
        resultado = lib.XGetWindowProperty(
            display,
            xid,
            estado,
            0,
            64,
            False,
            0,
            ctypes.byref(tipo),
            ctypes.byref(formato),
            ctypes.byref(cantidad),
            ctypes.byref(restante),
            ctypes.byref(datos),
        )
        if resultado != 0 or not datos:
            return False
        try:
            if formato.value != 32:
                return False
            return any(datos[i] == encima for i in range(cantidad.value))
        finally:
            lib.XFree(datos)
    except Exception:
        return False
    finally:
        try:
            lib.XCloseDisplay(display)
        except Exception:
            pass


def get_window_position(window) -> tuple[int, int] | None:
    xid = window_xid(window)
    lib = _cargar_libx11()
    if xid is None or lib is None:
        return None
    display = lib.XOpenDisplay(os.environ.get("DISPLAY", "").encode() or None)
    if not display:
        return None
    try:
        raiz = ctypes.c_ulong()
        x = ctypes.c_int()
        y = ctypes.c_int()
        ancho = ctypes.c_uint()
        alto = ctypes.c_uint()
        borde = ctypes.c_uint()
        profundidad = ctypes.c_uint()
        ok = lib.XGetGeometry(
            display,
            xid,
            ctypes.byref(raiz),
            ctypes.byref(x),
            ctypes.byref(y),
            ctypes.byref(ancho),
            ctypes.byref(alto),
            ctypes.byref(borde),
            ctypes.byref(profundidad),
        )
        if not ok:
            return None
        return int(x.value), int(y.value)
    except Exception:
        return None
    finally:
        try:
            lib.XCloseDisplay(display)
        except Exception:
            pass


def move_window(window, x: int, y: int) -> bool:
    xid = window_xid(window)
    lib = _cargar_libx11()
    if xid is None or lib is None:
        return False
    display = lib.XOpenDisplay(os.environ.get("DISPLAY", "").encode() or None)
    if not display:
        return False
    try:
        lib.XMoveWindow(display, xid, int(x), int(y))
        lib.XFlush(display)
        return True
    except Exception:
        return False
    finally:
        try:
            lib.XCloseDisplay(display)
        except Exception:
            pass
