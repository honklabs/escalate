"""NF-08: a file browser, on 64 pads.

`Shift`+`Browse` opens this over the samples root. Directories are white, audio
files blue, and the file the display is describing is bright. One press
highlights, a second press acts -- enter the directory, or import the file --
which is the project browser's gesture, so there is one rule for "you are about
to do something" rather than two.

Two things it refuses to do quietly. It does not stretch audio to fit the grid:
an imported file that is not a whole number of bars long is flagged off-grid
like any other mis-fitting take, and fixing it is a button on the sample page.
And it does not pretend to read formats the machine cannot: without
``soundfile``, a `.flac` pad is dim and says why when you highlight it.
"""

from __future__ import annotations

from pathlib import Path

from .. import colors
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    PAD_COUNT,
    Btn,
)
from ..history import ImportSample
from ..importer import listing, make_sample, probe
from .base import Mode

#: Buttons under the display, left to right.
IMPORT, UP, ROOT, HOME = 0, 1, 2, 4


class ImportBrowserMode(Mode):
    name = "import"

    @property
    def title(self) -> str:
        return "IMPORT"
    transient = True

    def __init__(self, app, directory=None) -> None:
        super().__init__(app)
        self.directory = Path(directory or app.samples_root).expanduser()
        self.dirs: list[Path] = []
        self.files: list[Path] = []
        #: Index a *second* press would act on, or None when nothing is armed.
        #:
        #: Starts at None rather than 0 so the first press is always a
        #: highlight.  With a default of 0 the top-left pad acted on a single
        #: press while every other pad took two -- and the action can be an
        #: import, which is not something to do on a stray press.
        self.selected: int | None = None
        self._info = None

    # -- contents ----------------------------------------------------------
    def on_enter(self) -> None:
        self.refresh()
        self._announce()

    def refresh(self) -> None:
        self.dirs, self.files = listing(self.directory)
        # One page: a samples folder with more than 64 entries needs paging, and
        # paging needs somewhere to put the page number.  Until then, say so
        # rather than silently showing the first 64.
        self.overflow = max(0, len(self.dirs) + len(self.files) - PAD_COUNT)
        self.entries = (self.dirs + self.files)[:PAD_COUNT]
        if self.selected is not None and self.selected >= len(self.entries):
            self.selected = None
        self._info = None

    @property
    def current(self) -> Path | None:
        if self.selected is not None and 0 <= self.selected < len(self.entries):
            return self.entries[self.selected]
        return None

    @property
    def info(self):
        """Header of the highlighted file, read once and remembered."""
        path = self.current
        if path is None or path.is_dir():
            return None
        if self._info is None or self._info.path != path:
            self._info = probe(path)
        return self._info

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed or index >= len(self.entries):
            return True
        if index == self.selected:
            self._act()
        else:
            self.selected = index
            self._info = None
            self._describe()
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        row = list(DISPLAY_ROW_BOTTOM)
        if cc == row[IMPORT]:
            self._act()
            return True
        if cc == row[UP]:
            self._go(self.directory.parent)
            return True
        if cc == row[ROOT]:
            self._go(Path(self.app.samples_root).expanduser())
            return True
        if cc == row[HOME]:
            self._go(Path.home())
            return True
        if cc in (Btn.SESSION, Btn.LEFT, Btn.NOTE, Btn.BROWSE):
            self.app.pop_mode()
            return True
        if cc in (Btn.UP, Btn.DOWN) and self.entries:
            step = -1 if cc == Btn.UP else 1
            here = 0 if self.selected is None else self.selected + step
            self.selected = here % len(self.entries)
            self._info = None
            self._describe()
            return True
        return False

    # -- actions -----------------------------------------------------------
    def _go(self, directory: Path) -> None:
        directory = Path(directory)
        if not directory.is_dir():
            self.app.notify(f"{directory} is not a directory")
            return
        self.directory = directory
        self.selected = None
        self.refresh()
        self._announce()

    def _announce(self) -> None:
        """One message per move, and the useful one.

        The first version notified the counts inside ``refresh`` and then the
        path in ``_go``, so "nothing to import" was immediately overwritten by
        the directory name -- the same burying that hid the auto-normalise note
        behind a page change earlier in this project.
        """
        if not self.entries:
            self.app.notify(f"nothing to import in {self.directory}")
            return
        self.app.notify(
            f"{self.directory}  --  {len(self.dirs)} folder(s), "
            f"{len(self.files)} audio file(s)"
        )

    def _act(self) -> None:
        path = self.current
        if path is None:
            return
        if path.is_dir():
            self._go(path)
        else:
            self._import(path)

    def _import(self, path: Path) -> None:
        slot = self.app.import_target()
        if slot is None:
            self.app.notify("every slot is full")
            return
        try:
            sample = make_sample(self.project, path, slot)
        except ImportError as exc:
            # A missing codec, an unreadable file, an empty one: all sentences,
            # none of them a traceback in the middle of a gesture.
            self.app.notify(str(exc))
            return
        self.app.do(ImportSample(slot, sample, source=str(path)))
        note = f"{sample.name} -> slot {slot + 1}, {sample.bars} bar(s)"
        if self.project.mismatched(sample):
            exact = sample.bars_at(
                self.project.bpm, self.project.samplerate, self.project.beats_per_bar
            )
            note += f" - OFF GRID, {exact:.2f} bars"
        self.app.pop_mode()
        self.app.goto_sample(slot)
        self.app.notify(note)

    def _describe(self) -> None:
        path = self.current
        if path is None:
            return
        if path.is_dir():
            dirs, files = listing(path)
            self.app.notify(
                f"{path.name}/  {len(dirs)} folder(s), {len(files)} audio file(s)"
            )
        else:
            self.app.notify(self.info.label)

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        for index in range(PAD_COUNT):
            pads[index] = colors.OFF
        for index, path in enumerate(self.entries):
            if path.is_dir():
                colour = (
                    colors.WHITE if index == self.selected else colors.WHITE_DIM
                )
            elif index == self.selected:
                colour = colors.BLUE
            else:
                colour = colors.BLUE_DIM
            pads[index] = colour

    def render_buttons(self, buttons: dict[int, int]) -> None:
        row = list(DISPLAY_ROW_BOTTOM)
        path = self.current
        buttons[row[IMPORT]] = BTN_BRIGHT if path is not None else BTN_DIM
        buttons[row[UP]] = (
            BTN_ON if self.directory.parent != self.directory else BTN_DIM
        )
        buttons[row[ROOT]] = BTN_DIM
        buttons[row[HOME]] = BTN_DIM
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.BROWSE] = BTN_BRIGHT

    def status_lines(self) -> list[str]:
        path = self.current
        lines = [
            f"IMPORT  {self.directory}",
            f"{len(self.dirs)} folder(s)  {len(self.files)} audio file(s)"
            + (f"  (+{self.overflow} not shown)" if self.overflow else ""),
        ]
        if path is None:
            lines.append(
                "press a pad to see what it is, again to open or import it"
                if self.entries
                else "nothing here - button 2 goes up, 3 to the samples root"
            )
            return lines
        if path.is_dir():
            lines.append(f"{path.name}/   press again to open")
        else:
            info = self.info
            lines.append(info.label if info else path.name)
            if info is not None and info.readable:
                target = self.app.import_target()
                where = f"slot {target + 1}" if target is not None else "no free slot"
                lines.append(f"press again to import into {where}")
            else:
                lines.append("cannot read this one")
        lines.append("button 1: import   2: up   3: samples root   5: home")
        return lines
