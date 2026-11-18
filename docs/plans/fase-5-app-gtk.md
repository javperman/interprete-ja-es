# Fase 5 — App de escritorio (GTK4 + libadwaita)

<!-- last-updated: 2026-11-13 -->

Objetivo: dejar de escribir comandos. Una **app nativa** desde la que comprobar el
sistema, ajustar voces, iniciar/parar la sesión y ver la transcripción en vivo,
con una ventana de subtítulos grandes durante la llamada.

## Arquitectura

La Fase 4 dejó una interfaz `Ui` con un `AppState` compartido; la GUI es **una
implementación más** de esa interfaz. Además se extrajo el motor del CLI a
`session.py` para que lo usen los dos:

| Fichero | Responsabilidad |
|---|---|
| `session.py` | `SessionOptions`, `resolve`, `make_state`, `Runtime` y `Session` (cargar STT/MT/TTS, montar canales, ejecutar y cerrar) |
| `routing.py` | Quién reproduce en `meet_in` y quién lee cada micrófono (solo lectura, `pactl -f json`) |
| `gui/engine.py` | Hilo con su propio bucle `asyncio` donde vive la sesión |
| `gui/ui.py` | `GuiUi`: misma interfaz que la TUI, pero pintando widgets (`GLib.idle_add`) |
| `gui/window.py` | Ventana, cabecera, pestañas, subtítulos y estado |
| `gui/page_meeting.py` | Controles, dispositivos, interruptores, volúmenes y transcripción |
| `gui/page_settings.py` | Voces (VOICEVOX/Piper con preescucha), traducción y preferencias |
| `gui/page_diagnostic.py` | El `doctor` con botones «Arreglar» y las conexiones en vivo |
| `gui/devices.py`, `gui/voices.py` | Catálogos de dispositivos y de voces |
| `gui/overlay.py` | Ventana de subtítulos grandes |

Hilos: GTK manda; la sesión corre en otro hilo y se comunica con
`GLib.idle_add` (hacia GTK) y `call_soon_threadsafe` (hacia el motor). El CLI
sigue existiendo y ahora usa el mismo `Session`.

## Entorno

`.venv/pyvenv.cfg` pasa `include-system-site-packages` a **true** para que el
entorno vea `python-gobject`/GTK4 del sistema (una línea, reversible; los paquetes
del venv conservan prioridad). No se instala nada nuevo.

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| **5.1** | Ventana + pestaña Reunión: iniciar/parar, dispositivos, transcripción, volúmenes, interruptores | **hecho** |
| **5.2** | Ajustes: voces VOICEVOX/Piper con preescucha, traducción, glosario, guardado en `config.toml` | **hecho** |
| **5.3** | Diagnóstico integrado + conexiones en vivo + aviso de micrófono físico | **hecho** |
| **5.4** | `.desktop`, icono, regla de Hyprland, `--toggle`/`--start`/`--subtitles`, `ver-llamada.sh` | **hecho** |
| **5.5** | Subtítulos grandes, tema, primera ejecución | **hecho** (subtítulos; tema sigue el del sistema) |

## Extras decididos con el usuario

- **Voz española de fondo** (`es_monitor_volume`, interruptor «Mi voz de fondo»):
  envía también tu voz real a la reunión por debajo del japonés sintético.
- **Autodetección de idioma** (`stt.auto_language`): si se mezclan JA y ES, el STT
  detecta el idioma; si ya está en el idioma de destino, no se traduce.
- **Aviso de enrutado**: la app detecta si el navegador está leyendo el
  **micrófono físico** (entonces te oirían en español) o si nadie reproduce en
  `meet_in`.

## Cómo se usa

```bash
./scripts/install-gui.sh          # lanzador + icono (sin root, reversible)
interprete gui                    # abre la app
interprete gui --toggle           # iniciar/parar desde un atajo de Hyprland
interprete gui --subtitles        # mostrar/ocultar subtítulos
```

## Resultado (2026-11-13)

- **Verificado en el la máquina de pruebas** con capturas: pestaña Reunión en marcha (botón
  «Parar», `● En marcha 00:29`, `JA → ES: 1 frases · 1.2s`), transcripción con el
  original atenuado y la traducción en negrita, y **ventana de subtítulos** con la
  última frase en grande.
- **Sesión lanzada desde la propia app** (D-Bus `--start`) con un clip japonés
  inyectado en `meet_in`: `stt 419.9 ms · 1er token 1256.3 ms · total 1353.6 ms`.
- **Diagnóstico**: las 11 comprobaciones en verde, incluido el enrutado.
- **129 tests** en verde (~2 s) y el CLI intacto tras el refactor.

## Pendiente / no verificado

- **Regla de aislamiento por `media.role`** (`scripts/aislar-llamada.sh`):
  escrita pero **pendiente de verificar en una llamada real**; el valor exacto de
  las propiedades se captura con `scripts/ver-llamada.sh`. Por eso es opt-in
  (`--install`) y no se aplica sola.
- **Bandeja**: GTK4 no tiene API de bandeja; se usa `.desktop` + atajo de Hyprland
  con `interprete gui --toggle`. Un módulo de waybar queda como alternativa.
