"""The public feature page, and the claim it makes about itself.

The page's footer says its codes, titles, sizes and releases are read from
`plans.md`, "so this page cannot drift from it". For two releases that was
false: the numbers were transcribed by hand, and the page said 45 items shipped
when the real number was 47. A claim a document makes about itself has to be
enforced by something. This is the something.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import feature_page  # noqa: E402


@pytest.fixture(scope="module")
def parsed():
    return feature_page.read_plan()


@pytest.fixture(scope="module")
def page():
    return feature_page.build(tests=1234, version="9.9.9")


# ==================================================== the plan is the source
def test_every_plan_item_is_on_the_page(parsed):
    """The count in the headline is the plan's count, whatever it becomes."""
    _trains, items = parsed
    plan = (ROOT / "plans.md").read_text()
    codes = set(re.findall(r"^### ([A-Z]+-\d+) — ", plan, re.M))
    assert {item.code for item in items} == codes


def test_every_item_appears_exactly_once(parsed):
    """An item in two releases would be two pads claiming one feature."""
    _trains, items = parsed
    codes = [item.code for item in items]
    assert len(codes) == len(set(codes))


def test_the_items_fit_on_a_grid_of_pads(parsed):
    """The layout is the instrument's, so the plan cannot outgrow it silently."""
    _trains, items = parsed
    assert len(items) <= feature_page.PADS


def test_every_item_has_a_blurb(parsed):
    """The one thing on the page the plan does not provide.

    So it is the one thing that can go missing, and the reason this test is the
    point of the file rather than an afterthought.
    """
    _trains, items = parsed
    missing = [item.code for item in items if item.code not in feature_page.BLURBS]
    assert missing == []


def test_no_blurb_is_left_over(parsed):
    """A blurb for an item that no longer exists is a stale sentence."""
    _trains, items = parsed
    codes = {item.code for item in items}
    assert [code for code in feature_page.BLURBS if code not in codes] == []


def test_titles_and_sizes_come_from_the_item_headings(parsed):
    _trains, items = parsed
    plan = (ROOT / "plans.md").read_text()
    for item in items:
        heading = re.search(
            rf"^### {re.escape(item.code)} — (.+?) `size: ([SML])`$", plan, re.M
        )
        assert heading, item.code
        assert item.size == heading.group(2)
        assert item.title == feature_page._plain(heading.group(1))


def test_a_struck_item_is_shipped_and_an_unstruck_one_is_not():
    """The roadmap table's strikethrough is the whole shipped/open signal.

    Tested against a table written here rather than against the real one, which
    a spot-check twice outlived: the codes it named kept shipping.  The
    *mechanism* is what has to hold, whatever the plan currently says.
    """
    plan = (
        "| Release | Theme | Contents |\n"
        "| --- | --- | --- |\n"
        "| ~~**v9.1 — Done**~~ | all finished | **complete** — ~~`ZZ-01`~~ |\n"
        "| **v9.2 — Doing** ← in progress | some of it | ~~`ZZ-02`~~† `ZZ-03` |\n"
        "\n"
        "### ZZ-01 — First `size: S`\n\n"
        "### ZZ-02 — Second `size: M`\n\n"
        "### ZZ-03 — Third `size: L`\n"
    )
    trains = feature_page.read_trains(plan)
    assert [train.version for train in trains] == ["v9.1", "v9.2"]
    assert [train.complete for train in trains] == [True, False]
    assert dict(trains[0].codes) == {"ZZ-01": True}
    # The dagger is a footnote marker, not part of a code.
    assert dict(trains[1].codes) == {"ZZ-02": True, "ZZ-03": False}
    titles = feature_page.read_titles(plan)
    assert titles == {"ZZ-01": ("First", "S"), "ZZ-02": ("Second", "M"),
                      "ZZ-03": ("Third", "L")}


def test_the_real_table_agrees_with_itself(parsed):
    """Whatever the plan says today, it has to say it consistently."""
    _trains, items = parsed
    for item in items:
        assert (item.state == "shipped") is item.shipped, item.code


def test_the_nearest_open_release_is_the_one_being_built(parsed):
    """`**complete**` in the table is what marks a release done.

    With every release complete -- which is now the case -- there is nothing to
    colour as "building now", and the page has to be able to say that rather
    than claiming a release is both finished and in progress.
    """
    trains, items = parsed
    open_trains = [train for train in trains if not train.complete]
    if not open_trains:
        assert all(item.shipped for item in items)
        return
    building = open_trains[0].version
    assert all(
        item.state == "now"
        for item in items
        if item.train == building and not item.shipped
    )


def test_the_page_says_complete_when_everything_is(page):
    """The stale-string bug a test caught: "v2.0 complete, v2.0 in progress"."""
    facts = re.search(r'<p class="facts">(.*?)</p>', page, re.S).group(1)
    assert "in progress" not in facts or "complete," in facts


def test_a_daggered_code_still_parses(parsed):
    """Several table entries carry a † footnote marker; it is not part of a code."""
    _trains, items = parsed
    codes = {item.code for item in items}
    assert "NH-10" in codes            # written `~~`NH-10`~~†` in the table
    assert not any("†" in item.code for item in items)


