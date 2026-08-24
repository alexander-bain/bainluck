#!/usr/bin/env bash
# UX-P122 item C — generate the ruled Option-C wording from the LIVE payload.
#
#   tools/option-c-staging/run.sh                 # curl production, then generate
#   tools/option-c-staging/run.sh --no-fetch      # generate from the saved payload
#
# ## Every path here is PRIVATE, and that is the whole of #2120's first defect
#
# Three tools in this repo USED TO default to `/tmp/cal.json`: one treated it as a
# frozen baseline, two `curl -o`d into it. UX-P121 watched that produce
# `calibration: FAIL — keys DISAPPEARED` against a payload that had not changed —
# the baseline's mtime was five seconds NEWER than the fresh fetch it was being
# compared against. The tell was a timestamp, not a value, which is why it took a
# cycle to see.
#
# So this tool never touched it. It owns `/tmp/option-c-staging/` and every path
# under it is overridable. #2120 (UX-P125) gave the other three the same
# treatment: `/tmp/cal-baseline/`, `/tmp/calibration-divergence/`,
# `/tmp/pooled-label-options/`. A new tool that defaults into a shared file is a
# new instance of that bug, and there is no reason to write one.
#
# Gotcha #54: never pipe a gate. The exit code is read from `$?` on its own line.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${OPTIONC_DIR:-/tmp/option-c-staging}"
PAYLOAD="${OPTIONC_PAYLOAD:-$WORK/cal.json}"
OUT_MD="${OPTIONC_OUT_MD:-$WORK/wording.md}"
OUT_JSON="${OPTIONC_OUT_JSON:-$WORK/wording.json}"
LOG="${OPTIONC_LOG:-$WORK/run.log}"

mkdir -p "$WORK"

if [ "${1:-}" != "--no-fetch" ]; then
  # shellcheck disable=SC1090
  [ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
  : "${BAINLUCK_API:=https://api.bainluck.com}"
  echo "[option-c] GET $BAINLUCK_API/api/calibration -> $PAYLOAD"
  curl -s --max-time 180 "$BAINLUCK_API/api/calibration" -o "$PAYLOAD" \
    -w '[option-c] HTTP %{http_code} bytes=%{size_download} t=%{time_total}\n'
  rc=$?
  if [ $rc -ne 0 ]; then echo "[option-c] curl FAILED rc=$rc"; exit 2; fi
fi

if [ ! -s "$PAYLOAD" ]; then
  echo "[option-c] no payload at $PAYLOAD"
  exit 2
fi

# `/api/calibration` 503s for 1–4 minutes after every release and then self-heals.
# A truncated or error body parses as JSON-less and would produce an empty
# staging file that reads exactly like "nothing pools" — check the shape before
# generating anything (gotcha #53).
python3 - "$PAYLOAD" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"[option-c] payload is not JSON: {exc!r}")
    raise SystemExit(2)
buckets, cats = d.get("buckets") or [], d.get("by_category") or []
av = d.get("availability")
cache = (d.get("cache") or {}).get("status")
print(f"[option-c] payload generated_at={d.get('generated_at')} "
      f"buckets={len(buckets)} by_category={len(cats)} "
      f"availability={av} cache={cache or '-'}")
if not buckets or not cats:
    print("[option-c] REFUSING to generate: an empty payload would stage a wording")
    print("           that says nothing pools, which is a false claim, not an empty one.")
    raise SystemExit(2)
if av not in (None, "fresh"):
    # #2120: a DATED tier answers 200 with a whole payload. It sweeps clean while
    # describing a copy nobody is looking at, so say which tier answered.
    print(f"[option-c] NOTE: served from a DEGRADED tier (availability={av}). The")
    print("           wording below describes that dated copy, not the live population.")
PY
rc=$?
if [ $rc -ne 0 ]; then exit $rc; fi

cd "$REPO_ROOT/frontend" || exit 2
OPTIONC_PAYLOAD="$PAYLOAD" OPTIONC_OUT_MD="$OUT_MD" OPTIONC_OUT_JSON="$OUT_JSON" \
  npx jest --config "$REPO_ROOT/tools/option-c-staging/jest.config.js" \
  > "$LOG" 2>&1
rc=$?
echo "EXIT CODE: $rc"
if [ $rc -ne 0 ]; then
  tail -40 "$LOG"
  exit $rc
fi
echo "[option-c] wording:  $OUT_MD"
echo "[option-c] machine:  $OUT_JSON"
