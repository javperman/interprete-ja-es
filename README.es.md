# Intérprete simultáneo japonés ⇄ español

Intérprete bidireccional para reuniones de **Google Meet / Microsoft Teams** en el
navegador, sobre Linux con **PipeWire**.

- **Escucha (JA → ES):** captura el audio de la reunión, lo transcribe, lo
  traduce y reproduce la voz en español **solo en tus auriculares** (con el
  japonés original de fondo a volumen bajo).
- **Habla (ES → JA):** captura tu micrófono, transcribe, traduce al japonés,
  sintetiza y lo envía a un **micrófono virtual** para que los demás te oigan en
  japonés.

Incluye una **app de escritorio** (GTK4) para llevarlo todo con botones, sin
escribir comandos: iniciar/parar, elegir dispositivos, transcripción en vivo,
subtítulos grandes y diagnóstico integrado.

> ⚠️ **Usa auriculares.** Con altavoces se produce un bucle.

## Estado

Proyecto en desarrollo por fases. Ver `docs/plans/` y `docs/CHANGELOG.md`.

## Requisitos

- Arch Linux con PipeWire + WirePlumber (probado en la máquina de pruebas).
- Python **3.14**.
- GPU NVIDIA con CUDA 12 para el STT (o CPU, más lento).
- `ffmpeg` en el PATH.
- VOICEVOX Engine (rootless) para la voz japonesa.

## Instalación

```bash
# 1. Entorno virtual
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'

# 2. Traducción con Vertex AI (Google Cloud)
./scripts/gcp-setup.sh        # habilita Vertex AI, crea la cuenta de servicio y su clave
# (alternativa sin GCP: export GEMINI_API_KEY='...' y provider="gemini" en config.toml)

# 3. Voz japonesa (VOICEVOX rootless, sin root; ~1,8 GB)
./scripts/install-voicevox.sh

# 4. Voz española (Piper, sin root)
./scripts/install-piper.sh

# 5. Grafo de audio
./scripts/interprete-audio setup
./scripts/interprete-audio verify  # prueba de tono: no debe haber bucles

# 6. App de escritorio (lanzador + icono; sin root y reversible)
./scripts/install-gui.sh
```

El STT usa `mobiuslabsgmbh/faster-whisper-large-v3-turbo`; si ya está en la caché
de Hugging Face del equipo no se descarga de nuevo. Para la GPU, el propio CLI se
reejecuta con `LD_LIBRARY_PATH` apuntando a las libs CUDA 12 de
`~/.local/share/hermes-cuda/` (no hay que exportar nada a mano).

## Configuración de Meet / Teams

1. **Salida (altavoz):** `Meet in` → así el intérprete captura las voces de los
   demás y tú las oyes por los auriculares.
2. **Entrada (micrófono):** `Meet mic` → así los demás reciben tu voz traducida al
   japonés. **Nunca** elijas tu micro físico en Meet: ese lo captura el intérprete.
3. **Desactiva** en Meet/Teams la *cancelación de eco* y la *supresión de ruido*
   (pueden cortar la voz sintetizada).

## Uso

### La app de escritorio (recomendado)

Búscala como **«Intérprete JA ⇄ ES»** en el lanzador (wofi/barra) o ábrela con:

```bash
interprete gui
```

Tres pestañas, todo con botones:

- **Reunión** — modo (ambos / solo oír / solo hablar), **micrófono** y
  **auriculares**, interruptores (voz en español, voz en japonés, japonés de
  fondo, tu voz de fondo, pausa), tres volúmenes (japonés de fondo, tu voz de
  fondo y cuánto se atenúan al traducir) y **transcripción en vivo** de los dos
  sentidos. Botón **Iniciar/Parar** en la cabecera y botón **Subtítulos** para
  abrir una ventana con la última traducción en grande.
- **Ajustes** — voz japonesa (los 128 estilos de VOICEVOX con **Probar voz**,
  velocidad, entonación y tono), voz española (Piper, con velocidad), proveedor y
  modelo de traducción, glosario, autodetección de idioma y mostrar el original.
  Se guarda en `config.toml`.
