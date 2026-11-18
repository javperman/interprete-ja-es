"""Pruebas del enrutado en vivo (parseo puro, sin PipeWire)."""

from __future__ import annotations

from interprete import routing

SINK_INPUTS = [
    {
        "index": 1,
        "sink": 2670,
        "properties": {
            "application.name": "Brave",
            "media.role": "Communication",
            "node.name": "brave",
        },
    },
    {"index": 2, "sink": 62, "properties": {"application.name": "mpv", "node.name": "mpv"}},
]
SOURCE_OUTPUTS = [
    {
        "index": 3,
        "source": 2687,
        "properties": {"application.name": "Brave", "node.name": "brave"},
    },
    {
        "index": 4,
        "source": 2678,
        "properties": {"node.name": "input.meet_mic", "client": "pipewire"},
    },
]
NAMES = {2670: "meet_in", 62: "alsa_output.hp", 2687: "meet_mic", 2678: "meet_out"}


def test_parse_streams_maps_target_names():
    streams = routing.parse_streams(SINK_INPUTS, "sink", NAMES)
    assert [s.target for s in streams] == ["meet_in", "alsa_output.hp"]
    assert streams[0].app == "Brave"
    assert streams[0].media_role == "Communication"


def test_internal_streams_are_filtered():
    streams = routing.parse_streams(SOURCE_OUTPUTS, "source", NAMES)
    assert streams[1].internal is True  # input.meet_mic (módulo interno)
    assert [s.app for s in routing.external(streams)] == ["Brave"]


def test_missing_or_bad_index_does_not_crash():
    entries = [{"index": 9, "sink": "x", "properties": {}}]
    streams = routing.parse_streams(entries, "sink", {})
    assert streams[0].target == "#-1"
    assert streams[0].label == "#9"


def test_routing_report_flags_physical_mic(monkeypatch):
    from interprete.config import Config

    cfg = Config()
    cfg.audio.mic = "alsa_input.mic"
    cfg.audio.source_mic = "meet_mic"
    monkeypatch.setattr(routing, "sink_inputs", lambda: routing.parse_streams(SINK_INPUTS, "sink", NAMES))
    monkeypatch.setattr(
        routing,
        "source_outputs",
        lambda: routing.parse_streams(
            [{"index": 5, "source": 63, "properties": {"application.name": "Brave"}}],
            "source",
            {63: "alsa_input.mic"},
        ),
    )
    report = "\n".join(routing.routing_report(cfg))
    assert "Brave" in report
    assert "alsa_input.mic" in report
    assert "NO debería leerlo" in report


def test_routing_report_when_idle(monkeypatch):
    from interprete.config import Config

    cfg = Config()
    cfg.audio.mic = "alsa_input.mic"
    monkeypatch.setattr(routing, "sink_inputs", lambda: [])
    monkeypatch.setattr(routing, "source_outputs", lambda: [])
    report = "\n".join(routing.routing_report(cfg))
    assert "nada" in report


def test_pactl_failure_is_silent(monkeypatch):
    monkeypatch.setattr(routing.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert routing.sink_inputs() == []
    assert routing.source_outputs() == []
