"""Interfaz de UI del intérprete.

Tres implementaciones comparten el mismo contrato y el mismo ``AppState``:

- ``PlainUi``: salida de texto corrida (la de las fases 1–3), ideal para logs.
- ``TuiUi``: pantalla completa en la terminal, con transcripción y atajos.
- ``SubtitleUi``: variante de la TUI centrada en la última traducción.

El CLI llama a ``turn`` y ``notice`` según llegan los resultados, y ejecuta las
acciones que devuelve la UI (teclas) a través de ``on_action``; así la UI no conoce
los detalles del pipeline.
"""

from __future__ import annotations

import abc
from collections.abc import Callable

from .state import AppState

# Una acción devuelve una nota opcional para mostrar al usuario.
ActionHandler = Callable[[str], "str | None"]


class Ui(abc.ABC):
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.on_action: ActionHandler | None = None
        self.on_tick: Callable[[], None] | None = None

    def tick(self) -> None:
        """Refresco periódico opcional (lo usa la TUI para sincronizar datos)."""
        if self.on_tick is not None:
            self.on_tick()

    # -------------------------------------------------- actualizaciones
    def turn(self, key: str, res) -> None:
        """Registra un ``TurnResult`` del canal ``key``."""
        channel = self.state.channel(key)
        if channel is not None:
            channel.add(res)
        self._on_turn(key, res)

    def notice(self, level: str, text: str) -> None:
        self.state.add_notice(level, text)
        self._on_notice(level, text)

    def dispatch(self, action: str) -> str | None:
        """Ejecuta una acción (la interpreta el CLI) y muestra la nota devuelta."""
        if self.on_action is None:
            return None
        note = self.on_action(action)
        if note:
            self.notice("info", note)
        return note

    # -------------------------------------------------- ciclo de vida
    async def start(self) -> None:  # pragma: no cover - trivial
        return None

    async def stop(self) -> None:  # pragma: no cover - trivial
        return None

    async def run(self, main, *, on_action: ActionHandler | None = None) -> None:
        """Arranca la UI, ejecuta ``main`` y la detiene pase lo que pase."""
        self.on_action = on_action
        await self.start()
        try:
            await main()
        finally:
            await self.stop()

    # -------------------------------------------------- hooks
    def _on_turn(self, key: str, res) -> None:
        return None

    def _on_notice(self, level: str, text: str) -> None:
        return None
