#!/usr/bin/env bash
# native — drive one screen of the app in a simulator and photograph it.
#
# WHY THIS EXISTS
# ---------------
# `LaunchRig` (ios/.../Utilities/LaunchRig.swift) already gives the app three
# launch arguments — `-launch_route`, `-launch_scroll`, `-launch_expand_sections`
# — and they are the ONLY way an unattended session can reach a screen that is
# not the default tab: this sandbox has no macOS Accessibility permission, so
# `osascript`/System Events taps fail with error -54 and there is no `cliclick`
# and no `idb`. Every native walkthrough therefore re-types the same four-step
# incantation (terminate, launch with args, sleep long enough, screenshot) by
# hand, and the two ways it silently lies are both easy to hit:
#
#   1. NOT TERMINATING FIRST. `simctl launch` on an already-running app
#      foregrounds it and the `.task` that reads the launch arguments never runs
#      again — so the rig photographs the PREVIOUS screen while appearing to
#      have navigated. The shot looks fine; it is of the wrong page.
#   2. SCREENSHOTTING TOO EARLY. LaunchRig's own waits are routeDelay 2.5s and
#      scrollDelay +8s, so a shot taken at 5s catches a half-mounted screen that
#      reads as "the content is missing" — manufacturing the exact finding a
#      mystery shop exists to test for.
#
# So this waits past the rig's own delays by construction (it reads them from
# the Swift file rather than hardcoding a guess) and always cold-starts.
#
# It also suppresses the notification permission prompt, via the app's OWN
# affordance (`-suppress_notification_prompt`, NotificationManager.swift). That
# alert lands over Discover 5s after launch and this sandbox cannot dismiss it,
# so without this every shot after the first is a photograph of a system dialog.
# `simctl privacy revoke notifications` is NOT the way — the simulator refuses
# that service (measured 2026-09-14) and exits 0 while doing nothing. Pass
# NATIVE_WALK_PROMPT=1 to leave the prompt in, which is what you want for the
# one first-run shot where the prompt IS the subject.
#
# READ-ONLY with respect to production: every screen this opens is a GET the app
# would make anyway. It signs nothing in, writes nothing, and cannot reach an
# authenticated surface.
#
# USAGE
#   tools/native-walk.sh <device-udid> <out.png> [route] [scroll-points]
#   tools/native-walk.sh "$DEV" shots/01-discover.png
#   tools/native-walk.sh "$DEV" shots/05-event.png "bainluck://events/15310222" 1600
set -uo pipefail

BUNDLE="com.bainluck.Bain-Luck"
DEV="${1:?device udid}"
OUT="${2:?output png path}"
ROUTE="${3:-}"
SCROLL="${4:-}"

mkdir -p "$(dirname "$OUT")"

# Read the rig's own waits out of the source rather than restating them: a
# hardcoded sleep here goes stale the moment someone tunes routeDelay, and it
# goes stale SILENTLY (an early shot looks like missing content, not like a bug
# in this script).
# Resolve LaunchRig.swift from this script's own repo, so the waits stay tied to
# the source being walked no matter which worktree the rig runs from.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RIG="$REPO/ios/Bain Luck/Bain Luck/Utilities/LaunchRig.swift"
route_delay=3
scroll_delay=8
if [ -f "$RIG" ]; then
  rd=$(/usr/bin/grep -o 'routeDelay: TimeInterval = [0-9.]*' "$RIG" | /usr/bin/grep -o '[0-9.]*$')
  sd=$(/usr/bin/grep -o 'scrollDelay: TimeInterval = [0-9.]*' "$RIG" | /usr/bin/grep -o '[0-9.]*$')
  [ -n "${rd:-}" ] && route_delay=$rd
  [ -n "${sd:-}" ] && scroll_delay=$sd
fi

# Network loads, not just mounting. The rig's routeDelay only covers "the app is
# mounted"; the destination's own fetches land after it.
SETTLE=${NATIVE_WALK_SETTLE:-11}

args=()
# Two first-run gates stand between a cold launch and the feed, and BOTH must be
# answered or every shot is a photograph of a consent card:
#   - the app's own telemetry sheet ("Help us find what's broken?"), which is a
#     SwiftUI .sheet over the whole app. `none` is exactly what "No thanks"
#     records (ConsentLevel.none, TelemetryConsent.storageKey), so this walks the
#     app as a reader who declined — the conservative choice, and the one that
#     turns analytics OFF rather than on.
#   - the system notification alert, via the app's own -suppress_notification_prompt.
# NATIVE_WALK_FIRSTRUN=1 leaves both in, for the one shot where first run IS the
# subject.
if [ "${NATIVE_WALK_FIRSTRUN:-0}" != "1" ]; then
  args+=(-bainluck_telemetry_consent none)
  [ "${NATIVE_WALK_PROMPT:-0}" = "1" ] || args+=(-suppress_notification_prompt YES)
fi
[ -n "$ROUTE" ]  && args+=(-launch_route "$ROUTE")
[ -n "$SCROLL" ] && args+=(-launch_scroll "$SCROLL")

xcrun simctl terminate "$DEV" "$BUNDLE" >/dev/null 2>&1
sleep 1
xcrun simctl launch "$DEV" "$BUNDLE" ${args[@]+"${args[@]}"} >/dev/null || {
  echo "WALK: launch FAILED for route='${ROUTE:-<default>}'" >&2; exit 1; }

# routeDelay, then the destination's network, then (only if asked) scrollDelay.
wait_for=$(python3 -c "print($route_delay + $SETTLE + (${scroll_delay} if '${SCROLL}' else 0))")
sleep "$wait_for"

xcrun simctl io "$DEV" screenshot "$OUT" >/dev/null 2>&1 || {
  echo "WALK: screenshot FAILED -> $OUT" >&2; exit 1; }

# A zero-byte or absent PNG is the failure that reads like a pass downstream.
if [ ! -s "$OUT" ]; then echo "WALK: EMPTY png -> $OUT" >&2; exit 1; fi
echo "WALK ok  route='${ROUTE:-<default tab>}' scroll='${SCROLL:-none}' waited=${wait_for}s -> $OUT"
