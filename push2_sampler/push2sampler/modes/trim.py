"""IN-09: trim a take by ear, without ever stopping the sound.

`NF-03` put trim on two encoders, in milliseconds, next to a picture of the
take. That is a good way to *adjust* a trim and a poor way to *find* one,
because finding the start of a loop goes: turn, listen, turn back, listen -- and
between two listens the sound is gone, so you end up comparing what you hear
against a memory of what you heard. This page never stops the sound. The take
plays, you tap when you hear the point, and a very short loop around that point
then plays over and over while the knobs move it, which turns the decision into
a comparison.

One button runs all of it, and it always means the same thing: **that's it.**
While you are hunting, that means *here is the point*; while you are tuning, it
means *the point is right, move on*.

    HUNT_START  --press/pad-->  TUNE_START  --press-->
    HUNT_END    --press/pad-->  TUNE_END    --press-->  committed

The two windows are deliberately not the same shape. A start window runs
*forward* from the point, so the sound at the loop seam is the attack; an end
window runs *back* to the point, so the sound at the seam is the cut. Whichever
edge you are judging is the one the loop puts under your ear -- and the fade
that stops the seam clicking goes on the *other* edge, so the edge being judged
is never smoothed into sounding better than it is.
"""

from __future__ import annotations

import numpy as np

from .. import colors
from ..analysis import onsets
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    ENCODER_TRACK,
    PAD_COUNT,
    Btn,
)
from ..history import SetTrim
from ..waveform import envelope
from .base import Mode

#: The one button that drives the whole sequence, and the one that opens it.
STEP_BUTTON = Btn.SELECT
#: Snap the point to the nearest attack.
SNAP_BUTTON = DISPLAY_ROW_BOTTOM[0]
#: Put this stage's point back where the take's own edge is.
RESET_BUTTON = DISPLAY_ROW_BOTTOM[7]
#: Buttons that abandon the whole thing, leaving the take untouched.
LEAVE_BUTTONS = (Btn.DELETE, Btn.DEVICE, Btn.SESSION, Btn.NOTE, Btn.LEFT)

#: The four stages, in order.
HUNT_START, TUNE_START, HUNT_END, TUNE_END = range(4)
#: Which stages are hunting (the take plays and a tap marks a point).
HUNTING = (HUNT_START, HUNT_END)
#: Which point each stage is about.
ABOUT_START = (HUNT_START, TUNE_START)

#: How long the homing-in loop is, and the bounds the encoder keeps it inside.
#:
#: 200 ms is long enough to recognise what you are listening to and short enough
#: that the point comes round about five times a second, which is the rate at
#: which two candidates can be compared rather than remembered.
DEFAULT_WINDOW_MS = 200.0
MIN_WINDOW_MS, MAX_WINDOW_MS = 40.0, 1000.0
WINDOW_STEP_MS = 20.0

#: Encoder steps. Two, because a step that is useful for hunting is useless for
#: the last millisecond and a step that is useful for the last millisecond takes
#: forty turns to cross a bar.
COARSE_MS = 20.0
FINE_MS = 1.0

#: Fade on the edge of a window that is *not* being judged, in milliseconds.
SEAM_FADE_MS = 4.0

#: How many windows wide the magnified grid is while tuning.
ZOOM_WINDOWS = 4.0
#: Nearest attack within this much of the point counts as a snap target.
SNAP_REACH_MS = 250.0

#: Leave at least this much audio, so a trim can never produce nothing.
MIN_KEEP_MS = 10.0

STAGE_NAMES = {
    HUNT_START: "find the start",
    TUNE_START: "tune the start",
    HUNT_END: "find the end",
    TUNE_END: "tune the end",
}


