#!/usr/bin/env python3
"""Build the tournament page payload OFFLINE, from production prices (UX-P139).

═══ WHY THIS EXISTS ═══

Alex, item 2: "Alex was spooked by 15-day-old data in the mock. Answer plainly
in your report: was that the real current price-dark state or a mock artifact?"

It was real, and the mock is *why he could not tell*.  ``payload-2026-08-25.json``
was a frozen production read whose board legs were genuinely 15 to 33 days dark
at the moment it was captured, and it then sat in the repo unchanged while the
world moved.  A capture rig that freezes a payload has two failure modes that
look identical from the artifact: the data was stale, or the *file* was.  This
script removes the second one by making a re-capture a one-line operation, so
every artifact carries a payload read minutes before it was rendered.

═══ WHY IT IS NOT JUST `curl $API/api/tournaments/us-open-2026` ═══

The branch that BUILDS the grid is not deployed — that is the whole point of
capturing an artifact for a verdict before the ship.  So this reproduces
``routes/tournaments.get_tournament`` exactly, against production data:

  * prices and trend series come from production over ``/api/admin/db-query``,
    reproducing ``_load_prices`` (current_probability + max(captured_at), never
    ``last_updated`` — the Day-1 census measured that a month stale while its
    snapshots ran current) and ``_load_series`` (daily mean, TREND_DAYS window);
  * every ``build_*`` call is the SAME function the route calls, imported, not
    re-implemented.  A capture that re-implements the server is a capture of
    something nobody ships.

The ESPN results leg is fetched live from the same public scoreboard the route
uses, so the finished-match section in the artifact is real too.

Usage:
    source ~/.claude/.env
    python3 scripts/capture_tournament_payload.py \\
        --slug us-open-2026 \\
        --out ../docs/mocks/us-open/payload-2026-08-27.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routes.tournaments import REGISTERED_TOURNAMENTS  # noqa: E402
from app.utils.tournament_board import TREND_DAYS, build_boards  # noqa: E402
from app.utils.tournament_grid import build_grids  # noqa: E402
from app.utils.tournament_register import TournamentRegister, load_register  # noqa: E402
from app.utils.tournament_slate import (  # noqa: E402
    build_bracket,
    build_props,
    build_results,
    build_slate,
)

#: db-query silently truncates at 1000 rows (a standing gotcha), so every read
#: here is batched under that and the batch count is asserted rather than hoped.
BATCH = 200


def _db_query(sql: str, *, limit: int = 1000) -> list[list[Any]]:
    api = os.environ["BAINLUCK_API"]
    token = os.environ["ADMIN_TOKEN"]
    body = json.dumps({"sql": sql, "limit": limit})
    proc = subprocess.run(
        [
            "curl", "-s", "-m", "90",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/json",
            "-X", "POST", "-d", body,
            f"{api}/api/admin/db-query",
        ],
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    if "rows" not in payload:
        raise SystemExit(f"db-query refused: {proc.stdout[:600]}")
    rows = payload["rows"]
    if len(rows) >= limit:
        # The 1000-row cap truncates SILENTLY. A capture that hit it would drop
        # prices and render as `unlinked` alarms — a fabricated defect, which is
        # worse than no artifact at all.
        raise SystemExit(f"db-query hit the {limit}-row cap; reduce the batch")
    return rows


def _load_prices(outcome_ids: list[int]) -> dict[int, dict[str, Any]]:
    """``routes/tournaments._load_prices``, over the wire.

    The price is ``futures_outcomes.current_probability``; the freshness is
    ``max(futures_odds_snapshots.captured_at)``.  Two different tables on
    purpose — see the route's own docstring for why ``last_updated`` is not
    trusted for either.
    """
    if not outcome_ids:
        return {}

    out: dict[int, dict[str, Any]] = {}
    for start in range(0, len(outcome_ids), BATCH):
        chunk = outcome_ids[start : start + BATCH]
        ids = ",".join(str(i) for i in chunk)
        for oid, name, current, opening in _db_query(
            f"SELECT id, name, current_probability, opening_probability "
            f"FROM futures_outcomes WHERE id IN ({ids})"
        ):
            out[int(oid)] = {
                "probability": float(current) if current is not None else None,
                "opening_probability": float(opening) if opening is not None else None,
                "observed_at": None,
                "source_name": name,
            }
        for oid, observed in _db_query(
            f"SELECT outcome_id, MAX(captured_at) FROM futures_odds_snapshots "
            f"WHERE outcome_id IN ({ids}) AND probability IS NOT NULL "
            f"GROUP BY outcome_id"
        ):
            if int(oid) in out and observed:
                out[int(oid)]["observed_at"] = datetime.fromisoformat(str(observed))
    return out


def _load_series(
    outcome_ids: list[int], *, now: datetime
) -> dict[int, list[tuple[str, float]]]:
    """``routes/tournaments._load_series``, over the wire. Daily mean per outcome."""
    if not outcome_ids:
        return {}
    cutoff = (now - timedelta(days=TREND_DAYS)).isoformat()
    series: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for start in range(0, len(outcome_ids), BATCH):
        chunk = outcome_ids[start : start + BATCH]
        ids = ",".join(str(i) for i in chunk)
        rows = _db_query(
            f"SELECT outcome_id, date_trunc('day', captured_at) AS day, "
            f"AVG(probability) AS probability FROM futures_odds_snapshots "
            f"WHERE outcome_id IN ({ids}) AND captured_at >= '{cutoff}' "
            f"AND probability IS NOT NULL "
            f"GROUP BY outcome_id, day ORDER BY outcome_id, day"
        )
        for oid, day, probability in rows:
            if probability is None or day is None:
                continue
            series[int(oid)].append(
                (str(day)[:10], float(probability))
            )
    return dict(series)


async def _espn(event_name: str) -> dict[str, Any]:
    try:
        from app.services.espn_tennis import fetch_tournament_results

        return await fetch_tournament_results(event_name)
    except Exception as exc:  # noqa: BLE001 — a capture must not die on ESPN
        print(f"  ESPN results unavailable: {exc}", file=sys.stderr)
        return {"draws": {}, "stats": {}, "errors": [str(exc)]}


def build_payload(slug: str, *, now: datetime) -> dict[str, Any]:
    spec = REGISTERED_TOURNAMENTS[slug]
    register = load_register(slug, spec["season"])
    if register is None:
        raise SystemExit(f"no register for {slug}")

    reg = TournamentRegister(register)
    board_outcome_ids = sorted(
        {
            block["outcome_id"]
            for player in reg.players
            for block in (player.get("sources") or [])
            if isinstance(block, dict) and isinstance(block.get("outcome_id"), int)
        }
    )
    every = sorted(
        set(board_outcome_ids)
        | set(reg.matchup_outcome_ids())
        | set(reg.prop_outcome_ids())
        | set(reg.reach_outcome_ids())
    )
    print(f"  outcomes: {len(every)} ({len(board_outcome_ids)} board)", file=sys.stderr)

    prices = _load_prices(every)
    priced = sum(1 for v in prices.values() if v["probability"] is not None)
    print(f"  priced: {priced} of {len(every)}", file=sys.stderr)
    series = _load_series(board_outcome_ids, now=now)

    by_identity: dict[tuple, dict[str, Any]] = {}
    for player in reg.players:
        for block in player.get("sources") or []:
            if not isinstance(block, dict):
                continue
            loaded = prices.get(block.get("outcome_id"))
            if loaded is None:
                continue
            by_identity[
                (block.get("source"), block.get("market_id"), block.get("outcome_id"))
            ] = loaded

    # ONE FETCH, BOTH HALVES OF THE DAY (Q463) — and hoisted above the slate for
    # the same reason `prices=` was pushed into `build_results` below: a rig that
    # renders the page WITHOUT the feature under review produces a real-looking
    # artifact that proves the opposite of what it appears to. Without this the
    # rig would still draw the empty "No matches scheduled" card this queue
    # exists to kill.
    espn = asyncio.run(_espn(spec["espn_event_name"]))

    payload = build_boards(register, prices=by_identity, series_by_outcome=series, now=now)
    payload["slate"] = build_slate(
        register,
        prices=prices,
        now=now,
        order_of_play=espn.get("order_of_play") or {},
    )
    payload["props"] = build_props(register, prices=prices, now=now)
    payload["grids"] = build_grids(
        register, boards=payload.get("boards") or [], prices=prices, now=now
    )
    payload["bracket"] = {
        draw: build_bracket(register, prices=prices, draw=draw)
        for draw in ("mens-singles", "womens-singles")
    }
    # `prices=` — WITHOUT IT THIS RIG CANNOT DRAW THE THING IT IS FOR (UX-P147).
    #
    # UX-P146 gave `build_results` a second leg: the pre-match probability
    # beside each name, read from `opening_probability` on the matchup outcomes.
    # The ROUTE passes `prices` (`routes/tournaments.py`); this rig did not, and
    # `_prematch_by_pair` degrades silently to an empty map when it cannot look
    # a price up — an absent prior is a legitimate state on 64 of 76 rows, so
    # nothing anywhere reported that the column had gone.
    #
    # Alex is being asked to judge that exact column tonight (item 4: the pair
    # summing to 101). A rig that renders the page WITHOUT the feature under
    # review is worse than no rig: it produces a real-looking artifact that
    # proves the opposite of what it appears to.
    #
    # It costs no query. `reg.matchup_outcome_ids()` is already in the one
    # `IN (...)` above, exactly as the route's own comment says of its version.
    payload["results"] = build_results(register, results=espn, prices=prices)
    payload["broadcasts"] = reg.broadcasts
    payload["slug"] = slug
    payload["title"] = spec["title"]
    payload["subtitle"] = spec["subtitle"]
    payload["draw_release_at"] = spec["draw_release_at"]
    payload["draw_release_label"] = spec["draw_release_label"]
    payload["main_draw_starts_at"] = spec["main_draw_starts_at"]
    payload["main_draw_label"] = spec["main_draw_label"]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="us-open")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    print(f"capturing {args.slug} at {now.isoformat()}", file=sys.stderr)
    payload = build_payload(args.slug, now=now)

    for draw, grid in (payload.get("grids") or {}).items():
        print(
            f"  grid {draw}: {grid['priced_cells']}/{grid['total_cells']} priced, "
            f"{grid['alarm_cells']} alarms, {grid['no_market_cells']} no-market",
            file=sys.stderr,
        )

    Path(args.out).write_text(json.dumps(payload, indent=1, default=str))
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
