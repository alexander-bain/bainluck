#!/bin/bash
# look.sh <url> [out.png] [clickText] — headless screenshot of a production page for LOOK passes.
# Set SHOT_W / SHOT_H for a phone-width pass (default 1280x2200): SHOT_W=390 SHOT_H=844 look.sh ...
# Lanes: run this, then Read the PNG (Claude reads images natively) and JUDGE it like Alex would:
# empty charts, flat lines, missing players/images, stale copy, broken layout.
#
# 2026-09-01 (ux/976): rewritten to delegate to shop-shot.mjs. The old `npx playwright screenshot`
# path CANNOT launch Chromium in the agent sandbox, and — worse — it exited 0 while producing no
# file, so a dead camera read as a clean pass. This version exits non-zero if no PNG is written.
set -o pipefail
URL="$1"; OUT="${2:-/tmp/look-$(date +%s).png}"; CLICK="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure playwright + chromium are cached (no-op once warm; needs the session proxy).
npx --yes playwright@1.55 --version >/dev/null 2>&1 || true

# ux/1052: `$CLICK` was UNQUOTED, so a multi-word click target ("AL / NL Champ")
# arrived as four argv entries and shop-shot only ever saw the first word — it
# printed CLICKFAIL and shot the un-clicked page, which reads as a clean pass.
if [ -n "$CLICK" ]; then
  node "$HERE/shop-shot.mjs" "$URL" "$OUT" "$CLICK" >/dev/null || exit 1
else
  node "$HERE/shop-shot.mjs" "$URL" "$OUT" >/dev/null || exit 1
fi
[ -s "$OUT" ] || { echo "look.sh: no screenshot written for $URL" >&2; exit 1; }
echo "$OUT"
