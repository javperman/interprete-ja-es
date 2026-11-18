# Fase 6 — Voz con tono de negocios y fondos audibles

<!-- last-updated: 2026-11-13 -->

Correcciones a partir de la primera prueba real con la novia del usuario
(reunión de Meet). Tres quejas concretas:

1. «La voz japonesa parece de anime, se escucha poco natural.»
2. «Estaría mejor que se escuche mi voz de fondo, no solo la traducción.»
3. «Tampoco escucho el japonés de fondo.»

Las tres tenían causa medida, no eran impresiones.

## 1. La voz japonesa sonaba a anime

### Medición (no a ojo)

Se midió el **rango de entonación** (diferencia p10–p90 del tono F0, en
semitonos) de las voces masculinas del motor con la misma frase de reunión. Un
rango alto es lo que suena a «anime»; uno bajo suena sobrio.

| Voz (estilo) | Rango de entonación (semitonos) |
|---|---|
| **離途 (シリアス)** | **3,0 – 4,7** (el más sobrio) |
| 雀松朱司 | 4,2 – 10,5 |
| 玄野武宏 | 5,3 – 13,1 |
| 青山龍星 (la que había) | 6,2 – 15,6 |
| ちび式じい | (tono muy agudo) |

La voz que sonaba a anime era **青山龍星**, la segunda más exagerada de todas.
También se comprobó que `intonationScale` aplana la melodía de forma **monótona**
en todas las voces (de ahí el rango de dos valores por fila).

### Primera decisión (después revertida, ver más abajo)

- Voz: **離途 (シリアス)** (`speaker = 101`), `intonation_scale = 0.80`.
- Efecto medido: **11,1 → 3,6 semitonos** de rango frente a la voz anterior.

## 1b. Segunda prueba real: «se escucha como teniendo sexo»

Con 離途 (シリアス) la novia del usuario describió la voz como «demasiado
entonada, incluso erótica». **La métrica elegida era la correcta pero
insuficiente**: se había optimizado solo la melodía y se acabó en la voz más
**grave, lenta y susurrante** de todas, que es justo el perfil de una voz íntima.

Se añadieron dos métricas y se midieron 13 voces:

| Voz | F0 | Rango | **Periodicidad** | ms/carácter |
|---|---|---|---|---|
| **離途 シリアス** (la que sonaba íntima) | 93 Hz | 3,7 | **0,568** (la peor) | 156 (la más lenta) |
| 玄野武宏 ← **nueva por defecto** | 130 Hz | 9,5 | 0,605 | **128** (la más ágil) |
| 黒沢冴白 | 150 Hz | 8,5 | 0,647 | 161 |
| No.7 アナウンス | 195 Hz | 7,3 | 0,725 | 138 |
| 中部つるぎ | 200 Hz | 9,4 | **0,755** | 143 |
| 猫使アル おちつき | 218 Hz | 9,5 | 0,767 | 135 |

- **Periodicidad** (pico medio de autocorrelación, 0–1) distingue una voz **clara**
  de una **susurrante con aire**: 離途 シリアス tenía la más baja del catálogo.
- **F0** muy bajo (93 Hz) + **ritmo** lento (156 ms/carácter) completan el perfil
  «íntimo».

### Decisión final

Voz por defecto: **玄野武宏** (`speaker = 11`, 130 Hz, la más ágil, voz masculina
neutra de narración) con `intonation_scale = 0.85`.

Criterios de la lista ★ de la app (verificados por pruebas automáticas):

| Criterio | Umbral |
|---|---|
| F0 | 120–210 Hz |
| Periodicidad | > 0,60 |
| Ritmo | < 150 ms/carácter |
| Rango de entonación | < 9 semitonos |

Recomendadas: **11** 玄野武宏, **30** No.7 アナウンス, **94** 中部つるぎ,
**100** 黒沢冴白. Descartadas y documentadas en `EVITAR_JA`: 101 離途 シリアス
(susurrante), 53 麒ヶ島宗麟 y 21 剣崎雌雄 (melodía teatral, > 11 semitonos: lo
detectó la propia prueba al intentar marcarlas con ★).

> **La TTS de Google** (`ja-JP-Neural2-*`, `ja-JP-Chirp3-HD-*`) sería la salida
> para una voz realmente profesional: se comprobó que la cuenta de servicio sirve
> para autenticarse, pero la API `texttospeech.googleapis.com` está **deshabilitada**
> en tu proyecto de GCP (403). Habilitarla es un comando sin coste
> (`gcloud services enable texttospeech.googleapis.com`); el uso cuesta ~2-5
> céntimos por reunión. Queda pendiente de decidir con el usuario.


