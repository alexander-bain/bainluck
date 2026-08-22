#!/usr/bin/env bash
# UX-P119 item 3 — post-deploy proof for #2084 (UX-P114, `program/ux-101`).
#
# ## The arithmetic this proves, which is why the proof can be exact
#
# `feed.py` builds the away side as `round(1.0 - home, 6)`, so the pair is exact
# by construction. With `home*100 = n + f`, independent half-up rounding of both
# sides prints 101 iff `f == 0.5`, and 100 otherwise — it can never print 99.
# UX-P114 measured 34 of 414 (8.2%) printing 101 and ZERO printing 99, which is
# the arithmetic's own prediction rather than a sample.
#
# The fix serves the two integers from one server-side decision
# (`rendered_duel_percents`) because four surfaces draw the strip — web, native,
# the macOS menu bar and the widget — and the widget cannot import the app's
# utilities, so a client-only fix meant a fourth copy of the band.
#
# ## What this asserts
#
#   1. every event card CARRIES `home_rendered_percent` + `away_rendered_percent`
#      (their absence is the pre-fix state, and is reported as such rather than
#      skipped — a missing field must never read as "no violations found");
#   2. the two ints sum to exactly 100 on every card;
#   3. the FAVOURITE's printed value equals its own half-up rounding. This is the
#      column UX-P114 rejected made checkable: `rendered_duel_percents` hands the
#      favourite in at index 0 "so it is the value that survives", and an
#      away-first implementation would print 67 for a Denver whose own value is
#      68. Sum-to-100 alone cannot see that — 67/33 sums to 100 too.
#
# The fields sit under `data.current_odds`, NOT at the top of `data`. That is
# recorded because the first draft of this script read the top level, found
# nothing, and printed a confident FAIL against a fix that was deployed and
# working. A proof that asserts on the wrong path fails in the same direction as
# a real regression.
#
#   tools/postdeploy/proof-2084-duel-sum.sh [--force]

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

REF="${REF:-program/ux-101}"
LIMIT="${FEED_LIMIT:-100}"
OUT=/tmp/proof-2084-feed.json

hdr "#2084 — served-feed duel percents sum to 100 ($REF)"

if [ "${1:-}" != "--force" ]; then
  require_deployed "$REF"; rc=$?
  [ $rc -ne 0 ] && exit $rc
else
  say "   --force: deploy gate SKIPPED (this is a baseline read, not a proof)"
fi

api_get "/api/feed?limit=$LIMIT" "$OUT" || { verdict "#2084" "UNKNOWN — feed unreachable"; exit $RC_TRANSPORT; }

python3 - "$OUT" <<'PY'
import json, sys

d = json.load(open(sys.argv[1]))
events = [i for i in (d.get("items") or []) if i.get("type") == "event"]
print(f"   event cards: {len(events)}")
if not events:
    print("#2084: UNKNOWN — 0 event cards served; nothing to measure (see #2065 proof)")
    raise SystemExit(3)

def half_up(p):
    """The clients' rounding. Python's round() is BANKER'S — UX-P116 reported a
    phantom `0 of 148` from exactly this, one file away from a docstring naming
    the trap."""
    from decimal import Decimal, ROUND_HALF_UP
    return int(Decimal(str(p * 100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

missing, bad_sum, bad_fav, blend = [], [], [], 0
for e in events:
    dd = e.get("data") or {}
    co = dd.get("current_odds") or {}
    h, a = co.get("home_rendered_percent"), co.get("away_rendered_percent")
    hp, ap = co.get("home_probability"), co.get("away_probability")
    ident = f"{dd.get('id')} {dd.get('away_team')} @ {dd.get('home_team')}"
    if h is None or a is None:
        missing.append(ident)
        continue
    blend += 1
    if h + a != 100:
        bad_sum.append(f"{ident}: {a}+{h}={a+h}")
    # 3 — the favourite's own value survives.
    if hp is not None and ap is not None:
        fav_pct, fav_prob = (h, hp) if hp >= ap else (a, ap)
        want = half_up(float(fav_prob))
        if fav_pct != want:
            bad_fav.append(f"{ident}: favourite prints {fav_pct} but its own value "
                           f"rounds to {want} ({fav_prob})")

print(f"   cards carrying the served pair: {blend} / {len(events)}")
print(f"   cards missing the pair:         {len(missing)}")

if blend == 0:
    print("#2084: FAIL — NO event card carries `home_rendered_percent` /")
    print("        `away_rendered_percent`. That is the PRE-FIX payload: the two")
    print("        ints are not being served, so all four surfaces are still")
    print("        rounding independently. Examples:")
    for m in missing[:5]:
        print("        - " + m)
    raise SystemExit(1)

if bad_sum or bad_fav:
    print(f"#2084: FAIL — {len(bad_sum)} of {blend} pairs do not sum to 100; "
          f"{len(bad_fav)} print a favourite that is not its own rounding")
    for b in (bad_sum + bad_fav)[:10]:
        print("        - " + b)
    raise SystemExit(1)

if missing:
    print(f"#2084: UNKNOWN — {blend} pairs all sum to 100, but {len(missing)} event")
    print("        cards carry no pair at all. A partial rollout and a blend-less")
    print("        card look identical here; check whether those events have a")
    print("        probability source before reading this as a pass.")
    for m in missing[:5]:
        print("        - " + m)
    raise SystemExit(3)

print(f"#2084: PASS — all {blend} served duel pairs sum to exactly 100, and every "
      f"favourite prints its own half-up rounding")
PY
rc=$?
echo "EXIT CODE: $rc"
exit $rc
