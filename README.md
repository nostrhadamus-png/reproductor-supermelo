# Reproductor Melo

Reproductor de música de escritorio nativo para Fedora/GNOME. Detecta la carpeta
Música del usuario (XDG), escanea sus subcarpetas, reproduce los formatos habituales
y permite reorganizar la playlist con arrastrar y soltar **sin tocar los archivos
originales**. Todo funciona en local: sin cuentas, nube, streaming ni publicidad.

## Requisitos e instalación

Sistema Linux con escritorio GNOME (probado en Fedora 44). Necesitas Python 3,
GTK4, libadwaita, PyGObject, Mutagen y GStreamer. Instalación en Fedora:

```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita python3-mutagen \
  gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugin-libav
```

Para ejecutar las pruebas se necesita además `ffmpeg` (no es necesario para usar
la aplicación).

## Ejecutar

```bash
./run.sh
```

o directamente:

```bash
python3 -m reproductor
```

Opciones útiles:

```bash
python3 -m reproductor --scan-only          # solo escanear e imprimir la biblioteca
python3 -m reproductor --music-dir /ruta    # usar otra carpeta de música
python3 -m reproductor --audio-sink fakesink --smoke-test   # prueba sin audio
python3 -m reproductor --audio-sink "fakesink sync=true" --smoke-mini       # mini + siempre encima
python3 -m reproductor --audio-sink "fakesink sync=true" --smoke-continuity # no se corta al alternar
```

`fakesink sync=true` reproduce en silencio a velocidad real (la posición avanza),
a diferencia de `fakesink` a secas, que vacía el audio de inmediato.

## Instalar el lanzador de escritorio

```bash
./install.sh
```

Crea `~/.local/share/applications/reproductor-melo.desktop` y el icono en
`~/.local/share/icons/hicolor/scalable/apps/`. Después aparece en el menú de
aplicaciones como **Reproductor Melo**.

## Detalle de dependencias

Paquetes incluidos en el comando de instalación anterior:

| Paquete | Para qué sirve |
|---|---|
| `python3` | Intérprete |
| `python3-gobject` | PyGObject (GTK/GStreamer desde Python) |
| `gtk4` | Interfaz gráfica |
| `libadwaita` | Widgets modernos (cabecera, tarjetas, avisos) |
| `python3-mutagen` | Lectura de metadatos (título, artista, álbum, duración) |
| `gstreamer1`, `gstreamer1-plugins-base` | Motor de audio, OGG/OPUS/WAV |
| `gstreamer1-plugins-good` | MP3, FLAC, reproducción y salida automática |
| `gstreamer1-plugin-libav` | AAC, M4A/ALAC y decodificadores adicionales |

Comprobado con `gst-inspect-1.0`: `mpg123audiodec`, `avdec_mp3`, `flacdec`,
`vorbisdec`, `opusdec`, `avdec_aac`, `avdec_alac` y `wavparse` disponibles.

## Uso

- **Doble clic o Enter** sobre una canción para reproducirla.
- **Espacio**: reproducir/pausar. **Ctrl+← / Ctrl+→**: anterior/siguiente.
- **Alt+↑ / Alt+↓** o los botones de la cabecera: mover la canción seleccionada.
- **Arrastrar y soltar** una fila sobre otra para reordenar.
- La barra inferior permite pausar, navegar, buscar posición y ajustar volumen.
- Al terminar una pista pasa sola a la siguiente; en la última se detiene.
- **Pestaña Ecualizador**: 10 bandas de −12 a +12 dB (paso 0,5), presets
  (Plano, Graves, Agudos, Rock, Pop, Clásica, Voz, Personalizado), interruptor
  de activación y botón Restablecer. Los ajustes se aplican en tiempo real.
- **Mini reproductor**: el botón de la cabecera oculta la ventana principal y
  muestra una ventana compacta con carátula, título, play/pausa, anterior,
  siguiente y restauración. Comparte el mismo motor y la misma playlist, así que
  alternar principal ↔ mini no corta ni reinicia la reproducción. El menú del
  mini permite activar **Siempre encima**.
- **Apariencia** (menú principal): esquema **Sistema / Claro / Oscuro** y seis
  paletas de acento (Predeterminada, Océano, Bosque, Atardecer, Orquídea y
  Medianoche). Cada paleta incluye variantes clara y oscura; el cambio se aplica
  al instante a la ventana principal y al mini, sin reiniciar ni cortar la
  reproducción. «Sistema» sigue el modo claro/oscuro del escritorio en tiempo
  real y «Predeterminada» respeta el acento configurado en GNOME.

## Persistencia

