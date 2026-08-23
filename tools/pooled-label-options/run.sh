#!/usr/bin/env bash
# UX-P120 item 2 — render the three pooled-category display options.
#
#   tools/pooled-label-options/run.sh                        # curl production, then render
#   CAL_PAYLOAD=/tmp/cal.json tools/.../run.sh --no-fetch    # render a saved payload
#
# MOCKS ONLY. This writes a markdown one-pager and touches nothing the page
# reads. The ruling on which option ships is Alex's (Fable directive, UX-P120).
#
# Gotcha #54: never pipe a gate. Exit code is read from `$?` on its own line.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CAL_PAYLOAD="${CAL_PAYLOAD:-/tmp/cal.json}"
OPTIONS_OUT="${OPTIONS_OUT:-/tmp/pooled-label-options.md}"
LOG="${OPTIONS_LOG:-/tmp/pooled-label-options.log}"

if [ "${1:-}" != "--no-fetch" ]; then
  # shellcheck disable=SC1090
  [ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
  : "${BAINLUCK_API:=https://api.bainluck.com}"
  echo "[options] GET $BAINLUCK_API/api/calibration -> $CAL_PAYLOAD"
  curl -s --max-time 180 "$BAINLUCK_API/api/calibration" -o "$CAL_PAYLOAD" \
    -w '[options] HTTP %{http_code} bytes=%{size_download} t=%{time_total}\n'
  rc=$?
  if [ $rc -ne 0 ]; then echo "[options] curl FAILED rc=$rc"; exit 2; fi
fi

if [ ! -s "$CAL_PAYLOAD" ]; then
  echo "[options] no payload at $CAL_PAYLOAD"
  exit 2
fi

cd "$REPO_ROOT/frontend" || exit 2
CAL_PAYLOAD="$CAL_PAYLOAD" OPTIONS_OUT="$OPTIONS_OUT" \
  npx jest --config "$REPO_ROOT/tools/pooled-label-options/jest.config.js" \
  > "$LOG" 2>&1
rc=$?
echo "EXIT CODE: $rc"
if [ $rc -ne 0 ]; then
  tail -40 "$LOG"
  exit $rc
fi
echo "[options] one-pager: $OPTIONS_OUT"
