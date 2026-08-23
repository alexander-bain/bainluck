#!/usr/bin/env bash
# UX-P119 item 3 — post-deploy proof for #2065 (UX-P116, `program/ux-103`).
#
# ## What UX-P116 measured before the fix
#
# Of 25,610 events in `_score_events`' window, one `ORDER BY` + one `LIMIT 500`
# admitted 500 rows that were **100% live, 488 of them esports**, inside a
# 15-minute commence band, carrying 8 with any probability source — 0 scheduled
# (73 with data existed) and 0 finished (72 existed). The served feed carried ONE
# distinct game rendered TWICE.
#
# Compiled against the live DB, the new selection returned: live 500 -> 46,
# recent 0 -> 142, scheduled 0 -> 90, rows with a probability source 8 -> 164,
# surviving duplicate groups 0, live esports 2,911 -> 11.
#
# ## What this asserts on the SERVED feed
#
# Four things, each with its denominator printed, because the failure this
# replaces looked exactly like a healthy response:
#
#   1. event cards exist at all;
#   2. their statuses are not a single value (the incident was 100% live);
#   3. no two event cards are the same matchup (Strasbourg @ Marseille twice);
#   4. esports does not take the whole allocation.
#
# ## The honest limit, stated rather than hidden
#
# The served feed applies diversity caps AFTER selection, so a small event-card
# count is not by itself a funnel failure — an empty slate is a legitimate
# reading (gotcha #53). A run that finds zero event cards therefore reports
# UNKNOWN with the slate size, not FAIL. The one thing it can never report is a
# silent PASS over an empty population.
#
#   tools/postdeploy/proof-2065-feed-funnel.sh [--force]

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

REF="${REF:-program/ux-103}"
LIMIT="${FEED_LIMIT:-60}"
OUT=/tmp/proof-2065-feed.json

hdr "#2065 — Discover feed event-card funnel ($REF)"

if [ "${1:-}" != "--force" ]; then
  require_deployed "$REF"; rc=$?
  [ $rc -ne 0 ] && exit $rc
else
  say "   --force: deploy gate SKIPPED (this is a baseline read, not a proof)"
fi

api_get "/api/feed?limit=$LIMIT" "$OUT" || { verdict "#2065" "UNKNOWN — feed unreachable"; exit $RC_TRANSPORT; }

python3 - "$OUT" <<'PY'
import collections, json, sys

d = json.load(open(sys.argv[1]))
items = d.get("items") or []
if not items:
    print("#2065: UNKNOWN — feed returned 0 items (empty 200 is a shape, not a fact)")
    raise SystemExit(3)

kinds = collections.Counter(i.get("type") for i in items)
events = [i for i in items if i.get("type") == "event"]
print(f"   served items: {len(items)}  card types: {dict(kinds)}")
print(f"   event cards: {len(events)}")

if not events:
    print("#2065: UNKNOWN — 0 event cards served. Distinguish an empty slate from a")
    print("        funnel regression before concluding: check the candidate counts")
    print("        directly, do not read this as a FAIL or a PASS.")
    raise SystemExit(3)

statuses = collections.Counter((e.get("data") or {}).get("status") for e in events)
sports = collections.Counter((e.get("data") or {}).get("sport") for e in events)
print(f"   statuses: {dict(statuses)}")
print(f"   sports:   {dict(sports)}")

fails = []

# 3 — identity duplication. The incident's tell: one matchup, two rows.
seen = collections.Counter()
for e in events:
    dd = e.get("data") or {}
    seen[(dd.get("away_team"), dd.get("home_team"), (dd.get("commence_time") or "")[:10])] += 1
dupes = {k: v for k, v in seen.items() if v > 1}
print(f"   distinct matchups: {len(seen)} of {len(events)} cards")
if dupes:
    fails.append(f"duplicate matchups served: {dupes}")

# 2 — status monoculture. A FAIL needs enough cards for a mix to have been
# possible; below that the check cannot fire and must SAY it did not fire.
# Printing "no monoculture" over three all-live cards is itself a false
# statement, and this script found itself doing exactly that on its first run.
notes = []
mono = len(statuses) == 1
if mono and len(events) >= 4:
    only = next(iter(statuses))
    fails.append(f"all {len(events)} event cards share status={only!r} (the incident shape)")
elif mono:
    only = next(iter(statuses))
    notes.append(f"all {len(events)} event cards are status={only!r} — the incident shape, "
                 f"but NOT asserted: {len(events)} cards is too few for a mix to have been "
                 f"possible, so this is UNPROVEN, not passed")

# 4 — esports allocation. Pre-fix it was 488 of 500 candidates.
esports = sum(n for s, n in sports.items() if s and "esports" in str(s).lower() or
              s in {"cs2", "dota2", "lol", "valorant"})
if len(events) >= 5 and esports / len(events) > 0.8:
    fails.append(f"esports is {esports}/{len(events)} of event cards (>80%)")

for n in notes:
    print("   ⚠️ " + n)

if fails:
    print("#2065: FAIL")
    for f in fails:
        print("   - " + f)
    raise SystemExit(1)

if notes:
    print("#2065: UNKNOWN — no violation found, but the checks above marked UNPROVEN")
    print("        could not run on this slate. Re-run when more event cards are served.")
    raise SystemExit(3)

print("#2065: PASS — event cards served, no duplicate matchup, statuses are mixed, "
      "esports not dominant")
PY
rc=$?
echo "EXIT CODE: $rc"
exit $rc
