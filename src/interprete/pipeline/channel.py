"""Canal completo: captura → VAD/STT/MT → locución opcional.

``Channel`` reúne un ``ListenPipeline`` con la salida de audio correspondiente
(``Speaker`` hacia un nodo) y, si procede, con el reenvío del original
(``JaForwarder``). Sirve tanto para el canal de escucha (JA→ES) como para el de
habla (ES→JA): solo cambian idiomas, motor TTS y nodo de destino.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

import numpy as np

from ..audio.player import PwPlayback
from ..latency import LatencyLog
from .listen import ListenPipeline, TurnResult
from .speaker import Speaker

log = logging.getLogger("interprete.pipeline")


async def tee_frames(
    frames: AsyncIterator[np.ndarray], forwarder
) -> AsyncIterator[np.ndarray]:
    """Reenvía cada frame al ``forwarder`` (original de fondo) y lo deja pasar."""
    iterator = frames.__aiter__()
    try:
        while True:
            try:
                frame = await iterator.__anext__()
            except StopAsyncIteration:
                break
            forwarder.feed(frame)
            yield frame
    finally:
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()


class Channel:
    def __init__(
        self,
        name: str,
        *,
        stt,
        translator,
        segmenter,
        source_lang: str,
        target_lang: str,
        context_sentences: int = 4,
        glossary: list[str] | None = None,
        tts=None,
        play_target: str | None = None,
        player=None,  # inyectable para tests; si no, se crea un PwPlayback
        speaker_lang: str | None = None,
        speaker_mode: str = "drop_new",
        speaker_queue: int = 1,
        forwarder=None,
        on_result: Callable[[TurnResult], None] | None = None,
        latency_log: LatencyLog | None = None,
        max_queue: int = 8,
        filters=None,
        on_spoken: Callable[[str], None] | None = None,
    ) -> None:
        self.name = name
        self._user_on_result = on_result
        self._forwarder = forwarder
        self._pipeline = ListenPipeline(
            stt=stt,
            translator=translator,
            segmenter=segmenter,
            source_lang=source_lang,
            target_lang=target_lang,
            context_sentences=context_sentences,
            glossary=glossary,
            on_result=self._handle,
            latency_log=latency_log,
            max_queue=max_queue,
            filters=filters,
        )
        self.speaker: Speaker | None = None
        if tts is not None and (play_target or player is not None):
            if player is None:
                player = PwPlayback(play_target)
            self.speaker = Speaker(
                tts,
                player,
                lang=speaker_lang or target_lang,
                mode=speaker_mode,
                queue_size=speaker_queue,
                forwarder=forwarder,
                on_spoken=on_spoken,
            )

    def _handle(self, res: TurnResult) -> None:
        if self._user_on_result is not None:
            self._user_on_result(res)
        if self.speaker is not None:
            self.speaker.submit(res.target_text)

    async def run(
        self, frames: AsyncIterator[np.ndarray], *, stop_event=None
    ) -> None:
        if self._forwarder is not None:
            frames = tee_frames(frames, self._forwarder)
        await self._pipeline.run(frames, stop_event=stop_event)

    async def aclose(self) -> None:
        if self.speaker is not None:
            await self.speaker.aclose()

    @property
    def stats(self) -> ListenPipeline:
        return self._pipeline
