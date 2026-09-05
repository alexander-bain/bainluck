#!/bin/bash
# native/011 Item 1 — the live-card shoot, one command per pass.
#
# Usage: tools/native_live_shoot.sh <pass-label> [event_id]
#   pass-label: e.g. P1, P2  (two passes minutes apart prove the card MOVES)
#   event_id:   optional; if given, also shoots that event's detail page
#
# Shoots Sports (Live Now) and Discover, plus the event page when an id is given.
# Every shot is preceded by a terminate so the seed re-runs from a cold launch.
#
# WHICH LAUNCH ARGUMENTS ARE REAL (#3141 — read this before trusting a shot):
#   ON MASTER, always honoured:
#     -suppress_notification_prompt YES   NotificationManager.suppressPromptKey
#     -bainluck_telemetry_consent none    TelemetryConsent.storageKey
#     -discover_onboarded YES             DiscoverView's onboarding seed
#   SCAFFOLD-ONLY, INERT unless tools/native-look-scaffold-TempScreenshot.swift.txt
#   has been hand-patched into the app first:
#     -temp_screenshot_tab / _event / _hub / _scroll
#   A scaffold-only argument does not fail — it is ignored, so the rig looks like
#   it is driving the app while the app launches on its default tab. If you did
#   not patch the scaffold in, believe the shot only for the default tab.
#
# ONE-TIME, on a simulator prompted before #3141 landed: the alert already on
# screen belongs to SpringBoard and survives install/terminate, so the first shot
# after this fix still catches a dialog the app no longer raises. Erase once:
#   xcrun simctl shutdown $SIM; xcrun simctl erase $SIM; xcrun simctl boot $SIM
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
    -suppress_notification_prompt YES -discover_onboarded YES -bainluck_telemetry_consent none \
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
