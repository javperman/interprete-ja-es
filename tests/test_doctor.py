"""Pruebas del doctor (comprobación previa a la reunión)."""

from __future__ import annotations

from interprete import doctor
from interprete.config import Config


def test_worst_status_prefers_error():
    checks = [doctor.Check("a", "ok"), doctor.Check("b", "warn"), doctor.Check("c", "error")]
    assert doctor.worst_status(checks) == "error"


def test_worst_status_all_ok():
    assert doctor.worst_status([doctor.Check("a", "ok"), doctor.Check("b", "skip")]) == "ok"


def test_format_checks_no_color_has_no_ansi():
    out = doctor.format_checks([doctor.Check("nodos", "ok", "todo bien")], color=False)
    assert "\x1b" not in out
    assert "nodos" in out and "todo bien" in out


def test_vertex_missing_key(tmp_path):
    cfg = Config()
    cfg.mt.provider = "vertex"
    cfg.mt.service_account = str(tmp_path / "nope.json")
    assert doctor._check_mt_credentials(cfg).status == "error"


def test_vertex_key_ok(tmp_path):
    key = tmp_path / "sa.json"
    key.write_text("{}", encoding="utf-8")
    key.chmod(0o600)
    cfg = Config()
    cfg.mt.provider = "vertex"
    cfg.mt.service_account = str(key)
    assert doctor._check_mt_credentials(cfg).status == "ok"


def test_vertex_key_wrong_permissions_warns(tmp_path):
    key = tmp_path / "sa.json"
    key.write_text("{}", encoding="utf-8")
    key.chmod(0o644)
    cfg = Config()
    cfg.mt.provider = "vertex"
    cfg.mt.service_account = str(key)
    assert doctor._check_mt_credentials(cfg).status == "warn"


def test_gemini_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = Config()
    cfg.mt.provider = "gemini"
    assert doctor._check_mt_credentials(cfg).status == "error"


def test_check_commands_detects_missing(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    check = doctor._check_commands(Config())
    assert check.status == "error"
    assert "pw-cat" in check.detail


def test_default_sink_is_meet_in_is_error(monkeypatch):
    import interprete.audio as audio_pkg

    monkeypatch.setattr(audio_pkg, "default_sink", lambda: "meet_in")
    cfg = Config()
    cfg.audio.sink_in = "meet_in"
    assert doctor._check_default_sink(cfg).status == "error"


def _patch_all(monkeypatch):
    monkeypatch.setattr(doctor, "_check_commands", lambda cfg: doctor.Check("commands", "ok"))
    monkeypatch.setattr(doctor, "_check_nodes", lambda cfg: doctor.Check("nodes", "ok"))
    monkeypatch.setattr(doctor, "_check_default_sink", lambda cfg: doctor.Check("sink", "ok"))
    monkeypatch.setattr(doctor, "_check_mic", lambda cfg: doctor.Check("mic", "ok"))
    monkeypatch.setattr(doctor, "_check_voicevox", lambda cfg: doctor.Check("voicevox", "ok"))
    monkeypatch.setattr(doctor, "_check_piper", lambda cfg: doctor.Check("piper", "ok"))
    monkeypatch.setattr(doctor, "_check_stt", lambda cfg: doctor.Check("stt", "ok"))
    monkeypatch.setattr(doctor, "_check_mt_credentials", lambda cfg: doctor.Check("mt", "ok"))
    monkeypatch.setattr(doctor, "_check_mt_live", lambda cfg: doctor.Check("live", "ok"))
    monkeypatch.setattr(doctor, "_check_routing", lambda cfg: doctor.Check("routing", "ok"))
    monkeypatch.setattr(doctor, "_check_gtk", lambda cfg: doctor.Check("gtk", "ok"))
    monkeypatch.setattr(doctor, "_check_memory", lambda cfg: doctor.Check("mem", "ok"))


def test_run_checks_full(monkeypatch):
    _patch_all(monkeypatch)
    checks = doctor.run_checks(Config(), listen=True, speak=True, live=True)
    assert len(checks) == 12  # traducción real, enrutado y GTK
    assert [c.name for c in checks][-1] == "mem"


def test_run_checks_without_live(monkeypatch):
    _patch_all(monkeypatch)
    checks = doctor.run_checks(Config(), listen=True, speak=True)
    names = [c.name for c in checks]
    assert "live" not in names
    assert "routing" in names
    assert len(checks) == 11


def test_run_checks_listen_only(monkeypatch):
    _patch_all(monkeypatch)
    checks = doctor.run_checks(Config(), listen=True, speak=False)
    names = [c.name for c in checks]
    assert "piper" in names and "voicevox" not in names and "mic" not in names


def test_apply_fixes_skips_ok(monkeypatch):
    ran: list = []
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: ran.append(a))
    applied = doctor.apply_fixes([doctor.Check("a", "ok"), doctor.Check("b", "warn", "", fix=None)])
    assert applied == []
    assert ran == []


def test_apply_fixes_runs_nodes_setup(monkeypatch, tmp_path):
    script = tmp_path / "scripts" / "interprete-audio"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "REPO_DIR", tmp_path)
    ran: list = []
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: ran.append(a))
    applied = doctor.apply_fixes([doctor.Check("nodos", "error", "", fix="nodes")])
    assert applied == ["scripts/interprete-audio setup"]
    assert ran and ran[0][0][0] == "bash"


def test_apply_fixes_voicevox(monkeypatch):
    ran: list = []
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: ran.append(a))
    applied = doctor.apply_fixes([doctor.Check("voicevox", "error", "", fix="voicevox")])
    assert applied == ["systemctl --user start interprete-voicevox.service"]
    assert ran[0][0][:3] == ["systemctl", "--user", "start"]
