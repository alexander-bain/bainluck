#!/usr/bin/env python3
"""Derive the attended event-CREATE plan from venue truth (#1796/#1902, queue 363).

Alex, 2026-08-17, ruling the four MC decisions: *attended event-CREATE from venue
truth is APPROVED — for the Aug 5 game and as the ruled pattern (provider
anchors, plan artifact, pre-cert, always attended).*

This script is the DRY RUN. It writes a plan and nothing else — it has no apply
mode at all, deliberately, so that no path through this file can create a row.
The apply lives on the attended rail and consumes the artifact by hash.

Two populations, one derivation, because the first is a subset of the second:

* **population 1** — the single Aug 5 MIN@KC game (`espn:401816407`), which is
  the missing link target behind market ``58609021``'s three-way identity error.
* **population 2** — the 328-game season backfill, whose row #1 is
  ``espn:401816534`` (Sox @ Pirates 2026-08-15), the game Alex reported missing
  from My Stuff (#1925). Population 1 is row N of this same set.

Usage (read-only; requires ADMIN_TOKEN + BAINLUCK_API in the environment)::

    python3 scripts/derive_event_create_plan.py --population 1
    python3 scripts/derive_event_create_plan.py --population 2

Why the team anchors are resolved the long way round
----------------------------------------------------
Club name -> team id is EXACTLY the poisoned path. ``team_identity_mapping``
holds 158 rows whose ``source_name`` is another club's canonical name in the same
sport (#1918), and ``resolve_team`` step 3 auto-registers its hits, so a lookup
that goes through that index can propagate poison into a brand-new row. This
script therefore resolves against ``teams`` directly and REFUSES any club that
does not resolve to exactly one row in the target sport.

That refusal is not theoretical. Every one of the 30 MLB clubs has TWO team rows
carrying the SAME ``espn_id`` — one under ``sport_id`` 33178
(``baseball_mlb_preseason``) and one under 53232 (``baseball_mlb``) — and both
are in live use: 178 regular-season events bind to the latter, 47 spring-training
events to the former. A resolver that took ``name`` alone would have had a 50%
chance of binding 328 regular-season games to preseason club rows, and nothing
downstream would have complained.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.utils.repair_apply_plan import (  # noqa: E402
    PlannedCreate,
    build_create_plan,
    create_gate,
)

HANDOFF = pathlib.Path(__file__).resolve().parents[2] / ".claude/handoff"
TRUTH_SET = HANDOFF / "ARTIFACT-Q362-POPULATION-2-CREATE-SET.json"

#: The regular-season MLB sport row. 33178 is ``baseball_mlb_preseason`` and is
#: NOT interchangeable with it — see the module docstring.
MLB_SPORT_ID = 53232

#: Population 1: the Aug 5 MIN@KC game (#1902). A subset of population 2.
POPULATION_1 = ["401816407"]

#: Row #1 of population 2, asserted by name so a re-derivation that loses Alex's
#: own missing game fails here instead of quietly shipping 327.
ROW_ONE = "401816534"

_LABEL_RE = re.compile(r"^(?P<away>.+?) @ (?P<home>.+?) (?P<date>\d{4}-\d{2}-\d{2})")


def _db_query(sql: str, limit: int = 1000) -> list[list]:
    api = os.environ["BAINLUCK_API"]
    token = os.environ["ADMIN_TOKEN"]
    req = urllib.request.Request(
        f"{api}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": limit}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    if payload.get("truncated"):
        raise SystemExit(
            "db-query TRUNCATED the result. A plan derived from a truncated read "
            "is a plan over a population nobody chose (memory: 1000-row cap)."
        )
    return payload["rows"]


def resolve_clubs(names: set[str]) -> dict[str, tuple[int, str]]:
    """name -> (team_id, espn_id), refusing anything that is not 1:1."""
    inlist = ",".join("'%s'" % n.replace("'", "''") for n in sorted(names))
    rows = _db_query(
        f"SELECT t.name, t.id, coalesce(t.espn_id,'') FROM teams t "
        f"WHERE t.sport_id = {MLB_SPORT_ID} AND t.name IN ({inlist}) ORDER BY t.name"
    )
    by_name: dict[str, list[tuple[int, str]]] = {}
    for name, team_id, espn in rows:
        by_name.setdefault(name, []).append((int(team_id), espn))

    ambiguous = {n: v for n, v in by_name.items() if len(v) != 1}
    missing = sorted(names - set(by_name))
    if ambiguous or missing:
        raise SystemExit(
            "REFUSED — club anchors are not 1:1 in sport "
            f"{MLB_SPORT_ID}. missing={missing} ambiguous={ambiguous}"
        )
    return {n: v[0] for n, v in by_name.items()}


def still_missing(truth_ids: list[str]) -> set[str]:
    """The gate's live half: which reviewed ids have STILL not been created.

    Asked as a set, never as a count. A count is a claim about the world's
    current state that the ordinary pipeline repairs on its own, so it expires
    while nothing is wrong — the measured Aug 10-12 ``2/14 -> 16/0`` inversion.
    """
    inlist = ",".join("'%s'" % i for i in truth_ids)
    present = {
        str(r[0])
        for r in _db_query(
            f"SELECT DISTINCT espn_id FROM events WHERE espn_id IN ({inlist})"
        )
    }
    return set(truth_ids) - present


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", choices=["1", "2"], required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    truth = json.loads(TRUTH_SET.read_text())
    games = {g["espn_id"]: g for g in truth["games"]}
    if ROW_ONE not in games:
        raise SystemExit(f"REFUSED — row #1 {ROW_ONE} absent from the reviewed set")

    wanted = POPULATION_1 if args.population == "1" else truth["truth_ids"]
    for tid in wanted:
        if tid not in games:
            raise SystemExit(f"REFUSED — {tid} is not in the reviewed truth set")

    clubs: set[str] = set()
    parsed: dict[str, tuple[str, str]] = {}
    for tid in wanted:
        m = _LABEL_RE.match(games[tid]["label"])
        if not m:
            raise SystemExit(f"REFUSED — unparseable label for {tid}")
        away, home = m.group("away"), m.group("home")
        parsed[tid] = (away, home)
        clubs.update((away, home))

    anchors = resolve_clubs(clubs)
    live_missing = still_missing(wanted)

    rows = []
    for tid in wanted:
        away, home = parsed[tid]
        rows.append(
            PlannedCreate(
                truth_id=tid,
                provider="espn",
                home_team_id=anchors[home][0],
                away_team_id=anchors[away][0],
                home_name=home,
                away_name=away,
                commence_time=games[tid]["commence"],
                sport_id=MLB_SPORT_ID,
                label=games[tid]["label"],
            )
        )

    plan = build_create_plan(
        rows,
        context={
            "population": args.population,
            "queue": 363,
            "ruling": "Alex 2026-08-17 — attended CREATE from venue truth, approved",
            "truth_set_hash": truth["truth_id_hash"],
            "sport_id": MLB_SPORT_ID,
            "sport_key": "baseball_mlb",
            "row_one": ROW_ONE,
        },
    )

    gate_ok, no_longer_missing = create_gate(plan, live_missing)
    payload = plan.as_payload()
    payload["gate"] = {
        "rule": truth["gate"],
        "passes": gate_ok,
        "no_longer_missing": no_longer_missing,
        "still_missing_count": len(live_missing),
    }

    out = pathlib.Path(
        args.out or HANDOFF / f"ARTIFACT-Q363-CREATE-PLAN-POP{args.population}.json"
    )
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))

    print(f"population       {args.population}")
    print(f"rows             {payload['row_count']}")
    print(f"plan_hash        {payload['plan_hash']}")
    print(f"duplicates       {payload['duplicate_truth_ids']}")
    print(f"doubleheaders    {len(payload['doubleheader_truth_ids'])}")
    print(f"gate passes      {gate_ok}  (no_longer_missing={no_longer_missing})")
    print(f"artifact         {out}")
    return 0 if gate_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