## 2 y 3. Los dos fondos estaban **mudos** (bug real)

`JaForwarder` reproduce con un `pw-cat` en segundo plano que hay que **arrancar**
(`await start()`). Sin ese arranque la cola interna queda en `None` y `feed()`
descarta todos los frames **sin error ni aviso**. Al extraer el motor del CLI a
`session.py` (Fase 5) se perdió esa llamada — el CLI antiguo la tenía:

```python
# 2ac26d7:src/interprete/__main__.py  (lo que se perdió)
async def _main() -> None:
    if forwarder is not None:
        await forwarder.start()
```

Es decir: **el japonés de fondo y el «mi voz de fondo» nunca sonaron**, aunque
los interruptores dijeran que sí.

### Arreglo

- Nuevo `_start_fondo()` en `session.py`: crea **y arranca** el reenvío; si falla,
  avisa en la interfaz y la sesión sigue sin ese fondo (un fondo roto no debe
  tumbar la llamada).
- Se arrancan los **dos** reenvíos (antes solo se contemplaba uno).
- Pruebas nuevas en `tests/test_fondos.py` que fijan el arranque (incluida una
  que abre una sesión completa con dobles).

### Verificación con audio grabado

Se grabó el nodo `meet_out` (para que no lo contaminara la llamada real del
usuario) silenciando las voces sintéticas para aislar cada fondo:

| Caso | RMS | Respecto al original |
|---|---|---|
| Japonés de fondo **ON** (vol 0,50) | 0,0276 | −6,3 dB (ganancia 0,50 exacta) |
| Japonés de fondo **OFF** (control) | 0,0000 | silencio absoluto |
| Mi voz de fondo **ON** (vol 0,50) | 0,0273 | −6,4 dB (ganancia 0,50 exacta) |
| Mi voz de fondo **OFF** (control) | 0,0000 | silencio absoluto |

Y de punta a punta **desde la propia app** (clip inyectado en `meet_in`,
grabando `meet_out`): 0–6 s el japonés de fondo, 7–9 s pausa, 10–14 s la voz
japonesa sintetizada a plena potencia.

## 4. Niveles y atenuación

Los valores anteriores (0,30 y 0,15 con atenuación a un valor **fijo** de 0,12)
dejaban los fondos al borde de lo inaudible: cualquier volumen de fondo acababa
cayendo a 0,12 mientras hablaba la traducción.

- `ja_monitor_volume = 0.50` y `es_monitor_volume = 0.50` por defecto.
- La atenuación pasa a ser **relativa** (`duck_factor = 0.40`): el fondo se
  multiplica por ese factor mientras suena la traducción, así **nunca
  desaparece** aunque se suba o baje el volumen.
- Tercer control en la pestaña Reunión: **«Atenuar fondos al traducir»** (0,40 por
  defecto; 1,00 = no atenuar), aplicable en caliente.
- `1.2`: la app también arregló dos fallos de interfaz encontrados por el camino
  (los tres desplegables salían vacíos y los marcos de Ajustes estaban vacíos con
  los controles fuera).

## 5. Tercera prueba: «traduce cualquier sonido» (ruidos y eco)

Dos causas distintas, medidas y atacadas por separado.

### 5a. El STT inventa frases con ruido o silencio

En la captura de la sesión aparecían frases que nadie había dicho
(「お待ちしております」「ご視聴ありがとうございました」): son **alucinaciones** de
Whisper, que con ruido, música o silencio genera texto plausible. Se atacan en
tres capas:

1. **Confianza del modelo** (parámetros de `transcribe` + filtro por segmento):
   `no_speech_threshold = 0,6`, `log_prob_threshold = -1,0`,
   `compression_ratio_threshold = 2,4`.
2. **Lista negra** de frases conocidas (`filters.is_hallucination`), ampliable
   desde `[filters] blocklist`.
3. **Duración mínima** de frase (`min_speech_ms = 350`): un golpe, una tos o un
   chasquido no llegan ni al STT.

**Verificado** con el modelo real (en CPU, la GPU estaba ocupada por la sesión
del usuario): silencio 2 s, ruido bajo, ruido fuerte y un golpe corto → **vacío**;
el clip de habla real → transcrito correctamente (no se filtra el habla buena).

### 5b. Eco: el intérprete se traducía a sí mismo

La voz sintetizada de los auriculares se escapa y vuelve por el micrófono; el
canal de habla la transcribía y la mandaba otra vez a la reunión.

