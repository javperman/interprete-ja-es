"""Instrumentación de latencia por etapa.

Objetivo realista: **2–4 s desde el fin de frase**. Este módulo mide el tiempo de
cada etapa (VAD, STT, primer token de MT, primer audio de TTS) y el extremo a
extremo, y lo puede volcar a un CSV.
"""

from __future__ import annotations

import csv
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Span:
    name: str
    t0: float
    dt_ms: float | None = None


@dataclass
class TurnTiming:
    """Tiempos de un turno (una frase) en milisegundos."""

    spans: dict[str, float] = field(default_factory=dict)
    total_ms: float | None = None

    def add(self, name: str, ms: float) -> None:
        self.spans[name] = round(ms, 1)

    def to_row(self) -> dict[str, float | str]:
        row: dict[str, float | str] = {k: v for k, v in self.spans.items()}
        if self.total_ms is not None:
            row["total_ms"] = round(self.total_ms, 1)
        return row


class Stopwatch:
    """Cronómetro simple por etapas dentro de un turno."""

    def __init__(self) -> None:
        self._marks: dict[str, float] = {}
        self._start: float | None = None
        self.timing = TurnTiming()

    def start(self) -> None:
        self._start = time.perf_counter()

    @contextmanager
    def span(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.timing.add(name, (time.perf_counter() - t0) * 1000)

    def mark(self, name: str) -> None:
        """Registra el instante de un hito (p. ej. primer token de MT)."""
        if self._start is None:
            raise RuntimeError("llama a start() antes de mark()")
        self.timing.add(name, (time.perf_counter() - self._start) * 1000)

    def finish(self) -> TurnTiming:
        if self._start is not None:
            self.timing.total_ms = (time.perf_counter() - self._start) * 1000
        return self.timing


class LatencyLog:
    """Escribe filas de latencia en CSV (cabecera a partir del primer turno)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._header_written = False

    def write(self, timing: TurnTiming) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = timing.to_row()
        new = not self.path.exists() or not self._header_written and not self.path.stat().st_size
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            if new:
                writer.writeheader()
                self._header_written = True
            writer.writerow(row)
