"""The Push 2 colour display, checked byte by byte against a fake USB device.

The display is the one part of the protocol with no forgiveness: a wrong frame
header or the wrong pixel packing shows as garbage rather than an error, and no
machine here has the device to try it on.  So the framing is pinned here, and
`--selftest` asks a human to confirm the result on real glass.
"""

import numpy as np
import pytest

from push2sampler.display import (
    ENDPOINT,
    FRAME_HEADER,
    HEIGHT,
    LINE_PIXELS,
    WIDTH,
    XOR_PATTERN,
    Push2Display,
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
    assert words[0] == expected_pixel ^ XOR_PATTERN[0]
    assert words[1] == expected_pixel ^ XOR_PATTERN[1]
    # The pattern alternates per 16-bit word, making a 0xFFE7F3E7 32-bit mask.
    assert words[2] == words[0]


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
        assert words[0] == pixel ^ XOR_PATTERN[0], rgb


def test_the_invisible_tail_of_each_line_is_still_sent():
    device = FakeUsb()
    Push2Display(device).draw_image(solid(255, 255, 255))
    words = np.frombuffer(device.writes[1][1], dtype="<u2").reshape(HEIGHT, LINE_PIXELS)
    assert words[0, WIDTH - 1] == 0xFFFF ^ XOR_PATTERN[(WIDTH - 1) % 2]
    # Past 960 pixels the line is padding: black, but shaped like everything else.
    assert words[0, WIDTH] == XOR_PATTERN[WIDTH % 2]


def test_open_display_is_absent_safe():
    # No pyusb and no device in this environment: None, never an exception.
    assert open_display() is None


def test_close_is_safe_without_pyusb():
    Push2Display(FakeUsb()).close()  # must not raise


def test_draw_needs_pillow_and_says_so():
    with pytest.raises(ImportError):
        Push2Display(FakeUsb()).draw(["hello"])
