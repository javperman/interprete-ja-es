# design.md — Crítica de diseño, decisiones y alternativas descartadas

<!-- last-updated: 2026-11-13 -->

Este documento resume **qué se mantiene**, **qué se cambia** y **por qué** de la
propuesta inicial, con los datos verificados el 2026-11-13 en el equipo la máquina de pruebas.

---

## 1. Entorno verificado

| Aspecto | Hallazgo |
|---|---|
| Stack de audio | PipeWire 1.6.10 + WirePlumber 0.5.18; ALC257 con `api.alsa.soft-mixer` y servicio `alsa-output-watch` |
| Hardware | Ryzen 7 6800H (16 hilos), **14 GiB RAM**, RTX 3050 Ti **4 GB** + Radeon 680M |
| CUDA | Driver 615.78.08 / UMD 13.4, **sin toolkit**; libs CUDA 12 de usuario en `~/.local/share/hermes-cuda/` |
| Python | **3.14.9** de sistema; ruedas cp314 para torch/ctranslate2/onnxruntime/numpy |
| STT existente | faster-whisper `large-v3-turbo` en GPU, `int8_float16`, **RTF ≈ 0,08**, ~1,2 GB VRAM |
| MT | DeepSeek `deepseek-flash`: `https://api.deepseek.com`, `stream=true`, **thinking ON por defecto**; ~$0,15/$0,60 por M tokens |
| TTS JA | Piper oficial: **una** voz `ja_JP-hi_fi_captain-medium`, **no comercial**. VOICEVOX Engine en AUR (build CPU) |
| TTS ES | Piper (`es_ES-davefx-medium` CC0, `es_MX-ald-medium` Unlicense) |

---

## 2. Qué se mantiene de la propuesta inicial

- **Nodos `meet_in` / `meet_out` / `meet_mic`** y la prohibición de capturar el
  monitor del sink por defecto. Es la única forma limpia de evitar
  realimentación y el análisis lo confirma (ver `ARCHITECTURE.md` §1).
- **`meet_mic` como virtual source** (Chromium oculta los monitores; hay que
  ofrecer una `Audio/Source` normal).
- **Interfaz de proveedor de MT intercambiable**, streaming de tokens, contexto
  de 3–5 frases y glosario.
- **Concurrencia híbrida**: callbacks de audio en hilos que pasan al bucle
  `asyncio` con `call_soon_threadsafe`; `asyncio.Queue` acotadas; inferencia
  bloqueante fuera del bucle.
- **Backpressure** y degradación a solo-texto.
- **Instrumentación de latencia por etapa** y modo de pruebas con WAV.

---

## 3. Qué se cambia, y por qué

### 3.1 STT: VAD-segmentado en GPU, no streaming

La propuesta planteaba streaming (`whisper_streaming`/WhisperLiveKit) frente a
segmentar por VAD. En este hardware el **VAD-segmentado con `large-v3-turbo` ya
está medido** (RTF ≈ 0,08) y el japonés, al no tener espacios, se beneficia de
segmentos por silencio. El streaming añade complejidad y empeora la frontera de
frase. **Decisión: VAD batch.** WhisperLiveKit queda como opción futura.

### 3.2 STT: modelo caliente en proceso, ejecutado en un hilo

**Decisión del usuario:** proceso propio con el modelo caliente en la RTX 3050 Ti,
desacoplado del gateway de Hermes. En la práctica (Fase 1) el modelo se carga una
vez dentro del propio proceso del intérprete y la inferencia se ejecuta en un
**hilo del executor** (`run_in_executor`), suficiente para el ritmo de una
conversación y más simple que un daemon con IPC. Si más adelante se quiere
compartir la copia del modelo con Hermes, la interfaz `SttBackend` permite pasar a
un socket sin tocar el pipeline.

**Hallazgo verificado (2026-11-13):** ctranslate2 carga `libcublas`/`libcudnn` con
`dlopen` perezoso y glibc lee `LD_LIBRARY_PATH` del entorno **inicial**, así que
`os.environ` en marcha no sirve (el modelo *carga* bien, pero falla al inferir con
`libcublas.so.12 is not found`). Solución: el CLI se **reejecuta** con
`LD_LIBRARY_PATH` apuntando a `~/.local/share/hermes-cuda/` antes de arrancar.

