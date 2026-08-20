#!/usr/bin/env bash
#
# THE PROP-RAIL BEFORE/AFTER DRIVER — the other half of
# frontend/__tests__/capture/propRailCapture.test.tsx.
#
# ⚠️ COMMITTED BY UX-P109 BECAUSE IT HAD BEEN REBUILT THREE TIMES. UX-P106 built
# a capture rig by hand and left nothing behind. UX-P107 rebuilt it and committed
# the JEST half — whose docstring then referred readers to `tools/capture-prop-rail.sh`,
# a file that did not exist. UX-P108 rebuilt the shell half again, used it, and
# again did not commit it. A rig referenced by a committed file, and absent from
# the repo, reads to the next lane as "someone deleted it" rather than "it was
# never here" — so it gets rebuilt rather than looked for. This is that file.
#
# WHAT IT DOES
#   1. renders every state in the harness to a self-contained HTML file, twice —
#      once from the working tree (AFTER), once with the changed source files
#      swapped to a base ref (BEFORE);
#   2. drives headless Chromium over each and writes a PNG;
#   3. restores the working tree and prints its diffstat, so a run that failed to
#      restore is visible rather than silent.
#
# WHY THE SWAP AND NOT TWO CHECKOUTS: the pair must be the SAME harness rendering
# the SAME fixture, differing only in the code under ruling. Checking out the base
# ref would also revert the harness — a new capture state would vanish from the
# BEFORE half and the pair would no longer be comparable.
#
# USAGE
#   tools/capture-prop-rail.sh <out-dir> <base-ref> [file ...]
#   tools/capture-prop-rail.sh /tmp/cap program/ux-95 frontend/lib/propDivergence.ts
#
# Files default to `frontend/lib/propDivergence.ts`. Pass more when a queue's
# change spans components.
#
# PRECONDITION: `npm run build` has been run, so `.next/static/css` holds the real
# stylesheet. The harness reds if it has not (an unstyled capture is a misleading
# one), which is deliberate — do not work around it.
#
# EXIT CODES
#   0   both halves rendered AND shot; tree restored.
#   10  both halves rendered, NO PNG produced — this window cannot drive a
#       browser. The HTML pair is complete and `tools/render-captures.sh` finishes
#       it. Distinct from 0 on purpose: "pairs produced" and "pictures produced"
#       are different claims.
#   1/3/4  harness red / no chromium binary / bad base ref.
# The restore runs on a trap, so an interrupted run still leaves the working tree
# as it found it.

set -u

