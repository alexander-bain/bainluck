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
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.utils.repair_apply_plan import (  # noqa: E402
    build_create_plan,
    create_gate,
)

# The ROW DERIVATION is shared with the live rail (`app.tasks.create_events_from_truth`),
# added queue 369 when that rail was finally built. The two shells read differently —
# this one over `/api/admin/db-query`, the rail over a session — and that is fine. What
# they must NOT do is BUILD differently: the plan is a content address, so a second
# implementation that trims a label or picks the other MLB registry mints a different
# address from the same approval, and the operator is left holding a hash nothing
# accepts. Hence one builder, two readers.
from app.utils.event_create_derivation import (  # noqa: E402
    MLB_SPORT_ID,
    ROW_ONE,
    anchors_from_rows,
    build_rows,
    load_games,
    required_club_names,
    select_population,
    truth_set_path_for,
)

HANDOFF = pathlib.Path(__file__).resolve().parents[2] / ".claude/handoff"

#: The reviewed set now lives in the repo (`backend/app/data/…`) so the deployed rail
#: can read it — handoff is gitignored and does not exist on the dyno. The handoff
#: copy is kept as the fallback for a checkout that predates the move.
TRUTH_SET_LEGACY = HANDOFF / "ARTIFACT-Q362-POPULATION-2-CREATE-SET.json"


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


def resolve_clubs(names: list[str]) -> dict[str, int]:
    """name -> team_id, refusing anything that is not 1:1 (via the shared checker)."""
    inlist = ",".join("'%s'" % n.replace("'", "''") for n in sorted(names))
    rows = _db_query(
        f"SELECT t.name, t.id FROM teams t "
        f"WHERE t.sport_id = {MLB_SPORT_ID} AND t.name IN ({inlist}) ORDER BY t.name, t.id"
    )
    missing = sorted(set(names) - {str(r[0]) for r in rows})
    if missing:
        raise SystemExit(
            f"REFUSED — {len(missing)} club(s) have no row in sport {MLB_SPORT_ID}: {missing}"
        )
    return anchors_from_rows(rows)


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
    ap.add_argument("--population", choices=["1", "2", "3"], required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    committed = pathlib.Path(__file__).resolve().parents[1] / truth_set_path_for(args.population)
    source = committed if committed.exists() else TRUTH_SET_LEGACY
    truth = json.loads(source.read_text())

    # `load_games` asserts row #1 by name and `select_population` refuses any id the
    # reviewed set does not contain — both in the shared module, so the rail applies
    # the identical assertions to the identical file.
    games = load_games(truth)
    wanted = select_population(truth, args.population)
    anchors = resolve_clubs(required_club_names(wanted, games))
    live_missing = still_missing(wanted)
    rows = build_rows(wanted, games, anchors, sport_id=MLB_SPORT_ID)

    plan = build_create_plan(
        rows,
        context={
            "population": args.population,
            "queue": 363,
            "ruling": "Alex 2026-08-17 — attended CREATE from venue truth, approved",
            "truth_set_hash": truth["truth_id_hash"],
            "sport_id": MLB_SPORT_ID,
            "sport_key": "baseball_mlb",
            "row_one": truth.get("row_one", ROW_ONE),
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
