# ARCHITECTURE.md — Arquitectura del intérprete JA ⇄ ES

<!-- last-updated: 2026-11-13 -->

Máquina objetivo: **portátil de referencia** (Arch/pipewire 1.6.10, wireplumber 0.5.18,
RTX 3050 Ti 4 GB + Radeon 680M, 14 GiB RAM, Python 3.14.9).

Este documento es la **fuente de verdad de la arquitectura**. Cualquier cambio
de nodos, contratos o flujo se refleja aquí **y** en `docs/CHANGELOG.md`.

---

## 1. Grafo de audio (PipeWire)

```text
                 ┌───────────────────────────── navegador (Meet/Teams) ──┐
                 │ salida → meet_in        micro ← meet_mic              │
                 └──────────────────────────────┬───────────────────────┘
                                                │
   ┌────────────┐   meet_in.monitor            │  meet_out.monitor
   │  Meet/Teams│──────────────┐                │        ▲
   └────────────┘              ▼                │        │ TTS(ja)
                        ┌───────────┐           │   ┌────────────┐
                        │  captura  │           │   │  meet_out  │
                        │  JA       │           │   │ (null sink)│
                        └─────┬─────┘           │   └─────┬──────┘
                              │ VAD→STT→MT      │         │
                              ▼                 │         │
                        TTS(es) ────────────────┼──► auriculares (físicos)
                              │                 │
   meet_in.monitor ───────────┴─► reenvío JA (vol bajo) ─► auriculares
   mic físico ──► captura ES ──► VAD→STT→MT ──► TTS(ja) ──► meet_out
```

### Nodos virtuales

| Nodo | Clase | Método | Uso |
|---|---|---|---|
| `meet_in` | `Audio/Sink` | `module-null-sink` (`pulse.cmd`) | Salida de Meet/Teams. La app captura `meet_in.monitor`. |
| `meet_out` | `Audio/Sink` | `module-null-sink` (`pulse.cmd`) | Destino de la TTS en japonés. |
| `meet_mic` | `Audio/Source` | `module-remap-source master=meet_out.monitor` | Micrófono que ve Meet/Teams; lleva la TTS(ja). |

**Japonés de fondo:** no se usa un nodo de bucle de PipeWire (el `pw-loopback`
resultó poco fiable al enlazar monitores en el la máquina de pruebas, ver `docs/CHANGELOG.md`).
La **propia aplicación** captura `meet_in.monitor` y lo reenvía a los auriculares
a volumen configurable (Fase 2), mezclado con la TTS(es). Menos piezas y control
de la mezcla/ducking en la app.

### Invariantes de realimentación (críticos)

1. La **TTS(es)** va **directo a los auriculares**, nunca a `meet_in` → nunca se
   re-transcribe.
2. La **TTS(ja)** va a `meet_out`, nunca a los auriculares ni a `meet_in`.
3. `meet_in` **nunca** es el sink por defecto.
4. El único acoplamiento es acústico (auriculares → mic físico) y se asume
   despreciable con auriculares. **Se exige usar auriculares.**

`scripts/interprete-audio verify` demuestra 1–3 con un tono de prueba.

---

## 2. Pipeline de datos (una instancia por canal)

```text
capture ──► VAD ──► STT ──► MT(stream) ──► TTS ──► playback
   │         │       │         │            │         │
  pw-record  silero  whisper   vertex       voicevox/  pw-cat
 (16k mono)  onnx    turbo     gemini       piper      --target
```

- **Captura:** `PwCapture` (`pw-record`) apunta al **sink** con
  `-P '{ stream.capture.sink=true }'` para leer su *monitor*. El monitor no es un
  nodo aparte: `--target=meet_in.monitor` **cae al micro por defecto** (bug
  detectado y corregido el 2026-11-13).
- **Cola `asyncio.Queue` acotada** entre el VAD y el procesado de cada frase.
- El `STT` (bloqueante) corre en un **hilo del executor**; el `MT` es asíncrono
  en streaming. No hay proceso aparte: el modelo se carga una vez y se calienta.
