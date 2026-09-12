from push2sampler.constants import (
    PAD_COUNT,
    index_to_note,
    index_to_xy,
    note_to_index,
    xy_to_index,
    encoder_delta,
)

import pytest


def test_top_left_is_index_zero():
    assert index_to_xy(0) == (0, 0)
    # Note 36 is the bottom-left pad, so the top-left pad is 36 + 7*8.
    assert index_to_note(0) == 92
    assert note_to_index(92) == 0


def test_corners():
    assert index_to_note(7) == 99  # top right
    assert index_to_note(56) == 36  # bottom left
    assert index_to_note(63) == 43  # bottom right


def test_note_index_round_trip():
    for index in range(PAD_COUNT):
        assert note_to_index(index_to_note(index)) == index
    for note in range(36, 100):
        assert index_to_note(note_to_index(note)) == note


def test_xy_round_trip():
    for index in range(PAD_COUNT):
        col, row = index_to_xy(index)
        assert xy_to_index(col, row) == index


def test_rejects_out_of_range():
    with pytest.raises(ValueError):
        note_to_index(35)
    with pytest.raises(ValueError):
        index_to_xy(64)
    with pytest.raises(ValueError):
        xy_to_index(8, 0)


def test_encoder_delta_is_signed():
    assert encoder_delta(1) == 1
    assert encoder_delta(63) == 63
    assert encoder_delta(127) == -1
    assert encoder_delta(126) == -2
