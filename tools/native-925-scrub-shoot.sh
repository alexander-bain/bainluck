#!/bin/bash
# native/309 — photograph #925's scrub readout under a synthesized finger.
#
# The readout exists only while a finger is on the chart (chartXSelection clears
# on release); tools/native-shoot.sh cannot drag and XCUITest cannot look
# mid-gesture. So: run AReaderCanScrubAGameChart925Tests (press-drag-HOLD at each
# stop) and photograph the simulator from OUTSIDE while it holds.
#
# Usage: tools/native-925-scrub-shoot.sh <label> [--route URL] [--tz ZONE] [--scroll N]
#                                        [--hold S] [--stops a,b,c] [--dry-run]
# Env:   NATIVE_SHOOT_SIM (default: bl_default_shoot_sim), NATIVE_SHOOT_OUT
# Frames: <OUT>/<label>-<HHMMSS.s>Z.png ; the test's SCRUB-STOP lines (UTC) say
# which frames fall inside which hold. Exit = xcodebuild's exit code.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/reserved-sim-guard.sh"
LABEL="${1:?label required}"; shift
ROUTE=""; TZV=""; SCROLL=""; HOLD=""; STOPS=""; DRY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --route) ROUTE="$2"; shift ;; --tz) TZV="$2"; shift ;; --scroll) SCROLL="$2"; shift ;;
    --hold) HOLD="$2"; shift ;; --stops) STOPS="$2"; shift ;; --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac; shift
done
SIM="${NATIVE_SHOOT_SIM:-$(bl_default_shoot_sim)}"
: "${SIM:?no disposable simulator — set NATIVE_SHOOT_SIM}"
bl_refuse_reserved_sim "$SIM" native-925-scrub-shoot.sh
OUT="${NATIVE_SHOOT_OUT:-$HERE/../artifacts-native-023}"
LOG="${TMPDIR:-/tmp}/native-925-scrub-$LABEL.log"
ENVS=()
[ -n "$ROUTE" ]  && ENVS+=("TEST_RUNNER_BL_SCRUB_ROUTE=$ROUTE")
[ -n "$TZV" ]    && ENVS+=("TEST_RUNNER_BL_SCRUB_TZ=$TZV")
[ -n "$SCROLL" ] && ENVS+=("TEST_RUNNER_BL_SCRUB_SCROLL=$SCROLL")
[ -n "$HOLD" ]   && ENVS+=("TEST_RUNNER_BL_SCRUB_HOLD=$HOLD")
[ -n "$STOPS" ]  && ENVS+=("TEST_RUNNER_BL_SCRUB_STOPS=$STOPS")
echo "sim $SIM · out $OUT · log $LOG · env ${ENVS[*]:-(defaults)}"
[ -n "$DRY" ] && { echo "dry-run: nothing run"; exit 0; }
mkdir -p "$OUT"
cd "$HERE/../ios/Bain Luck" || exit 2
env ${ENVS[@]+"${ENVS[@]}"} xcodebuild test -scheme BainLuckUITests -destination "id=$SIM" \
  -only-testing:BainLuckUITests/AReaderCanScrubAGameChart925Tests \
  -collect-test-diagnostics never OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
  > "$LOG" 2>&1 &
XPID=$!
N=0
while kill -0 $XPID 2>/dev/null; do
  if grep -q "SCRUB-STOP" "$LOG" 2>/dev/null; then
    T=$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime("%H%M%S.%f")[:8])')
    xcrun simctl io "$SIM" screenshot "$OUT/$LABEL-${T}Z.png" >/dev/null 2>&1 && N=$((N+1))
  fi
  sleep 1.2
done
wait $XPID; RC=$?
echo "frames: $N"
grep -o "SCRUB-STOP.*" "$LOG" | sort -u
grep -E "Executed [0-9]+ tests?, with [0-9]+ failures?" "$LOG" | sort -u | tail -1
echo "xcodebuild EXIT CODE: $RC"
exit $RC
