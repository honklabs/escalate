"""Switching songs without a terminal.

`Browse` lists the projects under one root, sixty-four at a time. Opening one
saves what you were working on, stops the transport, and swaps the project in
place -- the audio stream is never restarted, so the change is silent rather
than a gap.

No text entry here either: a new project is named from the date and a word, and
renaming picks from the same word list the sample namer uses.
"""

from __future__ import annotations

import time

from .. import colors, names
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    PAD_COUNT,
    Btn,
)
from .base import Mode

#: Buttons under the display, left to right.
OPEN, NEW, DUPLICATE, DELETE = 0, 1, 2, 4
#: Deleting a project needs the button held this long: it is the one action here
#: that undo cannot reach, because it is a directory rather than an edit.
HOLD_DELETE_S = 1.2


class BrowserMode(Mode):
    name = "browser"
    transient = True

    def __init__(self, app) -> None:
        super().__init__(app)
        self.entries = []
        self.selected = 0
        self._delete_since: float | None = None
        self._message = ""

    def on_enter(self) -> None:
        self.refresh()
        self.app.notify(f"{len(self.entries)} project(s) in {self.app.project_root}")

    def refresh(self) -> None:
        from ..project import Project

        self.entries = Project.scan(self.app.project_root)[:PAD_COUNT]
        here = str(self.app.project_dir) if self.app.project_dir else None
        for index, entry in enumerate(self.entries):
            if here and str(entry.path) == here:
                self.selected = index
        self.selected = min(self.selected, max(0, len(self.entries) - 1))

    @property
    def current(self):
        if 0 <= self.selected < len(self.entries):
            return self.entries[self.selected]
        return None

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed or index >= len(self.entries):
            return True
        if index == self.selected:
            self._open()  # a second press on the highlighted one opens it
        else:
            self.selected = index
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if cc in DISPLAY_ROW_BOTTOM and DISPLAY_ROW_BOTTOM.index(cc) == DELETE:
            self._delete_button(pressed)
            return True
        if not pressed:
            return False
        if cc in (Btn.BROWSE, Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        if cc in (Btn.UP, Btn.DOWN) and self.entries:
            step = -1 if cc == Btn.UP else 1
            self.selected = (self.selected + step) % len(self.entries)
            return True
        if cc in DISPLAY_ROW_BOTTOM:
            which = DISPLAY_ROW_BOTTOM.index(cc)
            if which == OPEN:
                self._open()
            elif which == NEW:
                self._new()
            elif which == DUPLICATE:
                self._duplicate()
            return True
        return False

    def _open(self) -> None:
        entry = self.current
        if entry is None:
            return
        if self.app.project_dir and str(entry.path) == str(self.app.project_dir):
            self.app.notify(f"{entry.name} is already open")
            return
        if self.app.open_project(entry.path):
            self.app.notify(f"opened {entry.name}")

    def _new(self) -> None:
        path = self.app.new_project_path()
        if self.app.open_project(path, create=True):
            self.refresh()
            self.app.notify(f"new project {path.name}")

    def _duplicate(self) -> None:
        entry = self.current
        if entry is None:
            return
        copy = self.app.duplicate_project(entry.path)
        if copy is None:
            return
        self.refresh()
        self.app.notify(f"copied to {copy.name}")

    def _delete_button(self, pressed: bool) -> None:
        """Hold to confirm: this is the one action undo cannot take back."""
        entry = self.current
        if not pressed:
            self._delete_since = None
            return
        if entry is None:
            return
        if self.app.project_dir and str(entry.path) == str(self.app.project_dir):
            self.app.notify("cannot delete the project you have open")
            return
        self._delete_since = time.monotonic()
        self.app.notify(f"hold to delete {entry.name}")

    def on_tick(self) -> None:
        if self._delete_since is None:
            return
        if time.monotonic() - self._delete_since < HOLD_DELETE_S:
            return
        self._delete_since = None
        entry = self.current
        if entry is not None and self.app.delete_project(entry.path):
            self.refresh()
            self.app.notify(f"deleted {entry.name}")

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        open_here = str(self.app.project_dir) if self.app.project_dir else None
        for index in range(PAD_COUNT):
            if index >= len(self.entries):
                pads[index] = colors.OFF.index
                continue
            entry = self.entries[index]
            if index == self.selected:
                pads[index] = colors.WHITE.index if self.app.blink else colors.AMBER.index
            elif open_here and str(entry.path) == open_here:
                pads[index] = colors.AMBER_DIM.index  # the one you are in
            elif entry.has_audio:
                pads[index] = colors.GREEN.index
            else:
                pads[index] = colors.WHITE_DIM.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.BROWSE] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.UP] = buttons[Btn.DOWN] = BTN_DIM
        for index, cc in enumerate(DISPLAY_ROW_BOTTOM):
            if index in (OPEN, NEW, DUPLICATE):
                buttons[cc] = BTN_ON
            elif index == DELETE:
                buttons[cc] = BTN_BRIGHT if self._delete_since else BTN_DIM
            else:
                buttons[cc] = 0

    def status_lines(self) -> list[str]:
        entry = self.current
        if entry is None:
            return [
                f"BROWSER  nothing in {self.app.project_root}",
                "button 2 below: start a new project",
                "Browse: back",
            ]
        when = time.strftime("%d %b %H:%M", time.localtime(entry.modified))
        return [
            f"BROWSER  {entry.name}",
            f"{entry.bpm:.0f} BPM   {entry.slots} sample(s)   "
            f"{entry.pages} page(s)   {when}",
            "pad again: open   1 open  2 new  3 duplicate  5 hold to delete",
            f"{len(self.entries)} project(s) in {self.app.project_root}",
        ]


#: Words a new project can be named after, so naming needs no keyboard.
def project_word(seed: int) -> str:
    pool = [w for _, group in names.CATEGORIES for w in group]
    return pool[seed % len(pool)]
