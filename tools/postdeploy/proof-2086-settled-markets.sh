#!/usr/bin/env bash
# UX-P119 item 3 — post-deploy proof for #2086 (UX-P115, `program/ux-102`).
#
# ## What UX-P115 measured
#
# `SpecialEventMarkets.tsx:14` DECLARED `eventStatus?`, `page.tsx:1170` PASSED it,
# and `:81` destructured `{ data }` only — so the "Additional Markets" section on
# a finished game rendered live-looking prices. Of 158 priced rows on 40 settled
# events, 58 sat in 0.40–0.60 and only 6 at 0.90+: the modal defect is a 47% on a
# match that ended a week ago, which reads as an ordinary live probability. 9,447
# settled events carry linked markets against 24 scheduled/live.
#
# ## 🚨 What this proof CANNOT be, and why that is the finding
#
# #2086's fix is entirely client-side: `SpecialEventMarkets.tsx` now destructures
# the `eventStatus` prop it always received. **The API payload is byte-identical
# before and after.** So no API check can distinguish a fixed deploy from an
# unfixed one, and any script claiming to "prove #2086 from production" without a
# browser is claiming something impossible.
#
# This script therefore does the two honest things instead:
#
#   1. **Verifies the INPUT is present** — the event serves a settled `status`,
#      the prop that was declared, passed, and never destructured. If that ever
#      stopped being served, the fixed component would silently revert to the old
#      behaviour, so it is worth a standing check.
#   2. **Hands Alex a live specimen URL** — a settled event that currently serves
#      mid-band prices in `other`, i.e. one where the bug WOULD be visible. A
#      rendered check against an event with nothing to render proves nothing, and
#      picking such an event is the easiest way to accidentally self-certify.
#
# The payload shape, recorded because the first draft got it wrong: `other` is a
# FLAT list of `{market_name, outcome_name, probability, source}`. There are no
# nested `outcomes`, and **no per-row `status` or `is_winner` on this endpoint** —
# UX-P115 read those from the database, not from here. A draft that asserted on
# `m["outcomes"]` found zero priced rows across 40 events and would have reported
# a confident UNKNOWN over a slate full of specimens.
#
# Specimen selection is dynamic on purpose — a hardcoded event id is a fixture
# with an expiry date (gotcha #44), and settled events fall out of every window.
#
#   tools/postdeploy/proof-2086-settled-markets.sh [--force]
#   EVENT_ID=15198923 tools/postdeploy/proof-2086-settled-markets.sh

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

REF="${REF:-program/ux-102}"

hdr "#2086 — settled game markets serve a settled status + graded outcomes ($REF)"

if [ "${1:-}" != "--force" ]; then
  require_deployed "$REF"; rc=$?
  [ $rc -ne 0 ] && exit $rc
else
  say "   --force: deploy gate SKIPPED (this is a baseline read, not a proof)"
fi

