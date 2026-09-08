#!/bin/bash
# look.sh <url> [out.png] [clickText] — headless screenshot of a production page for LOOK passes.
# Set SHOT_W / SHOT_H for a phone-width pass (default 1280x2200): SHOT_W=390 SHOT_H=844 look.sh ...
# Lanes: run this, then Read the PNG (Claude reads images natively) and JUDGE it like Alex would:
# empty charts, flat lines, missing players/images, stale copy, broken layout.
#
# SHOT_SCROLL — shoot ONE VIEWPORT instead of the whole page. Unset = fullPage, unchanged.
#   SHOT_SCROLL=top          the first screen
#   SHOT_SCROLL=22411        the viewport at that pixel offset
# Use it on any long page. `/hub/tennis` at 390px is 44,729px tall, and its fullPage PNG
# (1332x89458) downscales to an unreadable 30px strip — a shot you cannot read is not a LOOK.
# The document height is printed to stderr in both modes; a page 53 screens tall is a finding.
#
# SHOT_CLICKS — tap a SEQUENCE of controls before shooting, for a surface two or more taps deep.
# Steps are `;`-separated and run in order:
#   text=Doubles   (or a bare `Doubles`)  EXACT visible text
#   css=a[href="/sport/football/nfl"]     a CSS selector — also [ . # shorthand, e.g. [data-tab=x]
# Worked example, two taps deep from the home page:
#   SHOT_CLICKS='Sports;css=a[href="/sport/football/nfl"]' look.sh https://bainluck.com/ out.png
#
# 🔴 SAY `css=` WHEN YOU MEAN A SELECTOR. Only [ . and # are recognised as a selector on their
# own, so `a[href="…"]`, `button.pill` and `nav a` are read as literal TEXT and match nothing.
# You will get a loud CLICKFAIL naming the misreading, but `css=` is how you avoid it.
# A selector is the only way to reach a pill, an icon button or a `data-testid`: the text matcher
# is `exact: true`, and e.g. the NFL pill's text is "🏈NFL", so `NFL` does not match it.
#
# Steps resolve to the first VISIBLE match, not the first match in the DOM. At 390px
# `getByText('Sports')` finds three nodes and the first is the hidden desktop nav — clicking that
# is a 15s timeout on an element nobody can see, while the tab you meant sits third (#3932).
#
# 🔴 A TAP THAT DOES NOT LAND IS AN ERROR (#3932). look.sh exits non-zero (shop-shot exit 3) and
# writes NO PNG — including deleting any stale one already at that path. Until 2026-09-08 a failed
# tap printed CLICKFAIL to stderr and exited 0, so you got a readable screenshot of the UN-TAPPED
# page under a filename that said otherwise, and the LOOK rule read it as a pass (ux/1052 lost one
# that way). If you genuinely want "tap it if it's there", say so: SHOT_CLICK_OPTIONAL=1.
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
# PROPAGATE the real exit code rather than flattening every failure to 1 — the
# VALUE is the story (gotcha #124): 3 means a tap did not land and the page you
# wanted was never reached, 2 is usage, 1 is the camera. Flattened to 1 they are
# one indistinguishable "it didn't work".
if [ -n "$CLICK" ]; then
  node "$HERE/shop-shot.mjs" "$URL" "$OUT" "$CLICK" >/dev/null || exit $?
else
  node "$HERE/shop-shot.mjs" "$URL" "$OUT" >/dev/null || exit $?
fi
[ -s "$OUT" ] || { echo "look.sh: no screenshot written for $URL" >&2; exit 1; }
echo "$OUT"
