#!/bin/sh
# Publish dashboard/dist to the gh-pages branch.
#
#   sh tools/publish_pages.sh
#
# Builds clean and publishes everything. Both of those are deliberate.
#
# Vite does not empty dashboard/dist between builds, because build_dashboard.py
# writes data.json there and emptying would delete it. Superseded chunks
# therefore accumulate, and the temptation is to publish only the assets that
# index.html mentions. That is wrong: the app code-splits, so FleetField,
# PolicySpace and three.module are fetched at runtime by dynamic import() and
# appear in no href or src. Pruning on static references alone deletes them and
# the published page renders nothing at all, with no error until it is opened.
#
# Building clean removes the reason to prune, and the check below fails if any
# chunk the bundle imports is missing.
set -e
cd "$(dirname "$0")/.."

rm -rf dashboard/dist/assets dashboard/dist/index.html
make dashboard

python3 - <<'PY'
import pathlib, re, sys
d = pathlib.Path("dashboard/dist/assets")
present = {f.name for f in d.iterdir()}
refs = set()
for f in d.glob("*.js"):
    refs |= set(re.findall(r'["\']\./([\w.\-]+\.js)["\']', f.read_text(errors="ignore")))
missing = sorted(refs - present)
if missing:
    print(f"chunks referenced but not built: {missing}", file=sys.stderr)
    raise SystemExit(1)
print(f"  {len(present)} assets, {len(refs)} chunk references, none missing")
PY

WORK="${TMPDIR:-/tmp}/recovery-ledger-pages"
rm -rf "$WORK"
git worktree prune
git worktree add -q --detach "$WORK" origin/gh-pages
find "$WORK" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -R dashboard/dist/. "$WORK"/
touch "$WORK/.nojekyll"

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "  nothing changed"
else
  git -c user.name="Vaibhav" -c user.email="144893207+vaibhav375@users.noreply.github.com" \
      commit --quiet -m "Publish the Recovery Ledger dashboard"
  git push --quiet origin HEAD:gh-pages
  echo "  published to gh-pages"
fi
cd - >/dev/null
git worktree remove "$WORK" --force