### 3.3 MT: nube con proveedor intercambiable (Vertex AI por defecto)

**Decisión del usuario:** solo nube, con **Google Cloud**. Se usa **Vertex AI
(Gemini)** con autenticación por **cuenta de servicio** y token OAuth.
Modelo **`gemini-3.5-flash-lite`**, `location = global`,
`thinkingLevel = minimal` (sin eso, el TTFT se multiplica por 3–10). Se mantienen
como alternativas, tras la misma interfaz `Translator`: **Gemini API (AI Studio)**
(clave `GEMINI_API_KEY`) y **DeepSeek** (`thinking` desactivado, `DEEPSEEK_API_KEY`).

Detalle verificado: **solo `global`** publica los Gemini 3; las regiones europeas
(incluida Madrid) devuelven 404. El rol mínimo necesario es `roles/aiplatform.user`.

**El texto de la reunión sale a Vertex AI (Google)**: se avisa en UI y en logs.
Mediciones en `docs/latency.md`.

### 3.4 TTS japonés: VOICEVOX (rootless)

Piper japonés es insuficiente (una sola voz *medium*, licencia **no comercial**).
**Decisión del usuario: VOICEVOX Engine.**

El paquete **AUR** (`voicevox-engine`) quedó **descartado en la práctica**: la
base de datos de paquetes local estaba desfasada y `paru` fallaba con 404; un
upgrade parcial sería un error, y un `-Syu` completo implicaba **137 paquetes,
kernel 7.3.4 y NVIDIA 620 + reinicio**, un cambio de sistema ajeno a este
proyecto. En su lugar se instaló el **binario oficial `linux-cpu` 0.26.1 en modo
rootless** (`scripts/install-voicevox.sh` → `~/.local/share/voicevox-engine/`),
servicio de usuario, sin root. Ventajas: versión más nueva, aislado del sistema y
reversible; inconveniente: se actualiza a mano. Alternativas evaluadas:
piper-plus (MIT, ligero) y Kokoro-82M (descartado: exige Python <3.13).

### 3.5 PipeWire: drop-in persistente + setup/teardown

Los nodos (`meet_in`, `meet_out` con `module-null-sink`; `meet_mic` con
`module-remap-source`) se declaran en un **drop-in de `pipewire-pulse`**
(`pulse.cmd`), que sobrevive a reinicios de PipeWire y de pipewire-pulse.
`scripts/interprete-audio` (`setup`/`teardown`) los instala y los carga en
runtime de forma idempotente y reversible. No se usa `pactl load-module` suelto
(desaparece al reiniciar).

> Nota: la primera idea era usar `support.null-audio-sink` en `pipewire.conf.d`;
> en la práctica `module-null-sink` vía `pulse.cmd` cubre las tres piezas en
> **un solo fichero** y con un único servicio que reiniciar, así que se unificó.

### 3.8 Japonés de fondo: en la app, no un bucle de PipeWire

El plan inicial creaba un nodo `module-loopback`/`pw-loopback` para oír a los
demás en japonés a volumen bajo. En el la máquina de pruebas **`pw-loopback` no enlazó de forma
fiable el monitor de `meet_in`** (dejaba nodos sueltos y no conectaba). Se
descarta: la **propia aplicación** captura `meet_in.monitor` y lo reenvía a los
auriculares a volumen configurable, mezclado con la TTS(es). Ventajas: menos
piezas, un fallo menos de enrutado y control de la mezcla/ducking en la app.

### 3.6 Captura/playback con subprocesos `pw-record`/`pw-cat`

Se apunta a los nodos por nombre, sin depender del naming de PortAudio, y es
coherente con el dictado ya existente en el la máquina de pruebas. `sounddevice` queda como
alternativa.

