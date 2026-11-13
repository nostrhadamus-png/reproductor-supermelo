"""Búsqueda de carátulas: metadatos incrustados y archivos de la carpeta.

La parte de reglas (nombres de archivo, orden de búsqueda) no depende de GTK y
se puede probar sin pantalla. La decodificación usa GdkPixbuf, que tampoco
necesita un servidor gráfico.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

try:
    import mutagen
except ImportError:  # pragma: no cover - la app funciona sin metadatos
    mutagen = None

COVER_BASENAMES = ("cover", "folder", "front")
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MAX_COVER_SIDE = 512


def _picture_bytes(picture) -> bytes | None:
    try:
        data = getattr(picture, "data", None)
    except Exception:
        return None
    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data)
    return None


def _embedded_from_tags(tags) -> bytes | None:
    if tags is None:
        return None

    # MP3/WAV con etiquetas ID3 (APIC).
    try:
        apics = tags.getall("APIC")
    except Exception:
        apics = []
    for apic in apics or []:
        data = _picture_bytes(apic)
        if data:
            return data

    # M4A/MP4 (covr).
    try:
        covr = tags.get("covr")
    except Exception:
        covr = None
    if covr is not None:
        elementos = covr if isinstance(covr, (list, tuple)) else [covr]
        for elemento in elementos:
            try:
                data = bytes(elemento)
            except Exception:
                continue
            if data:
                return data

    # OGG/OPUS (METADATA_BLOCK_PICTURE en base64).
    try:
        bloques = tags.get("metadata_block_picture")
    except Exception:
        bloques = None
    if bloques is not None:
        elementos = bloques if isinstance(bloques, (list, tuple)) else [bloques]
        for bloque in elementos:
            try:
                if isinstance(bloque, str):
                    bloque = bloque.encode("ascii")
                crudo = base64.b64decode(bloque)
                from mutagen.flac import Picture

                data = _picture_bytes(Picture(crudo))
            except Exception:
                continue
            if data:
                return data

    return None


def read_embedded_cover(path: str | os.PathLike) -> bytes | None:
    """Devuelve la imagen incrustada o None si no existe o no se puede leer."""
    if mutagen is None:
        return None
    try:
        audio = mutagen.File(str(path))
    except Exception:
        return None
    if audio is None:
        return None

    # FLAC y algunos formatos exponen las imágenes como objetos Picture.
    try:
        pictures = getattr(audio, "pictures", None)
    except Exception:
        pictures = None
    for picture in pictures or []:
        data = _picture_bytes(picture)
        if data:
            return data

    try:
        tags = getattr(audio, "tags", None)
    except Exception:
        tags = None
    return _embedded_from_tags(tags)


def find_cover_file(song_path: str | os.PathLike) -> Path | None:
    """Busca cover/folder/front/albumart* en la carpeta, sin distinguir mayúsculas."""
    try:
        carpeta = Path(song_path).parent
        entradas = [entrada for entrada in carpeta.iterdir() if entrada.is_file()]
    except OSError:
        return None

    por_nombre = {entrada.name.casefold(): entrada for entrada in entradas}

    for base in COVER_BASENAMES:
        for extension in COVER_EXTENSIONS:
            encontrada = por_nombre.get(base + extension)
            if encontrada is not None:
                return encontrada

    candidatas = sorted(
        (
            entrada
            for nombre, entrada in por_nombre.items()
            if nombre.startswith("albumart") and Path(nombre).suffix in COVER_EXTENSIONS
        ),
        key=lambda entrada: entrada.name.casefold(),
    )
    return candidatas[0] if candidatas else None


def get_cover_bytes(song_path: str | os.PathLike) -> tuple[bytes | None, str]:
    """Devuelve (datos, origen) con origen ``embedded``, ``folder`` o ``none``."""
    incrustada = read_embedded_cover(song_path)
    if incrustada:
        return incrustada, "embedded"

    archivo = find_cover_file(song_path)
    if archivo is not None:
        try:
            datos = archivo.read_bytes()
        except OSError:
            datos = b""
        if datos:
            return datos, "folder"

    return None, "none"


def decode_cover(data: bytes | None, max_side: int = MAX_COVER_SIDE):
    """Decodifica y limita el tamaño; devuelve un GdkPixbuf o None si es inválida."""
    if not data:
        return None
    try:
        import gi

        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf, Gio, GLib

        flujo = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream(flujo, None)
        if pixbuf is None:
            return None
        ancho, alto = pixbuf.get_width(), pixbuf.get_height()
        if max_side > 0 and max(ancho, alto) > max_side:
            factor = max_side / float(max(ancho, alto))
            pixbuf = pixbuf.scale_simple(
                max(1, int(ancho * factor)),
                max(1, int(alto * factor)),
                GdkPixbuf.InterpType.BILINEAR,
            )
        return pixbuf
    except Exception:
        return None


def load_cover_pixbuf(song_path: str | os.PathLike, max_side: int = MAX_COVER_SIDE):
    """Atajo: bytes (incrustados o de carpeta) -> GdkPixbuf validado o None."""
    datos, _origen = get_cover_bytes(song_path)
    return decode_cover(datos, max_side=max_side)
