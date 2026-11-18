# Plan general — Intérprete JA ⇄ ES

<!-- last-updated: 2026-11-13 -->

Objetivo: intérprete simultáneo bidireccional japonés ⇄ español para Meet/Teams
sobre PipeWire en el la máquina de pruebas. Latencia objetivo: **2–4 s desde el fin de frase**.

Cada fase se implementa y **se prueba antes de pasar a la siguiente**. Toda fase
terminada actualiza `AGENTS.md`/docs y añade una entrada a `docs/CHANGELOG.md`.

---

## Resumen de fases

| Fase | Contenido | Criterio de aceptación | Estado |
|---|---|---|---|
| **0** | Grafo de audio + entorno (venv, VOICEVOX, setup/teardown) | `verify` pasa sin bucles y `teardown` deja el sistema igual | **hecho** (2026-11-13) |
| **0.5** | Benchmark local de STT JA (calidad, latencia, VRAM) | RTF y consumo documentados | pendiente |
| **1** | Canal JA→ES a **texto** + instrumentación de latencia | transcripción+traducción correctas sobre WAV JA | **hecho** (2026-11-13) |
| **2** | TTS(es) a auriculares + backpressure | voz ES audible; degrada a texto sin bloquear | **hecho** (2026-11-13) |
| **3** | Canal ES→JA hacia `meet_mic` | los demás oyen JA; sin eco ni cortes del AEC | **hecho** (2026-11-13) |
| **4** | UI mínima + config + logs + tests + modo de pruebas | suite en verde y UI usable | **hecho** (2026-11-13) |
| **5** | App de escritorio GTK4 + doctor + ajustes + subtítulos | usable sin comandos; verificado en el la máquina de pruebas | **hecho** (2026-11-13) |
| **6** | Voz con tono de negocios y fondos audibles | los dos fondos suenan (medido); melodía 11,1 → 3,6 semitonos | **hecho** (2026-11-13) |

---

## Decisiones fijadas (2026-11-13)

- **MT:** solo nube, DeepSeek `deepseek-flash`, `thinking` desactivado.
- **TTS(ja):** VOICEVOX Engine (AUR, CPU).
- **TTS(es):** Piper.
- **STT:** proceso propio, `faster-whisper large-v3-turbo` en GPU.
- **Python:** 3.14 (venv propio, sin uv).
- **Audio:** se oye el japonés original a volumen bajo mezclado con el español.
- **Ubicación:** proyecto hermano `$HOME/Programacion/interprete-ja-es`.

---

## Entregables finales

1. Código funcional por fases.
2. `docs/design.md` (crítica y decisiones).
3. `README.md` (instalación, uso, configuración de Meet/Teams).
4. Informe de latencias y limitaciones conocidas.
