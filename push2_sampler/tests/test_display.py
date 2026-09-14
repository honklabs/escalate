"""The Push 2 colour display, checked byte by byte against a fake USB device.

The display is the one part of the protocol with no forgiveness: a wrong frame
header or the wrong pixel packing shows as garbage rather than an error, and no
machine here has the device to try it on.  So the framing is pinned here, and
`--selftest` asks a human to confirm the result on real glass.

It has now been seen on real glass, and both defects a photograph found were
defects these tests were supposed to catch -- one because an assertion compared
a constant to itself, one because nothing measured text at all.  `F-08`
findings 9 and 10; the sections at the bottom are what closes them.
"""

import numpy as np
import pytest

from push2sampler.display import (
    ELLIPSIS,
    ENDPOINT,
    FRAME_HEADER,
    HEIGHT,
    LINE_PIXELS,
    WIDTH,
    XOR_MASK32,
    XOR_PATTERN,
    Push2Display,
    fit,
    open_display,
)


class FakeUsb:
    """Records what would have gone to the device."""

    def __init__(self):
        self.writes: list[tuple[int, bytes]] = []

    def write(self, endpoint, data, timeout=None):
        self.writes.append((endpoint, bytes(data)))
        return len(data)


class FakeImage:
    """Enough of a PIL image for draw_image, without needing Pillow."""

    def __init__(self, array):
        self.array = array

    def convert(self, _mode):
        return self.array


def solid(r, g, b):
    array = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    array[:, :, 0], array[:, :, 1], array[:, :, 2] = r, g, b
    return FakeImage(array)


def test_a_frame_is_a_header_then_one_full_buffer():
    device = FakeUsb()
    Push2Display(device).draw_image(solid(0, 0, 0))
    assert len(device.writes) == 2

    endpoint, header = device.writes[0]
    assert endpoint == ENDPOINT
    assert header == FRAME_HEADER
    assert len(header) == 16

    endpoint, payload = device.writes[1]
    assert endpoint == ENDPOINT
    # 160 lines of 1024 pixels at 16 bits, including the off-screen padding.
    assert len(payload) == HEIGHT * LINE_PIXELS * 2 == 327_680


def test_pixels_are_bgr565_with_the_shaping_pattern_applied():
    device = FakeUsb()
    Push2Display(device).draw_image(solid(255, 0, 0))  # pure red
    payload = device.writes[1][1]
    words = np.frombuffer(payload, dtype="<u2")

    # Red is five bits at the bottom of a BGR565 word.
    expected_pixel = 0x1F
    # Against the literal mask, NOT against the constant under test.  Comparing
    # `XOR_PATTERN` to `XOR_PATTERN` is a tautology, and it is how a transposed
    # first word shipped: every assertion here passed while the panel showed a
    # gold background and blue text (`F-08` finding 9).
    assert words[0] == expected_pixel ^ 0xF3E7
    assert words[1] == expected_pixel ^ 0xFFE7
    # The pattern alternates per 16-bit word, making a 0xFFE7F3E7 32-bit mask.
    assert words[2] == words[0]


def test_the_shaping_mask_is_the_documented_thirty_two_bit_value():
    """The bug the tautology hid, pinned against the number itself.

    The two words are the little-endian halves of 0xFFE7F3E7.  Stated as bytes
    as well, because the failure was a byte transposition and a hex literal is
    exactly where the eye slides over one.
    """
    assert XOR_MASK32 == 0xFFE7F3E7
    assert int(XOR_PATTERN[0]) == 0xF3E7
    assert int(XOR_PATTERN[1]) == 0xFFE7
    assert XOR_PATTERN.tobytes() == bytes((0xE7, 0xF3, 0xE7, 0xFF))


