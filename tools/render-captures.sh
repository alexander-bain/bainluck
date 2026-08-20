#!/usr/bin/env bash
#
# RENDER A CAPTURE DIRECTORY'S HTML TO PNG — the recovery half of
# tools/capture-prop-rail.sh.
#
# WHY IT IS A SEPARATE SCRIPT. Rendering needs a browser; producing the HTML does
# not. UX-P109 hit a window in which both Chromium and Chrome abort with
# `bootstrap_check_in ... Permission denied (1100)` before painting anything —
# a missing Mach bootstrap namespace, a property of the session's process tree.
# No flag reaches it (--no-sandbox, --headless=new, --disable-breakpad all fail
# identically), and the SAME binary shot cleanly for the previous cycle.
#
# Splitting the render out means the expensive, stateful half — swapping source
# files to a base ref and running the harness twice — is never re-run just to get
# pictures. Any healthy window, or Alex with a single `!` line, finishes the job:
#
#     ! cd ~/bainluck-dev/ux && tools/render-captures.sh .claude/handoff/artifacts-ux-p109
#
# Idempotent: an HTML that already has its PNG is skipped, so re-running after a
# partial failure costs only the missing shots.

set -u

DIR="${1:?usage: render-captures.sh <capture-dir>}"
CHROME="${CHROME_BIN:-$HOME/Library/Caches/ms-playwright/chromium-1140/chrome-mac/Chromium.app/Contents/MacOS/Chromium}"

if [ ! -x "$CHROME" ]; then
  echo "FATAL: no chromium at $CHROME (set CHROME_BIN)"
  exit 3
fi

shot=0
missed=0
skipped=0
for html in "$DIR"/*.html; do
  [ -e "$html" ] || continue
  png="${html%.html}.png"
  if [ -f "$png" ]; then
    skipped=$((skipped + 1))
    continue
  fi
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
    --window-size=390,2400 --screenshot="$png" \
    --virtual-time-budget=2000 "file://$html" >/dev/null 2>&1
  if [ -f "$png" ]; then
    shot=$((shot + 1))
    echo "  shot $(basename "$png")  ($(wc -c < "$png") bytes)"
  else
    missed=$((missed + 1))
    echo "  NO PNG $(basename "$png")"
  fi
done

echo "shot=$shot skipped=$skipped missed=$missed"
# A run that rendered nothing must not exit 0 and read as done.
[ "$missed" -eq 0 ]
