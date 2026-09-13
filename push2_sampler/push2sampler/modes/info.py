"""What a take sounds like, according to the instrument (IN-02).

`Layout` on a sample page opens this. The instrument has heard everything you
played, so it should be able to tell you something about it: what kind of sound
this is, what note, how fast, how bright, how loud. All of it DSP -- no
network, no model weights, nothing to install.

The grid is the take's **spectrum over time**: columns are time, rows are
frequency with the bottom row lowest, brightness is energy. It is a
spectrogram, which is the one view of a sample no other page gives -- the
[editor](sample_edit.py) shows the envelope and this shows what is in it. A
kick is a bright blob along the bottom, a hat is a stripe across the top, a
held note is a horizontal line.

Everything on this page is a **reading**, and every reading comes with how sure
it is. That is the whole design: a guess stated confidently is worse than no
guess, so `tone A4 (0.89)` and `tone A4 (0.21)` look different, and the page
says `not sure` rather than rounding a weak measurement up into a fact.

The one thing it can change
---------------------------
Button 1 accepts the suggested name. Nothing else here writes to the project,
because a page whose job is to tell you what it thinks should not be quietly
acting on it -- the spec called hints "proposals", and this is the shape of a
proposal: shown, and one press away from being taken.
"""

from __future__ import annotations

import numpy as np

from .. import colors, names
from ..analysis import N_FFT, describe
from ..constants import (
    BTN_BRIGHT,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    GRID_H,
    GRID_W,
    PAD_COUNT,
    Btn,
)
from ..history import SetName
from .base import Mode

#: Pad brightness thresholds for the spectrogram, as fractions of the loudest
#: cell.  Four steps is what the palette has; more would not read anyway.
BRIGHT, MID, DIM = 0.35, 0.12, 0.03
#: Confidence below which a reading is reported as unsure rather than as fact.
UNSURE = 0.35
#: The top row covers this fraction of the spectrum and up.  Linear frequency
#: would put a whole kick in one row and leave five rows for the hiss, so the
#: rows are spaced by octaves from here down.
TOP_HZ = 12_000.0
BOTTOM_HZ = 40.0


