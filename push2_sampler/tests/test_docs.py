"""The docs are part of the product, so their links are testable.

This exists because of a real bug rather than a policy: the tutorial had two
`Step 11b`s and two `Step 11c`s from being extended four times, and renumbering
it broke a `[step 12](#step-12-the-settings-worth-knowing)` link that no longer
pointed at anything.  Nobody notices a dead in-page anchor until they click it,
which is exactly the kind of thing a test is for.

It checks structure, not prose: every internal link resolves, every heading is
unique enough to link to, and the numbered tutorial is numbered once each.  It
deliberately does *not* check claims about behaviour -- those belong in the
tests for the behaviour, next to the code that has to keep them true.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent
MARKDOWN = sorted(
    [DOCS / "README.md", DOCS / "CHANGELOG.md", DOCS / "plans.md"]
    + sorted((DOCS / "docs").glob("*.md"))
)

#: `[text](target)`, with the target captured.  Good enough for our own files:
#: none of them contain a link with a nested bracket or a title string.
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
#: ATX headings only; none of these files use the underline style.
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$", re.MULTILINE)


def slug(heading: str) -> str:
    """GitHub's anchor rules, near enough for the subset we write.

    Lowercase, strip anything that is not a word character, a space or a
    hyphen, then spaces to hyphens.  Markdown emphasis and inline code are
    removed first because we write plenty of both in headings.

    **Each space becomes its own hyphen**, and runs are not collapsed -- that
    is what github-slugger does, and it is why a heading with an em dash in it
    (`Clock -- playing with other gear`) anchors as `clock--playing-...`: the
    dash is removed and the two spaces around it are left behind.  Collapsing
    them here would have this test disagree with GitHub and call a working
    link dead.
    """
    text = re.sub(r"`|\*\*|\*|~~|_", "", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links in headings
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text.strip())


#: An explicit `<a id="x">` (or `name="x"`) target.  The tutorial uses these for
#: the handful of steps it links to internally: a heading's own slug carries its
#: step number, so inserting a step silently breaks every link into the ones
#: after it -- which is exactly the bug that started this file.
EXPLICIT = re.compile(r"""<a\s+(?:id|name)=["\']([^"\']+)["\']""")


def anchors(path: Path) -> set[str]:
    text = path.read_text()
    return ({slug(m.group(2)) for m in HEADING.finditer(text)}
            | {m.group(1) for m in EXPLICIT.finditer(text)})


def links(path: Path) -> list[str]:
    return [m.group(1) for m in LINK.finditer(path.read_text())]


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_every_in_page_anchor_resolves(path):
    """`#foo` has to name a heading in the same file."""
    available = anchors(path)
    broken = [
        target for target in links(path)
        if target.startswith("#") and target[1:] not in available
    ]
    assert not broken, f"{path.name}: dead anchors {broken}"


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_every_link_to_another_file_resolves(path):
    """A relative link has to name a file that exists, and its anchor too."""
    broken = []
    for target in links(path):
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        file_part, _, anchor = target.partition("#")
        destination = (path.parent / file_part).resolve()
        if not destination.exists():
            broken.append(target)
        elif anchor and destination.suffix == ".md" and anchor not in anchors(destination):
            broken.append(target)
    assert not broken, f"{path.name}: dead links {broken}"


def test_the_tutorial_numbers_each_step_once():
    """Two `Step 11b`s is how the dead anchor got there in the first place."""
    text = (DOCS / "docs" / "getting-started.md").read_text()
    numbers = re.findall(r"^### Step (\S+):", text, re.MULTILINE)
    assert numbers, "no steps found -- has the heading style changed?"
    assert len(numbers) == len(set(numbers)), (
        f"repeated step numbers: "
        f"{sorted({n for n in numbers if numbers.count(n) > 1})}"
    )


def test_the_tutorial_steps_run_in_order():
    """Plain integers, one after another: no suffixes to collide."""
    text = (DOCS / "docs" / "getting-started.md").read_text()
    numbers = [int(n) for n in re.findall(r"^### Step (\d+):", text, re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_no_two_headings_share_an_anchor(path):
    """Duplicate headings make `#foo` ambiguous: GitHub silently appends `-1`."""
    seen: dict[str, int] = {}
    for match in HEADING.finditer(path.read_text()):
        key = slug(match.group(2))
        seen[key] = seen.get(key, 0) + 1
    clashes = sorted(name for name, count in seen.items() if count > 1)
    # plans.md has a "Status" line under many items by design; nothing links to
    # those, so an exception here is honest rather than a loophole.
    if path.name == "plans.md":
        clashes = [name for name in clashes if not name.startswith("status")]
    assert not clashes, f"{path.name}: repeated headings {clashes}"
