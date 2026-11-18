"""Voces disponibles y preescucha (VOICEVOX y Piper).

- VOICEVOX: ``GET /speakers`` devuelve los 128 estilos; se listan por nombre.
- Piper: se listan las voces descargadas en ``~/.local/share/interprete/piper``.
- La preescucha sintetiza y reproduce por ``pw-cat`` en un hilo aparte.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import numpy as np

from ..audio import default_sink
from ..audio.player import playback_command
from ..tts.base import AudioOut

PREVIEW_JA = "こんにちは。本日の打ち合わせを始めます。よろしくお願いします。"
PREVIEW_ES = "Hola, encantado de conocerte. Empecemos la reunión."

# Voces de VOICEVOX recomendadas para una reunión, medidas en el la máquina de pruebas.
#
# Criterios (una voz de trabajo NO es grave-lenta-con-aire, que suena íntima):
#   F0      120-210 Hz (tono medio; 93 Hz suena demasiado grave/personal)
#   period  > 0,60 (voz clara; menos es voz susurrante o con mucho aire)
#   ms/car  < 150 (ritmo normal; 156 suena lento y sensual)
#   rango   < 9 semitonos (melodía sobria, no teatral)
#
# Hay una prueba (tests/test_voicevox.py) que comprueba estos criterios sobre la
# lista: si una voz nueva no los cumple, el test falla y no llega a la interfaz.
# (id, F0 Hz, period, ms/car, rango) con una frase de reunión
RECOMENDADAS_JA = (
    11,   # 玄野武宏     130 Hz · 0,62 · 128 ms · 8,4 st  (masculina neutra, la más ágil)
    30,   # No.7 アナウンス 198 Hz · 0,74 · 138 ms · 7,0 st  (estilo «anuncio», muy neutra)
    94,   # 中部つるぎ    200 Hz · 0,76 · 143 ms · 8,0 st  (la más clara; tono alto)
    100,  # 黒沢冴白     150 Hz · 0,65 · 161 ms · 7,6 st  (masculina clara, algo lenta)
)

# Voces a evitar en una reunión: medidas y confirmadas como «íntimas» (graves,
# lentas y con aire) o demasiado teatrales.
EVITAR_JA = (
    101,  # 離途 シリアス  93 Hz · 0,57 (la más susurrante) · 156 ms/car
    53,   # 麒ヶ島宗麟    137 Hz · 0,63 · 136 ms · 12,0 st (melodía teatral)
    21,   # 剣崎雌雄     127 Hz · 0,64 · 146 ms · 11,2 st (melodía teatral)
)


def abrevia(nombre: str, maximo: int = 18) -> str:
    """Acorta el nombre para que el desplegable no ensanche la ventana."""
    return nombre if len(nombre) <= maximo else nombre[: maximo - 1] + "…"


def order_styles(styles: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Deja las voces recomendadas primero (marcadas con ★) y acorta los nombres.

    El valor guardado sigue siendo el id del estilo, así que acortar el nombre no
    afecta a la configuración.
    """
    primeras = [(i, f"★ {abrevia(n)}") for i, n in styles if i in RECOMENDADAS_JA]
    resto = [(i, abrevia(n)) for i, n in styles if i not in RECOMENDADAS_JA]
    return primeras + resto


# ------------------------------------------------------------------ catálogos
def list_voicevox_styles(url: str, timeout: float = 5.0) -> list[tuple[int, str]]:
    """[(id_estilo, "Personaje (estilo)")] ordenado por id."""
    import httpx

    try:
        data = httpx.get(f"{url}/speakers", timeout=timeout).json()
    except Exception:  # noqa: BLE001 - el servicio puede estar parado
        return []
    styles: list[tuple[int, str]] = []
    for speaker in data:
        name = speaker.get("name") or "?"
        for style in speaker.get("styles") or []:
            style_id = style.get("id")
            if style_id is None:
                continue
            styles.append((int(style_id), f"{name} ({style.get('name') or '?'})"))
    return sorted(styles)


def list_piper_voices(voices_dir: str) -> list[str]:
    root = Path(voices_dir).expanduser()
    if not root.is_dir():
        return []
    voices = [p.name for p in sorted(root.iterdir()) if (p / f"{p.name}.onnx").exists()]
    return voices


# ------------------------------------------------------------------ síntesis
def synthesize_voicevox(
    url: str,
    style_id: int,
    text: str = PREVIEW_JA,
    *,
    speed_scale: float = 1.0,
    intonation_scale: float = 0.80,
    pitch_scale: float = 0.0,
) -> AudioOut:
    from ..tts import VoicevoxTts

    tts = VoicevoxTts(
        url=url,
        speaker=style_id,
        speed_scale=speed_scale,
        intonation_scale=intonation_scale,
        pitch_scale=pitch_scale,
    )
    try:
        return tts.synthesize(text, "ja")
    finally:
        tts.close()


def synthesize_piper(
    voice: str, voices_dir: str, text: str = PREVIEW_ES, length_scale: float = 1.0
) -> AudioOut:
    from ..tts import PiperTts

    return PiperTts(voice=voice, voices_dir=voices_dir, length_scale=length_scale).synthesize(
        text, "es"
    )


# ------------------------------------------------------------------ preescucha
def play_audio(audio: np.ndarray, rate: int, target: str = "") -> None:
    """Reproduce PCM float32 mono en ``target`` (o el sink por defecto)."""
    data = np.asarray(audio, dtype=np.float32)
    if data.size == 0:
        return
    node = target or default_sink()
    proc = subprocess.Popen(
        playback_command(node, rate),
        stdin=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None
    try:
        proc.stdin.write(data.tobytes())
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        return
    proc.wait()


def play_in_background(audio: np.ndarray, rate: int, target: str = "") -> threading.Thread:
    thread = threading.Thread(target=play_audio, args=(audio, rate, target), daemon=True)
    thread.start()
    return thread
