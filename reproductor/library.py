"""Detección de la carpeta Música, escaneo recursivo y metadatos."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

try:
    import mutagen
except ImportError:  # pragma: no cover - la app avisa al arrancar
    mutagen = None

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac"}


@dataclass(frozen=True)
class Song:
    """Una pista de la biblioteca. `id` es la ruta real (sin enlaces simbólicos)."""

    id: str
    path: str
    title: str
    artist: str | None = None
    album: str | None = None
    duration: float | None = None

    def subtitle(self) -> str:
        partes = [p for p in (self.artist, self.album) if p]
        return " · ".join(partes)


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _parse_user_dirs() -> dict[str, str]:
    """Lee ~/.config/user-dirs.dirs sin depender de GLib (útil para tests)."""
    config = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config"))
    archivo = config / "user-dirs.dirs"
    valores: dict[str, str] = {}
    try:
        texto = archivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return valores
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = valor.strip().strip('"')
        valor = valor.replace("$HOME", str(_home()))
        valores[clave.strip()] = valor
    return valores


def get_music_dir() -> Path:
    """Ruta de la carpeta Música según XDG User Directories."""
    try:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        ruta = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC)
        if ruta:
            return Path(ruta)
    except Exception:
        pass

    valor = _parse_user_dirs().get("XDG_MUSIC_DIR")
    if valor:
        return Path(valor)
    for candidata in (_home() / "Music", _home() / "Música"):
        if candidata.is_dir():
            return candidata
    return _home() / "Music"


def _first_tag(tags, claves: tuple[str, ...]) -> str | None:
    if not tags:
        return None
    for clave in claves:
        try:
            valor = tags.get(clave)
        except Exception:
            valor = None
        if isinstance(valor, (list, tuple)):
            valor = valor[0] if valor else None
        if valor is None:
            continue
        texto = str(valor).strip()
        if texto:
            return texto
    return None


def read_metadata(path: str) -> tuple[str | None, str | None, str | None, float | None]:
    """Devuelve (título, artista, álbum, duración) tolerando archivos rotos."""
    if mutagen is None:
        return None, None, None, None
    try:
        audio = mutagen.File(path, easy=True)
    except Exception:
        return None, None, None, None
    if audio is None:
        return None, None, None, None
    tags = getattr(audio, "tags", None)
    titulo = _first_tag(tags, ("title",))
    artista = _first_tag(tags, ("artist", "albumartist"))
    album = _first_tag(tags, ("album",))
    duracion = None
    try:
        duracion = float(audio.info.length)
        if duracion <= 0:
            duracion = None
    except Exception:
        duracion = None
    return titulo, artista, album, duracion


def make_song(path: str) -> Song | None:
    """Crea una Song a partir de una ruta; None si no es un archivo legible."""
    try:
        real = os.path.realpath(path)
        info = os.stat(real)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    titulo, artista, album, duracion = read_metadata(real)
    if not titulo:
        titulo = os.path.splitext(os.path.basename(real))[0]
    return Song(
        id=real,
        path=real,
        title=titulo or os.path.basename(real),
        artist=artista,
        album=album,
        duration=duracion,
    )


def iter_audio_files(root: Path):
    """Recorre root recursivamente y produce archivos con extensión de audio."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for nombre in sorted(filenames):
            if Path(nombre).suffix.lower() in AUDIO_EXTENSIONS:
                yield Path(dirpath) / nombre


def scan_library(root: Path | str) -> list[Song]:
    """Escanea la carpeta y devuelve canciones sin duplicados (por ruta real)."""
    raiz = Path(root)
    canciones: dict[str, Song] = {}
    if not raiz.is_dir():
        return []
    for archivo in iter_audio_files(raiz):
        cancion = make_song(str(archivo))
        if cancion is None:
            continue
        canciones.setdefault(cancion.id, cancion)
    return sorted(canciones.values(), key=lambda s: s.path.casefold())
