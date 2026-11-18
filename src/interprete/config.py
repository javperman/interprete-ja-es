"""Carga de configuración (config.toml) y claves desde el entorno.

Las **claves nunca** van en el fichero de configuración: se leen de variables
de entorno (p. ej. ``DEEPSEEK_API_KEY``).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Variable de entorno de la clave según proveedor de MT.
_KEY_ENV = {"deepseek": "DEEPSEEK_API_KEY", "gemini": "GEMINI_API_KEY"}


def load_env_file(path: str | Path | None = None) -> Path | None:
    """Carga claves desde un fichero ``KEY=valor`` (por defecto
    ``~/.config/interprete/env``), sin sobrescribir lo ya definido en el entorno.

    El fichero debe ser privado (``chmod 600``) y no se versiona nunca.
    """
    import os

    p = Path(path or os.environ.get("INTERPRETE_ENV", Path.home() / ".config/interprete/env"))
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    return p


@dataclass(slots=True)
class AudioConfig:
    sink_in: str = "meet_in"
    sink_out: str = "meet_out"
    source_mic: str = "meet_mic"
    mic: str = ""  # micrófono físico; vacío = fuente por defecto del sistema
    headphones: str = ""  # vacío = sink por defecto
    ja_monitor_volume: float = 0.50  # japonés original en tus auriculares (fondo)
    es_monitor_volume: float = 0.50  # tu voz original hacia Meet (de fondo)
    duck_factor: float = 0.40  # cuánto se atenúa el fondo mientras suena la traducción
    capture_rate: int = 48000
    stt_rate: int = 16000


@dataclass(slots=True)
class VadConfig:
    engine: str = "silero_onnx"
    threshold: float = 0.5
    min_silence_ms: int = 500
    speech_pad_ms: int = 200
    pre_roll_ms: int = 300
    max_speech_s: float = 20.0


@dataclass(slots=True)
class SttConfig:
    backend: str = "faster_whisper"
    model: str = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    device: str = "auto"  # auto (CUDA y, si no cabe, CPU) | cuda | cpu
    compute_type: str = "int8_float16"
    beam_size: int = 1
    cuda_lib_path: str = "~/.local/share/hermes-cuda"
    auto_language: bool = False  # detectar el idioma en vez de fijarlo por canal
    # Umbrales de confianza de Whisper: por encima/debajo se considera que no hay
    # voz real (evita las frases inventadas con ruido o silencio).
    no_speech_threshold: float = 0.6
    log_prob_threshold: float = -1.0
    compression_ratio_threshold: float = 2.4


@dataclass(slots=True)
class FilterConfig:
    """Qué se descarta antes de traducir (ruido, alucinaciones y eco)."""

    hallucination_filter: bool = True  # frases que el STT inventa con ruido
    echo_guard: bool = True  # lo que suena en los auriculares y vuelve por el micro
    min_speech_ms: int = 350  # no transcribir sonidos más cortos que esto
    echo_window_s: float = 15.0  # cuánto se recuerda lo locutado para el eco
    blocklist: list[str] = field(default_factory=list)  # frases extra a ignorar


@dataclass(slots=True)
class MtConfig:
    provider: str = "deepseek"  # deepseek | gemini | vertex
    model: str = ""  # vacío = el del proveedor
    base_url: str = ""  # vacío = el del proveedor
    thinking: bool = False
    temperature: float = 0.2
    context_sentences: int = 4
    glossary: list[str] = field(default_factory=list)
    api_key_env: str = ""  # vacío = el del proveedor
    # Vertex AI (Google Cloud)
    project: str = ""
    location: str = "global"
    service_account: str = "~/.config/interprete/gcp-sa.json"
    thinking_level: str = "minimal"  # Vertex: "minimal" (rápido) | "low" | "high"; "" = omitir


@dataclass(slots=True)
class TtsEngineConfig:
    engine: str = "piper"
    voice: str = "es_ES-davefx-medium"
    url: str = "http://127.0.0.1:50021"
    speaker: int = 3
    voices_dir: str = "~/.local/share/interprete/piper"  # Piper
    length_scale: float = 1.0  # Piper: <1 más rápido, >1 más lento
    speed_scale: float = 1.0  # VOICEVOX: <1 más lento
    intonation_scale: float = 0.85  # VOICEVOX: <1 más plano (menos melódico)
    pitch_scale: float = 0.0  # VOICEVOX: tono en semitonos (-0.1 más grave)


@dataclass(slots=True)
class UiConfig:
    mode: str = "auto"  # auto | tui | subtitles | plain
    show_original: bool = True


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    latency_log: str = "logs/latency.csv"


@dataclass(slots=True)
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    mt: MtConfig = field(default_factory=MtConfig)
    tts_es: TtsEngineConfig = field(default_factory=TtsEngineConfig)
    tts_ja: TtsEngineConfig = field(
        default_factory=lambda: TtsEngineConfig(
            engine="voicevox",
            voice="",
            # 玄野武宏: tono medio (130 Hz), ritmo normal y voz clara. Ojo con las
            # voces graves, lentas y con aire (p. ej. 離途 シリアス, 93 Hz): se
            # midió que la segunda prueba real sonaba «íntima» (periodicidad 0,57).
            speaker=11,
            intonation_scale=0.85,
        )
    )
    ui: UiConfig = field(default_factory=UiConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @property
    def mt_api_key(self) -> str | None:
        """Clave del proveedor de MT desde el entorno (nunca del fichero)."""
        env = self.mt.api_key_env or _KEY_ENV.get(self.mt.provider, "")
        return os.environ.get(env) if env else None


def _section(data: dict, cls):
    known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
    return cls(**{k: v for k, v in (data or {}).items() if k in known})


def load_config(path: str | Path | None = None) -> Config:
    """Carga ``config.toml`` si existe; si no, devuelve los valores por defecto."""
    cfg = Config()
    if path and Path(path).exists():
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        tts = raw.get("tts", {})
        cfg = Config(
            audio=_section(raw.get("audio", {}), AudioConfig),
            vad=_section(raw.get("vad", {}), VadConfig),
            stt=_section(raw.get("stt", {}), SttConfig),
            filters=_section(raw.get("filters", {}), FilterConfig),
            mt=_section(raw.get("mt", {}), MtConfig),
            tts_es=_section(tts.get("es", {}), TtsEngineConfig),
            tts_ja=_section(tts.get("ja", {}), TtsEngineConfig),
            ui=_section(raw.get("ui", {}), UiConfig),
            logging=_section(raw.get("logging", {}), LoggingConfig),
        )
    return cfg


# --------------------------------------------------------------------------
# Escritura (la usa la app para guardar los ajustes)
_HEADER = """# config.toml — generado por la app del intérprete JA ⇄ ES.
# Las CLAVES no van aquí: van en variables de entorno o en ~/.config/interprete/env.
# Cópialo/complétalo a mano si lo prefieres; la app solo reescribe este fichero
# cuando pulsas Guardar en la pestaña Ajustes.
"""


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def dumps_config(cfg: Config) -> str:
    """Serializa la configuración a TOML (con valores legibles)."""
    out: list[str] = [_HEADER]
    sections = (
        ("audio", cfg.audio),
        ("vad", cfg.vad),
        ("stt", cfg.stt),
        ("filters", cfg.filters),
        ("mt", cfg.mt),
        ("tts.es", cfg.tts_es),
        ("tts.ja", cfg.tts_ja),
        ("ui", cfg.ui),
        ("logging", cfg.logging),
    )
    for name, obj in sections:
        out.append(f"[{name}]")
        for field_name in obj.__dataclass_fields__:  # type: ignore[attr-defined]
            out.append(f"{field_name} = {_toml_value(getattr(obj, field_name))}")
        out.append("")
    return "\n".join(out)


def save_config(cfg: Config, path: str | Path = "config.toml") -> Path:
    """Guarda ``cfg`` en ``path`` sin tocar los secretos (nunca van aquí)."""
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps_config(cfg), encoding="utf-8")
    return target
