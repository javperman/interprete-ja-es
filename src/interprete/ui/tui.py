"""TUI: pantalla completa en la terminal, con transcripción y atajos.

Sin dependencias externas (solo ``termios``/``tty``/``os``). Deja la terminal en
modo *raw*, lee las teclas con ``loop.add_reader`` y redibuja a ~5 Hz. Si stdin no
es una TTY, se degrada a no-op (el ``factory`` normalmente ya elige ``PlainUi``).

Toda la maquetación vive en ``render.py`` (puro); aquí solo se dibuja y se
gestionan las teclas, de modo que un fallo de dibujado nunca tumba el pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys

from .base import Ui
from .keys import parse_actions
from .render import render_frame, subtitles_frame
from .state import AppState

log = logging.getLogger("interprete.ui.tui")

HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR = "\x1b[2J\x1b[H"


class TuiUi(Ui):
    """Pantalla completa. ``renderer`` permite la variante de subtítulos."""

    def __init__(
        self,
        state: AppState,
        *,
        show_original: bool = True,
        fps: float = 5.0,
        renderer=render_frame,
    ) -> None:
        super().__init__(state)
        self.show_original = show_original
        self.show_help = False
        self.fps = max(1.0, fps)
        self.renderer = renderer
        self._fd: int | None = None
        self._old_term = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._out_fd = sys.stdout.fileno() if sys.stdout.isatty() else None

    # ------------------------------------------------------------------ ciclo
    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if not sys.stdin.isatty():
            log.warning("stdin no es una TTY: la TUI no capturará teclas")
            return
        import termios
        import tty

        self._fd = sys.stdin.fileno()
        try:
            self._old_term = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        except Exception:
            log.warning("no se pudo poner la terminal en modo raw", exc_info=True)
            self._old_term = None
            return
        self._write(HIDE_CURSOR + CLEAR)
        self._loop.add_reader(self._fd, self._on_input)
        self._task = self._loop.create_task(self._render_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        if self._fd is not None and self._loop is not None and self._old_term is not None:
            import termios

            try:
                self._loop.remove_reader(self._fd)
            except Exception:  # noqa: BLE001
                pass
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_term)
            except Exception:  # noqa: BLE001
                pass
        self._write(SHOW_CURSOR + CLEAR)

    # ------------------------------------------------------------------ entrada
    def _on_input(self) -> None:
        assert self._fd is not None
        try:
            data = os.read(self._fd, 64)
        except OSError:
            return
        if not data:
            return
        try:
            for action in parse_actions(data):
                self._handle_action(action)
        except Exception:
            log.exception("error procesando una tecla")
        self._draw()

    def _handle_action(self, action: str) -> None:
        if action == "help":
            self.show_help = not self.show_help
            return
        if action == "toggle_original":
            self.show_original = not self.show_original
            return
        self.dispatch(action)

    # ------------------------------------------------------------------ salida
    def _write(self, text: str) -> None:
        if self._out_fd is None:
            return
        try:
            os.write(self._out_fd, text.encode("utf-8", "replace"))
        except OSError:
            pass

    async def _render_loop(self) -> None:
        try:
            while True:
                self._draw()
                await asyncio.sleep(1.0 / self.fps)
        except asyncio.CancelledError:  # pragma: no cover - parada normal
            raise
        except Exception:
            log.exception("fallo en el bucle de dibujado")

    def _draw(self) -> None:
        size = shutil.get_terminal_size(fallback=(100, 30))
        self.tick()
        try:
            frame = self.renderer(
                self.state,
                size.columns,
                size.lines,
                show_original=self.show_original,
                show_help=self.show_help,
            )
        except Exception:
            log.exception("fallo al componer el cuadro")
            return
        self._write("\x1b[H" + frame + "\x1b[J")

    # ------------------------------------------------------------------ avisos
    def _on_turn(self, key: str, res) -> None:
        self._draw()

    def _on_notice(self, level: str, text: str) -> None:
        self._draw()


class SubtitleUi(TuiUi):
    """Variante centrada en la última traducción (útil en ventana flotante)."""

    def __init__(self, state: AppState, *, show_original: bool = True, fps: float = 5.0) -> None:
        super().__init__(state, show_original=show_original, fps=fps, renderer=subtitles_frame)
