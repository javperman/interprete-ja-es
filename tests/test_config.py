"""Pruebas de la carga de configuración."""

from __future__ import annotations

import textwrap

from interprete.config import load_config


def test_defaults():
    cfg = load_config(None)
    assert cfg.audio.sink_in == "meet_in"
    assert cfg.audio.source_mic == "meet_mic"
    assert cfg.mt.provider == "deepseek"
    assert cfg.mt.model == ""  # vacío = el del proveedor
    assert cfg.mt.thinking is False
    assert cfg.stt.model == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    assert cfg.tts_ja.engine == "voicevox"


def test_load_from_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent(
            """
            [audio]
            ja_monitor_volume = 0.2

            [mt]
            model = "deepseek-v4-pro"
            glossary = ["API", "onboarding"]
            """
        ),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.audio.ja_monitor_volume == 0.2
    assert cfg.mt.model == "deepseek-v4-pro"
    assert cfg.mt.glossary == ["API", "onboarding"]


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secreto-de-prueba")
    cfg = load_config(None)
    assert cfg.mt_api_key == "secreto-de-prueba"


def test_load_env_file(tmp_path, monkeypatch):
    from interprete.config import load_env_file

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = tmp_path / "env"
    p.write_text("DEEPSEEK_API_KEY=desde-fichero\n# comentario\n", encoding="utf-8")
    load_env_file(p)
    assert load_config(None).mt_api_key == "desde-fichero"
