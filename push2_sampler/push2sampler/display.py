"""Optional Push 2 colour display (960x160).

The display is not a MIDI device: frames are pushed to USB bulk endpoint 0x01
as 160 lines of 1024 pixels, 16 bits per pixel (BGR565, little endian), each
32-bit word XOR-ed with the signal-shaping pattern 0xFFE7F3E7 and preceded by a
16-byte frame header.  Only the leftmost 960 pixels of each line are visible.

Both ``pyusb`` and ``Pillow`` are required; if either is missing (or the USB
interface is claimed by Ableton Live) :func:`open_display` returns ``None`` and
the program simply runs without a display.
"""

from __future__ import annotations

import numpy as np

from .constants import USB_PRODUCT_ID, USB_VENDOR_ID

WIDTH = 960
HEIGHT = 160
LINE_PIXELS = 1024
FRAME_HEADER = bytes(
    (0xFF, 0xCC, 0xAA, 0x88, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)
)
XOR_PATTERN = np.array([0xE7F3, 0xFFE7], dtype=np.uint16)
ENDPOINT = 0x01
#: Space reserved at the bottom for the big transport readout.
BIG_LINE_HEIGHT = 44
#: Space reserved at the top for the mode banner (CC-20).
BANNER_HEIGHT = 34
#: Banner colours: recording, armed for something destructive, otherwise.
BANNER_COLORS = {
    "recording": (255, 90, 80),
    "armed": (255, 190, 90),
    "normal": (255, 255, 255),
}


class Push2Display:
    def __init__(self, device, font=None, big_font=None, banner_font=None) -> None:
        self._device = device
        self._font = font
        self._big_font = big_font or font
        self._banner_font = banner_font or font
        self._buffer = np.zeros((HEIGHT, LINE_PIXELS), dtype=np.uint16)

    # ------------------------------------------------------------------
    def draw(self, lines: list[str], readout: str | None = None,
             banner: str | None = None, banner_state: str = "normal") -> None:
        """Render the text lines, with a banner on top and a readout below.

        Three regions, each answering a different question.  The banner says
        *where you are*, the big bottom line says *where the music is*, and the
        text between them says what this page does.  Both extras are optional,
        so anything holding a display can still hand over plain lines.

        Vertical space is the real constraint -- 160 px -- so each extra costs
        one text line.
        """
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        y = 6
        room = 5
        if banner:
            draw.text((12, y), banner,
                      fill=BANNER_COLORS.get(banner_state, BANNER_COLORS["normal"]),
                      font=self._banner_font)
            y += BANNER_HEIGHT
            room -= 1
        if readout:
            room -= 1
        for i, text in enumerate(lines[:max(1, room)]):
            fill = (230, 230, 230) if i == 0 and not banner else (170, 170, 170)
            draw.text((12, y), text, fill=fill, font=self._font)
            y += 30 if (i == 0 and not banner) else 26
        if readout:
            draw.text((12, HEIGHT - BIG_LINE_HEIGHT), readout,
                      fill=(255, 210, 120), font=self._big_font)
        self.draw_image(image)

    def draw_image(self, image) -> None:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint16)
        r = (rgb[:, :, 0] >> 3) & 0x1F
        g = (rgb[:, :, 1] >> 2) & 0x3F
        b = (rgb[:, :, 2] >> 3) & 0x1F
        self._buffer[:, :WIDTH] = (b << 11) | (g << 5) | r
        shaped = self._buffer ^ np.tile(XOR_PATTERN, LINE_PIXELS // 2)
        self._device.write(ENDPOINT, FRAME_HEADER, 1000)
        self._device.write(ENDPOINT, shaped.tobytes(), 1000)

    def close(self) -> None:
        try:
            import usb.util

            usb.util.dispose_resources(self._device)
        except Exception:  # pragma: no cover - best effort
            pass


def open_display(font_size: int = 22, big_font_size: int = 38,
                 banner_font_size: int = 30):
    """Return a :class:`Push2Display`, or ``None`` if it is unavailable."""
    try:
        import usb.core
        from PIL import ImageFont
    except Exception:
        return None
    try:
        device = usb.core.find(idVendor=USB_VENDOR_ID, idProduct=USB_PRODUCT_ID)
        if device is None:
            return None
        device.set_configuration()
    except Exception:
        return None
    font, big_font, banner_font = _fonts(
        ImageFont, font_size, big_font_size, banner_font_size
    )
    return Push2Display(device, font, big_font, banner_font)


#: Where a bold system font tends to live, per platform.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _fonts(ImageFont, size: int, big_size: int, banner_size: int = 30):
    """A text font, a larger one for the readout, and one for the banner.

    Falls back to the bitmap default, which cannot be scaled -- so on a machine
    with no usable TrueType font the big lines are merely the same size as the
    rest, rather than absent.
    """
    for candidate in FONT_CANDIDATES:
        try:
            return (ImageFont.truetype(candidate, size),
                    ImageFont.truetype(candidate, big_size),
                    ImageFont.truetype(candidate, banner_size))
        except Exception:
            continue
    try:
        default = ImageFont.load_default()
    except Exception:
        return None, None, None
    return default, default, default
