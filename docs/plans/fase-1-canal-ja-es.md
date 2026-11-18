# Fase 1 — Canal de escucha JA → ES (a texto)

<!-- last-updated: 2026-11-13 -->

Objetivo: unir las piezas en el pipeline real
**captura → VAD → STT → MT → texto**, con instrumentación por etapa y un **modo
de pruebas** que no necesita una reunión real.

## Tareas

1. **`audio/capture.py`**
   - `PwCapture`: captura continua de un nodo con `pw-record`; frames float32
     mono de 512 muestras (32 ms a 16 kHz, lo que exige Silero). Con
     `monitor=True` captura el monitor del sink (`stream.capture.sink`).
   - `wav_frames`: reproduce un WAV como flujo de frames (replay, `realtime=`).
   - `inject_wav`: envía un WAV a un nodo con `pw-cat` (inyección de pruebas).
2. **`pipeline/listen.py`** — `ListenPipeline`:
   - VAD (Silero) en el bucle de captura; cola `asyncio.Queue` acotada;
   - `STT` en hilo del executor; `MT` asíncrono en streaming;
   - `TurnResult` con transcripción, traducción y tiempos
     (`stt_ms`, `mt_ttft_ms`, `first_token_ms`, `mt_ms`, `queue_ms`, `total_ms`).
3. **CLI** `interprete listen`:
   - `--input FILE` (replay sin PipeWire), `--inject FILE` (inyecta y escucha el
     monitor), `--seconds N`, `--sink`, `--from/--to`, `--latency-log`.
   - Re-exec automático con `LD_LIBRARY_PATH` de CUDA (ctranslate2 lo necesita
     antes de arrancar, no basta `os.environ`).
4. **`scripts/make-test-clip.sh`** — genera un clip JA con VOICEVOX.
5. **Corrección** de `interprete-audio verify`: la captura del monitor del sink.

## Criterio de aceptación

- Un WAV japonés (sintetizado con VOICEVOX) inyectado en `meet_in` produce, por la
  cadena real de PipeWire, la **traducción al español** con tiempos medidos.
- `pytest` en verde (los tests del pipeline usan dobles, sin hardware).
- `interprete-audio verify` sigue pasando.

## Resultado (2026-11-13)

- **Hecho.** Flujo completo validado de dos formas:
  - replay del WAV (`--input`): STT 381 ms, MT 1er token 982 ms, 1er token desde
    el fin de frase **1363 ms**, total 1612 ms;
  - cadena real (`--inject` en `meet_in` + monitor): STT 418 ms, MT 1er token
    862 ms, 1er token **1281 ms**, total 1396 ms.
- Traducciones correctas JA→ES. Sin procesos `pw-record`/`pw-cat` colgados.
- **Hallazgo clave:** el monitor de un sink no es un nodo aparte;
  `--target=meet_in.monitor` cae al micro por defecto. Se usa
  `-P '{ stream.capture.sink=true }'`.
- **Hallazgo:** ctranslate2 exige `LD_LIBRARY_PATH` antes de arrancar el proceso;
  el CLI se reejecuta con él puesto.
- **Pendiente de fases siguientes:** TTS(es) a auriculares y backpressure (Fase 2),
  canal ES→JA hacia `meet_mic` (Fase 3), UI y logs (Fase 4).
