"""Estado observable de la aplicación (lo que pinta la UI).

Es un contenedor **puro** (sin terminal, sin asyncio): el pipeline y el CLI lo
actualizan, y cada UI (plana, TUI o subtítulos) decide cómo mostrarlo. Esto
permite probar la lógica de la interfaz sin abrir una terminal real.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

MAX_NOTICES = 40


@dataclass(slots=True)
class Line:
    """Una frase ya traducida (texto original + traducción)."""

    source: str
    target: str


@dataclass(slots=True)
class ChannelState:
    """Estado de un canal (escucha JA→ES o habla ES→JA)."""

    key: str
    name: str
    source_lang: str
    target_lang: str
    tts_label: str = ""
    turns: int = 0
    spoken: int = 0
    skipped: int = 0
    muted: int = 0
    dropped: int = 0
    errors: int = 0
    empty: int = 0
    filtered: int = 0  # ruidos, frases inventadas y ecos descartados
    echos: int = 0
    last_stt_ms: float | None = None
    last_first_token_ms: float | None = None
    last_total_ms: float | None = None
    lines: list[Line] = field(default_factory=list)
    max_lines: int = 200
    tts_on: bool = True

    def add(self, res) -> Line:
        """Registra un ``TurnResult`` del pipeline."""
        line = Line(source=res.source_text, target=res.target_text)
        self.lines.append(line)
        if len(self.lines) > self.max_lines:
            del self.lines[: len(self.lines) - self.max_lines]
        self.turns += 1
        self.last_stt_ms = res.timing.spans.get("stt_ms")
        self.last_first_token_ms = res.first_token_ms
        self.last_total_ms = res.total_ms
        return line

    def latest(self, n: int = 1) -> list[Line]:
        """Los últimos ``n`` turnos (el más reciente al final)."""
        if n <= 0:
            return []
        return self.lines[-n:]


@dataclass(slots=True)
class Notice:
    level: str  # info | warn | error | ok
    text: str


@dataclass
class AppState:
    """Todo lo que la UI necesita para pintarse."""

    mode: str = "run"
    provider: str = ""
    model: str = ""
    privacy: str = ""
    channels: list[ChannelState] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    info: dict[str, str] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)
    running: bool = True

    # ------------------------------------------------------------------
    def channel(self, key: str) -> ChannelState | None:
        for ch in self.channels:
            if ch.key == key:
                return ch
        return None

    def elapsed_s(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def add_notice(self, level: str, text: str) -> Notice:
        notice = Notice(level=level, text=text)
        self.notices.append(notice)
        if len(self.notices) > MAX_NOTICES:
            del self.notices[: len(self.notices) - MAX_NOTICES]
        return notice

    def last_notice(self, levels: tuple[str, ...] = ("warn", "error", "ok", "info")) -> Notice | None:
        """La última notificación de mayor prioridad (o la más reciente)."""
        for level in levels:
            for notice in reversed(self.notices):
                if notice.level == level:
                    return notice
        return None
