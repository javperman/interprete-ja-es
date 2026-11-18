"""Motor del intérprete: recursos, canales y ciclo de vida de una sesión.

Extraído del CLI para que lo compartan la **línea de comandos** y la **app GTK**.
Una ``Session`` carga STT/MT/TTS, monta los canales de escucha (JA→ES) y habla
(ES→JA) y los ejecuta hasta que se pide parar. La interfaz solo observa
``AppState`` y envía acciones a través de ``Runtime``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .filters import EchoGuard, TurnFilters
from .latency import LatencyLog
from .mt import build_translator
from .mt.factory import model_name
from .ui.state import AppState, ChannelState

log = logging.getLogger("interprete.session")

MODES = ("listen", "speak", "run")


# --------------------------------------------------------------------------
@dataclass(slots=True)
class SessionOptions:
    """Cómo arrancar una sesión (equivalente a los flags del CLI)."""

    mode: str = "run"
    sink_in: str = ""
    meet_out: str = ""
    mic: str = ""
    headphones: str = ""
    ja_volume: float | None = None
    es_volume: float | None = None
    duck_factor: float | None = None  # cuánto se atenúa el fondo al traducir
    ja_forward: bool = True  # japonés original → auriculares
    es_forward: bool = False  # español original → meet_out (de fondo)
    speak_es: bool = True  # voz en español (canal de escucha)
    speak_ja: bool = True  # voz en japonés (canal de habla)
    auto_language: bool = False  # STT detecta el idioma en vez de fijarlo
    input_wav: str | None = None  # replay de un WAV (sin PipeWire)
    inject_wav: str | None = None  # WAV inyectado en el sink antes de escuchar
    fast: bool = False
    seconds: float | None = None
    latency_log: str = ""


@dataclass(slots=True)
class Resolved:
    """Opciones ya resueltas contra la configuración y los dispositivos."""

    sink_in: str = ""
    meet_out: str = ""
    mic: str = ""
    headphones: str = ""
    ja_volume: float = 0.50
    es_volume: float = 0.50
    duck_factor: float = 0.40
    listen_origin: str = ""
    speak_origin: str = ""


# --------------------------------------------------------------------------
def resolve(cfg: Config, options: SessionOptions) -> tuple[Resolved, list[str]]:
    """Valida y completa las opciones. Devuelve (resueltas, errores)."""
    from .audio import (
        default_sink,
        default_source,
        list_sink_names,
        list_source_names,
    )

    errors: list[str] = []
    res = Resolved()
    want_listen = options.mode in ("listen", "run")
    want_speak = options.mode in ("speak", "run")
    replay = options.input_wav

    res.sink_in = options.sink_in or cfg.audio.sink_in
    res.meet_out = options.meet_out or cfg.audio.sink_out
    res.ja_volume = cfg.audio.ja_monitor_volume if options.ja_volume is None else options.ja_volume
    res.es_volume = cfg.audio.es_monitor_volume if options.es_volume is None else options.es_volume
    res.duck_factor = cfg.audio.duck_factor if options.duck_factor is None else options.duck_factor

    if want_listen:
        if replay:
            if not Path(replay).exists():
                errors.append(f"no existe el fichero {replay}")
            res.listen_origin = f"WAV {replay} (replay{' rápido' if options.fast else ''})"
        else:
            if res.sink_in not in list_sink_names():
                errors.append(
                    f"el sink {res.sink_in!r} no existe. Ejecuta 'scripts/interprete-audio setup'."
                )
            res.listen_origin = f"monitor de {res.sink_in}"
            if options.inject_wav:
                if not Path(options.inject_wav).exists():
                    errors.append(f"no existe el fichero {options.inject_wav}")
                res.listen_origin += f" + inyección de {options.inject_wav}"

    if want_speak:
        res.mic = options.mic or cfg.audio.mic or ""
        if replay:
            res.speak_origin = f"WAV {replay} (replay{' rápido' if options.fast else ''})"
        else:
            if not res.mic:
                try:
                    res.mic = default_source()
                except Exception:  # noqa: BLE001
                    res.mic = ""
            if not res.mic or res.mic not in list_source_names():
                errors.append(f"no encuentro el micrófono {res.mic!r}.")
            elif res.mic == cfg.audio.source_mic:
                errors.append(
                    f"el micrófono {res.mic!r} es el micro virtual; usa el físico."
                )
            res.speak_origin = f"micrófono {res.mic}"

    res.headphones = options.headphones or cfg.audio.headphones
    if want_listen and not res.headphones:
        try:
            res.headphones = default_sink()
        except Exception:  # noqa: BLE001
            res.headphones = ""
    return res, errors


def privacy_note(cfg: Config) -> str:
    if cfg.mt.provider in ("vertex", "gemini"):
        return "el TEXTO de la conversación sale a Google"
    if cfg.mt.provider == "deepseek":
        return "el TEXTO de la conversación sale a DeepSeek"
    return "el TEXTO de la conversación sale a un proveedor en la nube"


def make_state(cfg: Config, options: SessionOptions, res: Resolved) -> AppState:
    """Estado inicial para la UI (lo usan CLI y GUI)."""
    want_listen = options.mode in ("listen", "run")
    want_speak = options.mode in ("speak", "run")
    speak_es = want_listen and options.speak_es
    ja_forward = want_listen and options.ja_forward and not (options.input_wav and options.fast)
    es_forward = want_speak and options.es_forward

    detail = []
    if ja_forward:
        detail.append(
            f"japonés de fondo → {res.headphones} (vol {res.ja_volume:.2f},"
            f" se atenúa al {cfg.audio.duck_factor:.2f} al traducir)"
        )
    if want_listen:
        detail.append(
            f"voz en español → {res.headphones}: {cfg.tts_es.engine} ({cfg.tts_es.voice})"
            if speak_es
            else "voz en español: DESACTIVADA (solo texto)"
        )
    if want_speak:
        detail.append(
            f"voz en japonés → {res.meet_out}: {cfg.tts_ja.engine} (estilo {cfg.tts_ja.speaker})"
        )
        if es_forward:
            detail.append(f"español de fondo → {res.meet_out} (vol {res.es_volume:.2f})")

    state = AppState(
        mode=options.mode,
        provider=cfg.mt.provider,
        model=cfg.mt.model or model_name(cfg.mt),
        privacy=privacy_note(cfg),
        info={
            "listen_origin": res.listen_origin,
            "speak_origin": res.speak_origin,
            "detail": detail,
        },
        flags={
            "ja_volume": res.ja_volume,
            "ja_forward": ja_forward,
            "es_volume": res.es_volume,
            "es_forward": es_forward,
            "duck_factor": res.duck_factor,
            "speak_es": speak_es,
            "speak_ja": want_speak and options.speak_ja,
            "auto_language": options.auto_language,
            "paused": False,
            "show_original": cfg.ui.show_original,
        },
    )
    if want_listen:
        state.channels.append(
            ChannelState(
                key="listen",
                name="JA → ES   (tú oyes español)",
                source_lang="ja",
                target_lang="es",
                tts_label=cfg.tts_es.voice,
                tts_on=speak_es,
            )
        )
    if want_speak:
        state.channels.append(
            ChannelState(
                key="speak",
                name="ES → JA   (ellos oyen japonés)",
                source_lang="es",
                target_lang="ja",
                tts_label=f"estilo {cfg.tts_ja.speaker}",
                tts_on=want_speak and options.speak_ja,
            )
        )
    return state


# --------------------------------------------------------------------------
class Runtime:
    """Ajustes en caliente compartidos con las interfaces (teclas, botones)."""

    def __init__(self) -> None:
        self.stop: asyncio.Event | None = None
        self.forwarder = None  # japonés de fondo
        self.forwarder_es = None  # español de fondo
        self.speakers: dict[str, object] = {}
        self.channels: dict[str, object] = {}
        self.state = None
        self.extras: dict[str, object] = {}

    # ------------------------------------------------------------------ sync
    def sync(self) -> None:
        """Copia a la UI el estado real de locutores, reenvíos y pipeline."""
        st = self.state
        if st is None:
            return
        if self.forwarder is not None:
            st.flags["ja_volume"] = round(self.forwarder.volume, 2)
            st.flags["ja_forward"] = self.forwarder.enabled
        if self.forwarder_es is not None:
            st.flags["es_volume"] = round(self.forwarder_es.volume, 2)
            st.flags["es_forward"] = self.forwarder_es.enabled
        for fwd in (self.forwarder, self.forwarder_es):
            if fwd is not None:
                st.flags["duck_factor"] = round(fwd.duck_factor, 2)
                break
        for key, speaker in self.speakers.items():
            channel = st.channel(key)
            if channel is None:
                continue
            channel.spoken = int(getattr(speaker, "spoken", 0))
            channel.skipped = int(getattr(speaker, "skipped", 0))
            channel.muted = int(getattr(speaker, "muted", 0))
            channel.tts_on = bool(getattr(speaker, "enabled", True))
        for key, pipeline_channel in self.channels.items():
            channel = st.channel(key)
            if channel is None:
                continue
            stats = pipeline_channel.stats
            speaker = self.speakers.get(key)
            channel.dropped = int(getattr(stats, "dropped", 0))
            channel.empty = int(getattr(stats, "empty", 0))
            channel.filtered = int(getattr(stats, "filtered", 0))
            channel.echos = int(getattr(stats, "echos", 0))
            channel.errors = int(getattr(stats, "errors", 0)) + int(
                getattr(speaker, "errors", 0)
            )

    # ------------------------------------------------------------------ apply
    def apply(self, action: str) -> str | None:
        result = self._apply(action)
        self.sync()
        return result

    def _apply(self, action: str) -> str | None:
        if action == "quit":
            if self.stop is not None:
                self.stop.set()
            return None
        if action == "toggle_tts_listen":
            return self._toggle_speaker("listen", "voz en español")
        if action == "toggle_tts_speak":
            return self._toggle_speaker("speak", "voz en japonés")
        if action == "toggle_ja":
            return self._toggle_forwarder("forwarder", "japonés de fondo")
        if action == "toggle_es":
            return self._toggle_forwarder("forwarder_es", "español de fondo")
        if action in ("ja_volume_up", "ja_volume_down"):
            return self._bump_volume("forwarder", 1 if action.endswith("up") else -1)
        if action in ("es_volume_up", "es_volume_down"):
            return self._bump_volume("forwarder_es", 1 if action.endswith("up") else -1)
        if action.startswith("set_volume:"):
            return self._set_volume(action)
        if action.startswith("set_duck:"):
            return self._set_duck(action)
        if action.startswith("set_switch:"):
            return self._set_switch(action)
        if action == "toggle_pause":
            return self._toggle_pause()
        return f"acción desconocida: {action}"

    def _toggle_speaker(self, key: str, label: str) -> str:
        speaker = self.speakers.get(key)
        if speaker is None:
            return f"{label} no disponible en este modo"
        speaker.set_enabled(not speaker.enabled)
        return f"{label} {'activada' if speaker.enabled else 'silenciada'}"

    def _toggle_forwarder(self, attr: str, label: str) -> str:
        fwd = getattr(self, attr, None)
        if fwd is None:
            return f"{label} no está activo"
        fwd.set_enabled(not fwd.enabled)
        return f"{label} {'activado' if fwd.enabled else 'desactivado'}"

    def _bump_volume(self, attr: str, sign: int) -> str:
        fwd = getattr(self, attr, None)
        if fwd is None:
            return "ese reenvío no está activo"
        fwd.set_volume(fwd.volume + 0.05 * sign)
        return f"volumen: {fwd.volume:.2f}"

    def _set_volume(self, action: str) -> str:
        # set_volume:<attr>:<valor>
        try:
            _, attr, value = action.split(":", 2)
            level = float(value)
        except ValueError:
            return "acción de volumen inválida"
        fwd = getattr(self, attr, None)
        if fwd is None:
            return "ese reenvío no está activo"
        fwd.set_volume(level)
        return f"volumen: {fwd.volume:.2f}"

    def _set_duck(self, action: str) -> str:
        # set_duck:<factor 0-1> — cuánto se atenúa el fondo al traducir
        try:
            _, value = action.split(":", 1)
            factor = float(value)
        except ValueError:
            return "acción de atenuación inválida"
        applied = []
        for fwd in (self.forwarder, self.forwarder_es):
            if fwd is not None:
                fwd.set_duck_factor(factor)
                applied.append(fwd)
        if not applied:
            return "no hay fondos activos"
        return f"el fondo se atenúa al {applied[0].duck_factor:.2f} al traducir"

    def _set_switch(self, action: str) -> str:
        try:
            _, key, value = action.split(":", 2)
            on = value not in ("0", "false", "")
        except ValueError:
            return "acción de interruptor inválida"
        targets = {
            "tts_es": lambda: self._toggle_speaker("listen", "voz en español"),
            "tts_ja": lambda: self._toggle_speaker("speak", "voz en japonés"),
            "ja": lambda: self._toggle_forwarder("forwarder", "japonés de fondo"),
            "es": lambda: self._toggle_forwarder("forwarder_es", "español de fondo"),
        }
        current = {
            "tts_es": self._speaker_enabled("listen"),
            "tts_ja": self._speaker_enabled("speak"),
            "ja": getattr(self.forwarder, "enabled", None),
            "es": getattr(self.forwarder_es, "enabled", None),
        }.get(key)
        if current is None:
            return f"interruptor desconocido: {key}"
        if bool(current) == on:
            return ""
        return targets[key]()

    def _speaker_enabled(self, key: str) -> bool | None:
        speaker = self.speakers.get(key)
        return None if speaker is None else bool(getattr(speaker, "enabled", True))

    def _toggle_pause(self) -> str:
        st = self.state
        if st is None:
            return "sin estado"
        paused = not st.flags.get("paused", False)
        st.flags["paused"] = paused
        if paused:
            st.flags["_saved"] = {k: getattr(s, "enabled", True) for k, s in self.speakers.items()}
            st.flags["_saved_ja"] = getattr(self.forwarder, "enabled", True)
            st.flags["_saved_es"] = getattr(self.forwarder_es, "enabled", True)
            for speaker in self.speakers.values():
                speaker.set_enabled(False)
            for fwd in (self.forwarder, self.forwarder_es):
                if fwd is not None:
                    fwd.set_enabled(False)
            return "PAUSA: voces y fondos silenciados (la captura sigue)"
        saved = st.flags.pop("_saved", {})
        for key, speaker in self.speakers.items():
            speaker.set_enabled(bool(saved.get(key, True)))
        if self.forwarder is not None:
            self.forwarder.set_enabled(bool(st.flags.pop("_saved_ja", True)))
        if self.forwarder_es is not None:
            self.forwarder_es.set_enabled(bool(st.flags.pop("_saved_es", True)))
        return "reanudado"


# Alias histórico (tests y código previo).
_Runtime = Runtime


# --------------------------------------------------------------------------
class Session:
    """Ciclo de vida completo de una sesión del intérprete."""

    def __init__(self, cfg: Config, options: SessionOptions, ui) -> None:
        self.cfg = cfg
        self.options = options
        self.ui = ui
        self.state = ui.state
        self.runtime = Runtime()
        self.runtime.state = self.state
        ui.on_tick = self.runtime.sync

        self.filters = TurnFilters()  # se rellena al abrir la sesión
        self.error: str | None = None
        self.summary: list[str] = []
        self.running = False
        self._stop = asyncio.Event()
        self._channels: list = []
        self._injector = None
        self._watcher: asyncio.Task | None = None
        self._stt = None
        self._translator = None
        self._tts_es = None
        self._tts_ja = None
        self._ja_fwd = None
        self._es_fwd = None
        self._log_listen = ""
        self._latency_logs: list = []

    # ------------------------------------------------------------------ API
    def request_stop(self) -> None:
        """Pide parar (llamar desde el hilo del bucle o con call_soon_threadsafe)."""
        self._stop.set()

    async def serve(self) -> None:
        """Abre, ejecuta hasta que se pide parar y cierra. No lanza excepciones."""
        try:
            if not await self.open():
                return
            await self._run()
        except asyncio.CancelledError:  # pragma: no cover - cancelación externa
            log.info("sesión cancelada")
            raise
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            log.exception("error en la sesión")
            self.ui.notice("error", f"falló la sesión: {self.error}")
        finally:
            try:
                await self.close()
            except Exception:
                log.exception("error al cerrar la sesión")

    # ------------------------------------------------------------------ open
    async def open(self) -> bool:
        from .pipeline import Channel
        from .tts import build_tts

        opts, cfg = self.options, self.cfg
        res, errors = resolve(cfg, opts)
        if errors:
            self.error = "; ".join(errors)
            for msg in errors:
                self.ui.notice("error", msg)
            return False
        self.resolved = res

        want_listen = opts.mode in ("listen", "run")
        want_speak = opts.mode in ("speak", "run")
        self._speak_es = want_listen and opts.speak_es
        self._speak_ja = want_speak and opts.speak_ja
        ja_forward = want_listen and opts.ja_forward and not (opts.input_wav and opts.fast)
        es_forward = want_speak and opts.es_forward

        # ---------------- recursos ----------------
        self.ui.notice("info", "Cargando modelo de voz (puede tardar unos segundos)…")
        self._stt = _build_stt(cfg)
        self._stt.warmup()
        if self._stop.is_set():
            return False
        self._translator = build_translator(cfg.mt)

        if self._speak_es:
            self._tts_es = build_tts(cfg.tts_es)
            if hasattr(self._tts_es, "is_ready") and not self._tts_es.is_ready():
                self.ui.notice(
                    "warn",
                    f"TTS español no instalado ({cfg.tts_es.voice}); solo texto "
                    "(scripts/install-piper.sh).",
                )
                self._tts_es, self._speak_es = None, False

        if self._speak_ja:
            self._tts_ja = build_tts(cfg.tts_ja)
            if hasattr(self._tts_ja, "is_ready") and not self._tts_ja.is_ready():
                self.error = (
                    "VOICEVOX no responde en :50021. Arranca el servicio "
                    "(systemctl --user start interprete-voicevox) o pulsa Comprobar."
                )
                self.ui.notice("error", self.error)
                return False

        if ja_forward:
            self._ja_fwd = await _start_fondo(
                res.headphones, res.ja_volume, res.duck_factor, self.ui, "el japonés de fondo"
            )
            self.runtime.forwarder = self._ja_fwd
        if es_forward:
            self._es_fwd = await _start_fondo(
                res.meet_out, res.es_volume, res.duck_factor, self.ui, "tu voz de fondo"
            )
            self.runtime.forwarder_es = self._es_fwd

        # ---------------- filtros ----------------
        # Un único guardia de eco para los dos canales: lo que locuta uno lo puede
        # estar oyendo el micrófono del otro.
        self.filters = TurnFilters(
            hallucination_filter=cfg.filters.hallucination_filter,
            blocklist=tuple(cfg.filters.blocklist),
            min_speech_ms=cfg.filters.min_speech_ms,
            echo_guard=(
                EchoGuard(window_s=cfg.filters.echo_window_s)
                if cfg.filters.echo_guard
                else None
            ),
        )

        # ---------------- canales ----------------
        self._log_listen = opts.latency_log or cfg.logging.latency_log
        listen_src = "auto" if opts.auto_language else "ja"
        speak_src = "auto" if opts.auto_language else "es"

        if want_listen:

            def on_listen(turn) -> None:
                self.runtime.sync()
                self.ui.turn("listen", turn)

            channel = Channel(
                "escucha",
                stt=self._stt,
                translator=self._translator,
                segmenter=_build_segmenter(cfg),
                source_lang=listen_src,
                target_lang="es",
                context_sentences=cfg.mt.context_sentences,
                glossary=cfg.mt.glossary,
                tts=self._tts_es,
                play_target=res.headphones,
                speaker_lang="es",
                speaker_mode="drop_new",
                forwarder=self._ja_fwd,
                filters=self.filters,
                on_spoken=self.filters.remember_spoken,
                on_result=on_listen,
                latency_log=LatencyLog(self._log_listen),
            )
            self._channels.append(channel)
            if channel.speaker is not None:
                self.runtime.speakers["listen"] = channel.speaker
            self.runtime.channels["listen"] = channel

        if want_speak:

            def on_speak(turn) -> None:
                self.runtime.sync()
                self.ui.turn("speak", turn)

            channel = Channel(
                "habla",
                stt=self._stt,
                translator=self._translator,
                segmenter=_build_segmenter(cfg),
                source_lang=speak_src,
                target_lang="ja",
                context_sentences=cfg.mt.context_sentences,
                glossary=cfg.mt.glossary,
                tts=self._tts_ja,
                play_target=res.meet_out,
                speaker_lang="ja",
                speaker_mode="queue",
                speaker_queue=2,
                forwarder=self._es_fwd,
                filters=self.filters,
                on_spoken=self.filters.remember_spoken,
                on_result=on_speak,
                latency_log=LatencyLog(_sibling_log(self._log_listen, "speak")),
            )
            self._channels.append(channel)
            if channel.speaker is not None:
                self.runtime.speakers["speak"] = channel.speaker
            self.runtime.channels["speak"] = channel

        # ---------------- fuentes de frames ----------------
        for sig in ("SIGINT", "SIGTERM"):
            try:
                import signal

                asyncio.get_running_loop().add_signal_handler(
                    getattr(signal, sig), self.request_stop
                )
            except (NotImplementedError, RuntimeError, ValueError):  # pragma: no cover
                pass

        self._want_listen = want_listen
        self._want_speak = want_speak
        self.runtime.sync()
        return True

    # ------------------------------------------------------------------- run
    async def _run(self) -> None:
        res, opts = self.resolved, self.options
        self.running = True
        self.ui.notice("ok", "Intérprete en marcha.")
        self._watcher = asyncio.create_task(self._stop_after())
        try:
            if opts.mode == "listen":
                frames = await self._listen_frames()
                if opts.inject_wav:
                    from .audio import inject_wav

                    self._injector = await inject_wav(res.sink_in, opts.inject_wav)
                await self._channels[0].run(frames, stop_event=self._stop)
            elif opts.mode == "speak":
                await self._channels[0].run(await self._speak_frames(), stop_event=self._stop)
            else:
                await asyncio.gather(
                    self._channels[0].run(await self._listen_frames(), stop_event=self._stop),
                    self._channels[1].run(await self._speak_frames(), stop_event=self._stop),
                )
        finally:
            self.running = False

    async def _listen_frames(self):
        from .audio import FRAME_SAMPLES, PwCapture, wav_frames

        opts = self.options
        if opts.input_wav:
            return wav_frames(opts.input_wav, frame_samples=FRAME_SAMPLES, realtime=not opts.fast)
        return PwCapture(
            self.resolved.sink_in, rate=16000, channels=1, frame_samples=FRAME_SAMPLES, monitor=True
        ).frames()

    async def _speak_frames(self):
        from .audio import FRAME_SAMPLES, PwCapture, wav_frames

        opts = self.options
        if opts.input_wav:
            return wav_frames(opts.input_wav, frame_samples=FRAME_SAMPLES, realtime=not opts.fast)
        return PwCapture(
            self.resolved.mic, rate=16000, channels=1, frame_samples=FRAME_SAMPLES, monitor=False
        ).frames()

    async def _stop_after(self) -> None:
        opts = self.options
        try:
            if opts.seconds:
                await asyncio.sleep(opts.seconds)
            elif self._injector is not None:
                await self._injector.wait()
                await asyncio.sleep(self.cfg.vad.min_silence_ms / 1000.0 + 0.7)
            else:
                return
        except asyncio.CancelledError:  # pragma: no cover - parada normal
            return
        self._stop.set()

    # ----------------------------------------------------------------- close
    async def close(self) -> None:
        if self._injector is not None and self._injector.returncode is None:
            self._injector.terminate()
            try:
                await self._injector.wait()
            except Exception:  # noqa: BLE001
                pass
        if self._watcher is not None:
            self._watcher.cancel()
            try:
                await self._watcher
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._watcher = None
        for channel in self._channels:
            try:
                await channel.aclose()
            except Exception:  # noqa: BLE001
                pass
        for fwd in (self._ja_fwd, self._es_fwd):
            if fwd is not None:
                try:
                    await fwd.stop()
                except Exception:  # noqa: BLE001
                    pass
        if self._translator is not None:
            try:
                await self._translator.aclose()
            except Exception:  # noqa: BLE001
                pass
        for closer in (self._stt, self._tts_es, self._tts_ja):
            if closer is not None:
                try:
                    closer.close()
                except Exception:  # noqa: BLE001
                    pass
        self.summary = self._build_summary()
        self._channels = []
        self.runtime.speakers.clear()
        self.runtime.channels.clear()
        self.runtime.forwarder = None
        self.runtime.forwarder_es = None
        self._ja_fwd = self._es_fwd = None
        self._stt = self._translator = self._tts_es = self._tts_ja = None

    def _build_summary(self) -> list[str]:
        lines: list[str] = []
        for channel in self._channels:
            stats = channel.stats
            lines.append(
                f"[{channel.name}] {len(stats.results)} frases | descartadas {stats.dropped}"
                f" | filtradas {getattr(stats, 'filtered', 0)}"
                f" (ecos {getattr(stats, 'echos', 0)})"
                f" | sin texto {stats.empty} | errores {stats.errors}"
                f" | audio {stats.seconds_processed:.1f}s"
            )
            if channel.speaker is not None:
                sp = channel.speaker
                lines.append(
                    f"[{channel.name}] TTS {channel.speaker.lang}: {sp.spoken} locutadas"
                    f" | {sp.skipped} descartadas | {sp.muted} silenciadas"
                    f" | {sp.dropped} caducadas | {sp.errors} errores"
                )
        if self._ja_fwd is not None and self._ja_fwd.dropped:
            lines.append(f"Reenvío JA: {self._ja_fwd.dropped} frames descartados (backpressure)")
        if self._log_listen:
            lines.append(f"Latencia registrada en {self._log_listen}")
        return lines


# --------------------------------------------------------------------------
async def _start_fondo(
    target: str, volume: float, duck_factor: float, ui, etiqueta: str
):
    """Crea **y arranca** un reenvío de fondo.

    ``start()`` es obligatorio: sin él la cola interna queda en ``None`` y
    ``feed()`` descarta todo — el fondo se queda mudo sin dar ningún error.
    Fue el fallo real de «no oigo el japonés de fondo» ni mi voz de fondo.
    Si el reproductor no arranca, se avisa y la sesión sigue sin ese fondo.
    """
    from .audio.player import JaForwarder

    if not target:
        ui.notice("warn", f"no sé dónde reproducir {etiqueta}")
        return None
    forwarder = JaForwarder(target, rate=16000, volume=volume, duck_factor=duck_factor)
    try:
        await forwarder.start()
    except Exception as exc:  # noqa: BLE001 - un fondo roto no debe tumbar la sesión
        log.warning("no se pudo activar %s: %s", etiqueta, exc)
        ui.notice("warn", f"no pude activar {etiqueta}: {exc}")
        return None
    log.info("%s activo → %s (vol %.2f)", etiqueta, target, volume)
    return forwarder


def _build_segmenter(cfg: Config):
    from .vad import SileroOnnxVad
    from .vad.base import Segmenter

    return Segmenter(
        SileroOnnxVad(sample_rate=16000),
        sample_rate=16000,
        threshold=cfg.vad.threshold,
        min_silence_ms=cfg.vad.min_silence_ms,
        speech_pad_ms=cfg.vad.speech_pad_ms,
        pre_roll_ms=cfg.vad.pre_roll_ms,
        max_speech_s=cfg.vad.max_speech_s,
    )


def _build_stt(cfg: Config):
    from .stt import FasterWhisperStt

    return FasterWhisperStt(
        model=cfg.stt.model,
        device=cfg.stt.device,
        compute_type=cfg.stt.compute_type,
        beam_size=cfg.stt.beam_size,
        cuda_lib_path=cfg.stt.cuda_lib_path,
        no_speech_threshold=cfg.stt.no_speech_threshold,
        log_prob_threshold=cfg.stt.log_prob_threshold,
        compression_ratio_threshold=cfg.stt.compression_ratio_threshold,
    )


def _sibling_log(path: str, suffix: str) -> str:
    p = Path(path)
    return str(p.with_name(f"{p.stem}-{suffix}{p.suffix or '.csv'}"))
