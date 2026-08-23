#!/usr/bin/env bash
# UX-P122 item A — the PROVABILITY CONDITION for #2065, as a self-gating check.
#
# ## The problem this exists to end
#
# `proof-2065-feed-funnel.sh` has now reported UNKNOWN on two consecutive
# post-deploy runs — 2 event cards one day, and 1 the next. Its own honesty is
# what produced that: it refuses to print "statuses are mixed" over three
# all-live cards, because a monoculture check cannot fire on a slate too thin
# for a mix to have been possible. That refusal is correct and it is not the
# problem.
#
# The problem is that UNKNOWN was recorded as a state of the WORLD — "re-run on
# a thicker slate" — when nobody had ever measured whether a thicker slate was
# reachable. Two cycles of "re-run later" is what an unstated provability
# condition costs. **A check that can be unprovable must be able to say why.**
#
# ## The condition, stated as a number instead of a hope
#
# #2065's four assertions have different appetites, and only two of them are
# actually slate-hungry:
#
#   | assertion            | needs                    | why |
#   |----------------------|--------------------------|-----|
#   | event cards exist    | >= 1 card                | trivially |
#   | no duplicate matchup | >= 2 cards               | a duplicate needs two rows |
#   | statuses are mixed   | >= MIN_CARDS **and** a mixed candidate pool | the incident was 100% live |
#   | esports not dominant | >= 5 cards               | 1-of-1 esports is 100% and means nothing |
#
# `MIN_CARDS` is 4, which is not a taste call: it is the threshold
# `proof-2065-feed-funnel.sh` already hard-codes for its own monoculture
# assertion. Restating it here as a different number would create two
# provability conditions for one proof, and the looser one would be the one
# quoted. It is read from the same env var the proof honours.
#
# ## THREE SURFACES, AND THAT IS THE ACTUAL FINDING
#
# The gate measures three populations, because two of them can only be told
# apart by the third:
#
#   1. **The default Discover slate** (`/api/feed`) — what the proof reads today.
#   2. **The funnel-isolated slate** (`/api/feed?include_futures=false`) — the
#      same event funnel with the futures competition removed.
#   3. **The candidate pool** (one admin `db-query` over the feed's own
#      -24h/+12h `commence_time` band) — how many events with a REAL
#      win-probability source exist at all, by status.
#
# Measured 2026-08-23 with all three, and they do not agree in the slightest:
#
#   default slate            60 items ->  1 event card, {live: 1}
#   include_futures=false    60 items -> 47 event cards, {closed:21 completed:16
#                                        scheduled:7 live:3}, 47 distinct matchups
#   candidate pool           185 events with a real source: completed 85,
#                            closed 67, scheduled 19, live 14
#
# So the default slate's thinness is **not** the world being empty, and it is
# **not** a funnel regression either. It is Discover's deliberate event
# demotion: a non-exceptional event is capped at score 35 when `event_pct < 0.3`
# (`_is_discover_event_demotion_exception`), so event cards lose to futures by
# design. #2065 fixed the SELECTION funnel; the default slate measures RANKING
# on top of it, and no amount of waiting for a thicker slate changes that.
#
# **The proof was reading the wrong surface.** That is a different defect from
# "the slate is thin", and it is the one two cycles of UNKNOWN were hiding.
#
# ## Why this does not report a FAIL over a thin default slate
#
# It would be easy, and wrong, to call "1 event card over a 185-event pool" a
# funnel regression. The demotion rule above is a sufficient and DELIBERATE
# explanation, and filing against a deliberate rule is the cried-wolf failure
# the Grid Sentinel's REAL/EXPLAINED/WATCH split exists to prevent. So the
# closure gets a REASON, and a reason that names a known rule is EXPLAINED, not
# a defect claim.
#
#   OPEN(0)              at least one surface can carry every assertion
#   CLOSED/EXPLAINED(3)  no surface can, and the candidate pool is thin too —
#                        the world, not us
#   CLOSED/WATCH(3)      no surface can while the pool is rich — not a defect
#                        claim, but the numbers are printed so the next reader
#                        starts from data instead of from "re-run later"
#
# There is deliberately no exit-1 path. This is a GATE; the thing that can fail
# is the proof, and when the gate is OPEN this script runs #2065's four
# assertions on the surface it just certified and reports their verdict too —
# so an OPEN run is not a promise that the proof could be run, it is the run.
#
#   tools/postdeploy/checks/gate-2065-provability.sh [--force]

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib.sh"

REF="${REF:-program/ux-103}"
LIMIT="${FEED_LIMIT:-60}"
# Same threshold `proof-2065-feed-funnel.sh` uses for its monoculture assertion.
MIN_CARDS="${MIN_EVENT_CARDS:-4}"
# A pool is "rich" when it could plausibly have produced a provable slate.
POOL_MIN="${POOL_MIN:-20}"

DEFAULT_OUT=/tmp/gate-2065-default.json
ISOLATED_OUT=/tmp/gate-2065-isolated.json
POOL_OUT=/tmp/gate-2065-pool.json

