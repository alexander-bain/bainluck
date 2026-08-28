#!/usr/bin/env python3
"""Build ONE event page's tournament extensions offline, from production (UX-P152).

Same posture as ``capture_match_payload.py`` and for the same reason: the branch
that serves ``/api/tournaments/by-event/{id}`` is not deployed, so an artifact
for Alex's verdict has to be assembled from production *inputs* through the
shipped *functions*.  Every ``build_*`` call below is the one the route makes,
imported rather than re-implemented — including the id-anchored event
resolution, which is the whole architectural claim this queue is making and
therefore the last thing that should be faked in the artifact.

It also captures what the event page renders ABOVE the extensions — the event
row and its probability history — so the mock is the whole page and not the new
section floating on white.  Those two come from the public API, which is already
serving them today.

Usage:
    source ~/.claude/.env
    python3 scripts/capture_event_tournament.py --slug us-open \\
        --pick richest --out-dir ../docs/mocks/us-open
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routes.tournaments import REGISTERED_TOURNAMENTS  # noqa: E402
from app.utils.tournament_advancement import build_advancement  # noqa: E402
from app.utils.tournament_board import build_boards  # noqa: E402
from app.utils.tournament_event_link import (  # noqa: E402
    _resolve_one,
    pinned_market_ids,
)
from app.utils.tournament_grid import build_grids  # noqa: E402
from app.utils.tournament_match import build_match_detail  # noqa: E402
from app.utils.tournament_register import TournamentRegister, load_register  # noqa: E402
from app.utils.tournament_slate import build_results  # noqa: E402
from scripts.capture_match_payload import _live_block, load_group  # noqa: E402
from scripts.capture_tournament_payload import _db_query, _espn, _load_prices  # noqa: E402

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")


def _api(path: str) -> Any:
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as response:
        return json.loads(response.read())


def market_event_ids(market_ids: list[int]) -> dict[int, Optional[int]]:
    """``resolve_matchup_events``' one query, over the wire."""
    if not market_ids:
        return {}
    ids = ",".join(str(int(m)) for m in market_ids)
    return {
        int(mid): (int(eid) if eid is not None else None)
        for mid, eid in _db_query(
            f"SELECT id, event_id FROM futures_markets WHERE id IN ({ids})"
        )
    }