OUT_DIR="${1:?usage: capture-prop-rail.sh <out-dir> <base-ref> [file ...]}"
BASE_REF="${2:?usage: capture-prop-rail.sh <out-dir> <base-ref> [file ...]}"
shift 2
FILES=("$@")
if [ ${#FILES[@]} -eq 0 ]; then FILES=("frontend/lib/propDivergence.ts"); fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/frontend"
CHROME="${CHROME_BIN:-$HOME/Library/Caches/ms-playwright/chromium-1140/chrome-mac/Chromium.app/Contents/MacOS/Chromium}"
LOG="$OUT_DIR/capture.log"

mkdir -p "$OUT_DIR"
DEGRADED=0
: > "$LOG"

say() { echo "$@" | tee -a "$LOG"; }

if [ ! -x "$CHROME" ]; then
  say "FATAL: no chromium at $CHROME (set CHROME_BIN)"
  exit 3
fi

# The restore runs whatever happens. `cp` backups, never `git checkout --`:
# a checkout in a shared tree is the write-direction hazard of gotcha #51, and
# it discards more than this script put there.
BACKUP_DIR="$(mktemp -d)"
for f in "${FILES[@]}"; do
  cp "$REPO/$f" "$BACKUP_DIR/$(echo "$f" | tr '/' '_')"
done
restore() {
  for f in "${FILES[@]}"; do
    cp "$BACKUP_DIR/$(echo "$f" | tr '/' '_')" "$REPO/$f"
  done
  rm -rf "$BACKUP_DIR"
}
trap restore EXIT

# ** THE HTML IS THE ARTIFACT; THE PNG IS A RENDERING OF IT. ** UX-P109 learned
# this the hard way: both Chromium and Chrome abort with
# `bootstrap_check_in ... Permission denied (1100)` in a window whose process tree
# has no Mach bootstrap namespace — a property of the WINDOW, not of a flag, and
# not fixed by --no-sandbox, --headless=new or --disable-breakpad. The previous
# cycle shot the same binary fine.
#
# So the HTML is kept ALWAYS and named with the same prefix. A window that cannot
# shoot still produces a complete, comparable before/after pair that any healthy
# window (or Alex, with one `!` line) can render later — instead of the run being
# a total loss. Deleting the HTML after a successful shot was the old behaviour
# and it is exactly what made a failed shot unrecoverable.
#
# ⚠️ RAW DIR, NOT $OUT_DIR: the harness writes `<slug>.html`, and once a pass
# KEEPS its output as `<prefix>-<slug>.html` in the same directory, the NEXT
# pass's glob picks those up too and produces `before-after-pregame.html`. That
# is a real bug this script shipped for exactly one run. The harness renders into
# a scratch dir which is emptied per pass; only prefixed files ever reach $OUT_DIR.
RAW="$OUT_DIR/.raw"

shoot() {   # shoot <prefix>
  local prefix="$1" shot=0 missed=0
  for html in "$RAW"/*.html; do
    [ -e "$html" ] || continue
    local slug png keep
    slug="$(basename "$html" .html)"
    png="$OUT_DIR/${prefix}-${slug}.png"
    keep="$OUT_DIR/${prefix}-${slug}.html"
    mv "$html" "$keep"
    "$CHROME" --headless --disable-gpu --hide-scrollbars \
      --window-size=390,2400 --screenshot="$png" \
      --virtual-time-budget=2000 "file://$keep" >/dev/null 2>&1
    if [ -f "$png" ]; then
      shot=$((shot + 1))
      say "    shot $(basename "$png")  ($(printf '%8d' "$(wc -c < "$png")") bytes)"
    else
      missed=$((missed + 1))
      say "    NO PNG $(basename "$png")  — html kept at $(basename "$keep")"
    fi
  done
  # LOUD on the degraded case (gotcha #53's sibling: a run that produced nothing
  # must not read like a run with nothing to do).
  if [ "$missed" -gt 0 ]; then
    DEGRADED=1
    say "  ⚠️  $prefix: $shot shot, $missed NOT shot — this window cannot drive a browser."
    say "     Render the pair from a healthy window with:"
    say "     tools/render-captures.sh $OUT_DIR"
  fi
}

render() {  # render <label>
  # NEVER piped: `cmd | tail` reports tail's exit code, and two UX-P064 gate runs
  # recorded a clean 0 over runs that never happened (gotcha #54).
  rm -rf "$RAW"; mkdir -p "$RAW"
  ( cd "$FRONTEND" && UX_CAPTURE_DIR="$RAW" TZ=UTC \
      npx jest --testPathPatterns=propRailCapture ) > "$OUT_DIR/jest-$1.txt" 2>&1
  local code=$?
  say "  jest($1) EXIT CODE: $code"
  # Read the VALUE, not just non-zero: 1 is a failing test, anything else is a
  # story about the harness (gotcha #54's amendment).
  if [ "$code" -ne 0 ]; then
    tail -25 "$OUT_DIR/jest-$1.txt" | tee -a "$LOG"
    return "$code"
  fi
}

say "== AFTER (working tree) =="
render after || exit 1
shoot after

say "== BEFORE ($BASE_REF) =="
for f in "${FILES[@]}"; do
  git -C "$REPO" show "$BASE_REF:$f" > "$REPO/$f" || { say "FATAL: cannot read $BASE_REF:$f"; exit 4; }
done
render before || exit 1
shoot before

restore
trap - EXIT
say "== restored; working tree must show ONLY the intended edits =="
git -C "$REPO" diff --stat -- "${FILES[@]}" | tee -a "$LOG"
rmdir "$RAW" 2>/dev/null

# EXIT 10 = the before/after HTML pair exists but no PNG was rendered. Distinct
# from 0, because "pairs produced" and "pictures produced" are different claims
# and a caller that cannot tell them apart will report the wrong one.
if [ "$DEGRADED" -ne 0 ]; then exit 10; fi
