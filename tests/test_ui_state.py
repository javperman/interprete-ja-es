"""Pruebas del estado de la UI (sin terminal)."""

from __future__ import annotations

import time

from interprete.latency import TurnTiming
from interprete.pipeline.listen import TurnResult
from interprete.ui.state import AppState, ChannelState


def _res(source: str, target: str, *, stt: float = 400, first: float = 1200, total: float = 1400):
    timing = TurnTiming(spans={"stt_ms": stt, "first_token_ms": first}, total_ms=total)
    return TurnResult("ja", "es", source, target, 2.0, timing)


def test_channel_add_updates_counters_and_latencies():
    ch = ChannelState(key="listen", name="JA → ES", source_lang="ja", target_lang="es")
    ch.add(_res("こんにちは", "Hola"))
    assert ch.turns == 1
    assert ch.last_stt_ms == 400
    assert ch.last_first_token_ms == 1200
    assert ch.last_total_ms == 1400
    assert ch.lines[0].source == "こんにちは"
    assert ch.lines[0].target == "Hola"


def test_channel_caps_history():
    ch = ChannelState(key="listen", name="x", source_lang="ja", target_lang="es", max_lines=3)
    for i in range(10):
        ch.add(_res(f"s{i}", f"t{i}"))
    assert len(ch.lines) == 3
    assert [line.target for line in ch.lines] == ["t7", "t8", "t9"]
    assert ch.turns == 10


def test_channel_latest():
    ch = ChannelState(key="listen", name="x", source_lang="ja", target_lang="es")
    for i in range(4):
        ch.add(_res(f"s{i}", f"t{i}"))
    assert [line.target for line in ch.latest(2)] == ["t2", "t3"]
    assert ch.latest(0) == []


def test_app_state_channel_lookup():
    state = AppState()
    state.channels.append(ChannelState(key="listen", name="a", source_lang="ja", target_lang="es"))
    assert state.channel("listen") is not None
    assert state.channel("nope") is None


def test_app_state_notices_priority():
    state = AppState()
    state.add_notice("info", "hola")
    state.add_notice("warn", "ojo")
    state.add_notice("info", "otra")
    assert state.last_notice().text == "ojo"


def test_app_state_elapsed_is_monotonic():
    start = time.monotonic()
    state = AppState()
    assert state.elapsed_s() >= 0
    assert time.monotonic() - start < 1
