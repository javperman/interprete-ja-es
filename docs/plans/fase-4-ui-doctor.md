# Fase 4 — UI, doctor y ajustes en caliente

<!-- last-updated: 2026-11-13 -->

Objetivo: una interfaz usable durante la reunión (no solo texto corrido), una
comprobación previa que detecte los fallos típicos y ajustes en vivo sin reiniciar.

## Tareas

1. **`interprete doctor`** — comprobación **de solo lectura** antes de la reunión:
   comandos, nodos (`meet_in`/`meet_out`/`meet_mic`), sink por defecto (no puede
   ser `meet_in`), micrófono físico, VOICEVOX, voz de Piper, STT/CUDA,
   credenciales del traductor y memoria libre. `--live` hace una traducción real;
   `--fix` aplica solo dos arreglos (crear nodos, arrancar VOICEVOX).
2. **UI intercambiable** (`src/interprete/ui/`), sobre un `AppState` común:
   - `PlainUi` — texto corrido (la de las fases 1–3; se usa si no hay TTY).
   - `TuiUi` — pantalla completa: dos columnas, transcripción, latencias y atajos.
   - `SubtitleUi` — la última traducción centrada y en grande (ventana flotante).
   - `auto` (por defecto): TUI si hay terminal, plana si no.
3. **Ajustes en caliente** (teclas de la TUI → acciones del CLI):
   `m` voz ES · `n` voz JA · `j` japonés de fondo · `+/-` volumen del JA ·
   `p` pausa (silencia todo sin parar la captura) · `o` original · `?` ayuda · `q` salir.
   Se implementan con `Speaker.set_enabled`, `JaForwarder.set_enabled/set_volume`.
4. **Maquetación pura** (`ui/render.py` + `ui/text.py`): ancho real de los
   caracteres CJK (doble ancho) para recortar y alinear; probada sin terminal.
5. **Logs fuera de la pantalla**: con la TUI activa los logs van a
   `logs/interprete.log` para no romper el dibujado.
6. **`scripts/reunion.sh`** — corre el doctor y lanza `interprete run`.

## Criterio de aceptación

- La TUI muestra la transcripción de los dos canales y responde a las teclas.
- El doctor detecta un fallo real (nodos ausentes, VOICEVOX parado, micro virtual
  como fuente) y devuelve código ≠ 0.
- La suite de tests sigue en verde (incluye tests de texto, estado, teclas,
  maquetación, estado/ajustes en caliente y doctor).

## Resultado (2026-11-13)

- **Hecho.** TUI verificada en un pseudo-terminal real (100×26 y 110×24): dos
  columnas, transcripción JA→ES con el original atenuado y la traducción marcada
  con `▸`, estado por canal (`1 frases · 1er 1.05s · TTS 1/1`), ayuda (`?`) y
  barra de atajos. El modo subtítulos centra la última traducción.
- **Verificado en caliente:** con un clip inyectado en `meet_in`, pulsar `m`
  cambia el canal a `voz OFF` y el contador de locución se actualiza; `q` sale y
  la terminal queda restaurada.
- **Doctor real:** en el la máquina de pruebas informa *todo listo* (nodos, VOICEVOX 0.26.1, Piper,
  STT CUDA, Vertex) y `--live` traduce `こんにちは` → `Hola`.
- **Pruebas:** 101 tests en verde (~2 s), sin procesos `pw-cat`/`pw-record`
  huérfanos tras cerrar.

### Modos de UI

| Valor | Qué hace |
|---|---|
| `auto` | TUI si hay terminal interactiva; plana si no (por defecto) |
| `tui` | Pantalla completa de dos columnas |
| `subtitles` | Última traducción centrada y grande |
| `plain` | Texto corrido (para `tee`, cron o systemd) |

Se elige con `--ui <modo>` o `[ui] mode` en `config.toml`.