- **Instrumentación por frase** (`latency.py`): `stt_ms`, `mt_ttft_ms`,
  `first_token_ms` (fin de frase → primer token), `mt_ms`, `queue_ms`, `total_ms`.
- **Backpressure (dos niveles):**
  - entre frases (STT/MT): cola acotada; con la cola llena se descarta la frase
    nueva (contador `dropped`);
  - en la locución: **escucha** → `drop_new` (si está hablando, la frase nueva
    queda solo como texto); **habla** → `queue` (se dicen en orden, se descarta la
    más antigua si la cola se llena).

### UI (Fase 4)

La interfaz es intercambiable y comparte un `AppState` (`ui/state.py`):

| Modo | Clase | Uso |
|---|---|---|
| `auto` (def.) | `TuiUi` si hay TTY, si no `PlainUi` | reunión |
| `tui` | `TuiUi` | dos columnas, transcripción, latencias, atajos |
| `subtitles` | `SubtitleUi` | última traducción centrada y grande |
| `plain` | `PlainUi` | `tee`, cron, systemd |

- **Maquetación pura** (`ui/render.py`, `ui/text.py`): se calcula el ancho real
  (CJK de doble ancho) y se devuelven filas ya recortadas/alineadas, lo que
  permite probarla sin terminal.
- **Ajustes en caliente:** la TUI traduce teclas a acciones que ejecuta el CLI
  (`_Runtime`): silenciar voces (`Speaker.set_enabled`), japonés de fondo
  (`JaForwarder.set_enabled/set_volume`), pausa global. `--ui`/`[ui] mode`.
- **Logs:** con la TUI activa van a `logs/interprete.log` (no a stderr) para no
  romper el dibujado.

`interprete doctor` (`doctor.py`) comprueba en solo lectura nodos, sink/auriculares
y micro por defecto, VOICEVOX, Piper, STT/CUDA, credenciales del traductor y
memoria; `--live` añade una traducción real y `--fix` solo arregla nodos y
VOICEVOX.

### App de escritorio (Fase 5)

El motor se extrajo a `session.py` (`Session`, `SessionOptions`, `Runtime`), de
modo que **el CLI y la GUI comparten el mismo pipeline**; la GUI es otra
implementación de la interfaz `Ui` (`gui/ui.py`).

- **Hilos:** GTK en el hilo principal; la sesión en un hilo con su propio bucle
  `asyncio` (`gui/engine.py`). Comunicación con `GLib.idle_add` y
  `call_soon_threadsafe`.
- **Pestañas:** Reunión (arrancar/parar, dispositivos, interruptores, volúmenes,
  transcripción en vivo), Ajustes (voces con preescucha, traducción, guardado en
  `config.toml`) y Diagnóstico (doctor + conexiones en vivo).
- **Enrutado en vivo** (`routing.py`): detecta si el navegador lee el **micrófono
  físico** (aviso rojo: te oirían en español) o si nadie reproduce en `meet_in`.
  La app **no** se integra con la pestaña del navegador: trabaja con nodos.
- **Subtítulos:** ventana aparte con la última traducción en grande; la regla de
  Hyprland que escribe `scripts/install-gui.sh` la deja fijada encima.
- **Entorno:** `include-system-site-packages = true` en `.venv/pyvenv.cfg` para
  que el venv vea el GTK4 del sistema (reversible, sin instalar nada).

**Japonés de fondo / español de fondo:** se reutiliza `JaForwarder` para los dos
sentidos (el ES de fondo lleva tu voz real a `meet_out` con *ducking*).

### Implementación por fases

