# AGENTS.md — Intérprete simultáneo JA ⇄ ES

<!-- last-updated: 2026-11-13 -->
<!-- auto-log: scripts/update-changelog.py -->

Reglas para cualquier agente (OpenCode, Hermes u otros) que trabaje en este
repositorio. Prevalecen sobre la comodidad. **Léelas antes de tocar nada.**

---

## 0. Propósito del proyecto

Aplicación de escritorio que actúa como **intérprete simultáneo bidireccional
japonés ⇄ español** en reuniones de Google Meet / Microsoft Teams (navegador)
sobre Linux con PipeWire:

- **Canal de escucha (JA → ES):** captura el audio de la reunión, lo transcribe,
  lo traduce y reproduce la voz en español **solo en los auriculares**.
- **Canal de habla (ES → JA):** captura el micrófono físico, transcribe, traduce
  al japonés, sintetiza y envía a un **micrófono virtual** para que los demás lo
  oigan en japonés.

Máquina objetivo: portátil de referencia, Arch Linux, Hyprland,
PipeWire, RTX 3050 Ti (4 GB) + Radeon 680M, 14 GiB de RAM, Python 3.14.

---

## 1. Regla de oro: actualizar la documentación tras **cada** cambio

**Obligatorio.** Toda investigación, decisión, prueba o implementación debe:

1. **Verificarse** con una fuente oficial o una comprobación local.
2. **Documentarse** en el documento que corresponda de `docs/` (nunca dejar la
   información solo en el chat).
3. **Registrar una entrada** en `docs/CHANGELOG.md`:

   ```bash
   python3 scripts/update-changelog.py \
     --task "Descripción breve del cambio" \
     --files "src/interprete/audio/nodes.py, docs/plans/fase-0-grafo-audio.md" \
     --sources "https://docs.pipewire.org/..., comprobación local con pw-dump" \
     --notes "Conclusión o decisión"
   ```

4. **Hacer commit.** El hook `.githooks/pre-commit` añade una entrada
   automáticamente si se toca `src/`, `scripts/`, `docs/` o `systemd/` y
   `AGENTS.md` no va en el commit.

No se borra ni reescribe a mano el bloque
`<!-- AUTO-LOG:START --> … <!-- AUTO-LOG:END -->` de `docs/CHANGELOG.md`; lo
gestiona el script. El resto del fichero se edita normalmente.

**El agente no debe dar una tarea por terminada si no ha actualizado la
documentación y el registro.**

---

## 2. Fuente de verdad y orden de lectura

1. `AGENTS.md` — este documento (reglas).
2. `ARCHITECTURE.md` — arquitectura vigente, nodos de audio y contratos.
3. `docs/design.md` — crítica del diseño, decisiones y alternativas descartadas.
4. `docs/plans/` — plan general y planes por fase.
5. `docs/CHANGELOG.md` — registro de cambios.
6. `README.md` — instalación, uso y configuración de Meet/Teams.

Si algo contradice a la documentación oficial (ArchWiki, PipeWire, vendor del
modelo), **gana la documentación oficial** y este repo se corrige.

---

## 3. Reglas de seguridad (no negociables)

1. **Secretos por variables de entorno.** `DEEPSEEK_API_KEY` y cualquier clave
   **nunca** en el código, en `config.toml` ni en los commits.
2. **No tocar la configuración de audio permanente del usuario** sin
   confirmación explícita. Todo lo que este proyecto cree debe poder deshacerse
   con `scripts/interprete-audio teardown`. No se editan ficheros ajenos como
   `51-alsa-soft-mixer.conf`; los ficheros de este proyecto se añaden aparte.
3. **`meet_in` jamás será el sink por defecto.** Si lo fuera, la TTS volvería a
   la entrada y habría realimentación.
4. **Operaciones destructivas** (`wipefs`, `mkfs`, `dd`, `parted`, `sgdisk`,
   `cryptsetup`, cambios de arranque) exigen confirmación humana explícita en el
   chat, aunque haya ventana de `sudo`.