**Hallazgo verificado (2026-11-13):** el *monitor* de un sink **no** es un nodo
PipeWire aparte; es un puerto del propio sink. Por eso
`pw-record --target=meet_in.monitor` **no enlaza con el monitor y cae al micro por
defecto** (captura ~-40 dB de ruido de sala en vez del audio del sink). La forma
correcta es apuntar al sink y pedir su monitor:
`pw-record --target=meet_in -P '{ stream.capture.sink=true }'`. Se corrigió tanto
`PwCapture` como la comprobación `interprete-audio verify` (que pasaba "por
casualidad" con el umbral laxo). Confirmado cruzando con `parec`, que sí captura a
plena escala.

### 3.7 VAD sin torch

El paquete `silero-vad` arrastra `torch` y fija `torchaudio<2.10` (roto en
Python 3.14). Se usa el **modelo ONNX de Silero directamente con onnxruntime**,
evitando torch por completo.

**Detalle verificado:** el modelo exige **anteponer 64 muestras de contexto** al
fotograma de 512 (16 kHz). Sin ese contexto devuelve probabilidades ~0 incluso
con voz real (comprobado con `jfk.wav` y voz sintética). Con él, JFK da picos de
1.0 y la segmentación funciona.

---

### 3.9 Salida de audio: flujos `pw-cat`, *ducking* y dos políticas de cola

La traducción (Piper) y el japonés original de fondo se reproducen como **flujos
`pw-cat` independientes** al mismo nodo de auriculares, y PipeWire los mezcla. No
se usa un nodo de mezcla propio: menos piezas y el `ducking` se hace en la app
(bajar `ja_monitor_volume` a `duck_volume` mientras habla la traducción). La TTS
español es **Piper** (`piper-tts`, 22050 Hz): rápida (RTF ≈ 0,04) y sin torch.

La locución usa **dos políticas** según el canal:

- **escucha** (`drop_new`): mientras habla, la frase nueva se descarta y queda solo
  como texto. Así cada frase se oye entera; es preferible perder una locución a
  cortar la anterior.
- **habla** (`queue`): las frases se dicen **en orden** y, si la cola se llena, se
  descarta la más antigua. Aquí **no** se puede descartar la nueva: perderíamos lo
  que el usuario acaba de decir. La cola acota el retraso máximo.

### 3.10 APIs speech-to-speech en tiempo real (evaluadas, no usadas)

Se valoraron modelos que traducen voz→voz de una pieza (OpenAI
`gpt-realtime-translate` ≈ $0,034/min; Gemini 3.5 Live Translate ≈ $0,037/min;
Azure/Deepgram/ElevenLabs, $0,04–0,08/min). Ventaja: latencia de 300–500 ms.
Inconvenientes para nuestro caso: (1) **no resuelven el enrutado** (seguiríamos
necesitando los nodos virtuales y el micro virtual); (2) menos control sobre
glosario y registro; (3) coste por minuto mayor que la cascada con
`flash-lite` + VOICEVOX + Whisper local; (4) todo el audio sale a la nube, no solo
el texto. **Decisión: cascada** (STT→MT→TTS), que además mantiene la puerta abierta
a un modo local.

---

## 4. Riesgos abiertos

1. **AEC/NS de Chrome** sobre `meet_mic` (puede cortar o alterar la TTS(ja)).
   Mitigación: desactivar cancelación de eco y supresión de ruido en Meet.
2. **Selección persistente de dispositivo** en Brave/Meet. Plan A: reglas
   WirePlumber por `application.name`; Plan B: elección manual una vez.
3. **VRAM 4 GB compartida** con Hermes/Steam. No usar dictado y reunión a la vez.
4. **RAM 14 GiB**; cerrar pestañas durante la reunión.
5. **Cambio de auriculares en caliente** (ALC257 ↔ Beats BT).

---

## 5. Alternativas descartadas (resumen)

| Alternativa | Motivo del descarte |
|---|---|
| Piper japonés | Calidad/licencia insuficientes |
| Kokoro-82M | Requiere Python <3.13 |
| Whisper streaming (WLK) | Complejidad y peor frontera de frase en JA |
| `pactl load-module` suelto | No persiste tras reiniciar PipeWire |
| Capturar el monitor del sink por defecto | Realimentación de la TTS |
| STT en CPU | RTF mucho peor (~6,6 s por 8 s de audio) |
| APIs speech-to-speech (OpenAI/Gemini) | Se evalúan, pero privatidad/coste y control del enrutado local |
