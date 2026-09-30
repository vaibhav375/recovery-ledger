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
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPACE = ROOT / "deploy" / "hf-space"
DIST = ROOT / "dashboard" / "dist"


def referenced_assets() -> set[str]:
    """Only the assets this build actually uses.

    dashboard/dist is not emptied between builds (data.json lives there and
    Vite would delete it), so superseded content-hashed chunks pile up. Copying
    the directory wholesale would put 29 files in the image where 2 are live.
    """
    index = (DIST / "index.html").read_text()
    refs = set(re.findall(r'(?:src|href)="\./assets/([^"]+)"', index))
    for name in list(refs):
        f = DIST / "assets" / name
        if f.exists() and f.suffix in (".css", ".js"):
            text = f.read_text(errors="ignore")
            refs |= set(re.findall(
                r"(?:\./)?assets/([\w.\-]+\.(?:woff2?|css|js|png|svg))", text))
            refs |= set(re.findall(
                r"[\"'](?:\./)?([\w.\-]+\.(?:woff2?|png|svg))[\"']", text))
    return refs


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

    out = SPACE / "dashboard" / "dist"
    (out / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DIST / "index.html", out / "index.html")
    shutil.copy2(DIST / "data.json", out / "data.json")
    kept = 0
    for name in sorted(referenced_assets()):
        src = DIST / "assets" / name
        if src.exists():
            shutil.copy2(src, out / "assets" / name)
            kept += 1

    total = sum(f.stat().st_size for f in SPACE.rglob("*") if f.is_file())
    print(f"  {kept} assets kept of {len(list((DIST / 'assets').iterdir()))}")
    print(f"  deploy/hf-space is {total / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