`filters.EchoGuard` recuerda lo que el intérprete acaba de locutar (15 s, guardia
**compartido** por los dos canales) y descarta lo que se parezca demasiado
(comparación normalizada con `SequenceMatcher` ≥ 0,85 o contención ≥ 0,70). Las
frases de menos de 8 caracteres («Sí», «はい») quedan exentas para no tirar
respuestas cortas legítimas.

### Interfaz y ajustes

Pestaña Ajustes → *Ruido, toses y eco*: «Ignorar ruidos y frases inventadas»,
«Evitar que se traduzca a sí mismo (eco)» y la **duración mínima** en ms. La barra
de estado muestra **`N ignoradas`** por canal, y el resumen final añade
`filtradas N (ecos M)`.

Ficheros: `src/interprete/filters.py` (nuevo y puro), `stt/faster_whisper.py`,
`pipeline/listen.py`, `pipeline/channel.py`, `session.py`, `ui/state.py`,
`gui/page_settings.py`, `gui/window.py`, `config.py` (sección `[filters]`).

Pruebas: `tests/test_filters.py` (31, incluidas cuatro sobre el pipeline real),
y las de pipeline/canal pasan con `min_speech_ms=0` porque usan segmentos de 32 ms.

## 6. Cuarta prueba: «CUDA failed with error out of memory»

Al pulsar **Iniciar** una segunda vez (sin cerrar la app) la sesión fallaba con
`RuntimeError: CUDA failed with error out of memory`.

El registro lo dejó claro: a las 11:48 la sesión iba bien y a las 11:55 el
**mismo proceso** intentó cargar el modelo otra vez sin soltar el anterior. La
GPU del equipo tiene **4 GB** y el modelo ocupa ~2 GB, así que la segunda copia no
cabía. Comprobado con `nvidia-smi`: el proceso de la app retenía **3,6 GB** de
VRAM; al cerrarlo bajaron a 150 MiB.

Es decir: **no se podía parar y volver a iniciar una sesión**, que es justo lo que
hace cualquiera al probar.

### Arreglo

- `modelo_compartido()`: el modelo vive en una caché **por proceso** y se
  reutiliza; la segunda sesión usa el mismo objeto (0 MB extra).
- `close()` del STT ya no lo descarga (se comparte); para liberar de verdad está
  `liberar_modelos()`, expuesto como botón **«Liberar memoria de la GPU»** en
  Diagnóstico.
- `device = "auto"` (nuevo valor por defecto): intenta CUDA y, si falla por
  memoria, **cae a CPU con `int8`** y avisa en el log. `cuda` explícito sigue
  fallando si no cabe, para no mentir sobre el rendimiento.
- El reejecutado con `LD_LIBRARY_PATH` también cubre `auto` (si no, ctranslate2
  no encontraba las libs y caía a CPU sin avisar).

Pruebas: `tests/test_stt_modelo.py` (7), con un `WhisperModel` falso que simula la
falta de memoria y comprueba que el modelo se reutiliza entre sesiones.

## Ficheros tocados

| Fichero | Cambio |
|---|---|
| `audio/player.py` | `duck_factor` relativo, `current_gain()`, `set_duck_factor()` |
| `session.py` | `_start_fondo()` (arranque de los dos fondos), `set_duck`, `duck_factor` en opciones/estado |
| `config.py` | volúmenes 0,50; `duck_factor`; prosodia de VOICEVOX; voz por defecto 11 |
| `tts/voicevox.py`, `tts/factory.py` | `speed_scale`, `intonation_scale`, `pitch_scale` |
| `gui/page_meeting.py` | tercer control de volumen (atenuación) |
| `gui/page_settings.py`, `gui/voices.py` | prosodia con preescucha y voces ★ medidas (con `abrevia()`) |
| `gui/widgets.py` | `Choice` se dibujaba vacío; nuevo `Section` |
| `gui/window.py` | `INTERPRETE_START_PAGE` (abrir la app en una pestaña, útil para pruebas) |
| `__main__.py` | `--duck-factor` |
| `tests/` | `test_fondos.py`, prosodia de VOICEVOX, fondo relativo, config |

## Pendiente

- Probar en una llamada real la mezcla final (los dos fondos a la vez con la voz
  sintetizada): los niveles 0,50/0,50 son un punto de partida medido, no una
  preferencia confirmada por el usuario.
- **Voz de Google**: la métrica de claridad acota el problema, pero VOICEVOX es un
  motor de voces de personaje; si 玄野武宏 sigue sin convencer en la prueba real,
  la TTS de Google es el siguiente paso (requiere habilitar la API).