def resolve_links(register: dict[str, Any]) -> dict[str, Any]:
    """``resolve_matchup_events``, with the query swapped for the wire one.

    The pure half — `_resolve_one`, the refusal table, the double-claim drop —
    is the shipped function, imported. Only the SQL is different, and it is the
    same SQL.
    """
    matchups = [m for m in (register.get("matchups") or []) if isinstance(m, dict)]
    lookup = market_event_ids(
        sorted({mid for m in matchups for mid in pinned_market_ids(m)})
    )

    by_matchup: dict[str, int] = {}
    unresolved: dict[str, str] = {}
    claims: dict[int, list[str]] = {}
    for matchup in matchups:
        key = str(matchup.get("matchup_key") or "")
        if not key:
            continue
        event_id, reason = _resolve_one(matchup, lookup)
        if event_id is None:
            unresolved[key] = reason or "NO_PINNED_MARKET"
            continue
        by_matchup[key] = event_id
        claims.setdefault(event_id, []).append(key)

    by_event: dict[int, str] = {}
    for event_id, keys in claims.items():
        if len(keys) == 1:
            by_event[event_id] = keys[0]
        else:
            for key in keys:
                by_matchup.pop(key, None)
                unresolved[key] = "EVENT_DISAGREEMENT"

    counts: dict[str, int] = {}
    for reason in unresolved.values():
        counts[reason] = counts.get(reason, 0) + 1
    return {"by_matchup": by_matchup, "by_event": by_event, "reason_counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="us-open")
    parser.add_argument(
        "--pick",
        default="richest",
        help="'richest' (most sibling props), 'advancement' (both players on "
        "the reach board), or a matchup key",
    )
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    spec = REGISTERED_TOURNAMENTS[args.slug]
    register = load_register(args.slug, spec["season"])
    if register is None:
        raise SystemExit(f"no register for {args.slug}")

    links = resolve_links(register)
    print(
        f"event links: {len(links['by_matchup'])} resolved, "
        f"unresolved {links['reason_counts']}",
        file=sys.stderr,
    )
    if not links["by_matchup"]:
        raise SystemExit(
            "no matchup dereferences to an events row — nothing to capture. "
            "This is the honest failure: the artifact must not be assembled "
            "from a fixture the shipped path could not reach."
        )

    reg = TournamentRegister(register)

    # The hub's own grids, built exactly as `_hub_payload` builds them, so the
    # advancement strip in the artifact is a slice of the real grid.
    board_outcome_ids = sorted(
        {
            b["outcome_id"]
            for p in reg.players
            for b in (p.get("sources") or [])
            if isinstance(b, dict) and isinstance(b.get("outcome_id"), int)
        }
    )
    grid_prices = _load_prices(
        sorted(set(board_outcome_ids) | set(reg.reach_outcome_ids()))
    )
    boards = build_boards(
        register,
        prices={
            (b.get("source"), b.get("market_id"), b.get("outcome_id")): loaded
            for p in reg.players
            for b in (p.get("sources") or [])
            if isinstance(b, dict)
            and (loaded := grid_prices.get(b.get("outcome_id"))) is not None
        },
        series_by_outcome={},
        now=now,
    )
    grids = build_grids(
        register, boards=boards.get("boards") or [], prices=grid_prices, now=now
    )

    # ── Pick the fixture ──
    candidates = sorted(links["by_matchup"])
    if args.pick == "advancement":
        on_board = {
            r["entity_key"]
            for g in grids.values()
            for r in g["rows"]
            if any(
                isinstance(c.get("probability"), (int, float))
                for c in r["cells"].values()
            )
        }
        by_key = {str(m.get("matchup_key")): m for m in reg.matchups}
        candidates = [
            k
            for k in candidates
            if all(p in on_board for p in (by_key[k].get("players") or []))
        ]
        if not candidates:
            raise SystemExit("no linked fixture has both players on the reach board")
        matchup_key = candidates[0]
    elif args.pick == "richest":
        best: Optional[tuple[int, str]] = None
        by_key = {str(m.get("matchup_key")): m for m in reg.matchups}
        for key in candidates:
            block = _live_block(by_key[key])
            market_id = (block or {}).get("market_id")
            if not isinstance(market_id, int):
                continue
            _group, markets = load_group(market_id)
            if best is None or len(markets) > best[0]:
                best = (len(markets), key)
        if best is None:
            raise SystemExit("no linked fixture has a live market")
        matchup_key = best[1]
    else:
        matchup_key = args.pick

    event_id = links["by_matchup"].get(matchup_key)
    if event_id is None:
        raise SystemExit(f"{matchup_key} does not dereference to an events row")
    print(f"picked {matchup_key} -> event {event_id}", file=sys.stderr)

    matchup = next(
        (m for m in reg.matchups if str(m.get("matchup_key")) == matchup_key)
    )

    # ── What the event page already renders, from the live API ──
    event = _api(f"/api/events/{event_id}")
    history = _api(f"/api/events/{event_id}/history")

    advancement = build_advancement(
        grids,
        matchup=matchup,
        event_id=event_id,
        home_team_name=event.get("home_team"),
        away_team_name=event.get("away_team"),
        tournament_title=spec["title"],
        tournament_slug=args.slug,
    )

    # ── The props, through the route's own path ──
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
            o["outcome_id"]
            for m in prop_markets
            for o in m["outcomes"]
        }
    )
    prices = _load_prices(outcome_ids)
    decided = build_results(
        register, results=asyncio.run(_espn(spec["espn_event_name"])), prices=prices
    )
    result = next(
        (r for r in decided["matches"] if r.get("matchup_key") == matchup_key), None
    )
    detail = build_match_detail(
        register,
        matchup_key,
        prop_markets=prop_markets,
        prices=prices,
        result=result,
        now=now,
    )

    extensions = {
        "event_id": event_id,
        "tournament": {
            "slug": args.slug,
            "title": spec["title"],
            "url": f"/tournaments/{args.slug}",
        },
        "matchup_key": matchup_key,
        "round": matchup.get("round"),
        "draw_label": (grids.get(matchup.get("draw")) or {}).get("label"),
        "advancement": advancement,
        "props": (detail or {}).get("props") or [],
        "props_count": (detail or {}).get("props_count") or 0,
        "props_dropped": (detail or {}).get("props_dropped") or {},
        "decided": bool((detail or {}).get("decided")),
        "result": (detail or {}).get("result"),
        "generated_at": now.isoformat(),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.date().isoformat()
    for name, payload in (
        (f"event-{stamp}.json", event),
        (f"event-history-{stamp}.json", history),
        (f"event-tournament-{stamp}.json", extensions),
        (f"event-links-{stamp}.json", {
            "linked": len(links["by_matchup"]),
            "unresolved": links["reason_counts"],
            "captured_at": now.isoformat(),
        }),
    ):
        (out_dir / name).write_text(json.dumps(payload, indent=2, default=str))
        print(f"wrote {out_dir / name}", file=sys.stderr)

    print(
        f"{extensions['props_count']} questions, "
        f"advancement {'yes' if advancement else 'no'}, "
        f"dropped {extensions['props_dropped']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