| Módulo | Responsabilidad | Fase |
|---|---|---|
| `audio/capture.py` | `PwCapture` (frames de un nodo, `monitor=`), `wav_frames` (replay), `inject_wav` | 1 |
| `pipeline/listen.py` | `ListenPipeline`: frames → VAD → cola → STT → MT → `TurnResult` con tiempos | 1 |
| `audio/player.py` | `PwPlayback` (voz), `PwPlayStream` (flujo), `JaForwarder` (japonés de fondo con ducking) | 2 |
| `pipeline/speaker.py` | `Speaker`: síntesis + reproducción; modos `drop_new` (escucha) y `queue` (habla) | 2–3 |
| `pipeline/channel.py` | `Channel`: canal completo reutilizable por ambos sentidos | 3 |
| `tts/piper.py` | TTS español (Piper, 22050 Hz) | 2 |
| `vad/base.py` | `Segmenter` (lógica pura de segmentación por silencio) | 1 |
| `ui/` | `AppState` + `PlainUi`/`TuiUi`/`SubtitleUi`; `render.py` y `text.py` puros (ancho CJK) | 4 |
| `session.py` | `Session`: motor reutilizable (recursos, canales, ciclo de vida) | 5 |
| `routing.py` | Quién reproduce en `meet_in` y quién lee cada micrófono (solo lectura) | 5 |
| `gui/` | App GTK4 + libadwaita: ventana, pestañas, subtítulos, `GuiUi`, `Engine` | 5 |
| `doctor.py` | comprobación previa a la reunión (solo lectura), con `--fix` acotado | 4 |
| `__main__.py` | `interprete nodes\|gui\|doctor\|translate\|listen\|speak\|run …` | 1–5 |

### Canal de habla ES→JA (Fase 3)

Mismo `Channel` que la escucha, con `source=es`, `target=ja`, TTS VOICEVOX y salida
a `meet_out` (que alimenta `meet_mic`, el micro que ve Meet). El micrófono
**físico** lo captura la app (nunca Meet). Política de locución **`queue`**: las
frases se dicen en orden y, si la cola se llena, se descarta la más antigua.
El `STT` es **compartido** entre canales (un modelo, un `Lock`).

### Salida de audio (Fases 2–3)

La traducción y el original de fondo se reproducen como **flujos `pw-cat`
independientes** que PipeWire mezcla; no hay nodo de mezcla propio:

- **Escucha (JA→ES):** `PwPlayback` reproduce a Piper (22050 Hz) en los
  **auriculares**; `JaForwarder` reenvía el japonés capturado a
  `ja_monitor_volume` y lo **atenúa a `duck_volume`** mientras suena la traducción.
- **Habla (ES→JA):** `PwPlayback` reproduce a VOICEVOX en `meet_out` (→ `meet_mic`,
  el micro que ve Meet). **Nunca** va a los auriculares.
- **Solo texto:** `Speaker` con `drop_new` descarta la frase nueva si está
  hablando (canal de escucha); con `queue` las dice en orden (canal de habla).

---

## 3. Componentes y contratos

Cada componente vive detrás de una **interfaz** para poder cambiar de modelo o
proveedor sin tocar el pipeline.

| Paquete | Interfaz | Implementación por defecto | Alternativas |
|---|---|---|---|
| `vad` | `VadSegmenter.push(frame)->Event` | `silero_onnx` (onnxruntime, **sin torch**) | `silero-vad` pip (torch) |
| `stt` | `Stt.transcribe(pcm, lang)->str` | `faster_whisper` `large-v3-turbo` en GPU | Hermes gateway (socket) |
| `mt` | `Translator.translate_stream(text, ctx)->AsyncIterator[str]` | `vertex` (Gemini `gemini-3.5-flash-lite`) | Gemini API (AI Studio), DeepSeek, LLM local |
| `tts` | `Tts.synthesize(text, lang)->pcm` | `voicevox` (ja) / `piper` (es) | piper-plus, Kokoro |
| `audio` | `Capturer` / `Player` | `pw-record` / `pw-cat` (subprocesos) | sounddevice |

### Elección de modelos (2026-11-13)