class InfoMode(Mode):
    """A reading of one take, and a name you can accept."""

    name = "info"
    transient = True

    @property
    def title(self) -> str:
        return f"ABOUT {self.slot + 1}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        self._described = None
        self._grid: list[float] | None = None

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        reading = self.described
        if reading is None or not reading.role:
            self.app.notify("nothing to listen to in that slot")
            return
        self.app.notify(
            f"{reading.role} ({reading.confidence:.2f}) - "
            f"button 1 names it {self.described.suggested_name!r}"
        )

    # -- the reading -------------------------------------------------------
    @property
    def described(self):
        """The reading, computed once.

        An FFT over the whole take is not a per-frame cost: this is cached for
        the life of the page, and the page is opened by a button press.
        """
        if self._described is None:
            sample = self.sample
            if sample is None:
                return None
            self._described = describe(
                sample.effective_audio(self.project.samplerate),
                self.project.samplerate,
                reference_bpm=self.project.bpm,
            )
        return self._described

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """Pads are a picture here.  A press auditions, and nothing else."""
        if pressed:
            sample = self.sample
            if sample is not None:
                self.engine.preview(
                    sample.effective_audio(self.project.samplerate),
                    gain=sample.gain, slot=self.slot,
                )
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc in (Btn.LAYOUT, Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        if cc == DISPLAY_ROW_BOTTOM[0]:
            self._accept_name()
            return True
        return False

    def _accept_name(self) -> None:
        """Take the suggested name.  The one thing this page can change."""
        sample = self.sample
        reading = self.described
        if sample is None or reading is None or not reading.suggested_name:
            self.app.notify("no name to suggest")
            return
        # The same uniqueness rule the naming page uses, so a second "kick"
        # becomes "kick 2" rather than colliding.
        taken = {s.name for s in self.project.filled() if s.slot != self.slot}
        wanted = names.suffixed(reading.suggested_name, taken)
        if wanted == sample.name:
            self.app.notify(f"already called {wanted!r}")
            return
        self.app.do(SetName(self.slot, wanted, sample.name))
        self.app.notify(f"named {wanted!r}")

    # -- output ------------------------------------------------------------
    def _spectrogram(self) -> list[float]:
        """The take as 8x8 cells of energy, 0..1, top row highest in pitch.

        Rows are spaced by **octaves** rather than linearly: a linear split
        would put every drum in the bottom row and give five rows to hiss
        nobody can hear, which is a picture of the FFT rather than of the
        sound.
        """
        if self._grid is not None:
            return self._grid
        sample = self.sample
        if sample is None:
            self._grid = [0.0] * PAD_COUNT
            return self._grid
        audio = sample.effective_audio(self.project.samplerate)
        mono = audio.mean(axis=1) if audio.ndim > 1 else audio
        cells = [0.0] * PAD_COUNT
        if mono.size < N_FFT:
            self._grid = cells
            return cells

        samplerate = self.project.samplerate
        # One spectrum per column, from that column's slice of the take.
        edges = np.linspace(0, mono.shape[0], GRID_W + 1).astype(int)
        freqs = np.fft.rfftfreq(N_FFT, 1.0 / samplerate)
        # Octave-spaced row edges, lowest row first.
        row_edges = np.geomspace(BOTTOM_HZ, min(TOP_HZ, samplerate / 2), GRID_H + 1)
        window = np.hanning(N_FFT).astype(np.float32)
        for column in range(GRID_W):
            start, end = edges[column], edges[column + 1]
            if end - start < N_FFT:
                # A short column still gets a spectrum, centred on its middle,
                # rather than being left blank for being narrow.
                centre = max(0, min(mono.shape[0] - N_FFT, (start + end) // 2))
                chunk = mono[centre:centre + N_FFT]
            else:
                chunk = mono[start:start + N_FFT]
            if chunk.shape[0] < N_FFT:
                continue
            spectrum = np.abs(np.fft.rfft(chunk * window))
            for row in range(GRID_H):
                band = (freqs >= row_edges[row]) & (freqs < row_edges[row + 1])
                value = float(spectrum[band].sum()) if band.any() else 0.0
                # Row 0 of the grid is the top, and row 0 here is the lowest
                # band, so the picture is flipped on the way in.
                cells[(GRID_H - 1 - row) * GRID_W + column] = value
        top = max(cells)
        self._grid = [c / top for c in cells] if top > 0 else cells
        return self._grid

    def render_pads(self, pads: list[int]) -> None:
        cells = self._spectrogram()
        for index, value in enumerate(cells):
            if value >= BRIGHT:
                pads[index] = colors.GREEN.index
            elif value >= MID:
                pads[index] = colors.GREEN_MID.index
            elif value >= DIM:
                pads[index] = colors.GREEN_DIM.index
            else:
                pads[index] = colors.OFF.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.LAYOUT] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        reading = self.described
        can_name = bool(reading is not None and reading.suggested_name)
        buttons[DISPLAY_ROW_BOTTOM[0]] = BTN_ON if can_name else 0
        for cc in DISPLAY_ROW_BOTTOM[1:]:
            buttons[cc] = 0

    def status_lines(self) -> list[str]:
        sample = self.sample
        reading = self.described
        if sample is None or reading is None:
            return ["ABOUT", "that slot is empty"]
        if not reading.role:
            return [
                f"ABOUT slot {self.slot + 1} {sample.name}",
                "nothing audible in this take",
                f"{reading.seconds:.2f}s, peak {reading.peak:.3f}",
                "Layout: close",
            ]

        lines = [
            f"ABOUT slot {self.slot + 1} {sample.name}   "
            f"{reading.seconds:.2f}s  {sample.bars} bar(s)",
            self._sound_line(reading),
            self._time_line(reading),
            self._level_line(reading),
        ]
        suggestion = reading.suggested_name
        if suggestion:
            lines.append(f"button 1: name it {suggestion!r}   pad: hear it")
        lines.append("every reading is a measurement, not a fact - Layout: close")
        return lines

    @staticmethod
    def _sound_line(reading) -> str:
        """What kind of sound, and the pitch if there is one."""
        sure = "" if reading.confidence >= UNSURE else "  not sure"
        line = f"sounds like: {reading.role} ({reading.confidence:.2f}){sure}"
        if reading.note:
            pitch = f"   {reading.note} ({reading.f0:.0f} Hz"
            if reading.pitch_confidence < UNSURE:
                pitch += ", unsure"
            line += pitch + ")"
        return line

    @staticmethod
    def _time_line(reading) -> str:
        """Tempo and how busy it is, each only when it can be claimed."""
        parts = []
        if reading.bpm > 0:
            confidence = f"{reading.bpm_confidence:.2f}"
            if reading.bpm_confidence < UNSURE:
                confidence += ", loose"
            parts.append(f"about {reading.bpm:.0f} BPM ({confidence})")
        else:
            parts.append("no tempo to read")
        parts.append(f"{len(reading.onsets)} hit(s)")
        if reading.seconds > 0:
            parts.append(f"{reading.density:.1f}/s")
        return "   ".join(parts)

    @staticmethod
    def _level_line(reading) -> str:
        low, mid, high = reading.bands
        brightness = (
            "dark" if reading.centroid < 500 else
            "warm" if reading.centroid < 2000 else
            "bright" if reading.centroid < 6000 else "very bright"
        )
        return (
            f"{brightness} ({reading.centroid:.0f} Hz)   "
            f"low {low * 100:.0f}% mid {mid * 100:.0f}% high {high * 100:.0f}%   "
            f"peak {reading.peak:.2f}"
        )
