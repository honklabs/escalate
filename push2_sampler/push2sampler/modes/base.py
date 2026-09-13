"""The mode contract.

A mode owns the meaning of the 64 pads and the buttons while it is on screen.
Modes never touch MIDI or the audio stream directly: they mutate the project and
call back into :class:`~push2sampler.app.App` (``rebuild_schedule``,
``save_soon``, ``notify``, ``goto_*``).

``render_pads`` / ``render_buttons`` run 30 times a second, so they must stay
pure and cheap -- no allocation of audio buffers, no disk access.
"""

from __future__ import annotations

#: Beats of count-in before a take starts recording.
COUNT_IN_BEATS = 4


class Mode:
    """Base class: handles nothing, lights nothing."""

    name = "mode"
    #: True for a mode that opens *over* another one and pops back to it.
    transient = False

    def __init__(self, app) -> None:
        self.app = app

    @property
    def project(self):
        return self.app.project

    @property
    def engine(self):
        return self.app.engine

    # -- lifecycle ---------------------------------------------------------
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def on_tick(self) -> None:
        """Called once per event-loop pass, for time-based behaviour.

        Use this rather than doing work in ``render_pads``: rendering is a pure
        function of state, this is where state may change on its own.
        """

    # -- input; return True when the event has been consumed ---------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        return False

    def on_button(self, cc: int, pressed: bool) -> bool:
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        return False

    def on_engine_event(self, event: tuple) -> None:
        pass

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        pass

    def render_buttons(self, buttons: dict[int, int]) -> None:
        pass

    def status_lines(self) -> list[str]:
        return [self.name]
