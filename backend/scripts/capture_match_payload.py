#!/usr/bin/env python3
"""Build ONE match page's payload offline, from production data (UX-P149).

Same posture as ``capture_tournament_payload.py`` and for the same reason: the
branch that builds this page is not deployed, so an artifact for Alex's verdict
has to be assembled from production *inputs* through the shipped *functions*.
Everything below reproduces ``routes/tournaments.get_tournament_match`` —
the group hop, the price load, the ESPN join — and every ``build_*`` call is
the one the route makes, imported rather than re-implemented.

``--pick richest`` selects the registered matchup whose group carries the most
sibling markets, because an artifact of a match with two props proves nothing
about the layout of a match with eleven.

Usage:
    source ~/.claude/.env
    python3 scripts/capture_match_payload.py --slug us-open \\
        --pick richest --out ../docs/mocks/us-open/match-2026-08-28.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routes.tournaments import REGISTERED_TOURNAMENTS  # noqa: E402
from app.utils.tournament_match import build_match_detail  # noqa: E402
from app.utils.tournament_register import TournamentRegister, load_register  # noqa: E402
from app.utils.tournament_slate import build_results  # noqa: E402
from scripts.capture_tournament_payload import (  # noqa: E402
    _db_query,
    _espn,
    _load_prices,
)


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _live_block(matchup: dict[str, Any]) -> Optional[dict[str, Any]]:
    return next(
        (
            b for b in (matchup.get("sources") or [])
            if isinstance(b, dict) and b.get("status") == "live"
        ),
        None,
    )


def load_group(winner_market_id: int) -> tuple[Optional[str], list[dict[str, Any]]]:
    """``routes/tournaments._load_match_group``, over the wire."""
    rows = _db_query(
        f"SELECT group_id FROM futures_markets WHERE id = {int(winner_market_id)}"
    )
    if not rows or not rows[0][0]:
        return None, []
    group_id = str(rows[0][0])

    markets: dict[int, dict[str, Any]] = {}
    for mid, name, source, external, oid, oname, oext in _db_query(
        "SELECT m.id, m.name, m.source, m.external_id, o.id, o.name, o.external_id "
        "FROM futures_markets m JOIN futures_outcomes o ON o.market_id = m.id "
        f"WHERE m.group_id = {_sql_str(group_id)} ORDER BY m.id, o.id"
    ):
        if int(mid) == int(winner_market_id):
            continue
        if group_id == f"{source}:{external}":
            continue
        entry = markets.setdefault(
            int(mid), {"market_id": int(mid), "name": name, "outcomes": []}
        )
        entry["outcomes"].append(
            {"outcome_id": int(oid), "name": oname, "external_id": oext}
        )
    return group_id, list(markets.values())


def pick_richest(reg: TournamentRegister) -> Optional[str]:
    """The registered matchup whose Polymarket group carries the most props."""
    best: Optional[tuple[int, str]] = None
    for matchup in reg.matchups:
        block = _live_block(matchup)
        market_id = (block or {}).get("market_id")
        if not isinstance(market_id, int):
            continue
        _group, markets = load_group(market_id)
        count = len(markets)
        key = str(matchup.get("matchup_key"))
        print(f"  {key}: {count} sibling markets", file=sys.stderr)
        if best is None or count > best[0]:
            best = (count, key)
    return best[1] if best else None


def build(slug: str, matchup_key: Optional[str], *, now: datetime) -> dict[str, Any]:
    spec = REGISTERED_TOURNAMENTS[slug]
    register = load_register(slug, spec["season"])
    if register is None:
        raise SystemExit(f"no register for {slug}")
    reg = TournamentRegister(register)

    if matchup_key in (None, "richest"):
        matchup_key = pick_richest(reg)
        print(f"picked {matchup_key}", file=sys.stderr)
    if matchup_key is None:
        raise SystemExit("no matchup with a live source")

    matchup = next(
        (m for m in reg.matchups if str(m.get("matchup_key")) == matchup_key), None
    )
    if matchup is None:
        raise SystemExit(f"no registered matchup {matchup_key}")

    block = _live_block(matchup)
    winner_market_id = (block or {}).get("market_id")
    prop_markets: list[dict[str, Any]] = []
    if isinstance(winner_market_id, int):
        _group, prop_markets = load_group(winner_market_id)

    outcome_ids = sorted(
        {
            side.get("outcome_id")
            for side in ((block or {}).get("sides") or {}).values()
            if isinstance(side, dict) and isinstance(side.get("outcome_id"), int)
        }
        | {
            outcome["outcome_id"]
            for market in prop_markets
            for outcome in market["outcomes"]
        }
    )
    prices = _load_prices(outcome_ids)

    espn = asyncio.run(_espn(spec["espn_event_name"]))
    decided = build_results(register, results=espn, prices=prices)
    result = next(
        (r for r in decided["matches"] if r.get("matchup_key") == matchup_key), None
    )

    payload = build_match_detail(
        register,
        matchup_key,
        prop_markets=prop_markets,
        prices=prices,
        result=result,
        now=now,
    )
    if payload is None:
        raise SystemExit(f"{matchup_key} is registered but not renderable")
    payload["slug"] = slug
    payload["title"] = spec["title"]
    payload["subtitle"] = spec["subtitle"]
    payload["broadcasts"] = reg.broadcasts
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="us-open")
    parser.add_argument("--matchup-key", default="richest")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    payload = build(args.slug, args.matchup_key, now=now)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        f"wrote {out} — {payload['props_count']} questions, "
        f"dropped {payload['props_dropped']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
