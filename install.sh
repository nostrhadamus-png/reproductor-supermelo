#!/usr/bin/env bash
# Instala el lanzador y el icono en las rutas XDG del usuario.
set -euo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"

mkdir -p "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
sed -e "s|@EXEC@|\"$DIR/run.sh\"|g" -e "s|@DIR@|$DIR|g" \
    "$DIR/data/reproductor-melo.desktop.in" > "$DATA/applications/reproductor-melo.desktop"
cp "$DIR/assets/reproductor-melo.svg" "$DATA/icons/hicolor/scalable/apps/reproductor-melo.svg"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$DATA/icons/hicolor" >/dev/null 2>&1 || true

echo "Instalado:"
echo "  $DATA/applications/reproductor-melo.desktop"
echo "  $DATA/icons/hicolor/scalable/apps/reproductor-melo.svg"
echo "Puedes abrirlo desde el menú de aplicaciones o ejecutar: $DIR/run.sh"
