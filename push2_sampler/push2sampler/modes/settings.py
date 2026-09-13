"""The settings page: one parameter per button under the display.

Opened and closed with `Setup`.  The pads stay dark, deliberately -- a grid with
nothing on it is the clearest possible signal that this is not a page where
pressing pads does something to your song.

Each of the eight buttons under the display owns one setting: the encoder above
it adjusts the value, and pressing the button cycles it.  Changes take effect at
once and are written to the settings file when the page closes.
"""

from __future__ import annotations

from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    ENCODER_TRACK,
    PAD_COUNT,
    Btn,
)
from ..settings import EDITABLE_PAGES
from .base import Mode


class SettingsMode(Mode):
    name = "settings"
    transient = True

    def __init__(self, app) -> None:
        super().__init__(app)
        self.page = 0

    @property
    def names(self) -> tuple[str, ...]:
        return EDITABLE_PAGES[self.page]

    def on_enter(self) -> None:
        self.app.notify("settings: encoders adjust, Setup closes")

    def on_exit(self) -> None:
        saved = self.app.save_settings()
        if saved:
            self.app.notify("settings saved")

    @property
    def settings(self):
        return self.app.settings

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        return True  # pads do nothing here, on purpose

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc in DISPLAY_ROW_BOTTOM:
            name = self._name_for(DISPLAY_ROW_BOTTOM.index(cc))
            if name is not None:
                spec = self.settings.spec(name)
                self._change(name, spec.cycle(self.settings[name]))
            return True
        if cc in (Btn.UP, Btn.DOWN):
            step = -1 if cc == Btn.UP else 1
            self.page = (self.page + step) % len(EDITABLE_PAGES)
            self.app.notify(f"settings page {self.page + 1}/{len(EDITABLE_PAGES)}")
            return True
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT, Btn.STOP):
            self.app.pop_mode()
            return True
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        if cc in ENCODER_TRACK:
            name = self._name_for(ENCODER_TRACK.index(cc))
            if name is not None:
                spec = self.settings.spec(name)
                self._change(name, spec.nudge(self.settings[name], delta))
            return True
        return False

    def _name_for(self, index: int) -> str | None:
        names = self.names
        return names[index] if index < len(names) else None

    def _change(self, name: str, value) -> None:
        self.settings.set(name, value)
        if self.app.apply_settings(name):
            self.app.notify(self.settings.label(name))
        # On failure the engine's audio_error event does the talking.

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        for i in range(PAD_COUNT):
            pads[i] = 0

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.SETUP] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        for index, cc in enumerate(DISPLAY_ROW_BOTTOM):
            buttons[cc] = BTN_ON if index < len(self.names) else BTN_DIM
        if len(EDITABLE_PAGES) > 1:
            buttons[Btn.UP] = buttons[Btn.DOWN] = BTN_DIM

    def status_lines(self) -> list[str]:
        pages = len(EDITABLE_PAGES)
        head = "SETTINGS   Setup closes   encoder above each button"
        if pages > 1:
            head = (f"SETTINGS {self.page + 1}/{pages}   Setup closes   "
                    "up/down for more")
        lines = [head]
        row: list[str] = []
        for name in self.names:
            row.append(self.settings.label(name))
            if len(row) == 3:
                lines.append("   ".join(row))
                row = []
        if row:
            lines.append("   ".join(row))
        return lines
