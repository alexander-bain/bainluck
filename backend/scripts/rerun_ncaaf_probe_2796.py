"""Re-run the 109 NCAAF `no_candidate` rejects through the COVERING probe (#2796).

#2796 concluded "upstream gap: we do not carry these teams" from
``candidate_probe.covering_hits = 0`` on all 109. Measured 2026-09-03, 103 of
those 109 probes returned exactly 5 rows — the LIMIT — so `covering_hits` was
counted over the five earliest one-token coincidences in a 165-day window, not
over the question asked. This script asks the question the fixed probe asks:
does an event carrying the WHOLE matchup exist in the probe window?

It runs the SHIPPING oracle (``app.utils.match_receipts.row_coverage``) over
production rows pulled through ``/api/admin/db-query`` — not a SQL
re-implementation of it, because a second copy of the coverage rule is a second
thing to be wrong.

    python3 scripts/rerun_ncaaf_probe_2796.py
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.match_receipts import (  # noqa: E402
    coverage_anchors,
    row_coverage,
    sides_from_market_name,
)


def _nests(side, team) -> bool:
    """One name's anchor tokens contain the other's — "Morehead St." ~ "Morehead
    State", but not "Elizabeth City State" ~ "Kent State".

    ``row_coverage`` is DELIBERATELY permissive (its comment says so: when in
    doubt a row counts as covered, so the receipt keeps the label it had rather
    than inventing an upstream gap). That is right for the matcher and wrong for
    a headline count, because a shared "state" or "carolina" then reads as a
    found game. This is the stricter second opinion, used only to grade the
    output — never to decide a receipt.
    """
    a, b = coverage_anchors(side), coverage_anchors(team)
    return bool(a) and bool(b) and (a <= b or b <= a)


def _strict_pair(side_a, side_b, home, away) -> bool:
    return (
        (_nests(side_a, home) and _nests(side_b, away))
        or (_nests(side_a, away) and _nests(side_b, home))
    )

API = os.environ["BAINLUCK_API"]
TOKEN = os.environ["ADMIN_TOKEN"]

# The probe's own bracket. Widened here ONLY in the sense that the covering
# arm's WHERE does the filtering — the window is identical to _PROBE_PAST_DAYS /
# _PROBE_FUTURE_DAYS.
WINDOW = "commence_time BETWEEN now() - interval '45 days' AND now() + interval '120 days'"


def q(sql, limit=1000):
    req = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": limit}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if "rows" not in body:
        raise SystemExit(f"db-query refused: {body}")
    return body["rows"]


def main():
    rejects = q(
        "SELECT r.market_id, fm.external_id, fm.name, "
        "(r.detail->'candidate_probe'->>'hits')::int AS old_hits "
        "FROM market_match_receipts r JOIN futures_markets fm ON fm.id=r.market_id "
        "WHERE r.reject_reason='no_candidate' AND fm.status='open' "
        "AND fm.external_id LIKE 'KXNCAAFGAME%' ORDER BY fm.external_id"
    )
    print(f"rejects: {len(rejects)}  saturated_at_5: "
          f"{sum(1 for r in rejects if r[3] == 5)}")

    # Every football event the probe window brackets, chunked past the 1000-row
    # cap. Football only: these are college football markets, and an event
    # covering one of them that is filed under, say, basketball would be a
    # different (and louder) bug than the one under test.
    events = []
    for part in range(6):
        events += q(
            "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, "
            f"e.status, s.key FROM events e JOIN sports s ON s.id=e.sport_id "
            f"WHERE {WINDOW} AND s.key LIKE 'americanfootball%' "
            f"AND e.id % 6 = {part}"
        )
    print(f"football events in the probe window: {len(events)}")

    covered, uncovered = [], []
    for market_id, external_id, name, old_hits in rejects:
        side_a, side_b = sides_from_market_name(name)
        hits = []
        for eid, home, away, commence, status, key in events:
            matched, named = row_coverage(name, side_a, side_b, home, away)
            if matched >= named:
                hits.append((eid, home, away, commence, status, key))
        (covered if hits else uncovered).append(
            (external_id, name, old_hits, hits)
        )

    strict, loose = [], []
    for external_id, name, old_hits, hits in covered:
        side_a, side_b = sides_from_market_name(name)
        best = [h for h in hits if _strict_pair(side_a, side_b, h[1], h[2])]
        (strict if best else loose).append((external_id, name, best or hits))

    print(f"\nCOVERING EVENT EXISTS : {len(covered)} / {len(rejects)}")
    print(f"  of which NAME-NESTED: {len(strict)}  (the correction)")
    print(f"  of which generic-token coincidences: {len(loose)}")
    print(f"NO COVERING EVENT     : {len(uncovered)} / {len(rejects)}")

    for label, bucket in (("NESTED", strict), ("LOOSE", loose)):
        print(f"\n── {label} ──")
        for external_id, name, hits in bucket:
            eid, home, away, commence, status, key = hits[0]
            print(f"  {external_id:30} {name[:40]:42} -> {eid} [{key}] "
                  f"{home} vs {away} @ {commence} ({status})")

    by_key = {}
    for _x, _n, hits in strict:
        by_key[hits[0][5]] = by_key.get(hits[0][5], 0) + 1
    print(f"\nnested covering events by sport key: {by_key}")
    placeholder = sum(
        1 for _x, _n, hits in strict if hits[0][3][17:19] != "00"
    )
    print(f"nested covering events whose commence_time is a non-round "
          f"second (ingest-instant placeholder): {placeholder} / {len(strict)}")


if __name__ == "__main__":
    main()