hdr "#2065 — PROVABILITY GATE ($REF)"

if [ "${1:-}" != "--force" ]; then
  require_deployed "$REF"; rc=$?
  [ $rc -ne 0 ] && exit $rc
else
  say "   --force: deploy gate SKIPPED (this is a baseline read, not a proof)"
fi

say "   provability condition: >= $MIN_CARDS event cards on some surface,"
say "   over a candidate pool carrying >= 2 statuses (pool floor $POOL_MIN)."

# ── surface 1 + 2 ────────────────────────────────────────────────────────────
api_get "/api/feed?limit=$LIMIT" "$DEFAULT_OUT" \
  || { verdict "#2065-gate" "UNKNOWN — default feed unreachable"; exit $RC_TRANSPORT; }
api_get "/api/feed?limit=$LIMIT&include_futures=false" "$ISOLATED_OUT" \
  || { verdict "#2065-gate" "UNKNOWN — isolated feed unreachable"; exit $RC_TRANSPORT; }

# ── surface 3: the candidate pool ────────────────────────────────────────────
#
# The feed's own window, transcribed: `_score_events` uses `now - 24h` to
# `now + 12h` on `commence_time` for the non-`my_teams_only` path.
#
# `?|` against the SOURCE_WEIGHTS key list, NOT `<> '{}'` — `win_probability_sources`
# also carries metadata keys (`betting_book_count` and friends), so a non-empty
# test over-counts. Measured today: 260 events pass `<> '{}'` and 185 carry an
# actual source. Reporting the larger number would make every thin slate look
# like a funnel bug.
POOL_SQL=$(cat <<'SQL'
SELECT status,
       count(*) AS n_in_window,
       count(*) FILTER (WHERE win_probability_sources ?| array['final_result','betting','espn','stat_model','kalshi','polymarket','mlb']) AS with_real_src
FROM events
WHERE commence_time >= now() - interval '24 hours'
  AND commence_time <= now() + interval '12 hours'
GROUP BY 1
SQL
)
POOL_OK=1
if [ -z "${ADMIN_TOKEN:-}" ]; then
  say "   ADMIN_TOKEN unset — candidate pool NOT measured (the third signal is missing)"
  POOL_OK=0
else
  # The read guard is a substring check over the WHOLE statement, comments and
  # string literals included, so the SQL above carries no `;` and no `grant`.
  python3 - "$POOL_SQL" > /tmp/gate-2065-pool-body.json <<'PY'
import json, sys
print(json.dumps({"sql": " ".join(sys.argv[1].split()), "limit": 20}))
PY
  code=$(curl -s --max-time 60 -o "$POOL_OUT" -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
    --data @/tmp/gate-2065-pool-body.json "$BAINLUCK_API/api/admin/db-query")
  if [ "$code" != "200" ]; then
    say "   HTTP $code on db-query — candidate pool NOT measured"
    POOL_OK=0
  fi
fi

MIN_CARDS="$MIN_CARDS" POOL_MIN="$POOL_MIN" POOL_OK="$POOL_OK" python3 - \
  "$DEFAULT_OUT" "$ISOLATED_OUT" "$POOL_OUT" <<'PY'
import collections, json, os, sys

MIN_CARDS = int(os.environ["MIN_CARDS"])
POOL_MIN = int(os.environ["POOL_MIN"])
POOL_OK = os.environ["POOL_OK"] == "1"


def surface(path, name):
    d = json.load(open(path))
    items = d.get("items") or []
    events = [i for i in items if i.get("type") == "event"]
    data = [(e.get("data") or {}) for e in events]
    statuses = collections.Counter(x.get("status") for x in data)
    sports = collections.Counter(x.get("sport") for x in data)
    matchups = collections.Counter(
        (x.get("away_team"), x.get("home_team"), (x.get("commence_time") or "")[:10])
        for x in data
    )
    return {
        "name": name,
        "items": len(items),
        "events": len(events),
        "statuses": statuses,
        "sports": sports,
        "matchups": matchups,
    }


default = surface(sys.argv[1], "default Discover (/api/feed)")
isolated = surface(sys.argv[2], "funnel-isolated (include_futures=false)")

pool = {}
pool_total = 0
if POOL_OK:
    try:
        p = json.load(open(sys.argv[3]))
        cols = p.get("columns") or []
        idx = {c: i for i, c in enumerate(cols)}
        for row in p.get("rows") or []:
            pool[row[idx["status"]]] = int(row[idx["with_real_src"]])
        pool_total = sum(pool.values())
    except Exception as exc:  # noqa: BLE001 - the shape is the thing being reported
        print(f"   pool read unusable: {exc!r}")
        POOL_OK = False

print("")
print("   ── the three surfaces ──")
for s in (default, isolated):
    print(
        f"   {s['name']}: {s['items']} items -> {s['events']} event cards, "
        f"{dict(s['statuses'])}"
    )
if POOL_OK:
    print(f"   candidate pool (-24h..+12h, real source only): {pool_total} events {pool}")
