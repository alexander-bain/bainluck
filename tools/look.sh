#!/bin/bash
# look.sh <url> [out.png] [clickText] — headless screenshot of a production page for LOOK passes.
# Set SHOT_W / SHOT_H for a phone-width pass (default 1280x2200): SHOT_W=390 SHOT_H=844 look.sh ...
# Lanes: run this, then Read the PNG (Claude reads images natively) and JUDGE it like Alex would:
# empty charts, flat lines, missing players/images, stale copy, broken layout.
#
# 2026-09-10 (#4664): THE WHOLE-PAGE SHOT NO LONGER LOSES THE CHART.
# The default used to be `page.screenshot({ fullPage: true })`, which Chromium serves through
# captureBeyondViewport — it re-renders the document off-screen, remounts every chart, and
# restarts Recharts' entry animation, so the shutter caught the line at t≈0 and the plot came
# out EMPTY. Measured on /events/15309061 at 390px, three captures in one page context:
# viewport 2870 stroke px, fullPage 0, viewport grown to the document height 2870. The line was
# in the DOM, complete and correct, for all three. It also stamped the fixed bottom nav across
# mid-page content and then left it off the real page bottom.
# Now: a whole-page shot GROWS the viewport to the document height and takes an ordinary
# viewport shot. stderr says which you got — `mode=wholePage@grown<N>` is the good one.
# 🔴 `mode=fullPage(CHART-UNSAFE)` means the page was over the grown-capture ceiling and you
# have the old, chart-losing capture. A loud CHART-UNSAFE line names it. On such a page, judge
# charts with SHOT_SCROLL=<offset> instead — never off the whole-page PNG.
# EXPECT A LAZY PAGE TO GET LONGER, and that is the capture being honest. Growing the viewport
# puts the whole document on screen, so anything that loads on intersection loads at once.
# Measured: /sports at 390px reports docHeight=9,954 and then settles at 17,820 once it is all
# on screen — a 26,504px PNG where the old capture gave 19,908px of the same page. The extra is
# real content the old whole-page shot never rendered. The re-measure is bounded (two growths,
# then the shutter), so an endless feed cannot hold the camera open. /calibration (11,668px)
# grows with no change to the artifact at all.
# STILL THE RULE FOR ANY EMPTY-LOOKING CHART: confirm before you file. One command —
#   node ~/bainluck/tools/chart-in-raster-4664.mjs <url> [width]
# exit 0 the picture holds the lines the DOM has · 3 it lost one (#4664 is back) · 4 no chart.
# It hides the line layer and diffs, so it is blind to colour and alpha; a colour count is not
# good enough (nine lines stroked `rgba(0,0,0,0.15)` read as "missing" to the first cut).
#
# SHOT_SCROLL — shoot ONE VIEWPORT instead of the whole page. Unset = the whole page (above).
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
# 🔴 2026-09-10 (#4903): A SHOT WITH NO IMAGES IN IT EXITS 5, and it says IMAGE-BLACKOUT on stderr.
# From 2026-09-09 17:56 PT to this fix, EVERY LOOK the fleet took was of a page with no crests, no
# faces and no market art: notice 39's `x-bainluck-origin` tag was set as a context-wide header, and
# Playwright puts those on every request — including the `<img>` loads Chromium issues in no-cors
# mode, which it then fails outright. Measured on /sports/baseball_mlb at 390px, one A/B: with the
# header 215/215 `img` at naturalWidth 0 and 28 x net::ERR_FAILED; without it, 28 x 200. The tag now
# rides our own origins only. If you judged a missing image from a LOOK in that window, RE-SHOOT it.
# Exit 5 is the backstop, not the fix: every image request failing at the network layer before the
# server answered is the CAMERA. A 404 crest is a response, so a real broken image still reaches you.
#
# 2026-09-09 (#4408): the pointer is PARKED OFF-VIEWPORT before every shot, so no shot carries a
# `:hover`. It used to be left wherever SHOT_CLICKS clicked, and SHOT_SCROLL then scrolled content
# underneath it: `SHOT_CLICKS="Men's" SHOT_SCROLL=900` on /tournaments/us-open at 390px painted one
# finished match grey, in three disjoint blocks with a white seam, while its identical siblings
# stayed white — a layout defect that did not exist. A DOM census found no grey background on any
# element, so it was invisible to a probe and visible only in the PNG. These are phone-width shots
# of a touch surface: a reader has no pointer, so a hover state in a LOOK is never evidence.
# Deliberately photographing a hover-only affordance? SHOT_KEEP_POINTER=1.
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