def window(audio: np.ndarray, point: int, frames: int, forward: bool,
           fade_frames: int) -> np.ndarray:
    """The short loop for ``point``: ``frames`` of audio on one side of it.

    ``forward`` gives ``[point, point + frames)`` -- a start, whose attack lands
    on the loop seam. Otherwise ``(point - frames, point]`` -- an end, whose cut
    lands there instead.

    The fade goes on the far edge, the one this window is not asking about. A
    raw slice looped in place clicks at the seam, and fading the edge under
    judgement would hide the very thing being judged: a start faded in sounds
    clean whether or not it clips the attack. So a start window is faded at its
    tail and an end window at its head, and what you hear at the seam is the
    truth -- including a click, when a start lands in the middle of a sustain,
    which is worth knowing and is why it is not smoothed away.
    """
    total = 0 if audio is None else audio.shape[0]
    if total == 0 or frames <= 0:
        return np.zeros((0, 1), dtype=np.float32)
    if forward:
        lo = max(0, min(point, total - 1))
        hi = min(total, lo + frames)
    else:
        hi = max(1, min(point, total))
        lo = max(0, hi - frames)
    piece = np.array(audio[lo:hi], dtype=np.float32, copy=True)
    fade = min(int(fade_frames), piece.shape[0])
    if fade > 0:
        ramp = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        if forward:
            piece[-fade:] *= ramp[:, None]
        else:
            piece[:fade] *= ramp[::-1][:, None]
    return np.ascontiguousarray(piece)


