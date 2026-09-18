"""The run sheet: every feature, and the buttons that show it working.

Same bargain as `test_feature_page.py`. The page is generated from `plans.md`,
so what these tests are for is the half the plan *cannot* supply -- the button
recipes -- and the ways a hand-written page quietly goes stale: a feature
shipped with no way to see it, a recipe left behind for an item that no longer
exists, a step naming a button the program does not have.

That last one is the interesting test. A run sheet whose presses are wrong is
worse than no run sheet, because the reader blames the instrument.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import demo_page  # noqa: E402
from feature_page import read_plan  # noqa: E402

from push2sampler.constants import BUTTON_NAMES  # noqa: E402


@pytest.fixture(scope="module")
def parsed():
    return read_plan()


@pytest.fixture(scope="module")
def page():
    return demo_page.build("9.9.9")


# ===================================================== nothing is missed
def test_every_shipped_feature_has_a_recipe(parsed):
    """The whole point of generating it from the plan.

    A feature with no way to see it is a feature nobody will find.
    """
    _trains, items = parsed
    assert not demo_page.check(items)


def test_a_new_plan_item_refuses_to_build(monkeypatch, parsed):
    _trains, items = parsed
    thinned = dict(demo_page.RECIPES)
    thinned.pop(items[0].code)
    monkeypatch.setattr(demo_page, "RECIPES", thinned)
    with pytest.raises(SystemExit) as raised:
        demo_page.build("0")
    assert items[0].code in str(raised.value)


def test_a_recipe_for_a_removed_item_refuses_to_build(monkeypatch, parsed):
    """The other direction, which is the one that rots silently."""
    extra = dict(demo_page.RECIPES)
    extra["ZZ-99"] = ("library", (("press", "Play", ""),), "nothing")
    monkeypatch.setattr(demo_page, "RECIPES", extra)
    with pytest.raises(SystemExit) as raised:
        demo_page.build("0")
    assert "ZZ-99" in str(raised.value)


def test_a_recipe_in_a_group_that_does_not_exist_refuses(monkeypatch, parsed):
    _trains, items = parsed
    broken = dict(demo_page.RECIPES)
    broken[items[0].code] = ("nowhere", (), "x")
    monkeypatch.setattr(demo_page, "RECIPES", broken)
    with pytest.raises(SystemExit) as raised:
        demo_page.build("0")
    assert "nowhere" in str(raised.value)


# ===================================================== the recipes themselves
def test_every_recipe_says_what_you_should_see():
    """A step list with no outcome cannot be checked by the person doing it."""
    for code, (_group, _steps, proof) in demo_page.RECIPES.items():
        assert proof.strip(), code
        assert len(proof) > 40, f"{code}: {proof!r} is too thin to be useful"


def test_every_recipe_has_steps_except_the_one_that_cannot():
    """`F-02` is a refactor; everything else is something you can do."""
    stepless = [c for c, (_g, steps, _p) in demo_page.RECIPES.items() if not steps]
    assert stepless == ["F-02"]


def test_every_step_kind_is_one_the_page_can_render():
    for code, (_group, steps, _proof) in demo_page.RECIPES.items():
        for kind, _what, _why in steps:
            assert kind in demo_page.KIND_LABEL, f"{code}: {kind}"


def test_every_named_button_is_a_button_the_program_has():
    """The test worth having: a run sheet whose presses are wrong is worse than
    none, because the reader blames the instrument.

    Only the named hardware buttons are checkable -- `button 1 below the
    display` is positional and `encoder 3` is a knob -- so those are skipped by
    shape rather than by a list of exceptions that would itself go stale.
    """
    known = {name.replace("_", " ").lower() for name in BUTTON_NAMES.values()}
    known |= {"page ◀", "page ▶", "up", "down", "left", "right", "shift"}
    positional = re.compile(r"^(button|encoder|the |a |any |hold |i?f )", re.I)

    unknown = []
    for code, (_group, steps, _proof) in demo_page.RECIPES.items():
        for kind, what, _why in steps:
            if kind != "press":
                continue
            for part in re.split(r"[+/]", what):
                part = part.strip()
                if positional.match(part) or not part[:1].isupper():
                    continue
                if part.lower().replace("_", " ") not in known:
                    unknown.append(f"{code}: {part!r}")
    assert not unknown, "not buttons this program binds: " + ", ".join(unknown)


def test_the_terminal_steps_are_real_command_lines():
    for code, (_group, steps, _proof) in demo_page.RECIPES.items():
        for kind, what, _why in steps:
            if kind == "type":
                assert what.startswith(("python -m push2sampler", "p ", "record",
                                        "wait ")), f"{code}: {what!r}"


# ===================================================== the page
def test_every_feature_reaches_the_page(page, parsed):
    _trains, items = parsed
    for item in items:
        assert item.code in page, item.code
        assert item.title.replace("×", "&#215;") in page or item.title in page, item.title


def test_each_place_says_how_to_get_there(page):
    for _key, title, how, _blurb in demo_page.GROUPS:
        assert title in page
        assert how in page


def test_a_chord_becomes_two_keycaps(page):
    """`Shift`+`Record` is two physical keys and has to look like two."""
    rendered = demo_page._keys("Shift+Record")
    assert rendered.count("<kbd>") == 2
    assert "Shift" in rendered and "Record" in rendered


def test_a_positional_button_stays_prose_not_a_keycap():
    """There is nothing engraved `button 1`, so a keycap would be a lie."""
    rendered = demo_page._keys("the tempo encoder")
    assert "<kbd>" not in rendered


def test_an_alternation_is_not_rendered_as_a_chord():
    """`+` means both at once and `/` means either one.

    One keycap reading `Up / Down` invents a button that does not exist, which
    is exactly the failure this file is here to prevent.
    """
    rendered = demo_page._keys("Up / Down")
    assert rendered.count("<kbd>") == 2
    assert "or" in rendered
    assert "<span class=\"plus\">" not in rendered


def test_the_page_does_not_double_escape_its_own_entities(page):
    assert "&amp;#" not in page
    assert "&amp;lt;" not in page


def test_the_page_is_theme_aware(page):
    """Tokens in bare :root, then redefined for both dark routes."""
    assert "@media (prefers-color-scheme: dark)" in page
    assert ':root:not([data-theme="light"])' in page
    assert ':root[data-theme="dark"]' in page
    # Every token used must exist in the bare :root block, or it is undefined
    # in the un-stamped light state -- the classic unreadable-artifact bug.
    root = page.split("@media (prefers-color-scheme: dark)")[0]
    for token in sorted(set(re.findall(r"var\((--[a-z0-9-]+)\)", page))):
        assert f"{token}:" in root, f"{token} is never defined for light"


def test_the_only_external_resources_are_allowed_fonts(page):
    for url in re.findall(r'https?://[^"\')\s]+', page):
        if url.startswith("http://localhost"):
            continue  # the monitor page's own address, as content
        assert url.startswith(("https://fonts.googleapis.com",
                               "https://fonts.gstatic.com")), url


def test_the_javascript_braces_survived_the_format_call(page):
    """The template is one big str.format, so a lone brace is a live grenade."""
    assert "entry.hidden = !hit;" in page
    assert "{{" not in page and "}}" not in page


def test_the_filter_starts_empty_so_the_page_is_whole_at_rest(page):
    assert 'id="find"' in page
    assert 'value=' not in page.split('id="find"')[1].split(">")[0]


def test_the_footer_explains_the_two_button_rows(page):
    """`button 1` and `encoder 1` are positional, and a reader needs telling."""
    assert "below</i>\n      the display" in page or "below" in page
    assert "encoder 1" in page


def test_the_primer_gets_you_a_sample_to_work_on(page):
    """Every recipe assumes a recorded take; the page has to say how."""
    assert "one recorded sample" in page
    assert "top-left pad" in page
