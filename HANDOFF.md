# HANDOFF — Reproductor Melo

Basado en comprobaciones reales (12 nov 2026). Lo no comprobado se marca como
**No verificado**.

## 1. Qué es el proyecto

Reproductor de música local para Fedora/GNOME: detecta la carpeta Música XDG,
escanea subcarpetas, lee metadatos, reproduce y permite reordenar la playlist sin
tocar los archivos. Es personal, local, sin cuentas/nube/streaming/publicidad y
con interfaz en español.

Stack: Python 3.14.10, GTK 4.22.5, libadwaita 1.9.4, GStreamer 1.28.9 y mutagen.
App 1.1.0. Entorno: Fedora 44, sesión Wayland con GNOME; `run.sh` fuerza
`GDK_BACKEND=x11` (XWayland) para «Siempre encima» del mini.

## 2. Ejecutar, instalar y probar

```bash
./run.sh                                  # o: python3 -m reproductor
python3 -m reproductor --music-dir /ruta
python3 -m reproductor --scan-only
./install.sh
PYTHONWARNINGS=ignore python3 -m unittest discover -s tests -q
python3 -m reproductor --audio-sink fakesink --smoke-test
python3 -m reproductor --audio-sink "fakesink sync=true" --smoke-mini
python3 -m reproductor --audio-sink "fakesink sync=true" --smoke-continuity
```

Dependencias Fedora (README): `python3`, `python3-gobject`, `gtk4`,
`libadwaita`, `python3-mutagen`, `gstreamer1`, `gstreamer1-plugins-base`,
`gstreamer1-plugins-good`, `gstreamer1-plugin-libav`.

`install.sh` no instala dependencias: genera
`~/.local/share/applications/reproductor-melo.desktop` desde
`data/reproductor-melo.desktop.in`, copia el icono a
`~/.local/share/icons/hicolor/scalable/apps/reproductor-melo.svg` y actualiza
cachés si están disponibles. Para pruebas, aislar con `dbus-run-session`,
`--state-path` o un `XDG_DATA_HOME` temporal.

## 3. Estado por funcionalidad

| Funcionalidad | Qué hace | Módulo | Verificación |
|---|---|---|---|
| Biblioteca | Escaneo recursivo, metadatos, fallback al nombre y deduplicado por ruta real | `library.py` | `test_library` (7); smoke «canciones: 1» |
| Reproducción | playbin3/playbin, play/pausa, seek, volumen, auto-avance y salto de errores | `player.py`, `playback.py` | `test_player` (10); smoke duración 8,05 s |
| Playlist y drag & drop | Orden en memoria; nunca modifica archivos | `playlist.py`, `app.py` | `test_playlist` (8) |
| Ecualizador | 10 bandas −12…+12 dB, presets, tiempo real y persistencia | `equalizer.py`, `app.py` | `test_equalizer` (5); smoke de preset/slider |
| Mini reproductor | Ventana compacta con carátula y controles; comparte motor y playlist | `miniplayer.py`, `app.py` | `--smoke-mini` (exit 0) |
| Siempre encima | `_NET_WM_STATE_ABOVE` vía EWMH en X11/XWayland | `windowing.py` | smoke: `above: True` + `xprop` |
| Apariencia | Sistema/Claro/Oscuro, 6 paletas, diálogo y cambio en vivo | `theme.py`, `style.css`, `app.py` | `test_theme` (11); arranque oscuro sin warnings; capturas |
| Persistencia | Orden, pista, volumen, posición, EQ, mini y apariencia | `state.py` | `test_state` (16); cerrar/reabrir comprobado |

## 4. Arquitectura

Módulos: `library` (escaneo/metadatos), `playlist` (orden), `state` (JSON),
`equalizer` (bandas/presets), `covers` (carátulas), `player` (GStreamer),
`playback` (secuenciación sin GTK), `windowing` (X11 con ctypes),
`miniplayer`, `theme` (paletas/contraste/CSS sin GTK), `style.css`, `app`
(interfaz) y `__main__` (CLI).

`MainWindow` crea una sola `Playlist`, un `Player` y un `PlaybackController`.
`MiniPlayer(self)` reutiliza `main.playlist`, `main.player`, `main.controller`,
`main.get_cover_texture()` y `main.app_state`; alternar ventanas no reinicia la
reproducción.

