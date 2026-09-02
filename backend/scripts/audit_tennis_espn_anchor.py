#!/usr/bin/env python3
"""THE NEEDLE for lane1/057 STEP 0: do our tennis rows agree with ESPN?

Two numbers, both re-derivable by anyone with an ``ADMIN_TOKEN``:

    ANCHOR COVERAGE      how many tennis events on today's board carry the
                         ESPN competition id they belong to
    CONTRADICTIONS       how many of them say something the authority denies

The target for both is stated as a pair, because either one alone lies.  100%
coverage with the contradictions unread would be an audit of a join; zero
contradictions over three anchored rows would be a rounding error.  The bar is
**every anchorable US Open row anchored, and contradictions == 0**.

═══ WHAT IT MEASURED THE DAY IT WAS WRITTEN (2026-09-02T21:0xZ) ═══

    events in window           194
    anchored                   190   174 exact / 13 names-agree / 3 pairing-anchored
    refused                      4   every one a player NOT IN THE DRAW
    contradictions               5   3 live-and-completed
                                     1 settled-but-in-play  (Linette v Jones)
                                     1 in-play-but-decided   (Jodar v Bu)

The 4 refusals are the finding, not the shortfall — see
``app/utils/espn_tennis_anchor``.  A refusal whose ``absent_players`` is empty
would be a different animal entirely (our matcher failing on two players who ARE
both in the draw), and this script prints the two classes separately so they can
never be read as one number.

Read-only against the database: uses ``/api/admin/db-query`` (needs
``ADMIN_TOKEN`` + ``BAINLUCK_API``; ``source ~/.claude/.env``) and ESPN's public
tennis scoreboard.  Writes nothing anywhere.

    python3 scripts/audit_tennis_espn_anchor.py
    python3 scripts/audit_tennis_espn_anchor.py --sport-key-like 'tennis%'
    python3 scripts/audit_tennis_espn_anchor.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.espn_tennis import (  # noqa: E402
    fetch_scoreboards,
    scoreboard_competitions,
)
from app.utils.espn_tennis_anchor import (  # noqa: E402
    REJECT_OFF_BOARD,
    anchor_receipt,
    anchorable_sport_keys,
    state_contradiction,
)

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
TOKEN = os.environ.get("ADMIN_TOKEN", "")

#: Same window the task uses — see ``espn_sync.TENNIS_ANCHOR_WINDOW_DAYS``. A
#: needle measured over a different population than the rail it watches is a
#: needle that can read green while the rail is broken.
WINDOW_DAYS = 21


def db_query(sql: str, limit: int = 1000) -> list[dict]:
    """Run a read-only SQL query via the admin endpoint; return list-of-dicts."""
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"db-query {exc.code}: {detail}\nSQL: {sql[:200]}") from None
    cols = payload["columns"]
    return [dict(zip(cols, row)) for row in payload["rows"]]


def _moment(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Default: the SAME scope the rail writes on — the buckets naming a
    # tournament this board carries. `--sport-key-like 'tennis%'` widens it to
    # every tennis row, which is how the twin population gets counted; that view
    # is a measurement of #2693 step 2's backlog, not of this rail.
    parser.add_argument("--sport-key-like", default=None)
    parser.add_argument("--dates", default=None, help="ESPN YYYYMMDD; omit for today")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    payloads, errors = fetch_scoreboards(args.dates)
    if not payloads:
        # AUTHORITY DARK is not a green needle (gotcha #53). Exit non-zero so a
        # scheduled caller cannot read a failed fetch as "nothing wrong".
        print(f"AUTHORITY DARK — both tours failed: {errors}", file=sys.stderr)
        return 3

    competitions = scoreboard_competitions(payloads)
    by_id = {c["espn_competition_id"]: c for c in competitions}

    if args.sport_key_like:
        key_clause = f"s.key LIKE '{args.sport_key_like}'"
        scope = args.sport_key_like
    else:
        all_keys = [r["key"] for r in db_query(
            "SELECT key FROM sports WHERE key LIKE 'tennis%'", limit=1000)]
        wanted = anchorable_sport_keys(all_keys, competitions)
        if not wanted:
            print("No sport bucket matches the tournament on the board.", file=sys.stderr)
            return 3
        key_clause = "s.key IN (" + ", ".join(f"'{k}'" for k in wanted) + ")"
        scope = ", ".join(wanted)

    now = datetime.now(timezone.utc)
    lo = (now - timedelta(days=WINDOW_DAYS)).isoformat()
    hi = (now + timedelta(days=WINDOW_DAYS)).isoformat()
    rows = db_query(
        "SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name, "
        "e.status, e.commence_time, e.completed_at, e.espn_id "
        "FROM events e JOIN sports s ON s.id = e.sport_id "
        f"WHERE {key_clause} "
        "AND e.commence_time IS NOT NULL "
        f"AND e.commence_time >= '{lo}' AND e.commence_time <= '{hi}' "
        "AND e.home_team_name IS NOT NULL AND e.away_team_name IS NOT NULL "
        "ORDER BY e.commence_time DESC",
        limit=1000,
    )

    methods: Counter = Counter()
    refusals: Counter = Counter()
    contradictions: Counter = Counter()
    fabricated: list[dict] = []
    unmatched: list[dict] = []
    contradicting: list[dict] = []
    stale_anchor = 0
    anchored = 0
    off_board = 0

    # AN ESPN COMPETITION ANCHORS AT MOST ONE OF OUR EVENTS — resolved over the
    # whole population first, exactly as the rail does it. A needle that counted
    # a contested competition as anchored would read green on rows the task
    # deliberately refuses to write (`espn_sync._sync_tennis_from_espn`).
    receipts = {}
    claimants: dict[str, list] = {}
    for row in rows:
        receipt = anchor_receipt(
            [row["home_team_name"], row["away_team_name"]],
            competitions,
            our_commence_time=_moment(row["commence_time"]),
        )
        receipts[row["id"]] = receipt
        if receipt["espn_competition_id"]:
            claimants.setdefault(receipt["espn_competition_id"], []).append(row["id"])
    contested = {c: ids for c, ids in claimants.items() if len(ids) > 1}

    for row in rows:
        ours = [row["home_team_name"], row["away_team_name"]]
        receipt = receipts[row["id"]]
        comp_id = receipt["espn_competition_id"]

        if comp_id is not None and comp_id in contested:
            continue

        if comp_id is None:
            refusals[receipt["reason"]] += 1
            record = {
                "event_id": row["id"],
                "pairing": f"{ours[0]} v {ours[1]}",
                "status": row["status"],
                "reason": receipt["reason"],
                "absent_players": receipt["absent_players"],
                "candidates": receipt["candidates"],
            }
            # THREE DIFFERENT THINGS, AND ONLY ONE IS A DEFECT.
            #
            # `off-board` is a fixture from a tournament this scoreboard does
            # not carry — the ordinary case at any scope wider than the event
            # on the board, and the reason the default scope is the US Open.
            # `no-candidate` with an absent player is the fabricated-pairing
            # shape. `no-candidate` with both players present is OUR matcher
            # failing, which is the one that would need code.
            if receipt["reason"] == REJECT_OFF_BOARD:
                off_board += 1
            elif receipt["absent_players"]:
                fabricated.append(record)
            else:
                unmatched.append(record)
            continue

        anchored += 1
        methods[receipt["method"]] += 1
        if row.get("espn_id") != comp_id:
            # The rail has not written this link yet (or wrote a different one).
            # Counted so "the matcher can anchor it" is never mistaken for "the
            # database holds the anchor" — the whole point of STEP 0.
            stale_anchor += 1

        contradiction = state_contradiction(
            row["status"], _moment(row["completed_at"]), by_id[comp_id]["state"],
            competition=by_id[comp_id], now=now,
        )
        if contradiction:
            contradictions[contradiction] += 1
            contradicting.append({
                "event_id": row["id"],
                "pairing": f"{ours[0]} v {ours[1]}",
                "kind": contradiction,
                "ours": f"{row['status']} / completed_at={row['completed_at']}",
                "espn": by_id[comp_id]["state"],
                "espn_competition_id": comp_id,
            })

    result = {
        "measured_at": now.isoformat(),
        "scope": scope,
        "fetch_errors": errors,
        "competitions_on_board": len(competitions),
        "events_in_window": len(rows),
        "anchored": anchored,
        "anchor_coverage_pct": round(100 * anchored / len(rows), 1) if rows else 0.0,
        "anchors_not_yet_written": stale_anchor,
        "by_method": dict(methods),
        "refused": dict(refusals),
        "off_board": off_board,
        "contested_competitions": len(contested),
        "contested_events": sum(len(v) for v in contested.values()),
        "contested_detail": {c: ids for c, ids in list(contested.items())[:50]},
        "fabricated_pairings": fabricated,
        "unmatched_both_players_present": unmatched,
        "contradictions": dict(contradictions),
        "contradiction_rows": contradicting,
    }

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"ESPN tennis anchor — {now.isoformat()}")
        print(f"  scope            {scope}")
        print(f"  board            {len(competitions)} singles competitions"
              f"{'  ERRORS: ' + str(errors) if errors else ''}")
        print(f"  events in window {len(rows)}")
        print(f"  ANCHORED         {anchored} ({result['anchor_coverage_pct']}%)  "
              f"{dict(methods)}")
        print(f"  not yet written  {stale_anchor}")
        print(f"  refused          {sum(refusals.values())}  {dict(refusals)}")
        print(f"  off board        {off_board}  (another tournament — not a defect)")
        print(f"  CONTESTED        {sum(len(v) for v in contested.values())} events over "
              f"{len(contested)} competitions — duplicate instances, anchored to nobody")
        for comp, ids in list(contested.items())[:10]:
            print(f"    ESPN {comp}  claimed by {ids}")
        if fabricated:
            print(f"\n  FABRICATED PAIRINGS ({len(fabricated)}) — a named player is not in the draw:")
            for f in fabricated:
                print(f"    {f['event_id']}  {f['pairing']}  [{f['status']}]"
                      f"  absent: {', '.join(f['absent_players'])}")
        if unmatched:
            print(f"\n  UNMATCHED, BOTH PLAYERS PRESENT ({len(unmatched)}) — matcher gap:")
            for u in unmatched:
                print(f"    {u['event_id']}  {u['pairing']}  {u['reason']}"
                      f"  candidates={u['candidates']}")
        print(f"\n  CONTRADICTIONS   {sum(contradictions.values())}  {dict(contradictions)}")
        for c in contradicting:
            print(f"    {c['event_id']}  {c['pairing']}")
            print(f"        {c['kind']}: ours={c['ours']}  espn={c['espn']}")

    # Exit code is the needle: 0 only when the authority and the database agree.
    # `stale_anchor` counts too — a link the matcher can make and the rail has
    # not written is the rail not running, which is exactly what this watches.
    return 0 if not contradictions and not stale_anchor and not contested else 1


if __name__ == "__main__":
    sys.exit(main())
