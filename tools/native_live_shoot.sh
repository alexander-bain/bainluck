#!/bin/bash
# native/011 Item 1 — the live-card shoot, one command per pass.
#
# Usage: tools/native_live_shoot.sh <pass-label> [event_id]
#   pass-label: e.g. P1, P2  (two passes minutes apart prove the card MOVES)
#   event_id:   optional; if given, also shoots that event's detail page
#
# Shoots Sports (Live Now) and Discover, plus the event page when an id is given.
# Every shot is preceded by a terminate so the seed re-runs from a cold launch.
set -u
SIM=76D961F0-8575-479F-ABCE-652D8A79DBF9
BUNDLE=com.bainluck.Bain-Luck
A=/Users/bain/bainluck-dev/native/artifacts-native-011
PASS="${1:?pass label required, e.g. P1}"
EVENT="${2:-}"
mkdir -p "$A"

shoot () {   # shoot <name> <launch-args...>
  local name="$1"; shift
  xcrun simctl terminate "$SIM" "$BUNDLE" >/dev/null 2>&1
  sleep 1
  xcrun simctl launch "$SIM" "$BUNDLE" \
    -temp_screenshot_quiet YES -discover_onboarded YES -bainluck_telemetry_consent none \
    "$@" >/dev/null 2>&1
  sleep 17
  xcrun simctl io "$SIM" screenshot "$A/${PASS}-${name}.png" >/dev/null 2>&1 \
    && echo "  shot ${PASS}-${name}.png"
}

echo "== pass $PASS  $(date -u +%H:%M:%SZ) =="
shoot sports   -temp_screenshot_tab sports
shoot discover -temp_screenshot_tab discover
if [ -n "$EVENT" ]; then
  shoot event-"$EVENT" -temp_screenshot_event "$EVENT"
fi
echo "== pass $PASS done  $(date -u +%H:%M:%SZ) =="
