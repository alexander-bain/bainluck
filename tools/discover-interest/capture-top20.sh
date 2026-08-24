#!/usr/bin/env bash
# UX-P124 item 1 — capture ONE Discover top-20 pull, three surfaces, as JSONL.
#
# MEASUREMENT ONLY. Read-only against production: every request is a GET, and the
# only admin surface touched is `debug=true`, which the route itself documents as
# cache-disabled and side-effect-free. Nothing here writes a Redis key, and in
# particular nothing touches `interestingness:blend_weight` — see the dark ruling
# (LAT-P043, Alex 2026-08-12) and `interestingness-side-by-side`'s own docstring.
#
# THREE SURFACES, because "what Discover serves" is three different questions and
# a single pull answers only one of them:
#
#   anon    — GET /api/feed?limit=20 with no identity at all. This is the cached,
#             pre-warmed serve a brand-new visitor gets. It is also the ONLY one
#             of the three that the response cache serves, so its churn is bounded
#             below by the cache TTL, not by the ranker.
#   session — the same call carrying a STABLE `x-session-id`. This is the returning
#             user: personalization context loads, and impression suppression
#             (DiscoverInteraction / user_seen_markets) applies. The whole "open it
#             twice a day" question lives on THIS surface, not on `anon` — an anon
#             pull cannot show you what a returning user is spared or re-shown.
#   debug   — GET /api/feed?limit=20&debug=true with the admin bearer. Returns
#             `debug_items` (per-card category/archetype/quality_class/family_key/
#             story_key/reasons) and `debug_summary`. `cache: disabled_debug`, so
#             this one is always a COLD build and always ~5 s. It is the component
#             view item 2 needs; it is NOT what a user is served, and it runs
#             `debug_global` so personalization is deliberately off.
#
# Every pull records the FULL payload. That is ~200 KB/pull and deliberately
# unparsed: the analysis questions for cycle one are not settled yet, and a
# capture that pre-summarises is a capture you have to re-run when the question
# moves. Decide later, from the raw.
#
# USAGE
#   ./capture-top20.sh                 # one pull of all three surfaces
#   OUT_DIR=/tmp/foo ./capture-top20.sh
#   SESSION_ID=ux-p124-returning ./capture-top20.sh
#
# ENV OVERRIDES ARE HONOURED, AND THAT TOOK A BUG TO LEARN (#2120, UX-P123):
# `~/.claude/.env` uses `export BAINLUCK_API=...`, so sourcing it UNCONDITIONALLY
# overwrites a caller's override and the script silently reads production while
# reporting whatever the caller thought it pointed at. A UX-P123 mutation proof
# printed PASS against production for exactly this reason. So: capture the caller
# values first, source, then put the caller values back.

set -u

_caller_api="${BAINLUCK_API:-}"
_caller_token="${ADMIN_TOKEN:-}"
# shellcheck disable=SC1090
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
[ -n "$_caller_api" ] && BAINLUCK_API="$_caller_api"
[ -n "$_caller_token" ] && ADMIN_TOKEN="$_caller_token"

API="${BAINLUCK_API:-https://api.bainluck.com}"
OUT_DIR="${OUT_DIR:-/tmp/ux-p124-captures}"
SESSION_ID="${SESSION_ID:-ux-p124-returning-user}"
LIMIT="${LIMIT:-20}"

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SLUG="$(date -u +%Y%m%dT%H%M%SZ)"

# The deployed commit is recorded on EVERY pull, not once at the top of the run.
# A capture window that straddles a release is not one population, and the only
# way to know afterwards is to have stamped each pull as it happened.
COMMIT="$(curl -s --max-time 20 "$API/api/health" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("commit","?"))' 2>/dev/null || echo "?")"

_pull() {
  # $1 label, $2 output path, rest: curl args
  local label="$1" out="$2"; shift 2
  local code
  code="$(curl -s --max-time 90 -o "$out" -w '%{http_code}' "$@" 2>/dev/null)" || code="000"
  echo "$code"
}

ANON_RAW="$OUT_DIR/raw-anon-$SLUG.json"
SESS_RAW="$OUT_DIR/raw-session-$SLUG.json"
DBG_RAW="$OUT_DIR/raw-debug-$SLUG.json"

ANON_CODE="$(_pull anon "$ANON_RAW" "$API/api/feed?limit=$LIMIT")"
SESS_CODE="$(_pull session "$SESS_RAW" -H "x-session-id: $SESSION_ID" "$API/api/feed?limit=$LIMIT")"
DBG_CODE="$(_pull debug "$DBG_RAW" -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/api/feed?limit=$LIMIT&debug=true&debug_ground_truth=false")"

python3 - "$OUT_DIR/pulls.jsonl" "$STAMP" "$COMMIT" "$SESSION_ID" \
  "$ANON_CODE" "$ANON_RAW" "$SESS_CODE" "$SESS_RAW" "$DBG_CODE" "$DBG_RAW" <<'PY'
import json, sys

jsonl, stamp, commit, session_id = sys.argv[1:5]
rest = sys.argv[5:]

def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None

rec = {"captured_at": stamp, "deployed_commit": commit, "session_id": session_id,
       "surfaces": {}}

for label, code, path in (("anon", rest[0], rest[1]),
                          ("session", rest[2], rest[3]),
                          ("debug", rest[4], rest[5])):
    body = load(path)
    entry = {"http": code, "raw_path": path}
    # An HTTP 200 whose body is empty/short is NOT the same fact as a 200 with a
    # slate, and both used to record as success (gotcha #53). Record the shape,
    # never infer "nothing interesting today" from an absence.
    if body is None:
        entry["parsed"] = False
    else:
        entry["parsed"] = True
        items = body.get("items") if isinstance(body, dict) else None
        entry["item_count"] = len(items) if isinstance(items, list) else None
        entry["total"] = body.get("total") if isinstance(body, dict) else None
        entry["cache"] = body.get("cache") if isinstance(body, dict) else None
        if label == "debug" and isinstance(body, dict):
            entry["debug_summary"] = body.get("debug_summary")
            entry["missing_ground_truth_summary"] = body.get(
                "missing_ground_truth_summary")
    rec["surfaces"][label] = entry

with open(jsonl, "a") as fh:
    fh.write(json.dumps(rec) + "\n")

ok = all(v.get("http") == "200" and v.get("parsed") for v in rec["surfaces"].values())
print("CAPTURE %s commit=%s anon=%s session=%s debug=%s -> %s"
      % (stamp, commit,
         rec["surfaces"]["anon"].get("item_count"),
         rec["surfaces"]["session"].get("item_count"),
         rec["surfaces"]["debug"].get("item_count"),
         "OK" if ok else "DEGRADED"))
sys.exit(0 if ok else 1)
PY
exit $?