class TrimMode(Mode):
    """Trim one take by ear, in four stages driven by one button."""

    name = "trim"
    transient = True

    @property
    def title(self) -> str:
        return f"TRIM SLOT {self.slot + 1}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        self.stage = HUNT_START
        #: Both points in frames of the *recording*, absolute.  Absolute rather
        #: than as `Edits`' two millisecond offsets -- one of which counts from
        #: the far end -- because every question this page asks ("is the end
        #: before the start", "which pad is this") is about positions, and
        #: converting at the edges beats converting at every comparison.
        self.start = 0
        self.end = 0
        self.window_ms = DEFAULT_WINDOW_MS
        self._onsets: list[int] | None = None
        self._auditioning: tuple | None = None
        #: Whether the engine has confirmed the current audition is sounding.
        #: See `on_tick`: it is what tells a loop that was stopped from
        #: outside apart from one that has not started yet.
        self._heard = False
        #: Frame of the recording the audition buffer starts at, so the
        #: engine's position inside that buffer can be read as a position in
        #: the take.
        self._origin = 0

    # -- the take ----------------------------------------------------------
    @property
    def sample(self):
        return self.project[self.slot]

    @property
    def samplerate(self) -> int:
        return self.project.samplerate

    @property
    def audio(self) -> np.ndarray:
        """The **recording**, not the edited result.

        Trim is measured against the raw take, so homing in on a point while
        looking at audio that has already had the trim taken out of it would
        move the ground under the number being set.
        """
        sample = self.sample
        if sample is None:
            return np.zeros((0, 1), dtype=np.float32)
        return sample.audio

    def _ms(self, frames: int) -> float:
        return frames * 1000.0 / max(1, self.samplerate)

    def _frames(self, ms: float) -> int:
        return int(round(ms * self.samplerate / 1000.0))

    # -- lifecycle ---------------------------------------------------------
    def on_enter(self) -> None:
        sample = self.sample
        if sample is None or sample.raw_frames <= 0:
            self.app.notify("nothing recorded in that slot")
            self.app.pop_mode()
            return
        total = sample.raw_frames
        # Open on the trim the sample already has, so this page refines an
        # earlier pass rather than throwing it away.
        self.start = min(self._frames(sample.edits.trim_start_ms), total - 1)
        self.end = max(self.start + 1,
                       total - self._frames(sample.edits.trim_end_ms))
        self.stage = HUNT_START
        self._restart_audition()
        self.app.notify(
            "trim by ear: tap a pad when you hear the start   "
            "Select: that's it   Delete: give up"
        )

    def on_exit(self) -> None:
        self.engine.stop_audition()
        self._auditioning = None

    def on_tick(self) -> None:
        """Keep the right thing looping, and only re-post when it changed.

        The audition is a buffer the engine holds, so it has to be replaced
        whenever the stage, the point or the window length moves -- and must
        *not* be replaced otherwise, because thirty re-posts a second would
        restart the loop thirty times a second and play nothing but its seam.

        It also has to be put *back* when something outside this page stops it.
        Several things release every voice without knowing an audition exists
        -- `Stop`, arming a take, voice stealing -- and going silent in the
        middle of a decision, with the published playhead frozen so the next
        tap lands on frame 0, is the worst failure this page has. So the engine
        says whether one is sounding and this re-posts when it stops being
        true. The ``_heard`` latch is what keeps that from fighting the normal
        case: a freshly posted audition is not audible until the callback has
        run a block, and re-posting during that gap would restart the loop
        every tick forever.
        """
        wanted = self._audition_key()
        if wanted != self._auditioning:
            self._restart_audition()
            return
        if self.engine.auditioning:
            self._heard = True
        elif self._heard:
            self._restart_audition()

    # -- what is playing ---------------------------------------------------
    def _audition_spec(self) -> tuple:
        """``(origin, frames, forward)`` for the loop this stage wants.

        Both the buffer and the cache key are built from this one answer, so
        the key cannot come to disagree with the buffer -- which it did while
        they were worked out separately, and which shows up as a loop that
        either never updates or restarts thirty times a second.
        """
        total = self.audio.shape[0]
        if self.stage in HUNTING:
            # Hunting plays the region still in play, looping, so a point can be
            # tapped next time round rather than needing one good pass.  From
            # the accepted start when hunting the end: the part before it is
            # already decided, and replaying it wastes the listen.
            origin = 0 if self.stage == HUNT_START else self.start
            return origin, max(0, total - origin), True
        forward = self.stage in ABOUT_START
        point = self.start if forward else self.end
        return point, self._frames(self.window_ms), forward

    def _audition_key(self) -> tuple:
        """Everything the current loop depends on; the cache key for re-posting."""
        return self._audition_spec() + (id(self.audio), self.audio.shape)

    def _audition_buffer(self) -> tuple[np.ndarray, int]:
        """The loop for this stage, and the frame of the take it begins at."""
        point, frames, forward = self._audition_spec()
        piece = window(self.audio, point, frames, forward,
                       self._frames(SEAM_FADE_MS))
        origin = point if forward else max(0, point - piece.shape[0])
        return piece, origin

    def _restart_audition(self) -> None:
        buf, origin = self._audition_buffer()
        self._origin = origin
        self._auditioning = self._audition_key()
        self._heard = False
        if buf.shape[0] == 0:
            self.engine.stop_audition()
            return
        sample = self.sample
        self.engine.audition(buf, sample.gain if sample else 1.0)

    @property
    def playhead(self) -> int:
        """Where the sound has reached, as a frame of the recording."""
        return self._origin + int(self.engine.audition_frame)

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """Any pad means *now* -- but only while hunting.

        Any pad rather than the pad under the playhead, because the gesture is
        tapping in time with what you hear and a person doing that is not also
        aiming. And nothing at all while tuning: a pad that meant "now" in one
        stage and "jump here" in the next would make the grid unreadable, and
        the knobs are the tuning instrument.
        """
        if not pressed:
            return True
        if self.stage not in HUNTING:
            self.app.notify("the knobs move the point; Select accepts it")
            return True
        self._mark()
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == STEP_BUTTON:
            self._step()
            return True
        if cc == SNAP_BUTTON:
            self._snap()
            return True
        if cc == RESET_BUTTON:
            self._reset_point()
            return True
        if cc in LEAVE_BUTTONS:
            self.app.notify("trim abandoned; the take is as it was")
            self.app.pop_mode()
            return True
        # Everything else is claimed rather than passed on, which is the
        # opposite of what most pages do here.  This one is making sound and
        # holding a half-finished decision, and the unhandled buttons that
        # reach `App._global_button` include four that open another page *over*
        # this one (`Mix`, `Clip`, `Browse`, `Setup`).  `push_mode` does not
        # call `on_exit` on what it covers, so that buried this page with its
        # loop still playing and no `on_tick` left to stop it.  An allowlist of
        # those four would go stale the next time a page is added; claiming the
        # surface cannot.
        self.app.notify("not while trimming: Select accepts, Delete gives up")
        return True

    def on_encoder(self, cc: int, delta: int) -> bool:
        if cc not in ENCODER_TRACK:
            return False
        index = ENCODER_TRACK.index(cc)
        if index == 2:
            self.window_ms = max(MIN_WINDOW_MS,
                                 min(MAX_WINDOW_MS,
                                     self.window_ms + delta * WINDOW_STEP_MS))
            self.app.notify(f"hearing {self.window_ms:.0f}ms")
            return True
        if index not in (0, 1):
            return False
        if self.stage in HUNTING:
            self.app.notify("tap a pad when you hear it, then the knobs tune it")
            return True
        step = COARSE_MS if index == 0 else FINE_MS
        self._move(delta * self._frames(step))
        return True

    # -- moving the points -------------------------------------------------
    def _limits(self) -> tuple[int, int]:
        """How far this stage's point may travel, in frames.

        The two points may not cross, and may not meet: a start at or past the
        end is a sample of no length, which every later stage of the program
        would then have to have an opinion about.
        """
        total = self.audio.shape[0]
        keep = max(1, self._frames(MIN_KEEP_MS))
        if self.stage in ABOUT_START:
            return 0, max(0, min(self.end - keep, total - 1))
        return min(self.start + keep, total), total

    def _place(self, frame: int) -> None:
        low, high = self._limits()
        frame = max(low, min(high, int(frame)))
        if self.stage in ABOUT_START:
            self.start = frame
        else:
            self.end = frame

    @property
    def point(self) -> int:
        return self.start if self.stage in ABOUT_START else self.end

    def _move(self, frames: int) -> None:
        before = self.point
        self._place(before + frames)
        if self.point != before:
            self.app.notify(self._point_line())

    def _mark(self) -> None:
        """Capture the playhead and go and tune it.

        The playhead the *engine* published, not one worked out from a clock:
        the stream is buffered, a dropout moves it, and a loop wrap resets it,
        so the only frame that matches what a person just heard is the one the
        callback last played.
        """
        self._place(self.playhead)
        self.stage = TUNE_START if self.stage == HUNT_START else TUNE_END
        self._restart_audition()
        self.app.notify(
            f"{self._point_line()}   knobs 1-2: coarse, fine   Select: that's it"
        )

    def _step(self) -> None:
        """One button, one meaning: *that's it.*"""
        if self.stage in HUNTING:
            self._mark()
            return
        if self.stage == TUNE_START:
            self.stage = HUNT_END
            self._restart_audition()
            self.app.notify(
                f"start set at {self._ms(self.start):.0f}ms   "
                "now tap a pad when you hear the end"
            )
            return
        self._commit()

    def _snap(self) -> None:
        """Move the point to the nearest attack, if one is near enough."""
        if self.stage in HUNTING:
            self.app.notify("mark a point first, then snap it to the attack")
            return
        nearest = self._nearest_onset(self.point)
        if nearest is None:
            self.app.notify("no attack near enough to snap to")
            return
        self._place(nearest)
        self.app.notify(f"snapped to the attack   {self._point_line()}")

    def _nearest_onset(self, frame: int) -> int | None:
        if self._onsets is None:
            # Found once and kept: the same take cannot grow new attacks, and
            # this runs an FFT over the whole recording.
            self._onsets = onsets(self.audio, self.samplerate)
        if not self._onsets:
            return None
        nearest = min(self._onsets, key=lambda at: abs(at - frame))
        if abs(nearest - frame) > self._frames(SNAP_REACH_MS):
            return None
        return nearest

    def _reset_point(self) -> None:
        """This stage's point back to the take's own edge."""
        target = 0 if self.stage in ABOUT_START else self.audio.shape[0]
        low, high = self._limits()
        if self.point == max(low, min(high, target)):
            self.app.notify("already at the edge of the take")
            return
        self._place(target)
        self.app.notify(self._point_line())

    def _commit(self) -> None:
        """Write both trims as one undo step and go back to the editor."""
        sample = self.sample
        if sample is None:
            self.app.pop_mode()
            return
        total = sample.raw_frames
        start_ms = self._ms(self.start)
        end_ms = self._ms(max(0, total - self.end))
        previous = sample.edits
        if (round(start_ms, 3) == round(previous.trim_start_ms, 3)
                and round(end_ms, 3) == round(previous.trim_end_ms, 3)):
            self.app.notify("trim unchanged")
        else:
            self.app.do(SetTrim(self.slot, start_ms, end_ms,
                                previous.trim_start_ms, previous.trim_end_ms))
        self.app.pop_mode()

    # -- output ------------------------------------------------------------
    def _view(self) -> tuple[int, int]:
        """The span of the recording the grid is showing, in frames.

        Hunting shows the whole take, because the question is "where in this
        take is it". Tuning shows a few windows either side of the point,
        because the question is "what exactly am I cutting" and the knobs are
        working at a millisecond -- a picture of the whole take cannot show a
        millisecond, and a picture that cannot show what a knob does is a
        decoration.
        """
        total = self.audio.shape[0]
        if self.stage in HUNTING or total == 0:
            return 0, max(1, total)
        span = max(1, int(self._frames(self.window_ms) * ZOOM_WINDOWS))
        low = max(0, self.point - span // 2)
        return low, min(total, low + span)

    def render_pads(self, pads: list[int]) -> None:
        audio = self.audio
        low, high = self._view()
        if audio.shape[0] == 0 or high <= low:
            for index in range(PAD_COUNT):
                pads[index] = colors.OFF.index
            return
        levels = envelope(audio[low:high], PAD_COUNT)
        span = high - low

        def pad_of(frame: int) -> int:
            return int((frame - low) / span * PAD_COUNT)

        start_pad = pad_of(self.start)
        end_pad = pad_of(self.end)
        head = pad_of(self.playhead)
        for index, level in enumerate(levels):
            if index < start_pad or index >= end_pad:
                pads[index] = colors.RED_DIM.index  # outside the trim
            elif level >= 0.5:
                pads[index] = colors.GREEN.index
            elif level >= 0.12:
                pads[index] = colors.GREEN_MID.index
            elif level > 0.0:
                pads[index] = colors.GREEN_DIM.index
            else:
                pads[index] = colors.OFF.index
        # The point on top of the waveform, then the playhead on top of that:
        # the playhead moves, so it has to win, or it vanishes every time it
        # crosses the mark it is being compared against.
        marker = start_pad if self.stage in ABOUT_START else max(0, end_pad - 1)
        if 0 <= marker < PAD_COUNT:
            pads[marker] = (colors.AMBER.index if self.stage in HUNTING
                            else colors.YELLOW.index)
        if 0 <= head < PAD_COUNT:
            pads[head] = colors.WHITE.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[STEP_BUTTON] = BTN_BRIGHT
        buttons[Btn.DEVICE] = BTN_ON
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.DELETE] = BTN_ON
        tuning = self.stage not in HUNTING
        buttons[SNAP_BUTTON] = BTN_ON if tuning else BTN_DIM
        buttons[RESET_BUTTON] = BTN_ON if tuning else BTN_DIM

    def _point_line(self) -> str:
        which = "start" if self.stage in ABOUT_START else "end"
        return f"{which} {self._ms(self.point):.0f}ms"

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["TRIM", "nothing in that slot"]
        total = self.audio.shape[0]
        kept = self._ms(max(0, self.end - self.start))
        lines = [
            f"TRIM slot {self.slot + 1} {sample.name}"
            f"   stage {self.stage + 1} of 4: {STAGE_NAMES[self.stage]}",
            f"start {self._ms(self.start):.0f}ms   "
            f"end {self._ms(self.end):.0f}ms   "
            f"keeping {kept / 1000.0:.2f}s of {self._ms(total) / 1000.0:.2f}s",
        ]
        if self.stage in HUNTING:
            lines.append(
                "it is playing round and round: tap any pad when you hear "
                f"the {'start' if self.stage == HUNT_START else 'end'}"
            )
            lines.append("Select does the same   encoder 3: how much you hear")
        else:
            lines.append(
                f"looping {self.window_ms:.0f}ms "
                f"{'from' if self.stage in ABOUT_START else 'up to'} the point   "
                "encoder 1: coarse   2: fine   3: how much you hear"
            )
            lines.append("button 1: snap to the attack   button 8: back to the edge")
        lines.append(
            "Select: that's it   Delete: give up   the grid magnifies while tuning"
        )
        return lines
