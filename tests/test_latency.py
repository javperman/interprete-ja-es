"""Pruebas de la instrumentación de latencia."""

from __future__ import annotations

import time

from interprete.latency import LatencyLog, Stopwatch


def test_stopwatch_spans():
    sw = Stopwatch()
    sw.start()
    with sw.span("stt"):
        time.sleep(0.01)
    sw.mark("mt_first_token")
    timing = sw.finish()
    assert timing.spans["stt"] >= 10
    assert "mt_first_token" in timing.spans
    assert timing.total_ms is not None


def test_latency_log_csv(tmp_path):
    sw = Stopwatch()
    sw.start()
    with sw.span("vad"):
        pass
    timing = sw.finish()

    out = tmp_path / "latency.csv"
    LatencyLog(out).write(timing)
    content = out.read_text(encoding="utf-8")
    assert "vad" in content.splitlines()[0]
    assert "total_ms" in content.splitlines()[0]
