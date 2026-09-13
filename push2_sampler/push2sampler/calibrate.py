"""Measure input latency by listening for your own click come back.

Setting `record latency` by hand is guesswork. This plays a click and watches the
input for it -- over a loopback cable, or just a speaker and a microphone in a
quiet room -- and writes what it measures.

It deliberately does **not** go through :class:`~push2sampler.audio.Engine`.
What we are measuring is the round trip through the audio device, so the less of
our own code is in the path the more honest the number is; and a duplex
play-and-record is one call to PortAudio.

The work is split so that none of it needs hardware to test:

* :func:`detect_offset` is arithmetic over two buffers.
* :func:`measure` drives an injected ``playrec``, so a synthetic delayed
  loopback stands in for a sound card.
"""

from __future__ import annotations

import numpy as np

from .audio import make_click

#: Clicks to play.  The median of several rejects one cough or door slam.
ROUNDS = 5
#: Seconds recorded per round; the click is played at the start of the window.
WINDOW_S = 0.4
#: A detection must stand this far above the noise floor to count.
THRESHOLD_RATIO = 8.0
#: Beyond this it is not latency, it is an echo or a misdetection.
MAX_LATENCY_MS = 250.0
#: Below this the input is silence as far as we are concerned.
MIN_PEAK = 1e-4
#: Rounds varying by more than this mean the measurement should not be trusted.
SPREAD_WARN_MS = 10.0


def _mono(buf) -> np.ndarray:
    array = np.asarray(buf, dtype=np.float64)
    return array.mean(axis=1) if array.ndim > 1 else array


def detect_offset(captured, click, threshold_ratio: float = THRESHOLD_RATIO) -> int | None:
    """Frames from the start of ``captured`` to the click arriving in it.

    Cross-correlation rather than a threshold crossing: a click that went out of
    a speaker and came back through a microphone is smeared and coloured, and its
    *shape* survives that far better than its amplitude does.

    Returns None when nothing in the window looks like the click, which is the
    normal answer when the output is not reaching the input at all.
    """
    signal, kernel = _mono(captured), _mono(click)
    if kernel.size == 0 or signal.size <= kernel.size:
        return None
    if float(np.max(np.abs(signal))) < MIN_PEAK:
        return None  # nothing came back
    correlation = np.abs(np.correlate(signal, kernel, mode="valid"))
    peak = int(np.argmax(correlation))
    magnitude = float(correlation[peak])
    if magnitude <= 0.0:
        return None
    # The noise floor is the rest of the correlation, with the peak's own
    # neighbourhood cut out so a strong hit cannot raise its own bar.
    guard = max(1, kernel.size // 2)
    rest = np.concatenate([correlation[: max(0, peak - guard)], correlation[peak + guard:]])
    floor = float(np.median(rest)) if rest.size else 0.0
    if floor > 0.0 and magnitude < floor * threshold_ratio:
        return None
    return peak


def latency_ms(offset: int, samplerate: int) -> float:
    return offset / float(samplerate) * 1000.0


def summarise(measurements: list[float | None]) -> tuple[float | None, str]:
    """The median of the rounds that worked, and a sentence about them."""
    usable = [m for m in measurements if m is not None]
    total = len(measurements)
    if not usable:
        return None, (
            "heard nothing come back - connect the output to the input, or put a "
            "microphone near the speaker, and turn both up a little"
        )
    median = float(np.median(usable))
    spread = float(max(usable) - min(usable))
    if median > MAX_LATENCY_MS:
        return None, (
            f"measured {median:.0f} ms, too much to be latency - probably a room "
            f"reflection rather than the click itself, so it is not being written"
        )
    note = f"{median:.1f} ms from {len(usable)}/{total} rounds"
    if spread > SPREAD_WARN_MS:
        note += f", varying by {spread:.0f} ms - worth running again somewhere quieter"
    return median, note


def measure(playrec, samplerate: int, channels: int = 2, rounds: int = ROUNDS,
            window_s: float = WINDOW_S) -> tuple[float | None, str]:
    """Play a click ``rounds`` times through ``playrec`` and time its return.

    ``playrec(outdata) -> captured`` plays one buffer and returns what was heard
    over the same span, which is what :func:`sounddevice.playrec` does.
    """
    click = make_click(samplerate, 1000.0, channels, gain=0.9)
    frames = max(click.shape[0] + 1, int(window_s * samplerate))
    outdata = np.zeros((frames, channels), dtype=np.float32)
    outdata[: click.shape[0]] = click
    measurements: list[float | None] = []
    for _ in range(rounds):
        captured = playrec(outdata)
        offset = detect_offset(captured, click)
        measurements.append(None if offset is None else latency_ms(offset, samplerate))
    return summarise(measurements)


def sounddevice_playrec(samplerate: int, channels: int, input_device=None,
                        output_device=None):
    """A ``playrec`` backed by the real audio device."""
    import sounddevice as sd

    def playrec(outdata):
        captured = sd.playrec(
            outdata,
            samplerate=samplerate,
            channels=1,
            device=(input_device, output_device),
            dtype="float32",
        )
        sd.wait()
        return captured

    return playrec


def run(settings, playrec=None, write: bool = True, say=print) -> int:
    """The ``--calibrate`` command: measure, report, and store the result."""
    samplerate = int(settings["samplerate"])
    channels = int(settings["out_channels"])
    say("Calibrating input latency.")
    say("Connect the output to the input, or point a microphone at the speaker.")
    say(f"Playing {ROUNDS} clicks at {samplerate} Hz...")
    if playrec is None:
        try:
            playrec = sounddevice_playrec(
                samplerate, channels,
                settings["input_device"], settings["output_device"],
            )
        except Exception as exc:
            say(f"Could not open the audio device: {exc}")
            return 2
    try:
        value, note = measure(playrec, samplerate, channels)
    except Exception as exc:
        say(f"Could not measure: {exc}")
        return 2
    if value is None:
        say(f"Could not measure: {note}")
        return 1
    say(f"Measured {note}.")
    if not write:
        say("Not writing it (--no-settings).")
        return 0
    stored = settings.set("rec_latency_ms", value)
    if abs(float(stored) - value) > 0.05:
        say(f"Clamped to {stored:.1f} ms by the setting's range.")
    path = settings.save()
    say(f"rec_latency_ms = {float(stored):.1f}" + (f" -> {path}" if path else ""))
    return 0