def test_shaping_a_black_frame_twice_gives_black_back():
    """The property the panel actually relies on, and the one that broke.

    The display XORs with the same mask on the way in, so shaping has to be its
    own inverse.  Black is the strongest case: 0x0000 means every channel is
    zero, so a channel-order mistake cannot show up here and only the mask can.
    """
    device = FakeUsb()
    Push2Display(device).draw_image(solid(0, 0, 0))
    words = np.frombuffer(device.writes[1][1], dtype="<u2").copy()
    mask = np.tile(np.array([0xF3E7, 0xFFE7], dtype=np.uint16), words.size // 2)
    assert not (words ^ mask).any()


def test_each_colour_lands_in_its_own_bits():
    for rgb, pixel in (
        ((255, 0, 0), 0x1F),  # r: bits 0-4
        ((0, 255, 0), 0x3F << 5),  # g: bits 5-10
        ((0, 0, 255), 0x1F << 11),  # b: bits 11-15
        ((255, 255, 255), 0xFFFF),
    ):
        device = FakeUsb()
        Push2Display(device).draw_image(solid(*rgb))
        words = np.frombuffer(device.writes[1][1], dtype="<u2")
        assert words[0] == pixel ^ 0xF3E7, rgb


def test_the_invisible_tail_of_each_line_is_still_sent():
    device = FakeUsb()
    Push2Display(device).draw_image(solid(255, 255, 255))
    words = np.frombuffer(device.writes[1][1], dtype="<u2").reshape(HEIGHT, LINE_PIXELS)
    literal = (0xF3E7, 0xFFE7)
    assert words[0, WIDTH - 1] == 0xFFFF ^ literal[(WIDTH - 1) % 2]
    # Past 960 pixels the line is padding: black, but shaped like everything else.
    assert words[0, WIDTH] == literal[WIDTH % 2]


def test_open_display_is_absent_safe():
    # No pyusb and no device in this environment: None, never an exception.
    assert open_display() is None


def test_close_is_safe_without_pyusb():
    Push2Display(FakeUsb()).close()  # must not raise


def test_draw_needs_pillow_and_says_so():
    with pytest.raises(ImportError):
        Push2Display(FakeUsb()).draw(["hello"])


#: Width of one character in the monospace stand-in `_draw` measures with.
CHAR_PX = 10


# ============================== CC-20: the mode banner on the big display
def _draw(display, *args, **kwargs):
    """Call ``display.draw`` with a stand-in for PIL, recording the text.

    Pillow is optional and not installed in CI, and what these tests are about
    is *where each region lands*, not how PIL rasterises it.
    """
    import sys
    import types

    placed: list[tuple[int, str]] = []

    class Recorder:
        def text(self, xy, text, fill=None, font=None):
            placed.append((xy[1], text))

        def textlength(self, text, font=None):
            # A monospace stand-in.  ``draw`` only asks "how wide is this", and
            # the answer it needs from a test is a predictable one.
            return len(text) * CHAR_PX

    fake = types.ModuleType("PIL")
    fake.Image = types.SimpleNamespace(new=lambda mode, size, colour: object())
    fake.ImageDraw = types.SimpleNamespace(Draw=lambda image: Recorder())
    saved = sys.modules.get("PIL")
    sys.modules["PIL"] = fake
    try:
        display.draw(*args, **kwargs)
    finally:
        if saved is None:
            del sys.modules["PIL"]
        else:
            sys.modules["PIL"] = saved
    return placed


def _display():
    from push2sampler.display import Push2Display

    display = Push2Display(FakeUsb())
    display.draw_image = lambda image: None
    return display


def test_the_banner_is_drawn_above_the_text_and_costs_one_line():
    """160 px is the real constraint, so each big region costs a text line."""
    from push2sampler.display import BANNER_HEIGHT

    placed = _draw(_display(), ["one", "two", "three", "four", "five"],
                   readout="BAR 3", banner="SLOT 7")
    texts = [text for _y, text in placed]

    assert texts[0] == "SLOT 7"                    # banner first, at the top
    assert "BAR 3" in texts                        # readout still drawn
    # Banner and readout each take a line, so three of five fit between them.
    assert texts[1:4] == ["one", "two", "three"]
    assert "four" not in texts
    assert placed[0][0] < placed[1][0]             # banner above the text
    assert placed[1][0] >= BANNER_HEIGHT


def test_without_a_banner_five_lines_still_fit():
    placed = _draw(_display(), ["a", "b", "c", "d", "e"])
    assert [text for _y, text in placed] == ["a", "b", "c", "d", "e"]


def test_draw_still_works_with_only_lines():
    """Anything holding a display keeps working without the new arguments."""
    placed = _draw(_display(), ["just lines"])
    assert [text for _y, text in placed] == ["just lines"]


def test_at_least_one_text_line_survives_both_regions():
    """Banner plus readout must not squeeze the text out entirely."""
    placed = _draw(_display(), ["only one"], readout="BAR 1", banner="SETUP")
    assert "only one" in [text for _y, text in placed]


def test_the_banner_state_picks_a_colour():
    from push2sampler.display import BANNER_COLORS

    assert BANNER_COLORS["recording"] != BANNER_COLORS["normal"]
    assert BANNER_COLORS["armed"] != BANNER_COLORS["normal"]
    assert BANNER_COLORS.get("nonsense", BANNER_COLORS["normal"]) \
        == BANNER_COLORS["normal"]


# ============================== F-08 finding 10: text that runs off the edge
#
# A photograph of a real Push 2 showed `0 muted`, `song page  0` and
# `hold: audit` all cut mid-word at the right-hand edge.  Nothing measured
# anything, so nothing could have stopped it.  `fit` takes the measurer as an
# argument precisely so this section can exist without Pillow.
def _ten_px_per_char(text):
    return len(text) * 10


def test_text_that_fits_is_left_exactly_alone():
    assert fit("short", _ten_px_per_char, limit=100) == "short"
    # Exactly on the limit still fits: the edge pixel is the last usable one.
    assert fit("0123456789", _ten_px_per_char, limit=100) == "0123456789"


def test_text_that_does_not_fit_comes_back_shortened_and_marked():
    fitted = fit("0123456789abc", _ten_px_per_char, limit=100)
    assert fitted.endswith(ELLIPSIS)
    assert _ten_px_per_char(fitted) <= 100
    # The ellipsis costs a character's width, so nine of the thirteen survive.
    assert fitted == "012345678" + ELLIPSIS


def test_the_longest_prefix_that_fits_is_the_one_chosen():
    """Not merely *a* fitting prefix -- the longest, or it throws away text."""
    for length in range(1, 40):
        fitted = fit("x" * length, _ten_px_per_char, limit=100)
        assert _ten_px_per_char(fitted) <= 100, length
        if len(fitted) < length:
            assert _ten_px_per_char(fitted + "x") > 100, length


def test_a_limit_with_no_room_at_all_gives_back_just_the_ellipsis():
    """Better one character saying "there was more" than a silent blank."""
    assert fit("anything", _ten_px_per_char, limit=5) == ELLIPSIS
    assert fit("anything", _ten_px_per_char, limit=0) == ELLIPSIS


def test_empty_text_stays_empty():
    assert fit("", _ten_px_per_char, limit=0) == ""


def test_the_default_limit_is_the_visible_width_less_both_insets():
    """Text starts at TEXT_X, so it has to stop TEXT_X before the far edge."""
    from push2sampler.display import TEXT_X

    limit = WIDTH - TEXT_X * 2
    assert limit == 936
    # 93 characters fit in 936 px and 94 do not, so 92 plus the ellipsis is it.
    assert fit("x" * 500, _ten_px_per_char) == "x" * 92 + ELLIPSIS
    assert _ten_px_per_char("x" * 93) <= limit < _ten_px_per_char("x" * 94)


def test_every_region_drawn_is_measured_and_shortened():
    """The banner, the lines and the readout -- the photo clipped all three."""
    from push2sampler.display import TEXT_X

    long = "word " * 60
    placed = _draw(_display(), [long, long], readout=long, banner=long)
    assert placed, "nothing was drawn"
    for _y, text in placed:
        assert text.endswith(ELLIPSIS), text
        assert len(text) * CHAR_PX <= WIDTH - TEXT_X * 2, text


def test_short_regions_are_drawn_unchanged():
    placed = _draw(_display(), ["a line"], readout="BAR 3", banner="SLOT 7")
    assert [text for _y, text in placed] == ["SLOT 7", "a line", "BAR 3"]