Estado: `~/.local/share/reproductor-melo/state.json` (o
`$XDG_DATA_HOME/reproductor-melo/state.json`). Claves: `order`, `last_song`,
`selected_song`, `volume`, `position`, `equalizer`, `window_mode`, `mini`,
`color_scheme`, `palette`. Se escribe con temporal + `fsync` + `os.replace`; JSON
ausente/corrupto usa valores por defecto y los inválidos se sanean.

## 5. Decisiones técnicas

- **X11/XWayland**: necesario para EWMH (siempre encima y posición). Wayland puro
  no lo permite. Efecto secundario: el portal avisa «GDK backend forced via env
  var, portal dialogs will not work properly».
- **`fakesink sync=true`**: reproduce en silencio a velocidad real; `fakesink`
  solo vacía el audio al instante y falsea la continuidad.
- **Lógica separada de GTK**: biblioteca, playlist, estado, EQ y temas se prueban
  sin pantalla; `playback` tampoco conoce GTK.
- **Sin dependencias nuevas**: X11 mediante `ctypes` + `libX11`.
- **CSS dividido**: estático + proveedor generado por `theme.py`, con contraste
  WCAG AA comprobable.
- **Estado atómico** para no corromper el JSON anterior.

## 6. Git

Rama `master`, árbol limpio tras este commit. Estable: `1276832` «feat(theme):
diálogo de apariencia con esquema y paletas en vivo». Historial: `1276832`
apariencia, `48cbb84` paletas/contraste/persistencia, `12e210f` checkpoint,
`49a3db9` mini con continuidad, `e7c3317` mini en curso, `b459fa4` ecualizador.

Volver al estado estable: `git switch master` (o `git switch --detach 1276832`
solo para inspeccionar). La rama `mini-wip` ya está contenida en `master`; es un
resto borrable.

## 7. Verificación

- Tests: **66 OK** en ≈12 s. Reparto: covers 8, equalizer 5, integración 1,
  library 7, player 10, playlist 8, state 16, theme 11.
- `--smoke-test`: exit 0; interfaz, 1 canción, EQ y presets correctos.
- `--smoke-mini`: exit 0; mini visible, reproduciendo, `x11: True`,
  `posicion viable: False` (Wayland), `above: True` y restauración correcta.
- `--smoke-continuity`: exit 0; posición 0,57 → 1,37 → 2,37 s con
  `playing=True` en principal → mini → principal.
- Apariencia: Medianoche/Oscuro sin `Theme parser`, `Gtk-WARNING` ni
  `Gtk-CRITICAL`; las 18 combinaciones de la fase anterior tampoco dieron
  warnings. Capturas en `docs/capturas/`: `ocean-light-main.png` (970×817),
  `forest-dark-eq.png` (970×817) y `medianoche-dark-mini.png` (340×100).

## 8. Limitaciones y deuda técnica

- Posición del mini no se guarda/restaura en Wayland (`positioning_supported`
  es `False`); «Siempre encima» sí funciona bajo XWayland (visto con `xprop`).
- **No verificado**: audio real por PipeWire/altavoces (todo usa `fakesink`).
- **No verificado**: carátula con arte incrustado real (la pista de prueba da
  «carátula: generic»).
- **No verificado**: ejecución de `install.sh` y aparición real del lanzador
  (solo se leyó).
- Verificación visual limitada a 3 capturas; el resto se cubre con tests de
  CSS/contraste y arranques de humo.
- Discrepancias: README no lista `ffmpeg` (necesario para tests; presente 8.1.3)
  e `install.sh` no instala dependencias. No hay `TODO`/`FIXME`/`XXX`/`HACK` ni
  código muerto evidente; sí la rama sobrante `mini-wip`.

## 9. Próximos pasos sugeridos

Pulido visual (carátula en la barra inferior, filas y espaciados), modo aleatorio
y repetir, buscador, preamplificador del ecualizador y presets propios.

## 10. Guía para el siguiente agente

- Una sesión nueva por tarea (el contexto se satura hacia el 80 %).
- Cambios mínimos y localizados; editar con la herramienta de edición, no con
  scripts de reemplazo.
- Sin dependencias nuevas. Preguntar solo antes de `sudo`/`dnf`.
- No tocar los archivos de música.
- Commit tras cada fase y pruebas en modo silencioso.
- No interferir con la instancia/estado reales del usuario: usar
  `dbus-run-session` y `XDG_DATA_HOME` temporal.
- Ser honesto sobre lo «verificado» frente a lo «no verificable aquí».
- Estructura de prompt: nota de git, Fase 0 breve, reglas, funcionalidad,
  verificación y tabla final.