- **Diagnóstico** — las mismas comprobaciones que `interprete doctor` con botones
  **Arreglar**, más las **conexiones de audio en vivo** (quién reproduce en
  `meet_in` y quién lee tu micrófono) y el aviso si el navegador está usando el
  **micrófono físico** (te oirían en español).

Desde fuera de la app (atajos de Hyprland, scripts):

```bash
interprete gui --toggle      # iniciar/parar sin abrir la ventana
interprete gui --start       # iniciar directamente
interprete gui --subtitles   # mostrar/ocultar los subtítulos
```

`scripts/install-gui.sh` escribe además una regla de ejemplo de Hyprland
(`docs/hyprland-interprete.conf`) para dejar la ventana flotante y los subtítulos
fijados encima.

### Antes de una reunión: comprobación rápida

```bash
interprete doctor            # nodos, auriculares, micro, VOICEVOX, Piper, STT, Vertex
interprete doctor --live     # además, una traducción real de prueba
interprete doctor --fix      # crea los nodos / arranca VOICEVOX si faltan
./scripts/reunion.sh         # doctor + arranque del intérprete completo
```

`doctor` es **de solo lectura** y devuelve código ≠ 0 si hay bloqueos. `--fix`
solo ejecuta `interprete-audio setup` y `systemctl --user start
interprete-voicevox`; nada más toca el sistema.

### Intérprete completo (los dos sentidos a la vez)

Es el modo de reunión: oyes español por los auriculares y los demás te oyen en
japonés por `meet_mic`.

```bash
interprete run
interprete run --seconds 60           # se para solo a los 60 s (pruebas)
interprete run --ui subtitles         # solo la última traducción, en grande
```

### Interfaz y atajos

Con una terminal interactiva se abre la **TUI**: dos columnas (lo que oyes y lo
que oyen ellos), la transcripción reciente, las latencias por frase y el estado de
la voz. Elige el modo con `--ui` o `[ui] mode` en `config.toml`:

| `--ui` | Qué muestra |
|---|---|
| `auto` | TUI si hay terminal; texto corrido si no (por defecto) |
| `tui` | Pantalla completa de dos columnas |
| `subtitles` | La última traducción centrada y grande |
| `plain` | Texto corrido (para `tee`, cron o systemd) |

Atajos en la TUI:

| Tecla | Acción |
|---|---|
| `q` / `Ctrl+C` | salir |
| `m` | activar/silenciar la voz en español (lo que oyes) |
| `n` | activar/silenciar la voz en japonés (lo que oyen ellos) |
| `j` | japonés original de fondo sí/no |
| `+` / `-` | volumen del japonés de fondo |
| `p` | pausa: silencia voces y japonés sin dejar de capturar |
| `o` | mostrar/ocultar el texto original |
| `?` | ayuda |

Con la TUI activa, los logs van a `logs/interprete.log` para no romper la
pantalla.

### Canal de escucha JA → ES (texto + voz, tú oyes español)

```bash
interprete listen                     # reunión real: captura el monitor de meet_in
./scripts/make-test-clip.sh           # genera tests/clips/ja_sample.wav con VOICEVOX
interprete listen --inject tests/clips/ja_sample.wav   # prueba sin reunión
interprete listen --input tests/clips/ja_sample.wav    # replay del WAV por el pipeline
```

Opciones: `--sink meet_in`, `--headphones NODO` (por defecto el sink por defecto),
`--ja-volume 0-1` (volumen del japonés de fondo), `--no-ja` (no reenviar el
original), `--no-speak` (solo texto), `--seconds N`, `--latency-log RUTA`.

### Canal de habla ES → JA (los demás oyen japonés)

```bash
interprete speak                      # captura tu micro físico
interprete speak --input tests/clips/es_sample.wav   # replay para probar
```

Opciones: `--mic NODO` (por defecto el micro del sistema), `--meet-out meet_out`.

