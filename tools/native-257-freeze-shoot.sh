#!/bin/bash
# native/257 (#7019) — photograph a chip AGEING, or failing to.
#
# ═══ WHY native-shoot.sh CANNOT TAKE THIS PICTURE ═══
#
# #7019 is not a wrong number. It is a RIGHT number that stops being right while
# the reader is looking at it: Alex's My Stuff row said `In 1d 3h` beside
# `Tomorrow 1:10 PM` at 11:57, and a cold relaunch of the same build seven
# minutes later said `In 1d 1h` and was correct. **Every single frame of this
# defect is a frame of a correct-looking chip.** The evidence is the PAIR — two
# frames, minutes apart, from ONE uninterrupted session — and `native-shoot.sh`
# installs, terminates and relaunches per invocation, so two calls to it produce
# two first renders and can never show a freeze in either direction.
#
# So this launches once and photographs twice, touching nothing in between.
#
# ═══ THE SURFACE HAS TO BE ONE THAT DOES NOT REFRESH ITSELF ═══
#
# `FeedViewModel` and `MyStuffViewModel` arm a 30s / 15s auto-refresh — but BOTH
# are gated on `hasLiveGames`. A refresh republishes the rows, which re-renders
# them, which recomputes the countdown: on an afternoon with live baseball the
# Discover and My Stuff chips self-correct every half minute and the defect is
# invisible. That gate is also why Alex met it on a Friday MORNING and why it
# reads as intermittent. `TeamDetailView` and `SearchView` arm no timer at all,
# so they are the honest surfaces for this measurement — a shoot at Discover
# that comes back green has measured the live-game gate, not the fix.
#
# ═══ THE SPECIMEN HAS TO MOVE WITHIN THE GAP ═══
#
# `formatCountdown` resolves to the minute, but it PRINTS `Nd Nh` above a day
# out. A kickoff tomorrow moves its string once an hour, so a two-minute gap
# photographs a correct chip twice and reads as a freeze. Pick a fixture 1–23
# hours away, where the chip reads `Nh Nm` and one minute changes it.
#
# Usage:
#   tools/native-257-freeze-shoot.sh <label> <route> [gap-seconds]
#
#   tools/native-257-freeze-shoot.sh after bainluck://teams/texas-rangers
#   tools/native-257-freeze-shoot.sh before bainluck://search?q=Rangers 90
#
# Build the tree you mean to photograph FIRST. This refuses a binary older than
# the newest Swift source, for native-shoot.sh's reason (#5480): a shot of the
# previous build is wrong evidence and looks identical to a right one.
set -u
. "$(dirname "$0")/reserved-sim-guard.sh"
SIM="${NATIVE_SHOOT_SIM:-$(bl_default_shoot_sim)}"
: "${SIM:?no disposable iPhone simulator available — set NATIVE_SHOOT_SIM}"
bl_refuse_reserved_sim "$SIM" native-257-freeze-shoot.sh
BUNDLE=com.bainluck.Bain-Luck
OUT="${NATIVE_SHOOT_OUT:-/Users/bain/bainluck-dev/native/artifacts/native-257}"
DERIVED="${NATIVE_SHOOT_DERIVED:-$HOME/Library/Developer/Xcode/DerivedData}"

LABEL="${1:?label required, e.g. before / after}"
ROUTE="${2:?route required, e.g. bainluck://teams/texas-rangers}"
GAP="${3:-75}"

shopt -s nullglob
CANDS=( "$DERIVED"/Bain_Luck-*/Build/Products/Debug-iphonesimulator/"Bain Luck.app" )
shopt -u nullglob
APP=""
newest=0
for cand in ${CANDS[@]+"${CANDS[@]}"}; do
  m=$(stat -f %m "$cand/Bain Luck" 2>/dev/null || echo 0)
  if [ "$m" -gt "$newest" ]; then newest=$m; APP="$cand"; fi
done
[ -n "$APP" ] || { echo "NO BUILT APP FOUND — build first." >&2; exit 1; }
APP_MTIME=$newest
echo "  app  : $APP"
echo "  built: $(date -r "$APP_MTIME" '+%Y-%m-%d %H:%M:%S')"

# Stale-binary refusal, native-shoot.sh's rule and its reason.
SRC_ROOT="$( ( cd "$(dirname "${BASH_SOURCE[0]}")" && git rev-parse --show-toplevel 2>/dev/null ) || true )"
[ -n "$SRC_ROOT" ] || SRC_ROOT="$(pwd)"
NEWEST_SRC_MTIME=0
NEWEST_SRC=""
while IFS= read -r f; do
  m=$(stat -f %m "$f" 2>/dev/null || echo 0)
  if [ "$m" -gt "$NEWEST_SRC_MTIME" ]; then NEWEST_SRC_MTIME=$m; NEWEST_SRC="$f"; fi
done < <(find "$SRC_ROOT/ios" -name '*.swift' -type f 2>/dev/null)
if [ "$NEWEST_SRC_MTIME" -gt "$APP_MTIME" ]; then
  echo "  REFUSING — $(basename "$NEWEST_SRC") is newer than the binary. Rebuild." >&2
  exit 1
fi

mkdir -p "$OUT"
xcrun simctl bootstatus "$SIM" -b >/dev/null 2>&1
xcrun simctl install "$SIM" "$APP" || { echo "install failed" >&2; exit 1; }
xcrun simctl terminate "$SIM" "$BUNDLE" >/dev/null 2>&1
sleep 1

xcrun simctl launch "$SIM" "$BUNDLE" \
  -suppress_notification_prompt YES -bainluck_telemetry_consent none \
  -discover_onboarded YES -launch_route "$ROUTE" >/dev/null 2>&1

# LaunchRig.routeDelay is 2.5s and the destination then loads; 18s is
# native-shoot.sh's measured allowance for a cold screen on a cold sim.
sleep 18
T0="$OUT/$LABEL-t0.png"
xcrun simctl io "$SIM" screenshot "$T0" >/dev/null 2>&1
echo "  shot 1: $T0   ($(TZ=America/Los_Angeles date '+%H:%M:%S %Z'))"

# NOTHING happens here. No tap, no relaunch, no install, no scroll — any of
# those re-renders the row and hands back a correct chip whether or not the fix
# is present, which is the whole trap this script exists to avoid.
sleep "$GAP"

T1="$OUT/$LABEL-t${GAP}s.png"
xcrun simctl io "$SIM" screenshot "$T1" >/dev/null 2>&1
echo "  shot 2: $T1   ($(TZ=America/Los_Angeles date '+%H:%M:%S %Z'))"

# The frames are the evidence and a human reads them. A byte-diff is reported
# because it is cheap and it is a USEFUL NEGATIVE — two identical PNGs mean
# nothing on the screen moved at all, chip included — but it is NOT the verdict:
# a clock elsewhere on the page, a lazy image, or a pulse animation all move
# bytes without the chip ageing. Read both PNGs.
if cmp -s "$T0" "$T1"; then
  echo "  frames are byte-identical — NOTHING on the screen changed in ${GAP}s"
else
  echo "  frames differ — read them; something moved, and it may not be the chip"
fi
