"""Combat-targeted, oldest-first win_probability_sources backfill (#178 follow-up).

The on-demand `/api/admin/prediction-markets/backfill-wps` endpoint orders
newest-first (`FuturesMarket.id.desc()`) so a bounded run reaches recent
links/merges.  That ordering can NEVER reach the ~178 older *settled* combat
fights whose Kalshi line was linked but never folded into the event blend — they
sit far down the id ordering behind 170K+ candidates.

This task fixes exactly that population: Kalshi combat fight-winner markets
(`KXUFCFIGHT*` / `KXBOXING*`, the `COMBAT_FIGHT_WINNER_PREFIXES` that
`feeds_win_prob_blend` accepts) on completed/closed/resolved events whose blend
is missing the `kalshi` source — ordered OLDEST-first by commence_time so the
long tail of settled fights gets covered.

Reuses the endpoint's exact blend logic (strip the `NNN: ` sport_id name prefix,
ticker-fallback matchup extraction, moneyline resolution, Core JSONB update —
gotcha #4).  Idempotent (skips events that already carry the kalshi blend) and
commits per batch so a soft-limit overrun leaves progress (gotcha #6/#13).
"""

import logging
import re as _re

from sqlalchemy import or_, select, update
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

_COMMIT_EVERY = 25


async def _backfill_combat_wps(limit: int = 500, dry_run: bool = False) -> dict:
    """Fold Kalshi combat fight-winner lines into settled events' blend, oldest-first."""
    from app.models.models import Event, FuturesMarket
    from app.tasks.base import get_task_session
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        feeds_win_prob_blend,
        find_moneyline_outcome,
    )

    stats = {
        "processed": 0, "written": 0, "skipped_has_blend": 0,
        "skipped_no_matchup": 0, "skipped_no_moneyline": 0,
        "errors": 0, "dry_run": dry_run,
    }

    async with get_task_session() as session:
        query = (
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.isnot(None),
                Event.status.in_(("completed", "closed", "resolved")),
                or_(
                    FuturesMarket.external_id.ilike("kxufcfight%"),
                    FuturesMarket.external_id.ilike("kxboxing%"),
                ),
            )
            # OLDEST-first — the whole point: reach the settled-fight tail the
            # newest-first endpoint can't. NULLS LAST so undated rows don't jump
            # the queue.
            .order_by(Event.commence_time.asc().nullslast())
            .limit(limit)
        )
        result = await session.execute(query)
        rows = result.unique().all()

        # Prefer the blend-eligible fight-winner line per event (combat prefixes
        # all pass feeds_win_prob_blend, but a single event can carry prop
        # siblings that were also fetched).
        by_event = {}
        for market, event in rows:
            key = event.id
            if key not in by_event or feeds_win_prob_blend(market.external_id):
                by_event[key] = (market, event)

        n = 0
        for eid, (market, event) in by_event.items():
            stats["processed"] += 1
            wps = event.win_probability_sources or {}
            if "kalshi" in wps:
                stats["skipped_has_blend"] += 1
                continue
            if not feeds_win_prob_blend(market.external_id):
                # Defensive — should not happen given the ticker filter.
                stats["skipped_no_matchup"] += 1
                continue

            try:
                clean_name = _re.sub(r"^\s*\d+:\s*", "", market.name or "")
                matchup = extract_matchup_with_ticker_fallback(
                    clean_name, external_id=market.external_id,
                )
                if not matchup:
                    stats["skipped_no_matchup"] += 1
                    continue

                ml = find_moneyline_outcome(
                    list(market.outcomes), matchup,
                    event.home_team_name, event.away_team_name,
                )
                if not ml:
                    stats["skipped_no_moneyline"] += 1
                    continue

                outcome, yes_is_home = ml
                prob = float(outcome.current_probability or 0)
                home_prob = prob if yes_is_home else 1.0 - prob

                if not dry_run:
                    new_wps = dict(wps)
                    new_wps["kalshi"] = round(home_prob, 4)
                    await session.execute(
                        update(Event)
                        .where(Event.id == eid)
                        .values(win_probability_sources=new_wps)
                    )
                stats["written"] += 1
                n += 1
                if not dry_run and n % _COMMIT_EVERY == 0:
                    await session.commit()
            except Exception as e:
                stats["errors"] += 1
                logger.warning("combat-wps blend failed for event %s: %s", eid, e)

        if not dry_run:
            await session.commit()

    logger.info("backfill_combat_wps: %s", stats)
    return stats