## Voz sintética

**Ambas voces son sintéticas** (no se clona tu voz ni la de los demás): el sistema
hace `voz → texto → texto traducido → voz`. Español con **Piper**
(`es_ES-davefx-medium`) y japonés con **VOICEVOX** (por defecto el estilo **11,
玄野武宏**; hay 128 estilos). Se cambian en `config.toml` (`[tts.es]`, `[tts.ja]`)
o desde la pestaña **Ajustes** de la app.

La voz japonesa viene elegida **midiendo tres cosas**, no a ojo: que sea **clara**
(no susurrante), de **tono medio** (ni grave) y con **ritmo normal** (ni lento).
Las voces graves, lentas y con aire suenan íntimas: la primera que se probó
(離途 シリアス, 93 Hz y la más susurrante de todas) resultó sonar «a otra cosa».
La voz por defecto es **玄野武宏** (130 Hz, clara y ágil) con
`intonation_scale = 0.85` para que la melodía no sea teatral.

En Ajustes puedes probar otras con **Probar voz** —las recomendadas van marcadas
con **★** y primero, todas medidas— y tocar **Velocidad**, **Entonación** y
**Tono**. Hay pruebas automáticas que verifican esos criterios, así que no se
puede colar una voz susurrante sin que falle la suite.

### Los dos fondos

La app reproduce **por debajo** de la traducción, para que la conversación no se
corte:

- **«Japonés de fondo»** (0,50): oyes a la otra persona en japonés mientras suena
  la traducción al español. Se ajusta con `[audio] ja_monitor_volume`.
- **«Mi voz de fondo»** (0,50): envía tu voz real a la reunión, además del japonés
  sintético. Se ajusta con `[audio] es_monitor_volume`.

Mientras habla la traducción, los dos fondos se atenúan al **40 %** del volumen
elegido (`[audio] duck_factor`; control **«Atenuar fondos al traducir»** en la
pestaña Reunión, 1,00 = no atenuar). Es un atenuado **relativo**: el fondo nunca
desaparece, solo baja.

Y si en la llamada se mezclan japonés y español, activa **«Detectar el idioma
automáticamente»** (`[stt] auto_language`).

> ⚠️ **Usa auriculares.** Con altavoces, la voz traducida vuelve por el micrófono.

## Si el intérprete traduce ruidos o «se traduce a sí mismo»

Son dos problemas distintos y hay un filtro para cada uno (pestaña **Ajustes** →
*Ruido, toses y eco*):

1. **Frases inventadas.** Con ruido, música, toses o silencio el STT *inventa*
   frases que nadie ha dicho (en japonés son típicas 「お待ちしております」 o
   「ご視聴ありがとうございました」). Se descartan por tres vías: la confianza del
   propio modelo (`no_speech_threshold`, `log_prob_threshold`,
   `compression_ratio_threshold`), una lista negra de frases conocidas
   (`[filters] blocklist`, ampliable) y una **duración mínima** de frase
   (`min_speech_ms`, 350 ms por defecto) para que un golpe en la mesa no cuente.
   Interruptor: **«Ignorar ruidos y frases inventadas»**.

2. **Eco (se traduce a sí mismo).** La voz sintetizada que suena en tus
   auriculares se escapa, la recoge el micrófono y el intérprete la vuelve a
   traducir. El intérprete recuerda lo que acaba de locutar (15 s) y descarta lo
   que suene demasiado parecido. Interruptor: **«Evitar que se traduzca a sí
   mismo (eco)»**.

En la barra inferior de la ventana verás `N ignoradas` en cada canal: es lo que
se ha descartado por estos filtros.

> Si aun así oyes que se cuela, baja el volumen del **japonés de fondo** o de la
> voz en español, o usa auriculares cerrados: el eco es físico antes que
> digital. Y si una frase legítima se está filtrando, el `min_speech_ms` hay que
> bajarlo, o quitar el interruptor.

## Si no oyes los fondos

