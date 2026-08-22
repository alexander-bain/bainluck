#!/usr/bin/env bash
# UX-P119 item 1 — run the normalizeCat divergence sweep against a live payload.
#
#   tools/calibration-divergence/run.sh              # curl production, then sweep
#   CAL_PAYLOAD=/tmp/cal.json tools/.../run.sh --no-fetch   # sweep a saved payload
#
# Exit codes are the runner's, not the finding's: this is a MEASUREMENT, so a
# divergence is reported in the table and does not fail the run. Non-zero means
# the sweep could not be performed (no payload, jest could not start).
#
# Gotcha #54: never pipe a gate. Output is redirected to a file and the exit code
# is read from `$?` on its own line.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CAL_PAYLOAD="${CAL_PAYLOAD:-/tmp/cal.json}"
SWEEP_OUT="${SWEEP_OUT:-/tmp/normalizeCat-divergence.md}"
LOG="${SWEEP_LOG:-/tmp/normalizeCat-divergence.log}"

if [ "${1:-}" != "--no-fetch" ]; then
  # shellcheck disable=SC1090
  [ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
  : "${BAINLUCK_API:=https://api.bainluck.com}"
  echo "[sweep] GET $BAINLUCK_API/api/calibration -> $CAL_PAYLOAD"
  curl -s --max-time 180 "$BAINLUCK_API/api/calibration" -o "$CAL_PAYLOAD" \
    -w '[sweep] HTTP %{http_code} bytes=%{size_download} t=%{time_total}\n'
  rc=$?
  if [ $rc -ne 0 ]; then echo "[sweep] curl FAILED rc=$rc"; exit 2; fi
fi

if [ ! -s "$CAL_PAYLOAD" ]; then
  echo "[sweep] no payload at $CAL_PAYLOAD"
  exit 2
fi

cd "$REPO_ROOT/frontend" || exit 2
CAL_PAYLOAD="$CAL_PAYLOAD" SWEEP_OUT="$SWEEP_OUT" \
  npx jest --config "$REPO_ROOT/tools/calibration-divergence/jest.config.js" \
  > "$LOG" 2>&1
rc=$?
echo "EXIT CODE: $rc"
if [ $rc -ne 0 ]; then
  tail -40 "$LOG"
  exit $rc
fi
echo "[sweep] report: $SWEEP_OUT"
cat "$SWEEP_OUT"
