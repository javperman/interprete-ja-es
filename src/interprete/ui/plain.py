"""UI de texto corrido (la de las fases 1–3, ahora unificada).

Se usa cuando la salida no es una terminal interactiva (``| tee log``, cron,
systemd) o cuando se pide ``--ui plain``. Mantiene el formato de siempre.
"""

from __future__ import annotations

import sys

from .base import Ui
from .state import AppState

_TITLES = {
    "listen": "canal de escucha JA → ES (tú oyes español)",
    "speak": "canal de habla ES → JA (los demás oyen japonés)",
    "run": "intérprete completo JA ⇄ ES",
}

_PREFIX = {"info": "·", "ok": "✓", "warn": "!", "error": "✗"}


class PlainUi(Ui):
    def __init__(self, state: AppState, *, stream=None) -> None:
        super().__init__(state)
        self.stream = stream or sys.stdout

    # ------------------------------------------------------------------
    def _p(self, text: str = "") -> None:
        print(text, file=self.stream, flush=True)

    async def start(self) -> None:
        st = self.state
        self._p("=" * 68)
        self._p(f" Intérprete — {_TITLES.get(st.mode, st.mode)}")
        self._p(f" Traducción: {st.provider} ({st.model or 'modelo por defecto'})")
        if st.privacy:
            self._p(f" {st.privacy}")
        self._p("=" * 68)
        for key, label in (("listen_origin", "Escucha"), ("speak_origin", "Habla")):
            if st.info.get(key):
                self._p(f" {label}: {st.info[key]}")
        for line in st.info.get("detail", []):
            self._p(f"   {line}")

    # ------------------------------------------------------------------
    def _on_turn(self, key: str, res) -> None:
        channel = self.state.channel(key)
        index = channel.turns if channel else 0
        tag = "JA→ES " if key == "listen" else "ES→JA "
        self._p()
        self._p(f"[{index:02d}] {tag}{res.source_lang.upper()}: {res.source_text}")
        self._p(f"     {tag}{res.target_lang.upper()}: {res.target_text}")
        stt = res.timing.spans.get("stt_ms", 0)
        self._p(
            f"     audio {res.speech_s:.2f}s"
            f" | STT {stt:.0f} ms"
            f" | MT 1er token {res.mt_ttft_ms or 0:.0f} ms"
            f" | 1er token (fin de frase) {res.first_token_ms or 0:.0f} ms"
            f" | total {res.total_ms or 0:.0f} ms"
        )

    def _on_notice(self, level: str, text: str) -> None:
        self._p(f"{_PREFIX.get(level, '·')} {text}")
