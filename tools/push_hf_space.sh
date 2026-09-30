#!/bin/sh
# Push deploy/hf-space to a Hugging Face Space.
#
#   sh tools/push_hf_space.sh https://huggingface.co/spaces/<owner>/<name>
#
# Clones the Space, copies the payload in, and merges the README rather than
# overwriting it: the Space's generated front matter carries fields Hugging
# Face fills in itself (sdk_version above all), and losing those makes the
# build fail in a way that reads like a code problem.
set -e
cd "$(dirname "$0")/.."

SPACE_URL="$1"
[ -n "$SPACE_URL" ] || { echo "usage: sh tools/push_hf_space.sh <space url>" >&2; exit 1; }

[ -f deploy/hf-space/app.py ] || { echo "deploy/hf-space is not assembled. Run 'make hf-space' first." >&2; exit 1; }

WORK="${TMPDIR:-/tmp}/pakka-space-push"
rm -rf "$WORK"
echo "cloning $SPACE_URL"
git clone --quiet "$SPACE_URL" "$WORK"

# everything except the README, which is merged below
tar -cf - -C deploy/hf-space --exclude README.md . | tar -xf - -C "$WORK"

python3 - "$WORK" <<'PY'
import pathlib, re, sys

work = pathlib.Path(sys.argv[1])
theirs = (work / "README.md").read_text() if (work / "README.md").exists() else ""
ours = pathlib.Path("deploy/hf-space/README.md").read_text()

def split(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fields, order = {}, []
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
            order.append(k.strip())
    return fields, m.group(2)

their_fields, _ = split(theirs)
our_fields, body = split(ours)

# ours wins on anything we set on purpose; theirs fills in what only Hugging
# Face knows, which in practice is sdk_version
merged = dict(their_fields)
merged.update(our_fields)

lines = "\n".join(f"{k}: {v}" for k, v in merged.items())
(work / "README.md").write_text(f"---\n{lines}\n---\n\n{body.lstrip()}")
print("  README merged, keeping:", ", ".join(k for k in their_fields if k not in our_fields) or "(nothing extra)")
PY

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "nothing changed"
  exit 0
fi
git -c user.name="Vaibhav" -c user.email="144893207+vaibhav375@users.noreply.github.com" \
    commit --quiet -m "The live console"
echo
echo "About to push $(git diff --stat HEAD~1 2>/dev/null | tail -1 || echo 'the payload')"
echo "Username: your Hugging Face username. Password: an access token with write scope."
echo
git push
