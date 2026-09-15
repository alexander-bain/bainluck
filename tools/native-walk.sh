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
# THREE first-run gates stand between a cold launch and the feed, and ALL must be
# answered or every shot is a photograph of a consent card:
#   - the app's own telemetry sheet ("Help us find what's broken?"), which is a
#     SwiftUI .sheet over the whole app. `none` is exactly what "No thanks"
#     records (ConsentLevel.none, TelemetryConsent.storageKey), so this walks the
#     app as a reader who declined — the conservative choice, and the one that
#     turns analytics OFF rather than on.
#   - the system notification alert, via the app's own -suppress_notification_prompt.
#   - DiscoverView's welcome sheet (`discover_onboarded`), the carousel that opens
#     "What the world thinks will happen" with Continue/Skip. It was missing here
#     until 2026-09-15 (native/172) and the omission is invisible on a container
#     that has already been through it — which every long-lived simulator has, so
#     the gap only shows on a genuinely clean install or after `simctl erase`, and
#     then EVERY route photographs the carousel while the log still says WALK ok.
#     `WelcomeView`'s own `onDisappear` writes this key, so setting it is the same
#     answer a reader gives by tapping Skip. BainLuckUITests/UITestLaunch.swift
#     has carried it since 2026-09-14; this file is the other consumer of the same
#     three gates and had only two.
# NATIVE_WALK_FIRSTRUN=1 leaves all three in, for the one shot where first run IS
# the subject.
if [ "${NATIVE_WALK_FIRSTRUN:-0}" != "1" ]; then
  args+=(-bainluck_telemetry_consent none)
  args+=(-discover_onboarded YES)
  [ "${NATIVE_WALK_PROMPT:-0}" = "1" ] || args+=(-suppress_notification_prompt YES)
  # Notice 39 — our own robots are tagged, never minted. Opening a route IS a
  # card open, and a card open POSTs to /api/feed/interactions, which is the
  # reader's downrank signal. The UI-test target has passed this since it was
  # written; this script opens the same routes and did not.
  args+=(-launch_no_interaction_upload YES)
fi
[ -n "$ROUTE" ]  && args+=(-launch_route "$ROUTE")
[ -n "$SCROLL" ] && args+=(-launch_scroll "$SCROLL")

# ── DOES THIS SCRIPT ANSWER EVERY GATE THE UI-TEST TARGET ANSWERS? ───────────
# The two consumers of the app's launch-argument channel are this script and
# BainLuckUITests/UITestLaunch.swift, and they drifted: the welcome carousel was
# added to that file on 2026-09-14 and never here. The drift is INVISIBLE on a
# container that has already been through the gate — which every long-lived
# simulator has — so it surfaces only after `simctl erase`, and then every route
# photographs a modal while this script still prints `WALK ok`. A wrong shot
# that announces itself as a right one is the failure this whole file exists to
# prevent, so the drift is a STOP, not a warning.
#
# Keys only, never values: the UI-test target answers `-discover_onboarded NO`
# when it is deliberately re-arming the gates, and that is not drift.
#
# It reads the `args+=` LINES, not the file — measured 2026-09-15: a whole-file
# scan passes on a script that only MENTIONS the key in this very comment, so
# deleting the line that sends it left the guard green and the walk still
# photographed the carousel. A guard whose own prose satisfies it is no guard.
GATES_SRC="$REPO/ios/Bain Luck/BainLuckUITests/UITestLaunch.swift"
if [ -f "$GATES_SRC" ]; then
  missing=""
  # CONTAINING, not starting with: the notification gate is sent from the tail
  # of a `[ … ] || args+=(…)` line, and an anchored pattern silently declared
  # the one gate this script has always answered to be missing.
  sent="$(/usr/bin/grep -F 'args+=(' "$0")"
  for key in $(/usr/bin/sed -n 's/^[[:space:]]*"\(-[A-Za-z_]*\)",.*/\1/p' "$GATES_SRC"); do
    printf '%s\n' "$sent" | /usr/bin/grep -q -- "\\$key" || missing="$missing $key"
  done
  if [ -n "$missing" ]; then
    echo "WALK: FIRST-RUN GATE MISSING —$missing" >&2
    echo "  UITestLaunch.swift answers it and this script does not. On a clean" >&2
    echo "  container every shot photographs that gate and the log still says ok." >&2
    exit 2
  fi
fi

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
