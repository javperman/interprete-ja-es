"""Pipeline de canales (escucha JA→ES y habla ES→JA)."""

from .channel import Channel, tee_frames
from .listen import ListenPipeline, TurnResult
from .speaker import Speaker, SpanishSpeaker

__all__ = [
    "Channel",
    "ListenPipeline",
    "Speaker",
    "SpanishSpeaker",
    "TurnResult",
    "tee_frames",
]