5. **Frontera de la nube.** Indicar siempre qué texto sale a Internet. El motor
   de traducción por defecto es DeepSeek (nube); el texto de la reunión sale al
   proveedor. Cualquier cambio de proveedor se documenta y se avisa al usuario.
6. **No publicar el repo tal cual:** puede contener rutas y datos de inventario.

---

## 4. Reparto de trabajo y `sudo`

El agente ejecuta por su cuenta todo lo que pueda: entorno virtual, código,
tests, `systemctl --user`, `pactl`, `pw-cli`, `pw-link`, edición de ficheros.

`sudo` (p. ej. instalar `voicevox-engine` desde AUR) sigue el protocolo:

- Antes de usar `sudo`, ejecutar `sudo -n true`. Si falla, **pedir al usuario**
  que ejecute `sudo -v` y esperar su confirmación. No usar `askpass` ni `pkexec`.
- Agrupar en una sola tanda los comandos que necesiten root.
- La contraseña la escribe **solo el usuario**. El agente no la pide ni la
  escribe.

---

## 5. Git

- Identidad del agente, si aplica: `Hermes Agent <hermes@localhost>`.
- Ramas de trabajo: `hermes/<tarea>` o `feat/<tarea>`.
- **Sin preguntar:** `git add`, `git commit`, ramas de trabajo, tests, builds.
- **Requiere autorización explícita del usuario:** `git push` a `main`/`master`,
  despliegues, borrado de ramas remotas o tags, cambios de configuración en
  plataformas.
- **Prohibido siempre:** `git push --force` fuera de la propia rama, `reset
  --hard`, `clean -fdx`, `rebase` que descarte trabajo, empujar secretos,
  reescribir historial.

---

## 6. Convenciones

- Idioma: español. Fechas ISO 8601 (`2026-11-13`).
- Distinguir siempre **verificado**, **pendiente** y **no verificado**.
- Tipado en Python; cada componente (VAD, STT, MT, TTS) detrás de una interfaz.
- Los comandos destructivos se documentan con `# PELIGRO`.
- No incluir claves, tokens ni contraseñas, ni rutas de documentos personales.

---

## 7. Estructura del repositorio

```text
.
├── AGENTS.md                 # reglas (este fichero)
├── ARCHITECTURE.md           # arquitectura y nodos
├── README.md                 # instalación y uso
├── pyproject.toml
├── config.example.toml
├── docs/
│   ├── CHANGELOG.md          # registro (bloque AUTO-LOG gestionado por script)
│   ├── design.md             # crítica de diseño y decisiones
│   └── plans/                # plan general y planes por fase
├── pipewire/
│   └── 60-interprete.conf    # drop-in de nodos virtuales
├── scripts/
│   ├── interprete-audio      # setup/teardown/status/verify
│   ├── reunion.sh            # doctor + arranque del intérprete
│   ├── install-gui.sh        # lanzador + icono de la app (reversible)
│   ├── ver-llamada.sh        # informe de audio durante una llamada (solo lectura)
│   ├── aislar-llamada.sh     # (opcional) regla WirePlumber por media.role
│   ├── install-voicevox.sh   # VOICEVOX rootless + servicio de usuario
│   ├── install-piper.sh      # Piper (TTS español) + voz es_ES
│   ├── gcp-setup.sh          # Vertex AI: API, cuenta de servicio y clave
│   ├── make-test-clip.sh     # genera un clip JA de prueba con VOICEVOX
│   └── update-changelog.py
├── src/interprete/
│   ├── audio/  vad/  stt/  mt/  tts/  pipeline/  ui/  gui/
│   ├── session.py            # motor compartido por CLI y app
│   ├── routing.py            # enrutado en vivo (solo lectura)
│   ├── doctor.py             # comprobación previa a la reunión
│   ├── config.py
│   └── latency.py
├── systemd/user/             # unidades de usuario
└── tests/
```
