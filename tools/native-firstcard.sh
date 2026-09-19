#!/bin/zsh
# native/003 — cold-open -> first REAL card on the simulator, Discover and Sports.
#
# Reads the app's OWN rails (DEBUG measurement tap in AnalyticsService.log) rather
# than video, so every number is the app's tested clock rather than a frame guess.
# The tap stamps LAUNCHMS = milliseconds since AppLaunchClock.start, which is set
# in Bain_LuckApp.init() — as close to process start as app code can get.
#
# Usage: native-firstcard.sh <discover|sports> <runs> <outdir>
#
# 🔴 THIS TOOL TERMINATES THE APP, DELETES ITS CACHES AND RELAUNCHES IT, SIX
# TIMES OVER. It resolved its target as the literal string `booted` at every one
# of those call sites, and `booted` is whatever simulator happens to be running —
# which, for four sessions running, has been Alex's signed-in `DD0DC456`. Every
# other rig entrypoint grew the shared guard on 2026-09-17/18 (#6444 row 19);
# this one was missed because it takes no device argument at all, so there was
# nothing that LOOKED like a device to guard. An implicit target is still a
# target. It now resolves a disposable iPhone through the same helper as
# `native-shoot.sh` and refuses a reserved one.
set -u
. "$(dirname "$0")/reserved-sim-guard.sh"
SIM="${NATIVE_SHOOT_SIM:-$(bl_default_shoot_sim)}"
: "${SIM:?no disposable iPhone simulator available — set NATIVE_SHOOT_SIM}"
bl_refuse_reserved_sim "$SIM" native-firstcard.sh

BUNDLE=com.bainluck.Bain-Luck
MODE=${1:?mode}
RUNS=${2:?runs}
OUT=${3:?outdir}
mkdir -p "$OUT"

# The device must be running before any of this measures anything; `booted`
# used to supply that by accident. Booting is idempotent and a no-op when it
# already is.
xcrun simctl boot "$SIM" >/dev/null 2>&1 || true
xcrun simctl bootstatus "$SIM" -b >/dev/null 2>&1 || true
echo "  device: $SIM"

CONT=$(xcrun simctl get_app_container "$SIM" "$BUNDLE" data)
# 🪤 AN EMPTY $CONT MAKES THE LOOP BELOW `rm -rf "/Library/Caches"`. That is one
# unquoted absence away from the host's own cache directory, and the app not
# being installed on the target is the ordinary case, not an exotic one — the
# uitest script uninstalls it per invocation. So the container is REFUSED unless
# it is a real directory, rather than being interpolated into a destructive
# command and left to SIP to decline.
case "${CONT:-}" in
  /*) ;;
  *)  echo "native-firstcard.sh: no app container for $BUNDLE on $SIM" >&2
      echo "  (install the app on that device first — nothing was measured)" >&2
      exit 2 ;;
esac
[ -d "$CONT" ] || { echo "native-firstcard.sh: container path is not a directory: $CONT" >&2; exit 2; }

for i in $(seq 1 "$RUNS"); do
  xcrun simctl terminate "$SIM" "$BUNDLE" >/dev/null 2>&1
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
    xcrun simctl launch "$SIM" "$BUNDLE" -startTabSports >/dev/null 2>&1
  else
    xcrun simctl launch "$SIM" "$BUNDLE" >/dev/null 2>&1
  fi

  # 3s: a visual check that a REAL card, not a skeleton, is what the rail counted.
  sleep 3
  xcrun simctl io "$SIM" screenshot "$OUT/$MODE-run$i-3s.png" >/dev/null 2>&1

  # 22s total > the 20s blank bar in the ask and > the rail's 10s no_card deadline.
  sleep 19
  {
    echo "===== $MODE run $i (launched $START) ====="
    xcrun simctl spawn "$SIM" log show \
      --predicate 'subsystem == "com.bainluck.latency"' \
      --start "$START" --info --style compact 2>/dev/null \
      | grep -v "getpwuid_r\|^Timestamp"
  } >> "$OUT/$MODE-rails.txt"
  echo "  $MODE run $i done"
done