# --- find candidate settled events with linked markets -----------------------
CANDIDATES="${EVENT_ID:-}"
if [ -z "$CANDIDATES" ]; then
  if [ -z "${ADMIN_TOKEN:-}" ]; then
    verdict "#2086" "UNKNOWN — no EVENT_ID given and ADMIN_TOKEN unset for discovery"
    exit $RC_UNKNOWN
  fi
  say "   discovering settled events with linked markets…"
  SQL='SELECT e.id FROM events e JOIN futures_markets fm ON fm.event_id = e.id
       WHERE e.status IN ('"'"'completed'"'"','"'"'closed'"'"')
         AND e.commence_time > NOW() - INTERVAL '"'"'10 days'"'"'
       GROUP BY e.id HAVING COUNT(fm.id) >= 2
       ORDER BY MAX(e.commence_time) DESC'
  printf '{"sql":%s,"limit":40}' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$SQL")" > /tmp/p2086-q.json
  # Retried: this window saw a transient 400 on a query that succeeded verbatim
  # seconds later (the read rail rate-limits at 60/min and other lanes share it).
  # One blip must not be reported as "no settled events exist".
  code=""
  for attempt in 1 2 3 4; do
    code=$(curl -s --max-time 90 -o /tmp/p2086-ids.json -w '%{http_code}' \
      -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
      --data @/tmp/p2086-q.json "$BAINLUCK_API/api/admin/db-query")
    [ "$code" = "200" ] && break
    say "   [retry $attempt/4] discovery query HTTP $code"
    sleep $(( attempt * 8 ))
  done
  if [ "$code" != "200" ]; then
    verdict "#2086" "UNKNOWN — discovery query HTTP $code after 4 attempts"
    exit $RC_UNKNOWN
  fi
  CANDIDATES=$(python3 -c "
import json
print(' '.join(str(r[0]) for r in json.load(open('/tmp/p2086-ids.json')).get('rows', [])))
")
fi

if [ -z "$CANDIDATES" ]; then
  verdict "#2086" "UNKNOWN — no settled event with linked markets in the last 10 days"
  exit $RC_UNKNOWN
fi

# --- scan for one whose `other` section is actually populated ----------------
# A specimen must be able to FAIL, or selecting it proves nothing. That means a
# non-empty `other` list AND at least one PRICED outcome in it — the price is the
# thing the bug rendered as live. The first draft of this script required only a
# non-empty list, picked an esports event whose single market had zero priced
# outcomes, and returned UNKNOWN on a slate that had usable specimens further
# down.
#
# It now scans up to P2086_SCAN_CAP candidates and keeps the one with the MOST
# mid-band rows, rather than the first usable one. A specimen with a single
# priced row is a weak thing to ask a human to eyeball; the richest one on the
# slate costs the same number of requests and makes the rendered check decisive.
PICKED=""
BEST_MID=-1
SCANNED=0
SKIPPED_EMPTY=0
SKIPPED_UNPRICED=0
SCAN_CAP="${P2086_SCAN_CAP:-12}"
for id in $CANDIDATES; do
  [ "$SCANNED" -ge "$SCAN_CAP" ] && break
  SCANNED=$(( SCANNED + 1 ))
  api_get "/api/events/$id/game-markets" "/tmp/p2086-cand.json" 3 || continue
  n=$(python3 -c "
import json
try: d = json.load(open('/tmp/p2086-cand.json'))
except Exception: print('0 0 0'); raise SystemExit
other = d.get('other') or []
priced = [r for r in other if r.get('probability') is not None]
mid = [r for r in priced if 0.40 <= float(r['probability']) <= 0.60]
print(len(other), len(priced), len(mid))
")
  set -- $n
  nother="${1:-0}"; npriced="${2:-0}"; nmid="${3:-0}"
  if [ "$nother" -eq 0 ]; then SKIPPED_EMPTY=$(( SKIPPED_EMPTY + 1 )); continue; fi
  if [ "$npriced" -eq 0 ]; then SKIPPED_UNPRICED=$(( SKIPPED_UNPRICED + 1 )); continue; fi
  if [ "$nmid" -gt "$BEST_MID" ]; then
    BEST_MID="$nmid"; PICKED="$id"
    cp /tmp/p2086-cand.json /tmp/p2086-gm.json
  fi
done
say "   skipped: $SKIPPED_EMPTY with no \`other\` section, $SKIPPED_UNPRICED with no priced row"

say "   scanned $SCANNED settled event(s) for a specimen that can fail"
if [ -z "$PICKED" ]; then
  verdict "#2086" "UNKNOWN — none of $SCANNED settled events serves a priced \`other\` market; nothing to render, so nothing to prove"
  exit $RC_UNKNOWN
fi
say "   specimen: event $PICKED"

python3 - /tmp/p2086-gm.json "$PICKED" "$SCANNED" <<'PYEOF'
import json, sys

d = json.load(open(sys.argv[1]))
eid = sys.argv[2]
scanned = sys.argv[3]
status = d.get("status")
other = d.get("other") or []
print(f"   event {eid}: status={status!r}   `other` rows={len(other)}")
print(f"   {d.get('away_team')} {d.get('away_score')} @ {d.get('home_team')} {d.get('home_score')}")

fails = []

# The prop that was declared, passed, and never destructured.
SETTLED = {"completed", "closed", "settled", "final"}
if str(status).lower() not in SETTLED:
    fails.append(
        f"served status={status!r} is not a settled status — the fixed component "
        f"cannot know the game is over, so it would still render live"
    )

priced = [r for r in other if r.get("probability") is not None]
mid = [r for r in priced if 0.40 <= float(r["probability"]) <= 0.60]
extreme = [r for r in priced
           if float(r["probability"]) >= 0.90 or float(r["probability"]) <= 0.10]
print(f"   priced rows: {len(priced)}   mid-band 0.40-0.60: {len(mid)}   "
      f"at 0.90+/0.10-: {len(extreme)}")

if not priced:
    print("#2086: UNKNOWN - specimen serves no priced rows; nothing to mis-render")
    raise SystemExit(3)

if fails:
    print("#2086: FAIL")
    for f in fails:
        print("   - " + f)
    raise SystemExit(1)

print("")
print(f"#2086: INPUT OK - the settled status IS served, and this event has "
      f"{len(priced)} priced row{'' if len(priced) == 1 else 's'} the surface "
      f"must re-state as frozen.")
print("")
print("       THE VERDICT IS ALEX'S, AND THIS PROOF CANNOT SUBSTITUTE FOR IT.")
print("       The fix is client-side; the payload is identical either way.")
print("")
print(f"       LOOK AT:  https://bainluck.com/event/{eid}")
print("       In Additional Markets, every row must:")
print("         - show NO probability bar")
if mid:
    ex = mid[0]
    print(f"         - read `last quote NN%`  (this event prints "
          f"{ex['probability'] * 100:.0f}% on \"{ex['outcome_name']}\")")
else:
    print("         - read `last quote NN%`")
print("         - say 'settled' exactly ONCE per section, not per row")
print("")
print(f"       Richest of the {scanned} candidates SCANNED (cap P2086_SCAN_CAP, not the "
      f"whole slate): {len(mid)} of its "
      f"{len(priced)} priced rows sit in")
print("       0.40-0.60, which is UX-P115's modal defect - a coin-flip on a finished")
print("       game reads as an ordinary live probability, where a 99% at least looks odd.")
PYEOF
rc=$?
echo "EXIT CODE: $rc"
exit $rc
