#!/bin/zsh
# native/003 — cold-open -> first REAL card on the simulator, Discover and Sports.
#
# Reads the app's OWN rails (DEBUG measurement tap in AnalyticsService.log) rather
# than video, so every number is the app's tested clock rather than a frame guess.
# The tap stamps LAUNCHMS = milliseconds since AppLaunchClock.start, which is set
# in Bain_LuckApp.init() — as close to process start as app code can get.
#
# Usage: native-firstcard.sh <discover|sports> <runs> <outdir>
set -u

BUNDLE=com.bainluck.Bain-Luck
MODE=${1:?mode}
RUNS=${2:?runs}
OUT=${3:?outdir}
mkdir -p "$OUT"

CONT=$(xcrun simctl get_app_container booted "$BUNDLE" data)

for i in $(seq 1 "$RUNS"); do
  xcrun simctl terminate booted "$BUNDLE" >/dev/null 2>&1
  sleep 1
  # Cold network state: drop URLCache + the Discover last-good feed cache.
  # Preferences survive on purpose — consent and the onboarding flag are
  # answered, which is the state Alex's phone is actually in.
  rm -rf "$CONT/Library/Caches"
  sleep 1

  START=$(date '+%Y-%m-%d %H:%M:%S')
  if [ "$MODE" = "sports" ]; then
    # Lands the cold launch ON Sports. NOT "launch then tap": a custom-scheme
    # openurl raises an "Open in Bain Luck?" confirmation that cannot be tapped
    # unattended here. So this is the Sports pipeline in isolation — no Discover
    # fetch competing for the link — and therefore a FLOOR for a real tap-through.
    xcrun simctl launch booted "$BUNDLE" -startTabSports >/dev/null 2>&1
  else
    xcrun simctl launch booted "$BUNDLE" >/dev/null 2>&1
  fi

  # 3s: a visual check that a REAL card, not a skeleton, is what the rail counted.
  sleep 3
  xcrun simctl io booted screenshot "$OUT/$MODE-run$i-3s.png" >/dev/null 2>&1

  # 22s total > the 20s blank bar in the ask and > the rail's 10s no_card deadline.
  sleep 19
  {
    echo "===== $MODE run $i (launched $START) ====="
    xcrun simctl spawn booted log show \
      --predicate 'subsystem == "com.bainluck.latency"' \
      --start "$START" --info --style compact 2>/dev/null \
      | grep -v "getpwuid_r\|^Timestamp"
  } >> "$OUT/$MODE-rails.txt"
  echo "  $MODE run $i done"
done
