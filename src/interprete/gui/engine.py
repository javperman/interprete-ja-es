"""Hilo del motor: ejecuta la sesión en su propio bucle ``asyncio``.

La GUI vive en el hilo principal de GTK; la sesión (STT/MT/TTS y captura) corre
en un hilo con su propio bucle. Toda comunicación hacia GTK se hace con
``GLib.idle_add`` y hacia el motor con ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable

from ..config import Config
from ..session import Session, SessionOptions

log = logging.getLogger("interprete.gui.engine")


class Engine:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="interprete", daemon=True)
        self._thread.start()
        self.session: Session | None = None
        self.busy = False

    # ------------------------------------------------------------------
    def start_session(
        self,
        cfg: Config,
        options: SessionOptions,
        ui,
        on_done: Callable[[Session], None],
    ) -> None:
        """Lanza una sesión nueva (no llamar si ya hay una en marcha)."""
        if self.busy:
            log.warning("ya hay una sesión en marcha")
            return

        def _spawn() -> None:
            self.session = Session(cfg, options, ui)
            self.busy = True

            async def _run() -> None:
                try:
                    await self.session.serve()
                finally:
                    self.busy = False
                    session = self.session
                    from gi.repository import GLib

                    GLib.idle_add(on_done, session)

            self._loop.create_task(_run())

        self._loop.call_soon_threadsafe(_spawn)

    def request_stop(self) -> None:
        session = self.session
        if session is not None:
            self._loop.call_soon_threadsafe(session.request_stop)

    def apply(self, action: str) -> None:
        session = self.session
        if session is not None:
            self._loop.call_soon_threadsafe(session.runtime.apply, action)

    def sync_state(self) -> None:
        """Refresca ``AppState`` desde el motor (lectura desde el hilo de GTK)."""
        session = self.session
        if session is not None:
            session.runtime.sync()

    def shutdown(self) -> None:
        self.request_stop()
        self._loop.call_soon_threadsafe(self._loop.stop)
