"""Pruebas del mapa de teclas de la TUI."""

from __future__ import annotations

from interprete.ui.keys import KEYMAP, parse_actions


def test_parse_single_keys():
    assert parse_actions(b"q") == ["quit"]
    assert parse_actions(b"m") == ["toggle_tts_listen"]
    assert parse_actions(b"n") == ["toggle_tts_speak"]
    assert parse_actions(b"j") == ["toggle_ja"]
    assert parse_actions(b"p") == ["toggle_pause"]
    assert parse_actions(b"o") == ["toggle_original"]
    assert parse_actions(b"?") == ["help"]


def test_parse_cyg_and_unknown():
    assert parse_actions(b"\x03") == ["quit"]  # Ctrl+C en modo raw
    assert parse_actions(b"zZ1") == []  # teclas no mapeadas se ignoran


def test_parse_multiple_bytes():
    assert parse_actions(b"j+p") == ["toggle_ja", "ja_volume_up", "toggle_pause"]


def test_volume_keys_aliases():
    assert parse_actions(b"+=") == ["ja_volume_up", "ja_volume_up"]
    assert parse_actions(b"-_") == ["ja_volume_down", "ja_volume_down"]


def test_every_action_has_a_key():
    actions = set(KEYMAP.values())
    for expected in ("quit", "toggle_tts_listen", "toggle_ja", "help"):
        assert expected in actions
