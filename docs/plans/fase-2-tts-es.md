# Fase 2 — Voz en español en los auriculares y backpressure

<!-- last-updated: 2026-11-13 -->

Objetivo: además del texto, **oír** la traducción en español por los auriculares,
mezclada con el japonés original de fondo a volumen bajo, y degradar a solo-texto
si la locución no da abasto.

## Tareas

1. **Piper (TTS español)** — `scripts/install-piper.sh`: instala `piper-tts` en el
   venv y descarga la voz `es_ES-davefx-medium` (22050 Hz) en
   `~/.local/share/interprete/piper/`. Sin root.
2. **`tts/piper.py`** — `PiperTts` con la API real de `piper-tts`
   (`PiperVoice.load` + `SynthesisConfig`).
3. **`audio/player.py`**
   - `PwPlayback`: reproduce un fragmento (voz) con `pw-cat … --raw -` por stdin.
   - `PwPlayStream`: flujo continuo.
   - `JaForwarder`: reenvía el japonés capturado a los auriculares a
     `ja_monitor_volume`, con **ducking** a `duck_volume` mientras habla la
     traducción y cola acotada (descarta frames si va retrasado).
4. **`pipeline/speaker.py`** — `SpanishSpeaker`: sintetiza y reproduce **una frase
   a la vez**; si llega otra mientras suena la anterior, la **descarta** (solo
   texto). Toggle de ducking alrededor de la reproducción.
5. **CLI** — `interprete listen` gana `--headphones`, `--ja-volume`, `--no-ja` y
   `--no-speak`; el reenvío del JA se desactiva en el replay acelerado.
6. **Tests** — `apply_gain` y `playback_command`, descarte del `JaForwarder`,
   locución y backpressure del `SpanishSpeaker` (dobles), y Piper real si está.

## Criterio de aceptación

- Un WAV japonés inyectado en `meet_in` produce, por la cadena real, la voz en
  español en el nodo de salida (verificado grabando su monitor) mezclada con el
  japonés de fondo.
- Si dos frases llegan seguidas, la segunda se salta en voz (solo texto).
- `pytest` en verde.

## Resultado (2026-11-13)

- **Hecho.** Salida enrutada a `meet_out` para verificar sin ruido: el monitor
  muestra el **japonés de fondo** a nivel bajo (rms ≈ 0,01) y la **voz española a
  plena escala** (max 1,0) tras el MT. `TTS(es): 1 locutadas | 0 descartadas`.
- Piper: 120 ms para sintetizar 3,3 s de audio (CPU).
- Backpressure verificado en tests: con locución en curso, la frase nueva se
  descarta y queda como texto.
- **Pendiente (Fase 3):** canal ES→JA hacia `meet_mic`.
