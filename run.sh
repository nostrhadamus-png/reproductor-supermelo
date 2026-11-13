#!/usr/bin/env bash
# Ejecuta el reproductor desde cualquier directorio.
set -euo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# El modo "siempre encima" del mini reproductor usa EWMH (X11). En GNOME
# Wayland se ejecuta bajo XWayland, que está disponible si DISPLAY no está vacío.
# Respeta un GDK_BACKEND elegido explícitamente por el usuario.
if [[ -z "${GDK_BACKEND:-}" && -n "${DISPLAY:-}" ]]; then
    export GDK_BACKEND=x11
fi

exec python3 -m reproductor "$@"
