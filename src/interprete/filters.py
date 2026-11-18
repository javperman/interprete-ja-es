"""Filtros de texto: quitan lo que el intérprete no debería traducir.

Dos problemas reales de la prueba con la novia del usuario:

1. **Alucinaciones**: cuando el STT recibe ruido, silencio, música o un sonido
   cualquiera, Whisper *inventa* frases que nadie ha dicho (en japonés son
   famosas 「お待ちしております」 o 「ご視聴ありがとうございました」). Se detectan
   con las métricas del propio modelo (``no_speech_prob``, ``avg_logprob``,
   ``compression_ratio``) y con una lista negra de frases conocidas.

2. **Eco**: la voz sintetizada que suena en los auriculares se escapa, la recoge
   el micrófono y el intérprete la vuelve a traducir (se traduce a sí mismo). El
   ``EchoGuard`` recuerda lo que el intérprete acaba de decir y descarta lo que
   suene demasiado parecido.

Todo es **puro** (sin audio ni red): se prueba con texto.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# --------------------------------------------------------------------------
# Normalización
_PUNTUACION = re.compile(r"[\s\u3000!¡?¿.,;:…、。！？「」『』（）()\[\]\"'’“”\-—–~〜]+")
_SIMBOLOS = re.compile(r"[♪♫♬♩*#☆★■□●○=]+")


def normalize(text: str) -> str:
    """Deja solo letras y números, en minúsculas y sin espacios.

    Sirve para comparar frases sin que estorben los signos ni el espaciado.
    """
    limpio = _SIMBOLOS.sub("", text or "")
    limpio = _PUNTUACION.sub("", limpio)
    return limpio.casefold()


# --------------------------------------------------------------------------
# Alucinaciones conocidas (frases que Whisper inventa con ruido/silencio)
HALLUCINATIONS: tuple[str, ...] = (
    # Japonés (las más frecuentes cuando no hay voz o hay ruido)
    "お待ちしております",
    "お待ちしています",
    "ご視聴ありがとうございました",
    "ご視聴ありがとうございます",
    "ご清聴ありがとうございました",
    "チャンネル登録よろしくお願いします",
    "チャンネル登録お願いします",
    "お気に入りしておく",
    "字幕by",
    "字幕",
    "ごゆっくりどうぞ",
    # Español
    "subtítulosrealizadosporlacomunidaddeamaraorg",
    "subtítulosespañol",
    "graciasporverelvideo",
    "graciasporverestevideo",
    "nolvidessuscribirte",
    "suscríbetealcana",
    # Inglés
    "thankyouforwatching",
    "thanksforwatching",
    "thankyouforwatchingthisvideo",
    "pleasesubscribe",
    "subtitlesbytheamaraorgcommunity",
    "theend",
)
# Coincidencia: se descarta si el texto normalizado **es** una de esas frases o si
# la contiene casi por completo (una alucinación puede salir pegada a más ruido).
_COINCIDENCIA = 0.85


def is_hallucination(text: str, extra: tuple[str, ...] | list[str] = ()) -> bool:
    """¿El texto es una frase que Whisper suele inventar?"""
    limpio = normalize(text)
    if not limpio:
        return True
    for patron in HALLUCINATIONS + tuple(extra or ()):
        objetivo = normalize(patron)
        if not objetivo:
            continue
        if limpio == objetivo:
            return True
        if len(objetivo) >= 6 and objetivo in limpio:
            return True
        if len(limpio) >= 6 and limpio in objetivo:
            return True
    return False


# --------------------------------------------------------------------------
@dataclass(slots=True)
class EchoGuard:
    """Recuerda lo que el intérprete acaba de decir para no volver a traducirlo.

    Los auriculares dejan escapar la voz sintetizada hacia el micrófono. Sin este
    filtro, el canal de habla transcribe **su propia traducción** y la manda otra
    vez a la reunión.
    """

    window_s: float = 15.0
    min_chars: int = 8  # los avisos cortos («Sí», «はい») no se filtran
    similarity: float = 0.85
    contencion: float = 0.70
    _dicho: deque = field(default_factory=deque, repr=False)

    def record(self, text: str, *, when: float | None = None) -> None:
        """Anota una frase que se acaba de locutar."""
        limpio = normalize(text)
        if len(limpio) < self.min_chars:
            return
        self._dicho.append(((when if when is not None else time.monotonic()), limpio))
        self._poda()

    def is_echo(self, text: str, *, when: float | None = None) -> bool:
        """¿Lo que se acaba de transcribir es algo que ya dijo el intérprete?"""
        limpio = normalize(text)
        if len(limpio) < self.min_chars:
            return False
        ahora = when if when is not None else time.monotonic()
        for t, dicho in list(self._dicho):
            if ahora - t > self.window_s:
                continue
            if limpio == dicho:
                return True
            largo = max(len(limpio), len(dicho))
            if largo and abs(len(limpio) - len(dicho)) / largo < 0.5:
                if SequenceMatcher(None, limpio, dicho).ratio() >= self.similarity:
                    return True
            corto, largo_txt = sorted((limpio, dicho), key=len)
            if len(corto) >= self.min_chars and corto in largo_txt:
                if len(corto) / len(largo_txt) >= self.contencion:
                    return True
        return False

    def _poda(self) -> None:
        while len(self._dicho) > 64:
            self._dicho.popleft()


@dataclass(slots=True)
class TurnFilters:
    """Ajustes de filtrado de un turno, compartidos por los dos canales."""

    hallucination_filter: bool = True
    blocklist: tuple[str, ...] = ()
    min_speech_ms: int = 350
    echo_guard: EchoGuard | None = None

    def is_too_short(self, duration_s: float) -> bool:
        return self.min_speech_ms > 0 and duration_s * 1000.0 < self.min_speech_ms

    def is_blocked_text(self, text: str) -> bool:
        return self.hallucination_filter and is_hallucination(text, self.blocklist)

    def is_echo(self, text: str) -> bool:
        return self.echo_guard is not None and self.echo_guard.is_echo(text)

    def remember_spoken(self, text: str, *, when: float | None = None) -> None:
        """Anota lo que acaba de locutar el intérprete (para detectar el eco)."""
        if self.echo_guard is not None:
            self.echo_guard.record(text, when=when)
