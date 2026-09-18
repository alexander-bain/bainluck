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
# A THIRD WAY IT LIES, AND THE ONLY ONE THAT SURVIVES BOTH FIXES ABOVE: the shot
# is of the right app at the right moment and is STILL the previous frame. Two
# measured instances, a day apart, both found by hashing PNGs by hand:
#
#   - native/204: `native-gates.sh` runs BainLuckTests, whose host app launches
#     WITHOUT -suppress_notification_prompt, so the permission alert is left on
#     SpringBoard. Every later walk photographs the DIALOG — two frames two
#     minutes apart, one of them supposedly scrolled 1800pt, were identical.
#   - native/203: a scroll that never applied. Same route, different `-launch_scroll`,
#     byte-identical frame.
#
# Neither is visible in the log: the terminate worked, the launch worked, the
# PNG is non-empty, and the script prints `WALK ok`. It is only visible if you
# compare the frames — which is why this now does it, and why a no-op is a STOP.
# Live prices and the clock move between any two honest shots of this app, so a
# byte-identical pair is not a coincidence worth tolerating.
#
# USAGE
#   tools/native-walk.sh <device-udid> <out.png> [route] [scroll-points]
#   tools/native-walk.sh "$DEV" shots/01-discover.png
#   tools/native-walk.sh "$DEV" shots/05-event.png "bainluck://events/15310222" 1600
#   tools/native-walk.sh --selftest   # prove the no-op rule. No simulator, no tree.
set -uo pipefail

BUNDLE="com.bainluck.Bain-Luck"

# ── frame-twin detection (the no-op guard) ───────────────────────────────────
# PURE: reads a ledger path and three strings, sets three globals, prints
# nothing — so `--selftest` drives THE SAME function the real walk calls. A copy
# of this logic inside a test would prove nothing about this script.
#
#   FRAME_VERDICT     NEW | DUP_OTHER_WALK | DUP_SAME_WALK
#   FRAME_TWIN        the earlier shot carrying this exact frame
#   FRAME_TWIN_PARAMS the walk parameters that earlier shot was taken with
#
# The two verdicts are kept apart because they mean different things to the
# reader: DUP_OTHER_WALK is the rig failing to move (a dead scroll, a modal
# drawn over every route); DUP_SAME_WALK is a before/after that is one frame
# filed twice. Both are a STOP — the escape hatch is explicit, see below.
frame_check () {   # <sha256> <params> <ledger> <this-out-path>
  _fc_hash="$1"; _fc_params="$2"; _fc_ledger="$3"; _fc_path="$4"
  FRAME_VERDICT=NEW; FRAME_TWIN=""; FRAME_TWIN_PARAMS=""
  [ -f "$_fc_ledger" ] || return 0
  while IFS="$(printf '\t')" read -r _h _p _q; do
    [ -n "${_h:-}" ] || continue
    [ "$_h" = "$_fc_hash" ] || continue
    # Re-shooting the SAME output path replaces its own earlier row: a frame is
    # never a twin of itself. Keyed on the PATH, not the hash, so a genuine
    # re-shoot that lands a different frame still clears the stale row below.
    [ "${_q:-}" = "$_fc_path" ] && continue
    FRAME_TWIN="$_q"; FRAME_TWIN_PARAMS="$_p"
    if [ "$_p" = "$_fc_params" ]; then
      FRAME_VERDICT=DUP_SAME_WALK
    else
      FRAME_VERDICT=DUP_OTHER_WALK
    fi
    return 0
  done < "$_fc_ledger"
  return 0
}

# ── --selftest: prove the rule above, on synthetic ledgers, with no simulator ─
if [ "${1:-}" = "--selftest" ]; then
  ST_FAIL=0
  _st_dir="$(mktemp -d)"; _st_led="$_st_dir/frames.tsv"
  st () {  # <case> <expected-verdict> <hash> <params> <path>
    frame_check "$3" "$4" "$_st_led" "$5"
    if [ "$FRAME_VERDICT" = "$2" ]; then
      echo "  ok    $1 -> $FRAME_VERDICT"
    else
      echo "  FAIL  $1 -> $FRAME_VERDICT (expected $2)"; ST_FAIL=$((ST_FAIL+1))
    fi
  }
  echo "--selftest — walk frame no-op rule (no simctl, no tree needed)"

  # 1. An absent ledger must not crash and must not accuse.
  st "absent ledger           " NEW "aaa" "route=X scroll=none" "shots/01.png"

  printf 'aaa\troute=X scroll=none\tshots/01.png\n'   >  "$_st_led"
  printf 'bbb\troute=Y scroll=none\tshots/02.png\n'   >> "$_st_led"
  printf 'ccc\troute=Y scroll=1600\tshots/03.png\n'   >> "$_st_led"

  # 2. THE CONTROL. A genuinely new frame must read NEW — without this the
  #    whole guard could be a function that returns a STOP for every input and
  #    every other case below would still pass.
  st "new frame               " NEW "zzz" "route=Z scroll=none" "shots/04.png"

  # 3. The native/204 shape: a different route photographed the same pixels.
  st "twin, different route   " DUP_OTHER_WALK "aaa" "route=Z scroll=none" "shots/04.png"

  # 4. The native/203 shape: same route, a scroll that never applied.
  st "twin, dead scroll       " DUP_OTHER_WALK "bbb" "route=Y scroll=1600" "shots/04.png"

  # 5. A before/after filed twice — same walk, same pixels.
  st "twin, same walk         " DUP_SAME_WALK  "ccc" "route=Y scroll=1600" "shots/04.png"

  # 6. A re-shoot of one path is not a twin of itself.
  st "re-shoot of same path   " NEW "aaa" "route=X scroll=none" "shots/01.png"

  # 7. Matching is on the FRAME, not the path: the same path name in a different
  #    directory carrying a known frame is still a twin.
  st "twin under another dir  " DUP_OTHER_WALK "aaa" "route=Q scroll=none" "other/01.png"

  # 8. Params differing only by first-run gates still count as a different walk,
  #    because those gates change what is on the screen.
  st "twin, firstrun differs  " DUP_OTHER_WALK "aaa" "route=X scroll=none firstrun=1" "shots/05.png"

  rm -rf "$_st_dir"
  echo "done (--selftest) — $([ $ST_FAIL -eq 0 ] && echo 'all cases passed' || echo 'FAILURES ABOVE'); nothing was launched"
  exit $([ $ST_FAIL -eq 0 ] && echo 0 || echo 1)
