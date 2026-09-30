"""Assemble deploy/hf-space/ — everything the live console needs, and nothing else.

    python3 tools/build_hf_space.py

The live console cannot be static. Everything above it on the dashboard is
measurement from runs that already happened; the console drives the agent in
real time, holds a run in memory, and streams events while the loop executes.
That needs one process with shared memory and a long-lived connection, so it
ships as a container rather than a function.

This copies in only what that container needs:

  app.py                 the Space entry point (Gradio SDK, which is free;
                         the Docker SDK is not)
  src/recovery_ledger/   the package
  redteam/attacks.py     the attack suite, which live/range.py loads by adding
                         redteam/ to sys.path so the interactive range and the
                         reported block rate cannot drift apart
  dashboard/dist/        the built front end, minus superseded chunks

Training data is generated from a seed at startup, so no data files are needed.
"""
from __future__ import annotations

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPACE = ROOT / "deploy" / "hf-space"
DIST = ROOT / "dashboard" / "dist"


def copy_dist(out: pathlib.Path) -> int:
    """Copy the built front end whole.

    An earlier version copied only the assets index.html mentions, to avoid the
    superseded chunks that pile up because Vite does not empty its output
    directory. That deletes the lazily-loaded ones: the app code-splits, so
    several chunks are fetched at runtime by dynamic import() and appear in no
    href or src. The published page then renders nothing, with no error until
    it is opened. Build clean instead, and copy everything.
    """
    (out / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DIST / "index.html", out / "index.html")
    shutil.copy2(DIST / "data.json", out / "data.json")
    kept = 0
    for f in (DIST / "assets").iterdir():
        if f.is_file():
            shutil.copy2(f, out / "assets" / f.name)
            kept += 1
    return kept


def main() -> int:
    if not (DIST / "index.html").exists():
        print("dashboard/dist is not built. Run `make dashboard` first.")
        return 1

    for stale in ("src", "dashboard", "redteam"):
        shutil.rmtree(SPACE / stale, ignore_errors=True)

    shutil.copytree(ROOT / "src" / "recovery_ledger", SPACE / "src" / "recovery_ledger",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    (SPACE / "redteam").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "redteam" / "attacks.py", SPACE / "redteam" / "attacks.py")

    kept = copy_dist(SPACE / "dashboard" / "dist")

    total = sum(f.stat().st_size for f in SPACE.rglob("*") if f.is_file())
    print(f"  {kept} assets copied")
    print(f"  deploy/hf-space is {total / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
