#!/bin/zsh
# BEFORE/AFTER capture of the prop rail — UX-P107.
#
# Alex rules these surfaces from screenshots, and three of this queue's four
# rulings came from one. "Prove it with a before/after capture of the same card"
# is the acceptance bar, so the before half must be the code that actually
# shipped — not a re-creation of it.
#
# So this swaps the three source files to a git ref (cp backup, never
# `git checkout --`, per the lane's mutation discipline), renders, restores, and
# renders again. Headless Chromium shoots the pair; no npm dependency is added,
# because the registry is unreachable from this sandbox.
#
#   usage: tools/capture-prop-rail.sh <out-dir> [before-ref]
set -u
OUT=${1:?usage: capture-prop-rail.sh <out-dir> [before-ref]}
REF=${2:-HEAD}
cd "$(dirname "$0")/.."
FRONTEND=$PWD
REPO=$(git rev-parse --show-toplevel)

FILES=(lib/propDivergence.ts components/PropTravelBar.tsx components/PropDivergenceRail.tsx components/PropDivergenceDetail.tsx)
CHROME="$HOME/Library/Caches/ms-playwright/chromium-1140/chrome-mac/Chromium.app/Contents/MacOS/Chromium"

# `--headless=old --single-process --no-zygote` is the ONLY combination that
# works in this sandbox, and each flag is load bearing. Plain `--headless` (new
# mode) exits 0 and writes NO FILE — a silent success that reads as a capture
# taken. `--headless=old` alone dies at
# `Check failed: kr == KERN_SUCCESS ... MachPortRendezvousServer`, because the
# sandbox refuses the child-process bootstrap; single-process never launches
# one. Google Chrome fails the same way, so this is not a Chromium build issue.
CHROME_FLAGS=(--headless=old --single-process --no-zygote --no-sandbox
              --disable-gpu --hide-scrollbars --force-device-scale-factor=2)

if [ ! -x "$CHROME" ]; then echo "no chromium at $CHROME"; exit 4; fi
mkdir -p "$OUT"

# Restore on ANY exit, including a failed `git show`. The first run of this
# script lost a source file to exactly that: `git show <bad-ref> > "$f"` had
# already TRUNCATED the target before git reported the error, and the restore
# line sat after an `|| exit`. Backups are cp copies, never `git checkout --`.
restore() { for f in $FILES; do
  [ -f "/tmp/cap.$(echo $f | tr / _).bak" ] && cp "/tmp/cap.$(echo $f | tr / _).bak" "$f"
done }
trap restore EXIT INT TERM

render() { # render <label>
  UX_CAPTURE_DIR="$OUT/$1" TZ=UTC npx jest --testPathPatterns=propRailCapture > "$OUT/$1.jest.log" 2>&1
  local code=$?
  echo "  jest($1) EXIT CODE: $code"
  if [ $code -ne 0 ]; then tail -20 "$OUT/$1.jest.log"; return $code; fi
  for f in "$OUT/$1"/*.html; do
    local base=$(basename "$f" .html)
    "$CHROME" $CHROME_FLAGS --window-size=390,1700 \
      --screenshot="$OUT/$1-$base.png" "file://$f" >/dev/null 2>&1
    if [ -f "$OUT/$1-$base.png" ]; then
      echo "    shot $1-$base.png  ($(wc -c < "$OUT/$1-$base.png") bytes)"
    else
      echo "    ** NO PNG WRITTEN for $1-$base — a zero-byte capture is not evidence **"
      return 5
    fi
  done
}

echo "== AFTER (working tree) =="
render after || exit 1

echo "== BEFORE (${REF}) =="
for f in $FILES; do cp "$f" "/tmp/cap.$(echo $f | tr / _).bak"; done
# Write to a temp first: a redirect truncates its target BEFORE the command runs.
for f in $FILES; do
  git -C "$REPO" show "${REF}:frontend/$f" > /tmp/cap.stage || { echo "git show failed for $f"; exit 3; }
  cp /tmp/cap.stage "$f"
done
render before

restore
echo "== restored; working tree must show ONLY the intended edits =="
git -C "$REPO" diff --stat -- $(for f in $FILES; do echo "frontend/$f"; done)
