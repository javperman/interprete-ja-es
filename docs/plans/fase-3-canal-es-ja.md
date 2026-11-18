# Fase 3 — Canal de habla ES → JA (hacia `meet_mic`)

<!-- last-updated: 2026-11-13 -->

Objetivo: que **los demás te oigan en japonés**. El intérprete captura tu
micrófono físico, transcribe en español, traduce al japonés con VOICEVOX y lo
envía a `meet_out`, que es lo que ve Meet/Teams como micrófono (`meet_mic`).

## Tareas

1. **`Speaker` generalizado** (`pipeline/speaker.py`) con dos políticas:
   - `drop_new` (escucha): mientras habla, la frase nueva se descarta → solo texto.
   - `queue` (habla): las frases se encolan y se dicen **en orden**; si la cola se
     llena, se descarta la **más antigua** (el retraso no crece sin límite).
2. **`pipeline/channel.py`** — `Channel`: un canal completo (captura → VAD/STT/MT →
   locución a un nodo) reutilizable por ambos sentidos.
3. **STT compartido**: un único modelo Whisper con un `threading.Lock` serializa
   las llamadas de los dos canales (una sola copia en VRAM, ~1,2 GB).
4. **CLI**: comandos `speak` (solo ES→JA) y `run` (los dos canales a la vez, que es
   el modo de reunión), más `--mic`.
5. **Tests**: modo cola (orden y descarte de la más antigua).

## Criterio de aceptación

- Un WAV en español reproducido por el canal de habla produce japonés en
  `meet_out`, y ese japonés **se transcribe de vuelta** (inteligible).
- `run` arranca los dos canales, funciona en paralelo y cierra sin procesos
  huérfanos.

## Resultado (2026-11-13)

- **Hecho.** ES audio → STT 404 ms → MT 1er token 1131 ms → VOICEVOX → `meet_out`
  (max -7,4 dB). El japonés capturado de `meet_out` y re-transcrito coincide:
  `皆様おはようございます。お越しいただきありがとうございます。それでは本日の会議の議事次第の確認から始めましょう。`
- **Concurrencia:** con `run` activo, inyectar un clip JA en `meet_in` produjo la
  traducción JA→ES con voz **mientras** el canal de habla seguía capturando el
  micro (0 frases, silencio). Cierre limpio, sin `pw-cat`/`pw-record` colgados.
- **Latencia ES→JA:** STT 404 ms | MT 1er token 1131 ms | 1er token 1534 ms |
  total 1842 ms.
- **Pendiente (Fase 4):** UI/ajustes en caliente y pulido de logs.
