"""Punto de entrada: `python3 -m reproductor`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reproductor",
        description="Reproductor Melo: música local para Fedora.",
    )
    parser.add_argument("--version", action="version", version=f"Reproductor Melo {__version__}")
    parser.add_argument(
        "--music-dir",
        type=Path,
        default=None,
        help="Carpeta de música alternativa (por defecto, la carpeta Música XDG).",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help="Ruta alternativa del estado JSON (por defecto, XDG_DATA_HOME).",
    )
    parser.add_argument(
        "--audio-sink",
        default=None,
        help="Sumidero GStreamer para depuración (p. ej. fakesink).",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Solo escanear e imprimir la biblioteca detectada, sin abrir la interfaz.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Abrir la interfaz, comprobar el arranque y cerrar automáticamente.",
    )
    parser.add_argument(
        "--smoke-mini",
        action="store_true",
        help="Probar el mini reproductor (modo, botones y siempre encima) y cerrar.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.scan_only:
        from .library import get_music_dir, scan_library

        carpeta = args.music_dir or get_music_dir()
        canciones = scan_library(carpeta)
        print(f"Carpeta Música: {carpeta}")
        print(f"Canciones encontradas: {len(canciones)}")
        for song in canciones:
            extras = " · ".join(p for p in (song.artist, song.album) if p)
            print(f"  - {song.title}" + (f"  [{extras}]" if extras else ""))
            print(f"    {song.path}")
        return 0

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import GLib

    from .app import MeloApplication

    GLib.set_application_name("Reproductor Melo")
    app = MeloApplication(
        music_dir=args.music_dir,
        state_path=args.state_path,
        audio_sink=args.audio_sink,
        smoke_test=args.smoke_test,
        smoke_mini=args.smoke_mini,
    )
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
