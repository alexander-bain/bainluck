"""Targeted price refresh for register-pinned tournament markets (UX-P139).

═══ THE DEFECT THIS EXISTS TO FIX ═══

Alex, item 2: "was that the real current price-dark state or a mock artifact?
Then state the production guarantee: with the freshness gates, silently-stale
data can never render."

The freshness gates work — that half of the guarantee has held since UX-P131.
What the gates cannot do is make a number fresh, and measured 2026-08-26 the
entire playoff grid was 27 hours old:

    futures_odds_snapshots, all 672 US Open ladder outcomes
        newest captured_at : 2026-08-25 20:21:47 UTC
        oldest captured_at : 2026-08-25 16:15:28 UTC
    futures_odds_snapshots, Polymarket overall
        newest captured_at : 2026-08-26 23:39:28 UTC   (current to the minute)

So the poller was healthy and these particular markets were not being reached.
The cause is structural, not a bug: Gamma caps offset pagination at 2000
(gotcha "Poly creation freeze"), so ``_poll_polymarket_markets`` rotates a
20-page window across the active-event space and re-prices a given event only
when the cursor lands on it.  For most of the catalogue a once-a-day reading is
fine.  For the 336 markets that ARE the bracket grid on the page whose subject
is what the market thinks right now, it is not.

═══ WHY A REGISTER MAKES THE FIX TRIVIAL ═══

The scanning poll has to discover what exists.  This task does not: the
register already names every market the page will render, as an exact
``(source, market_id, outcome_id)`` triple.  So it asks Gamma for precisely
those condition ids — ``/markets?condition_ids=...``, which does not paginate
and is therefore not subject to the offset cap at all — and updates them.

The whole US Open register is ~420 Polymarket markets, which is 11 batched
requests.  At the 10-minute cadence below that is ~66 Gamma calls an hour
against a limit around 1,000, and it is bounded by the register rather than by
the catalogue: a tournament that ends stops costing anything the moment its
register is retired.

This task NEVER creates a market and never touches identity.  It updates prices
for outcomes the register already pins, which is why it is safe to run at a
cadence the discovery poll could not sustain.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: How many condition ids per Gamma request.  See
#: ``PolymarketAPIService.get_markets_by_conditions``.
BATCH_SIZE = 40

#: A hard ceiling on how many markets one run will refresh, so a mis-sized
#: register can never turn a 10-minute task into a Gamma flood.  Well above the
#: US Open's ~420 and well below anything that would matter.
MAX_MARKETS = 2000


def registered_polymarket_conditions(register: dict[str, Any]) -> dict[str, list[int]]:
    """``condition_id -> [outcome_id, ...]`` for every Polymarket identity pinned.

    Walks players, matchups AND reaches.  Matchups are included even though
    their identities live under ``sides`` — the slate is the other half of the
    page and it has the same problem for the same reason.
    """
    out: dict[str, list[int]] = {}

    def add(block: Any) -> None:
        if not isinstance(block, dict) or block.get("source") != "polymarket":
            return
        condition = block.get("market_external_id")
        if not isinstance(condition, str) or not condition:
            return
        ids = out.setdefault(condition, [])
        if isinstance(block.get("outcome_id"), int):
            ids.append(block["outcome_id"])
        for side in (block.get("sides") or {}).values():
            if isinstance(side, dict) and isinstance(side.get("outcome_id"), int):
                ids.append(side["outcome_id"])

    for player in register.get("players") or []:
        if isinstance(player, dict):
            for block in player.get("sources") or []:
                add(block)
    for matchup in register.get("matchups") or []:
        if isinstance(matchup, dict):
            for block in matchup.get("sources") or []:
                add(block)
    for reach in register.get("reaches") or []:
        if isinstance(reach, dict):
            for block in reach.get("sources") or []:
                add(block)
    return out


async def _refresh_registered_tournament_prices(
    tournaments: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Re-price every Polymarket market a committed tournament register pins."""
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.base import get_task_session
    from app.tasks.polymarket import _resolve_market_probability
    from app.utils.odds_math import probability_to_american
    from app.utils.tournament_register import load_register

    # Explicit, like the route's own table: a register is refreshed because
    # somebody said so, never because a file appeared in a directory.
    targets = tournaments or [("us-open", "2026")]

    stats: dict[str, Any] = {
        "tournaments": 0,
        "conditions_requested": 0,
        "markets_returned": 0,
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "not_returned": 0,
        "errors": [],
    }

    wanted: dict[str, list[int]] = {}
    for tournament, season in targets:
        register = load_register(tournament, season)
        if register is None:
            stats["errors"].append(f"{tournament}-{season}: no readable register")
            continue
        stats["tournaments"] += 1
        for condition, outcome_ids in registered_polymarket_conditions(register).items():
            wanted.setdefault(condition, []).extend(outcome_ids)

    conditions = sorted(wanted)[:MAX_MARKETS]
    stats["conditions_requested"] = len(conditions)
    if not conditions:
        # gotcha #53: "it returned" is not "it worked". Nothing to refresh is a
        # real state, and it is reported as one rather than as a green run.
        stats["verdict"] = "no_registered_polymarket_identities"
        return stats

    service = PolymarketAPIService()
    try:
        markets = await service.get_markets_by_conditions(
            conditions, batch_size=BATCH_SIZE
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        stats["errors"].append(f"gamma fetch failed: {exc}")
        stats["verdict"] = "fetch_failed"
        return stats

    stats["markets_returned"] = len(markets)
    stats["not_returned"] = len(conditions) - len({m.condition_id for m in markets})

    now = datetime.now(timezone.utc)
    async with get_task_session() as session:
        for market in markets:
            probability = _resolve_market_probability(market)
            if probability is None:
                # A placeholder or an untradeable book. Not an error, and not a
                # number: gotcha #19's rule, unchanged.
                stats["unpriced"] += 1
                continue

            rows = (
                await session.execute(
                    select(FuturesOutcome.id, FuturesOutcome.name)
                    .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                    .where(FuturesMarket.external_id == market.condition_id)
                )
            ).all()
            if not rows:
                continue

            for outcome_id, name in rows:
                # The YES side carries the market's resolved probability; the
                # NO side is its complement. Read off the outcome NAME rather
                # than from position: `outcome_prices[1]` and "the row called
                # No" are the same thing only when the source ordered them the
                # way we assumed, and this task has no business re-deriving an
                # ordering the ingest already pinned.
                label = (name or "").strip().lower()
                if label == "yes":
                    value = probability
                elif label == "no":
                    value = 1.0 - probability
                else:
                    continue

                value = max(0.0, min(1.0, value))
                await session.execute(
                    update(FuturesOutcome)
                    .where(FuturesOutcome.id == outcome_id)
                    .values(
                        current_probability=value,
                        current_american_odds=probability_to_american(value),
                        last_updated=now,
                    )
                )
                stats["outcomes_updated"] += 1

                # The snapshot is what `price_observed_at` reads, so a refresh
                # that updated the outcome and wrote no snapshot would move the
                # price while leaving the page's freshness verdict at 27 hours
                # — a number that changed without admitting it had.
                await session.execute(
                    pg_insert(FuturesOddsSnapshot).values(
                        outcome_id=outcome_id,
                        bookmaker="polymarket",
                        probability=value,
                        american_odds=probability_to_american(value),
                        captured_at=now,
                    )
                )
                stats["snapshots_written"] += 1

        await session.commit()

    stats["verdict"] = "ok" if stats["snapshots_written"] else "no_prices_written"
    logger.info("tournament price refresh: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# ESPN results sync (UX-P139, Alex's item 9)
# ---------------------------------------------------------------------------

#: How long a cached results payload stays servable.  Generous relative to the
#: 3-minute sync so one missed run does not blank the section; a genuinely dead
#: task lets it expire, which is the honest outcome — an empty section with a
#: stated reason beats an hour-old result presented as current.
RESULTS_TTL_SECONDS = 900
RESULTS_PREFIX = "bainluck:tournament-results:"


async def _sync_tournament_results(
    tournaments: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Fetch ESPN's tennis results into Redis for the hub route to read.

    THE FETCH LIVES HERE AND NOT IN THE ROUTE, and that is the point of the
    task rather than an implementation detail.  A third-party call inside
    ``GET /api/tournaments/{slug}`` is the shape the feed's standing rule
    forbids by name: the first request after every cache expiry pays the round
    trip, a slow ESPN becomes a slow page for whoever is unlucky, and the route
    contract tests start making live network calls.

    Three minutes, because a finished match should appear while the reader is
    still on the page, and because two scoreboard requests every three minutes
    is nothing.
    """
    from app.tasks.redis_state import get_async_redis_client

    # Named, like the route's own table: a tournament is synced because
    # somebody wrote it down. `espn_event_name` selects it out of a scoreboard
    # that also carries whatever else is on that week.
    targets = tournaments or [("us-open", "US Open")]

    stats: dict[str, Any] = {"tournaments": 0, "written": 0, "errors": []}
    for slug, event_name in targets:
        try:
            from app.services.espn_tennis import fetch_tournament_results

            results = await fetch_tournament_results(event_name)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            stats["errors"].append(f"{slug}: {exc}")
            continue

        stats["tournaments"] += 1
        if results.get("errors"):
            # A partial fetch is written anyway — half the tours is better than
            # none — but the failure travels in the payload so the section can
            # say "we could not reach the feed" rather than "nothing finished".
            stats["errors"].extend(f"{slug}: {e}" for e in results["errors"])

        try:
            await get_async_redis_client().setex(
                f"{RESULTS_PREFIX}{slug}",
                RESULTS_TTL_SECONDS,
                json.dumps(results, default=str),
            )
            stats["written"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"{slug} cache write: {exc}")

    # gotcha #53: "it returned" is not "it worked". A run that wrote nothing is
    # a failure even when nothing raised.
    stats["verdict"] = "ok" if stats["written"] else "nothing_written"
    logger.info("tournament results sync: %s", stats)
    return stats
