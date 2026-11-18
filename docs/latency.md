# Informe de latencia

<!-- last-updated: 2026-11-13 -->

Objetivo: **2–4 s desde el fin de frase**. Se mide por etapa (VAD, STT, primer
token de MT, primer audio de TTS) y extremo a extremo.

Equipo: Ryzen 7 6800H (16 hilos), RTX 3050 Ti 4 GB, 14 GiB RAM.

---

## Traducción (MT) — Vertex AI, `location = global`

Frase JA de ~70 caracteres (≈5 s de habla). `thinkingLevel = minimal`.

| Modelo | TTFT (ms) | Total (ms) | Notas |
|---|---:|---:|---|
| `gemini-3.5-flash-lite` | **405–810** | **508–913** | ✅ Elegido: el más rápido y barato |
| `gemini-3.1-flash-lite` | 819–1641 | 1043–1845 | Correcto, algo más lento |
| `gemini-3.5-flash` | 1534–17495 | — | Variable; hay picos de 17 s |
| `gemini-3.8-flash` | — | — | Rechaza `thinkingLevel: minimal` (400) |

**Regiones:** solo funciona `global`. `europe-west4`, `europe-west1` y
`europe-southwest1` (Madrid) devuelven **404** para estos modelos Gemini 3, así
que la región no es una palanca de latencia aquí.

**Efecto del *thinking*:** sin ajustar, TTFT ≈ 5,1 s; con `thinkingLevel=minimal`,
≈ 1,5 s (y con flash-lite, < 1 s). `thinkingBudget=0` es un desastre (≈19 s).

## STT — faster-whisper `large-v3-turbo` en RTX 3050 Ti

`int8_float16`, ~1,2 GB VRAM, modelo ya en caché de Hugging Face.

| Prueba | Audio | Tiempo | Notas |
|---|---:|---:|---|
| VOICEVOX ja → Whisper ja | 4,23 s | **1,26 s** | Transcripción exacta |
| JFK (en) | 11,0 s | 0,38 s | Referencia histórica del equipo (RTF ≈ 0,08) |

## VAD — Silero ONNX (CPU)

Despreciable (< 10 ms por fotograma de 32 ms). La segmentación la marca el
silencio (`min_silence_ms` 500, `speech_pad_ms` 200, pre-roll 300).

## TTS — VOICEVOX 0.26.1 (CPU)

| Prueba | Texto | Audio | Notas |
|---|---|---:|---|
| Síntesis ja | frase de ~25 caracteres | ~2,9 s de audio | `liner` en :50021, latencia de síntesis < 1 s |

## TTS(es) — Piper `es_ES-davefx-medium` (CPU)

| Prueba | Texto | Audio | Síntesis | Notas |
|---|---|---:|---:|---|
| Piper es | «Buenos días a todos. Empecemos la reunión.» | 3,3 s @ 22050 Hz | **120 ms** | onnxruntime, RTF ≈ 0,04 |

## Fase 2 — cadena completa con voz (2026-11-13)

Salida enrutada a `meet_out` para verificar sin ruido de altavoces. El monitor del
nodo muestra las dos capas: el japonés de fondo a nivel bajo y la voz española a
plena escala cuando termina el MT.

| Etapa | Valor |
|---|---:|
| STT | ~410 ms |
| MT 1er token | ~860 ms |
| Piper (síntesis) | ~120 ms (medido aparte) |
| **1er token desde el fin de frase** | **~1270 ms** |
| Total (texto completo) | ~1480 ms |

## Fase 3 — canal de habla ES→JA (2026-11-13)

Clip en español de 6,35 s (Piper) por el canal de habla; salida a `meet_out`.

| Etapa | Valor |
|---|---:|
| STT (es) | 404 ms |
| MT 1er token | 1131 ms |
| **1er token desde el fin de frase** | **1534 ms** |
| Total (texto completo) | 1842 ms |

Verificado: el japonés enviado a `meet_out` se re-transcribe y coincide con la
traducción (inteligible). Complejidad añadida: el MT es→ja produce respuestas algo
más largas que ja→es, de ahí un 1er token algo mayor.

---

## Presupuesto por turno (medido)

`STT (~0,3–0,5 s) + MT 1er token (~0,4–1,0 s)` ⇒ **~1,3 s** hasta el primer token,
**~1,5–1,7 s** hasta el texto completo. Con la TTS(es) (< 0,2 s de síntesis + el
tiempo de reproducción) el objetivo de **2–4 s** queda holgado.
