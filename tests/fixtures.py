"""Utilidades compartidas por las pruebas: genera audio real con ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg")

EXTENSIONES_CODEC = {
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
    ".flac": ["-c:a", "flac"],
    ".wav": ["-c:a", "pcm_s16le"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "4"],
    ".opus": ["-c:a", "libopus", "-b:a", "96k"],
    ".m4a": ["-c:a", "aac", "-b:a", "128k"],
}


def make_audio(
    path: Path,
    duracion: float = 1.0,
    frecuencia: int = 440,
    titulo: str | None = None,
    artista: str | None = None,
    album: str | None = None,
) -> Path:
    """Genera un tono real en el formato indicado por la extensión."""
    if FFMPEG is None:
        raise RuntimeError("ffmpeg no está disponible")
    path.parent.mkdir(parents=True, exist_ok=True)
    codificador = EXTENSIONES_CODEC[path.suffix.lower()]
    comando = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frecuencia}:duration={duracion}",
    ]
    if titulo is not None:
        comando += ["-metadata", f"title={titulo}"]
    if artista is not None:
        comando += ["-metadata", f"artist={artista}"]
    if album is not None:
        comando += ["-metadata", f"album={album}"]
    comando += ["-vn", *codificador, str(path)]
    subprocess.run(comando, check=True, capture_output=True)
    return path
