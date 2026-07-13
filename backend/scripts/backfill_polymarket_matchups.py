#!/usr/bin/env python3
"""A2 title-backfill — stamp the group matchup onto Polymarket game sub-markets.

Closes the poly ``market_event`` shadow gap (see
``app/utils/polymarket_matchup_backfill.py``): a Polymarket game is stored as
decomposed sub-market rows and the spread/prop rows lose the "A vs. B" matchup, so
the resolution engine reads zero participants and can't reproduce their stored
event link. This backfills ``market_metadata['matchup_title']`` — recovered from a
sibling row in the SAME Polymarket group (``group_id``), never from the event — so
``annotate_stored_market`` can recover both participants.

Idempotent + additive: only writes ``matchup_title`` where it is missing, via a
Core ``||`` JSONB merge that preserves every other metadata key. Scoped by default
to LINKED poly markets (``event_id IS NOT NULL``) — the rows the win-prob blend and
the shadow audit measure; ``--all`` also backfills unlinked game groups.

Usage:
    heroku run --app bainluck python3 backend/scripts/backfill_polymarket_matchups.py --dry-run
    heroku run --app bainluck python3 backend/scripts/backfill_polymarket_matchups.py
    heroku run --app bainluck python3 backend/scripts/backfill_polymarket_matchups.py --all
"""
import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import cast, func, literal, select, update  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402

from app.models.models import FuturesMarket  # noqa: E402
from app.services.database import async_session_maker  # noqa: E402
from app.utils.polymarket_matchup_backfill import (  # noqa: E402
    group_matchup,
    needs_matchup_backfill,
)

PAGE = 5000


def _group_key(group_id, poly_event_id) -> str | None:
    if group_id:
        return group_id
    if poly_event_id:
        return f"polymarket:{poly_event_id}"
    return None


async def _load_rows(session, linked_only: bool) -> list[dict]:
    """(id, name, group key, existing matchup_title) for poly markets, paged."""
    rows: list[dict] = []
    offset = 0
    while True:
        stmt = (
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.group_id,
                FuturesMarket.market_metadata["polymarket_event_id"].astext,
                FuturesMarket.market_metadata["matchup_title"].astext,
            )
            .where(FuturesMarket.source == "polymarket")
            .order_by(FuturesMarket.id)
            .offset(offset)
            .limit(PAGE)
        )
        if linked_only:
            stmt = stmt.where(FuturesMarket.event_id.isnot(None))
        batch = (await session.execute(stmt)).all()
        if not batch:
            break
        offset += PAGE
        for mid, name, group_id, poly_ev, matchup_title in batch:
            gk = _group_key(group_id, poly_ev)
            if not gk:
                continue
            rows.append(
                {"id": mid, "name": name, "gk": gk, "matchup_title": matchup_title}
            )
    return rows


async def _run(dry_run: bool, linked_only: bool) -> None:
    async with async_session_maker() as session:
        rows = await _load_rows(session, linked_only)
        by_group: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_group[r["gk"]].append(r)
        print(f"Loaded {len(rows)} poly markets across {len(by_group)} groups "
              f"(linked_only={linked_only})")

        game_groups = 0
        to_update: list[tuple[int, str]] = []
        for gk, members in by_group.items():
            matchup = group_matchup(m["name"] for m in members)
            if not matchup:
                continue  # not a game group — no sibling names a matchup
            game_groups += 1
            for m in members:
                if needs_matchup_backfill(m["name"], m["matchup_title"]):
                    to_update.append((m["id"], matchup))

        print(f"Game groups: {game_groups}; rows needing matchup_title: {len(to_update)}")
        if dry_run:
            for mid, mt in to_update[:15]:
                print(f"  would set id={mid} matchup_title={mt!r}")
            print("DRY RUN — no writes committed.")
            return

        empty = cast(literal("{}"), JSONB)
        applied = 0
        for mid, mt in to_update:
            merged = func.coalesce(FuturesMarket.market_metadata, empty).op("||")(
                func.jsonb_build_object("matchup_title", mt)
            )
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == mid)
                .values(market_metadata=merged)
            )
            applied += 1
            if applied % 2000 == 0:
                await session.commit()
                print(f"  committed {applied}/{len(to_update)}")
        await session.commit()
        print(f"Backfilled matchup_title on {applied} poly rows.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Project counts + sample updates without committing.")
    parser.add_argument("--all", action="store_true",
                        help="Also backfill unlinked poly game groups (default: linked only).")
    args = parser.parse_args()
    asyncio.run(_run(args.dry_run, linked_only=not args.all))


if __name__ == "__main__":
    main()