1. Los interruptores **«Japonés de fondo»** y **«Mi voz de fondo»** deben estar
   marcados (arrancan apagados si los desmarcaste en una sesión anterior).
2. Mira los volúmenes: por debajo de ~0,15 no se distinguen de la traducción.
3. Comprueba en la pestaña **Diagnóstico** → *Ver conexiones* que el navegador
   usa `meet_mic` y reproduce en `meet_in`.
4. Revisa `logs/interprete.log`: al arrancar la sesión debe aparecer
   `el japonés de fondo activo → …` y `tu voz de fondo activo → …`. Si no
   aparecen, los fondos no se han podido arrancar (mira el aviso en la app).

## Si sale «CUDA failed with error out of memory»

Tu GPU tiene 4 GB y el modelo de voz ocupa ~2 GB. Desde la Fase 8 el modelo se
**reutiliza** entre sesiones del mismo proceso (antes, al parar y volver a
iniciar, se cargaba **otro** modelo sin soltar el primero y la GPU se quedaba sin
memoria), y `device = "auto"` intenta CUDA y, si no cabe, **sigue en CPU** para
que la reunión no se quede sin intérprete (más lento, pero funciona).

Si aun así se queda corta:

1. Pestaña **Diagnóstico** → botón **«Liberar memoria de la GPU»** (descarga el
   modelo; se vuelve a cargar al iniciar la próxima sesión).
2. Cierra pestañas del navegador con vídeo o juegos que usen la tarjeta.
3. Para no depender de la GPU: `[stt] device = "cpu"` en `config.toml`.

Para ver quién ocupa la memoria: `nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv`.

## Si Meet/Teams no ve el micrófono

El micrófono virtual debe llamarse **«Micro_del_interprete»** en la lista de Meet.
Chromium/Brave **oculta** las fuentes que parecen monitores, así que la
descripción del nodo **no** puede contener la palabra «monitor» (ya está
corregido en `pipewire/60-interprete.conf`).

Si no aparece en la lista:

1. **Recarga los nodos** (por si venían de una versión anterior):
   ```bash
   ./scripts/interprete-audio reload
   ```
2. **Recarga la página de Meet** (F5) para que el navegador vuelva a enumerar los
   dispositivos.
3. Comprueba el **permiso de micrófono** de Brave para `meet.google.com`: icono
   del candado/ajustes del sitio en la barra de direcciones → *Micrófono* →
   *Permitir*.
4. Elige **«Micro_del_interprete»**, **nunca** tu micro físico.

Para ver qué está pasando de verdad durante la llamada (solo lectura):

```bash
./scripts/ver-llamada.sh
```

> Nota: la app captura **tu micro físico**; Meet debe usar **«Micro_del_interprete»**.

### Otros comandos
```bash
interprete nodes                                 # estado de los nodos de audio
interprete gui                                   # app de escritorio (GTK4)
interprete doctor                                # comprobación previa a la reunión
interprete translate "こんにちは" --from ja --to es  # prueba del proveedor de MT
./scripts/ver-llamada.sh                         # informe de audio DURANTE una llamada
./scripts/aislar-llamada.sh                      # (opcional) aislar el audio de la llamada
```

## Desinstalación

```bash
./scripts/install-gui.sh --revert     # quita lanzador e icono de la app
./scripts/interprete-audio teardown   # elimina los nodos virtuales
```

## Documentación

- `ARCHITECTURE.md` — nodos de audio, pipeline y contratos.
- `docs/design.md` — decisiones de diseño y alternativas descartadas.
- `docs/plans/` — plan general y por fases.
- `AGENTS.md` — reglas para agentes que trabajen en el repo.

## Privacidad

El motor de traducción por defecto es **Google Gemini (nube)**: el **texto** de la
reunión sale a Google. La voz no sale del equipo. Alternativa: DeepSeek. Cambiar
de proveedor es una línea en `config.toml` (`provider = "deepseek"`).

---

[English README](README.md) · [Licencia](LICENSE) · [Terceros](THIRD-PARTY.md)
