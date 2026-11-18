"""Locución de la traducción (canales de escucha y de habla).

``Speaker`` sintetiza el texto traducido y lo reproduce en un nodo, con dos
políticas de backpressure:

- ``drop_new`` (canal de escucha): mientras habla, la frase nueva se **descarta**
  y queda solo como texto — así cada frase se oye entera.
- ``queue`` (canal de habla): las frases se **encolan y se dicen en orden**; si la
  cola se llena, se descarta la **más antigua** (el retraso no crece sin límite).

Opcionalmente aplica *ducking* sobre el japonés de fondo mientras habla.
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..audio.player import PwPlayback
from ..tts.base import TtsEngine

log = logging.getLogger("interprete.pipeline.speaker")


class Speaker:
    def __init__(
        self,
        tts: TtsEngine,
        player: PwPlayback,
        *,
        lang: str = "es",
        mode: str = "drop_new",
        queue_size: int = 1,
        forwarder=None,  # JaForwarder | None, para el ducking
        on_spoken=None,
    ) -> None:
        if mode not in ("drop_new", "queue"):
            raise ValueError(f"modo de locución desconocido: {mode!r}")
        self.tts = tts
        self.player = player
        self.lang = lang
        self.mode = mode
        self.forwarder = forwarder
        self.on_spoken = on_spoken

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max(1, queue_size))
        self._worker: asyncio.Task | None = None
        self._playing = False

        self.enabled = True  # ajuste en caliente (tecla m/n en la TUI)
        self.spoken = 0
        self.skipped = 0
        self.muted = 0
        self.dropped = 0
        self.errors = 0
        self.last_synth_ms: float | None = None
        self.last_play_ms: float | None = None

    # ------------------------------------------------------------------
    def set_enabled(self, on: bool) -> None:
        """Activa o desactiva la locución (ajuste en caliente)."""
        self.enabled = bool(on)

    def busy(self) -> bool:
        return self._playing or not self._queue.empty()

    def submit(self, text: str) -> bool:
        """Encola una locución. Devuelve ``False`` si se ha descartado.

        No es ``async``: se llama desde el callback de resultados del pipeline,
        que ya corre en el bucle de eventos.
        """
        text = (text or "").strip()
        if not text:
            return False
        if not self.enabled:
            self.muted += 1
            return False
        self._ensure_worker()
        if self.mode == "drop_new":
            if self.busy():
                self.skipped += 1
                log.info("locución ocupada: se descarta la frase nueva (solo texto)")
                return False
            self._queue.put_nowait(text)
            return True
        # modo cola: si está llena, se descarta la más antigua
        try:
            self._queue.put_nowait(text)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:  # pragma: no cover
                pass
            try:
                self._queue.put_nowait(text)
            except asyncio.QueueFull:  # pragma: no cover
                return False
        return True

    # ------------------------------------------------------------------
    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.get_running_loop().create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            text = await self._queue.get()
            if text is None:
                break
            await self._one(text)

    async def _one(self, text: str) -> None:
        self._playing = True
        try:
            t0 = time.perf_counter()
            audio = await asyncio.get_running_loop().run_in_executor(
                None, self.tts.synthesize, text, self.lang
            )
            self.last_synth_ms = (time.perf_counter() - t0) * 1000.0
            if audio.audio.size == 0:
                return
            if self.forwarder is not None:
                self.forwarder.set_duck(True)
            t1 = time.perf_counter()
            await self.player.play(audio.audio, audio.sample_rate)
            self.last_play_ms = (time.perf_counter() - t1) * 1000.0
            self.spoken += 1
            if self.on_spoken is not None:
                self.on_spoken(text)
        except Exception as exc:  # noqa: BLE001 - una locución no debe tumbar el canal
            self.errors += 1
            log.exception("error al locutar: %s", exc)
        finally:
            self._playing = False
            if self.forwarder is not None:
                self.forwarder.set_duck(False)

    async def aclose(self, timeout: float = 20.0) -> None:
        """Deja terminar la cola (con límite) y para el worker."""
        worker, self._worker = self._worker, None
        if worker is None:
            return
        try:
            await asyncio.wait_for(self._drain(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            log.warning("locución: se agotó el tiempo de drenado")
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            pass

    async def _drain(self) -> None:
        """Espera a que no quede nada en cola ni sonando."""
        while self._playing or not self._queue.empty():
            await asyncio.sleep(0.02)


# Alias histórico (Fase 2, canal de escucha).
SpanishSpeaker = Speaker
