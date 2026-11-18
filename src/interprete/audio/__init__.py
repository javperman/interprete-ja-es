"""Audio: captura y reproducción contra los nodos de PipeWire."""

from .capture import (
    DEFAULT_RATE,
    FRAME_SAMPLES,
    PwCapture,
    inject_wav,
    wav_frames,
)
from .player import (
    JaForwarder,
    PwPlayback,
    PwPlayStream,
    apply_gain,
    playback_command,
)
from .pw import (
    default_sink,
    default_source,
    list_sink_names,
    list_source_names,
    node_exists,
    play_file,
    read_wav,
    record_to_wav,
    resample,
    write_wav,
)

__all__ = [
    "DEFAULT_RATE",
    "FRAME_SAMPLES",
    "JaForwarder",
    "PwCapture",
    "PwPlayStream",
    "PwPlayback",
    "apply_gain",
    "default_sink",
    "default_source",
    "inject_wav",
    "list_sink_names",
    "list_source_names",
    "node_exists",
    "play_file",
    "playback_command",
    "read_wav",
    "record_to_wav",
    "resample",
    "wav_frames",
    "write_wav",
]