def test_the_release_theme_survives_the_markdown(parsed):
    trains, _items = parsed
    assert trains[0].name == "Trustworthy"
    assert trains[0].theme == "it never bites you"
    # "← in progress" is a note to a reader of the plan, not part of a name.
    assert all("←" not in train.version for train in trains)
    assert all("in progress" not in train.name for train in trains)


# ==================================================== the newest item
def test_the_page_opens_on_the_most_recently_shipped_item(parsed):
    """From the changelog, because the roadmap table has no sense of time."""
    _trains, items = parsed
    newest = feature_page.newest_code(items)
    assert newest in {item.code for item in items if item.shipped}


def test_the_newest_item_falls_back_when_there_is_no_changelog(parsed, tmp_path):
    _trains, items = parsed
    code = feature_page.newest_code(items, path=tmp_path / "nothing.md")
    assert code in {item.code for item in items if item.shipped}


# ==================================================== the rendered page
def test_the_page_states_the_plan_s_own_counts(page, parsed):
    _trains, items = parsed
    shipped = sum(1 for item in items if item.shipped)
    facts = re.search(r'<p class="facts">(.*?)</p>', page, re.S).group(1)
    assert f"<b>{shipped}</b> shipped" in facts
    assert f"<b>{len(items) - shipped}</b> planned" in facts
    assert "<b>1,234</b> tests passing" in facts


def test_each_release_counts_its_own_items(page, parsed):
    trains, items = parsed
    for train in trains:
        mine = [item for item in items if item.train == train.version]
        done = sum(1 for item in mine if item.shipped)
        assert f"<b>{done}</b> of {len(mine)} shipped" in page


def test_every_item_is_a_row_and_a_pad(page, parsed):
    _trains, items = parsed
    for item in items:
        assert f'<span class="code">{item.code}</span>' in page
        assert f'"code": "{item.code}"' in page or f'"code":"{item.code}"' in page


def test_the_blank_pads_are_counted_honestly(page, parsed):
    _trains, items = parsed
    blank = feature_page.PADS - len(items)
    assert f"{len(items)} features &#183; {feature_page.PADS} pads" in page
    assert f"{blank} blank" in page


def test_the_page_needs_no_doctype_or_body(page):
    """The artifact host wraps it, so those tags would be duplicated."""
    lowered = page.lower()
    assert "<!doctype" not in lowered
    assert "<html" not in lowered
    assert "<body" not in lowered


def test_the_title_is_first_so_the_host_finds_it(page):
    assert page.lstrip().startswith("<title>")


def test_the_page_carries_a_light_and_a_dark_palette(page):
    """Every colour token defined on bare :root, then redefined for dark."""
    assert page.count("--shipped:") >= 3        # light, media query, data-theme
    assert 'prefers-color-scheme: dark' in page
    assert ':root[data-theme="dark"]' in page


def test_the_javascript_braces_survived_the_format_call(page):
    """`str.format` on a template full of JS is exactly how this breaks."""
    assert "{{" not in page and "}}" not in page
    assert "const ITEMS = [" in page
    assert page.count("{") == page.count("}")


def test_the_only_external_resources_are_allowed_fonts(page):
    """The artifact CSP blocks everything else, silently."""
    hosts = set(re.findall(r'(?:src|href)="https://([^/"]+)', page))
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}


def test_a_title_with_markup_in_it_is_escaped(monkeypatch):
    """Titles come from the plan, which is prose, so `<` and `&` must escape."""
    item = feature_page.Item(
        code="ZZ-99", title="Trim & <slice> a take", size="S",
        train="v9.9", shipped=False, state="later", pad=7,
    )
    monkeypatch.setitem(feature_page.BLURBS, "ZZ-99", "Fictional, for this test.")
    row = feature_page._item_row(item)
    assert "Trim &amp; &lt;slice&gt; a take" in row
    assert "<slice>" not in row


def test_the_page_does_not_double_escape_its_own_entities(page):
    """The template's own &#8212; must survive as an entity, not as text."""
    assert "&amp;#8212;" not in page
    assert "&#8212;" in page


def test_the_footer_claim_names_the_generator(page):
    """If the page says it is generated, it has to say by what."""
    assert "tools/feature_page.py" in page
    assert "plans.md" in page


def test_the_hardware_caveat_is_still_there(page):
    """The most load-bearing paragraph on the page; it must not get trimmed."""
    assert "Push 2 MIDI and Display Interface" in page
    assert "never been seen to render" in page


def test_building_with_a_missing_blurb_refuses(monkeypatch, parsed):
    """A new plan item must not reach the page as a blank line."""
    _trains, items = parsed
    thinned = dict(feature_page.BLURBS)
    thinned.pop(items[0].code)
    monkeypatch.setattr(feature_page, "BLURBS", thinned)
    with pytest.raises(SystemExit) as raised:
        feature_page.build(tests=1, version="0")
    assert items[0].code in str(raised.value)