else:
    print("   candidate pool: NOT MEASURED")

pool_statuses = len([k for k, v in pool.items() if v > 0])
pool_rich = POOL_OK and pool_total >= POOL_MIN and pool_statuses >= 2


def provable(s):
    """Can #2065's full assertion set reach a verdict on this surface?

    Card count is the binding half. The second half is that a MIX has to have
    been reachable at all — a surface serving 40 cards from a world with only
    live events would print "monoculture" as a defect claim about the feed when
    it is a fact about the day. When the pool is unmeasured this degrades to the
    card count alone and says so, rather than silently asserting the stronger
    condition it could not check.
    """
    if s["events"] < MIN_CARDS:
        return False, f"{s['events']} event cards < {MIN_CARDS}"
    if POOL_OK and pool_statuses < 2:
        return False, f"candidate pool carries only {pool_statuses} status(es)"
    return True, f"{s['events']} event cards, pool spans {pool_statuses or '?'} statuses"


print("")
print("   ── the gate ──")
chosen = None
for s in (isolated, default):
    ok, why = provable(s)
    print(f"   {'OPEN  ' if ok else 'CLOSED'}  {s['name']}: {why}")
    if ok and chosen is None:
        chosen = s

if chosen is None:
    print("")
    if pool_rich:
        print("#2065-gate: CLOSED / WATCH — no surface can carry the assertions, but the")
        print(f"        candidate pool is NOT thin ({pool_total} events across {pool_statuses}")
        print("        statuses). The slate is therefore not the explanation. This is NOT a")
        print("        defect claim: Discover demotes non-exceptional events (score cap 35 at")
        print("        event_pct < 0.3), which is sufficient and deliberate. Printed so the")
        print("        next reader starts from these numbers instead of from 're-run later'.")
    elif POOL_OK:
        print("#2065-gate: CLOSED / EXPLAINED — the candidate pool is genuinely thin")
        print(f"        ({pool_total} events across {pool_statuses} status(es), floor {POOL_MIN}).")
        print("        An empty slate is a fact about the day, not about the funnel (gotcha #53).")
    else:
        print("#2065-gate: CLOSED / UNDETERMINED — no surface is thick enough AND the")
        print("        candidate pool could not be measured, so the world and the funnel")
        print("        cannot be told apart. Set ADMIN_TOKEN and re-run.")
    raise SystemExit(3)

print("")
print(f"   gate OPEN on: {chosen['name']}")
print("   running #2065's assertions on that surface — an OPEN gate that did not")
print("   then run the proof would just be a differently-worded 're-run later'.")

fails = []
notes = []

# 1 — cards exist. Guaranteed by the gate; asserted so the list is complete.
if chosen["events"] < 1:
    fails.append("no event cards served")

# 2 — identity duplication. The incident's tell: one matchup, two rows.
dupes = {k: v for k, v in chosen["matchups"].items() if v > 1}
print(f"   distinct matchups: {len(chosen['matchups'])} of {chosen['events']} cards")
if dupes:
    fails.append(f"duplicate matchups served: {dupes}")

# 3 — status monoculture. The incident was 100% live.
if len(chosen["statuses"]) == 1:
    only = next(iter(chosen["statuses"]))
    fails.append(
        f"all {chosen['events']} event cards share status={only!r} (the incident shape) "
        f"while the candidate pool spans {pool_statuses} statuses"
    )
else:
    print(f"   statuses: {dict(chosen['statuses'])} — {len(chosen['statuses'])} distinct")

# 4 — esports allocation. Pre-fix it was 488 of 500 candidates.
esports = sum(
    n
    for s, n in chosen["sports"].items()
    if (s and "esports" in str(s).lower()) or s in {"cs2", "dota2", "lol", "valorant"}
)
if chosen["events"] >= 5:
    print(f"   esports: {esports}/{chosen['events']} event cards")
    if esports / chosen["events"] > 0.8:
        fails.append(f"esports is {esports}/{chosen['events']} of event cards (>80%)")
else:
    notes.append(f"esports share not asserted: {chosen['events']} cards is under 5")

for n in notes:
    print("   ⚠️ " + n)

print("")
if fails:
    print("#2065-gate: OPEN — and the proof FAILS on it")
    for f in fails:
        print("   - " + f)
    raise SystemExit(1)

print("#2065-gate: OPEN — and the proof PASSES on it:")
print(f"   {chosen['events']} event cards · {len(chosen['statuses'])} distinct statuses · "
      f"{len(chosen['matchups'])}/{chosen['events']} distinct matchups · esports {esports}")
print("")
print("   NOTE FOR proof-2065-feed-funnel.sh: it reads the DEFAULT slate, where")
print("   Discover's event demotion leaves too few cards for its own monoculture")
print("   assertion to fire. Its UNKNOWN is a wrong-surface verdict, not a thin")
print("   world. Point it at include_futures=false when the stack merges and it")
print("   can stop deferring.")
PY
rc=$?
echo "EXIT CODE: $rc"
exit $rc
