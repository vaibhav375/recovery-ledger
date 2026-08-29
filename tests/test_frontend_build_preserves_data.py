"""The React build must not delete the data the page renders.

`dashboard/dist` has two producers: Vite writes the compiled app there, and
`build_dashboard.py` writes `data.json` there. That file is the entire content
of the page — every figure, every chart, every ledger entry.

Vite's `emptyOutDir` cleared the directory before writing, so running the
frontend build on its own after `make dashboard` deleted `data.json` and left a
shell that fetches a 404 and renders an empty page. Nothing failed: the build
exits 0, there is no TypeScript error and no console error until someone opens
the page and sees nothing. `make dashboard` depends on `frontend-build` and
therefore always regenerated the file, so the breakage only appeared when the
build was invoked directly — which is exactly what `make frontend-build`
invites.

This pins the config rather than the behaviour because reproducing the
behaviour would mean running npm in the test suite.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VITE_CONFIG = ROOT / "frontend" / "vite.config.ts"


def test_vite_does_not_empty_the_shared_output_directory():
    config = VITE_CONFIG.read_text()
    m = re.search(r"emptyOutDir:\s*(true|false)", config)
    assert m, "emptyOutDir is unset; Vite's default would clear dashboard/dist"
    assert m.group(1) == "false", (
        "emptyOutDir is true, so a frontend build deletes dashboard/dist/data.json "
        "and the page renders empty with no error"
    )


def test_the_output_directory_is_still_the_shared_one():
    """If the build ever stops writing beside data.json, the reasoning above
    no longer applies and emptyOutDir should be reconsidered."""
    config = VITE_CONFIG.read_text()
    assert 'outDir: "../dashboard/dist"' in config, (
        "the Vite output directory moved; revisit whether emptyOutDir should "
        "stay false"
    )


def test_the_reason_is_written_down_next_to_the_setting():
    """A bare `emptyOutDir: false` reads like a mistake and invites a cleanup
    commit that reintroduces the bug."""
    config = VITE_CONFIG.read_text()
    # rindex: the setting itself, not the explanation that mentions it.
    idx = config.rindex("emptyOutDir")
    preceding = config[max(0, idx - 900):idx]
    assert "data.json" in preceding, (
        "explain next to emptyOutDir why it is false, or someone will 'fix' it"
    )
