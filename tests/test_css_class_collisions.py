"""No CSS class may mean two different things.

This project's stylesheet uses one flat `rl-*` namespace with no CSS modules
and no build-time scoping, which is fine until two unrelated components reach
for the same plausible short name. It has now happened twice, and both times
the symptom was invisible in the component that broke:

* `.rl-field` was the three.js canvas host (`position: absolute; inset: 0`)
  and, later, a slider label in the live console. Every slider stacked on top
  of the run buttons.
* `.rl-sub` was the pinned subtraction section (`height: 340svh`) and, earlier,
  the solver-rationale text in the negotiation card. Each rationale rendered
  3,230 pixels tall, which silently wrecked the negotiation view — one of the
  project's own novelty claims.

Neither was caught by TypeScript, by the build, or by looking at the section
being worked on. So the rule is enforced here instead: a class that carries
*layout authority* — it sets a height, or takes itself out of normal flow —
must be used by exactly one component. Cosmetic classes (colour, type, border)
are shared freely; they are not what breaks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "frontend" / "src" / "app.css"
SRC = ROOT / "frontend" / "src"

# Properties that let a class dictate where an element sits or how big it is.
# A class with any of these applied to the wrong element moves or resizes it.
LAYOUT_PROPS = re.compile(
    r"(?:^|;|\{)\s*(height|min-height|position|inset|top|bottom|left|right)\s*:",
    re.M,
)
# `position: relative` and `static` claim no authority — they do not move
# anything on their own — so they do not make a class layout-authoritative.
BENIGN_POSITION = re.compile(r"position\s*:\s*(relative|static)\s*[;}]")

# Classes deliberately shared across components as a common vocabulary. Each
# one is here because sharing it is the point, not an accident.
SHARED_VOCABULARY = {
    "rl-live-head",   # section header bar, used by every live surface
    "rl-trace-row",   # one ledger entry, drawn identically wherever it appears
    "rl-note",        # callout paragraph
    "rl-chip",        # small status pill
    "rl-btn",         # button
    "rl-empty-note",  # "nothing here yet" text
}


def _top_level_blocks(css: str) -> list[tuple[str, str]]:
    """(selector-list, body) for every rule at the top level of the file.

    Media-query bodies are skipped: redefining `.rl-ledger-row` inside
    `@media (max-width: 900px)` is the intended responsive pattern, not a
    collision.
    """
    blocks: list[tuple[str, str]] = []
    depth = 0
    start = 0
    head_start = 0
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                head_start = start
                head = css[head_start:i]
                start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blocks.append((head, css[start:i]))
                start = i + 1
    return blocks


def _layout_classes() -> dict[str, str]:
    """Bare single-class selectors whose rule sets a layout property."""
    css = CSS.read_text()
    found: dict[str, str] = {}
    for head, body in _top_level_blocks(css):
        # Strip comments and at-rule preludes from the selector text.
        head = re.sub(r"/\*.*?\*/", " ", head, flags=re.S)
        if "@" in head:
            continue
        if not LAYOUT_PROPS.search(body):
            continue
        stripped = BENIGN_POSITION.sub("", body)
        if not LAYOUT_PROPS.search(stripped):
            continue
        for sel in head.split(","):
            sel = sel.strip()
            if re.fullmatch(r"\.[A-Za-z0-9_-]+", sel):
                found[sel[1:]] = body.strip()[:120]
    return found


def _class_usage() -> dict[str, set[str]]:
    """class name -> set of component files that apply it."""
    usage: dict[str, set[str]] = {}
    for path in SRC.rglob("*.tsx"):
        text = path.read_text()
        names: set[str] = set()
        # className="a b c"
        for literal in re.findall(r'className="([^"]*)"', text):
            names.update(literal.split())
        # className={`a ${x} b`} — take only the literal fragments
        for tpl in re.findall(r"className=\{`([^`]*)`\}", text):
            for chunk in re.split(r"\$\{[^}]*\}", tpl):
                names.update(chunk.split())
        for name in names:
            if name.startswith("rl-"):
                usage.setdefault(name, set()).add(path.name)
    return usage


def test_layout_classes_belong_to_exactly_one_component():
    layout = _layout_classes()
    usage = _class_usage()

    offenders = []
    for name, body in layout.items():
        if name in SHARED_VOCABULARY:
            continue
        files = usage.get(name, set())
        if len(files) > 1:
            offenders.append((name, sorted(files), body))

    assert not offenders, (
        "A class that controls layout is applied by more than one component. "
        "Whichever component did not expect it is being moved or resized:\n"
        + "\n".join(f"  .{n} used by {f}\n    rule: {b}" for n, f, b in offenders)
    )


@pytest.mark.parametrize("name", ["rl-field", "rl-sub"])
def test_the_two_known_collisions_stay_fixed(name):
    """Regression pins for the two that actually shipped."""
    usage = _class_usage()
    assert len(usage.get(name, set())) <= 1, (
        f".{name} has been reused across components again — this exact "
        f"collision has broken the page twice before."
    )


def test_every_layout_class_in_the_stylesheet_is_actually_used():
    """A layout class nothing applies is either dead or a typo away from the
    class that was meant. Both are worth knowing about."""
    layout = _layout_classes()
    usage = _class_usage()
    # Section roots referenced only from CSS (e.g. via descendant selectors)
    # are legitimate; require that the name appears somewhere in the TSX at all.
    all_text = "\n".join(p.read_text() for p in SRC.rglob("*.tsx"))
    unused = sorted(n for n in layout if n not in usage and n not in all_text)
    assert not unused, f"layout classes defined but never applied: {unused}"