fi

# This script is POSITIONAL, and its sibling rig has already been bitten by that
# (`look.sh --width 390 out.png` silently took `--width` as the OUTPUT PATH and
# shot nothing). So an unrecognised leading flag is a STOP here, not a udid.
case "${1:-}" in
  -*) echo "WALK: '$1' is not a device udid. This script takes POSITIONAL args:" >&2
      echo "  tools/native-walk.sh <device-udid> <out.png> [route] [scroll-points]" >&2
      echo "  tools/native-walk.sh --selftest" >&2
      exit 2 ;;
esac
case "${2:-}" in
  -*) echo "WALK: '$2' is not an output path (positional arg 2)." >&2; exit 2 ;;
esac

DEV="${1:?device udid}"
OUT="${2:?output png path}"

# The udid arrives from the caller, so the caller can hand us Alex's reserved
# device by copy-paste. This walk installs and launches; refuse it here too.
. "$(dirname "$0")/reserved-sim-guard.sh"
bl_refuse_reserved_sim "$DEV" native-walk.sh
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

# ── is this frame one we have already filed? ─────────────────────────────────
# The ledger lives beside the shots, so it is scoped to one walk the way a
# reader thinks of one: a directory of frames. NATIVE_WALK_NO_LEDGER=1 turns the
# whole check off; NATIVE_WALK_ALLOW_DUPLICATE=1 keeps recording but downgrades a
# twin to a warning, which is what you want for a deliberate control — a pair
# that is SUPPOSED to be identical because the change under test should not have
# moved this screen.
if [ "${NATIVE_WALK_NO_LEDGER:-0}" != "1" ]; then
  LEDGER="${NATIVE_WALK_LEDGER:-$(dirname "$OUT")/.native-walk-frames.tsv}"
  HASH="$(shasum -a 256 "$OUT" | awk '{print $1}')"
  # The gates belong in the identity of a walk: they change what is on screen,
  # so two shots that differ only by them are genuinely different walks.
  PARAMS="route=${ROUTE:-<default tab>} scroll=${SCROLL:-none} firstrun=${NATIVE_WALK_FIRSTRUN:-0} prompt=${NATIVE_WALK_PROMPT:-0}"

  frame_check "$HASH" "$PARAMS" "$LEDGER" "$OUT"

  if [ "$FRAME_VERDICT" != "NEW" ]; then
    {
      echo "WALK: NO-OP FRAME — this shot is byte-identical to one already taken."
      echo "  this shot : $OUT"
      echo "              $PARAMS"
      echo "  twin      : $FRAME_TWIN"
      echo "              $FRAME_TWIN_PARAMS"
      echo "  sha256    : $HASH"
      if [ "$FRAME_VERDICT" = "DUP_OTHER_WALK" ]; then
        echo "  Two DIFFERENT walks produced one frame, so the app did not move."
        echo "  Most likely: a system dialog is drawn over every route (run"
        echo "  'xcrun simctl shutdown \$DEV && xcrun simctl boot \$DEV' — a"
        echo "  BainLuckTests run leaves the notification alert on SpringBoard),"
        echo "  or -launch_scroll never applied."
      else
        echo "  The SAME walk twice, pixel for pixel — a before and an after that"
        echo "  hash the same are one frame filed twice. Live prices and the clock"
        echo "  move between two honest shots of this app."
      fi
      echo "  Deliberate control? NATIVE_WALK_ALLOW_DUPLICATE=1. Off entirely:"
      echo "  NATIVE_WALK_NO_LEDGER=1."
    } >&2
    [ "${NATIVE_WALK_ALLOW_DUPLICATE:-0}" = "1" ] || exit 3
  fi

  # Record it, dropping any earlier row for THIS path so a re-shoot replaces
  # itself rather than accumulating a stale frame that can never match again.
  if [ -f "$LEDGER" ]; then
    _tmp="$LEDGER.$$"
    awk -F'\t' -v p="$OUT" '$3 != p' "$LEDGER" > "$_tmp" 2>/dev/null && mv "$_tmp" "$LEDGER"
  fi
  printf '%s\t%s\t%s\n' "$HASH" "$PARAMS" "$OUT" >> "$LEDGER"
fi

echo "WALK ok  route='${ROUTE:-<default tab>}' scroll='${SCROLL:-none}' waited=${wait_for}s -> $OUT"
