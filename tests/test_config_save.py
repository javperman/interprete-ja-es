"""Pruebas de guardado de la configuración (lo que usa la pestaña Ajustes)."""

from __future__ import annotations

import tomllib

from interprete.config import Config, dumps_config, load_config, save_config


def test_dumps_has_all_sections():
    text = dumps_config(Config())
    for section in ("[audio]", "[vad]", "[stt]", "[mt]", "[tts.es]", "[tts.ja]", "[ui]", "[logging]"):
        assert section in text


def test_dumps_serializes_types_and_lists():
    cfg = Config()
    cfg.mt.glossary = ["API", 'con "comillas"']
    cfg.mt.thinking = True
    cfg.stt.auto_language = True
    text = dumps_config(cfg)
    parsed = tomllib.loads(text)
    assert parsed["mt"]["glossary"] == ["API", 'con "comillas"']
    assert parsed["mt"]["thinking"] is True
    assert parsed["stt"]["auto_language"] is True


def test_round_trip(tmp_path):
    cfg = Config()
    cfg.tts_ja.speaker = 8
    cfg.tts_ja.intonation_scale = 0.75
    cfg.tts_ja.speed_scale = 0.95
    cfg.audio.duck_factor = 0.55
    cfg.tts_es.voice = "es_MX-ald-medium"
    cfg.mt.provider = "gemini"
    cfg.mt.context_sentences = 6
    cfg.audio.es_monitor_volume = 0.22
    path = save_config(cfg, tmp_path / "sub" / "config.toml")
    assert path.exists()
    again = load_config(path)
    assert again.tts_ja.speaker == 8
    assert abs(again.tts_ja.intonation_scale - 0.75) < 1e-9
    assert abs(again.tts_ja.speed_scale - 0.95) < 1e-9
    assert abs(again.audio.duck_factor - 0.55) < 1e-9
    assert again.tts_es.voice == "es_MX-ald-medium"
    assert again.mt.provider == "gemini"
    assert again.mt.context_sentences == 6
    assert abs(again.audio.es_monitor_volume - 0.22) < 1e-9


def test_fondos_audibles_por_defecto():
    """Los dos fondos deben oírse sin tocar nada (regresión de la queja real)."""
    cfg = Config()
    assert cfg.audio.ja_monitor_volume >= 0.40
    assert cfg.audio.es_monitor_volume >= 0.40
    # El atenuado es relativo: nunca deja el fondo por debajo de la mitad.
    assert abs(cfg.audio.ja_monitor_volume * cfg.audio.duck_factor) > 0.10
    assert abs(cfg.audio.es_monitor_volume * cfg.audio.duck_factor) > 0.10


def test_no_secrets_written():
    cfg = Config()
    text = dumps_config(cfg)
    assert "API_KEY" not in text
    assert "key" not in text.lower().replace("api_key_env", "")