El estado se guarda en `~/.local/share/reproductor-melo/state.json` (o
`$XDG_DATA_HOME/reproductor-melo/state.json`): orden personalizado, última canción
seleccionada, canción cargada, volumen, posición, estado del ecualizador
(activado, preset y ganancias de las 10 bandas), modo de ventana (`main` o `mini`),
estado de **Siempre encima**, posición del mini y apariencia (`color_scheme` y
`palette`). La escritura es atómica (archivo temporal + `os.replace`). Si el JSON
falta o está corrupto se arranca con valores por defecto; un esquema o una paleta
desconocidos se sanean a `system`/`default`.

El modo mini y «Siempre encima» se guardan automáticamente. La posición del mini
solo se guarda y restaura en X11 real; en Wayland (incluido XWayland) el compositor
decide dónde colocar la ventana, así que la app no promete esa persistencia.
«Siempre encima» usa EWMH y funciona en X11/XWayland; en Wayland puro el
interruptor se muestra desactivado con una explicación.

## Arquitectura

```
reproductor/
  library.py    # carpeta Música XDG, escaneo recursivo, metadatos y deduplicado
  playlist.py   # orden, mover, siguiente/anterior (lógica pura, testeable)
  state.py      # JSON atómico en rutas XDG + validación del modo mini
  equalizer.py  # bandas, presets y utilidades puras del ecualizador
  covers.py     # carátulas incrustadas o cover/folder/front/albumart de la carpeta
  player.py     # envoltorio de GStreamer playbin3/playbin + equalizer-10bands
  playback.py   # secuenciación: auto-avance, errores, orden dinámico
  windowing.py  # X11 opcional: _NET_WM_STATE_ABOVE, posición de ventana
  miniplayer.py # ventana compacta que comparte Player, Playlist y estado
  theme.py      # paletas, contraste WCAG AA y generación de CSS (sin GTK)
  style.css     # estilos estáticos; los colores se inyectan en tiempo de ejecución
  app.py        # interfaz GTK4 + libadwaita: Biblioteca, Ecualizador, mini y Apariencia
  __main__.py   # CLI y arranque
assets/         # icono SVG
data/           # plantilla .desktop
tests/          # pruebas unittest con audio real generado por ffmpeg
```

La lógica (`library`, `playlist`, `state`) no depende de la interfaz y se prueba
sin pantalla. `playback` usa GStreamer pero tampoco conoce GTK. La interfaz solo
pinta el estado y delega las acciones.

- Metadatos con **mutagen** (ya instalado, sin hilos ni bus de GStreamer extra).
- Deduplicado por ruta real (`os.path.realpath`), de modo que los enlaces
  simbólicos al mismo archivo no se repiten.
- Si un archivo no tiene título se usa el nombre sin extensión.
- Reordenar modifica solo la lista en memoria; nunca renombra, mueve ni borra.

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas generan audio real con `ffmpeg` en carpetas temporales (MP3, FLAC,
WAV, OGG, OPUS, M4A), comprueban metadatos, fallback, duplicados, corrupción,
auto-avance, pausa, seek, volumen, errores de códec, reordenamiento, persistencia
tras reinicio y que los `sha256` de los archivos no cambian.

El ecualizador usa `equalizer-10bands` conectado a `audio-filter` de playbin;
viene en `gstreamer1-plugins-good` (ya listado). Las pruebas también comprueban
bandas, presets, cambio en tiempo real y persistencia.

El sistema de apariencia tiene pruebas propias (`tests/test_theme.py`): valida
todas las paletas y esquemas, genera el CSS y lo carga con `Gtk.CssProvider`, y
comprueba el contraste WCAG AA de cada par de colores, incluidos los acentos del
sistema. La persistencia de `color_scheme`/`palette` y el saneado de valores
inválidos se cubren en `tests/test_state.py`.

Prueba de humo de la interfaz real:

```bash
python3 -m reproductor --audio-sink fakesink --smoke-test
```

Prueba del mini reproductor y de continuidad (reproduce en silencio a velocidad
real, alterna principal → mini → principal y comprueba `playing=True` con la
posición creciente en las tres fases):

```bash
python3 -m reproductor --audio-sink "fakesink sync=true" --smoke-mini
python3 -m reproductor --audio-sink "fakesink sync=true" --smoke-continuity
```

La prueba de continuidad necesita una pista más larga que la duración de la
prueba (unos 5 segundos); si la canción termina, el auto-avance cambiaría de pista.

## Notas

- Los archivos WAV con etiquetas `INFO` (LIST/INFO) pueden no exponer título con
  mutagen; en ese caso se muestra el nombre del archivo, que es el fallback pedido.
- La reproducción usa `playbin3` y la salida de audio automática del sistema
  (PipeWire/PulseAudio vía GStreamer).
- Para una canción dañada o con códec ausente se muestra un aviso y se salta a la
  siguiente sin bloquear la interfaz.

## Licencia

MIT. Consulta el archivo [LICENSE](LICENSE).