- **STT:** `faster-whisper` **`large-v3-turbo`**, `device=cuda`,
  `compute_type=int8_float16` (~1,2 GB VRAM; RTF ≈ 0,08 medido en el la máquina de pruebas).
  Libs CUDA 12 desde `~/.local/share/hermes-cuda/` vía `LD_LIBRARY_PATH`.
- **MT:** Google **Vertex AI** (Gemini), cuenta de servicio y token OAuth.
  Modelo por defecto **`gemini-3.5-flash-lite`** en
  `location = global` con `thinkingLevel = minimal` (TTFT 0,4–0,8 s). Solo
  `global` sirve: las regiones europeas dan 404 para los Gemini 3. Alternativas
  tras la misma interfaz: Gemini API (AI Studio) y DeepSeek.
- **TTS(es):** **Piper** (`piper-tts` 1.8, OHF-voice/piper1-gpl) con la voz
  `es_ES-davefx-medium` (22050 Hz mono). Se instala sin root con
  `scripts/install-piper.sh` en `~/.local/share/interprete/piper/`. Síntesis
  medida: ~120 ms para 3,3 s de audio (CPU, onnxruntime).
- **TTS(ja):** **VOICEVOX Engine 0.26.1** en modo **rootless** (binario oficial
  `linux-cpu`, sin root ni pacman), servicio de usuario, API HTTP en
  `127.0.0.1:50021`. Voz por defecto: estilo **13 (青山龍星)**, registro de
  reunión. El motor CPU **no consume VRAM**.
- **VAD:** Silero, modelo ONNX directo con onnxruntime (evita el pin roto
  `torchaudio<2.10` de `silero-vad` en Python 3.14). Ojo: el modelo exige
  **contexto de 64 muestras** + fotograma de 512 (16 kHz).
- **Modelo Whisper:** `mobiuslabsgmbh/faster-whisper-large-v3-turbo`, ya presente
  en la caché de Hugging Face del equipo (se reutiliza; no se descarga de nuevo).
- **Libs CUDA 12:** `~/.local/share/hermes-cuda/`. ctranslate2 las carga con
  `dlopen` **perezoso**, y glibc lee `LD_LIBRARY_PATH` del entorno inicial, así
  que no basta con `os.environ`: si faltan, el CLI se **reejecuta** a sí mismo con
  la variable ya puesta (`_maybe_reexec_with_cuda`).

---

## 4. Presupuesto de recursos

| Recurso | Uso | Nota |
|---|---:|---|
| VRAM | 1,2 GB | Whisper turbo `int8_float16`. Hermes usa otra copia si hay dictado: **no usar ambos a la vez**. |
| RAM | ~1–2 GB | VOICEVOX + pipeline. Cerrar pestañas de Brave durante la reunión. |
| CPU | varios hilos | VOICEVOX (CPU) + VAD + resample. |

---

## 5. Persistencia y reversibilidad

- **Nodos de audio:** `~/.config/pipewire/pipewire-pulse.conf.d/60-interprete.conf`
  (copia de `pipewire/60-interprete.conf`), cargados por `pipewire-pulse` al
  arrancar; sobreviven a reinicios de PipeWire.
- **Gestión:** `scripts/interprete-audio setup|teardown|status|verify`,
  idempotente y reversible.
- **Unidades de usuario:** `systemd/user/*` (STT, VOICEVOX) en fases posteriores.
- **Teardown:** `scripts/interprete-audio teardown` elimina el drop-in y los
  nodos de runtime; el sistema queda como estaba.

---

## 6. Latencia (objetivo y medición)

Objetivo realista: **2–4 s desde que termina la frase**. Instrumentación por
etapa (`src/interprete/latency.py`): VAD, STT, primer token de MT, primer audio
de TTS y extremo a extremo. Se registra en logs y en el informe final.

---

## 7. Ver también

- `docs/design.md` — por qué estas decisiones y qué se descartó.
- `docs/plans/` — fases y criterios de aceptación.
