#!/usr/bin/env bash
# UX-P120 item 2 — render the three pooled-category display options.
#
#   tools/pooled-label-options/run.sh                        # curl production, then render
#   tools/pooled-label-options/run.sh --no-fetch    # render the saved payload
#
# Paths are PRIVATE to this tool (#2120). It owns `/tmp/pooled-label-options/`
# and every path under it is env-overridable — see the sibling note in
# `tools/calibration-divergence/run.sh` for the collision this prevents.
#
# MOCKS ONLY. This writes a markdown one-pager and touches nothing the page
# reads. The ruling on which option ships is Alex's (Fable directive, UX-P120).
#
# Gotcha #54: never pipe a gate. Exit code is read from `$?` on its own line.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CAL_PAYLOAD="${CAL_PAYLOAD:-/tmp/pooled-label-options/cal.json}"
mkdir -p "$(dirname "$CAL_PAYLOAD")"
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

# #2120 defect 2 — THE DEGRADED WINDOW.
#
# `/api/calibration` 503s for 1–4 minutes after every release and then self-heals,
# and it also serves DATED tiers (last-good copy, previous population version)
# that answer 200 with a whole payload marked `availability: stale|degraded`. A
# truncated or error body lands in the payload file as JSON-less text, and a
# dated body sweeps clean while describing a payload nobody is looking at.
#
# Both read, downstream, as a real measurement. An empty 200 is a response shape,
# not an absence (gotcha #53) — so check the shape and say which tier answered
# before generating anything.
python3 - "$CAL_PAYLOAD" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"[options] payload is not JSON: {exc!r}")
    raise SystemExit(2)
buckets, cats = d.get("buckets") or [], d.get("by_category") or []
av = d.get("availability")
cache = (d.get("cache") or {}).get("status")
print(f"[options] payload generated_at={d.get('generated_at')} "
      f"buckets={len(buckets)} by_category={len(cats)} "
      f"availability={av} cache={cache or '-'}")
if not buckets or not cats:
    print("[options] REFUSING: an empty payload would produce output that says")
    print("         nothing pools, which is a false claim rather than an empty one.")
    raise SystemExit(2)
if av not in (None, "fresh"):
    print(f"[options] NOTE: served from a DEGRADED tier (availability={av}). The")
    print("         sweep below describes that dated copy, not the live population.")
PYEOF
rc=$?
if [ $rc -ne 0 ]; then exit $rc; fi

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
