# Fase 0 — Grafo de audio y entorno

<!-- last-updated: 2026-11-13 -->

Objetivo: dejar el sistema listo para capturar/reproducir en los nodos virtuales
**sin bucles** y de forma **reversible**, y preparar el entorno (venv, VOICEVOX).

## Tareas

1. **Entorno virtual** Python 3.14 en `.venv` con las dependencias del proyecto.
2. **VOICEVOX Engine** desde AUR (build CPU). Servicio de usuario en
   `127.0.0.1:50021`.
3. **Drop-in de PipeWire** `60-interprete.conf` con `meet_in` y `meet_out`
   (`support.null-audio-sink`, `object.linger=true`).
4. **`scripts/interprete-audio`** con:
   - `setup` (idempotente): escribe el drop-in, crea `meet_mic` y el bucle a
     auriculares, arranca servicios.
   - `teardown`: elimina el drop-in y los nodos de runtime; deja el sistema como
     estaba.
   - `status`: lista nodos, enlaces y servicios.
   - `verify`: **prueba de tono** que demuestra que no hay bucles.
5. **Unidad systemd de usuario** para el grafo de audio.

## Prueba de tono (`verify`) — qué demuestra

- Un tono reproducido en `meet_in` **solo** debe oírse en los auriculares
  (nunca volver a `meet_out`/`meet_mic`).
- Un tono reproducido en `meet_out` **solo** debe aparecer en `meet_mic`
  (nunca en los auriculares ni en `meet_in`).
- `meet_in` no es el sink por defecto.

## Criterio de aceptación

- `interprete-audio verify` pasa todas las comprobaciones.
- Tras `teardown`, `pw-dump`/`pactl` no muestran ningún nodo `meet_*` y el sink
  por defecto sigue siendo el del usuario.
- VOICEVOX responde en `/version`.

## Registro

Cada paso implementado se anota en `docs/CHANGELOG.md` con
`scripts/update-changelog.py` (ver `AGENTS.md` §1).

## Resultado (2026-11-13)

- **Hecho.** `interprete-audio setup|verify|teardown` idempotentes y reversibles.
- `verify` pasa las 5 comprobaciones (nodos, sin realimentación, `meet_out→meet_mic`,
  captura de `meet_in.monitor`).
- Persistencia comprobada: tras `systemctl --user restart pipewire-pulse` los
  nodos se recrean desde el drop-in; `teardown` los elimina y deja el sink por
  defecto intacto.
- **Cambio de diseño:** se eliminó el nodo `pw-loopback` (no enlazaba bien el
  monitor); el japonés de fondo lo reenviará la app (Fase 2).
- **Entorno:** venv Python 3.14 con faster-whisper/ctranslate2/onnxruntime;
  VOICEVOX 0.26.1 rootless verificado (sintetiza japonés a 24 kHz).
- **Validación end-to-end:** VOICEVOX (ja) → Whisper GPU → texto correcto en 1,26 s.
