"""Canal de escucha (JA → ES): frames → VAD → STT → MT → texto.

El pipeline no sabe de PipeWire ni del proveedor: recibe un flujo de **frames**
(``AsyncIterator[np.ndarray]`` float32 mono) y emite ``TurnResult`` por frase.

Orden de etapas y concurrencia:

  captura ──► VAD (segmenta por silencio) ──► cola acotada ──► STT (executor)
                                                              └► MT (async stream)

- El VAD se ejecuta en el bucle de captura (es barato, CPU).
- El STT es bloqueante: se ejecuta en un hilo del *executor*.
- El MT es asíncrono en streaming y mide el primer token.
- La cola está acotada: con backpressure se **descartan frases nuevas** (se
  registra el número) antes que acumular retardo. En la Fase 2 el canal de
  escucha degradará a *solo texto* cuando no dé abasto.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import numpy as np

from ..filters import TurnFilters
from ..latency import LatencyLog, Stopwatch, TurnTiming
from ..vad.base import SpeechSegment

log = logging.getLogger("interprete.pipeline")


@dataclass(slots=True)
class TurnResult:
    """Resultado de un turno: la frase original y su traducción."""

    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    speech_s: float
    timing: TurnTiming

    @property
    def total_ms(self) -> float | None:
        return self.timing.total_ms

    @property
    def mt_ttft_ms(self) -> float | None:
        """Latencia del primer token del MT (solo el MT)."""
        return self.timing.spans.get("mt_ttft_ms")

    @property
    def first_token_ms(self) -> float | None:
        """Del fin de frase al primer token traducido (STT + MT)."""
        return self.timing.spans.get("first_token_ms")

    def to_row(self) -> dict[str, float | str]:
        row = self.timing.to_row()
        row["speech_s"] = round(self.speech_s, 2)
        row["source"] = self.source_text
        row["target"] = self.target_text
        return row


class ListenPipeline:
    """Canal de escucha: consume frames y produce traducciones."""

    def __init__(
        self,
        *,
        stt,
        translator,
        segmenter,
        source_lang: str = "ja",
        target_lang: str = "es",
        context_sentences: int = 4,
        glossary: list[str] | None = None,
        on_result: Callable[[TurnResult], None] | None = None,
        latency_log: LatencyLog | None = None,
        max_queue: int = 8,
        filters: TurnFilters | None = None,
    ) -> None:
        self.stt = stt
        self.translator = translator
        self.segmenter = segmenter
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.context_sentences = max(0, context_sentences)
        self.glossary = glossary or []
        self.on_result = on_result
        self.latency_log = latency_log
        self.max_queue = max_queue
        self.filters = filters or TurnFilters()

        self._context: list[str] = []
        self.results: list[TurnResult] = []
        self.dropped = 0
        self.empty = 0
        self.errors = 0
        self.filtered = 0  # ruidos, frases inventadas y ecos
        self.echos = 0
        self.seconds_processed = 0.0

    # ------------------------------------------------------------------
    async def run(
        self,
        frames: AsyncIterator[np.ndarray],
        *,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Consume ``frames`` hasta agotarse o hasta ``stop_event``."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        worker = asyncio.create_task(self._worker(queue))
        iterator = frames.__aiter__()
        try:
            while not (stop_event and stop_event.is_set()):
                try:
                    frame = await iterator.__anext__()
                except StopAsyncIteration:
                    break
                self.seconds_processed += len(frame) / self._frame_rate()
                segment = self.segmenter.push(frame)
                if segment is not None:
                    self._enqueue(queue, segment)
        finally:
            tail = self.segmenter.flush()
            if tail is not None:
                self._enqueue(queue, tail)
            await queue.put(None)  # fin para el worker
            await worker
            aclose = getattr(iterator, "aclose", None)
            if aclose is not None:
                await aclose()

    def _frame_rate(self) -> int:
        return getattr(self.segmenter, "sample_rate", 16000)

    def _enqueue(self, queue: asyncio.Queue, segment: SpeechSegment) -> None:
        try:
            queue.put_nowait((time.perf_counter(), segment))
        except asyncio.QueueFull:
            self.dropped += 1
            log.warning("cola llena: se descarta una frase (total %d)", self.dropped)

    async def _worker(self, queue: asyncio.Queue) -> None:
        while True:
            item = await queue.get()
            if item is None:
                break
            t_enqueued, segment = item
            queue_ms = (time.perf_counter() - t_enqueued) * 1000.0
            try:
                result = await self.process(segment, queue_ms=queue_ms)
            except Exception as exc:  # noqa: BLE001 - un turno no debe tumbar el canal
                self.errors += 1
                log.exception("error procesando un turno: %s", exc)
                continue
            if result is None:
                self.empty += 1
                continue
            self.results.append(result)
            if self.latency_log is not None:
                self.latency_log.write(result.timing)
            if self.on_result is not None:
                self.on_result(result)

    # ------------------------------------------------------------------
    async def process(
        self, segment: SpeechSegment, *, queue_ms: float = 0.0
    ) -> TurnResult | None:
        """VAD→STT→MT de un segmento ya cerrado, con instrumentación."""
        sw = Stopwatch()
        sw.start()

        # Un chasquido, una tos o un golpe en la mesa no son una frase.
        if self.filters.is_too_short(segment.duration):
            self.filtered += 1
            sw.finish()
            return None

        loop = asyncio.get_running_loop()
        with sw.span("stt_ms"):
            text, source = await loop.run_in_executor(None, self._transcribe, segment)
        if not text:
            sw.finish()
            return None

        # Frase inventada por el STT (ruido, música, silencio).
        if self.filters.is_blocked_text(text):
            self.filtered += 1
            sw.finish()
            log.info("descartado por parecer inventado: %r", text)
            return None

        # Eco: el intérprete se está oyendo a sí mismo por los auriculares.
        if self.filters.is_echo(text):
            self.filtered += 1
            self.echos += 1
            sw.finish()
            log.info("descartado por eco del propio intérprete: %r", text)
            return None

        # Modo automático: si ya está en el idioma de destino, no hay nada que traducir.
        if self.source_lang == "auto" and source == self.target_lang:
            sw.mark("first_token_ms")
            timing = sw.finish()
            timing.add("no_translation", 1)
            return TurnResult(
                source_lang=source,
                target_lang=self.target_lang,
                source_text=text,
                target_text=text,
                speech_s=segment.duration,
                timing=timing,
            )

        parts: list[str] = []
        got_first = False
        mt_t0 = time.perf_counter()
        mt_ttft_ms: float | None = None
        with sw.span("mt_ms"):
            async for chunk in self.translator.translate_stream(
                text,
                source=source,
                target=self.target_lang,
                context=list(self._context) or None,
                glossary=self.glossary or None,
            ):
                if not got_first:
                    mt_ttft_ms = (time.perf_counter() - mt_t0) * 1000.0
                    sw.mark("first_token_ms")  # desde el fin de frase
                    got_first = True
                parts.append(chunk)
        target_text = "".join(parts).strip()

        timing = sw.finish()
        if mt_ttft_ms is not None:
            timing.add("mt_ttft_ms", mt_ttft_ms)
        if queue_ms:
            timing.add("queue_ms", queue_ms)
        if target_text and self.context_sentences:
            self._context.append(target_text)
            del self._context[: max(0, len(self._context) - self.context_sentences)]

        return TurnResult(
            source_lang=source,
            target_lang=self.target_lang,
            source_text=text,
            target_text=target_text,
            speech_s=segment.duration,
            timing=timing,
        )

    def _transcribe(self, segment: SpeechSegment) -> tuple[str, str]:
        """STT (idioma fijo o autodetectado). Devuelve (texto, idioma de origen)."""
        stt_lang = None if self.source_lang == "auto" else self.source_lang
        detailed = getattr(self.stt, "transcribe_detailed", None)
        if detailed is not None:
            text, detected = detailed(segment.audio, segment.sample_rate, stt_lang)
        else:  # pragma: no cover - backends sin detección
            text = self.stt.transcribe(segment.audio, segment.sample_rate, stt_lang)
            detected = None
        text = (text or "").strip()
        if self.source_lang == "auto":
            source = detected if detected in ("ja", "es") else self.target_lang
        else:
            source = self.source_lang
        return text, source
