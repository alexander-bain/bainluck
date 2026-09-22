"""Futures/Outrights API endpoints."""

import asyncio
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean, median
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, and_, or_, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Sport, Team
from app.services import get_db, OddsAPIService
from app.utils import movement_pool, probability_to_american
from app.utils.durable_venue_receipt import log_durable_venue_serve
from app.utils.feed_market_quality import is_empty_book_midpoint
from app.utils.futures_history_basis import devigged_consensus_by_time
from app.utils.futures_market_snapshot import dated_movement_points
from app.utils.generic_market_history import captures_are_coarse
from app.utils.kalshi_empty_book import KALSHI_BOOKMAKER
from app.utils.futures_unsupported_price import (
    MIDPOINT_TRADE_SOURCES,
    WITHHELD_PRICE_FIELDS,
    field_names_two_favourites,
    market_is_proved_exclusive_field,
    midpoint_refuted_by_last_trade,
    needs_trade_disconfirmation,
    needs_trade_evidence,
    needs_unbacked_ask_evidence,
    price_is_an_unbacked_ask,
    price_is_unlocated_in_broken_field,
    price_is_unsupported,
    price_refuted_by_live_book,
    row_carries_a_verdict,
    snapshot_price_is_unsupported,
)
from app.utils.game_market_club_names import repair_field_outcome_name
from app.utils.hook_staleness import hook_names_unpriced_outcome, is_hook_stale
from app.utils.leader_order import leader_first_outcomes
from app.utils.market_display_name import clean_market_display_name
from app.utils.event_rails import live_scheduled_settled_order
from app.utils.event_twin_fold import fold_twin_events
from app.utils.lifecycle import served_event_status
from app.utils.settlement_stamp import (
    last_charted_timestamp as _last_charted_timestamp,
    settled_point_timestamp,
)
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX, sport_display_name
from app.utils.tournament_stages import (
    get_stages_for_sport,
    classify_market_stage,
    get_datagolf_prefix,
    extract_tournament_name,
    tournament_names_match,
    is_game_level_market,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Kalshi ticker suffix extraction for sibling market discovery.
# Kalshi golf tickers: KX{TYPE}-{SUFFIX} where SUFFIX = tournament abbreviation + year
# e.g., KXPGATOP10-ARPIPBM26 → suffix "ARPIPBM26"
_KALSHI_TICKER_RE = re.compile(r"^[A-Z0-9]+-([A-Z0-9]{4,})$", re.IGNORECASE)

# The participant-name normalizer moved to `app.utils.golf_card_snapshot` in
# UX-P271, because the card receipt is computed over the keys it produces and a
# receipt whose normalizer could drift from this endpoint's would name a map this
# endpoint cannot apply. Imported under its original private name so every existing
# caller, patch target and test reference keeps resolving.
from app.utils.golf_card_snapshot import (  # noqa: E402
    progression_name_key as _progression_name_key,
)


def _extract_kalshi_suffix(external_id: str) -> Optional[str]:
    """Extract the tournament suffix from a Kalshi external_id.

    Returns None if the external_id doesn't match Kalshi ticker format.
    """
    if not external_id:
        return None
    m = _KALSHI_TICKER_RE.match(external_id)
    return m.group(1) if m else None


def _detect_elimination(history, threshold=0.005):
    """Detect if a participant has been eliminated from a tournament."""
    if len(history) < 3:
        return {"eliminated": False, "eliminated_at": None}
    tail = history[-3:]
    if all((p.get("probability") or 0) <= threshold for p in tail):
        for i, point in enumerate(history):
            if (point.get("probability") or 0) <= threshold:
                remaining = history[i:]
                if all((p.get("probability") or 0) <= threshold for p in remaining):
                    return {"eliminated": True, "eliminated_at": point["timestamp"]}
        return {"eliminated": True, "eliminated_at": tail[0]["timestamp"]}
    return {"eliminated": False, "eliminated_at": None}


def _norm_outcome_name(s) -> str:
    """Case/space-insensitive outcome-name key for champion-by-name matching."""
    return (s or "").strip().casefold()


def _apply_settled_winner_freeze(
    market, outcome_history, outcome_names, outcome_id_filter=None, champion_name=None
):
    """Settled-means-settled evolution freeze (#1177, Queue #230/#232).

    When a market has a graded champion, that champion's path-to-resolution line
    MUST end at 1.0 at settlement time, regardless of which source's snapshots we
    happened to chart.

    "A champion" is ONE outcome with ``is_winner=True`` on a mutually-exclusive
    field, and EVERY graded winner on an independent one (#7921) — a cumulative
    ladder settles several rungs YES and a golf cut settles dozens, and each of
    those is a completed journey that must end at its win. The mutex case with
    two winners remains a no-op; see ``_co_winners_are_legitimate``. odds_api can fizzle to a longshot value on a settled field (Spain
    0.587 on the World Cup, Ryan Fox on the Open) while Kalshi resolves to ~1.0;
    #225 Item 3 already forces the winner's OUTCOME into the chart, but its LINE
    still ends wherever the charted source left it. This resolves the ending.

    Source-independent by design: it keys on the graded ``is_winner`` flag, NOT
    on the winner market's ``status`` (Kalshi settled winner markets stay
    ``status='open'`` — gotcha #33 — so status is unreliable) and NOT on which
    source is snapshot-richest. That means it also fires while the winner market
    is stuck open (the THOC26 class), as soon as the grade lands.

    ``champion_name`` extends this to the odds_api winner-field class (#1177/#1196,
    Queue #232): odds_api winner-field outcomes NEVER carry ``is_winner`` (the
    field just fizzles — Spain 0.618 on WC-2026), so the ``is_winner`` path can't
    fire. When no outcome is graded, the caller supplies the concept's
    AUTHORITATIVE structural crown (``_apply_settled_crown`` — the sole bracket
    survivor, not a raw price) and we resolve that champion's line by OUTCOME
    NAME. We only accept an UNGRADED market here (``winners == []``); a graded
    ``is_winner`` always takes precedence and a name arg is ignored.

    Read-side only (gotcha #21): appends/synthesizes a terminal CHART point;
    never writes snapshots or ``is_winner``. The terminal point carries
    settlement-time semantics (gotcha #22 spirit — the completed journey ends at
    the finish, not fabricated mid-event movement), and is never placed before
    the champion's own last real data point. Non-champion lines are left to
    terminate at their own last real value.

    ⭐ #6360 — WHERE THAT TIMESTAMP COMES FROM IS ITS OWN DECISION, AND IT USED
    TO END AT THE CLOCK. ``resolution_date`` is a SCHEDULE, and on Kalshi it is
    routinely in the FUTURE for a market that has already settled (gotcha #14),
    so ``min(resolution_date, now)`` returned ``now`` and the champion's point
    was stamped with the moment of the request — a dot that moves every time the
    page is opened, measured twice 28 s apart on `/api/futures/58675941/history`.
    ``app/utils/settlement_stamp.py`` holds the ladder that replaces it, the
    populations (8,773 markets on the clock arm, 593,549 unchanged) and the
    measurement that keeps ``settled_at`` OUT of first place.
    """
    winners = [o for o in (market.outcomes or []) if getattr(o, "is_winner", False)]
    champs = []
    # Synthesizing a line the chart did not draw is a SINGLE-champion affordance:
    # a market's one champion must be visible even with no snapshots. It is not
    # extended to co-winners — see `_co_winners_are_legitimate`.
    allow_synthesis = True
    if len(winners) == 1:
        champs = [winners[0]]  # a graded grade always wins
    elif len(winners) >= 2:
        # #7921 — CO-WINNERS ARE THE NORM, NOT AN AMBIGUITY, ON AN INDEPENDENT
        # FIELD. 73 golfers make the cut; `>= 75 wins` and `>= 80 wins` both
        # settle YES on one cumulative ladder. This used to be a blanket no-op
        # ("co-winners fall through"), which left EVERY graded winner on 119,870
        # markets ending at a stale mid-price — 8,162 of them below 50% — while
        # the same page's own table already printed "Won · Settled" beside it.
        # The chart contradicted the verdict its own page had published.
        #
        # 🔴 The discriminator is NOT new and is NOT derived here: it is the
        # stored `futures_markets.mutually_exclusive` column that
        # `repair_kalshi_fabricated_loss` and `backfill_winners` already use for
        # exactly this question (two YES legs on a mutex field is a genuine
        # contradiction; on an independent field it is the answer). Deriving a
        # second opinion from names or outcome counts here is how the two halves
        # drift into disagreeing about the same market.
        if _co_winners_are_legitimate(market):
            champs = winners
            allow_synthesis = False
        # A mutex field with two winners is a CONTRADICTION, not a settlement:
        # it stays a no-op, because fabricating a terminal 1.0 on both legs would
        # publish the contradiction as truth. That population (1,404 markets) is
        # the fabricated-loss repair's, not this read path's.
    elif not winners and champion_name:
        norm = _norm_outcome_name(champion_name)
        named = [o for o in (market.outcomes or []) if _norm_outcome_name(getattr(o, "name", "")) == norm]
        if len(named) == 1:
            champs = [named[0]]
    if not champs:
        return  # nothing unambiguously graded to freeze
    # When the caller filtered to a single outcome, do not inject any OTHER
    # outcome's line into a view that didn't ask for it.
    if outcome_id_filter is not None:
        champs = [c for c in champs if c.id == outcome_id_filter]
        if not champs:
            return

    now = datetime.now(timezone.utc)
    # #6360: the last REAL point anywhere on this chart — the second witness in
    # the ladder, read before the champion's own entry is touched so the
    # synthesized point can never be its own evidence.
    settle_ts, _settle_basis = settled_point_timestamp(
        resolution_date=getattr(market, "resolution_date", None),
        last_observed=_last_charted_timestamp(outcome_history),
        settled_at=getattr(market, "settled_at", None),
        now=now,
    )

    for champ in champs:
        _freeze_one_winner_line(
            champ,
            outcome_history,
            outcome_names,
            settle_ts,
            allow_synthesis=allow_synthesis,
        )


def _co_winners_are_legitimate(market) -> bool:
    """Is a field where SEVERAL outcomes may truthfully be graded winners?

    #7921. Strict ``is False`` on purpose — this FAILS CLOSED. A missing
    attribute, ``None`` (never measured), or a test double that auto-creates a
    truthy attribute all read as "we do not know", and an unknown field is
    treated as mutually exclusive so the freeze stays a no-op. The cost of
    failing open is publishing a grading contradiction as a settled result on a
    chart, which is exactly what the single-champion gate existed to prevent.
    """
    return getattr(market, "mutually_exclusive", None) is False


def _freeze_one_winner_line(
    champ, outcome_history, outcome_names, settle_ts, *, allow_synthesis: bool
):
    """End ONE graded winner's charted line at 1.0. See the caller's docstring."""
    entry = outcome_history.get(champ.id)
    if entry and entry.get("history"):
        last = entry["history"][-1]
        last_ts = None
        try:
            last_ts = datetime.fromisoformat(str(last.get("timestamp")))
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
        except Exception:
            last_ts = None
        last_prob = last.get("probability")
        # Already resolved (the charted source converged to ~1.0) — the line
        # already ends at the win; nothing to add, just clear any spurious
        # elimination flag a fizzle-then-recover pattern may have set.
        if last_prob is not None and last_prob >= 0.999:
            entry["eliminated"] = False
            entry["eliminated_at"] = None
            return
        term_ts = settle_ts
        if last_ts is not None and term_ts <= last_ts:
            term_ts = last_ts + timedelta(seconds=1)
        entry["history"].append(
            {
                "timestamp": term_ts.isoformat(),
                "probability": 1.0,
                "american_odds": None,
                "bookmaker": "settlement",
            }
        )
        entry["eliminated"] = False
        entry["eliminated_at"] = None
    elif allow_synthesis:
        # Champion carried no charted snapshots at all — synthesize a minimal
        # terminal resolve point so the winner line exists and resolves.
        outcome_history[champ.id] = {
            "outcome_id": champ.id,
            "name": outcome_names.get(champ.id, getattr(champ, "name", None) or "Unknown"),
            "history": [
                {
                    "timestamp": settle_ts.isoformat(),
                    "probability": 1.0,
                    "american_odds": None,
                    "bookmaker": "settlement",
                }
            ],
            "eliminated": False,
            "eliminated_at": None,
        }


def _detect_round_boundaries_from_eliminations(outcome_histories, existing_boundaries):
    """Detect round boundaries from simultaneous elimination patterns."""
    if existing_boundaries:
        return existing_boundaries
    elimination_times = []
    for info in outcome_histories.values():
        elim = info.get("eliminated_at")
        if elim:
            try:
                ts = datetime.fromisoformat(elim.replace("Z", "+00:00")).timestamp()
                elimination_times.append(ts)
            except (ValueError, AttributeError):
                continue
    if len(elimination_times) < 2:
        return None
    elimination_times.sort()
    clusters = []
    current_cluster = [elimination_times[0]]
    for ts_val in elimination_times[1:]:
        if ts_val - current_cluster[-1] < 24 * 3600:
            current_cluster.append(ts_val)
        else:
            clusters.append(current_cluster)
            current_cluster = [ts_val]
    clusters.append(current_cluster)
    boundaries = []
    for i, cluster in enumerate(clusters):
        if len(cluster) >= 2:
            avg_ts = sum(cluster) / len(cluster)
            boundaries.append({
                "timestamp": datetime.fromtimestamp(avg_ts, tz=timezone.utc).isoformat(),
                "label": "Round " + str(i + 1),
            })
    return boundaries if boundaries else None

def _derive_round_boundaries(metadata: dict | None) -> list[dict] | None:
    """Extract round boundary markers from FuturesMarket.market_metadata.round_history.

    Returns a list of {timestamp, label} dicts suitable for chart ReferenceLine markers,
    or None if no round history exists.
    """
    if not metadata:
        return None
    round_history = metadata.get("round_history")
    if not round_history:
        return None
    return [
        {"timestamp": entry["timestamp"], "label": entry.get("label", f"R{entry.get('round', '?')}")}
        for entry in round_history
        if "timestamp" in entry
    ]


# NOTE: Specific routes MUST come before /{market_id} to avoid being matched as IDs


@router.get("/debug/sources")
async def debug_futures_sources(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to see futures counts by source and status."""
    # Count by source and status
    query = select(
        FuturesMarket.source,
        FuturesMarket.status,
        func.count(FuturesMarket.id).label("count")
    ).group_by(FuturesMarket.source, FuturesMarket.status)

    result = await db.execute(query)
    rows = result.all()

    breakdown = {}
    for row in rows:
        source = row.source or "unknown"
        if source not in breakdown:
            breakdown[source] = {"total": 0, "by_status": {}}
        breakdown[source]["by_status"][row.status] = row.count
        breakdown[source]["total"] += row.count

    # Get sample markets from each source
    samples = {}
    for source in breakdown.keys():
        sample_query = (
            select(FuturesMarket.id, FuturesMarket.name, FuturesMarket.status, FuturesMarket.updated_at)
            .where(FuturesMarket.source == source)
            .order_by(FuturesMarket.updated_at.desc())
            .limit(3)
        )
        sample_result = await db.execute(sample_query)
        samples[source] = [
            {"id": r.id, "name": r.name, "status": r.status, "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in sample_result.all()
        ]

    return {
        "breakdown": breakdown,
        "samples": samples,
    }


@router.get("/debug/sport-mapping")
async def debug_sport_mapping(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to see how futures markets are linked to sports."""
    # Get all sports
    sports_result = await db.execute(
        select(Sport.id, Sport.key, Sport.name).order_by(Sport.key)
    )
    sports = [{"id": r.id, "key": r.key, "name": r.name} for r in sports_result.all()]
    sport_map = {s["key"]: s["id"] for s in sports}

    # Get all futures markets with their sport links
    markets_result = await db.execute(
        select(
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.external_id,
            FuturesMarket.sport_id,
            Sport.key.label("sport_key"),
            Sport.name.label("sport_name"),
        )
        .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
        .order_by(FuturesMarket.external_id)
    )
    # Import here to avoid circular import issues
    from app.tasks import _infer_base_sport

    markets = []
    for r in markets_result.all():
        # Compute what _infer_base_sport would return
        inferred_key = _infer_base_sport(r.external_id) if r.external_id else None
        markets.append({
            "id": r.id,
            "name": r.name,
            "external_id": r.external_id,
            "sport_id": r.sport_id,
            "linked_sport_key": r.sport_key,
            "linked_sport_name": r.sport_name,
            "inferred_base_sport": inferred_key,
            "inferred_sport_id": sport_map.get(inferred_key) if inferred_key else None,
            "linking_works": r.sport_id is not None and r.sport_id == sport_map.get(inferred_key),
        })

    # Summary: count linked vs unlinked
    linked = sum(1 for m in markets if m["sport_id"])
    unlinked = sum(1 for m in markets if not m["sport_id"])

    return {
        "summary": {
            "total_sports": len(sports),
            "total_futures_markets": len(markets),
            "linked_markets": linked,
            "unlinked_markets": unlinked,
        },
        "sports": sports,
        "markets": markets,
    }


@router.get("/available")
async def get_available_futures():
    """
    Get list of sports with futures markets available from The Odds API.

    Useful for discovering what futures can be tracked.
    """
    try:
        service = OddsAPIService()
        sports = await service.get_sports_with_outrights()
        await service.close()

        return {
            "sports": [
                {
                    "key": s["key"],
                    "group": s.get("group"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                }
                for s in sports
            ],
            "count": len(sports),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching from Odds API: {str(e)}")


# ── /movers: why "Biggest Movers" cost 11 s of database time to produce ten
# ── rows, and the bound that removes it. LAT-P108.
#
# The old query was `futures_outcomes JOIN futures_markets ... ORDER BY
# abs(probability_change_24h) DESC LIMIT n`. `abs()` is not indexed, so Postgres
# parallel-seq-scanned 1.95 M outcome rows, hash-joined 124 k survivors and
# sorted all of them to emit ten. Measured on production 2026-08-28:
# 11,129 ms execution, 9,799 ms of it in the seq scan alone.
#
# THE BOUND. `futures_markets.max_movement_24h` is, by the definition of the
# task that writes it (`app.tasks.update_max_movement`, every 10 min),
# `MAX(ABS(outcome.probability_change_24h))` for that market. So an outcome whose
# |change| beats the smallest max_movement in the pool must live in a market
# already inside the pool: the pool is a provable SUPERSET of the answer, not a
# sample of it. `routes/feed.py` and `routes/admin_judgments.py` already read the
# column this way; this is the third consumer, not a new idea.
#
# Verified on production 2026-08-28, not asserted — one atomic statement per
# probe so the two arms see the same snapshot: limit 10 / pool 400 and limit 20 /
# pool 800 both return the IDENTICAL id list AND value vector as the unbounded
# scan. At limit 100 / pool 1500 the value vector is still identical and the ids
# differ inside a tie group, which the legacy query never determined either — its
# `ORDER BY abs(...) DESC` carries no tie-break and hundreds of outcomes sit on
# the same value.
#
# 🔴 WHAT THIS DELIBERATELY DOES **NOT** FIX, because doing it here would be
# wrong: three of the ten rows this endpoint served on 2026-08-28 were last
# written on 2026-07-24 — thirty-five days of "24-hour change". A read-side
# freshness filter on the outcome's own poll stamp looks like the fix and is NOT
# compatible with this bound: `max_movement_24h` is computed over ALL of a
# market's outcomes including stale ones, so ranking the pool by it while
# filtering the answer by freshness breaks the superset guarantee — measured, at
# limit 20 the two arms disagree on VALUES, not just on ties. The staleness is an
# upstream data bug (nothing ever clears `probability_change_24h` on a row that
# stops being written) and it is parked as one, with the evidence.
#
# ⚠️ That paragraph deliberately avoids writing the comparison out. #2024's
# census (`tests/test_futures_stamp_semantics.py`) greps `app/routes` for a
# literal stamp comparison, and an earlier draft of this COMMENT tripped it —
# a 14-minute suite spent on prose. Recorded rather than worked around silently.
#
# Reversible without a deploy: `FUTURES_MOVERS_POOLED=0` restores the legacy
# scan — which is also the ORACLE the equivalence gate drives both paths through.
_MOVERS_POOLED = os.getenv("FUTURES_MOVERS_POOLED", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

#: Statuses a market must be in to have a mover. Unchanged from the legacy query.
_MOVERS_OPEN_STATUSES = ("open", "active")

#: `limit` was unbounded. iOS asks for 10 and the default is 20; anything past
#: this is a caller sorting a 3.2 M-row table on our dime.
_MOVERS_MAX_LIMIT = 100

#: Pool size, in markets. The bound is sound at any size — 40x the ask and a
#: floor of 400 buy margin over the ~10-minute lag of `update_max_movement`, so
#: a market that leaps into contention between two runs of that task is still
#: very likely inside the pool. The ceiling is where the pool sort stops being
#: cheap (production: 200 -> 627 ms, 1000 -> 1,138 ms, 2500 -> 2,833 ms).
_MOVERS_POOL_PER_ITEM = 40
_MOVERS_POOL_MIN = 400
_MOVERS_POOL_MAX = 1500


def _clamp_movers_limit(limit: int) -> int:
    """Clamp rather than 422 — a shipped iOS build must not start erroring."""
    return max(1, min(int(limit), _MOVERS_MAX_LIMIT))


def _movers_market_pool_size(limit: int) -> int:
    return max(_MOVERS_POOL_MIN, min(_MOVERS_POOL_MAX, limit * _MOVERS_POOL_PER_ITEM))


def _build_movers_query(limit: int, *, pooled: bool):
    """Build the `/futures/movers` query.

    `pooled=False` is the legacy full-scan arm, kept as rollback and as the
    equivalence oracle the gate drives both paths through.
    """
    conditions = [FuturesOutcome.probability_change_24h.isnot(None)]

    if pooled:
        # LAT-P151: the pool SHAPE moved to `app/utils/movement_pool.py` so the
        # second consumer of this bound (search-suggestions section 3) reads the
        # same claim about `max_movement_24h` rather than re-spelling it. The
        # SIZE stays here — it scales with this route's caller-supplied `limit`,
        # which is a decision the other consumer does not have. Nothing about
        # the emitted SQL changes; `test_pooled_sql_bounds_the_market_scan` and
        # the equivalence gate below it are the pins.
        market_pool = movement_pool.market_pool_subquery(
            pool_size=_movers_market_pool_size(limit),
            statuses=_MOVERS_OPEN_STATUSES,
        )
        # `market_id IN pool` carries the status filter — the pool is already
        # restricted to open/active — so the join is not re-stated here.
        query = (
            select(FuturesOutcome)
            .options(joinedload(FuturesOutcome.market))
            .where(*conditions, FuturesOutcome.market_id.in_(market_pool))
        )
    else:
        query = (
            select(FuturesOutcome)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .options(joinedload(FuturesOutcome.market))
            .where(*conditions, FuturesMarket.status.in_(_MOVERS_OPEN_STATUSES))
        )

    return query.order_by(
        func.abs(FuturesOutcome.probability_change_24h).desc()
    ).limit(limit)


#: The route's own write-through TTL, unchanged from LAT-P108. A reader that
#: cold-builds keeps the answer for a minute; the WARMER (below) writes a longer
#: one, and the two are deliberately different numbers — see
#: `app/tasks/futures_movers_warm.py` for why a reader's TTL and a producer's
#: are not the same question.
MOVERS_ROUTE_TTL_SECONDS = 60


def movers_cache_key(hours: int, limit: int) -> str:
    """The Redis key for one `(hours, limit)` shape. ONE minter, one format.

    LAT-P115. The warmer writes the key the route reads, so the format cannot
    live in two places: a producer that mints `movers:24:10` while the consumer
    reads `movers:24:0010` warms nothing and reports success — gotcha #53's
    shape, and the reason `hub_cache_keys` / `league_cache_keys` exist next door
    rather than being re-spelled inside their refresh tasks.

    `limit` is clamped by the CALLER before it reaches here, so this function is
    a pure format and the clamp has exactly one home (`_clamp_movers_limit`).
    """
    return f"bainluck:movers:{hours}:{limit}"


async def build_and_cache_movers(
    hours: int,
    limit: int,
    db: AsyncSession,
    redis=None,
    *,
    ttl: int = MOVERS_ROUTE_TTL_SECONDS,
) -> dict:
    """Build one movers payload and write it to its cache key. Never raises on Redis.

    LAT-P115 extracted this from the route body so that `update_max_movement` —
    the 10-minute task that WRITES the very column this answer is ranked by — can
    publish the answer instead of leaving every reader to derive it.

    🔴 THE EXTRACTION IS THE POINT, not a tidy-up. The alternative was a warmer
    that re-implements the payload, and a warmed payload that differs from the
    served one by a single key is worse than no warmer at all: it is a wrong
    answer served fast, to the only client that exists, with the cache hiding it.
    `timeframe_hours` alone is strip-unsafe in shipped iOS (see below) — a second
    copy of this dict is one refactor away from omitting it and crashing every
    build in the wild.

    The route passes no `ttl` and therefore keeps LAT-P108's 60 s exactly.
    """
    import json as _json

    query = _build_movers_query(limit, pooled=_MOVERS_POOLED)

    result = await db.execute(query)
    outcomes = result.unique().scalars().all()

    response = _movers_payload(outcomes, hours)

    if redis is not None:
        try:
            redis.setex(
                movers_cache_key(hours, limit),
                ttl,
                _json.dumps(response, default=str),
            )
        except Exception:
            pass

    return response


def _movers_payload(outcomes, hours: int) -> dict:
    """Shape the response. The ONLY place this dict is spelled."""
    return {
        "movers": [
            {
                "outcome_id": o.id,
                "name": o.name,
                "market_id": o.market_id,
                "market_name": o.market.name if o.market else None,
                "current_probability": float(o.current_probability) if o.current_probability is not None else None,
                "probability_change_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
                # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
                # Deliberately present and deliberately unrendered. The standing
                # no-price-format ruling bans odds SOLD AS A FEATURE, not odds NAMED
                # as the thing we refuse to show — so this is a judgment call, not a
                # mechanical strip. It costs one integer and preserves the ability to
                # say "-150 means 60%" at the boundary; stripping it forecloses that
                # framing, and re-deriving it later means re-plumbing a producer
                # through two typed clients. Revisit only WITH the ruling.
                "current_american_odds": o.current_american_odds,
                "rank": o.rank,
                "rank_change_24h": o.rank_change_24h,
            }
            for o in outcomes
            if not _GARBAGE_OUTCOME_RE.match(o.name or "")
        ],
        # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
        # Request-echo: the window actually applied, which is not always the window
        # asked for. A caller that cannot see this cannot tell a clamped or normalised
        # response from the one it requested.
        # ⚠️ STRIP-UNSAFE: `timeframeHours` is a NON-OPTIONAL `Int` in shipped iOS
        # (Models/SearchModels.swift:146). Removing it throws on decode for every build
        # already in the wild — a crash, not a cleanup. The App Store does not redeploy
        # atomically with the backend.
        "timeframe_hours": hours,
    }


@router.get("/movers")
async def get_futures_movers(
    hours: int = Query(24, description="Timeframe for movement calculation"),
    limit: int = Query(20, description="Number of movers to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get outcomes with biggest probability changes.

    Useful for discovering betting line movement and market sentiment shifts.
    """
    import json as _json
    from app.tasks.redis_state import get_redis_client

    # Clamped BEFORE the cache key so an unbounded `limit` can neither sort the
    # whole outcome table nor mint an unbounded number of Redis keys.
    limit = _clamp_movers_limit(limit)

    redis = None
    try:
        redis = get_redis_client()
        cached = redis.get(movers_cache_key(hours, limit))
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    # `redis` stays None if the client could not be built, and
    # `build_and_cache_movers` then skips the write rather than raising a
    # NameError into its own bare `except` — which is what the inlined version
    # did, silently, on every Redis outage.
    return await build_and_cache_movers(hours, limit, db, redis)


@router.get("/live/{sport_key}")
async def get_live_futures(
    sport_key: str,
):
    """
    Fetch live futures odds directly from The Odds API.

    Bypasses the database for real-time data. Useful for debugging
    or when you need the absolute latest odds.
    """
    try:
        service = OddsAPIService()
        api_response = await service.get_futures_odds(sport_key)
        markets = service._parse_futures(api_response, sport_key)
        await service.close()

        return {
            "sport_key": sport_key,
            "markets": [
                {
                    "bookmaker": m.bookmaker,
                    "market_name": m.market_name,
                    "outcomes": [
                        {
                            "name": o.name,
                            "american_odds": o.american_odds,
                            "probability": round(o.probability, 4),
                        }
                        for o in sorted(m.outcomes, key=lambda x: x.probability, reverse=True)
                    ],
                }
                for m in markets
            ],
            "bookmaker_count": len(markets),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching from Odds API: {str(e)}")


@router.get("/canonical-keys")
async def list_canonical_keys(
    sport: Optional[str] = Query(None, description="Filter by sport category"),
    has_multiple_sources: bool = Query(False, description="Only show keys with 2+ sources"),
    limit: int = Query(50, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """
    List distinct canonical market keys across all futures markets.

    Useful for discovering which markets have cross-source coverage.
    """
    query = (
        select(
            FuturesMarket.canonical_market_key,
            func.count(FuturesMarket.id).label("market_count"),
            func.count(func.distinct(FuturesMarket.source)).label("source_count"),
            func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
        )
        .where(FuturesMarket.canonical_market_key.isnot(None))
        .group_by(FuturesMarket.canonical_market_key)
        .order_by(func.count(func.distinct(FuturesMarket.source)).desc())
    )

    if sport:
        query = query.where(FuturesMarket.llm_sport_category == sport)

    if has_multiple_sources:
        query = query.having(func.count(func.distinct(FuturesMarket.source)) > 1)

    query = query.limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return {
        "keys": [
            {
                "canonical_key": row.canonical_market_key,
                "market_count": row.market_count,
                "source_count": row.source_count,
                "sources": sorted(row.sources) if row.sources else [],
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.get("/browse")
async def browse_futures(
    category: Optional[str] = Query(None, description="Filter by llm_sport_category"),
    q: Optional[str] = Query(None, description="Search within market names"),
    limit: int = Query(50, description="Results per page", ge=1, le=200),
    offset: int = Query(0, description="Pagination offset", ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Paginated category browsing for the Search tab.

    Returns markets with their top 3 outcomes, total count, and pagination info.
    Designed for lazy-loading: only fetches data when a user clicks into a category.
    """
    base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= datetime.now(timezone.utc),
        ),
        ~FuturesMarket.name.ilike('% vs %'),
        ~FuturesMarket.name.ilike('% vs. %'),
    ]

    if category:
        # #4047: the panel behind a category tile must contain what the tile
        # counted. The census counts unclassified markets under `other`, so this
        # has to as well, or the tile says 215 and the panel shows 206.
        base_filters.append(_category_condition(category))

    if q:
        base_filters.append(FuturesMarket.name.ilike(f"%{q}%"))

    # ONE scan, not two. `total` used to be a separate COUNT over `base_filters`
    # — and the page query below scans exactly the same rows, because
    # `ORDER BY resolution_date` has to see all of them before it can take a
    # page. Measured on production 2026-08-29: `category=politics` was 8,410
    # shared blocks twice, and the uncategorised call 38,990 blocks twice
    # (~305 MB, the negated ILIKEs are unindexable — ruling 080 / P122-4).
    # `count(*) OVER ()` rides the scan the sort already pays for: the plan
    # gains a WindowAgg above the same Bitmap Heap Scan and the second scan
    # disappears. The window is evaluated before LIMIT/OFFSET, so `total` is
    # the EXACT same integer the COUNT returned — this is a cost change, not
    # a precision change. The counts are printed to the user ("(6,611)",
    # "Load more (N remaining)"), so an approximation would have been a
    # formatting lie shipped as a latency win.
    query = (
        select(FuturesMarket, func.count().over().label("browse_total"))
        .options(selectinload(FuturesMarket.outcomes))
        .where(*base_filters)
        # `resolution_date` alone is NOT a page-able order: it is massively
        # non-unique (golf's 88 open markets hold a 26-row tie and a 20-row tie;
        # economics resolves ~1,500 daily markets at the same 20:00Z instant).
        # A tie block is ordered arbitrarily, and Postgres is free to resolve it
        # DIFFERENTLY for each `OFFSET+LIMIT` because a top-N sort only has to
        # produce the first `offset+limit` rows — so the same row can land on
        # page 2 and again on page 4, and whichever row it displaced is never
        # served at all. Measured on production 2026-09-18 at the reader's own
        # `limit=20`: a reader who clicks "Load more" until it stops sees 88
        # golf slots holding 79 distinct markets — 9 of 88 are unreachable by
        # ANY sequence of clicks. `motorsports` is the control that names the
        # mechanism rather than correlating with it: its biggest tie block is 11
        # rows, under the page size, and it loses nothing.
        # The fix is a total order, which is the idiom this file already uses
        # for group members (`group_position.nulls_last(), FuturesMarket.id`).
        # `id` is the PK, so the sort is now unique and OFFSET paging is
        # consistent; it costs one extra comparison on ties in a sort node the
        # query already pays for, and adds no index requirement.
        .order_by(FuturesMarket.resolution_date.asc().nulls_last(), FuturesMarket.id.asc())
        .limit(limit)
        .offset(offset)
    )
    # `list()` and not a bare Result: an empty page must be falsy here, and it
    # is the empty page that decides whether the fallback below runs.
    rows = list((await db.execute(query)).unique().all())
    markets = [row[0] for row in rows]

    if rows:
        total = int(rows[0][1])
    elif offset:
        # No rows AND a non-zero offset: the window function never ran, so it
        # cannot tell us the size of the population. That is the one case the
        # single scan does not answer, so pay for the COUNT here — off the hot
        # path, because `has_more` stops the UI from ever asking for a page
        # past the end. Reporting 0 instead would tell a reader who hand-typed
        # an offset that the category is empty.
        count_query = select(func.count(FuturesMarket.id)).where(*base_filters)
        total = (await db.execute(count_query)).scalar() or 0
    else:
        # Offset 0 and no rows: the population really is empty. No query needed.
        total = 0

    # UX-P165: browse was the FOURTH divergent copy of the display rules — the one
    # #993's docstring warns about. It filtered only the legacy `player AB` regex
    # and then sorted RAW, so an unrankable row could hold position 0. That matters
    # more here than anywhere else: `CompactMarketCard` renders `top_outcomes[0]`
    # and NOTHING else, so the artifact is not a wasted row inside a list — it is
    # the market's entire one-line description on the /search category browser.
    #
    # Measured on the deployed build 2026-08-29 over ALL 21,441 browse markets
    # (100% sweep, not a sample): 686 cards led with an unrankable outcome — 181 a
    # dominant field row ("FedEx Cup Playoffs: Winner -> Other 100%") and 505 an
    # anonymized reserved slot ("Massachusetts Governor Republican Primary Winner
    # -> Candidate Z 100%"). A further 9 led with a sub-threshold field outcome
    # ("Fed decisions (Jun-Sep) -> Other 51%", a 9-way market). 695 total, 3.24%.
    #
    # Same three primitives, same order, as `_format_market_detail` (UX-P164) so
    # the click-through from a browse card to the market page cannot disagree with
    # the card that produced it.
    #
    # ONE deliberate difference from detail, and it is a scope decision, not an
    # omission: `normalize_display_probs` is NOT applied. Browse has no
    # mutual-exclusivity-safe basis to normalize on at the top-3 slice, and the
    # #199/#1200/#1201 guards exist precisely because squeezing the wrong family
    # (golf make-cut, threshold ladders, independent binaries) is worse than
    # leaving raw prices alone. Browse serves raw prices today and still does;
    # 386 markets whose whole field is visible in the top 3 sum >1.02 and are left
    # exactly as they were. Measured and parked, not silently changed.
    #
    # Because nothing is normalized here, the raw probability IS the rendered
    # number — so `_FIELD_DOMINANT_MIN`'s documented rule ("judge the number
    # RENDERED") is satisfied by judging the raw price. That is the placement
    # answer for this, the fourth caller: feed drops BEFORE its scale, detail and
    # search drop AFTER normalization, and browse has no basis step to sit either
    # side of.
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs
    from app.utils.outcome_display import (
        drop_dominant_field_outcomes,
        drop_incoherent_near_certain,
        drop_unbacked_legs,
        is_placeholder_outcome_name,
        leader_pick_order,
    )

    items = []
    for market in markets:
        # Q480: one condition, one outcome — drop a `_yes`/`_no` leg that duplicates
        # a bare rung this same market already holds. See the module docstring; the
        # legs carry the sub-market's price, so a 64.5% "No" outranks every real
        # answer and becomes the browse card's subtitle. FIRST, so the placeholder
        # filter's `or list(market.outcomes)` fallback can never resurrect one.
        deduped = drop_duplicate_legs(market.outcomes, lambda o: o.external_id)
        # #6524: a leg with no venue id is not a quote. Browse needs this MORE than
        # the other two surfaces, not less: market 3821229 (*GPT-5.5 released by…?*)
        # carries its unbacked leg at **rank 1**, so the frozen `April 8 1.0` is
        # exactly what a browse card prints as its subtitle. BEFORE the sort and the
        # `[:3]` slice for the reason the sibling's docstring gives.
        deduped = drop_unbacked_legs(
            deduped,
            lambda o: o.external_id,
            market_is_open=getattr(market, "status", None) == "open",
            is_winner_of=lambda o: bool(o.is_winner),
        )
        # NEVER EMPTIES, matching `display_rank_order`/`drop_dominant_field_outcomes`:
        # a market whose every outcome is a placeholder keeps its rows rather than
        # rendering a card with no subtitle at all.
        real_outcomes = [
            o for o in deduped
            if not is_placeholder_outcome_name(o.name)
        ] or list(deduped)
        # #6993, THE THIRD AND WORST SITE OF THE SAME BYPASS. `/api/futures/109485`
        # served `24,800 or below 1.0` as `top_outcomes[0]` here while
        # `/api/futures/109485` (detail) served `probability: null` for that exact
        # outcome id in the same minute. `CompactMarketCard` renders
        # `top_outcomes[0]` AND NOTHING ELSE — the comment at the top of this block
        # says so — so on this route the refused number was not one row in a table
        # and not one rung in a ladder: it was the market's entire one-line
        # description on the /search category browser, printed as 100%.
        #
        # Cost, measured on production 2026-09-18 over the first 200-market browse
        # page with the filters and ordering above: 16 of 200 markets hold a leg
        # that reaches a candidate screen at all (an upper bound — the real screens
        # are narrower than the bid/ask shape counted), so 184 pay no query. The
        # reader's own page size is 20.
        withheld = await _withheld_price_outcome_ids(db, market)
        # Sort on the SERVED value, matching `get_group`. Ordering by the raw
        # column is what put a withheld stored 1.0 at rank 1 in the first place,
        # and rank 1 is the only rank this payload's consumer renders.
        sorted_outcomes = sorted(
            real_outcomes,
            key=lambda o: 0 if o.id in withheld
            else (float(o.current_probability) if o.current_probability else 0),
            reverse=True,
        )
        # #4253: same drop as detail and search, and browse needs it for the same
        # reason it needs the one below — this list is about to be sliced to 3, and
        # frozen 1.0s sort to the very top. Browse has no normalization step at all
        # (see the placement note at the top of this block), so the raw price IS the
        # rendered price here and there is no ordering question to settle.
        #
        # Applied to the ORM rows rather than the dicts below because the browse
        # payload does not carry `is_winner`, and the crowned-leg exemption is not
        # optional — without it this deletes the result from a settled market.
        # #6081 CHANGED THE NINE SERVED SITES IN THIS FILE AND DELIBERATELY NOT
        # THIS ONE. Every other `float(...) if o.current_probability else None`
        # built a value a client renders, where a falsy 0 became a false "no
        # price". This one is an INPUT TO A PREDICATE: what
        # `drop_incoherent_near_certain` sees decides which rows it deletes, and
        # the comment four lines up says what is at stake when it deletes the
        # wrong one. Feeding it 0.0 where it has always seen None is a behaviour
        # change to the dropper, not a serialization fix, and it needs its own
        # argument and its own guard. Left as-is on purpose, not missed.
        sorted_outcomes = drop_incoherent_near_certain(
            sorted_outcomes,
            lambda o: float(o.current_probability) if o.current_probability else None,
            mutually_exclusive=getattr(market, "mutually_exclusive", True),
            market_is_open=getattr(market, "status", None) == "open",
            is_winner_of=lambda o: bool(o.is_winner),
        )
        # `drop_incoherent_near_certain` above is deliberately NOT told about the
        # withhold: its docstring states that judging the RAW price is the whole
        # point of it (the frozen 1.0s are why the rendered number is wrong), so
        # feeding it a refused-to-None leg would blind it to exactly the shape it
        # exists to find. The refusal applies from here down, where the number is
        # serialized — which is also where `_FIELD_DOMINANT_MIN`'s documented
        # "judge the number RENDERED" rule needs it, since the raw price is no
        # longer the rendered number once a leg is withheld.
        display_outcomes = []
        for o in sorted_outcomes:
            od = {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability is not None else None,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            if o.id in withheld:
                # Keyed on presence, as the detail and group arms are. `movement`
                # is in `WITHHELD_PRICE_FIELDS` because it is this payload's
                # spelling of `probability_change_24h` — a delta measured from the
                # number being refused.
                for field in WITHHELD_PRICE_FIELDS:
                    if field in od:
                        od[field] = None
            display_outcomes.append(od)
        # Drop BEFORE the `[:3]` slice, then leader-pick: demotion alone only keeps
        # a row out of a top-N slot while the list is LONGER than N (UX-P163), and
        # the mean browse market has 6.3 outcomes.
        display_outcomes = drop_dominant_field_outcomes(
            display_outcomes, lambda o: o.get("name"), lambda o: o.get("probability")
        )
        leader_pick_order(display_outcomes)
        top3 = display_outcomes[:3]
        items.append({
            "id": market.id,
            "name": market.name,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "top_outcomes": top3,
            "outcome_count": len(real_outcomes),
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/categories")
async def list_futures_categories(
    db: AsyncSession = Depends(get_db),
):
    """
    Category counts for the Search tab category grid.

    Returns `{categories: [{key, count}], total}` plus the cache envelope.

    🔴 THE DOCSTRING THAT USED TO BE HERE SAID "Lightweight ... Single GROUP BY
    query" AND IT WAS MEASURED AT 1,586 ms, EVERY TIME, FOR EVERY VISITOR.
    Single-statement is true; lightweight was a claim about a shape, not about a
    cost. The statement reads 39,014 shared blocks — the two negated `ILIKE`s
    are unindexable — and sorts 21,439 rows to group into 42. This tier had no
    cache at all, so the grid on `/search` cost that scan on every single load.

    The serve ladder is now: shared slot → its 24 h mirror (age-bounded, with one
    rebuild behind it) → build. Policy, and the numbers behind it, live in
    `app/utils/futures_categories_cache.py`.
    """
    from app.utils import futures_categories_cache as fcc
    from app.utils.event_concept_cache import serve_stale_and_refresh

    body, state = fcc.read()
    if state == "live" and body is not None:
        return body
    if state == "stale_ok" and body is not None:
        # Exactly one rebuild behind the mirror, fleet-wide: the lock is in Redis,
        # not in a process-global set, so `WEB_CONCURRENCY=2` x N dynos still
        # produces one build for one expiry.
        if serve_stale_and_refresh(fcc.keys(), _rebuild_futures_categories):
            return body
        # No running loop to refresh behind us — fall through and build, rather
        # than serve stale with nothing coming to replace it.

    return _publish_futures_categories(await _build_futures_categories(db))


#: 🔴 #4047. THE KEY AN UNCLASSIFIED MARKET IS SHOWN UNDER — and the point is that
#: it is ONE key, decided in ONE place, used by the census AND by every endpoint
#: that takes a `category` from it.
#:
#: Production served `[('other', 206), ('other', 9)]` on 2026-09-08: two tiles in
#: the `/search` grid, both reading "Other", with different counts. The census
#: grouped by `llm_sport_category` and then wrote `row.llm_sport_category or
#: "other"` — so `'other'` (we classified it as other) and `NULL` (we never
#: classified it) arrived as separate groups wearing one name, because the
#: rename happened AFTER the GROUP BY.
#:
#: It cost a reader more than a repeated tile. `CategoryBrowser` keys its grid on
#: `cat.key` and tracks expansion as `expandedCategory === cat.key`, so tapping
#: either tile highlighted BOTH and opened the same panel — and that panel asks
#: `/browse?category=other`, which matched `llm_sport_category == 'other'` and
#: therefore could never show the 9 rows behind the second tile.
_UNCLASSIFIED_CATEGORY = "other"


def _category_condition(category: str):
    """The filter for a category key the census can emit. #4047.

    ⚠️ WIDENED FOR EXACTLY ONE KEY, AND SPELLED AS A BRANCH RATHER THAN AS
    `coalesce(llm_sport_category, 'other') == category`. The uniform spelling is
    tidier and would put a function call on the left of every comparison — an
    unindexable expression on a route whose own comment records that the
    uncategorised call already reads 38,990 shared blocks (~305 MB). Every key
    but this one keeps its plain, sargable equality; only `other` pays for the
    OR, and only `other` needs it.
    """
    if category == _UNCLASSIFIED_CATEGORY:
        return or_(
            FuturesMarket.llm_sport_category == category,
            FuturesMarket.llm_sport_category.is_(None),
        )
    return FuturesMarket.llm_sport_category == category


async def _build_futures_categories(db: AsyncSession) -> dict:
    """Build the census from scratch. The pre-LAT-P122 route body, unchanged."""
    now = datetime.now(timezone.utc)

    # #4047: the fallback belongs in the GROUP BY, not in the serialiser. Grouped
    # on the raw column, `NULL` and `'other'` are two rows that the `or "other"`
    # below then gave one name to.
    category_key = func.coalesce(
        FuturesMarket.llm_sport_category, _UNCLASSIFIED_CATEGORY
    ).label("category_key")

    query = (
        select(
            category_key,
            func.count(FuturesMarket.id).label("count"),
        )
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
            ~FuturesMarket.name.ilike('% vs %'),
            ~FuturesMarket.name.ilike('% vs. %'),
        )
        .group_by(category_key)
        .order_by(func.count(FuturesMarket.id).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    categories = [
        {
            "key": row.category_key,
            "count": row.count,
        }
        for row in rows
    ]

    return {
        "categories": categories,
        "total": sum(r["count"] for r in categories),
    }


def _publish_futures_categories(response: dict) -> dict:
    """Stamp a fresh build, publish it, and return what the reader gets.

    Returns the ENVELOPED body — the same dict the next reader will get out of
    Redis plus one `availability`, so a build and a hit are the same bytes.
    """
    from app.utils import futures_categories_cache as fcc

    enveloped = fcc.stamp(response)
    fcc.write(enveloped)
    return fcc.with_availability(enveloped, fcc.AVAILABILITY_LIVE)


async def _rebuild_futures_categories() -> None:
    """Rebuild the census behind a stale serve.

    Opens its OWN session: the request's `AsyncSession` is not ours to hold past
    the response, and that is why `serve_stale_and_refresh` takes a zero-arg
    coroutine FUNCTION rather than a coroutine.
    """
    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        _publish_futures_categories(await _build_futures_categories(session))


#: A market that holds at least one `futures_outcomes` row (#6354).
#:
#: `/faceted` is the iPhone Browse tab's list — `FuturesListViewModel.load()` opens on
#: `?page=1&per_page=20&sort=soonest` — and it had no outcome gate, so a row we ingested
#: but never filled arrived as a name, a category chip and no number. Measured on
#: production 2026-09-15, the app's own query, three sorts x five screens:
#:
#:     soonest (THE DEFAULT)   44 / 100 answer-less   (page 1 alone: 12 of 20)
#:     newest                  10 / 100
#:     trending                 0 / 100
#:
#: 🔴 THE DEFAULT SORT IS THE ONLY ONE THAT SURFACES THEM, and `trending` is clean by
#: accident rather than by design: it orders on `max(abs(probability_change_24h))
#: … nulls_last()`, and a market with no outcome rows has no movement, so that sort
#: fences them out on its way past. `soonest` orders on `resolution_date asc`, which
#: carries no such property, and the soonest-resolving rows are exactly the churn that
#: never got outcomes. So the LIST is worse than the CORPUS — 25% of the scope is
#: answer-less, 44% of the first five screens is — and anyone re-measuring this on
#: `trending` will read a clean 0% and conclude there is nothing here.
#:
#: 🔴 IT ASKS FOR A *DRAWABLE* ROW, NOT MERELY A ROW. The formatter below counts outcomes
#: AFTER `_GARBAGE_OUTCOME_RE`, so a gate on bare row existence would let a market whose
#: every row is named `player AB` through and it would still serve `outcome_count: 0` —
#: the same blank card by a different road. Measured on this population, same filter, same
#: day, that residue is currently EMPTY:
#:
#:     in scope                                     24,888
#:     no outcome rows at all                        6,259  (841 of them tier 1-2)
#:     rows present but every one garbage-named          0
#:
#: An empty set is a reason to keep a gate honest, not a reason to leave a hole in it: the
#: predicate mirrors the formatter so the two agree BY CONSTRUCTION, and the contract a
#: guard asserts is the true one — every row this route serves has `outcome_count > 0`.
#:
#: The mirror is behavioural, not textual, and a real-Postgres test grades it by running
#: both engines over the same names. Two places they would otherwise diverge:
#:
#:   * `re.match` anchors only at the start, so `_GARBAGE_OUTCOME_RE`'s own trailing `$`
#:     is what makes it a full match; POSIX `~*` is unanchored and needs both anchors
#:     written out.
#:   * **A NULL name is a REAL outcome to the formatter** (`o.name or ""` makes it `""`,
#:     which the regex does not match) and would be a NULL — hence not-true, hence
#:     EXCLUDED — to a bare `!~*`. Hence the `IS NULL` arm.
#:
#:     🔴 It is DEFENCE, not a live path, and the first version of this comment said
#:     otherwise. `futures_outcomes.name` is `NOT NULL` — in the model and on production,
#:     where `information_schema` reads `is_nullable = NO` and there are 0 NULL names in
#:     ~1.1M rows — so no reachable row exercises this arm today. It stays because it
#:     costs nothing, fails safe, and is what the predicate would need the day the column
#:     becomes nullable; `test_the_is_null_arm_is_defence_and_the_schema_says_so` asserts
#:     that day has not come and fails loudly when it does.
#:
#:   * **`$` IS NOT `$`.** Python's `$` matches at the end of the string OR immediately
#:     before a single trailing newline; POSIX `$` matches only at the end. So
#:     `"player AB\n"` is GARBAGE to the formatter (`outcome_count: 0`) and NOT garbage
#:     to a bare `…{1,3}$` gate — the market passes the gate and still serves a blank
#:     row, which is precisely the defect this predicate exists to remove, reintroduced
#:     by the gate meant to close it. The trailing `\n?` is what mirrors Python's `$`; it
#:     must not become a whitespace class, which would swallow a trailing space that
#:     Python's `$` rejects and start hiding real rows.
#:
#:   * **`\s` IS NOT `[[:space:]]`, AND WHETHER IT IS DEPENDS ON THE SERVER.** Python's
#:     `\s` on a `str` is Unicode and fixed: 29 characters, exactly `str.isspace()`.
#:     `[[:space:]]` is the server's, and it is decided by the database's ctype — so the
#:     two agree on one machine and disagree on the next, which is the worst shape a
#:     predicate can have. MEASURED, both engines, same names: on PostgreSQL 14 at
#:     `en_US.UTF-8` the old `[[:space:]]` form diverged on `\x85` (NEL) and `\x1c` (file
#:     separator); on CI's server it diverged on `\xa0` (NBSP) as well. Each divergence is
#:     the same defect as the newline one — garbage to the formatter, answerable to the
#:     gate, blank row served.
#:
#:     So the class is no longer asked of the server. It is WRITTEN OUT from Python's own
#:     set below, which makes the two engines agree BY CONSTRUCTION rather than by a
#:     measurement that was only ever true of the machine it was taken on. It also closes
#:     the mirror-image hole nobody had looked for: a locale whose `[[:space:]]` is WIDER
#:     than `\s` would make the gate stricter than the formatter and start hiding rows
#:     that do have a visible outcome.
#:
#: It goes in `conditions` — the list shared by the count query, the data query and the
#: facet counts — deliberately, and NOT as a filter over `formatted`. Filtering after the
#: `LIMIT` would hand the app short pages, a `total` that disagrees with what it can
#: actually scroll to, and facet chips that promise more than the list holds.

#: Every character Python's `\s` matches on a `str`, written out so the SQL mirror does
#: not have to ask the server what whitespace is. Hardcoded rather than derived, because
#: deriving it means scanning 1.1M code points at import; `test_the_written_out_space_
#: class_is_exactly_pythons` does that scan instead and fails if a Python upgrade ever
#: adds one. Ordered by code point. No character here is `]`, `^`, `-` or `\`, so every
#: one is literal inside the bracket expression and none needs escaping.
_PYTHON_SPACE_CHARS = (
    "\t\n\v\f\r"  # HT LF VT FF CR
    "\x1c\x1d\x1e\x1f"  # the four ASCII separators — NOT in POSIX `[[:space:]]`
    " "  # SPACE
    "\x85"  # NEL — diverged on PostgreSQL 14 / en_US.UTF-8
    "\xa0"  # NBSP — diverged on CI's server
    " "  # OGHAM SPACE MARK
    "           "  # EN QUAD…HAIR
    "  "  # LINE / PARAGRAPH SEPARATOR
    "  "  # NARROW NBSP, MEDIUM MATHEMATICAL SPACE
    "　"  # IDEOGRAPHIC SPACE
)

_GARBAGE_OUTCOME_SQL = "^player[" + _PYTHON_SPACE_CHARS + "]+[A-Za-z]{1,3}\\n?$"

_HAS_ANY_OUTCOME_ROW = exists().where(
    and_(
        FuturesOutcome.market_id == FuturesMarket.id,
        or_(
            FuturesOutcome.name.is_(None),
            ~FuturesOutcome.name.op("~*")(_GARBAGE_OUTCOME_SQL),
        ),
    )
)


@router.get("/faceted")
async def faceted_futures_search(
    tags: Optional[str] = Query(None, description="JSON array of tags"),
    sport: Optional[str] = Query(None, description="Sport tag value (e.g., basketball)"),
    category: Optional[str] = Query(None, description="llm_sport_category filter"),
    stakes: Optional[str] = Query(None, description="Stakes tag value"),
    narrative: Optional[str] = Query(None, description="Narrative tag value"),
    audience: Optional[str] = Query(None, description="Audience tag value"),
    q: Optional[str] = Query(None, description="Search within market names"),
    sort: Optional[str] = Query(None, description="Sort order: soonest (default), newest, trending"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
):
    """Faceted search over futures markets using GIN-indexed taxonomy tags."""
    import json as _json
    from sqlalchemy import literal_column, text as sql_text
    from app.utils.event_taxonomy import validate_tag

    # Build tag filter from both sources
    tag_filter: list[str] = []
    if tags:
        try:
            parsed = _json.loads(tags)
            if isinstance(parsed, list):
                tag_filter.extend(str(t) for t in parsed)
        except (ValueError, TypeError):
            pass

    convenience = {"sport": sport, "stakes": stakes, "narrative": narrative, "audience": audience}
    for ns, val in convenience.items():
        if val:
            tag_filter.append(f"{ns}:{val}")

    # Base conditions — open, non-game-level, unresolved, ANSWERABLE
    now = datetime.now(timezone.utc)
    conditions = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        _HAS_ANY_OUTCOME_ROW,
    ]

    if category:
        # #4047, same reason as `/browse`: this endpoint takes the same category
        # keys the census emits, so it inherits the same definition of `other`.
        conditions.append(_category_condition(category))

    if q:
        conditions.append(FuturesMarket.name.ilike(f"%{q}%"))

    # GIN containment filter
    valid_tags: list[str] = []
    if tag_filter:
        valid_tags = [t for t in tag_filter if validate_tag(t)]
        if valid_tags:
            escaped = _json.dumps(valid_tags).replace("'", "''")
            conditions.append(
                FuturesMarket.market_tags.op("@>")(
                    literal_column(f"'{escaped}'::jsonb")
                )
            )

    # Count
    count_q = select(func.count(FuturesMarket.id)).where(*conditions)
    total_count = (await db.execute(count_q)).scalar() or 0

    # Data
    offset_val = (page - 1) * per_page

    # Sort order
    if sort == "trending":
        # Order by max absolute 24h movement across outcomes (desc)
        trending_sub = (
            select(
                FuturesOutcome.market_id,
                func.max(func.abs(FuturesOutcome.probability_change_24h)).label("max_move"),
            )
            .group_by(FuturesOutcome.market_id)
            .subquery()
        )
        data_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .outerjoin(trending_sub, FuturesMarket.id == trending_sub.c.market_id)
            .where(*conditions)
            # Same total-order rule as `/browse` — see that comment. This sort
            # needs it MOST: `max_move` is NULL for every market with no 24h
            # movement, so `nulls_last()` parks a very large block at the tail
            # in arbitrary order. Measured on production 2026-09-18, golf at
            # `per_page=20`: 88 slots, 78 distinct markets.
            .order_by(trending_sub.c.max_move.desc().nulls_last(), FuturesMarket.id.asc())
            .offset(offset_val)
            .limit(per_page)
        )
    elif sort == "newest":
        data_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(*conditions)
            # Total order, as above. NOTE the honest bound: this fixes the TIE
            # half only. `updated_at` is rewritten by price polling, so a row
            # whose timestamp genuinely changes between two page fetches can
            # still move across a boundary — that is inherent to offset paging
            # over a mutating sort key and is NOT claimed fixed here.
            .order_by(FuturesMarket.updated_at.desc().nulls_last(), FuturesMarket.id.asc())
            .offset(offset_val)
            .limit(per_page)
        )
    else:
        # Default: soonest resolution date
        data_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(*conditions)
            # Total order, as above: this is the DEFAULT sort, so it is the one
            # the native futures browser pages on. Measured on production
            # 2026-09-18, golf at `per_page=20`: 88 slots, 79 distinct.
            .order_by(FuturesMarket.resolution_date.asc().nulls_last(), FuturesMarket.id.asc())
            .offset(offset_val)
            .limit(per_page)
        )
    markets = (await db.execute(data_q)).scalars().unique().all()

    formatted = []
    for market in markets:
        real_outcomes = [
            o for o in market.outcomes
            if not _GARBAGE_OUTCOME_RE.match(o.name or "")
        ]
        # #6993, the same bypass as `/browse` above and the reason this arm is not
        # a lesser copy of it: `/api/futures/faceted` is what the iOS client reads
        # (`APIClient.swift`), so the refused price reaches a surface the web fix
        # does not cover. Verified on production 2026-09-18 — market `109485`
        # served outcome `1597367` at `1.0` here and `null` on its own detail
        # route. Slicing `[:3]` after the sort means the sort key has to know about
        # the withhold or a refused leg takes a slot it then renders empty.
        withheld = await _withheld_price_outcome_ids(db, market)
        sorted_outcomes = sorted(
            real_outcomes,
            key=lambda o: 0 if o.id in withheld
            else (float(o.current_probability) if o.current_probability else 0),
            reverse=True,
        )
        top3 = []
        for o in sorted_outcomes[:3]:
            od = {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability is not None else None,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            if o.id in withheld:
                for field in WITHHELD_PRICE_FIELDS:
                    if field in od:
                        od[field] = None
            top3.append(od)
        formatted.append({
            "id": market.id,
            "name": market.name,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            # STRIPPED — SCHEDULED, not yet executed. Queue 333, C272/B4 census (#1620).
            # Unlike the annotated fields in this file, no retention argument survived:
            # it is a stored taxonomy column surfaced on browse rows, declared by both
            # typed clients, read by neither, for five months (introduced 2026-03-01,
            # `39a70392`). It is not diagnostic, not a request-echo, and not half of a
            # rendered pair.
            # Old-build check RECORDED (Item 0's rule — not a grep of the current tree):
            # iOS `marketTags` is `[String]?` — OPTIONAL — so removal is decode-safe for
            # builds already shipped; no crash, the key simply stops arriving.
            # NOT stripped here because a strip is Red: it spans this producer, the web
            # types, the native model, and it moves the typecheck baseline, which the CI
            # ratchet fails on in BOTH directions (gotcha #10). Scheduled deliberately
            # rather than taken opportunistically.
            "market_tags": market.market_tags or [],
            "top_outcomes": top3,
            "outcome_count": len(real_outcomes),
            "image_url": market.image_url,
            "hook_description": market.hook_description,
        })

    # Facet counts
    # #6354: the same answerability gate as `conditions` above, in SQL because this half
    # is raw. A facet chip is a PROMISE ABOUT THE LIST — tapping "Tennis (812)" must not
    # land on 400 rows — so the counter and the thing it counts share one definition. The
    # two are written separately (ORM there, text here) and drift silently if only one
    # moves, which is why a guard test asserts a tag's facet count equals the `total` of
    # the request filtered to that tag.
    facet_sql = """
        SELECT split_part(tag, ':', 1) AS ns, tag, COUNT(*) AS cnt
        FROM futures_markets, jsonb_array_elements_text(market_tags) AS tag
        WHERE status = 'open' AND event_id IS NULL
          AND (resolution_date IS NULL OR resolution_date >= :now)
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo
              WHERE fo.market_id = futures_markets.id
                AND (fo.name IS NULL OR fo.name !~* :garbage_outcome)
          )
    """
    facet_params: dict = {"now": now, "garbage_outcome": _GARBAGE_OUTCOME_SQL}
    if category:
        facet_sql += " AND llm_sport_category = :category"
        facet_params["category"] = category
    if valid_tags:
        escaped_facet = _json.dumps(valid_tags).replace("'", "''")
        facet_sql += f" AND market_tags @> '{escaped_facet}'::jsonb"
    facet_sql += " GROUP BY ns, tag ORDER BY ns, cnt DESC"

    facet_rows = (await db.execute(sql_text(facet_sql), facet_params)).all()
    facets: dict = {}
    for row in facet_rows:
        ns = row[0]
        if ns not in facets:
            facets[ns] = []
        facets[ns].append({"tag": row[1], "count": row[2]})

    return {
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "filters": tag_filter,
        "markets": formatted,
        "facets": facets,
    }


@router.get("")
async def list_futures_markets(
    sport: Optional[str] = Query(None, description="Filter by sport key"),
    status: str = Query("open", description="Filter by status (open, resolved, all)"),
    source: Optional[str] = Query(None, description="Filter by source (odds_api, kalshi)"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all futures markets.

    Returns markets with their top outcomes sorted by probability.
    """
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.sport))
        .options(selectinload(FuturesMarket.outcomes))
    )

    # Apply filters
    conditions = []
    if status != "all":
        conditions.append(FuturesMarket.status == status)
        # Exclude resolved markets (past resolution_date) from non-"all" queries
        now = datetime.now(timezone.utc)
        conditions.append(
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            )
        )

    if source:
        conditions.append(FuturesMarket.source == source)

    if sport:
        # Join to Sport table to filter by sport key
        query = query.join(Sport, FuturesMarket.sport_id == Sport.id)
        conditions.append(Sport.key.ilike(f"%{sport}%"))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(FuturesMarket.updated_at.desc()).limit(500)

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    # Build canonical key → source count map for cross-source badges
    canonical_keys = [m.canonical_market_key for m in markets if m.canonical_market_key]
    source_count_map = {}
    if canonical_keys:
        source_query = (
            select(
                FuturesMarket.canonical_market_key,
                func.count(func.distinct(FuturesMarket.source)).label("source_count"),
                func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
            )
            .where(FuturesMarket.canonical_market_key.in_(canonical_keys))
            .group_by(FuturesMarket.canonical_market_key)
        )
        source_result = await db.execute(source_query)
        for row in source_result.all():
            source_count_map[row.canonical_market_key] = {
                "count": row.source_count,
                "sources": sorted(row.sources) if row.sources else [],
            }

    return {
        "markets": [
            _format_market_summary(market, source_count_map)
            for market in markets
        ],
        "count": len(markets),
    }


# =============================================================================
# Playoff / tournament progression grid (league-wide)
# IMPORTANT: This route MUST appear before /{market_id} to avoid being
# swallowed by the dynamic path parameter.
# =============================================================================


@router.get("/playoff-grid")
async def get_playoff_grid(
    sport: str = Query(..., description="Sport category (basketball, football, hockey, baseball, golf, soccer, tennis)"),
    league: str = Query("", description="League filter (NBA, NFL, NHL, MLB, NCAAB, NCAAF, etc.). Optional."),
    season: str = Query("", description="Season filter (2025-26, 2025). Auto-detected if omitted."),
    top_n: int = Query(40, ge=1, le=64, description="Max teams/participants to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    League-wide playoff progression grid.

    Returns all teams in a league with their probability of making each
    playoff round, merged across sources (Kalshi, Polymarket, Odds API).

    For NCAA basketball, returns March Madness rounds (Round of 32 through Champion).
    For pro leagues, returns Make Playoffs through Championship.

    Example: /api/futures/playoff-grid?sport=basketball&league=NBA
    → columns: Make Playoffs, Conference, Championship
    → rows: all 30 NBA teams with probabilities at each stage
    """
    sport_lower = sport.lower().strip()
    league_upper = league.upper().strip() if league else None

    stages = get_stages_for_sport(sport_lower, league_upper)
    if not stages:
        return {
            "sport": sport_lower,
            "league": league_upper,
            "season": None,
            "stages": [],
            "teams": [],
            "sources": [],
        }

    # --- Find progression markets ---
    # Strategy 1: canonical_market_key pattern matching
    # Keys look like "basketball:NBA:championship:2025-26"
    # We want all keys matching "basketball:NBA:*:*" (or with season filter)

    # Map canonical key market_type → stage key
    # The canonical key "market_type" uses slightly different names than
    # tournament_stages keys (e.g., "conference_winner" vs "conference")
    _CANONICAL_TO_STAGE = {
        "championship": "championship",
        "conference_winner": "conference",
        "division_winner": "division",
        "make_playoffs": "make_playoffs",
        "pennant": "pennant",
        # Golf
        "win": "win",
        "top_5": "top_5",
        "top_10": "top_10",
        "top_20": "top_20",
        "make_cut": "make_cut",
        # Soccer / tennis
        "group_stage": "group_stage",
        "make_final": "make_final",
        # March Madness / NCAA tournament
        "round_of_32": "round_of_32",
        "sweet_16": "sweet_16",
        "elite_eight": "elite_eight",
        "final_four": "final_four",
        "title_game": "title_game",
        # CFP
        "quarterfinal": "quarterfinal",
        "semifinal": "semifinal",
    }

    # Build canonical key patterns that ONLY match valid stage types.
    # Without this filter, "basketball:NBA:%" would also match win_totals,
    # mvp, dpoy, roy, game_prop, etc. — all of which are NOT playoff stages.
    ck_prefix = sport_lower
    if league_upper:
        ck_prefix += f":{league_upper}"
    else:
        ck_prefix += ":"

    # Build OR of specific canonical key patterns for each valid stage type
    valid_ck_types = list(_CANONICAL_TO_STAGE.keys())
    ck_conditions = []
    for ck_type in valid_ck_types:
        pattern = f"{ck_prefix}:{ck_type}:%"
        if season:
            pattern = f"{ck_prefix}:{ck_type}:{season.strip()}"
        ck_conditions.append(FuturesMarket.canonical_market_key.ilike(pattern))

    # NOTE: We intentionally do NOT fall back to leagueless keys
    # (e.g., "basketball::championship:2026") when a league is specified.
    # Those keys are a dumping ground for misclassified markets
    # (NASCAR drivers, hockey teams, misc props all under "basketball::").

    ck_markets: list = []
    if ck_conditions:
        result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                or_(*ck_conditions),
                FuturesMarket.status == "open",
            )
        )
        ck_markets = list(result.scalars().unique().all())

    # Strategy 2: Also find markets by sport category + name-based stage detection
    # (catches Odds API markets that may have no/wrong canonical key)
    name_filters = [
        FuturesMarket.llm_sport_category == sport_lower,
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),  # Not game-level
    ]
    if league_upper:
        name_filters.append(
            or_(
                FuturesMarket.canonical_market_key.ilike(f"%:{league_upper}:%"),
                # Also check market name for league references
                FuturesMarket.name.ilike(f"%{league_upper}%"),
            )
        )
    result2 = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*name_filters)
        .limit(500)
    )
    name_markets = list(result2.scalars().unique().all())

    # Merge and dedup
    seen_ids: set[int] = set()
    all_markets: list[FuturesMarket] = []
    for m in ck_markets + name_markets:
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            all_markets.append(m)

    # Filter out game-level markets
    all_markets = [m for m in all_markets if not is_game_level_market(m.name)]

    # Filter out markets that are NOT playoff progression (draft, awards, stat leaders, etc.)
    _NOT_PROGRESSION_RE = re.compile(
        r"""
        \bdraft\b                 |   # "2026 NBA Draft: 1st Overall pick"
        \b\d+(?:st|nd|rd|th)\s+overall\b |  # "1st Overall pick"
        per\s+game\s+leader       |   # "NBA Assists Per Game Leader"
        scoring\s+leader          |   # "NBA Scoring Leader"
        \bbest\s+record\b         |   # "NBA Best Record"
        \bworst\s+record\b        |   # "NBA Worst Record"
        \b(?:\#?\d+)\s*seed\b     |   # "Western Conference #1 Seed"
        \bseeding\b               |   # "NBA Seeding"
        \bwin\s+total\b           |   # "Win Total"
        \bwins?\s+totals?\b       |   # "Wins Total" / "Win Totals"
        \bover.under\s+wins\b     |   # "Over/Under Wins"
        \bmvp\b                   |   # "NBA MVP"
        \bdpoy\b                  |   # "NBA DPOY"
        \broy\b                   |   # "NBA ROY"
        \brookie\s+of\s+the\s+year\b |
        \bdefensive\s+player\b    |
        \bcoach\s+of\s+the\s+year\b |
        \bmost\s+improved\b       |
        \ball[- ]?star\b          |
        \btotal\s+(?:points|rebounds|assists|wins)\b |
        \b6th\s+man\b             |
        \bexecutive\b             |
        \bretire\b                |   # "Will LeBron James retire before..."
        \bcover\s+of\b            |   # "Who will be on the cover of NBA 2K27?"
        \b2k\d+\b                 |   # "NBA 2K27"
        \badd\s+a\s+new\s+team\b  |   # "Will the NBA add a new team before 2030?"
        \bcba\b                   |   # "New WNBA CBA agreement by...?"
        \bplay[- ]?in\b           |   # "play-in tournament" — not a standard stage
        \bbefore\s+the\s+\d{4}\b  |   # "Canadian team wins X before the 2031 season?"
        \bcanadian\s+team\b           # "Canadian team wins the Stanley Cup"
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    all_markets = [
        m for m in all_markets
        if not _NOT_PROGRESSION_RE.search(m.name)
    ]

    # --- Classify each market into a stage ---
    # Group by stage, allowing multiple markets per stage (from different sources)
    stage_market_groups: dict[str, list[FuturesMarket]] = defaultdict(list)
    detected_season: str | None = season.strip() if season else None

    for m in all_markets:
        # Extract season from canonical key if available
        if not detected_season and m.canonical_market_key:
            parts = m.canonical_market_key.split(":")
            if len(parts) >= 4 and parts[3]:
                detected_season = parts[3]

        # ALWAYS use name-based classification — canonical keys are unreliable
        # (Polymarket assigns "championship" key to draft, awards, stat leaders, etc.)
        stage_key = classify_market_stage(
            m.name, m.external_id, m.market_tier, stages
        )

        # Only include stages that are part of this sport's progression
        if stage_key and any(s["key"] == stage_key for s in stages):
            stage_market_groups[stage_key].append(m)

    if not stage_market_groups:
        return {
            "sport": sport_lower,
            "league": league_upper,
            "season": detected_season,
            "stages": [],
            "teams": [],
            "sources": [],
        }

    # --- Merge outcomes across sources within each stage ---
    # participant merge_key → {name, team_id, probabilities by stage, sources by stage}
    participants: dict[str, dict] = {}
    all_sources: set[str] = set()

    # Load teams for this league for name resolution
    # This lets us merge "Oklahoma City" (Kalshi) with "Oklahoma City Thunder" (Odds API)
    # IMPORTANT: When a league is specified, ONLY load teams from that league
    # to prevent college/MLS/other teams from being matched
    sport_team_lookup: dict[str, dict] = {}  # lowercase name/fragment → team info
    _SPORT_KEY_PREFIXES = {
        "basketball": "basketball_",
        "football": "americanfootball_",
        "hockey": "icehockey_",
        "baseball": "baseball_",
        "soccer": "soccer_",
    }
    # Map league to specific sport key for precise team filtering
    _LEAGUE_TO_SPORT_KEY = {
        "NBA": "basketball_nba",
        "WNBA": "basketball_wnba",
        "NCAAB": "basketball_ncaab",
        "NFL": "americanfootball_nfl",
        "NCAAF": "americanfootball_ncaaf",
        "NHL": "icehockey_nhl",
        "MLB": "baseball_mlb",
        "MLS": "soccer_usa_mls",
    }
    sport_prefix = _SPORT_KEY_PREFIXES.get(sport_lower)
    if sport_prefix or league_upper:
        team_query = select(Team)
        if league_upper and league_upper in _LEAGUE_TO_SPORT_KEY:
            # League-specific: ONLY load teams from this exact league
            # Prevents NCAAB teams from appearing in NBA grid, etc.
            exact_sport_key = _LEAGUE_TO_SPORT_KEY[league_upper]
            team_query = team_query.where(
                Team.sport_id.in_(
                    select(Sport.id).where(Sport.key == exact_sport_key)
                )
            )
        elif league_upper:
            # Unknown league — try ILIKE match
            team_query = team_query.where(
                Team.sport_id.in_(
                    select(Sport.id).where(Sport.key.ilike(f"%{league_upper.lower()}%"))
                )
            )
        elif sport_prefix:
            team_query = team_query.where(
                Team.sport_id.in_(
                    select(Sport.id).where(Sport.key.ilike(f"{sport_prefix}%"))
                )
            )
        team_result = await db.execute(team_query)
        for t in team_result.scalars().all():
            t_dict = {
                "id": t.id,
                "name": t.name,
                "logo_url": t.logo_url_small or t.logo_url,
                "primary_color": t.primary_color,
                "secondary_color": t.secondary_color,
                # Only include record when standings data has active season info
                # (prevents showing stale past-season records during offseason)
                "record": t.current_record if (t.standings_data or {}).get("wins") is not None else None,
                "conference": (t.standings_data or {}).get("conference"),
                "division": (t.standings_data or {}).get("division"),
            }
            # Index by full name, lowercase
            sport_team_lookup[t.name.lower()] = t_dict
            # Also index by short name fragments for partial matching
            # "Oklahoma City Thunder" → also index "oklahoma city"
            parts = t.name.rsplit(" ", 1)
            if len(parts) == 2 and len(parts[0]) >= 3:
                # "Oklahoma City" from "Oklahoma City Thunder"
                sport_team_lookup[parts[0].lower()] = t_dict
            # Index alternate names
            for alt in (t.alternate_names or []):
                sport_team_lookup[alt.lower()] = t_dict

    # Market-level league validation: reject markets from wrong leagues
    # that were miskeyed with a matching canonical key.
    # Strategy: If the market name explicitly mentions a DIFFERENT league, reject it.
    if league_upper:
        _OTHER_LEAGUES = {
            "NBA": [r"\bMLS\b", r"\bWNBA\b", r"\bNHL\b", r"\bNFL\b", r"\bMLB\b", r"\bNCAA\b", r"\bPGA\b"],
            "NFL": [r"\bNBA\b", r"\bMLS\b", r"\bWNBA\b", r"\bNHL\b", r"\bMLB\b", r"\bNCAA\b"],
            "NHL": [r"\bNBA\b", r"\bMLS\b", r"\bWNBA\b", r"\bNFL\b", r"\bMLB\b", r"\bNCAA\b"],
            "MLB": [r"\bNBA\b", r"\bMLS\b", r"\bWNBA\b", r"\bNHL\b", r"\bNFL\b", r"\bNCAA\b"],
            "MLS": [r"\bNBA\b", r"\bWNBA\b", r"\bNHL\b", r"\bNFL\b", r"\bMLB\b", r"\bNCAA\b"],
        }
        wrong_league_patterns = _OTHER_LEAGUES.get(league_upper, [])
        if wrong_league_patterns:
            wrong_league_re = re.compile("|".join(wrong_league_patterns), re.IGNORECASE)
            for stage_key in list(stage_market_groups.keys()):
                stage_market_groups[stage_key] = [
                    m for m in stage_market_groups[stage_key]
                    if not wrong_league_re.search(m.name)
                ]

    # Additionally validate markets with no league in their name by checking
    # if their outcomes match known teams (catches NHL teams miskeyed as NBA, etc.)
    if sport_team_lookup and league_upper:
        for stage_key in list(stage_market_groups.keys()):
            validated = []
            for m in stage_market_groups[stage_key]:
                non_binary_outcomes = [
                    o for o in m.outcomes
                    if o.name and not re.match(r"^(yes|no)$", o.name.strip(), re.IGNORECASE)
                ]
                if not non_binary_outcomes:
                    validated.append(m)
                    continue
                matched = 0
                for o in non_binary_outcomes:
                    name = re.sub(r"^(?:Yes|No)\s*[-:]\s*", "", o.name, flags=re.IGNORECASE).strip()
                    name_lower = name.lower()
                    if name_lower in sport_team_lookup:
                        matched += 1
                match_rate = matched / len(non_binary_outcomes)
                if match_rate >= 0.3:
                    validated.append(m)
                # else: skip — outcomes don't match league teams
            stage_market_groups[stage_key] = validated

    # Build team_info from the sport-specific team lookup ONLY
    # Do NOT blindly load teams from outcome team_ids — those could point
    # to NCAAB/MLS/other teams that shouldn't appear in the NBA grid
    team_info: dict[int, dict] = {}
    # Build team_info from sport_team_lookup (league-specific teams only)
    seen_team_ids: set[int] = set()
    for t_dict in sport_team_lookup.values():
        if t_dict["id"] not in seen_team_ids:
            seen_team_ids.add(t_dict["id"])
            team_info[t_dict["id"]] = t_dict

    def _resolve_outcome_team(outcome) -> tuple[str, int | None, dict | None]:
        """Resolve an outcome to a team, returning (merge_key, team_id, team_info).

        Uses outcome.team_id if available, otherwise fuzzy-matches
        the outcome name against the sport's team list.
        """
        if outcome.team_id and outcome.team_id in team_info:
            return f"team:{outcome.team_id}", outcome.team_id, team_info[outcome.team_id]

        # Try name-based resolution against sport teams
        name = outcome.name or ""
        # Strip "Yes: " / "No: " prefixes (Kalshi format)
        clean_name = re.sub(r"^(?:Yes|No)\s*[-:]\s*", "", name, flags=re.IGNORECASE).strip()

        # Exact match on full cleaned name
        t_info = sport_team_lookup.get(clean_name.lower())
        if t_info:
            return f"team:{t_info['id']}", t_info["id"], t_info

        # Try without trailing "s" (e.g. "76er" → won't work, but catches edge cases)
        # Try stripping common suffixes like "Celtics" → match "Boston Celtics"
        # by checking if any team name ends with this word
        for team_name_lower, t_info in sport_team_lookup.items():
            # "Celtics" matches "Boston Celtics" (exact suffix)
            if team_name_lower.endswith(clean_name.lower()) and len(clean_name) >= 4:
                return f"team:{t_info['id']}", t_info["id"], t_info
            # "Oklahoma City" matches "Oklahoma City Thunder" (exact prefix)
            if team_name_lower.startswith(clean_name.lower()) and len(clean_name) >= 4:
                return f"team:{t_info['id']}", t_info["id"], t_info

        # No match — use name-based merge key
        return _progression_merge_key(outcome), None, None

    # Outcomes to skip — binary outcomes, over/under, dates, generic names
    _SKIP_OUTCOME_RE = re.compile(
        r"""
        ^(yes|no)$                |   # Binary market outcomes
        \bover\b.*\(              |   # "Team: Over (41.5)"
        \bunder\b.*\(             |   # "Team: Under (41.5)"
        ^\d{1,2}\+?\s*(wins?|losses?)|  # "50 wins", "10+ wins"
        ^at\s+least\s+\d          |   # "At least 10% of total games"
        ^(january|february|march|april|may|june|july|august|september|october|november|december)\b |  # month names
        ^\d{1,2}\s*$              |   # bare numbers like "5"
        ^(first|second|third)\s+half |  # "First Half"
        \d+\.\d+\)$                  # trailing "41.5)" from over/under
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # For team sports, require outcomes to resolve to a known team
    # This filters out player names (Wembanyama, Edwards), wrong-league teams
    # (NCAAB teams in NBA grid), and other non-team outcomes
    require_team_resolution = bool(sport_team_lookup) and sport_lower in (
        "basketball", "football", "hockey", "baseball",
    )

    for stage_key, markets in stage_market_groups.items():
        for m in markets:
            source = m.source or "unknown"
            all_sources.add(source)

            for o in m.outcomes:
                # Skip non-team outcomes (binary yes/no, over/under, dates)
                if _SKIP_OUTCOME_RE.search(o.name):
                    continue

                merge_key, resolved_team_id, resolved_info = _resolve_outcome_team(o)

                # For team sports: skip outcomes that don't resolve to a known team
                # This filters player names, wrong-league teams, etc.
                if require_team_resolution and not resolved_team_id:
                    continue

                if merge_key not in participants:
                    t_info = resolved_info or (team_info.get(o.team_id) if o.team_id else None)
                    participants[merge_key] = {
                        "name": resolved_info["name"] if resolved_info else o.name,
                        "team_id": resolved_team_id or o.team_id,
                        "logo_url": t_info["logo_url"] if t_info else None,
                        "primary_color": t_info["primary_color"] if t_info else None,
                        "secondary_color": t_info["secondary_color"] if t_info else None,
                        "conference": t_info["conference"] if t_info else None,
                        "division": t_info["division"] if t_info else None,
                        "record": t_info["record"] if t_info else None,
                        "stages": {},
                    }

                p = participants[merge_key]
                prob = float(o.current_probability) if o.current_probability is not None else None

                # Update team info if resolved in this iteration but not before
                effective_team_id = resolved_team_id or o.team_id
                if effective_team_id and not p["team_id"]:
                    p["team_id"] = effective_team_id
                    t_info = resolved_info or team_info.get(effective_team_id)
                    if t_info:
                        p["name"] = t_info.get("name", p["name"])
                        p["logo_url"] = t_info["logo_url"]
                        p["primary_color"] = t_info["primary_color"]
                        p["secondary_color"] = t_info["secondary_color"]
                        p["conference"] = t_info["conference"]
                        p["division"] = t_info["division"]
                        p["record"] = t_info["record"]

                if stage_key not in p["stages"]:
                    p["stages"][stage_key] = {
                        "sources": [],
                        "probability": None,
                        "change_24h": None,
                        "status": None,
                        "market_id": None,
                    }

                stage_data = p["stages"][stage_key]
                stage_data["sources"].append({
                    "source": source,
                    "probability": prob,
                    "market_id": m.id,
                    "change_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
                })

    # --- Infer conference from conference/pennant stage market names ---
    # When standings_data doesn't have conference (e.g., NFL offseason), we can
    # infer it from which conference-stage market a team appears in.
    # E.g., a team in "NFL: 2027 AFC Champion" → conference = "AFC"
    # A team in "NBA Eastern Conference Champion" → conference = "Eastern Conference"
    _CONF_MARKET_PATTERNS: list[tuple[re.Pattern, str]] = [
        # NFL: "AFC" / "NFC" (no "Conference" suffix in NFL naming)
        (re.compile(r"\bAFC\b(?!\s+(?:East|North|South|West))", re.IGNORECASE), "AFC"),
        (re.compile(r"\bNFC\b(?!\s+(?:East|North|South|West))", re.IGNORECASE), "NFC"),
        # NBA / NHL: "Eastern Conference" / "Western Conference"
        (re.compile(r"\bEastern\b", re.IGNORECASE), "Eastern Conference"),
        (re.compile(r"\bWestern\b", re.IGNORECASE), "Western Conference"),
        # MLB: "American League" / "National League"
        (re.compile(r"\bAmerican\s+League\b", re.IGNORECASE), "American League"),
        (re.compile(r"\bNational\s+League\b", re.IGNORECASE), "National League"),
    ]
    # Only check conference/pennant stage markets
    conf_stage_keys = {"conference", "pennant"}
    for stage_key in conf_stage_keys:
        if stage_key not in stage_market_groups:
            continue
        for m in stage_market_groups[stage_key]:
            # Detect conference from market name
            detected_conf = None
            for pat, conf_name in _CONF_MARKET_PATTERNS:
                if pat.search(m.name):
                    detected_conf = conf_name
                    break
            if not detected_conf:
                continue

            # Assign conference to all outcomes in this market
            for o in m.outcomes:
                if _SKIP_OUTCOME_RE.search(o.name):
                    continue
                merge_key, _, _ = _resolve_outcome_team(o)
                if merge_key in participants and not participants[merge_key].get("conference"):
                    participants[merge_key]["conference"] = detected_conf

    # Average probabilities across sources per stage
    for p in participants.values():
        for stage_key, stage_data in p["stages"].items():
            probs = [s["probability"] for s in stage_data["sources"] if s["probability"] is not None]
            if probs:
                avg_prob = sum(probs) / len(probs)
                stage_data["probability"] = round(avg_prob, 4)
                # Pick best market_id (prefer source with most outcomes for linking)
                stage_data["market_id"] = stage_data["sources"][0]["market_id"]
                # Average 24h changes
                changes = [s["change_24h"] for s in stage_data["sources"] if s["change_24h"] is not None]
                if changes:
                    stage_data["change_24h"] = round(sum(changes) / len(changes), 4)
                # Detect clinched / eliminated
                if avg_prob >= 0.999:
                    stage_data["status"] = "clinched"
                elif avg_prob <= 0.001:
                    stage_data["status"] = "eliminated"

    # Normalize probabilities per stage so they sum to ~100%
    # Sportsbook/prediction market odds often have overround (sum > 100%)
    for stage_key in stage_market_groups:
        stage_total = sum(
            p["stages"][stage_key]["probability"]
            for p in participants.values()
            if stage_key in p["stages"] and p["stages"][stage_key]["probability"] is not None
        )
        if stage_total > 0 and abs(stage_total - 1.0) > 0.05:  # Only normalize if >5% off
            scale = 1.0 / stage_total
            for p in participants.values():
                if stage_key in p["stages"] and p["stages"][stage_key]["probability"] is not None:
                    p["stages"][stage_key]["probability"] = round(
                        p["stages"][stage_key]["probability"] * scale, 4
                    )

    # Sort by highest-stage probability (championship first, fallback to conference, etc.)
    stage_order = sorted(
        [s for s in stages if s["key"] in stage_market_groups],
        key=lambda s: s["order"],
        reverse=True,
    )

    def sort_key(p: dict) -> tuple:
        for stage_def in stage_order:
            sk = stage_def["key"]
            stage_data = p["stages"].get(sk)
            if stage_data and stage_data["probability"] is not None:
                return (stage_def["order"], stage_data["probability"])
        return (0, 0)

    sorted_participants = sorted(participants.values(), key=sort_key, reverse=True)[:top_n]

    # Build ordered stages response
    stages_response = []
    for stage_def in sorted(stages, key=lambda s: s["order"]):
        if stage_def["key"] in stage_market_groups:
            markets_in_stage = stage_market_groups[stage_def["key"]]
            sources_in_stage = list({m.source or "unknown" for m in markets_in_stage})
            stages_response.append({
                "key": stage_def["key"],
                "label": stage_def["label"],
                "order": stage_def["order"],
                "market_count": len(markets_in_stage),
                "sources": sources_in_stage,
                "market_ids": [m.id for m in markets_in_stage],
            })

    return {
        "sport": sport_lower,
        "league": league_upper,
        "season": detected_season,
        "stages": stages_response,
        "teams": sorted_participants,
        "sources": sorted(all_sources),
    }


#: How far a sparse history window is widened, and when. Slowly-polled futures
#: (politics, economics, and every league's DIVISION markets) carry only a
#: handful of snapshots in seven days, so a literal 7-day read charts nothing.
#:
#: MODULE SCOPE since UX-1052 item 7. It used to be a local inside
#: `get_futures_history`, which is how `/multi-history` came to lack it — and
#: `/multi-history` is the ONLY path a league page's stage tabs use, so the MLB
#: "Division" tab printed "Limited price history available" over a market whose
#: single-market endpoint served 5,065 points.
_EXTEND_TIERS = [
    (20, 720),   # <20 snapshots -> try 30 days
    (10, 2160),  # <10 snapshots -> try 90 days
]


#: UX-1052 item 3 — how many players a placement grid puts on a FEED card.
#: The concept page's version of the same grid shows 20; a strip card is a
#: glance, and a 156-golfer table inside it is the five-card wall it replaced
#: wearing a different shape. The card prints `row_total` so the depth of the
#: real field is stated rather than hidden.
PLACEMENT_GRID_FEED_ROWS = 8


def _leg_prices_an_empty_book(outcome) -> bool:
    """Is this leg's number the midpoint of a book with nothing in it? (#6676)

    WHAT A READER SAW. Three consecutive Game Props cards in one 390px viewport
    on ``/sports``, each printing **Over 50% / Under 50%** with the bar drawn at
    exactly half, directly beneath a card whose 57/43 was real — so the reader
    had no way to tell a manufactured coin flip from a forecast. The stored rows
    behind them (outcomes 230498576, 230496527, 230475436, read 2026-09-17):
    ``current_probability 0.500000`` beside ``current_yes_bid 0.0200 /
    current_yes_ask 0.9700``, ``volume`` and ``price_changed_at`` both NULL. That
    quote bounds nothing, and its own midpoint is 0.495 — the stored number is
    half a cent off the book it was averaged from. A fabricated 50% is the one
    number that looks most like an answer.

    THE RULE IS NOT NEW AND IS NOT RE-DERIVED HERE. :func:`is_empty_book_midpoint`
    is #5247's shipped predicate, with its own measured constants, and the
    expression below is field for field the one already running at its call site
    in ``routes/events.py`` (``game-markets``). That surface got the rule and this
    one did not, which is the entire defect: the strip and the event page draw
    from the same rows and disagreed about whether those rows have a price. A
    second, differently-spelled copy of a price rule is exactly what
    ``futures_unsupported_price`` exists to prevent, so this is a delegation with
    a name, not a policy.

    IT IS A NAMED FUNCTION AND NOT AN INLINE COMPREHENSION for the reason
    :func:`_market_has_priced_outcome` states directly below: the one property
    that makes it a fix has to be testable without standing up the route.

    A LEG, NOT A MARKET, for the reason the shipped call site gives: a props
    market carries real lines beside its unpriced ones and dropping the card
    would take the real ones with it. A market whose legs are ALL empty-book then
    has no priced outcome left, and ``_market_has_priced_outcome`` drops its card
    BEFORE the truncation (#2710) — so the vacated slot is backfilled from the
    ``limit * 5`` rows the route already loaded and the strip stays a full strip.

    WHAT IT DELIBERATELY DOES NOT TOUCH. Read-side only (gotcha #21): nothing
    here rewrites a stored price, and withholding rather than rewriting is the
    standing rule, because ``calibration_probability`` coalesces to stored values
    (gotcha #144 / ruling 103) and an invented price becomes a forecast we are
    graded on. A genuine 50% on a tight book (49c/51c), a one-sided real ask and
    every model price (both book columns NULL) are all passed through by the
    predicate's own construction.

    🪤 "A TRADED 50% IS PASSED THROUGH" USED TO BE ON THAT LIST AND IT WAS WRONG.
    The #5333 bid-bound move (0.02 -> 0.05, 2026-09-17) made it measurable: of the
    1,119 rows it newly reaches, two are a genuinely traded 0.500 sitting on a
    now-empty 3c/97c book, and this function withdraws them. It cannot do
    otherwise — it reads three columns and the serve path carries no provenance of
    where a stored price came from. The writer's volume-gated last-trade exception
    protects the ingest side by SUBSTITUTING the trade price; nothing carries that
    label through to here. So the honest sentence for this surface is "no current
    quote supports this number", never "this number was never real".
    """
    # `getattr` RATHER THAN ATTRIBUTE ACCESS, matching `_book_refuted_outcome_ids`
    # below, and #6757 is why it changed. Until then this ran on exactly one call
    # site holding ORM rows, where the three columns always exist. It now also runs
    # on every `/api/futures/{id}` request, and a serve path must not 500 because a
    # caller handed it an object without a book — the absent case is "no book to
    # call empty", which falls through to the honest answer of leaving the price
    # alone. `is_empty_book_midpoint` already returns False for a null book, so this
    # is the same fail-open the predicate documents and not a second rule.
    return is_empty_book_midpoint(
        getattr(outcome, "current_probability", None),
        getattr(outcome, "current_yes_bid", None),
        getattr(outcome, "current_yes_ask", None),
    )


def _market_has_priced_outcome(market: dict) -> bool:
    """Does this grouped-feed market carry a probability the card can print?

    #2710. The strip renders one card per row with no admission of its own, so a
    market with no outcomes, or with outcomes that are all unpriced, becomes a
    card whose body is the words "No outcomes available" or a column of dashes.

    `Decimal` IS THE NORMAL CASE HERE AND MUST BE ACCEPTED EXPLICITLY.
    `FuturesOutcome.probability` is a property returning `current_probability`,
    whose column is `Numeric(7, 6)`, so SQLAlchemy hands back a
    `decimal.Decimal` — the `Mapped[Optional[float]]` annotation on that column
    describes the intent, not the runtime type. `isinstance(x, (int, float))`
    is False for a Decimal, and so is `isinstance(x, numbers.Real)` (verified in
    the interpreter, not recalled: Decimal registers as `numbers.Number` only).
    Either of those spellings would have dropped EVERY ungrouped market and
    emptied the strip. This is the same Decimal-on-this-endpoint seam as #2554.

    A truthiness test would be wrong in the other direction: it discards a
    genuine 0.0, which is a real and printable "0%". `bool` is excluded because
    `isinstance(True, int)` is True, and a string is refused outright — a
    stringified probability (#2554's shape) is not something the card can
    render, so it must not readmit a row by merely looking truthy.
    """
    for outcome in market.get("outcomes") or ():
        probability = outcome.get("probability")
        if isinstance(probability, bool):
            continue
        if isinstance(probability, (int, float, Decimal)):
            return True
    return False


#: A container group is only worth a round trip once it is actually flooding the
#: strip. One member in the pool is one card, which is the shape it should have
#: anyway — the fold exists to collapse walls, not to reshape singletons.
CONTAINER_FOLD_MIN_POOL_MEMBERS = 2

#: How many of a folded field's entities the card prints, matching the ungrouped
#: market card's own `[:5]`. The strip is a glance; the full field lives on the
#: market page behind it.
CONTAINER_FOLD_CARD_ROWS = 5


async def load_container_field_folds(
    db: AsyncSession, market_dicts: list[dict]
) -> dict[str, dict]:
    """The container groups in this pool that fold into one field card (#4153).

    TWO QUERIES, BOTH KEYED ON `group_id`, BOTH SKIPPED WHEN NOTHING FLOODS.
    This runs on the miss path of a Redis-cached, pre-warmed endpoint that was
    measured at ~1 s (LAT-P100), so it earns its place by being bounded: the
    candidate set is at most the number of distinct groups in a 100-row pool,
    and a pool with no repeated group returns before touching the database.

    THE SECOND QUERY IS THE POINT. The pool holds whichever legs were polled
    most recently — 5 of the 40 members of "To Reach the Final" on the night
    this was written. Folding that slice would head a card with the question and
    then rank a field the leader is missing from, which is #2789 rebuilt: the
    strip's own comment records a 192-golfer market whose card led with 0.09%.
    So the fold reads the group's FULL membership and ranks that.
    """
    from ..utils.market_grouping import detect_container_field_groups

    pool_by_group: dict[str, int] = defaultdict(int)
    for m in market_dicts:
        if m.get("market_type") != "container_member":
            continue
        group_id = m.get("group_id")
        if group_id:
            pool_by_group[str(group_id)] += 1

    candidates = [
        gid for gid, n in pool_by_group.items()
        if n >= CONTAINER_FOLD_MIN_POOL_MEMBERS
    ]
    if not candidates:
        return {}

    # The venue's own wording for the question. No parent row, no fold — the
    # alternative is inventing a headline out of the members' grammar, and a
    # title is the one thing on this card a reader cannot check.
    parent_rows = await db.execute(
        select(FuturesMarket.group_id, FuturesMarket.name).where(
            FuturesMarket.group_id.in_(candidates),
            FuturesMarket.market_type == "field",
        )
    )
    parent_names: dict[str, str] = {}
    for group_id, name in parent_rows.all():
        if group_id and name and group_id not in parent_names:
            parent_names[str(group_id)] = name
    if not parent_names:
        return {}

    # BOTH legs, not just the Yes. #4203: the two rows of one binary are written
    # by separate passes, so a member that has gone closed at the venue can sit
    # at Yes 0.833 / No 1.000 indefinitely — and the Yes alone looks like a
    # perfectly good price. The No leg is fetched only so the fold can check the
    # pair and refuse the member; it is never rendered and never inverted.
    member_rows = await db.execute(
        select(
            FuturesMarket.group_id,
            FuturesMarket.id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesOutcome.name,
            FuturesOutcome.current_probability,
        )
        .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.group_id.in_(list(parent_names.keys())),
            FuturesMarket.market_type == "container_member",
            FuturesMarket.status.in_(["active", "open"]),
            func.lower(FuturesOutcome.name).in_(["yes", "no"]),
        )
    )
    members_by_id: dict[int, dict] = {}
    for group_id, market_id, name, source, leg, probability in member_rows.all():
        member = members_by_id.setdefault(
            market_id,
            {
                "group_id": str(group_id),
                "id": market_id,
                "name": name,
                "source": source,
                "probability": None,
                "complement_probability": None,
            },
        )
        key = (
            "probability"
            if (leg or "").strip().lower() == "yes"
            else "complement_probability"
        )
        member[key] = probability

    members_by_group: dict[str, list[dict]] = defaultdict(list)
    for member in members_by_id.values():
        members_by_group[member["group_id"]].append(member)

    return detect_container_field_groups(members_by_group, parent_names)


def select_ungrouped_markets(
    market_dicts: list, grouped_market_ids: set, limit: int
) -> list:
    """The ungrouped markets the grouped feed will ship, at most ``limit``.

    #2710. Exists as a named function rather than an inline comprehension so the
    ONE property that makes it a fix is testable: the priceless rows come out
    BEFORE the truncation, so their slots are backfilled from the ``limit * 5``
    rows the route already loaded. Filtering after the slice would leave the
    reader short — 18 cards where 20 were asked for — which is a different and
    worse outcome than the bug it replaces.
    """
    return [
        m
        for m in market_dicts
        if m["id"] not in grouped_market_ids and _market_has_priced_outcome(m)
    ][:limit]


async def _read_grouped_feed_cache(cache_key: str):
    """Fresh-then-stale read of the shared grouped-feed entry.

    Returns ``(payload, status)`` with status ``"hit"`` or ``"stale_hit"``, or
    ``(None, None)``. It never raises. The caller was about to pay a ~1 s build
    anyway, so every failure here degrades to that build rather than to an error:
    a cache that can 500 the endpoint it was added to speed up is a net loss at
    any hit rate (the same contract ``_read_shared_feed_cache`` states in
    ``routes/feed.py``).
    """
    import json as _json

    from app.utils import request_cache as _rc

    try:
        client = await _rc.get_shared_async_redis()
        if client is None:
            return None, None
        for suffix, status in (("", "hit"), (":stale", "stale_hit")):
            got = await _rc.bounded_redis_call(
                lambda k=f"{cache_key}{suffix}": client.get(k)
            )
            if got.is_ok and got.value is not None:
                try:
                    payload = _json.loads(got.value)
                except Exception:
                    continue  # malformed is a typed miss, never a crash
                if isinstance(payload, dict):
                    return payload, status
    except Exception:
        logger.debug("grouped-feed cache read failed", exc_info=True)
    return None, None


async def _publish_grouped_feed_cache(cache_key: str, payload: dict) -> None:
    """Publish one grouped-feed shape under the key the route just read.

    Best-effort by construction: the response has already been built and the
    caller is about to return it, so a Redis failure must cost the next visitor a
    rebuild and this visitor nothing.

    #2554 — THE CACHED BODY IS ENCODED THE WAY THE MISS PATH ENCODES IT.
    This used to be ``_json.dumps(payload, default=str)``. ``default=`` fires for
    every value ``json`` cannot serialize natively, and ``current_probability`` is
    a ``Numeric`` column, so each one arrived here as a ``Decimal`` and was
    written as the STRING ``"0.682560"``. The route's own return path never sees
    that: FastAPI encodes the dict with ``jsonable_encoder``, which turns a
    ``Decimal`` into a float. So one endpoint served two different types for one
    field depending on whether the caller hit the cache — floats on a miss,
    strings on every hit, i.e. on ~all real traffic.

    Downstream that is not a cosmetic difference. ``/sports`` prop cards read the
    value twice: ``Number.isFinite("0.68")`` is ``false`` so the number renders as
    an em dash, while ``prob * 100`` coerces the same string happily so the bar
    beside it draws the correct width. A card with a right-sized bar and no
    number is the signature of this bug, not of a missing price.

    Encoding with ``jsonable_encoder`` rather than special-casing ``Decimal`` is
    the point: it is the SAME encoder the miss path runs, so hit and miss cannot
    disagree by construction, and the next non-JSON type to enter this payload
    cannot silently reopen the defect for a different field.
    """
    import json as _json

    from fastapi.encoders import jsonable_encoder

    from app.utils import request_cache as _rc
    from app.utils.grouped_feed_cache import (
        GROUPED_FEED_STALE_TTL_SECONDS,
        GROUPED_FEED_TTL_SECONDS,
    )

    try:
        client = await _rc.get_shared_async_redis()
        if client is None:
            return
        body = _json.dumps(jsonable_encoder(payload))
        await _rc.bounded_redis_call(
            lambda: client.setex(cache_key, GROUPED_FEED_TTL_SECONDS, body)
        )
        await _rc.bounded_redis_call(
            lambda: client.setex(
                f"{cache_key}:stale", GROUPED_FEED_STALE_TTL_SECONDS, body
            )
        )
    except Exception:
        logger.debug("grouped-feed cache write failed", exc_info=True)


@router.get("/grouped-feed")
async def grouped_feed(
    request: Request,
    response: Response,
    category: Optional[str] = Query(None, description="Filter by category (sports, crypto, politics, weather)"),
    sport: Optional[str] = Query(None, description="Filter by sport"),
    sports_only: bool = Query(False, description="Restrict to /sports-page sport categories (excludes esports/geopolitics/crypto/etc.)"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a feed of grouped futures markets optimized for display.

    Returns markets intelligently grouped into:
    - stat_prop: Player stat props (e.g., "Tatum 25+ Points")
    - playoff_progression: Tournament stage progressions
    - threshold: Numeric threshold variants (e.g., Bitcoin price targets)
    - ungrouped: Markets without detected groupings

    Each group includes metadata for rendering the appropriate card type
    (ThresholdSparkline, PlayerStatCard, ProgressionLadder, etc.)

    LAT-P100: this route had no cache of any kind while being one of the three
    requests the native Sports tab issues on every open — measured 1,034.5 ms p50
    (max 1,308) for the native shape and 683.0 ms p50 for the web one, on every
    open, for every person. It reads ``limit * 5`` markets with their outcomes
    eagerly loaded and then runs three grouping passes over them, and it takes no
    principal at all, so one shared entry per shape serves everybody. The pre-warm
    beat keeps both real shapes warm; this read is what makes that warm worth
    anything, and the request path still publishes on a miss so the cache works
    even if the beat is broken.
    """
    from ..utils.market_grouping import (
        detect_exact_score_groups,
        detect_placement_groups,
        detect_stat_prop_groups,
        detect_playoff_progression_groups,
        detect_threshold_groups,
    )
    from ..utils.grouped_feed_cache import (
        GROUPED_FEED_CACHE_HEADER,
        GROUPED_FEED_PREWARM_SCOPE_KEY,
        grouped_feed_cache_key,
    )

    # LAT-P100. The marker is read from the ASGI *scope*, never from a header or
    # query param, so it is unreachable from HTTP — an outside caller must not be
    # able to force cold rebuilds of an expensive endpoint.
    _prewarm_rebuild = bool(
        getattr(request, "scope", None)
        and request.scope.get(GROUPED_FEED_PREWARM_SCOPE_KEY)
    )
    _cache_key = grouped_feed_cache_key(
        category=category, sport=sport, sports_only=sports_only, limit=limit
    )
    if not _prewarm_rebuild:
        _cached, _status = await _read_grouped_feed_cache(_cache_key)
        if _cached is not None:
            response.headers[GROUPED_FEED_CACHE_HEADER] = _status
            return _cached
    response.headers[GROUPED_FEED_CACHE_HEADER] = (
        "prewarm" if _prewarm_rebuild else "miss"
    )

    filters = [
        FuturesMarket.status.in_(["active", "open"]),
    ]
    if category:
        filters.append(FuturesMarket.category == category)
    if sport:
        filters.append(FuturesMarket.llm_sport_category == sport)
    if sports_only:
        # #959: real sports filter on llm_sport_category (NOT FuturesMarket.category,
        # which holds values like "championship"). esports is excluded — it stays in
        # Discover/Browse but is not a /sports surface (#958). Function-level import
        # keeps this route circular-import-safe.
        from app.routes.feed import SPORTS_PAGE_CATEGORIES

        filters.append(
            FuturesMarket.llm_sport_category.in_(SPORTS_PAGE_CATEGORIES)
        )

    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(and_(*filters))
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit * 5)
    )
    result = await db.execute(stmt)
    markets = result.scalars().unique().all()

    market_dicts = []
    outcome_dicts = []
    for m in markets:
        m_dict = {
            "id": m.id,
            "name": m.name,
            "source": m.source,
            "category": m.category,
            "sport": m.llm_sport_category,
            "status": m.status,
            "group_id": m.group_id,
            "group_type": m.group_type,
            # #4153: the canonical shape, so the container fold can tell one
            # leg of a field apart from a market that is a whole question.
            "market_type": m.market_type,
            "outcomes": [],
        }
        for o in m.outcomes:
            if _leg_prices_an_empty_book(o):
                continue
            o_dict = {
                "id": o.id,
                "name": o.name,
                "probability": o.probability,
                "american_odds": o.american_odds,
                "market_id": m.id,
                # #1102: thread parent-market context so threshold grouping scopes
                # to a single real-world question (player/game/entity) instead of
                # pooling every "over #" outcome across unrelated markets.
                "market_name": m.name,
                "group_id": m.group_id,
                "source": m.source,
            }
            m_dict["outcomes"].append(o_dict)
            outcome_dicts.append(o_dict)
        market_dicts.append(m_dict)

    stat_prop_groups = detect_stat_prop_groups(market_dicts)
    playoff_groups = detect_playoff_progression_groups(market_dicts)
    threshold_groups = detect_threshold_groups(outcome_dicts)
    # UX-1052 item 2 — exact-score outcomes are a discrete distribution over
    # scorelines. `extract_threshold` now refuses them, so without this they
    # would simply vanish from the strip; with it they keep their card and gain
    # rung labels that are the actual outcomes ("2–3"), which is what Alex
    # asked for: "show the real scorelines or the real thresholds."
    exact_score_groups = detect_exact_score_groups(outcome_dicts)
    # UX-1052 item 3 — one tournament's placement questions are ONE grid.
    # Alex: five near-identical Omega European Masters cards (Winner / Top 5 /
    # Top 10 / Top 20 / Make the Cut) listing the same golfers — "group them
    # into a beautiful grid."
    placement_groups = detect_placement_groups(market_dicts)
    # #4153 — one Polymarket container group is ONE question, not one card per
    # member. Loaded here rather than detected from `market_dicts` because the
    # fold needs the group's whole membership; see `load_container_field_folds`.
    container_folds = await load_container_field_folds(db, market_dicts)

    grouped_market_ids = set()
    grouped_outcome_ids = set()
    feed_items = []

    # The fold goes FIRST so its members are already claimed when the ungrouped
    # pass runs: leaving them unclaimed would put the wall back underneath the
    # card built to replace it, which is the mistake the placement grid's own
    # "the grid CONSUMES its markets" note records.
    # Sport and category are the pool row's own, never invented: the strip and
    # its callers filter on them, and a made-up value would put a tennis card
    # under a soccer filter.
    #
    # THE POOL IS WHAT GETS CLAIMED, not the fold's own `market_ids`. Those come
    # from the membership query, which only returns members carrying a Yes leg —
    # so a member with no Yes leg would survive into the ungrouped pass and put
    # its group on a second card, which is the one thing this fix must make
    # impossible ("no group_id appears on more than one card", #4153).
    _pool_by_group: dict[str, dict] = {}
    for m in market_dicts:
        gid = m.get("group_id")
        if gid and str(gid) in container_folds:
            _pool_by_group.setdefault(str(gid), m)
            grouped_market_ids.add(m["id"])

    for group_id, fold in container_folds.items():
        for market_id in fold["market_ids"]:
            grouped_market_ids.add(market_id)
        entries = fold["entries"][:CONTAINER_FOLD_CARD_ROWS]
        representative = _pool_by_group.get(group_id, {})
        feed_items.append({
            # Deliberately `market`, not a new row type. `propStripAdmission`
            # fails closed on a type it does not know, so a fresh one would have
            # dropped every folded card instead of rendering it — the same trap
            # the exact-score ladders had to route around (UX-1052 item 2).
            "type": "market",
            "market": {
                # The LEADING MEMBER, not the parent. The card is a link, and
                # the parent field row is the one place these prices are wrong
                # (#4163: 0.000000 for an 83% leader), so a tap must not land
                # there. The leader's own market page says the same thing about
                # the same field and says it correctly.
                "id": entries[0]["market_id"],
                "name": fold["title"],
                "source": (fold["sources"] or [None])[0],
                "category": representative.get("category"),
                "sport": representative.get("sport"),
                "outcomes": [
                    {
                        "id": e["market_id"],
                        "name": e["name"],
                        "probability": e["probability"],
                        "american_odds": probability_to_american(e["probability"]),
                        "market_id": e["market_id"],
                        "market_name": fold["title"],
                        "group_id": group_id,
                        "source": e["source"],
                    }
                    for e in entries
                ],
            },
        })

    for group_key, group_markets in stat_prop_groups.items():
        if len(group_markets) < 2:
            continue
        for gm in group_markets:
            grouped_market_ids.add(gm["id"])
        first = group_markets[0]
        feed_items.append({
            "type": "stat_prop",
            "group_key": group_key,
            "player_name": first.get("player_name", ""),
            "stat_category": first.get("stat_category", ""),
            "lines": [
                {
                    "id": gm["id"],
                    "name": gm["name"],
                    "probability": gm["outcomes"][0]["probability"] if gm.get("outcomes") else None,
                    "threshold_value": gm.get("threshold_value", 0),
                    "threshold_direction": gm.get("threshold_direction", "above"),
                    "source": gm.get("source", ""),
                }
                for gm in group_markets
            ],
            "market_count": len(group_markets),
        })

    for group_key, group_markets in playoff_groups.items():
        if len(group_markets) < 2:
            continue
        for gm in group_markets:
            grouped_market_ids.add(gm["id"])
        first = group_markets[0]
        feed_items.append({
            "type": "playoff_progression",
            "group_key": group_key,
            "entity_name": first.get("team_name", ""),
            "stages": [
                {
                    "id": gm["id"],
                    "name": gm["name"],
                    "stage_name": gm.get("stage_name", ""),
                    "stage_order": gm.get("stage_order", 0),
                    "probability": gm["outcomes"][0]["probability"] if gm.get("outcomes") else None,
                    "source": gm.get("source", ""),
                }
                for gm in group_markets
            ],
            "market_count": len(group_markets),
        })

    for tournament_key, grid in placement_groups.items():
        # The grid CONSUMES its markets: leaving them ungrouped would put the
        # five cards back underneath the thing built to replace them.
        for mid in grid["market_ids"]:
            grouped_market_ids.add(mid)
        feed_items.append({
            "type": "placement_grid",
            "group_key": f"placement:{tournament_key}",
            "title": grid["tournament"],
            "columns": grid["columns"],
            # The card shows a readable field and says how deep the real one is.
            "rows": grid["rows"][:PLACEMENT_GRID_FEED_ROWS],
            "row_total": grid["row_total"],
            "market_count": len(grid["market_ids"]),
            "sources": grid["sources"],
        })

    def _group_title(outcomes: list[dict], scope: str) -> str:
        # #1102: build a context-carrying title from the parent market name
        # (strip the specific numeric threshold, preserve case for the entity),
        # falling back to the shared stem for legacy/context-free groups.
        market_name = (outcomes[0].get("market_name") or "").strip()
        if market_name:
            title = re.sub(
                r"\$?\b[\d,]+(?:\.\d+)?\+?\b\s*(?:°[FCK]|%|points?|goals?|runs?|yards?)?",
                "",
                market_name,
            )
            title = re.sub(r"\s{2,}", " ", title).strip(" :–-·?")
            if not title:
                title = market_name
            return title
        return scope.replace("#", "").strip()

    for scope, outcomes in exact_score_groups.items():
        if len(outcomes) < 2:
            continue
        for o in outcomes:
            grouped_outcome_ids.add(o["id"])
        feed_items.append({
            "type": "threshold",
            # UX-1052 item 2 — the discriminator the renderer reads. Kept
            # inside the `threshold` row type on purpose: the strip's
            # fail-closed admission (`propStripAdmission`) refuses any row type
            # it does not recognise, so a brand-new type would have silently
            # dropped every exact-score card instead of relabelling it.
            "kind": "exact_score",
            "group_key": f"exact_score:{scope}",
            "title": _group_title(outcomes, scope),
            "points": [
                {
                    "id": o["id"],
                    "name": o["name"],
                    "probability": o.get("probability"),
                    # The rung label IS the outcome. No threshold is claimed.
                    "label": o["score_label"],
                    "threshold_value": 0,
                    "threshold_unit": "",
                    "threshold_direction": "exact",
                }
                for o in outcomes
            ],
            "outcome_count": len(outcomes),
        })

    for scope, outcomes in threshold_groups.items():
        if len(outcomes) < 2:
            continue
        for o in outcomes:
            grouped_outcome_ids.add(o["id"])
        feed_items.append({
            "type": "threshold",
            "kind": "threshold",
            "group_key": f"threshold:{scope}",
            "title": _group_title(outcomes, scope),
            "points": [
                {
                    "id": o["id"],
                    "name": o["name"],
                    "probability": o.get("probability"),
                    "threshold_value": o.get("threshold_value", 0),
                    "threshold_unit": o.get("threshold_unit", ""),
                    "threshold_direction": o.get("threshold_direction", "above"),
                }
                for o in outcomes
            ],
            "outcome_count": len(outcomes),
        })

    # #2710 — DROP THE PRICELESS ONES BEFORE TRUNCATING, NOT AFTER.
    #
    # Alex, on mobile /sports: "every outcome is a dash … a card with no number
    # is not shown." A market whose outcomes are all unpriced (or absent
    # entirely) renders a full card reading "No outcomes available" or a column
    # of dashes. Measured on the served payload at the page's own limit of 20 on
    # 2026-09-03: 2 of 20 rows carried `outcomes: []`.
    #
    # The filter goes HERE, above the slice, because the slice is what makes it
    # worth doing: dropping these after `[:limit]` would leave the reader with
    # 18 cards, while dropping them before backfills the two slots from the
    # `limit * 5` rows already loaded. Same reason #2789 sorted above its own
    # truncation rather than below it.
    #
    # `status` is filtered to active/open at the top of this route, so there is
    # no settled arm to preserve here — an unpriced open market has nothing to
    # put on a card. (The Discover futures arm keeps a zero-outcome card when it
    # carries an authoritative result; that rule lives in
    # `contracts/feed_card_admission.json` and governs a different endpoint.)
    ungrouped = select_ungrouped_markets(market_dicts, grouped_market_ids, limit)

    for m in ungrouped:
        feed_items.append({
            "type": "market",
            "market": {
                "id": m["id"],
                "name": m["name"],
                "source": m["source"],
                "category": m.get("category"),
                "sport": m.get("sport"),
                # #2789: leader-first BEFORE the truncation. `FuturesMarket.outcomes`
                # declares no `order_by=`, so `m["outcomes"]` arrives in whatever order
                # the selectinload returned, and taking five off the front of that is a
                # uniform random sample the card then stamps `1 2 3 4 5` on. Measured on
                # the live /sports shape: 0 of 5 five-outcome cards led with their
                # favourite, and the 192-golfer Winner market shipped a top row of 0.09%
                # while the true leader (11.8%) was not on the card at all.
                "outcomes": leader_first_outcomes(m["outcomes"])[:5],
            },
        })

    payload = {
        "feed": feed_items[:limit],
        # #4153: a folded container group is a GROUPED row that rides the
        # `market` type for the renderer's sake (see the fold above). Counting
        # it by its type would file it as ungrouped and understate the grouping
        # by exactly the thing this endpoint was just taught to do.
        "total_grouped": len(
            [f for f in feed_items if f["type"] != "market"]
        ) + len(container_folds),
        "total_ungrouped": len(ungrouped),
        "group_counts": {
            "stat_prop": len(stat_prop_groups),
            "playoff_progression": len(playoff_groups),
            "threshold": len(threshold_groups),
            "exact_score": len(exact_score_groups),
            "placement_grid": len(placement_groups),
            "container_field": len(container_folds),
        },
    }

    # An EMPTY feed must never become shared truth for 3 minutes — the same
    # contract the feed pre-warm enforces (Queue 283 / C80). A transient empty
    # read published here would be served to everyone until it expired, which is
    # strictly worse than the 1-second build it replaced.
    if payload["feed"]:
        await _publish_grouped_feed_cache(_cache_key, payload)

    return payload


@router.get("/multi-history")
async def get_multi_market_history(
    market_ids: str = Query(..., description="Comma-separated market IDs to aggregate"),
    hours: int = Query(168, description="Hours of history (default 7 days)"),
    top_n: int = Query(10, description="Number of top outcomes to return (default 10, max 50)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated historical odds across multiple markets (cross-source).

    Merges snapshots from multiple market IDs (e.g., Kalshi + Polymarket + Odds API
    for the same stage) into a single timeline. Outcomes are matched across markets
    by team_id or normalized name, and probabilities are averaged per time bucket.

    Returns the same shape as the single-market history endpoint for drop-in compatibility.
    """
    # Parse market IDs
    try:
        parsed_ids = [int(x.strip()) for x in market_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="market_ids must be comma-separated integers")

    if not parsed_ids:
        raise HTTPException(status_code=400, detail="At least one market_id is required")

    # Single market: delegate to the standard endpoint logic.
    #
    # EVERY PARAMETER RESOLVED, and `outcome_id`/`champion` are why this reads
    # verbose (#6838). A direct Python call gets the UNRESOLVED ``Query``
    # default object, which is not None and is TRUTHY, so `if outcome_id:` took
    # the single-outcome branch and filtered the chart to `[Query(...)]` — an id
    # no column can be compared against. Measured on production 2026-09-18:
    # `/api/futures/multi-history?market_ids=7&hours=168` **500s**, and a league
    # stage tab whose stage carries exactly one market is the reader who gets it
    # (this route is the ONLY path those tabs use). `champion` has carried a
    # defensive coercion inside the handler for the same reason; `outcome_id`
    # never did, and coercing there would hide the next caller's version of this
    # rather than fix this one.
    if len(parsed_ids) == 1:
        return await get_futures_history(
            parsed_ids[0],
            outcome_id=None,
            hours=hours,
            top_n=top_n,
            champion=None,
            db=db,
        )

    # Load all markets with their outcomes
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id.in_(parsed_ids))
    )
    markets = list(result.scalars().unique().all())

    if not markets:
        raise HTTPException(status_code=404, detail="No markets found")

    # Use the first market for metadata
    primary_market = markets[0]

    # Merge outcomes across markets by team_id or normalized name
    # merge_key -> {name, outcome_ids: [int], current_probabilities: [float]}
    #
    # #6641 — one condition, one line, applied INSIDE the per-market loop so a
    # rung on market A can never justify dropping a leg on market B (the
    # helper's scoping rule). Converted alongside the file's other three chart
    # readers; leaving one of the four serving the leg is how the class
    # survived on `/probability-timeline` after the board was fixed.
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

    merged_outcomes: dict[str, dict] = {}
    for market in markets:
        for outcome in drop_duplicate_legs(
            market.outcomes, lambda o: o.external_id
        ):
            merge_key = _progression_merge_key(outcome)
            if merge_key not in merged_outcomes:
                merged_outcomes[merge_key] = {
                    "name": outcome.name,
                    "outcome_ids": [],
                    "current_probabilities": [],
                    "changes_24h": [],
                }
            entry = merged_outcomes[merge_key]
            entry["outcome_ids"].append(outcome.id)
            if outcome.current_probability is not None:
                entry["current_probabilities"].append(float(outcome.current_probability))
            if outcome.probability_change_24h is not None:
                entry["changes_24h"].append(float(outcome.probability_change_24h))

    # Sort by average current probability to pick top N
    # Track merge_key alongside each entry for later lookup
    sorted_merged: list[tuple[str, dict]] = sorted(
        merged_outcomes.items(),
        key=lambda kv: mean(kv[1]["current_probabilities"]) if kv[1]["current_probabilities"] else 0,
        reverse=True,
    )

    capped_n = min(top_n, 50)
    top_entries = sorted_merged[:capped_n]

    all_outcome_ids = []
    for _, entry in sorted_merged:
        all_outcome_ids.extend(entry["outcome_ids"])

    if not all_outcome_ids:
        return {
            "market_id": primary_market.id,
            "market_name": primary_market.name,
            "hours": hours,
            "outcomes": [],
            "round_boundaries": None,
            "leaderboard": None,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Fetch all snapshots
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    snap_result = await db.execute(snapshot_query)
    # #5898, and this endpoint is the sharper half of it. It merges outcomes
    # ACROSS source markets and averages every book's row at one timestamp into
    # one consensus point, so a refuted Polymarket row here does not just draw a
    # false line of its own — it pulls the blended line toward a number our own
    # ladder refuses to print. The filter keys on each row's own `bookmaker`
    # exactly so the honest contributors at that timestamp survive it.
    _multi_outcomes = [o for m in markets for o in m.outcomes]
    _multi_field_ids = _exclusive_field_outcome_ids(markets)
    snapshots = _drop_unsupported_snapshot_points(
        list(snap_result.scalars().all()), _multi_outcomes, _multi_field_ids
    )

    # ── UX-1052 item 7 — THE SAME SPARSE-WINDOW WIDENING ITS SIBLING HAS ──
    #
    # Alex, on the MLB league page: the chart's "Division" tab says "Limited
    # price history available". Measured on production 2026-09-03, that claim
    # was an artefact of THIS endpoint, not of the data:
    #
    #   GET /api/futures/multi-history?market_ids=<13 division markets>&hours=168
    #       → 50 outcomes, 0 history points, every one
    #   GET /api/futures/199075/history?hours=168   (one of those 13)
    #       → 5,065 history points
    #
    # `get_futures_history` widens a sparse window (`_EXTEND_TIERS`: under 20
    # snapshots → 30 days, under 10 → 90 days) precisely because slowly-polled
    # futures carry only a handful of points in seven days. This path never
    # learned it, so the multi-market tabs — which are the ONLY way a league
    # page charts a stage — went dark while the single-market page charted the
    # very same market fine. Same tiers, same "only if it actually finds more"
    # rule, so a genuinely empty stage still reports empty.
    if len(snapshots) < _EXTEND_TIERS[0][0]:
        for threshold, extended_hours in _EXTEND_TIERS:
            if len(snapshots) >= threshold or extended_hours <= hours:
                continue
            ext_result = await db.execute(
                select(FuturesOddsSnapshot)
                .where(
                    FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
                    FuturesOddsSnapshot.captured_at
                    >= datetime.now(timezone.utc) - timedelta(hours=extended_hours),
                )
                .order_by(FuturesOddsSnapshot.captured_at)
            )
            extended = _drop_unsupported_snapshot_points(
                list(ext_result.scalars().all()), _multi_outcomes, _multi_field_ids
            )
            if len(extended) > len(snapshots):
                snapshots = extended
                hours = extended_hours

    # Build outcome_id -> merge_key lookup
    oid_to_merge_key: dict[int, str] = {}
    for mk, entry in merged_outcomes.items():
        for oid in entry["outcome_ids"]:
            oid_to_merge_key[oid] = mk

    # Group snapshots: merge_key -> captured_at -> [probabilities]
    # This naturally averages across sources since different outcome_ids
    # from different source markets map to the same merge_key
    merged_time_groups: dict[str, dict[datetime, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for snap in snapshots:
        if snap.probability is not None:
            mk = oid_to_merge_key.get(snap.outcome_id)
            if mk is None:
                continue
            merged_time_groups[mk][snap.captured_at].append(float(snap.probability))

    # Build aggregated history per merged outcome
    outcome_history_list = []

    for mk, entry in top_entries:
        synthetic_id = entry["outcome_ids"][0]
        time_groups = merged_time_groups.get(mk, {})

        history = []
        for captured_at in sorted(time_groups.keys()):
            probs = time_groups[captured_at]
            avg_prob = mean(probs)
            history.append({
                "timestamp": captured_at.isoformat(),
                "probability": avg_prob,
                "american_odds": probability_to_american(avg_prob) if avg_prob > 0 else None,
                "bookmaker": "consensus",
            })

        elim = _detect_elimination(history)
        outcome_history_list.append({
            "outcome_id": synthetic_id,
            "name": entry["name"],
            "history": history,
            "eliminated": elim["eliminated"],
            "eliminated_at": elim["eliminated_at"],
        })

    # Round boundaries from primary market
    explicit_boundaries = _derive_round_boundaries(primary_market.market_metadata)
    round_boundaries = _detect_round_boundaries_from_eliminations(
        {oh["outcome_id"]: oh for oh in outcome_history_list}, explicit_boundaries
    )

    return {
        "market_id": primary_market.id,
        "market_name": primary_market.name,
        "hours": hours,
        "outcomes": outcome_history_list,
        "round_boundaries": round_boundaries,
        "leaderboard": (primary_market.market_metadata or {}).get("leaderboard"),
    }


def _as_float(value) -> Optional[float]:
    """`Numeric` columns arrive as `Decimal`; the price predicates take floats.

    None-preserving on purpose: ``is_lone_ask_on_empty_book`` distinguishes a
    missing book from a zero bid, and coercing None to 0.0 here would hand it a
    bid nobody recorded and call it nobody bidding.
    """
    return None if value is None else float(value)


def _exclusive_field_outcome_ids(markets) -> set[int]:
    """Outcome ids belonging to markets the classifier PROVED are single-winner fields.

    #6846's chart arm needs the field verdict per POINT, and a snapshot row knows
    only its ``outcome_id`` — so the market-level verdict is resolved to a set of
    outcome ids once, by the caller that still has the markets in hand, and the
    filter below does a set membership test per row.

    Accepts one market or many: ``/multi-history`` and the league timeline chart
    several markets at once, and each is judged on its OWN shape, so a proved
    field's legs are screened while a sibling binary's are not. Fails closed on a
    market missing either column (``getattr``), which serves the point.
    """
    ids: set[int] = set()
    for market in markets:
        if market is None:
            continue
        if market_is_proved_exclusive_field(
            getattr(market, "market_type", None),
            getattr(market, "market_metadata", None),
        ):
            ids.update(o.id for o in getattr(market, "outcomes", ()) or ())
    return ids


def _drop_unsupported_snapshot_points(
    snapshots: list, outcomes, exclusive_field_outcome_ids: set | None = None
) -> list:
    """Remove the chart points whose own row says nothing supported that price (#5898).

    THE LADDER AND THE CHART MUST NOT DISAGREE. ``/api/futures/{id}`` withholds an
    outcome's price when no book and no trade supports it (#5611), when the
    venue's newest trade refutes the midpoint (#5876), or when the price is the
    midpoint of a book with nothing in it (#6757). Until this filter existed
    the chart above that ladder still plotted the refused value as the series'
    last point, so a reader who ticked a row displaying ``—`` was shown the number
    the table had just declined to state.

    PER POINT, NOT PER SERIES, and that is the whole design. These series are
    mixtures: Ceará's 812 served points on 8641774 split 537 honest (0.0045–0.1025,
    agreeing with a ~0.002 trade) against 275 fabricated (0.1025–0.4930), and the
    fabricated ones bunch at the right-hand edge. Withholding the series would
    delete a real curve to remove a false tail; withholding the point leaves the
    curve and takes the tail. Measured on production 2026-09-13 20:51Z.

    NO EXTRA QUERY. Every column the predicate reads is already on the snapshot
    rows the handler fetched, and the grade is already on the outcomes it loaded,
    so this is one pass over data in hand — the reason it can sit on two endpoints
    without a latency argument.

    AN OUTCOME WE DID NOT LOAD IS LEFT ALONE. ``snapshot_price_is_unsupported``
    treats a null ``resolution_source`` as "ungraded, therefore a candidate", so
    defaulting an unknown outcome to ``None`` would make ignorance a reason to
    drop a reader's point. Unknown ids keep every point instead; the callers below
    always load the outcomes whose ids they queried, so this is a guard against a
    future caller, not a live branch.
    """
    # #6532: the verdict rides along with the grade because the third arm needs
    # BOTH — a graded winner keeps every point whatever its stale book says, and
    # only an affirmative loser is asked the question at all. One dict, so an
    # outcome we did not load still fails the `in` test above and keeps its points.
    grades = {o.id: (o.resolution_source, o.is_winner) for o in outcomes}
    # #6846. Same premise as #6757's arm below, one rule further on: without this
    # the 2027 Masters table would print "—" against Ryan Gerard and Tiger Woods
    # while the Probability Trend above them went on drawing those very legs as a
    # flat line at 39%. An id we were given no verdict for is not in the set, so
    # it keeps every point — absence is not evidence, here as everywhere else in
    # this function.
    in_field = exclusive_field_outcome_ids or set()
    kept = []
    for snapshot in snapshots:
        if snapshot.outcome_id in grades:
            resolution_source, is_winner = grades[snapshot.outcome_id]
            # #6757. THE LADDER AND THE CHART MUST NOT DISAGREE, which is this
            # function's whole premise, so the arm lands here in the same change
            # that adds `_empty_book_outcome_ids` to the detail payload. Without it
            # that fix would rebuild #5898's defect with its own repair:
            # `/futures/57777176` would print "—" against Chicago Bulls in the
            # table while the graph above drew that row's five stored points at
            # 0.485 on a 0.0100/0.9600 book.
            #
            # INSIDE THIS BRANCH AND GATED ON THE GRADE, both deliberately, and an
            # earlier revision of this arm sat above it and was wrong twice over.
            # Outside the branch it withheld points from an outcome the caller did
            # not load, which the docstring above refuses on purpose; ungated it
            # took the tail off a settled series, and `_REFUSED_TAIL` in #5898's
            # own tests is exactly that shape — a champion whose journey ran
            # through midpoints of a 0.002/0.938 book before it was decided.
            # Settled means settled: the completed journey is shown whole, and the
            # ladder's arm exempts the grade for the same reason.
            #
            # A RETRACTION IS NOT A GRADE (#6757 residual). `ungradeable_result`
            # asserts no result, so there is no result for the exemption to
            # protect — only the empty-book midpoint it was written to withhold.
            # `row_carries_a_verdict` is #6876's canonical spelling of that
            # question, already asked by `needs_trade_evidence` and
            # `price_refuted_by_live_book` two calls below; asking it here too is
            # what stops the ladder, the chart and the price rails disagreeing
            # about one row. The exemption is only WITHDRAWN: the retracted row
            # is then judged by the same empty-book predicate as an ungraded one.
            if not row_carries_a_verdict(resolution_source) and is_empty_book_midpoint(
                _as_float(snapshot.probability),
                _as_float(getattr(snapshot, "yes_bid", None)),
                _as_float(getattr(snapshot, "yes_ask", None)),
            ):
                continue
            if snapshot_price_is_unsupported(
                snapshot.bookmaker,
                resolution_source,
                _as_float(snapshot.probability),
                _as_float(getattr(snapshot, "yes_bid", None)),
                _as_float(getattr(snapshot, "yes_ask", None)),
                _as_float(getattr(snapshot, "last_price", None)),
                is_winner=is_winner,
                in_exclusive_field=snapshot.outcome_id in in_field,
            ):
                continue
        kept.append(snapshot)
    return kept


async def _unsupported_price_outcome_ids(
    db: AsyncSession, market: FuturesMarket
) -> set[int]:
    """Which of this market's outcomes serve a price no book and no trade supports.

    #5611. The screen is done on the outcome rows first — source, grade, bid and
    ask are all in memory — so a market with no candidate outcomes costs NOTHING
    here and never reaches the snapshot table. Measured on production
    2026-09-13, only 47 open Kalshi markets hold a leg this can fire on.

    The trade read is scoped to Kalshi's own snapshots, matching
    ``lone_ask_on_empty_book_sql``, which carries the same bookmaker term and
    says why: this is Kalshi's price policy and Polymarket's rule for these
    columns is a different one (gotcha #19). It rides
    ``ix_futures_odds_snapshots_outcome_bookmaker_captured``.

    Absence fails OPEN. An outcome with no Kalshi snapshot is left exactly as it
    is served today — see ``price_is_unsupported`` for why "we never looked" and
    "we looked and it never traded" may not be collapsed into one answer.

    #6846 WIDENS THE SCREEN FOR ONE CLASS OF MARKET AND NOTHING ELSE. The shape
    verdict is read ONCE per market, not once per leg — it is a property of the
    market — and when the classifier PROVES a single-winner partition the
    ask-only bound is dropped for every leg of it. Measured on production
    2026-09-18: of 21,274 proved exclusive Kalshi fields, 654 hold a leg this
    widening fires on; 548 of those 654 already sum above 100%, 49 seat an
    ask-only leg above their best two-sided book, and the touched fields sum to
    a mean of 1.97. It fires on distortion, not on breadth.

    TWENTY OF THE 654 LOSE EVERY PRICED LEG, and that is the correct outcome
    rather than a cost to be engineered around: a field whose only priced legs
    are all untaken offers has no price discovery to show, and Alex's standing
    rule is that a number which cannot be shown honestly leaves the space empty.
    The legs keep their names, exactly as the 33 never-priced legs on the
    specimen market already render.
    """
    # `getattr` for the same reason the outcome reads below use it: a caller may
    # hand this a market object that never loaded these columns, and an absent
    # attribute must read as "not proved" rather than raise or, worse, be taken
    # for evidence. The gate fails closed on None, so the leg is served.
    in_exclusive_field = market_is_proved_exclusive_field(
        getattr(market, "market_type", None),
        getattr(market, "market_metadata", None),
    )
    # 🔴 #7747 — A SECOND ARM SHARES THIS CANDIDATE LIST AND THIS SNAPSHOT READ.
    # `price_is_an_unbacked_ask` asks a different question of the same three
    # columns (does the book LOCATE the price, not does it REFUTE it) and needs
    # the same one thing from the snapshot table: the newest Kalshi trade. It is
    # unioned in here rather than given its own `_..._outcome_ids` helper so the
    # page still issues ONE trade query per market — the arm adds 38 candidate
    # legs across 34 boards on production, so the widened `IN` list is noise
    # against the 429 the sibling already sends.
    candidates = [
        o
        for o in market.outcomes
        if needs_trade_evidence(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            in_exclusive_field=in_exclusive_field,
        )
        or needs_unbacked_ask_evidence(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_probability", None)),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            in_exclusive_field=in_exclusive_field,
            volume_24h=getattr(o, "volume_24h", None),
            volume_24h_at=getattr(o, "volume_24h_at", None),
            last_seen_at=getattr(o, "last_updated", None),
        )
    ]
    if not candidates:
        return set()

    candidate_ids = [o.id for o in candidates]
    newest = (
        select(
            FuturesOddsSnapshot.outcome_id,
            func.max(FuturesOddsSnapshot.captured_at).label("captured_at"),
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(candidate_ids),
            FuturesOddsSnapshot.bookmaker == KALSHI_BOOKMAKER,
        )
        .group_by(FuturesOddsSnapshot.outcome_id)
        .subquery()
    )
    rows = await db.execute(
        select(
            FuturesOddsSnapshot.outcome_id,
            func.max(FuturesOddsSnapshot.last_price),
        )
        .join(
            newest,
            and_(
                FuturesOddsSnapshot.outcome_id == newest.c.outcome_id,
                FuturesOddsSnapshot.captured_at == newest.c.captured_at,
            ),
        )
        .where(FuturesOddsSnapshot.bookmaker == KALSHI_BOOKMAKER)
        .group_by(FuturesOddsSnapshot.outcome_id)
    )
    # Two Kalshi snapshots can share one `captured_at`; the aggregate above keeps
    # the HIGHEST last_price among them, which is the fail-open direction — any
    # trade evidence at all leaves the price on the page.
    latest_trade = {outcome_id: price for outcome_id, price in rows.all()}

    return {
        o.id
        for o in candidates
        if price_is_unsupported(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            _as_float(latest_trade.get(o.id)),
            has_trade_evidence=o.id in latest_trade
            and latest_trade[o.id] is not None,
            in_exclusive_field=in_exclusive_field,
        )
        # #7747. An OR, so the two arms are independent screens over one
        # candidate list: a leg either arm refuses is withheld, and neither can
        # acquit what the other caught.
        or price_is_an_unbacked_ask(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_probability", None)),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            _as_float(latest_trade.get(o.id)),
            has_trade_evidence=o.id in latest_trade
            and latest_trade[o.id] is not None,
            in_exclusive_field=in_exclusive_field,
            # `getattr` throughout: a caller may hand this a market whose
            # outcomes never loaded these columns, and an absent stamp must read
            # as "do not withhold" rather than raise.
            volume_24h=getattr(o, "volume_24h", None),
            volume_24h_at=getattr(o, "volume_24h_at", None),
            last_seen_at=getattr(o, "last_updated", None),
        )
    }


async def _refuted_midpoint_outcome_ids(
    db: AsyncSession, market: FuturesMarket
) -> set[int]:
    """Which of this market's outcomes serve a midpoint the newest trade refutes.

    #5876, the Polymarket sibling of ``_unsupported_price_outcome_ids``. Same
    two-step shape for the same reason: the fabricated-midpoint screen is done on
    the outcome rows first, so a market holding no candidate costs nothing here
    and never reaches the snapshot table.

    THE NEWEST SNAPSHOT, NOT THE BEST ONE, AND THAT IS THE WHOLE RULE. An
    aggregate over an outcome's history reads its liquid past: ``max(last_price)``
    across market 8641774's 2,386 snapshots per outcome returns 0.92–0.96 and
    would spare every leg on the page, while the newest rows read 0.0040. So the
    LATERAL takes one row per outcome, ordered by ``captured_at`` — it rides
    ``ix_futures_odds_snapshots_outcome_bookmaker_captured``, the same index the
    Kalshi arm uses, one seek per candidate.

    Ties on ``captured_at`` resolve to the trade CLOSEST to the served price,
    which is the fail-open direction: if two snapshots share a microsecond, the
    one most likely to support what we print is the one that gets to speak.

    🔴 THE BOOKMAKER IS READ OFF THE MARKET, NOT HARDCODED (#7222), AND THIS LINE
    IS THE WHOLE REASON THE KALSHI HALF OF THE PREDICATE WOULD OTHERWISE BE INERT.
    Both queries below named ``POLYMARKET_BOOKMAKER`` literally, so widening
    ``needs_trade_disconfirmation`` to Kalshi would have produced Kalshi candidates
    and then looked for their trades in Polymarket's snapshots, found none, and
    served every one of them unchanged — a fix that passes its unit tests and
    changes nothing a reader sees. The screen and the read now take their venue
    from the same place, and ``MIDPOINT_TRADE_SOURCES`` is the membership test both
    sides share, so a third venue cannot be added to one half alone.
    """
    venue = (market.source or "").strip().lower()
    if venue not in MIDPOINT_TRADE_SOURCES:
        return set()

    candidates = [
        o
        for o in market.outcomes
        if needs_trade_disconfirmation(
            market.source,
            o.resolution_source,
            _as_float(o.current_probability),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
        )
    ]
    if not candidates:
        return set()

    candidate_ids = [o.id for o in candidates]
    newest = (
        select(
            FuturesOddsSnapshot.outcome_id,
            func.max(FuturesOddsSnapshot.captured_at).label("captured_at"),
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(candidate_ids),
            FuturesOddsSnapshot.bookmaker == venue,
        )
        .group_by(FuturesOddsSnapshot.outcome_id)
        .subquery()
    )
    rows = await db.execute(
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.last_price,
        )
        .join(
            newest,
            and_(
                FuturesOddsSnapshot.outcome_id == newest.c.outcome_id,
                FuturesOddsSnapshot.captured_at == newest.c.captured_at,
            ),
        )
        .where(FuturesOddsSnapshot.bookmaker == venue)
    )
    served = {o.id: _as_float(o.current_probability) for o in candidates}
    latest_trade: dict[int, float] = {}
    for outcome_id, last_price in rows.all():
        price = _as_float(last_price)
        if price is None:
            continue
        target = served.get(outcome_id)
        held = latest_trade.get(outcome_id)
        if held is None or (
            target is not None and abs(price - target) < abs(held - target)
        ):
            latest_trade[outcome_id] = price

    return {
        o.id
        for o in candidates
        if midpoint_refuted_by_last_trade(
            market.source,
            o.resolution_source,
            _as_float(o.current_probability),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
            latest_trade.get(o.id),
            has_trade_evidence=o.id in latest_trade,
        )
    }


def _book_refuted_outcome_ids(market: FuturesMarket) -> set[int]:
    """Which of this market's outcomes serve a price their own book prices out.

    #6532, the third arm, and the only one of the three that costs NOTHING. Its
    two siblings each need the newest snapshot to answer "did this ever trade" or
    "what did it last trade at", so each runs a query. This one reads the served
    price against the book columns sitting on the same row — three fields of one
    write — so it is a pass over outcomes already in memory, no query, no index,
    and synchronous for that reason rather than by omission.

    The rule and everything measured about it are in
    :func:`app.utils.futures_unsupported_price.price_refuted_by_live_book`,
    including why a graded winner is never touched and why a graded loser is asked
    only half the predicate.
    """
    return {
        o.id
        for o in market.outcomes
        if price_refuted_by_live_book(
            market.source,
            o.resolution_source,
            o.is_winner,
            _as_float(o.current_probability),
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
        )
    }


def _empty_book_outcome_ids(market: FuturesMarket) -> set[int]:
    """Which of this market's outcomes price a book with nothing in it (#6757).

    WHAT A READER SAW. ``/futures/57777176`` — "NBA: Steph Curry Next Team" —
    printed a confident percentage against all 30 teams and not one of them was
    a traded price: sixteen clubs read **48%**, the ladder summed to **1112.5%**,
    and every row had been written in one batch six weeks earlier
    (``2026-08-01 00:19:45.171081``, identical microsecond ⇒ one batch writer).
    The same shape answers a real election on ``/futures/110297`` — "Who will win
    the 2026 Colombia Senate election? Opposition 49.7% / Government Alliance
    49.1%" — and prices five mutually exclusive CPI rungs at 50% EACH on
    ``/futures/109681``.

    THE RULE IS NOT NEW AND IS NOT RE-DERIVED HERE. This is
    :func:`_leg_prices_an_empty_book`, the same object the grouped feed already
    calls at its one shipped call site, which is in turn #5247's measured
    predicate wearing #6727's spread form. The defect was never the rule; it was
    that this route never asked it. Three read surfaces refuse these rows today
    — ``game-markets``, the search slice and the grouped feed — so the strip and
    the page a reader opens FROM the strip disagreed about the same row in the
    same hour, which is the whole of #6757.

    WITHHELD, NOT SKIPPED, and that is the difference from the grouped-feed call
    site rather than an inconsistency with it. The strip drops the leg from a
    five-row card; this page IS the full field, and dropping sixteen clubs out of
    "Steph Curry Next Team" would answer a question nobody asked. The price is
    nulled and the row stays — the contract the three arms above already keep.

    A GRADED ROW IS EXEMPT, and that exemption is this function's and NOT the
    shared predicate's. ``_leg_prices_an_empty_book`` reads three price columns
    and knows nothing about settlement, which is right for the strip; here it
    would mean withholding the price of a row the venue has already decided, and
    #6532 states the cost of that plainly — withholding a settled row deletes a
    result. Settled means settled, so the grade is checked HERE, at the call
    site, rather than by teaching the shared rule a fourth condition its three
    other consumers never asked for. Measured on production 2026-09-17: 58 of the
    4,192 legs this arm reaches are graded, so the exemption costs the ship
    nothing and buys back the one class where withholding does harm.

    NO QUERY, like :func:`_book_refuted_outcome_ids` directly above and for the
    same reason — the columns it reads are on rows already in memory.

    MEASURED BEFORE SHIPPING (production, 2026-09-17): 4,192 legs across 2,402
    open markets. 1,973 of those markets are left with no priced leg at all, and
    1,910 of THOSE carry one or two legs — an untraded binary whose only book is
    empty, which is exactly the row that should print nothing rather than a
    manufactured coin flip. Eleven markets with six or more legs blank entirely.

    A RETRACTION IS NOT A GRADE, and this is the one refinement the exemption
    has needed since it shipped. ``ungradeable_result`` is the no-result
    sentinel (CAL-P056): a leg carrying it has been declared unknowable, not
    decided, so there is no result for the exemption to protect — only the
    empty-book midpoint it was written to withhold. ``/futures/2951399`` printed
    thirteen identical 49s under that badge on an open market resolving in
    2027, ``prices_withheld: 0`` beneath them.

    THE TEST IS NOT WRITTEN HERE. :func:`row_carries_a_verdict` (#6876) is the
    codebase's one spelling of "is there a grade at all", and this route's price
    rails already ask it — ``needs_trade_evidence`` and
    ``price_refuted_by_live_book`` both call it. This arm and the chart arm in
    :func:`_drop_unsupported_snapshot_points` call the same function so the
    ladder, the graph and the rails cannot read one row three ways. Every other
    non-null source keeps the exemption exactly as before: whether a terminal
    no-winner source such as ``all_losers`` should also yield is a settlement
    question, and the tests pin today's answer so it is changed visibly.
    """
    return {
        o.id
        for o in market.outcomes
        if not row_carries_a_verdict(getattr(o, "resolution_source", None))
        and _leg_prices_an_empty_book(o)
    }


def _unlocated_in_broken_field_outcome_ids(
    market: FuturesMarket, already_withheld: set[int]
) -> set[int]:
    """Which outcomes price a book that bounds nothing, inside a field that cannot be one (#7059).

    The fifth arm, and the second one to cost no query: like
    :func:`_book_refuted_outcome_ids` it reads columns already on rows in memory.

    The rule, the specimen and every number behind it are in
    :func:`app.utils.futures_unsupported_price.price_is_unlocated_in_broken_field`
    and its field-level half :func:`field_names_two_favourites` — including why the
    recency question is never asked and why both halves are load-bearing.

    ``already_withheld`` IS THE WHOLE REASON THIS ARM TAKES AN ARGUMENT AND THE
    OTHERS DO NOT. Its gate is a fact about the COLUMN A READER SEES, so it has to
    be computed over the legs that survive the four arms above rather than over
    every stored row — "the caller passes the list it will actually print, because
    that is the set whose coherence the page is claiming"
    (``classify_field_openings``). On the specimen this is not academic: Tyson Fury
    stores 0.97 and is ALREADY refused by :func:`_book_refuted_outcome_ids` (he
    serves above his own ask), so counting stored rows would credit the field with a
    favourite no reader is shown. It still names two — Usyk 0.93 and Kabayel 0.87 —
    so the gate holds either way here, but a rule about what a page claims may not
    be measured on rows the page withholds.

    THE ORDER IS THEREFORE FIXED AND ONE-PASS. This arm runs last, over the survivors
    of the other four, and its own refusals do NOT re-open the gate. Iterating to a
    coherent column would be chasing a sum, which this module does not do
    (gotcha #21, withholding never rewriting); one pass also makes the result
    independent of the order ids happen to arrive in.

    A MARKET WHOSE SHAPE IS NOT PROVED EXCLUSIVE NEVER REACHES THE GATE, and the
    check fails closed on absent metadata exactly as it does at the #6846 call site
    above — ``market_is_proved_exclusive_field`` reads the persisted classifier, not
    ``futures_markets.mutually_exclusive``, which defaults to true and is evidence of
    nothing.
    """
    if not market_is_proved_exclusive_field(
        getattr(market, "market_type", None),
        getattr(market, "market_metadata", None),
    ):
        return set()
    served = [o for o in market.outcomes if o.id not in already_withheld]
    if not field_names_two_favourites(
        [_as_float(getattr(o, "current_probability", None)) for o in served]
    ):
        return set()
    return {
        o.id
        for o in served
        if _as_float(getattr(o, "current_probability", None)) is not None
        and price_is_unlocated_in_broken_field(
            market.source,
            o.resolution_source,
            _as_float(getattr(o, "current_yes_bid", None)),
            _as_float(getattr(o, "current_yes_ask", None)),
        )
    }


async def _withheld_price_outcome_ids(
    db: AsyncSession, market: FuturesMarket
) -> set[int]:
    """Every outcome of this market whose served price is refused, all five arms.

    #6993. THE ARMS WERE ALREADY COMPOSED — in the body of
    :func:`get_futures_market`, where only that route could reach them. The group
    route serves the SAME market's prices and never asked, so one page carried both
    answers at once.

    WHAT A READER SAW. ``/futures/109485`` — "How low will the Nasdaq-100 get in
    2026?" — drew the ``# OR BELOW`` ladder rung **``≤ 24800  100%``** with a full
    green bar, while the "All Outcomes" table BELOW IT ON THE SAME SCREEN folded
    that identical outcome (id ``1597367``) away into "More outcomes (1)" because
    its price is withheld. Detail served ``probability: None`` for the leg; the
    group payload served ``1.0`` for it in the same minute. The ladder is the only
    ladder that draws for a threshold-shaped market — ``ownLadderRungs`` returns
    ``[]`` whenever ``thresholdEntries`` is non-empty — so on exactly this class of
    market the withhold was not merely duplicated, it was BYPASSED.

    ONE HELPER, NOT A FIFTH SPELLING. This is the #6960 lesson applied before the
    second copy exists rather than after: the four arms hang from one hook, so a
    route that serves a price cannot accidentally serve the refused one. Adding an
    arm here reaches every caller, which is the property the in-line union did not
    have.
    """
    ids = await _unsupported_price_outcome_ids(db, market)
    ids |= await _refuted_midpoint_outcome_ids(db, market)
    ids |= _book_refuted_outcome_ids(market)
    ids |= _empty_book_outcome_ids(market)
    # Last, and reading the four above rather than the stored rows: its gate is a
    # fact about the column a reader is actually shown. See the arm's docstring.
    ids |= _unlocated_in_broken_field_outcome_ids(market, ids)
    return ids


@router.get("/{market_id}")
async def get_futures_market(
    market_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information about a specific futures market.

    Returns all outcomes with current and opening odds.
    """
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.sport))
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # The provenance half — which books contributed, and their latest price per
    # outcome — is the whole cost of this endpoint and it is the only half that
    # is cached. `market` and its outcomes were just read fresh above and are
    # formatted below from those rows, so the hero and the outcome ladder cannot
    # be served stale by this cache: they were never in it.
    outcome_ids = [o.id for o in market.outcomes]
    bookmakers = []
    source_breakdown = []
    if outcome_ids:
        bookmakers, source_breakdown = await _load_market_sources(
            db, market_id, outcome_ids
        )

    # Two venues, two price rules, plus one that belongs to neither — ONE set of
    # withheld ids. The first three arms are mutually exclusive by construction,
    # each screening on `market.source`, so their union was a union of disjoint
    # sets and never a precedence question. They stay separate functions because
    # the rules are genuinely different (gotcha #19): Kalshi's asks whether
    # anything supports the price at all, Polymarket's asks whether the newest
    # trade refutes it.
    #
    # #6757's arm BREAKS THAT DISJOINTNESS, DELIBERATELY, so the sentence above is
    # corrected here rather than left to rot. An empty book is an empty book at
    # either venue, so this one screens on no source at all and can name a row one
    # of the others has already named. Nothing downstream has to care: this is a
    # union of ids, an overlap is absorbed by definition, and `prices_withheld`
    # counts ROWS rather than reasons. What it is not is a fourth spelling of the
    # same rule — it is the single predicate three other read surfaces already
    # call, asked on this route for the first time.
    #
    # #6993 lifted this union into `_withheld_price_outcome_ids` so the group
    # route serves the same refusal. The composition is unchanged; it just has a
    # name now, and a second caller.
    unsupported_price_ids = await _withheld_price_outcome_ids(db, market)

    detail = _format_market_detail(market, bookmakers, unsupported_price_ids)
    if len(bookmakers) > 1 and source_breakdown:
        detail["source_breakdown"] = source_breakdown
    return detail


#: How many cards "Games This Week" shows. Was the bare `.limit(20)` on the
#: query itself until #5905/#5918 — see `RELATED_EVENTS_FOLD_HEADROOM`.
RELATED_EVENTS_LIMIT = 20

#: Extra rows fetched so the twin fold has something to spend.
#:
#: The same bargain `teams.py` reasons out for its five-card rail, and it is
#: available here for the same reason: this strip has no `offset` and no
#: cursor, so over-fetching cannot make page one consume rows a page two would
#: then re-serve. `list_events` folds AFTER its limit precisely because it IS
#: offset-paginated; that hazard does not exist on a fixed strip.
#:
#: Folding after a DB limit of 20 would instead spend a card slot on a row it
#: then drops: the three duplicate pairs measured below would leave the reader
#: seventeen games instead of twenty.
RELATED_EVENTS_FOLD_HEADROOM = RELATED_EVENTS_LIMIT


@router.get("/{market_id}/related-events")
async def get_related_events(
    market_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get upcoming and live events related to a futures market.

    Finds events where home or away team has a linked outcome in this market.
    Returns events sorted: live first, then upcoming by commence_time.
    """
    from app.models import Event, Team

    # Load market with outcomes (need team_ids)
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Get all team_ids from linked outcomes
    team_ids = [o.team_id for o in market.outcomes if o.team_id is not None]
    if not team_ids:
        return {
            "market_id": market_id,
            "market_name": market.name,
            "events": [],
        }

    # Build team_id → outcome mapping for context
    team_outcome_map = {}
    for o in market.outcomes:
        if o.team_id:
            team_outcome_map[o.team_id] = {
                "outcome_name": o.name,
                "probability": float(o.current_probability) if o.current_probability is not None else None,
                "american_odds": o.current_american_odds,
                "rank": o.rank,
            }

    # Find events where either team is linked
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=1)  # Include recently completed games
    week_ahead = now + timedelta(days=7)

    # ═══ THIS MARKET'S SPORT IS A CONSTRAINT, NOT A HINT (#2553) ═══
    #
    # `/futures/1` — MLB World Series Winner — served five MLS soccer fixtures
    # under "Games This Week" during the MLB season: D.C. United at FC
    # Cincinnati, CF Montreal at Philadelphia Union, San Diego FC at Orlando
    # City. A reader needs no domain knowledge to see that D.C. United is not in
    # the World Series race.
    #
    # The join above is by `futures_outcomes.team_id`, and it did exactly what
    # it was told: outcome "Cincinnati Reds" carries the team id of FC
    # Cincinnati, "Philadelphia Phillies" carries Philadelphia Union's,
    # "San Diego Padres" carries San Diego FC's. A city name got matched across
    # sports when those outcomes were linked, and 2,762 outcomes site-wide are
    # linked to a team in the wrong sport (measured 2026-09-01). That corruption
    # is the matching layer's to repair and is filed separately — it is NOT
    # hand-patched here, and this route is not the place that would know how.
    #
    # But a futures market's related-games strip has no business showing a
    # fixture from another sport WHATEVER the team link says, and that is a
    # property of this query rather than of the data. So the sport is a WHERE
    # clause now: an MLB market can only surface baseball events, and the day a
    # link is repaired the strip is already correct instead of newly correct.
    #
    # Keyed off `llm_sport_category` through `sport_keys.py`, the single source
    # of truth, rather than `Event.sport_id == market.sport_id` — the market is
    # `baseball_mlb` and its own games arrive under `baseball_mlb` AND
    # `baseball_mlb_preseason`, so an id equality would drop real baseball.
    #
    # FAIL OPEN, NARROWLY. A market with no category, or a category the map does
    # not carry, gets the old behaviour — the alternative is emptying the strip
    # on every non-league market to fix a cross-sport bug, and an absent
    # category is not evidence of a wrong sport.
    sport_prefix = (
        LLM_CATEGORY_TO_SPORT_PREFIX.get(market.llm_sport_category)
        if market.llm_sport_category
        else None
    )
    sport_filters = []
    if sport_prefix:
        sport_filters.append(
            or_(
                Sport.key == sport_prefix,
                # `startswith` and not a hand-built LIKE: the argument is
                # escaped and bound by SQLAlchemy, which is the half of gotcha
                # #45 that bites when a key contains an underscore — and every
                # key here does.
                Sport.key.startswith(f"{sport_prefix}_"),
            )
        )

    events_result = await db.execute(
        select(Event)
        .join(Sport, Sport.id == Event.sport_id)
        .options(selectinload(Event.sport))
        .where(
            or_(
                Event.home_team_id.in_(team_ids),
                Event.away_team_id.in_(team_ids),
            ),
            Event.commence_time.between(week_ago, week_ahead),
            *sport_filters,
        )
        # Live first, then upcoming, then completed — Q438/CERT-1924: through
        # the shared clause, so a row that is live before its own kickoff sorts
        # with the scheduled games it is SERVED as, instead of being promoted
        # above nearer ones and then printed `scheduled` three lines later.
        .order_by(
            live_scheduled_settled_order(now),
            Event.commence_time.asc(),
        )
        .limit(RELATED_EVENTS_LIMIT + RELATED_EVENTS_FOLD_HEADROOM)
    )
    events = list(events_result.scalars().all())

    # ── #5918/#5905: one fixture may not take two slots on this strip ─────────
    #
    # MEASURED ON PRODUCTION 2026-09-14 00:2xZ, `/api/futures/400/related-events`
    # ("La Liga Winner", the page a reader reaches from the La Liga hub). Three
    # pairs, each the same game twice, each exactly three hours apart:
    #
    #     15312069 Sevilla v Barcelona        19:00Z
    #     15307701 Sevilla v Barcelona        22:00Z
    #     15312070 Getafe v Málaga            12:00Z
    #     15307708 Getafe v Malaga            15:00Z
    #     15312067 Celta Vigo v Santander     16:30Z
    #     15307700 Celta Vigo v Santander     19:30Z
    #
    # On the page that reads "Barcelona at Sevilla" on two rows of "Games This
    # Week", three hours apart.
    #
    # THE THREE HOURS ARE THE WHOLE STORY, AND THEY ARE WHY ONE CALL FIXES BOTH
    # HALVES. The second row of each pair is a Kalshi-minted row whose
    # `commence_time` is the market's expected expiration, not kick-off (gotcha
    # #14) — `KALSHI_EXPECTED_EXPIRATION_PAD`, 180 minutes exactly. So the twins
    # are not near-misses a tolerance would have to reach: they are the SAME
    # MINUTE once the pad is subtracted, and they read as different games only
    # because it has not been. `recover_kalshi_occurrence_starts` runs at the
    # top of `fold_twin_events` for exactly this reason, so the fold's
    # same-minute soccer pass can then see one game where the raw columns show
    # two. Neither ran here: every other list surface reaches both through this
    # one call (`list_events`, search, the three league rails, the team rails,
    # the feed) and this strip reached neither.
    #
    # `Event.sport` is eagerly loaded on the query above, which is load-bearing
    # rather than incidental: `loaded_sport_key` answers `None` for an unloaded
    # relationship — deliberately, so the fold never emits IO inside a stage
    # wrapped in a bare `except` — and the soccer pass would then skip every row
    # on a soccer strip while looking like it ran. That is CERT-2805's finding
    # on the league rails, and the test for this change asserts the loader.
    #
    # Ordering is deliberately NOT recomputed. `live_scheduled_settled_order` is
    # a five-group SQL authority (#3946, #3211/D107, CERT-1924) with no Python
    # twin, and hand-rolling one here would make this route a second place that
    # decides rail order — the exact shape CERT-1924 caught on this very
    # endpoint. The survivors keep the order the database gave them, which is
    # what every other folding surface does. Measured for the three pairs above:
    # the elected survivor is in each case the row already sitting in its
    # correct chronological slot, so no served row moves.
    #
    # Gotcha #42 as a whole stage: the fold improves the strip and is never a
    # precondition for having one. If it raises, the reader gets today's strip —
    # duplicates and all — rather than a 500 on a futures page.
    try:
        _fold = fold_twin_events(events)
        if _fold.dropped_ids:
            logger.info(
                "futures related events: market %s collapsed %d duplicate rows "
                "(dropped=%s)",
                market.id,
                len(_fold.dropped_ids),
                _fold.dropped_ids,
            )
        events = _fold.events
    except Exception:
        logger.exception(
            "futures related events: twin fold failed for market %s", market.id
        )

    # The cap is applied AFTER the fold, which is the point of the headroom.
    #
    # No `set_committed_value` dance for `merged_sources` here, unlike the team
    # rails and the feed: this payload serves no probability for an event — id,
    # names, kick-off, status, scores and the linked outcome — so there is no
    # number that could disagree with the source list behind it. Taking the
    # union anyway would be a write-shaped operation on a row nothing reads it
    # from.
    events = events[:RELATED_EVENTS_LIMIT]

    formatted_events = []
    for event in events:
        # Determine which team in this event is linked to the market
        linked_teams = []
        for team_id in [event.home_team_id, event.away_team_id]:
            if team_id in team_outcome_map:
                side = "home" if team_id == event.home_team_id else "away"
                linked_teams.append({
                    "side": side,
                    "team_name": event.home_team_name if side == "home" else event.away_team_name,
                    **team_outcome_map[team_id],
                })

        formatted_events.append({
            "event_id": event.id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "commence_time": event.commence_time.isoformat(),
            # Q438: the lifecycle invariant, not the raw column. See
            # `app/utils/lifecycle.served_event_status`.
            "status": served_event_status(
                event.status, event.commence_time, datetime.now(timezone.utc)
            ),
            "sport": event.sport.key if event.sport else None,
            "home_score": event.home_score,
            "away_score": event.away_score,
            "linked_teams": linked_teams,
        })

    return {
        "market_id": market_id,
        "market_name": market.name,
        "events": formatted_events,
        "total_count": len(formatted_events),
    }


@router.get("/{market_id}/progression")
async def get_progression(
    market_id: int,
    top_n: int = Query(32, ge=1, le=64, description="Max participants to return"),
    golf_card_receipt: Optional[str] = Query(
        None,
        max_length=64,
        description=(
            "Receipt of the GET /api/golf card snapshot the caller is displaying "
            "(UX-P271). Golf only. Binds the Win column to that exact snapshot "
            "rather than to whatever the cache holds at request time, which is not "
            "the same thing once the card has been served from an HTTP cache. The "
            "receipt actually applied is echoed back as `golf_card_receipt`."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get tournament progression table for a futures market.

    Given any market, finds sibling markets at different stages for the same
    sport/season and assembles a cross-stage pivot showing each participant's
    probability at each stage (e.g., Make Cut → Top 20 → Top 10 → Top 5 → Win).
    """
    # Load starting market
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    sport_cat = market.llm_sport_category
    if not sport_cat:
        return {"sport": None, "stages": [], "participants": []}

    stages = get_stages_for_sport(sport_cat)
    if not stages:
        return {"sport": sport_cat, "stages": [], "participants": []}

    # --- Discover sibling markets ---
    sibling_markets: list[FuturesMarket] = [market]
    source_tournament_name = extract_tournament_name(market.name)

    # Method 1: DataGolf prefix matching
    dg_prefix = get_datagolf_prefix(market.external_id) if market.external_id else None
    if dg_prefix:
        dg_result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.external_id.ilike(f"{dg_prefix}:%"),
                FuturesMarket.id != market_id,
                FuturesMarket.status == "open",
            )
        )
        sibling_markets.extend(dg_result.scalars().unique().all())

    # Method 1b: Kalshi ticker suffix matching
    # Kalshi golf tickers: KX{TYPE}-{SUFFIX} where SUFFIX identifies the tournament
    # e.g., KXPGATOP10-ARPIPBM26 and KXPGAR3LEAD-ARPIPBM26 share suffix ARPIPBM26
    if len(sibling_markets) < 2 and market.external_id:
        kalshi_suffix = _extract_kalshi_suffix(market.external_id)
        if kalshi_suffix and len(kalshi_suffix) >= 4:
            ks_result = await db.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(
                    FuturesMarket.external_id.ilike(f"%-{kalshi_suffix}"),
                    FuturesMarket.id != market_id,
                    FuturesMarket.status == "open",
                )
            )
            sibling_markets.extend(ks_result.scalars().unique().all())

    # Method 2: Canonical key siblings
    if len(sibling_markets) < 2 and market.canonical_market_key:
        # Parse key: "sport:league:category:season" → find same sport:league:*:season
        parts = market.canonical_market_key.split(":")
        if len(parts) >= 4:
            sport_part, league_part = parts[0], parts[1]
            season_part = parts[-1]
            # Search for markets sharing sport:league:*:season
            ck_result = await db.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(
                    FuturesMarket.canonical_market_key.ilike(
                        f"{sport_part}:{league_part}:%:{season_part}"
                    ),
                    FuturesMarket.id != market_id,
                    FuturesMarket.status == "open",
                )
            )
            sibling_markets.extend(ck_result.scalars().unique().all())

    # Method 3: Tournament name matching (fallback)
    # Only include markets whose extracted tournament name matches the source market
    if len(sibling_markets) < 2 and source_tournament_name:
        filters = [
            FuturesMarket.llm_sport_category == sport_cat,
            FuturesMarket.id != market_id,
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),  # Not game-level
        ]
        if market.resolution_date:
            # Look for markets resolving within 30 days of this one
            window = timedelta(days=30)
            filters.append(
                FuturesMarket.resolution_date.between(
                    market.resolution_date - window,
                    market.resolution_date + window,
                )
            )
        scan_result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(*filters)
            .limit(100)
        )
        candidates = scan_result.scalars().unique().all()
        # Filter: must be same tournament AND not a game-level market
        for candidate in candidates:
            if is_game_level_market(candidate.name):
                continue
            candidate_name = extract_tournament_name(candidate.name)
            if tournament_names_match(source_tournament_name, candidate_name):
                sibling_markets.append(candidate)

    # Method 4: Cross-source sibling discovery (UX-P268 / #2661)
    # Methods 1-3 stop as soon as they have found A sibling, which answers "does
    # this tournament have other STAGES" but never asks "does it have other
    # SOURCES". Omega European Masters is the worked case: the DataGolf prefix scan
    # returns the four other DataGolf stages, so `len(sibling_markets) >= 2` and the
    # Kalshi "Omega European Masters Winner" — priced, open, and blended into the
    # /api/golf card the user is reading two lists above — is never looked for at
    # all. Without this pass the blend below has nothing to blend and the table
    # keeps publishing one source's raw price.
    #
    # Scoped so it only costs a query when it can pay: it runs solely when every
    # market found so far shares the primary's source, it asks for the other
    # sources by name, and it makes Postgres do the tournament-name narrowing
    # instead of shipping 100 unrelated markets and their outcomes to Python.
    # Measured on this tournament: 1 market / 162 outcomes in 13ms, against
    # Method 3's unfiltered 47 / 3,266.
    if (
        len(sibling_markets) >= 2
        and source_tournament_name
        and len({m.source for m in sibling_markets}) < 2
    ):
        # `source_tournament_name` is data, so neutralize LIKE metacharacters —
        # a tournament called "50_50 Open" must not match every 5-char prefix.
        name_needle = (
            source_tournament_name.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        cross_filters = [
            FuturesMarket.llm_sport_category == sport_cat,
            FuturesMarket.id != market_id,
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),  # Not game-level
            FuturesMarket.source != market.source,
            FuturesMarket.name.ilike(f"%{name_needle}%", escape="\\"),
        ]
        if market.resolution_date:
            window = timedelta(days=30)
            cross_filters.append(
                FuturesMarket.resolution_date.between(
                    market.resolution_date - window,
                    market.resolution_date + window,
                )
            )
        cross_result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(*cross_filters)
            .limit(100)
        )
        for candidate in cross_result.scalars().unique().all():
            if is_game_level_market(candidate.name):
                continue
            candidate_name = extract_tournament_name(candidate.name)
            if tournament_names_match(source_tournament_name, candidate_name):
                sibling_markets.append(candidate)

    # Deduplicate by market ID
    seen_ids: set[int] = set()
    unique_markets: list[FuturesMarket] = []
    for m in sibling_markets:
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            unique_markets.append(m)

    # Filter out non-golf false positives (soccer, esports, etc.) for golf markets
    if sport_cat == "golf":
        from app.routes.golf import _is_golf_market
        unique_markets = [m for m in unique_markets if _is_golf_market(m)]

    # --- Classify each market into a stage ---
    # The first market classified into a stage is that stage's PRIMARY: it alone
    # decides which participants the stage has a row for. A further market at the
    # same stage is SECONDARY — it contributes a price to participants that already
    # merge, but never introduces a participant of its own.
    #
    # UX-P268 (#2661): a tournament can carry one stage from two sources (Omega
    # European Masters has a Kalshi "Winner" and a DataGolf "- Winner"). Keeping only
    # the first meant publishing one source's raw price while the /api/golf card
    # published the blend, so one golfer read 5.8% on the card and 4.5% in the table.
    # Letting the secondary market define rows too is NOT the fix: 15 of its 162
    # outcomes do not merge and 7 of those outrank the display cut, so "Eugenio
    # Chacarra" and "Eugenio Lopez-Chacarra" would both render, as would "Angel
    # Ayora" and "Angel Ayora Fanegas".
    stage_markets: dict[str, FuturesMarket] = {}
    stage_secondary_markets: dict[str, list[FuturesMarket]] = defaultdict(list)
    for m in unique_markets:
        stage_key = classify_market_stage(
            m.name, m.external_id, m.market_tier, stages
        )
        if not stage_key:
            continue
        if stage_key in stage_markets:
            stage_secondary_markets[stage_key].append(m)
        else:
            stage_markets[stage_key] = m

    if len(stage_markets) < 1:
        return {"sport": sport_cat, "stages": [], "participants": []}

    # --- Build participant cross-reference ---
    # outcome merge key → {name, team_id, probabilities by stage, ...}
    participants: dict[str, dict] = {}

    # Load team info for team_id lookups
    all_team_ids = set()
    for m in stage_markets.values():
        for o in m.outcomes:
            if o.team_id:
                all_team_ids.add(o.team_id)

    team_info: dict[int, dict] = {}
    if all_team_ids:
        team_result = await db.execute(
            select(Team).where(Team.id.in_(all_team_ids))
        )
        for t in team_result.scalars().all():
            team_info[t.id] = {
                "logo_url": t.logo_url_small or t.logo_url,
                "primary_color": t.primary_color,
                "record": t.current_record,
                "conference": (t.standings_data or {}).get("conference"),
            }

    for stage_key, m in stage_markets.items():
        for o in m.outcomes:
            merge_key = _progression_merge_key(o)
            if merge_key not in participants:
                t_info = team_info.get(o.team_id) if o.team_id else None
                participants[merge_key] = {
                    "name": o.name,
                    "team_id": o.team_id,
                    "logo_url": t_info["logo_url"] if t_info else None,
                    "primary_color": t_info["primary_color"] if t_info else None,
                    "conference": t_info["conference"] if t_info else None,
                    "record": t_info["record"] if t_info else None,
                    "probabilities": {},
                    "changes_24h": {},
                    "status": {},
                }
            p = participants[merge_key]
            prob = float(o.current_probability) if o.current_probability is not None else None
            p["probabilities"][stage_key] = prob
            if o.probability_change_24h:
                p["changes_24h"][stage_key] = float(o.probability_change_24h)
            # Detect clinched / eliminated
            if prob is not None:
                if prob >= 0.999:
                    p["status"][stage_key] = "clinched"
                elif prob <= 0.001:
                    p["status"][stage_key] = "eliminated"
            # Update team_id if we found one in a later stage
            if o.team_id and not p["team_id"]:
                p["team_id"] = o.team_id
                t_info = team_info.get(o.team_id)
                if t_info:
                    p["logo_url"] = t_info["logo_url"]
                    p["primary_color"] = t_info["primary_color"]
                    p["conference"] = t_info["conference"]
                    p["record"] = t_info["record"]

    # --- Blend same-stage sources into one number per participant ---
    # "The blend is the product": where two sources price the same stage, a
    # participant's number is the unweighted mean of the sources that name them —
    # the same rule GET /api/golf uses for its card, so the two surfaces agree.
    # A participant absent from the primary market is skipped, which is what keeps
    # the row set identical to the single-source response. The mean is taken over
    # every contributing source at once, so the published number does not depend on
    # which market happened to be primary.
    for stage_key, extra_markets in stage_secondary_markets.items():
        prob_contrib: dict[str, list[float]] = defaultdict(list)
        change_contrib: dict[str, list[float]] = defaultdict(list)
        for m in extra_markets:
            for o in m.outcomes:
                merge_key = _progression_merge_key(o)
                if merge_key not in participants:
                    continue  # secondary-only participant: never becomes a row
                if o.current_probability is not None:
                    prob_contrib[merge_key].append(float(o.current_probability))
                if o.probability_change_24h is not None:
                    change_contrib[merge_key].append(float(o.probability_change_24h))

        for merge_key, extra_probs in prob_contrib.items():
            p = participants[merge_key]
            primary_prob = p["probabilities"].get(stage_key)
            sources = (
                extra_probs if primary_prob is None
                else [primary_prob, *extra_probs]
            )
            # Quantize each source to 3dp before averaging, then quantize the mean.
            # This is not cosmetic: it is GET /api/golf's own arithmetic
            # (`golf.py` rounds every per-source price to 3dp, means them, and
            # rounds again), and reproducing it is the difference between the two
            # surfaces agreeing and merely getting closer. Averaging the raw prices
            # instead still left 4 of 15 golfers printing two different numbers —
            # Wallace 5.7% against the card's 5.8% — because a 0.0002 gap survives
            # into the first decimal the page renders. Single-source stages never
            # reach this line, so their raw values are untouched.
            blended = round(mean([round(v, 3) for v in sources]), 3)
            p["probabilities"][stage_key] = blended
            # Clinched/eliminated is a claim about the number we publish, so it is
            # recomputed from the blend rather than left on the primary's verdict.
            p["status"].pop(stage_key, None)
            if blended >= 0.999:
                p["status"][stage_key] = "clinched"
            elif blended <= 0.001:
                p["status"][stage_key] = "eliminated"

        for merge_key, extra_changes in change_contrib.items():
            p = participants[merge_key]
            primary_change = p["changes_24h"].get(stage_key)
            p["changes_24h"][stage_key] = mean(
                extra_changes if primary_change is None
                else [primary_change, *extra_changes]
            )

    # --- One clock: the card is the authority for the number it publishes ---
    # UX-P270 / CERT-740. Applied AFTER the blend so it overrides it, and BEFORE
    # the sort below so the table is ordered by the numbers it actually prints
    # rather than by values the user never sees. Scoped to golf's `win` stage
    # because that is the only cell `GET /api/golf` also publishes: every other
    # stage, and every golfer the card does not carry, keeps the live blend and is
    # left strictly fresher. See `_golf_card_win_probabilities` for why the card
    # rather than this endpoint is the authority.
    #
    # UX-P271 / CERT-746: the page names WHICH card it is holding, because the one
    # this process would read now is not necessarily the one on the user's screen.
    applied_card_receipt: Optional[str] = None
    if sport_cat == "golf" and "win" in stage_markets:
        card_wins, applied_card_receipt = await _golf_card_win_probabilities(
            source_tournament_name, golf_card_receipt
        )
        for merge_key, card_prob in card_wins.items():
            p = participants.get(merge_key)
            if p is None:
                continue  # on the card, not in this market's field — never a row
            p["probabilities"]["win"] = card_prob
            # Terminal state is a claim about the number we publish, so it is
            # recomputed from the published value rather than left on the blend's.
            p["status"].pop("win", None)
            if card_prob >= 0.999:
                p["status"]["win"] = "clinched"
            elif card_prob <= 0.001:
                p["status"]["win"] = "eliminated"

    # Sort participants by highest-stage probability (rightmost stage first)
    stage_order = sorted(stage_markets.keys(), key=lambda k: next(
        (s["order"] for s in stages if s["key"] == k), 0
    ), reverse=True)

    def sort_key(p: dict) -> tuple:
        for sk in stage_order:
            prob = p["probabilities"].get(sk)
            if prob is not None:
                return (1, prob)
        return (0, 0)

    sorted_participants = sorted(participants.values(), key=sort_key, reverse=True)[:top_n]

    # Build ordered stages response (only include stages that have markets)
    stages_response = []
    for stage in sorted(stages, key=lambda s: s["order"]):
        if stage["key"] in stage_markets:
            m = stage_markets[stage["key"]]
            stages_response.append({
                "key": stage["key"],
                "label": stage["label"],
                "order": stage["order"],
                "market_id": m.id,
                "market_name": m.name,
            })

    return {
        "sport": sport_cat,
        "tournament_name": source_tournament_name,
        "stages": stages_response,
        "participants": sorted_participants,
        # The card snapshot the Win column was actually bound to (UX-P271).
        # Echoed rather than assumed: when this differs from the receipt the page
        # sent, the page is holding a card this response could not bind to — an
        # LRU eviction, or a client older than the deploy — and it re-reads the
        # card past its HTTP cache so the two converge. Silence there would be the
        # original defect wearing a fix's clothes.
        "golf_card_receipt": applied_card_receipt,
    }


async def _golf_card_win_probabilities(
    tournament_name: Optional[str],
    requested_receipt: Optional[str] = None,
) -> tuple[dict[str, float], Optional[str]]:
    """The win probabilities the card is publishing, and the receipt they came from.

    Returns `(win_map, applied_receipt)`. The receipt is echoed to the caller so the
    page can tell whether the table bound to the card it is actually holding; see
    the module docstring of `app.utils.golf_card_snapshot` for why that matters.

    UX-P270 / CERT-740. The blend above reproduces the card's ARITHMETIC, and that
    is not enough to make the two numbers on `/categories/golf` agree, because they
    are not computed at the same MOMENT. `GET /api/golf` serves
    `bainluck:category:golf`, written hourly by the category precompute with a
    7,200 s TTL; this endpoint reads `futures_outcomes.current_probability` live.
    So the two surfaces read the same rows through different clocks and drift apart
    whenever a price moves between the snapshot and the request — during play the
    DataGolf poller rewrites those rows every 90 seconds. Reproducing the
    arithmetic more exactly cannot close a gap that is made of time.

    Two independently-clocked computations of one quantity cannot be made to agree;
    only ONE authority can. This returns the card's own published numbers so the
    win column can adopt them, which makes agreement true by construction rather
    than true-when-nothing-moved. The card is the authority and not the reverse
    because the reverse is unaffordable: `get_golf` is a ~1.5 s rebuild behind a
    45 ms cached read, and `/api/golf` additionally ships
    `max-age=300, stale-while-revalidate=60`, so even a live origin would be read
    through a browser cache this endpoint does not share.

    KNOWN AND DELIBERATE: the win column therefore inherits the card's staleness
    for the golfers the card carries. That is a trade, and it is the right way
    round — a user reading two different numbers for one golfer on one screen is
    the reported defect (#2661), whereas both numbers being equally old is the
    ordinary freshness budget of the page they are already reading. This does NOT
    re-open CERT-686, which blocked serving the golf tournament HEADLINE field from
    this cache: nothing here changes what the headline reads, and the rows the card
    does not carry keep their live blended value.

    UX-P271 / CERT-746 — WHICH card. "Adopt the card" and "adopt the card the
    browser is holding" are different, because `/api/golf` ships
    `public, max-age=300, stale-while-revalidate=60` while this endpoint sends no
    `Cache-Control` at all. A page can therefore render a card response up to 360 s
    old out of an HTTP cache while this request reads Redis now, and if the hourly
    precompute landed in between, adopting "the current card" reintroduces exactly
    the two numbers #2661 reports. UX-P270's page-side fingerprint cannot catch
    that: it is computed from the card response alone, so it is perfectly stable
    while the two clocks disagree.

    So the page names the snapshot it is holding, by a receipt over that snapshot's
    own contents, and this resolves THAT snapshot. The bind is exact at any card
    age within the cache window, because a receipt cannot come to mean different
    numbers — different numbers are a different receipt.

    Fails open in every direction — no Redis, no payload, no matching tournament,
    or a malformed entry all return `({}, None)` and leave the live blend in place.
    A receipt that cannot be resolved (Redis here is an LRU and may evict) does NOT
    silently fall through to a different snapshot's numbers pretending to be the
    requested one: the current card is adopted and its OWN receipt is echoed, so
    the mismatch is visible to the caller instead of being absorbed here.
    """
    if not tournament_name:
        return {}, None

    from app.utils.golf_card_snapshot import (
        card_win_map,
        card_win_receipt,
        resolve_snapshot,
        snapshot_key,
    )

    try:
        import json as _json

        from app.routes.golf import GOLF_CATEGORY_CACHE_KEY
        from app.tasks.redis_state import get_async_redis_client

        rc = get_async_redis_client()
        try:
            # The requested snapshot first: it is what the user is looking at.
            # Only fall back to the current card when it cannot be resolved.
            if requested_receipt:
                pinned_raw = await rc.get(snapshot_key(requested_receipt))
                pinned = resolve_snapshot(
                    pinned_raw, requested_receipt, tournament_name
                )
                if pinned:
                    return pinned, requested_receipt
            raw = await rc.get(GOLF_CATEGORY_CACHE_KEY)
        finally:
            await rc.aclose()
        if not raw:
            return {}, None
        payload = _json.loads(raw)
    except Exception:
        logger.debug("golf card authority unavailable", exc_info=True)
        return {}, None

    if not isinstance(payload, dict):
        return {}, None
    for entry in payload.get("tournaments") or []:
        if not isinstance(entry, dict):
            continue
        card_name = entry.get("name")
        if not card_name or not tournament_names_match(tournament_name, card_name):
            continue
        published = card_win_map(entry)
        if not published:
            return {}, None
        # Recomputed from the map actually being applied rather than read off the
        # payload's stamped field, so the echoed receipt always describes the
        # numbers this response carries — even if the stamp were stale or absent.
        return published, card_win_receipt(published)
    return {}, None


def _progression_merge_key(outcome: FuturesOutcome) -> str:
    """Generate a merge key for cross-market participant matching.

    Priority: team_id (most reliable) > normalized name (fallback).

    Name normalization handles cross-source variations:
    - DataGolf: "Scheffler, Scottie" → "scottie scheffler"
    - Kalshi: "Yes: Scottie Scheffler" → "scottie scheffler"
    - Polymarket: "Scottie Scheffler" → "scottie scheffler"
    - Diacritics: "Skarsgård" → "skarsgard"
    - Suffixes: "Jr.", "Sr.", "III" stripped
    """
    if outcome.team_id:
        return f"team:{outcome.team_id}"
    return _progression_name_key(outcome.name or "")


# `_progression_name_key` is imported at the top of this module from
# `app.utils.golf_card_snapshot`, which owns it as of UX-P271.


# ---------------------------------------------------------------------------
# #7351 — the venue's own history, for the two ORDINARY chart readers
# ---------------------------------------------------------------------------
#
# PILLAR: TRUTH. SHIP: opening a generic Discover market shows its supported
# historical observations on the phone and the web, including history our
# periodic polls missed.
#
# `futures_odds_snapshots` is a sampler. Market 59165099 ("Will federal capital
# gains taxes be cut in 2026?") served ONE observation in its seven-day window
# while Kalshi's own candlesticks for the exact ticker held more. The venue
# history machinery already existed (`tasks/futures_chart_series_fill`) but only
# the concept envelope read it, and its cache is keyed by outcome NAME — unsafe
# for a single question, because every binary has a "Yes". These helpers read
# the identity-bound sibling cache (`utils/generic_market_history`) instead.
#
# WHAT THE READERS MAY AND MAY NOT DO WITH IT:
#   * a venue point is a REAL observation at a REAL instant: never interpolated,
#     never carried across a gap, never given a synthetic "now" endpoint;
#   * it passes `_drop_unsupported_snapshot_points` — the SAME canonical support
#     predicates as our own rows, asked of the point's own book, at read time;
#   * a capture is never displaced: venue points fill only the instants no
#     capture claims (`unclaimed_instants`), so every point served before this
#     change is served unchanged after it;
#   * nothing here touches current price, rank, movement, settlement or Field
#     metadata, and nothing is written to Postgres;
#   * no provider is ever called from a request. A cold page serves what it has
#     and asks the background lane ONCE, behind a per-market claim and an hourly
#     site-wide budget; the next ordinary read uses the result.


#: Captures in the requested window under which a read may ask the background
#: lane for one venue fill. A BOUNDED FETCH TRIGGER — see the call site: it is
#: counted in rows, so it is not, and does not claim to be, a judgement about
#: whether any individual line on the chart is thin.
_VENUE_FILL_THIN_CAPTURES = 20


class _GenericVenueHistory:
    """What the generic-history cache holds for ONE market, already vetted."""

    def __init__(self) -> None:
        self.applicable = False
        self.state = "not_applicable"
        self.rows: dict[int, list] = {}
        self.payload: Optional[dict] = None
        self.refusals: list[dict] = []
        self.unsupported_dropped = 0
        self.fill = "not_considered"
        self.thin_basis: Optional[str] = None
        #: Which tier ANSWERED — `cache` (Redis), `durable` (Postgres, #7807), or
        #: None when neither did. Published so the two-tier read is READABLE from
        #: the served payload rather than inferred from a chart that looks the
        #: same either way, which is the only way an after-check can tell the
        #: durable tier paid. It names a tier that produced a payload: a cold
        #: read reports None, because saying `cache` there would describe a tier
        #: that answered nothing.
        self.tier: Optional[str] = None

    def in_window(self, cutoff: datetime, capture_rows: list, outcome_ids) -> list:
        """Venue rows at/after `cutoff` that no capture already speaks for."""
        if not self.rows:
            return []
        from app.utils.generic_market_history import unclaimed_instants

        captured: dict[int, list[datetime]] = defaultdict(list)
        for row in capture_rows:
            captured[row.outcome_id].append(row.captured_at)
        kept: list = []
        for oid in outcome_ids:
            rows = [r for r in self.rows.get(oid, ()) if r.captured_at >= cutoff]
            if not rows:
                continue
            # #7547 — the tier labels travel with the instants. Without them the
            # layering measures the venue's grain off the gaps it happens to see,
            # and a quiet minute-tier reads as coarse (see `unclaimed_instants`).
            free = unclaimed_instants(
                [r.captured_at for r in rows],
                captured.get(oid, ()),
                venue_tiers=[getattr(r, "tier", "") for r in rows],
            )
            kept.extend(r for r in rows if r.captured_at in free)
        return kept

    def describe(self, served_rows: list, *, scale_refused: Optional[str] = None) -> dict:
        """The reader's own statement of what it served and why — metadata only."""
        stamps = [r.captured_at for r in served_rows]
        payload = self.payload or {}
        block = {
            "state": self.state if not scale_refused else "refused",
            "tier": self.tier,
            "points_served": len(served_rows),
            "outcomes_served": len({r.outcome_id for r in served_rows}),
            "observed_from": min(stamps).isoformat() if stamps else None,
            "observed_through": max(stamps).isoformat() if stamps else None,
            "built_at": payload.get("built_at"),
            "fill_status": payload.get("status"),
            "scale": payload.get("scale"),
            "unsupported_points_withheld": self.unsupported_dropped,
            "fill": self.fill,
        }
        if self.thin_basis:
            # What "thin" MEANT for this response. Stated so the trigger cannot be
            # read back as a claim that every sparse line on this chart was
            # repaired — it is the rule that decided whether to ask, nothing more.
            block["fill_trigger"] = self.thin_basis
        refusals = [r for r in self.refusals]
        if scale_refused:
            refusals.append({"scope": "reader", "reason": scale_refused})
        if refusals:
            block["refusals"] = refusals[:10]
        return block


def _venue_scale_refusal(
    market: FuturesMarket,
    charted_outcomes: list,
    venue_by_outcome: dict,
    outcome_time_groups: dict,
    devigged: dict,
) -> Optional[str]:
    """None when `/history`'s PRINTED scale is the venue's raw scale here; else why not.

    🔴 FOR A SQUEEZABLE EXCLUSIVE FIELD THE EVIDENCE MUST BE CONTEMPORANEOUS WITH
    THE POINT BEING ADMITTED. The squeeze is a whole-field operation: what it does
    to one outcome's number is a function of the OTHER outcomes' values at the
    SAME instant. A venue point is, by construction, at an instant no capture
    reached (`unclaimed_instants`), so the captures cannot answer for it.

    The first presentation admitted such a market whenever every CAPTURED instant
    happened to come through the squeeze unchanged. That is the inference removed
    here: two outcomes sitting at .5/.5 all week are exactly the case where the
    squeeze is the identity *because the field already sums to one*, and that says
    nothing about an unobserved instant where it may not.

    So the venue instants are asked to answer for themselves, through the SAME
    scale contract this route prints with rather than a second copy of its rules:
    every charted outcome must have an observation at that instant (a field with a
    hole has no denominator), and running `devigged_consensus_by_time` over those
    contemporaneous raw values must return them unchanged. Where that holds the
    squeeze is measured to be the identity AT THE POINT BEING SERVED; where it
    does not, the series is refused rather than converted by a rule nobody ruled
    on. Nothing new is fetched and no denominator is borrowed from today.

    A market that cannot be squeezed by construction needs none of this — a
    non-exclusive family (#199) or the single-outcome binary the named specimen is
    — and falls straight through to the per-capture comparison below.
    """
    squeezable = bool(getattr(market, "mutually_exclusive", True)) and len(charted_outcomes) > 1
    if squeezable:
        from app.utils.futures_history_basis import devigged_consensus_by_time

        charted_ids = {int(o.id) for o in charted_outcomes}
        venue_columns: dict[datetime, dict[int, float]] = defaultdict(dict)
        for oid, rows in venue_by_outcome.items():
            for row in rows:
                venue_columns[row.captured_at][int(oid)] = float(row.probability)
        for column in venue_columns.values():
            if set(column) != charted_ids:
                return "exclusive_field_incomplete_at_venue_instant"
        venue_printed = devigged_consensus_by_time(
            {at: {market.source: col} for at, col in venue_columns.items()},
            mutually_exclusive=True,
        )
        for at, column in venue_columns.items():
            printed_here = venue_printed.get(at)
            if printed_here is None:
                return "printed_scale_is_not_the_venue_raw_scale"
            for oid, raw in column.items():
                if abs(float(printed_here.get(oid, raw + 1.0)) - raw) > 5e-5:
                    return "printed_scale_is_not_the_venue_raw_scale"
    for oid in venue_by_outcome:
        for captured_at, raw_values in (outcome_time_groups.get(oid) or {}).items():
            point = devigged.get(captured_at)
            if point is None or oid not in point or not raw_values:
                continue
            if abs(float(point[oid]) - mean(raw_values)) > 5e-5:
                return "printed_scale_is_not_the_venue_raw_scale"
    return None


def _venue_rows_served(venue_cells: dict) -> list:
    """The venue observations a served timeline entry actually carries.

    Since the reader serves each of these at its OWN recorded instant, the cells
    ARE the served rows — one per (outcome, bucket) the captures left empty, the
    last observation in each. The `observed_from` / `observed_through` stamps
    `describe` builds from them are therefore real venue instants, and can be
    compared directly with the timestamps in the timeline.
    """
    return [row for cells in venue_cells.values() for row in cells.values()]


def _request_path_redis():
    """The Redis client a CHART READ is allowed to wait on (#7351).

    THE LATENCY MIDDLEWARE'S OWN SIGNATURE, ON PURPOSE — `socket_timeout=0.5,
    fast_fail=True`. Two reasons, and the second is a budget, not a preference:

      * the default client retries three times at up to 5 s each. A chart must
        lose its venue history to a sick Redis in about half a second, not hold
        the reader for fifteen;
      * `get_redis_client` caches ONE POOL PER DISTINCT SIGNATURE PER PROCESS, and
        the plan's 80 connections are shared by every process of both apps
        (#1197; `test_redis_pool_fits_the_shared_budget_1197` pins the signature
        set). The web process already holds this exact pool for the latency
        sampler, so this call is a dict lookup and adds NO pool and NO signature.
    """
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=0.5, fast_fail=True)


async def _load_generic_venue_history(
    market: FuturesMarket, charted_outcomes: list, exclusive_field_ids: set,
    db: Optional[AsyncSession] = None,
) -> _GenericVenueHistory:
    """Read + vet the venue history. NEVER raises, NEVER calls a provider.

    TWO TIERS, FAST ONE FIRST (#7807). Redis answers when it has the bank; when
    it does not — which #7563 measured is most of the time, because a 100 MB
    `allkeys-lru` instance evicts a rarely-read 35 KB value within hours — the
    durable copy in `durable_state_snapshots` answers instead. Only when BOTH
    miss is the chart cold. The payload is identical and goes through the
    identical `validate_payload` bindings either way: which tier held it is a
    fact about our storage, never about whether the series may be trusted.
    """
    venue = _GenericVenueHistory()
    try:
        from app.tasks.generic_market_history_fill import (
            declared_ttl_seconds,
            market_is_fillable,
            read_cached_history,
            read_durable_history,
            write_cached_history,
        )
        from app.utils.generic_market_history import (
            as_snapshot_rows,
            payload_built_at,
            validate_payload,
        )

        if not market_is_fillable(market, charted_outcomes):
            return venue
        venue.applicable = True
        # Off the loop: the sync client is bounded (gotcha #39), but bounded at
        # seconds, and a chart read must not hold every other request for them.
        payload = await asyncio.to_thread(
            read_cached_history, market.id, _request_path_redis()
        )
        if payload is not None:
            venue.tier = "cache"
        elif db is not None:
            payload = await read_durable_history(db, market.id)
            if payload is not None:
                venue.tier = "durable"
                # Put it back in front of the next reader, with what is LEFT of
                # its declared life — never a fresh TTL, which would let a bank
                # outlive its own lifetime once per eviction. Best-effort in
                # every direction: this is an optimisation for the NEXT request
                # and may not cost this one its series.
                built = payload_built_at(payload)
                if built is not None:
                    settled = bool(payload.get("market_settled"))
                    remaining = declared_ttl_seconds(settled=settled) - (
                        datetime.now(timezone.utc) - built
                    ).total_seconds()
                    if remaining > 0:
                        await asyncio.to_thread(
                            write_cached_history, market.id, payload,
                            settled=settled, rc=_request_path_redis(),
                            ttl_s=int(remaining),
                        )
        if payload is None:
            venue.state = "cold"
            return venue
        venue.payload = payload
        accepted, venue.refusals = validate_payload(payload, market, charted_outcomes)
        for oid, points in accepted.items():
            rows = as_snapshot_rows(oid, market.source, points)
            supported = _drop_unsupported_snapshot_points(
                rows, charted_outcomes, exclusive_field_ids
            )
            venue.unsupported_dropped += len(rows) - len(supported)
            if supported:
                venue.rows[oid] = supported
        if any(r.get("scope") == "payload" for r in venue.refusals):
            venue.state = "refused"
        else:
            venue.state = "warm" if venue.rows else "empty"
    except Exception as exc:  # noqa: BLE001 — history enrichment never fails a chart
        logger.warning("generic venue history unavailable for market %s: %s",
                       getattr(market, "id", None), str(exc)[:200])
        venue.rows = {}
        venue.state = "unavailable"
    return venue


def _capture_lines(capture_rows: list) -> list[list[datetime]]:
    """Capture instants grouped PER OUTCOME — one list per line on the chart.

    `captures_are_coarse` must be handed lines and never a pooled stream: ten
    outcomes captured once an hour merge into a six-minute median gap, which
    reads as minute data and is ten hourly lines.
    """
    by_line: dict[int, list[datetime]] = defaultdict(list)
    for row in capture_rows:
        stamp = getattr(row, "captured_at", None)
        if stamp is not None:
            by_line[row.outcome_id].append(stamp)
    return list(by_line.values())


def _plan_and_dispatch_generic_history_fill(
    market, charted_outcomes: list, payload: Optional[dict], chart_is_thin: bool,
    chart_is_coarse: bool = False,
) -> str:
    """Win the claim, spend it, hand it back if the broker refuses. Sync; run off-loop.

    THE DISPATCH LIVES IN THE ROUTE, NOT THE TASK MODULE — `test_no_task_dispatches
    _another_task` keeps `.apply_async` out of `app/tasks/`, the same bargain as
    `/api/events/{id}/history`'s on-demand chart backfill.
    """
    from app.tasks.generic_market_history_fill import plan_on_demand_fill, release_claim

    plan = plan_on_demand_fill(
        market, charted_outcomes, payload,
        chart_is_thin=chart_is_thin, chart_is_coarse=chart_is_coarse,
        rc=_request_path_redis(),
    )
    if not plan.get("enqueue"):
        return str(plan.get("reason"))
    try:
        from app.tasks import fill_generic_market_history

        fill_generic_market_history.apply_async(
            kwargs={"market_ids": [int(market.id)]}, queue="background",
        )
        return "requested"
    except Exception as exc:  # noqa: BLE001 — a broker hiccup must not hold the claim
        release_claim(market.id)
        logger.warning("generic venue history: dispatch failed for market %s: %s",
                       market.id, str(exc)[:200])
        return "dispatch_failed"


async def _consider_generic_history_fill(
    venue: _GenericVenueHistory, market: FuturesMarket, charted_outcomes: list,
    *, chart_is_thin: bool, chart_is_coarse: bool = False,
) -> None:
    """Ask the background lane for this market's venue history, at most once."""
    if not venue.applicable or venue.state == "unavailable":
        return
    try:
        # PLAIN DATA crosses the thread boundary, never a live ORM row: an
        # attribute the session had expired would lazy-load from the worker
        # thread and raise `MissingGreenlet` (gotcha #6's family).
        from types import SimpleNamespace

        market_ref = SimpleNamespace(
            id=market.id, source=market.source,
            external_id=market.external_id, status=market.status,
            # #7736 — the planner needs the durable "this market held a bank
            # once" stamp to tell an EVICTED venue history from one that never
            # existed. Already-loaded column, so this is a dict reference and
            # not a lazy load; `bank_marker` is defensive about every shape.
            market_metadata=market.market_metadata,
        )
        outcome_refs = [
            SimpleNamespace(id=o.id, external_id=o.external_id) for o in charted_outcomes
        ]
        venue.fill = await asyncio.to_thread(
            _plan_and_dispatch_generic_history_fill,
            market_ref, outcome_refs, venue.payload, chart_is_thin,
            chart_is_coarse,
        )
    # (Load bearing for `scan_mutation_residue.py` Pass B — without a line here
    # the closing paren above plus the bare `noqa` below reproduce
    # `typeahead_outcome_arm_mutations:M2-NO-LIMIT`'s replacement literal
    # verbatim and this file reads as mutation residue. Do not delete.)
    except Exception as exc:  # noqa: BLE001 — a chart never fails on its refill
        venue.fill = "error"
        logger.warning("generic venue history: fill consideration failed for %s: %s",
                       market.id, str(exc)[:200])


@router.get("/{market_id}/probability-timeline")
async def get_probability_timeline(
    market_id: int,
    top: int = Query(10, ge=1, le=50, description="Number of top outcomes to show"),
    hours: int = Query(168, ge=1, le=8760, description="Hours of history (default 7 days)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a time-bucketed probability timeline for a futures market.

    Aggregates FuturesOddsSnapshot data into time buckets, takes the median
    probability across bookmakers per outcome, and returns the top N outcomes
    plus a "Field" entry that sums all remaining outcomes' probabilities.

    Designed for multi-participant charts (golf tournaments, championship
    markets with many contestants). Auto-extends the time window for sparse
    markets (common for non-sports futures).
    """
    # Verify market exists and load outcomes + team enrichment.
    #
    # `FuturesMarket.sport` is loaded because this route asks `_format_market_detail`
    # for its numbers (#7284), and that helper dereferences `market.sport.key`.
    # `sport` is a plain lazy `relationship()` (models.py), so on the async session
    # an un-eager-loaded access raises `MissingGreenlet` — a 500, not a fallback.
    # The detail route has always loaded it; delegating to its formatter without
    # matching its loads is what made that a defect here. Measured when it was
    # caught: 18,179 of 51,088 open futures markets carry a non-NULL `sport_id`,
    # and the rest short-circuit on `if market.sport` with no IO at all, which is
    # exactly why no fixture showed it.
    result = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes)
            .selectinload(FuturesOutcome.team),
            selectinload(FuturesMarket.sport),
        )
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # #6641 — ONE CONDITION, ONE LINE. A Polymarket "field" row is served to us
    # twice over: the bare condition id carries the named rung ("March 31,
    # 2026") and the decomposition branch writes the same condition's two legs
    # as `{condition_id}_yes` / `_no`, named literally "Yes"/"No". On 1,455
    # markets both land on ONE market row. `_format_market_detail` has dropped
    # them since Q480; this reader never did, and it is the one the phone's
    # chart reads (`APIClient.swift` -> `/probability-timeline`). So Alex's
    # 2026-09-16 phone pass got a participant table of five rows crowned by
    # "No 100%" sitting directly above an All Outcomes board of three, which
    # lists no "No" at all — one screen, two answers (`market-mixed-outcomes.png`,
    # market 112868 "Taylor Swift pregnant by...?"). The web page is immune only
    # by accident: it picks its series off the deduped board.
    #
    # `drop_duplicate_legs` drops a leg ONLY when the bare rung it duplicates is
    # present on the SAME market, so a correctly decomposed sub-market row —
    # where the legs are the only outcomes — is untouched and its chart still
    # draws. That positive-fact rule is the whole safety argument; see the
    # helper.
    #
    # Everything below reads THIS list and not `market.outcomes`, deliberately:
    # the `> top` test that adds "Field" and the Field sum itself must count the
    # same outcomes the participants come from, or a duplicate leg reappears as
    # an inflated Field line after being dropped from the table.
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

    charted_outcomes = drop_duplicate_legs(
        market.outcomes, lambda o: o.external_id
    )

    # 🔴 #7284 — THE PARTICIPANT TABLE ASKS THE BOARD; IT DOES NOT RE-DERIVE IT.
    #
    # #6641 above fixed ONE of the ways this reader disagreed with the board
    # below it on the same phone screen. It was not one drop that had been
    # missed, it was the whole display policy: every value in `outcomes_meta`
    # came straight off `futures_outcomes`, so the table served raw prices where
    # the ladder served squeezed ones, and per-write deltas where the ladder
    # served #4079's dated amount or refused to speak.
    #
    # WHAT A READER SAW (native/255, iPhone 17 Pro, 2026-09-19 18:48Z, both
    # tables inside ONE viewport):
    #
    #   /futures/58776433   table `October 1 - 31, 2026  59%  +12.5%`
    #                       ladder `October 1 - 31, 2026  49%  (no movement)`
    #   /futures/60268421   table 10 movement claims, three of them disagreeing
    #                       with the ladder's 7 and two on rows it withheld
    #   /futures/58321581   table -0.4% on a row whose detail value is null
    #
    # So this reader asks `_format_market_detail` — the one place the display
    # policy lives — and takes its answer. Not a copy of the rules: the call.
    # Every drop, every withheld price, the #23 squeeze, the dated movement and
    # its refusals arrive together and cannot drift from the ladder, because
    # there is nothing here to drift.
    #
    # ROWS THE BOARD DROPS LEAVE THE CHART TOO, for #6641's own reason stated one
    # comment above: the `> top` test and the Field sum must count the outcomes
    # the participants come from. Leaving a dropped row inside Field would
    # re-publish, as part of a line, exactly the number the board refused to
    # print as a row.
    #
    # THE PLOTTED HISTORY IS NOT RESCALED, and that is codex's ruling of
    # 2026-09-19 rather than an oversight: the series are real observations at
    # real instants, and dividing them by TODAY's field sum would assert a
    # historic displayed percent nobody observed — the same arithmetic #4079's
    # scale ruling rejected by name. On a squeezed board the line and the table
    # are therefore on different scales; the honest fix for that is the board
    # not being squeezed (#7274), not a second fiction here.
    canonical_board = {
        row["id"]: row
        for row in _format_market_detail(
            market, None, await _withheld_price_outcome_ids(db, market)
        )["outcomes"]
    }
    charted_outcomes = [o for o in charted_outcomes if o.id in canonical_board]

    requested_hours = hours
    actual_hours = hours
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    # #1138: for a live in-play market (golf major, etc.), pin the window's left
    # edge to the event start ("since the event started" — Kalshi's LIVE view).
    # The fixed now-Nh lookback otherwise pads the x-axis with a flat pre-event
    # dead zone (The Open: ~3 of 7 days), which visually crushes real intra-round
    # movement into a sliver. Clamping to commence_time makes the tournament fill
    # the frame at full resolution.
    in_play = bool(market.commence_time and now >= market.commence_time)
    # Only clamp (and skip the extend below) when the start is INSIDE the
    # requested window — i.e. a recently-started short event like a 4-day golf
    # tournament. A season-long futures that commenced months ago
    # (commence_time < cutoff) is left on its normal window + extend behavior.
    clamped_to_start = in_play and market.commence_time > cutoff
    if clamped_to_start:
        cutoff = market.commence_time
        actual_hours = max(1, int((now - cutoff).total_seconds() // 3600))

    # Get ALL outcome IDs (we need them all to compute Field)
    all_outcome_ids = [o.id for o in charted_outcomes]

    if not all_outcome_ids:
        return {
            "market_id": market_id,
            "market_name": market.name,
            "hours": hours,
            "actual_hours": hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    # Fetch all snapshots
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )

    result = await db.execute(snapshot_query)
    # #5898. This endpoint takes the MEDIAN across bookmakers per bucket, which
    # makes an unsupported row worse than one bad line: a demoted source still
    # decides a median by position, so a refused Polymarket midpoint can BE the
    # published bucket value. Filtered on the same rule and before the same
    # sparse decision as `/history`.
    _field_ids = _exclusive_field_outcome_ids([market])
    snapshots = _drop_unsupported_snapshot_points(
        list(result.scalars().all()), charted_outcomes, _field_ids
    )

    # #7351 — the venue's own history for this market's own contracts, from the
    # identity-bound cache. A cache read, never a provider call. `venue_rows` is
    # what it adds INSIDE the window being served: real observations our polls
    # missed, already through the support filter above, and never an instant a
    # capture already speaks for. With a cold cache this is `[]` and every line
    # below behaves exactly as it did.
    venue = await _load_generic_venue_history(market, charted_outcomes, _field_ids, db)
    venue_rows = venue.in_window(cutoff, snapshots, all_outcome_ids)
    # Thin is judged on OUR captures in the window the reader ASKED for — the
    # same `< 20` this route has always used to call a window sparse — so a
    # chart our polls already draw densely never spends a venue request.
    #
    # ⚠️ IT IS A FETCH TRIGGER, NOT A VERDICT ON THE CHART, and this ship does not
    # claim otherwise. The count is rows, not lines: twenty captures spread over
    # twenty outcomes clear the trigger while every individual line is still one
    # point, and those charts are NOT repaired here. Naming a per-line density
    # policy is its own question with its own evidence; what this bounds is how
    # often a public GET may turn into an outbound venue request. Read
    # `venue_history.fill_trigger` in the response rather than inferring the rule
    # from the number.
    #
    # #7547 — OR the captures are DENSE BUT COARSE. Counting rows cannot see a
    # window full of hourly captures of a market the venue publishes by the
    # minute; `captures_are_coarse` asks that second question, per line.
    _thin = len(snapshots) < _VENUE_FILL_THIN_CAPTURES
    _coarse = captures_are_coarse(
        _capture_lines(snapshots), window_hours=actual_hours
    )
    venue.thin_basis = (
        f"captures_in_requested_window<{_VENUE_FILL_THIN_CAPTURES}"
        + (" or captures_coarser_than_fine_tier" if _coarse else "")
    )
    await _consider_generic_history_fill(
        venue, market, charted_outcomes,
        chart_is_thin=_thin, chart_is_coarse=_coarse,
    )

    # Auto-extend for sparse markets (same logic as /history endpoint). Skipped
    # for in-play markets (#1138): those are pinned to the event start above and
    # are snapshot-dense, so extending would only re-introduce the pre-event dead
    # zone the clamp exists to remove.
    _TIMELINE_EXTEND_TIERS = [] if clamped_to_start else [
        (20, 720),   # <20 snapshots -> try 30 days
        (10, 2160),  # <10 snapshots -> try 90 days
    ]
    for threshold, extended_hours in _TIMELINE_EXTEND_TIERS:
        # #7351: an admitted venue observation IS an observation, so it counts
        # toward "is this window sparse" exactly as a capture does. A market the
        # venue documents well stops being stretched to 90 days to find nine
        # points, and `actual_hours` keeps describing the window served.
        if (len(snapshots) + len(venue_rows)) < threshold and extended_hours > actual_hours:
            extended_cutoff = datetime.now(timezone.utc) - timedelta(hours=extended_hours)
            ext_query = (
                select(FuturesOddsSnapshot)
                .where(
                    FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
                    FuturesOddsSnapshot.captured_at >= extended_cutoff,
                )
                .order_by(FuturesOddsSnapshot.captured_at)
            )
            ext_result = await db.execute(ext_query)
            extended_snapshots = _drop_unsupported_snapshot_points(
                list(ext_result.scalars().all()), charted_outcomes, _field_ids
            )
            extended_venue_rows = venue.in_window(
                extended_cutoff, extended_snapshots, all_outcome_ids
            )
            if (len(extended_snapshots) + len(extended_venue_rows)) > (
                len(snapshots) + len(venue_rows)
            ):
                snapshots = extended_snapshots
                venue_rows = extended_venue_rows
                actual_hours = extended_hours

    if not snapshots and not venue_rows:
        return {
            "market_id": market_id,
            "market_name": market.name,
            "hours": requested_hours,
            "actual_hours": actual_hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    # Determine bucket size based on market state.
    # If commence_time is set and we're past it, use 15-min buckets.
    # Otherwise use 1-hour buckets. (`now`/`in_play` computed above.)
    if in_play:
        bucket_seconds = 900  # 15 minutes
    else:
        bucket_seconds = 3600  # 1 hour

    # Determine the top N outcomes by current probability.
    #
    # #7284: the BOARD's probability, not the stored one, so the table cannot be
    # ordered by one number and labelled with another. A withheld row reads
    # `None` here and sinks, exactly as it does on the ladder (`probability ?? 0`
    # is the clients' own rule).
    sorted_outcomes = sorted(
        charted_outcomes,
        key=lambda o: canonical_board[o.id]["probability"] or 0,
        reverse=True,
    )
    top_outcome_ids = {o.id for o in sorted_outcomes[:top]}
    # #7284: the SERIES KEY is a name, so the label the table prints and the key
    # the line is filed under have to be the same string or the phone cannot join
    # them. Taking both from the board means a repaired rung name (#6479's
    # `Los Angeles R` -> `Los Angeles Rams`) reaches the chart legend too.
    outcome_names = {o.id: canonical_board[o.id]["name"] for o in charted_outcomes}

    # Group snapshots: outcome_id -> bucket_key -> [probabilities]
    # bucket_key is the truncated timestamp
    outcome_buckets: dict[int, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for snap in snapshots:
        if snap.probability is not None:
            ts = int(snap.captured_at.timestamp())
            bucket_key = (ts // bucket_seconds) * bucket_seconds
            outcome_buckets[snap.outcome_id][bucket_key].append(
                float(snap.probability)
            )

    # Collect all bucket keys across all outcomes
    all_bucket_keys = set()
    for buckets in outcome_buckets.values():
        all_bucket_keys.update(buckets.keys())

    # #7351 — venue observations fill ONLY the (outcome, bucket) cells no capture
    # reached. A cell a capture already fills is served byte-for-byte as before;
    # that is the whole compatibility argument for dense markets.
    #
    # THE VALUE IS THE LAST OBSERVATION IN THE BUCKET, NOT A MEDIAN. The median
    # above is a consensus ACROSS BOOKS at one reading. Two venue observations in
    # one hour are one book at two instants, and their median is a price nobody
    # quoted; the last one is the price the bucket closed on.
    #
    # 🔴 AND IT IS SERVED AT THE INSTANT IT WAS OBSERVED, NOT AT THE BUCKET START.
    # The bucket is how this route DEDUPLICATES against our own captures — one
    # venue point per (outcome, hour) that our polls missed — and that is all it
    # is. Writing the observation into the bucket's own entry would publish
    # 05:00 for a price the venue timestamped 05:41: a time nobody observed, on
    # the one series whose entire claim is that these are real observations at
    # real instants. `/history` has always served the raw instant; the phone read
    # the rounded one, so the two readers disagreed about when the same
    # observation happened.
    #
    # Capture buckets are untouched and still emit at the bucket start, so a
    # market with no venue history is byte-for-byte what it was. A venue
    # observation gets its own entry keyed by its own timestamp, which is also
    # why two outcomes observed at different instants inside one hour can no
    # longer be collapsed onto one shared reading.
    #
    # ONLY THE CHARTED TOP-N. A venue point never feeds "Field": the fill fetches
    # a bounded top-N, so a Field summed from venue points would be a partial sum
    # presented as the rest of the market.
    venue_cells: dict[int, dict[int, object]] = defaultdict(dict)
    for row in sorted(venue_rows, key=lambda r: r.captured_at):
        if row.outcome_id not in top_outcome_ids or row.probability is None:
            continue
        bucket_key = (int(row.captured_at.timestamp()) // bucket_seconds) * bucket_seconds
        if bucket_key in (outcome_buckets.get(row.outcome_id) or {}):
            continue
        # Last observation in the cell wins — the rows are in ascending order.
        venue_cells[row.outcome_id][bucket_key] = row

    # Build timeline: for each time bucket, compute median probability per outcome
    entries_by_instant: dict[datetime, dict] = {}
    for bucket_key in sorted(all_bucket_keys):
        bucket_at = datetime.fromtimestamp(bucket_key, tz=timezone.utc)
        entry = {"timestamp": bucket_at.isoformat(), "outcomes": {}}

        field_prob = 0.0

        for outcome in charted_outcomes:
            oid = outcome.id
            probs = outcome_buckets.get(oid, {}).get(bucket_key, [])
            if not probs:
                continue

            med_prob = median(probs)

            if oid in top_outcome_ids:
                entry["outcomes"][outcome_names[oid]] = round(med_prob, 6)
            else:
                field_prob += med_prob

        # Add Field if there are outcomes outside the top N. Cap at 1.0 (#1139):
        # independent binaries carry bookmaker overround and can sum >100%
        # (gotcha #23), which renders as an impossible >100% line.
        #
        # #7351: only in a bucket a CAPTURE reached — which is now every entry
        # built by this loop. In a venue-only entry no Field member was read at
        # all, and `0.0` there would be a fabricated zero rather than a missing
        # value (gotcha #53), so those entries below never carry the key.
        if len(charted_outcomes) > top:
            entry["outcomes"]["Field"] = round(min(field_prob, 1.0), 6)

        entries_by_instant[bucket_at] = entry

    # #7351: the venue's observations, each at the instant the venue recorded.
    # An instant that coincides exactly with a bucket start joins that entry
    # rather than shadowing it; the outcome cannot already be present there,
    # because a cell a capture reached was skipped above.
    for oid, cells in venue_cells.items():
        for row in cells.values():
            entry = entries_by_instant.get(row.captured_at)
            if entry is None:
                entry = {"timestamp": row.captured_at.isoformat(), "outcomes": {}}
                entries_by_instant[row.captured_at] = entry
            entry["outcomes"].setdefault(
                outcome_names[oid], round(float(row.probability), 6)
            )

    timeline = [entries_by_instant[at] for at in sorted(entries_by_instant)]

    # Build outcome metadata list (ordered by current probability)
    outcomes_meta = []
    for o in sorted_outcomes[:top]:
        # #7284: every served value comes off the board. `rank` and the team
        # enrichment below stay on the ORM row deliberately — they are identity,
        # not display, and the ladder does not restate them.
        served = canonical_board[o.id]
        meta: dict = {
            "id": o.id,
            "name": served["name"],
            "current_probability": served["probability"],
            "rank": o.rank,
            "probability_change_24h": served["probability_change_24h"],
            "opening_probability": served["opening_probability"],
        }
        # Team enrichment (logos, colors, record)
        if o.team:
            meta["team_id"] = o.team.id
            meta["logo_small"] = o.team.logo_url_small
            meta["logo_large"] = o.team.logo_url_large
            meta["primary_color"] = o.team.primary_color
            meta["secondary_color"] = o.team.secondary_color
            meta["abbreviation"] = o.team.abbreviation
            meta["record"] = o.team.current_record
            meta["location"] = o.team.location
            meta["espn_id"] = o.team.espn_id
        else:
            meta["team_id"] = o.team_id  # FK may exist without loaded team
        outcomes_meta.append(meta)
    if len(charted_outcomes) > top:
        # Sum remaining probabilities for Field — #7284: the BOARD's numbers, or
        # the Field row is the one line on the table still on the raw scale, and
        # a reader adding the column up gets a total the page disagrees with.
        field_current = sum(
            canonical_board[o.id]["probability"] or 0.0
            for o in sorted_outcomes[top:]
        )
        outcomes_meta.append({
            "id": None,
            "name": "Field",
            "current_probability": round(field_current, 6),
        })

    # #7351 — ADDITIVE and only on a market whose venue publishes history.
    # Built before the return rather than inside it so the receipt below and the
    # `venue_history` key can be the SAME object: a receipt that described a
    # second `describe()` call would be describing a different read.
    venue_block = (
        venue.describe(_venue_rows_served(venue_cells)) if venue.applicable else None
    )
    if venue_block is not None:
        # #7807 acceptance, second call site — and the one that carries the
        # PHONE. `APIClient.swift:929` fetches `/probability-timeline`; nothing
        # native calls `/history`. Both readers go through the same
        # `_load_generic_venue_history`, so either can be the FIRST to touch an
        # evicted bank, and the first one takes the durable tier and rehydrates
        # Redis for the other. With the receipt wired only into `/history`, a
        # phone-first fallback wrote nothing and the `/history` read that
        # followed it said `cache` — so the durable serve that actually happened
        # left no record, which is the exact lost-evidence race this ship exists
        # to remove. The surface is named distinctly so a reader of the log can
        # tell WHICH door fell back.
        log_durable_venue_serve(
            venue_block,
            market_id=market_id,
            surface="futures_probability_timeline",
        )

    return {
        "market_id": market_id,
        "market_name": market.name,
        "sport_category": market.llm_sport_category,
        "source": market.source,
        "hours": requested_hours,
        "actual_hours": actual_hours,
        "top": top,
        # #7077 live half — and THIS is the door the phone actually reads.
        # `APIClient.swift:929` fetches `/probability-timeline`; nothing native
        # calls `/futures/{id}/history`. Production 01:05Z for market 58321581,
        # the Game Awards market in Alex's screenshot: `actual_hours` **168**,
        # and NINE buckets spanning **20.0 hours**. Measured off the entries, so
        # what is reported is the domain the chart draws — bucket-aligned where a
        # capture built the entry, which is why it reads 04:30 where `/history`
        # reads the raw 04:31. #7351's venue entries are the exception and say so
        # honestly: they carry the venue's own recorded instant, so a domain that
        # ends on one ends on a real observation rather than on an hour mark.
        **_measure_timeline_coverage(timeline),
        # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
        # Self-describing payload metadata: it says what one step of `timeline` below
        # actually spans, which is not recoverable from the series itself. No client
        # reads it yet; a chart that labels its own x-axis will need it.
        # ⚠️ STRIP-UNSAFE: `bucketSeconds` is a NON-OPTIONAL `Int` in shipped iOS
        # (Models/FuturesModels.swift:302) — removing it makes `Decodable` throw on
        # every build already in the wild.
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
        "outcomes": outcomes_meta,
        # #7351 — ADDITIVE and only on a market whose venue publishes history.
        # Says what the venue-history seam contributed to THIS response, so the
        # coverage above can be read for what it is. Shipped clients ignore an
        # unknown key (`Decodable`); nothing above it changed shape.
        **({"venue_history": venue_block} if venue_block is not None else {}),
    }


@router.get("/cross-source-timeline")
async def get_cross_source_timeline(
    canonical_key: str = Query(..., description="Canonical market key"),
    top: int = Query(10, ge=1, le=50, description="Number of top outcomes to show"),
    hours: int = Query(168, ge=1, le=8760, description="Hours of history"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a merged probability timeline across all sources sharing a canonical key.

    Outcomes are matched across sources by team_id or normalized name.
    For each time bucket, probabilities from multiple sources are averaged.
    Returns the same shape as the single-market probability-timeline endpoint.
    """
    # Find all markets sharing this canonical key
    markets_result = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes)
            .selectinload(FuturesOutcome.team)
        )
        .where(FuturesMarket.canonical_market_key == canonical_key)
        .order_by(FuturesMarket.source)
    )
    markets = markets_result.scalars().unique().all()

    if not markets:
        raise HTTPException(status_code=404, detail="No markets found for this canonical key")

    sources = sorted(set(m.source for m in markets))

    # Merge outcomes across sources by team_id or normalized name
    # merge_key -> { name, team_id, outcome_ids: [int], team: Team|None }
    # #6641 — same rule, same placement inside the per-market loop, as the three
    # other chart readers in this file.
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

    merged_outcomes: dict[str, dict] = {}
    for market in markets:
        for outcome in drop_duplicate_legs(
            market.outcomes, lambda o: o.external_id
        ):
            merge_key = _outcome_merge_key(outcome)
            if merge_key not in merged_outcomes:
                merged_outcomes[merge_key] = {
                    "name": outcome.name,
                    "team_id": outcome.team_id,
                    "team": outcome.team,
                    "outcome_ids": [],
                    "current_probabilities": [],
                    "changes_24h": [],
                    "opening_probabilities": [],
                    "ranks": [],
                }
            entry = merged_outcomes[merge_key]
            entry["outcome_ids"].append(outcome.id)
            if outcome.current_probability is not None:
                entry["current_probabilities"].append(float(outcome.current_probability))
            if outcome.probability_change_24h is not None:
                entry["changes_24h"].append(float(outcome.probability_change_24h))
            if outcome.opening_probability is not None:
                entry["opening_probabilities"].append(float(outcome.opening_probability))
            if outcome.rank is not None:
                entry["ranks"].append(outcome.rank)
            # Prefer the team-linked entry for name/team
            if outcome.team and not entry["team"]:
                entry["team"] = outcome.team
                entry["name"] = outcome.name

    # Sort merged outcomes by average current probability
    sorted_merged = sorted(
        merged_outcomes.values(),
        key=lambda o: (
            mean(o["current_probabilities"]) if o["current_probabilities"] else 0
        ),
        reverse=True,
    )

    # Top N outcome merge keys
    top_entries = sorted_merged[:top]
    top_outcome_ids = set()
    for entry in top_entries:
        top_outcome_ids.update(entry["outcome_ids"])

    # All outcome IDs for Field computation
    all_outcome_ids = []
    for entry in sorted_merged:
        all_outcome_ids.extend(entry["outcome_ids"])

    if not all_outcome_ids:
        return {
            "market_id": markets[0].id,
            "market_name": markets[0].name,
            "canonical_key": canonical_key,
            "sources": sources,
            "hours": hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Fetch all snapshots across all sibling markets
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .where(
            FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    result = await db.execute(snapshot_query)
    # #5898, and this is the fourth and last chart reader in this file. It is the
    # explicit cross-source surface, so an unsupported row here is published
    # BESIDE the honest venue's line as if the two disagreed about the world —
    # the source-divergence-is-a-data-bug ruling in reverse. Same rule, same
    # per-row bookmaker key, so the sibling market's point at that timestamp is
    # untouched.
    snapshots = _drop_unsupported_snapshot_points(
        list(result.scalars().all()),
        [o for m in markets for o in m.outcomes],
        _exclusive_field_outcome_ids(markets),
    )

    if not snapshots:
        return {
            "market_id": markets[0].id,
            "market_name": markets[0].name,
            "canonical_key": canonical_key,
            "sources": sources,
            "hours": hours,
            "top": top,
            "timeline": [],
            "outcomes": [],
        }

    # Build outcome_id -> merge_key lookup
    oid_to_merge_key: dict[int, str] = {}
    merge_key_list = list(merged_outcomes.keys())
    for mk in merge_key_list:
        for oid in merged_outcomes[mk]["outcome_ids"]:
            oid_to_merge_key[oid] = mk

    # Determine bucket size
    now = datetime.now(timezone.utc)
    primary = markets[0]
    if primary.commence_time and now >= primary.commence_time:
        bucket_seconds = 900
    else:
        bucket_seconds = 3600

    # Group snapshots: merge_key -> bucket_key -> [probabilities]
    # This averages across sources automatically since different outcome_ids
    # from different sources map to the same merge_key
    merged_buckets: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for snap in snapshots:
        if snap.probability is not None:
            mk = oid_to_merge_key.get(snap.outcome_id)
            if mk is None:
                continue
            ts = int(snap.captured_at.timestamp())
            bucket_key = (ts // bucket_seconds) * bucket_seconds
            merged_buckets[mk][bucket_key].append(float(snap.probability))

    # Collect all bucket keys
    all_bucket_keys: set[int] = set()
    for buckets in merged_buckets.values():
        all_bucket_keys.update(buckets.keys())
    sorted_bucket_keys = sorted(all_bucket_keys)

    # Top merge keys
    top_merge_keys = set()
    for entry in top_entries:
        mk_match = _outcome_merge_key_from_entry(entry)
        top_merge_keys.add(mk_match)

    # Build timeline
    timeline = []
    for bucket_key in sorted_bucket_keys:
        bucket_ts = datetime.fromtimestamp(bucket_key, tz=timezone.utc).isoformat()
        tl_entry: dict = {"timestamp": bucket_ts, "outcomes": {}}
        field_prob = 0.0

        for mk, entry in merged_outcomes.items():
            probs = merged_buckets.get(mk, {}).get(bucket_key, [])
            if not probs:
                continue
            avg_prob = mean(probs)

            if mk in top_merge_keys:
                tl_entry["outcomes"][entry["name"]] = round(avg_prob, 6)
            else:
                field_prob += avg_prob

        if len(sorted_merged) > top and field_prob > 0:
            tl_entry["outcomes"]["Field"] = round(field_prob, 6)

        timeline.append(tl_entry)

    # Build outcome metadata
    outcomes_meta = []
    for entry in top_entries:
        avg_prob = mean(entry["current_probabilities"]) if entry["current_probabilities"] else None
        avg_change = mean(entry["changes_24h"]) if entry["changes_24h"] else None
        avg_opening = mean(entry["opening_probabilities"]) if entry["opening_probabilities"] else None
        best_rank = min(entry["ranks"]) if entry["ranks"] else None

        meta: dict = {
            "id": entry["outcome_ids"][0] if entry["outcome_ids"] else None,
            "name": entry["name"],
            "current_probability": round(avg_prob, 6) if avg_prob is not None else None,
            "rank": best_rank,
            "probability_change_24h": round(avg_change, 6) if avg_change is not None else None,
            "opening_probability": round(avg_opening, 6) if avg_opening is not None else None,
        }
        team = entry.get("team")
        if team:
            meta["team_id"] = team.id
            meta["logo_small"] = team.logo_url_small
            meta["logo_large"] = team.logo_url_large
            meta["primary_color"] = team.primary_color
            meta["secondary_color"] = team.secondary_color
            meta["abbreviation"] = team.abbreviation
            meta["record"] = team.current_record
            meta["location"] = team.location
            meta["espn_id"] = team.espn_id

        outcomes_meta.append(meta)

    # Add Field
    if len(sorted_merged) > top:
        remaining = sorted_merged[top:]
        field_current = 0.0
        for entry in remaining:
            if entry["current_probabilities"]:
                field_current += mean(entry["current_probabilities"])
        outcomes_meta.append({
            "id": None,
            "name": "Field",
            "current_probability": round(field_current, 6),
        })

    return {
        "market_id": markets[0].id,
        "market_name": markets[0].name,
        "canonical_key": canonical_key,
        "sources": sources,
        "sport_category": markets[0].llm_sport_category,
        "source": "merged",
        "hours": hours,
        "top": top,
        # #7077 live half, same defect on the sibling door. This one is read by
        # the web (`frontend/lib/api.ts:1104`), not native. Fixed with the same
        # helper rather than left lying: one door honest and its twin not is how
        # the next reader gets the wrong domain from the other route.
        **_measure_timeline_coverage(timeline),
        # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
        # Self-describing payload metadata: it says what one step of `timeline` below
        # actually spans, which is not recoverable from the series itself. No client
        # reads it yet; a chart that labels its own x-axis will need it.
        # ⚠️ STRIP-UNSAFE: `bucketSeconds` is a NON-OPTIONAL `Int` in shipped iOS
        # (Models/FuturesModels.swift:302) — removing it makes `Decodable` throw on
        # every build already in the wild.
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }


def _coverage_of(stamps: list) -> dict:
    """The one measurement both chart doors report, given their instants.

    Nulls rather than zeros on an empty series — gotcha #53: "no observations"
    and "an instant of observation" must not share a shape. One observation is
    `coverage_hours: 0.0` with `observation_times: 1`, which is a different
    sentence from `None`/`0` and has to render differently.
    """
    if not stamps:
        return {
            "coverage_start": None,
            "coverage_end": None,
            "coverage_hours": None,
            "observation_times": 0,
        }

    first, last = min(stamps), max(stamps)
    return {
        "coverage_start": first.isoformat(),
        "coverage_end": last.isoformat(),
        "coverage_hours": round((last - first).total_seconds() / 3600, 2),
        "observation_times": len({s.isoformat() for s in stamps}),
    }


def _parse_stamp(raw):
    """ISO string -> datetime, or None. A bad stamp is skipped, never fatal."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _measure_timeline_coverage(timeline: list) -> dict:
    """Coverage of a BUCKETED series (`/probability-timeline`, #7077).

    The door native's futures chart actually reads — `APIClient.swift:929`.
    Nothing native calls `/futures/{id}/history`, so this is the payload behind
    the Game Awards screenshot: `actual_hours` 168, nine buckets over 20.0 h.

    Measured off the bucket stamps because those are the x-positions drawn; a
    coverage claim taken from the raw rows would disagree with the plotted line
    by up to one `bucket_seconds`, which is a second error covering the first.
    """
    stamps = [
        s for s in (_parse_stamp((b or {}).get("timestamp")) for b in (timeline or []))
        if s is not None
    ]
    return _coverage_of(stamps)


def _measure_history_coverage(outcome_history: dict) -> dict:
    """Measure the span the served points ACTUALLY cover (#7077 live half).

    `actual_hours` is the window this route SEARCHED, not the window the data
    covers, and nothing in the payload has ever said the difference. Measured on
    production 2026-09-19 against the three markets Alex's build-15 phone walk
    named:

    | market | requested | served `actual_hours` | points actually span |
    |---|---|---|---|
    | 58321581 Game Awards | 168 h | **168** | **19.3 h**, all on Sep 18 |
    | 61122553 Meta training pause | 168 h | **168** | 75.4 h, 2 points/outcome |
    | 59530987 US bank failure | 168 h | **720** (auto-extended) | 598.6 h |

    So the field named "actual" echoes either the request or an internal
    `_EXTEND_TIERS` constant, and never the observations. A client that draws its
    domain from it draws a week and plots one day into it — which is exactly the
    Game Awards screenshot, six x-axis ticks all reading "Sep 18".

    `total_data_points` cannot stand in for this either: it is summed ACROSS
    outcomes, so Game Awards reports 80 from 8 distinct observation times, and a
    24-outcome field would clear the `sparse` threshold on one observation each.
    `observation_times` below is that count un-multiplied.

    Measured AFTER `_apply_settled_winner_freeze`, deliberately: the span
    reported is the span the chart DRAWS, injected settlement point included,
    because a domain label that disagreed with the plotted line would be a second
    error covering the first.

    Returns nulls rather than zeros on an empty history — gotcha #53: "no
    observations" and "an instant of observation" must not share a shape.
    """
    stamps = []
    for entry in outcome_history.values():
        for point in entry.get("history") or []:
            parsed = _parse_stamp(point.get("timestamp"))
            if parsed is not None:
                stamps.append(parsed)

    return _coverage_of(stamps)


@router.get("/{market_id}/history")
async def get_futures_history(
    market_id: int,
    outcome_id: Optional[int] = Query(None, description="Filter to specific outcome"),
    hours: int = Query(168, description="Hours of history (default 7 days)"),
    top_n: int = Query(10, description="Number of top outcomes to return (default 10, max 50)"),
    champion: Optional[str] = Query(
        None,
        description="Settled winner-field champion NAME (#232). When the market carries "
        "no is_winner grade (odds_api winner fields never do), resolve this outcome's "
        "evolution line to 1.0. Callers pass the concept's authoritative structural crown.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical odds movement for a futures market.

    Returns time-series data for charting probability changes.
    Auto-extends the time window for sparse markets (common for non-sports
    futures like politics, economics, entertainment) to ensure meaningful
    chart data density.
    """
    # Only a real, non-empty champion name is usable (direct/unit callers may pass
    # the unresolved Query sentinel rather than None).
    if not isinstance(champion, str) or not champion.strip():
        champion = None

    # Verify market exists
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id == market_id)
    )
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # #6641, same rule and same reason as `get_probability_timeline` above —
    # this is the other half of the same chart. No iOS client reads it, but the
    # web futures page does, and the payload carried the legs either way (four
    # rows served on 112868 where the board served three).
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

    charted_outcomes = drop_duplicate_legs(
        market.outcomes, lambda o: o.external_id
    )

    # #7546 — THE SELECTION IS MADE BELOW, AFTER THE FIELD READ, AND NOT HERE.
    # It has no business being here any more: #4992 widened the snapshot query to
    # the whole field, so the read no longer depends on which legs are charted,
    # and choosing the ten before the rows arrive is what forced the choice to be
    # made on `current_probability` alone. See the block after `field_rows`.

    # --- Auto-extend for sparse markets ---
    # Try the requested window first. If too few snapshots, widen to 30d then 90d.
    # This is critical for non-sports futures (polled every 1-2h) whose 7-day
    # window may contain only a handful of data points.
    requested_hours = hours
    actual_hours = hours
    auto_extended = False

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # #4992 — THE WHOLE FIELD, IN THE QUERY THE CHART ALREADY RAN.
    #
    # The window used to select `outcome_ids` (the ten charted lines). It now
    # selects every outcome of the market, because the de-vig below is only
    # meaningful over a book's WHOLE quoted column: `remove_vig_nway` divides a
    # column by its own sum, so ten of 205 outcomes would divide by the wrong
    # number and force the ten to sum to 1.0. Widening the existing read keeps
    # this route at one round trip per window instead of two.
    #
    # THE CHARTED SUBSET IS TAKEN BACK OUT IMMEDIATELY, so everything downstream
    # — #5898's filter, the sparse tiers, the point counter — sees exactly the
    # rows it saw before and none of their semantics move. The sparse tiers in
    # particular ask "does this outcome have enough points to draw", and handing
    # them a 205-outcome row count would answer a different question.

    # Fetch snapshots for the initial window
    snapshot_query = (
        select(FuturesOddsSnapshot)
        .join(FuturesOutcome, FuturesOutcome.id == FuturesOddsSnapshot.outcome_id)
        .where(
            FuturesOutcome.market_id == market_id,
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    result = await db.execute(snapshot_query)
    field_rows = list(result.scalars().all())
    # #5898 — filtered BEFORE the sparse-window decision below, never after. The
    # tiers ask "does this outcome have enough points to draw", and a refused
    # point is not a point: counting it can leave a chart thin rather than widen
    # it. A market whose recent history is entirely fabricated now reaches back
    # for real history instead of charting the fabrication.
    #
    # `field_rows` is deliberately left unfiltered, and that is the one place the
    # two diverge. #5898 governs which points a reader is SHOWN; `field_rows` is
    # the denominator of the book's own overround, and a book's quoted column is
    # what it quoted. Dropping part of it would inflate every outcome that
    # survived — a second error to cover the first.
    _history_field_ids = _exclusive_field_outcome_ids([market])
    _supported_field = _drop_unsupported_snapshot_points(
        field_rows, charted_outcomes, _history_field_ids
    )

    # #7546 — SPEND THE TEN SLOTS ON LEGS THAT CAN ACTUALLY DRAW.
    #
    # `current_probability` is not always a probability. On Kalshi's 133-leg
    # FedEx Open de France winner board (61461681) every one of the 128 legs with
    # `yes_bid = 0.0000` stores its ASK there — 127 of 133 have
    # `current_probability == current_yes_ask` — and the column sums to 17.60 on a
    # field the classifier proved single-winner. Ranking on it therefore ranks by
    # the size of an untaken offer, so the ten slots went to the ten biggest
    # unsupported asks and `_drop_unsupported_snapshot_points` below then refused
    # them, exactly as the ladder does. Eight of the ten lost every point and the
    # reader got two lines. The five legs that carry a real bid — Hovland, Pavon,
    # Gerard, Cameron Smith, Michael Kim, the only names on the board a person
    # could trade — rank 129th to 133rd on that column and were never candidates,
    # while holding supported points the whole time. Measured on production
    # 2026-09-20 19:2xZ; the served payload's 7 and 4 points reproduce exactly.
    #
    # THE FILTER WAS RIGHT AND STAYS UNTOUCHED. Nothing here overrides #5898 or
    # shows a refused point: the legs below are ordered so that the slots go to
    # legs with something honest to draw, and a leg with nothing honest to draw is
    # demoted rather than rescued. A chart that cannot be filled honestly is still
    # left empty.
    #
    # A PARTITION, NOT A NEW SCORE, so the common case cannot move. Legs are split
    # on "does this leg keep at least one point in this window", each side keeps
    # today's `current_probability` ordering, and the sides are concatenated. When
    # every candidate is chartable — every healthy market — side B is empty and
    # the resulting order is byte-for-byte today's. It can only differ on a market
    # that was about to spend a slot on a leg that draws nothing.
    #
    # NO NEW QUERY AND NO SECOND PREDICATE: this reads the pass over `field_rows`
    # already in hand, which the charted subset is then taken out of. The
    # predicate is per row and independent of the rows beside it, so filtering the
    # field and then subsetting is the same list as subsetting and then filtering
    # — the identity that lets one pass serve both.
    _chartable_ids = {r.outcome_id for r in _supported_field}

    # Get outcome IDs to chart
    if outcome_id:
        outcome_ids = [outcome_id]
    else:
        # Default to top N outcomes by current probability, chartable legs first
        capped_n = min(top_n, 50)
        # FALLS BACK WHOLE when the window holds nothing supported at all: with no
        # chartable leg the partition carries no information, and demoting on it
        # would reorder a market on noise. Today's order then stands and the
        # sparse tiers below reach further back, which is that case's own repair.
        _prefer_chartable = bool(_chartable_ids)
        sorted_outcomes = sorted(
            charted_outcomes,
            key=lambda o: (
                _prefer_chartable and o.id in _chartable_ids,
                o.current_probability or 0,
            ),
            reverse=True
        )[:capped_n]
        outcome_ids = [o.id for o in sorted_outcomes]
        # #225 Item 3 — settled charts show the completed journey: the graded
        # winner's line MUST appear even when it was a longshot (low
        # current_probability) or the market's prices went stale/None at
        # settlement. Without this, a settled winner-field charts everyone BUT the
        # winner (the "path to resolution" that never resolves).
        _selected = set(outcome_ids)
        for o in charted_outcomes:
            if getattr(o, "is_winner", False) and o.id not in _selected:
                outcome_ids.append(o.id)
                _selected.add(o.id)
        # #232 — same guarantee for the odds_api winner-field class, where the
        # champion is known only by NAME (no is_winner grade): force its line in
        # even if it fizzled to a longshot, so its path can resolve below.
        if champion and not any(getattr(o, "is_winner", False) for o in charted_outcomes):
            _cnorm = _norm_outcome_name(champion)
            for o in charted_outcomes:
                if _norm_outcome_name(getattr(o, "name", "")) == _cnorm and o.id not in _selected:
                    outcome_ids.append(o.id)
                    _selected.add(o.id)

    charted_ids = set(outcome_ids)
    snapshots = [r for r in _supported_field if r.outcome_id in charted_ids]

    # #7351 — same seam, same rules, as `get_probability_timeline` above: the
    # identity-bound venue history for this market's own contracts, read from
    # cache, support-filtered, and never displacing a capture. `[]` when cold.
    venue = await _load_generic_venue_history(
        market, charted_outcomes, _history_field_ids, db
    )
    venue_rows = venue.in_window(cutoff, snapshots, outcome_ids)
    # #7547 — the same two questions as the timeline route above: too FEW points,
    # or enough points spaced too COARSELY to carry the movement the venue holds.
    await _consider_generic_history_fill(
        venue, market, charted_outcomes,
        chart_is_thin=len(snapshots) < _EXTEND_TIERS[0][0],
        chart_is_coarse=captures_are_coarse(
            _capture_lines(snapshots), window_hours=actual_hours
        ),
    )

    # Auto-extend if sparse
    for threshold, extended_hours in _EXTEND_TIERS:
        # #7351: an admitted venue observation counts toward "is this sparse".
        if (len(snapshots) + len(venue_rows)) < threshold and extended_hours > actual_hours:
            extended_cutoff = datetime.now(timezone.utc) - timedelta(hours=extended_hours)
            ext_query = (
                select(FuturesOddsSnapshot)
                .join(
                    FuturesOutcome,
                    FuturesOutcome.id == FuturesOddsSnapshot.outcome_id,
                )
                .where(
                    FuturesOutcome.market_id == market_id,
                    FuturesOddsSnapshot.captured_at >= extended_cutoff,
                )
                .order_by(FuturesOddsSnapshot.captured_at)
            )
            ext_result = await db.execute(ext_query)
            extended_field = list(ext_result.scalars().all())
            extended_snapshots = _drop_unsupported_snapshot_points(
                [r for r in extended_field if r.outcome_id in charted_ids],
                charted_outcomes,
                _history_field_ids,
            )
            extended_venue_rows = venue.in_window(
                extended_cutoff, extended_snapshots, outcome_ids
            )
            if (len(extended_snapshots) + len(extended_venue_rows)) > (
                len(snapshots) + len(venue_rows)
            ):
                snapshots = extended_snapshots
                venue_rows = extended_venue_rows
                field_rows = extended_field
                actual_hours = extended_hours
                auto_extended = True

    # Group snapshots by outcome, then aggregate per-bookmaker snapshots
    # at the same timestamp into a single consensus value.
    # This prevents chart jaggedness caused by plotting each bookmaker's
    # slightly different probability as a separate data point.
    # #6479 chart half — the reader-side club-name repair the DETAIL payload has
    # applied since `_format_market_detail`, on the one reader path that never
    # got it. `/history` feeds the Probability Trend legend, so board 40533
    # printed `Los Angeles R` in its legend 800px below a hero reading
    # `Los Angeles Rams`: one club, two spellings, one screen, one of them a club
    # that does not exist. Measured on production before the fix — 8 truncated
    # labels inside the charted top-10 across 5 boards.
    #
    # Display-only, and that is checked rather than assumed. Nothing in this
    # route MATCHES on this dict: the champion lookup in
    # `_apply_settled_winner_freeze` reads `FuturesOutcome.name` off the ORM
    # (so the freeze still fires on the shipped spelling), and the web client
    # keys line selection on `outcome_id`, never on the label. Both display
    # sites read it — the per-outcome entry below and the champion entry the
    # freeze injects — so a settled board's legend and its "Settled — X won."
    # caption cannot drift into two spellings either.
    #
    # Per-row and id-anchored by construction: every rung carries its own Kalshi
    # OUTCOME ticker, so a rung that resolves never depends on a sibling that did
    # not, and an unresolved rung prints exactly what Kalshi sent.
    outcome_names = {
        o.id: (repair_field_outcome_name(o.external_id, o.name) or o.name)
        for o in charted_outcomes
    }

    # Group: outcome_id -> captured_at -> [probabilities from different bookmakers]
    outcome_time_groups: dict[int, dict[datetime, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for snapshot in snapshots:
        if snapshot.probability is not None:
            outcome_time_groups[snapshot.outcome_id][snapshot.captured_at].append(
                float(snapshot.probability)
            )

    # #4992 — THE HERO AND THE CHART UNDER IT, ON ONE SCALE. Keyed by BOOK, which
    # `outcome_time_groups` above throws away: `remove_vig_nway` normalizes a
    # book's column on that book's own outcome set, so a structure that has
    # already averaged across books can never be de-vigged afterwards. Built
    # from `field_rows` (the whole field) rather than `snapshots` (the ten
    # charted lines) for the reason given where they are partitioned.
    raw_by_time: dict[datetime, dict[str, dict[int, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in field_rows:
        if row.probability is not None:
            raw_by_time[row.captured_at][row.bookmaker][row.outcome_id] = float(
                row.probability
            )

    devigged = devigged_consensus_by_time(
        raw_by_time,
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
    )

    # Counted as the series is BUILT, not off `outcome_time_groups` above, and
    # #4992 is why it moved. This number is the only input to the `sparse` flag
    # the chart's own empty-state reads, and the skip below can now drop a
    # timestamp the grouping still holds — so counting the raw grouping would
    # promise points that are never drawn, and a market whose every timestamp
    # was refused would render a blank chart while reporting itself dense
    # (gotcha #53: an absence and a fact must not share a shape).
    total_data_points = 0

    # #7351 — THE SCALE CONTRACT. The cached venue series is the venue's RAW YES
    # probability. This route prints `devigged` — per-instant, whole-field, run
    # through the #23 squeeze — and a venue point has no whole field at its
    # instant to be squeezed with. So a venue point is admitted ONLY where the
    # printed scale is measurably the raw scale; otherwise the series is REFUSED
    # for this reader rather than converted by a rule nobody ruled on.
    venue_by_outcome: dict[int, list] = defaultdict(list)
    for row in sorted(venue_rows, key=lambda r: r.captured_at):
        if row.outcome_id in charted_ids and row.probability is not None:
            venue_by_outcome[row.outcome_id].append(row)
    venue_scale_refusal: Optional[str] = None
    if venue_by_outcome:
        venue_scale_refusal = _venue_scale_refusal(
            market, charted_outcomes, venue_by_outcome, outcome_time_groups, devigged
        )
        if venue_scale_refusal:
            venue_by_outcome = defaultdict(list)
    venue_rows_served: list = []

    # Build aggregated history: one data point per timestamp per outcome
    outcome_history = {}
    # Captured outcomes first and in their existing order, so a response with no
    # venue history is byte-for-byte what it was; an outcome our polls never
    # reached inside the window follows.
    _history_order = list(outcome_time_groups.keys()) + [
        oid for oid in outcome_ids
        if oid in venue_by_outcome and oid not in outcome_time_groups
    ]
    for oid in _history_order:
        time_groups = outcome_time_groups.get(oid) or {}
        history = []
        for captured_at in sorted(time_groups.keys()):
            # #4992: a timestamp whose books all refused normalization is
            # SKIPPED, never drawn raw. A gap in a line is honest; a raw point
            # sitting between de-vigged ones is the defect itself, and it would
            # be invisible — it renders as movement (gotcha #53).
            point = devigged.get(captured_at)
            if point is None or oid not in point:
                continue
            avg_prob = point[oid]
            history.append({
                "timestamp": captured_at.isoformat(),
                "probability": avg_prob,
                # WITHHELD, NOT RECONVERTED (#5835's rule, two screens up in
                # this file). A de-vigged, squeezed probability is not a price
                # any book quoted, so running it back through
                # `probability_to_american` would print exactly the thing #6757
                # just stopped this surface doing. Nothing renders this field
                # off /history — the chart reads `probability`, and the
                # progression table reads the DETAIL payload's odds.
                "american_odds": None,
                "bookmaker": "consensus",
            })
        # #7351: the venue's own observations at the instants no capture claims.
        # Real timestamp, raw value, and a provenance a reader can tell from a
        # capture — an older venue sample never passes as a fresh poll.
        for row in venue_by_outcome.get(oid, ()):
            history.append({
                "timestamp": row.captured_at.isoformat(),
                "probability": round(float(row.probability), 6),
                "american_odds": None,
                "bookmaker": row.bookmaker,
                "provenance": "venue_history",
            })
            venue_rows_served.append(row)
        if venue_by_outcome.get(oid):
            history.sort(key=lambda pt: _parse_stamp(pt["timestamp"]))
        elim = _detect_elimination(history)
        total_data_points += len(history)
        outcome_history[oid] = {
            "outcome_id": oid,
            "name": outcome_names.get(oid, "Unknown"),
            "history": history,
            "eliminated": elim["eliminated"],
            "eliminated_at": elim["eliminated_at"],
        }

    # Round boundaries: prefer DataGolf round_history, fall back to
    # inferring rounds from simultaneous elimination patterns
    explicit_boundaries = _derive_round_boundaries(market.market_metadata)
    round_boundaries = _detect_round_boundaries_from_eliminations(
        outcome_history, explicit_boundaries
    )

    # Settled-means-settled evolution freeze (#1177, Queue #230): resolve the
    # graded champion's line to 1.0 at settlement time. Runs AFTER round-boundary
    # detection (which reads real eliminations) so the injected terminal point
    # never perturbs boundary inference. Source-independent: fires on the
    # ``is_winner`` grade even while the winner market is stuck ``status='open'``.
    _apply_settled_winner_freeze(market, outcome_history, outcome_names, outcome_id, champion)

    response: dict = {
        "market_id": market_id,
        "market_name": market.name,
        "hours": requested_hours,
        "actual_hours": actual_hours,
        "outcomes": list(outcome_history.values()),
        "round_boundaries": round_boundaries,
        "leaderboard": (market.market_metadata or {}).get("leaderboard"),
        "total_data_points": total_data_points,
        # #7077 live half: what the points COVER, beside what we SEARCHED.
        # `actual_hours` above stays exactly as it was — it is the search window
        # and `auto_extended`'s caption is correct about it. These four are the
        # separate, measured claim, so no existing reader's meaning moves.
        **_measure_history_coverage(outcome_history),
    }

    # Signal to the frontend when data is sparse so it can show appropriate UI
    if auto_extended:
        response["auto_extended"] = True
    if total_data_points < 10:
        response["sparse"] = True
    # #7351 — additive, and only on a market whose venue publishes history.
    if venue.applicable:
        response["venue_history"] = venue.describe(
            venue_rows_served, scale_refused=venue_scale_refusal
        )
        # #7807 acceptance — write down a durable-tier serve at the instant it
        # happens. It cannot be sampled for afterwards: the fallback rehydrates
        # Redis, so the next read says `cache` and the payload is identical
        # either way. Fires ONLY when the durable tier answered, reads every
        # field off the block above, and can neither raise nor change what is
        # returned (see `app/utils/durable_venue_receipt`).
        log_durable_venue_serve(
            response["venue_history"],
            market_id=market_id,
            surface="futures_history",
        )

    return response


def _format_market_summary(market: FuturesMarket, source_count_map: dict = None) -> dict:
    """Format a market for list view with top outcomes."""
    # Filter out placeholder outcomes before sorting/display
    real_outcomes = [
        o for o in market.outcomes
        if not _GARBAGE_OUTCOME_RE.match(o.name or "")
    ]

    # Sort outcomes by probability
    sorted_outcomes = sorted(
        real_outcomes,
        key=lambda o: o.current_probability or 0,
        reverse=True
    )

    top_outcomes = [
        {
            "id": o.id,
            "name": o.name,
            "probability": float(o.current_probability) if o.current_probability is not None else None,
            "american_odds": o.current_american_odds,
            "rank": o.rank,
            "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
        }
        for o in sorted_outcomes[:5]
    ]

    # Cross-source info from canonical key
    source_info = None
    if source_count_map and market.canonical_market_key:
        source_info = source_count_map.get(market.canonical_market_key)

    result = {
        "id": market.id,
        "name": market.name,
        "sport": market.sport.key if market.sport else None,
        # #6444 — see `_format_market_detail`; the summary serves the same field
        # to the same readers and must not disagree with the detail beside it.
        "sport_name": (
            sport_display_name(market.sport.key, market.sport.name)
            if market.sport
            else None
        ),
        "category": market.category,
        "llm_sport_category": market.llm_sport_category,
        "status": market.status,
        "source": market.source,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "top_outcomes": top_outcomes,
        "outcome_count": len(real_outcomes),
        "category_tags": market.category_tags or [],
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }

    # Add source count if multiple sources track this market
    if source_info and source_info["count"] > 1:
        result["source_count"] = source_info["count"]
        result["sources"] = source_info["sources"]
    else:
        result["source_count"] = 1

    return result


_GARBAGE_OUTCOME_RE = re.compile(r"^player\s+[A-Z]{1,3}$", re.I)

SOURCE_DISAGREEMENT_THRESHOLD_PP = 5
SOURCE_STALENESS_DAYS = 7

#: TTL for the cached provenance half of `GET /api/futures/{market_id}`.
#:
#: The data underneath is written by `poll-futures-every-4h` and
#: `refresh-stale-futures-prices-hourly`, so it moves on a 1-4 HOUR cadence and
#: 300 s is 12-48x faster than the thing it caches. This is deliberately NOT the
#: "TTL must outlive the refill cadence" number from #901 — that rule is about a
#: WARMED key going cold in the gap between warms, and nothing warms this one.
#: There is no warmer and no new beat entry: this is a pure on-demand cache, so
#: the only thing the TTL buys is a staleness budget, and a short one is safer.
MARKET_SOURCES_TTL_S = 300


def market_sources_cache_key(market_id: int) -> str:
    """Redis key for one market's cached bookmaker/source-breakdown pair."""
    return f"bainluck:futures:detail-sources:{market_id}"


def _restore_source_breakdown(rows: list[dict]) -> list[dict]:
    """Undo the one lossy step in the JSON round-trip: ``outcomes`` dict keys.

    🔴 #1587's LESSON, IN THE ONE PLACE IT APPLIES HERE. `_get_source_breakdown`
    keys ``outcomes`` by ``outcome_id`` — an INT — and `json.dumps` turns every
    dict key into a string. On the wire the two are indistinguishable, because
    FastAPI stringifies int keys as well, so a hit and a miss would have shipped
    byte-identical HTTP for as long as nobody looked. But the cache would have
    been storing something that is not what it serves, and the next reader to
    consume this in-process — a warmer, a diff harness, an `assert hit == miss`
    — would have found a difference that no HTTP test could see. Restore the
    ints here so the cached object equals the computed object, not merely its
    rendering.
    """
    restored = []
    for row in rows:
        row = dict(row)
        row["outcomes"] = {int(k): v for k, v in (row.get("outcomes") or {}).items()}
        restored.append(row)
    return restored


async def _load_market_sources(
    db: AsyncSession, market_id: int, outcome_ids: list[int]
) -> tuple[list[str], list[dict]]:
    """Return ``(bookmakers, source_breakdown)`` for one market's outcomes.

    🔴 THIS USED TO BE TWO FULL SCANS OF THE SAME ROWS, AND THE SECOND ONE WAS
    FREE ALL ALONG. The handler ran ``SELECT DISTINCT bookmaker`` to learn which
    books had contributed, then ran the window query in `_get_source_breakdown`
    over the identical row set. The two answers are the same set by
    construction: `bookmaker` is NOT NULL in production, so a book appears in
    the DISTINCT iff it has at least one snapshot iff it has an ``rn = 1`` row
    for some outcome. The breakdown already knows every name the DISTINCT could
    return, so the DISTINCT is derived here instead of re-scanned.

    ⚠️ The breakdown is now computed for single-bookmaker markets too, where it
    previously did not run at all. That costs exactly the scan it replaced (one
    either way), and the caller still attaches ``source_breakdown`` only when
    there is more than one book — the response shape is unchanged in both
    directions.

    WHY THIS IS WORTH A CACHE AT ALL, IN ONE MEASURED SENTENCE. NFL Super Bowl
    Winner (market 86832) has 32 outcomes and **189,312 snapshot rows**; the
    window query sorts all of them to keep the ~256 that are current, twice, on
    every single request, which measured **3.4-5.6 s of database time** in
    production on 2026-08-29. MLB World Series Winner (market 1): 30 outcomes,
    131,807 rows, 2.1-2.9 s.

    ✅ WHAT A STALE ENTRY CAN AND CANNOT SAY. Every row it carries reports its
    own real ``captured_at`` and its own ``stale`` flag, both computed from the
    snapshot's own timestamp. A cached row can therefore be up to
    `MARKET_SOURCES_TTL_S` old, but it CANNOT misreport how old its data is —
    freshness is a field in the payload, not a property of the cache. That is
    what makes caching a deliberate source-comparison surface honest.

    Redis is best-effort in both directions: an unreachable cache degrades to
    computing the answer, never to failing the page.
    """
    import json as _json
    from app.tasks.redis_state import get_redis_client

    cache_key = market_sources_cache_key(market_id)
    redis = None
    try:
        redis = get_redis_client()
        cached = redis.get(cache_key)
        if cached:
            payload = _json.loads(cached)
            return (
                payload["bookmakers"],
                _restore_source_breakdown(payload["source_breakdown"]),
            )
    except Exception:
        logger.debug("futures detail source cache read failed", exc_info=True)

    source_breakdown = await _get_source_breakdown(db, outcome_ids)
    # `_get_source_breakdown` already sorts by source, so this is the same
    # ordering the `ORDER BY bookmaker` it replaces produced.
    bookmakers = [s["source"] for s in source_breakdown]

    if redis is not None:
        try:
            redis.set(
                cache_key,
                _json.dumps(
                    {"bookmakers": bookmakers, "source_breakdown": source_breakdown}
                ),
                ex=MARKET_SOURCES_TTL_S,
            )
        except Exception:
            logger.debug("futures detail source cache write failed", exc_info=True)

    return bookmakers, source_breakdown


async def _get_source_breakdown(
    db: AsyncSession, outcome_ids: list[int]
) -> list[dict]:
    """Get the latest probability per bookmaker for each outcome.

    Returns a list of per-source rows sorted alphabetically by bookmaker.
    Sources with ``captured_at`` older than SOURCE_STALENESS_DAYS are flagged
    ``stale: true`` so the frontend can exclude them from spread math and
    render them muted.

    🔴 THE INDEX LAT-P127 ASKED FOR COULD NOT BE USED BY THE SHAPE THAT ASKED
    FOR IT. P127-3 shipped `ix_futures_odds_snapshots_outcome_bookmaker_captured
    (outcome_id, bookmaker, captured_at DESC)` and the cold read did not move.
    The reason is not the index and not stale stats: the query it was built for
    was a `row_number() OVER (PARTITION BY outcome_id, bookmaker ORDER BY
    captured_at DESC)` carrying **no `bookmaker` predicate**, and PostgreSQL has
    no index skip scan — so a leading-column-only lookup can never descend into
    the second column. The planner correctly ignored the new index and took
    `ix_..._outcome_id`. Measured on production 2026-08-30, market 86832:

        Subquery Scan                         actual 9,163 ms   rows out 256
          WindowAgg
            Sort  external merge, 7,640 kB DISK       rows in 190,656
              Nested Loop
                Index Scan ix_futures_outcomes_market_id        rows 32
                Index Scan ix_..._outcome_id     rows 5,958  x 32 loops
        Shared I/O Read Time 7,973 ms      Temp Written 956 blocks

    **190,656 rows read and sorted to disk to return 256** — 745:1. (The planner
    also estimated 1,661 of those 190,656, a 115x miss: `last_analyze` is NULL
    and `last_autoanalyze` is 2026-08-22 on a 196,407,475-row table. Fixing the
    estimate would not have helped; every plan for this shape reads every row.)

    ✅ WHAT REPLACES IT: a loose index scan — the skip PostgreSQL will not do
    for us, written out. The recursive term walks `(outcome_id, bookmaker)`
    pairs one `LIMIT 1` at a time off `ix_fos_outcome_bookmaker`, then a LATERAL
    takes the newest row for each pair off the P127 index. Same rows, by seek
    instead of by scan. Same market, same minute:

        | executed row query | 3,533 ms -> 344 ms cold, 51-73 ms warm |
        | rows examined      | 190,656  -> 576 index seeks + 256 heap |
        | disk sort          | 7,640 kB -> none                       |

    and the plan finally names the index P127 bought:
    `Index Scan ix_futures_odds_snapshots_outcome_bookmaker_captured, 1 row,
    256 loops`. Verified row-for-row identical against the old statement across
    ten markets spanning 2-32 outcomes (2-256 result rows); see
    `TestLooseScanMatchesTheWindowQuery`.

    ⚠️ THIS IS THE BOUNDED-LIST SHAPE, exactly as
    `app.utils.latest_observation` argues for the one-dimensional case: N
    correlated probes beat one full pass because a market pins its outcomes.
    That module cannot be reused here — it answers "newest per OUTCOME", and
    this page needs "newest per outcome x BOOKMAKER", which is what forces the
    pair walk. But its two warnings both bind here, and one of them inverts:

    🔴 NO `captured_at IS NOT NULL`, AND THAT IS THE OPPOSITE OF P147's CALL.
    The column IS nullable on production (`information_schema` says so, checked
    2026-08-30, though the model declares it non-optional). P147 adds the
    predicate because it replaces a `max()`, and `max()` SKIPS nulls while
    `ORDER BY ... DESC` is NULLS FIRST — without it the two forms disagree.
    Here the thing being replaced is a WINDOW function, which is NULLS FIRST
    too. A null-`captured_at` row wins its partition under the old statement, so
    it must win its pair under this one. Adding the "safer" predicate would be
    the behaviour change. Equivalence is the bar, not tidiness.

    🔴 AND NO `NULLS LAST`, AND NO `id` TIEBREAK. Either one stops the ORDER BY
    matching the index's own ordering, so each probe stops being a one-row
    backward read and becomes a Sort over the whole pair — the full-scan cost
    back, wearing a more deterministic-looking clause. P147 measured `NULLS
    LAST` at 19x. The tiebreak buys nothing real: production carries **zero**
    `(outcome_id, bookmaker, captured_at)` groups with more than one row on this
    market, and the window function it replaces broke ties arbitrarily anyway.

    The pair walk is only correct because `bookmaker` is NOT NULL in production
    — the same premise `_load_market_sources` already leans on to derive the
    bookmaker list. A null would sort into the walk and `> p.bookmaker` would
    terminate it early, silently dropping every book after it.
    """
    from sqlalchemy import text as sql_text

    # Bound as an array rather than an expanding IN: the seed reads the ids as a
    # relation (`unnest`), and an expanding IN cannot be a FROM item. CAST(...)
    # rather than `::integer[]` — asyncpg parses the `::` spelling as a bind.
    rows = await db.execute(
        sql_text(
            """
            WITH RECURSIVE pairs AS (
                SELECT o.outcome_id,
                       (SELECT s.bookmaker
                          FROM futures_odds_snapshots s
                         WHERE s.outcome_id = o.outcome_id
                         ORDER BY s.bookmaker
                         LIMIT 1) AS bookmaker
                  FROM unnest(CAST(:outcome_ids AS integer[])) AS o(outcome_id)
                UNION ALL
                SELECT p.outcome_id,
                       (SELECT s.bookmaker
                          FROM futures_odds_snapshots s
                         WHERE s.outcome_id = p.outcome_id
                           AND s.bookmaker > p.bookmaker
                         ORDER BY s.bookmaker
                         LIMIT 1)
                  FROM pairs p
                 WHERE p.bookmaker IS NOT NULL
            )
            SELECT p.outcome_id, p.bookmaker, latest.probability,
                   latest.captured_at
              FROM pairs p
              CROSS JOIN LATERAL (
                    SELECT s.probability, s.captured_at
                      FROM futures_odds_snapshots s
                     WHERE s.outcome_id = p.outcome_id
                       AND s.bookmaker = p.bookmaker
                     ORDER BY s.captured_at DESC
                     LIMIT 1
                   ) AS latest
             WHERE p.bookmaker IS NOT NULL
            """
        ),
        {"outcome_ids": list(outcome_ids)},
    )

    staleness_cutoff = datetime.now(timezone.utc) - timedelta(days=SOURCE_STALENESS_DAYS)

    by_bookmaker: dict[str, dict] = {}
    for outcome_id, bookmaker, probability, captured_at in rows.all():
        if bookmaker not in by_bookmaker:
            is_stale = bool(captured_at and captured_at < staleness_cutoff)
            by_bookmaker[bookmaker] = {
                "source": bookmaker,
                "outcomes": {},
                "captured_at": captured_at.isoformat() if captured_at else None,
                "stale": is_stale,
            }
        by_bookmaker[bookmaker]["outcomes"][outcome_id] = round(
            float(probability) * 100, 1
        )
        if captured_at and (
            by_bookmaker[bookmaker]["captured_at"] is None
            or captured_at.isoformat() > by_bookmaker[bookmaker]["captured_at"]
        ):
            by_bookmaker[bookmaker]["captured_at"] = captured_at.isoformat()
            by_bookmaker[bookmaker]["stale"] = captured_at < staleness_cutoff

    return sorted(by_bookmaker.values(), key=lambda s: s["source"])


def _format_market_detail(
    market: FuturesMarket,
    bookmakers: list[str] = None,
    unsupported_price_outcome_ids: "set[int] | None" = None,
) -> dict:
    """Format a market for detail view with all outcomes.

    #993: the click-through must MATCH the answer search shows. Apply the SAME
    shared display pipeline (app.utils.outcome_display) — placeholder filter
    (incl. "Team C"), #23 normalization, leader-pick — so the detail page never
    leads with "Other 100%" while search shows "Cleveland Cavaliers 31%".
    """
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs
    from app.utils.superseded_name_twins import drop_superseded_name_twins
    from app.utils.field_opening_coherence import field_openings_publishable
    from app.utils.market_staleness import (
        expired_ladder_rungs,
        stale_observation_keys,
    )
    from app.utils.outcome_display import (
        assign_display_ranks,
        is_placeholder_outcome_name,
        normalize_display_probs,
        leader_pick_order,
        drop_dominant_field_outcomes,
        drop_incoherent_near_certain,
        drop_unbacked_legs,
    )

    # Q480: one condition, one outcome. Dropped here, on the ORM rows, because the
    # detail page renders the WHOLE list and then normalizes it — so a duplicate
    # `_yes`/`_no` leg does not merely add a junk row, it sits in
    # `normalize_display_probs`'s divisor and squeezes every number the page
    # prints. That is the same mechanism as the "Other 1.0" halving documented
    # below, arriving from a different direction.
    # #6508 — one question, one row. A prior cycle's leg stays attached to the
    # board that replaced it, so `/futures/113486` printed `December 31` at 10%
    # directly above `December 31` at 0%: one label, two answers, nothing on the
    # page telling them apart. Measured over all 36,369 open markets — the
    # population THIS function serves, not the 13 boards the issue names — it
    # fires on 13 labels across 12 boards: 112914, 113039, 113040, 113486 and
    # 112938 (twice over), plus seven Polymarket tennis boards where the
    # repeated label is a prop leg under two condition ids.
    #
    # Both rows are REAL — the venue's `end_date_iso` is 2026-01-01 on one leg
    # and 2027-01-01 on the other — so this is emphatically NOT dedup by name,
    # which would delete a true row and pick the survivor on an arbitrary sort
    # key. It drops only a row the venue has already GRADED A LOSS while an
    # unsettled, id-anchored sibling carries the same label; the whole
    # correspondence argument, the three guards and the measurement that killed
    # the two rival designs live on the helper.
    #
    # Here rather than in the summary serializer, and that is measured, not
    # assumed: the card's `top_outcomes` takes the top 5 by probability and
    # every superseded row prices 0.0, so no card surfaces one today (checked on
    # all five boards via `/api/events/search`). Applying it there as well would
    # put a ranking-path serializer in scope for no reader-visible gain.
    #
    # #6524 runs in the same comprehension, on the ORM rows, and AFTER the two
    # helpers above rather than beside them. It is the third row-level correctness
    # drop on this board and the only one keyed on the absence of a venue id:
    # `drop_duplicate_legs` folds two rows that share an id, `drop_superseded_name_twins`
    # needs both rows to be id-anchored to establish the correspondence, and neither
    # can say anything about a row that has no id at all. On 113545 the unbacked
    # `May 31 1.0` sits directly above an id-anchored `May 31 0.02`, so this also
    # resolves that board's duplicate label — but by removing the row that is not a
    # quote, never by picking a survivor on a sort key.
    #
    # HERE, and not at the `drop_incoherent_near_certain` line further down, because
    # this must land before `normalize_display_probs` puts the fabricated 1.0 in the
    # divisor. It is a no-op on today's six boards (all non-ME, so the squeeze
    # returns early) and the placement is what keeps it a no-op on the first ME
    # board that grows one.
    valid_outcomes = [
        o
        for o in drop_unbacked_legs(
            drop_superseded_name_twins(
                drop_duplicate_legs(market.outcomes, lambda o: o.external_id),
                name_of=lambda o: o.name,
                external_id_of=lambda o: o.external_id,
                is_winner_of=lambda o: o.is_winner,
                resolution_source_of=lambda o: o.resolution_source,
            ),
            lambda o: o.external_id,
            market_is_open=getattr(market, "status", None) == "open",
            is_winner_of=lambda o: bool(o.is_winner),
        )
        if not is_placeholder_outcome_name(o.name)
    ]
    sorted_outcomes = sorted(
        valid_outcomes,
        key=lambda o: o.current_probability or 0,
        reverse=True
    )

    # `is not None`, NOT a truth test, and this is #6081's whole fix (nine served
    # sites in this file carried the falsy form; only the predicate input at
    # `drop_incoherent_near_certain` still does, deliberately — see there).
    #
    # `Decimal('0.000000')` is falsy, so `if o.current_probability` served a
    # genuine 0% as `null` — the SAME value this payload uses for "withheld, we
    # cannot say". `/futures/261` ("Boston pro baseball wins this season?") is the
    # specimen: `100+ wins` and `105+ wins` store 0.000000 with
    # `resolution_source='api_settlement'`, `is_winner=false` and a
    # `yes_bid 0.0000 / yes_ask 1.0000` book — Kalshi has settled them NO. The
    # page's `#+ WINS` block printed **0%** and its `All Outcomes` table printed
    # **–** for the same rung, and the payload refuted itself in one object:
    # `prices_withheld: 0` beside two null prices. Nothing withheld them.
    #
    # THE DELIBERATE WITHHOLDING RAIL IS NOT THIS AND IS NOT WEAKENED.
    # `app.utils.futures_unsupported_price` (#5611/#5876) reads bid/ask and
    # snapshots, nulls `WITHHELD_PRICE_FIELDS` further down, and counts the row in
    # `prices_withheld`. That rule is evidence-based. The falsy test was an
    # accidental SECOND withholding rule whose only evidence was that the number
    # happened to be zero — which is exactly the value a settled-NO leg must have.
    # 3,738 of the 4,200 zero-priced legs on still-open markets are a definite
    # venue NO (measured 2026-09-14).
    # #6479: a rung whose name is the venue's width truncation is completed from
    # that rung's OWN ticker. `2027 Pro Football Champion` led with `Los Angeles
    # R` and `Pro Baseball Champion` offered `Los Angeles D` / `Chicago WS` —
    # ten rungs across the site's two longest-lived boards, each naming a club
    # that does not exist. The correspondence is id-anchored (the code and the
    # name are the same row) and the helper refuses unless the venue's own text
    # agrees, so a rung is either completed or printed exactly as Kalshi sent it.
    #
    # Serve-time, like its game-market sibling: the stored `name` stays the
    # venue's and no predicate that reads that column moves.
    #
    # HERE, where the dicts are built, so everything downstream sees one
    # vocabulary — `drop_dominant_field_outcomes` and `leader_pick_order` are
    # name-gated on "Other"/"Field", which this can neither create nor destroy.
    outcomes = [
        {
            "id": o.id,
            "name": repair_field_outcome_name(o.external_id, o.name) or o.name,
            "probability": float(o.current_probability) if o.current_probability is not None else None,
            "american_odds": o.current_american_odds,
            # The stored column is the SEED here, not the served answer: #2556
            # overwrites this from the display order at `assign_display_ranks`
            # below, once the drops and the demotion have settled which rows are
            # on the board and in what order. Left reading `o.rank` so a row the
            # pipeline never reaches still carries something.
            "rank": o.rank,
            # #7299 — THE ARROW IS THE SAME UNDATED CLAIM ITS NEIGHBOUR ALREADY
            # REFUSES, SO IT IS REFUSED BY THE SAME RULE.
            #
            # WHAT A READER SAW. On one row of `/futures/60268421`'s All Outcomes
            # ladder: `↓5` … `LAST MOVE —` … `LATEST 4%`. The LAST MOVE column is
            # blank because the guard ten lines below refused it — we could not
            # date the move, so we said nothing — and then the arrow beside the
            # same outcome's name says the row fell five places in that same
            # twenty-four hours. We refuse one 24h number and print another one
            # next to it, off a basis we have just declared unusable. Seven of
            # fourteen visible rows did this; `/futures/58321581` (a named #4079
            # control) printed `↓18` on a row whose `probability_change_24h` is
            # null, and a collapsed row carried `rank_change_24h: -1` with
            # `probability: null` — a rank move on a row with no price at all.
            #
            # 🔴 NO BANK CAN DATE THIS ONE, WHICH IS WHY THIS IS A REFUSAL AND NOT
            # A SECOND CALL TO `dated_movement_points`. That helper re-derives its
            # answer by SUBTRACTING an observed price, so a banked row can be
            # rescued. There is no equivalent here: the writers store
            # `old_rank - new_rank` FOR ONE POLL (`assign_display_ranks`'s own
            # docstring names the writer), so the stored integer is a rank change
            # over the gap between two polls of unknown length, labelled "24h".
            # Co-dating it with the price bank — the first shape this was filed
            # with — only narrows the mislabel: a per-poll delta on a row whose
            # PRICE basis happens to be datable is still a per-poll delta.
            #
            # A TRUE DATED ARROW IS A PROPERTY OF THE WHOLE BOARD, AND THE ROUTE
            # CANNOT SEE ONE. "Rank then" is only meaningful when EVERY row on the
            # board has a basis in the window, so the rule would be all-or-nothing
            # per market. Measured on production 2026-09-21 over the 24,398 open
            # markets with a future `resolution_date` (162,611 outcomes): the bank
            # dates 1,704 outcomes (1.0%), and exactly **37 markets** are covered
            # on every row. Those 37 hold 48 outcomes between them — they are
            # two-leg binaries, not ladders — and carry **4 arrows across 2
            # markets**, one of which has more than two outcomes. So computing
            # here would preserve 4 of the 9,748 arrows now live across 1,785
            # markets, 39 of which sit on rows with no price, and would cost a
            # rank-then ordering that has to agree with `assign_display_ranks`
            # after the drops, the withholding and the squeeze have run.
            #
            # 🔴 AND IT WOULD DECIDE A QUESTION THIS LANE DOES NOT OWN. Computing
            # an arrow means choosing its SIGN, and the sign is #6607 — the arrow's
            # direction, live and owned by ux. A refusal is sign-agnostic and
            # cannot collide with that fix; a computed integer would silently
            # settle it here. The direction defect keeps its own issue.
            #
            # WIDER COVERAGE IS REACHABLE AND IS NOT THIS SHIP.
            # `futures_odds_snapshots` carries per-outcome history with
            # `captured_at` and covers whole boards the bank does not (24/24 on
            # 58321581), but it is raw per-bookmaker and vig-inclusive, so the
            # ranking would have to stay inside one bookmaker or it is #1844
            # again, and it needs a per-market window query this route does not
            # make today. That is a costed follow-on, not a reason to keep
            # printing the number in the meantime.
            #
            # 🔴 THE COLUMN IS UNTOUCHED, here as in #4079. `/api/futures/movers`
            # still ranks on it, `compute_futures_highlight` still reads it off
            # its own query, `/futures/available` still serves it beside the raw
            # `probability_change_24h` that route also serves ungated, and the
            # A5/A6 sweeps still retire it. This nulls ONE served field on ONE
            # payload — the ladder a reader actually reads the arrow off.
            #
            # PRESENT AND NULL, NEVER OMITTED, and null rather than 0: every
            # client already draws nothing on null (`OutcomeRow` gates on
            # `rankChange !== null && rankChange !== 0`, `FuturesDetailView` on
            # `if let rankChange`, both shipped), while 0 is the answer for a day
            # something MEASURED as flat and would be the one wrong value this
            # can afford least.
            "rank_change_24h": None,
            # #4079 NUMERIC HALF (N3) — THE LADDER'S 24h COLUMN IS DATED OR ABSENT.
            #
            # This is the field behind Alex's phone line 21: `FuturesDetailView`
            # reads it as the hero's 24h change (`detailMovementBadge(leader.
            # probabilityChange24h)`) and `OutcomeRow` prints it on every rung —
            # a green `+30.5` above a plotted line that had barely moved, and
            # `-30` to `-41` on the rungs below it. The stored column is
            # `new - previous` at WRITE time, for a previous write of unknown
            # age, so it answers a different question from the one the column's
            # name and this page both ask.
            #
            # `dated_movement_points` subtracts a price the sweep actually
            # OBSERVED, and returns None wherever it cannot date the day. The
            # value changes; the field, its name and its shape do not — which is
            # deliberate, because the clients that draw this badge ship on the
            # App Store's clock and a new field would reach nobody for weeks
            # (#7226 is that lesson from the other side).
            #
            # ── THE COVERAGE ARGUMENT, ANSWERED (codex, 2026-09-19 16:00Z) ────
            #
            # The bank dates 14.22% of ladder rows (2,286 of 16,074), so most of
            # this column goes quiet. That was the case for withdrawing this once
            # and it is not a reason to keep the old value: the other 85.78% are
            # rows whose served number is a per-write delta labelled "24h", and a
            # blank is the honest rendering of an amount nobody measured. An
            # unbanked row returns null, and the reader loses a badge rather than
            # keeping a wrong one.
            #
            # BESIDE `price_changed_at`, NEVER INSTEAD OF IT. That column — the
            # other half of this two-lane ship, served a few keys below — answers
            # WHEN this rung last moved, for 79.35% of rows, and is untouched
            # here. One dates the instant, one states the amount; a surface may
            # show either without the other, which is why both exist.
            #
            # 🔴 The COLUMN is untouched, here and everywhere. `/api/futures/
            # movers` still ranks on it, `compute_futures_highlight` still picks
            # its subject with it, `max_movement_24h` is still computed from it,
            # and a row the writers left NULL is still silent here even when the
            # bank could date a large move for it.
            "probability_change_24h": dated_movement_points(
                market, o.id, o.current_probability, o.probability_change_24h
            ),
            "opening_probability": float(o.opening_probability) if o.opening_probability else None,
            "opening_american_odds": o.opening_american_odds,
            "is_winner": o.is_winner,
            # #4788/#4783: `is_winner` ALONE cannot say whether anyone graded this
            # row. The column is `boolean NULL DEFAULT false`, so an INSERT that
            # merely omits it stores an affirmative graded LOSS (CAL-P1004R) on a
            # leg nobody called — three of four Polymarket outcome INSERTs do
            # exactly that. `resolution_source` is the field that discriminates
            # "graded a loser" from "never graded", and without it on the wire the
            # client cannot tell them apart and prints a red `Lost` on both.
            #
            # Additive and read-only. The renderer's rule is in
            # `OutcomeRow.outcomeRowVerdict`: NULL source ⇒ ungraded ⇒ no verdict.
            "resolution_source": o.resolution_source,
            "last_updated": o.last_updated.isoformat() if o.last_updated else None,
            # #4079 — THE STAMP THAT DATES A MOVEMENT CLAIM, BECAUSE
            # `last_updated` CANNOT. #2024 settled the distinction at the writer
            # (`futures_price_refresh.py`: "`last_updated` records that a poll
            # RAN; this records that the price MOVED. Both matter and they are
            # not the same") and `price_changed_at_value` only advances the stamp
            # when the written price `IS DISTINCT FROM` the stored one. Until now
            # that column reached no reader on any route, so every surface dating
            # a move had to date it by the poll instead.
            #
            # WHAT THAT COSTS, MEASURED ON PRODUCTION 2026-09-19 over a 300-market
            # slice of the markets that actually make a movement claim: 1,054 of
            # 3,467 ladder rows carry a `price_changed_at` on a DIFFERENT DAY from
            # their `last_updated`, and of the 300 leader rows — the row the web
            # hero pill dates by — 52 name the wrong day and 26 have no stamp at
            # all. Market 58321581 (*Game of the Year*, one of #4079's three named
            # specimens) is the shape: all 24 rows stamped `last_updated`
            # 2026-09-19 10:38:51 by one sweep write, while thirteen of them last
            # actually moved on 09-18 04:31:29, thirty hours earlier.
            #
            # ADDITIVE AND READ-ONLY, and deliberately NOT a second movement
            # NUMBER: `probability_change_24h` keeps its meaning, its writers and
            # every ranking that reads it (`/api/futures/movers`, the sweep,
            # `max_movement_24h`), exactly as the dated-basis bank was careful to
            # leave them. This is the instant, not the delta.
            #
            # NOT in `WITHHELD_PRICE_FIELDS`, and that is a decision rather than an
            # omission: every member of that tuple is a value a reader could use to
            # reconstruct a price we refused to publish, and an instant is not one.
            # `last_updated` is served on withheld rows today for the same reason.
            #
            # NULL means "we have never observed this price move" — which is a
            # refusal, not a zero, and the reader owes it the same
            # honest-unavailable path the bank gets: say nothing about when it
            # moved. 79.35% of rows in that slice carry a stamp; the rest are rows
            # nothing has rewritten since the column shipped.
            #
            # `getattr` WITH A DEFAULT, not `o.price_changed_at`, and the reason is
            # the one `dated_movement_basis` writes out at length for its own
            # column: a carrier that does not hold this attribute must degrade to
            # EXCLUSION, never to an exception. The one caller loads full ORM rows
            # (`selectinload(FuturesMarket.outcomes)`), so the attribute is always
            # there today; a future projection that stopped loading it would
            # otherwise raise inside the per-item serializer and empty the whole
            # ladder rather than drop one claim (gotcha #42). Absent ⇒ None ⇒ the
            # reader says nothing about when the price moved, which is exactly the
            # answer a payload that cannot see the column should give.
            "price_changed_at": (
                stamp.isoformat()
                if (stamp := getattr(o, "price_changed_at", None))
                else None
            ),
        }
        for o in sorted_outcomes
    ]

    # 🔴 #7274 — ONE DIVISOR RULE, OR THE CARD AND THIS PAGE PRINT TWO NUMBERS
    # FOR ONE LEG.
    #
    # WHAT A READER SAW, measured on production 2026-09-19. Discover's card for
    # market 58776433 (*When will the Danube River return to normal levels?*)
    # printed `October 1 - 31, 2026` at **59%**; tapping it, `/futures/58776433`
    # printed the same leg at **49%**. Neither number was a cache artifact — the
    # card reproduced on two independently rebuilt feed payloads.
    #
    # THE CAUSE IS THE DIVISOR'S MEMBERSHIP, NOT A PRICE. Both surfaces divide by
    # the sum of the legs they show, and only one of them strips rungs whose own
    # deadline has passed. The feed drops them (`feed.py`, UX-P004 b+e) and
    # divides by the 0.8845 that survives — under the squeeze band, so it prints
    # the stored price. This page divided by all 1.1935, including a
    # `Before September 1, 2026` rung that on the 19th could no longer happen, so
    # every live rung was squeezed by 16% of probability mass held by dead ones.
    # `_feed_display_scale`'s own docstring names the contract that breaks: one
    # divisor, "so one outcome never renders at two different numbers".
    #
    # THE MEMBERSHIP RULE IS SHARED, NOT THE DIVISOR — the same
    # `expired_ladder_rungs` the feed calls, so the two surfaces cannot drift into
    # two answers about which rungs are real. It also stops this page pricing an
    # impossible option at 14%, which is a truth win on its own account.
    #
    # ABOVE the withheld-price nulling and everything below it, for the reason
    # that block states in its own comment: a row left in place until after the
    # squeeze is still in the divisor. Probabilities are passed raw and unnulled,
    # which is what the helper's `EXPIRED_RUNG_MAX_PROBABILITY` guard needs — a
    # past-dated rung priced at or above it already resolved YES and is the
    # ladder's answer, not a ghost, and is never stripped.
    #
    # CERT-3236: AND THE GRADE GOES WITH THE STAMP. A cumulative "Before Sep 1,
    # 2026" rung settles YES on the day the thing happens, which may be weeks
    # before its own deadline, and that settlement write is the last time the leg
    # is touched — so the stamp test alone reads 25 production winners (Claude 5,
    # Makary, baxdrostat, the DNC autopsy, every day of two Kyiv/Trump ladders) as
    # stale forecasts and deletes them. `is_winner` is a key this serializer
    # already publishes twenty lines up, beside `resolution_source`.
    #
    # #7784: AND THE STAMP GOES WITH THE PRICE, because that guard cannot tell a
    # verdict from a forecast without it. This page's own payload is where the
    # defect was photographed — five rungs of board 109403, four of them dated
    # 15 to 129 days ago, every price stamped `2026-04-30` and therefore taken
    # BEFORE the deadline it was sparing. `last_updated` is the ISO string this
    # serializer already publishes a few keys up; the helper reads a string or a
    # datetime, and an absent one leaves the rung exactly where it is today.
    #
    # OPEN MARKETS ONLY. A settled or closed board is a RESULT, and a result
    # shows what ran, including the windows that elapsed without the event
    # happening. Expiry is a statement about what can still happen, which is a
    # question only an open market asks. This also bounds the change to #7274's
    # population.
    #
    # AND NEVER THE WHOLE BOARD: if every rung has expired the ladder is dead,
    # and the feed answers that by dropping the card. This page cannot drop
    # itself, and an empty All Outcomes table would be a worse answer than a
    # stale one, so the list stands unchanged.
    expired_rungs_dropped = 0
    if getattr(market, "status", None) == "open":
        expired_rung_names = expired_ladder_rungs(
            [
                (
                    o["name"],
                    o.get("probability"),
                    o.get("last_updated"),
                    o.get("is_winner"),
                )
                for o in outcomes
            ],
            datetime.now(timezone.utc),
        )
        if expired_rung_names:
            live_rungs = [o for o in outcomes if o["name"] not in expired_rung_names]
            # ROWS, not names: the count below feeds the identity answer, and two
            # rows can carry one name on a board the earlier twin rules spared.
            if live_rungs:
                expired_rungs_dropped = len(outcomes) - len(live_rungs)
                outcomes = live_rungs

    # #5611/#5876: a price no book and no trade supports — and a Polymarket
    # midpoint the newest trade refutes — are not published. The rules and
    # everything measured about them are in `app.utils.futures_unsupported_price`;
    # the caller decided WHICH rows, because only it can read the snapshots.
    #
    # Both arms land here, in one set, so everything below this line (the
    # normalize-first ordering, the present-and-null key contract, the withheld
    # count) is written once and holds for both.
    #
    # HERE, ABOVE `normalize_display_probs`, AND THAT IS LOAD-BEARING. A withheld
    # value left in place until after the squeeze would still sit in the divisor,
    # so twelve fabricated 1.0s would go on halving every honest row on the same
    # board — the exact mechanism UX-P163 documents below for a no-bid `Other`,
    # which put `Democratic Party 43%` on Discover against a book price of 85.5%.
    # `normalize_display_probs` reads absent values as 0 (`o.get(key) or 0`) and
    # writes back only truthy ones, so nulling first removes them from the sum
    # without touching a surviving row.
    #
    # The key stays PRESENT and null, never omitted, for the same reason #5539
    # states: the clients test `!== null`, and `undefined !== null` is true.
    # Measured against the shipped client, no render change is needed —
    # `formatProbability(null)` already prints "-" (`lib/api.ts`), and both the
    # hero pick and the default sort read `probability ?? 0`, so a withheld row
    # can never be crowned leader and sinks to the bottom of the board on its own.
    withheld = unsupported_price_outcome_ids or set()

    # 🔴 #7537 — AND ONE MORE CLASS OF ROW JOINS THAT SET, FOR A REASON THE
    # RULES ABOVE STRUCTURALLY CANNOT REACH.
    #
    # WHAT A READER SAW. `/futures/3971707` (*Super League Rugby Championship*)
    # printed `Leeds Rhinos 30%` in its hero and its All Outcomes table while
    # the Probability Trend chart between them drew that same outcome at
    # **39.5%** — one screen, one stamp (`14:53:14`), two numbers. Fourteen legs
    # summing to 1.7200 entered this divisor and exactly THREE had been observed
    # that day; the other eleven were last written on 2026-09-06, all eleven at
    # one microsecond. So three genuinely-quoted prices were squeezed by the 41%
    # of probability mass held by rows nobody had repriced in a fortnight.
    #
    # THE CHART IS THE HONEST SIDE, which is why nothing below touches it. 0.395
    # is Kalshi's own midpoint (`yes_bid 0.3300 / yes_ask 0.4600`, read at the
    # venue); 0.302 is manufactured here. The comment on the chart's own call
    # into this function already said where the fix belongs — "the honest fix
    # for that is the board not being squeezed (#7274), not a second fiction
    # here" — and this is that fix.
    #
    # WHY THE EVIDENCE RULES ABOVE ACQUIT THESE ROWS. They read the leg's own
    # bid/ask/last, and on a fossil every one of those columns is frozen at the
    # same stale instant: Hull Kingston Rovers presents `0.1900 / 0.4700` and
    # reads as a healthy two-sided book, while the venue's live answer for
    # `KXSLRCHAMP-26-HKR` is `yes_bid 0.0000 / yes_ask 0.9600 / last 0.0000 /
    # volume_24h 0`. The rules are not wrong; they are being shown stale
    # evidence and acquitting it correctly. Nothing shipped asks whether the
    # evidence is CURRENT.
    #
    # NOT A DELISTING CLAIM. All fourteen tickers read `status = active`. The
    # predicate says only "this row was not observed when its siblings were",
    # which is Codex's ruling of 2026-09-20 — freshness as a display policy with
    # UNKNOWN behaviour, never proof a venue stopped quoting — and it is
    # measured WITHIN the board, so an ingestion outage that ages every leg
    # together withholds nothing.
    #
    # WITHHELD RATHER THAN DROPPED, and the difference is load-bearing twice
    # over. `WITHHELD_PRICE_FIELDS` nulls `probability`, and
    # `normalize_display_probs` reads an absent value as 0, so the row leaves the
    # DIVISOR without leaving the BOARD: the reader still sees every team, each
    # unpriced row prints "-" (`formatProbability(null)`), `len(outcomes)` does
    # not move so `concept_outcome_count` needs no add-back the way #7274's drop
    # did, and — the one that would have bitten — the chart's `canonical_board`
    # filter a few thousand lines up drops any row this list drops, so dropping
    # would have pulled the three honest lines' own board out from under them.
    #
    # OPEN MARKETS ONLY, for #7274's reason stated in its block above: a settled
    # board is a RESULT, and a result shows what ran.
    #
    # Measured on production 2026-09-20 over the 7,933 open tier-1/2
    # mutually-exclusive boards: 758 carry at least one such leg, 100 of those
    # are squeezed today and change what a reader sees (48 stop being squeezed
    # at all, 52 are squeezed less), and 0 have every leg stale.
    if getattr(market, "status", None) == "open":
        withheld = withheld | stale_observation_keys(
            (o.id, o.last_updated) for o in sorted_outcomes
        )

    prices_withheld = 0
    if withheld:
        for o in outcomes:
            if o["id"] in withheld:
                for field in WITHHELD_PRICE_FIELDS:
                    o[field] = None
                prices_withheld += 1

    # #5539: a one-winner field whose openings cannot be a distribution never
    # had an opening, and this page is where the reader meets it. `/futures/
    # 12337998` printed OPEN 99% against all 35 teams in the Women's 2027
    # College Basketball Champion field and captioned it "South Carolina down
    # 74.4 pts from opening" — the seeded midpoint of an untraded book, read by
    # the page as a 74-point move. The rule and its measured false-positive
    # bounds are in `app.utils.field_opening_coherence`; it is deliberately
    # arithmetic about the FIELD, because the tempting value rule ("suppress the
    # opening 18 legs share") was measured suppressing ~19,000 honest longshots.
    #
    # Withheld, not rescaled: rescaling would invent an opening, and
    # `calibration_probability` coalesces to `opening_probability` (gotcha #144 /
    # ruling 103), so an invented one becomes a forecast we are graded on. Both
    # client consumers already read NULL as "no opening" and print nothing —
    # `OutcomeRow` gates the column on `opening_probability !== null`, and
    # `movementExplanation` falls back to the 24h change — so the key must be
    # present and null, never omitted (`undefined !== null` is true).
    def _withhold_openings() -> None:
        for o in outcomes:
            o["opening_probability"] = None
            # The American-odds twin of the same fabricated number. Leaving it
            # would let any consumer reading the odds column reconstruct exactly
            # the price this rule just refused.
            o["opening_american_odds"] = None

    # Machine-readable so a cert or probe can prove a withhold rule fired and tell
    # it apart from a market that simply never had an opening. Not a reader
    # string: notice 34 keeps diagnostics off the page, in a key like this.
    openings_withheld = not field_openings_publishable(
        [o["opening_probability"] for o in outcomes],
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
    )
    if openings_withheld:
        _withhold_openings()

    # #993: #23-normalize the displayed distribution + demote a generic
    # "Other/Field" from the headline (same rules as search).
    # #199: gate on mutual-exclusivity — golf make-cut/top-N (mutually_exclusive
    # False) are NOT one-winner fields; normalizing them squashed an honest 86%
    # make-cut down to ~1% on The Open's detail/ladder rail.
    #
    # 🔴 #5835 — AND THE OPENINGS CANNOT SURVIVE IT. THIS CALL IS THE SECOND CAUSE
    # OF THE EXACT HARM THE BLOCK ABOVE EXISTS TO PREVENT, and it lands one
    # statement later.
    #
    # WHAT A READER SAW. `/futures/109564` (*2026 Oscar for Best Animated Feature
    # Film?*) printed `KPop Demon Hunters  OPEN 92%  LATEST 61%`, and the caption
    # under the hero said so in words. The stored price went 0.915 -> 0.925: it
    # went UP one point. Every rung on that board read as a fall and not one of
    # them fell. Same shape on `/futures/57792790`, captioned "Ohio State Buckeyes
    # down 10.4 pts from opening" over a row that went 0.33 -> 0.34.
    #
    # THE CAUSE IS A DENOMINATOR, NOT A PRICE. `normalize_display_probs` takes
    # `key="probability"` and is never called for `opening_probability`. A field
    # whose raw YES prices sum into the squeeze band is divided by that sum; the
    # openings beside it are not. Two columns headed OPEN and LATEST, two scales,
    # and the reader is invited to subtract one from the other.
    #
    # IT CAN ONLY EVER INVENT A FALL. The divisor is greater than 1.05 whenever it
    # fires, so the printed LATEST is always pushed down relative to the raw price
    # the opening was captured beside. Measured on production 2026-09-13 (tier 1-2,
    # open, mutually-exclusive): 805 markets squeezed, 663 of them printing an OPEN
    # column too, and on 96 the leader's printed direction is the OPPOSITE of its
    # true move. Zero in the other direction, exactly as the arithmetic predicts.
    # Worst artifact 37.2 points.
    #
    # NOT THE #5539 CLASS, which is why that rule spares all of them: these
    # openings CAN be a distribution (1.53 is nowhere near `FIELD_SUM_CEILING`) and
    # are individually honest. They are simply not comparable with the column now
    # printed beside them.
    #
    # WITHHELD AND NOT RESCALED, for #5539's reason and one of its own. Rescaling
    # the openings by their own sum would assert a price nobody quoted, and
    # `calibration_probability` coalesces to `opening_probability` (gotcha #144 /
    # ruling 103). And the opening field is frequently a STAGGERED capture, not a
    # snapshot — the Big Ten field carries ten legs seeded at exactly 0.04 — so
    # normalizing it would be arithmetic over a set that never existed at one
    # instant. That is a second fiction to cover the first.
    #
    # ASKED OF THE FUNCTION THAT DID THE SCALING, never re-derived: it reports
    # whether the printed values actually moved. A copy of the `> 105` test here
    # would be a second answer to one question, free to drift from the first.
    #
    # #7103 — AND NOT AT ALL WHEN THIS PAGE HAS WITHHELD A LEG. The block at the
    # nulling above says the order is load-bearing because it takes a refused row
    # out of the divisor "without touching a surviving row". That is true of the
    # WRITE — no stored price moves — and false of the printed value: removing
    # legs changes whether the squeeze FIRES, and on `/api/futures/2951423` it
    # flipped it on and restated an honest 0.870 as 0.767. `prices_withheld` is
    # the count this serializer actually nulled a line above, not a re-derivation,
    # so the gate can never disagree with the withholding it describes.
    #
    # THE HUB MOVES WITH IT, in `routes/league_futures.py`, which carries its own
    # copy of these two steps. Gating one surface and not the other would divide
    # the same board by two different numbers and manufacture exactly the
    # detail-vs-hub disagreement #7016 closed.
    if normalize_display_probs(
        outcomes,
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
        field_complete=prices_withheld == 0,
    ):
        _withhold_openings()
        openings_withheld = True
        # #4079 (N3), codex's scale ruling 2026-09-19: THE DATED MOVE CANNOT
        # SURVIVE THE SQUEEZE EITHER, AND FOR THE BLOCK ABOVE'S OWN REASON.
        #
        # The squeeze has just divided every printed `probability` by the field
        # sum. `probability_change_24h` above is raw − raw off the bank, which
        # holds a PRICE, so leaving it here reproduces exactly the harm #5835
        # named one statement earlier: two numbers on one row, on two scales,
        # and the reader invited to read one as the change in the other.
        #
        # Withheld rather than rescaled, for the same two reasons. Dividing the
        # delta by TODAY's sum asserts a historic DISPLAYED percent nobody
        # observed — the denominator moves whenever any leg moves — and no
        # column stores one. Codex ruled that arithmetic out by name. The
        # honest answer on a squeezed board is that there is no supported claim
        # about the change in the number on screen.
        #
        # ASKED OF THE SAME CALL, not re-derived: this rides
        # `normalize_display_probs`'s measured return, so the dated move and the
        # openings can never disagree about whether the column moved.
        #
        # Present and null, never omitted — the clients test `!== null` and
        # `undefined !== null` is true, so an omitted key would be read as a
        # number that never arrived rather than as a refusal.
        for o in outcomes:
            o["probability_change_24h"] = None
    # UX-P164: concept derivation reads the count this serializer saw BEFORE the
    # display drop, deliberately. `derive_market_concept_key` forwards it to the
    # combat adapters, which gate on `n_outcomes == 2` (`event_combat.py:245`,
    # `:356`) — so letting a DISPLAY rule feed it would let a dropped field row
    # flip a 3-outcome market into a fight-shaped one and invent a breadcrumb.
    # Display and identity are separate questions; this keeps the identity answer
    # bit-identical to today's.
    #
    # Captured HERE, not off `sorted_outcomes`: `normalize_display_probs` can
    # itself shorten the list (#1201 strips a run of exact-0.5 untraded midpoints
    # in place), so the pre-drop length is the only one that reproduces today's
    # `len(outcomes)` at this call site.
    #
    # #7274's expired rungs are ADDED BACK, and that is this comment's own rule
    # applied to a drop that now lands above this line rather than below it. A
    # date ladder is exactly the shape that can fall to two live rungs, and a
    # two-row count is what the combat adapters read as a fight — so letting the
    # expiry drop feed this would invent a breadcrumb on a river-level market.
    # The identity answer stays bit-identical to the one served before #7274.
    concept_outcome_count = len(outcomes) + expired_rungs_dropped

    # #4253: a single-winner field cannot have five different winners. Measured
    # live 2026-09-09, `/api/futures/12764689` (*Dancing with the Stars*) served
    # `Contestant 22 1.0 · Contestant 16 1.0 · Contestant 33 1.0 · Contestant 43
    # 1.0 · Contestant 45 1.0`, and `/api/futures/114045` led with `Goldman Sachs
    # 1.0` above four more banks at 1.0. `drop_dominant_field_outcomes` below is
    # name-gated and lets every one of them through — they are not field rows,
    # they are real candidates carrying a price nobody has written since May.
    #
    # AFTER `concept_outcome_count`, which is the identity answer and must stay
    # bit-identical (the comment above says why, and a display rule feeding it is
    # exactly what that comment forbids). This drop is display-only.
    #
    # AFTER `normalize_display_probs`, and here that is a no-op rather than a
    # judgement call: the predicate needs TWO legs at >= 0.95, whose raw sum is
    # already >= 1.9 — past `_FIELD_SUM_MAX` — so #1200 has always bailed this
    # field out to raw prices before this line is reached. The rule is inert on
    # every field the squeeze actually normalized, which bounds its blast radius
    # to the incoherent population it is for.
    #
    # Deliberately NOT re-normalizing the survivors afterwards. On 113419 (*Next
    # CEO of Apple?*) the three legs left behind are 0.0005 each; squeezing them to
    # sum ~100% would print three 33% contenders out of noise. We have no price for
    # that race, and saying so is the honest answer.
    outcomes = drop_incoherent_near_certain(
        outcomes,
        lambda o: o.get("probability"),
        mutually_exclusive=getattr(market, "mutually_exclusive", True),
        market_is_open=getattr(market, "status", None) == "open",
        is_winner_of=lambda o: bool(o.get("is_winner")),
    )

    # UX-P164 (#993's own opening sentence, still true here): demotion is not
    # enough on a SHORT list. `leader_pick_order` pushes a dominant field row to
    # "the end", which keeps it out of a top-N slot only while the list is longer
    # than N — and the detail page renders the WHOLE list, so "the end" is always
    # on the page. Measured live 2026-08-29, `/api/futures/112903` ("Which party
    # will win the House in 2026?") served exactly `Democratic Party 0.855 |
    # Republican Party 0.145 | Other 1.0`: a no-bid ask (gotcha #17/#19) printed
    # as "Other 100%" under two real answers, which is verbatim the defect #993
    # opened on and the one surface it was never fixed on.
    #
    # Ordering is deliberate and load-bearing in BOTH directions:
    #   - AFTER `normalize_display_probs`, because `_FIELD_DOMINANT_MIN` is
    #     documented as judging the number RENDERED, not the raw price. A field
    #     row that normalization squeezes below the threshold "genuinely carries
    #     most of the probability mass" and is INFORMATION — it must survive.
    #   - BEFORE `leader_pick_order`, so the two can never disagree about which
    #     rows they mean; both key off the same `_FIELD_DOMINANT_MIN`.
    # `drop_dominant_field_outcomes` NEVER EMPTIES, so an all-field market still
    # renders its list rather than a silent zero-outcome page.
    #
    # 🔴 #6110 — AND A SETTLED CHAMPION IS EXEMPT, BECAUSE THE RULE ABOVE IS
    # ABOUT A LIVE QUOTE. Everything UX-P164 argues is about a market still
    # being made: a no-bid `Other 1.0` is an ask nobody bids against, so it is
    # not an answer. Once the venue SETTLES the field, that same row is the
    # result. Measured on production 2026-09-15, minutes after the #6110 repair
    # ran: `futures_outcomes` for market 58675941 held 31 legs, exactly one
    # winner — `Other`, 1.0, `resolution_source='api_settlement'` — and this
    # line deleted it, so `/api/futures/58675941` served **30 outcomes and no
    # winner** and a finished Grand Tour still showed thirty riders who lost and
    # nobody who won. The data repair was complete and the page was unchanged.
    #
    # The predicate is stricter than the sibling's bare `is_winner` on purpose
    # (#4788, argued at the `resolution_source` key above): the column is
    # `boolean NULL DEFAULT false`, so a `True` beside a NULL source is a row
    # nobody graded, and this exemption should not be the one place that trusts
    # it. A settled field champion always carries a source.
    def _is_graded_winner(o: dict) -> bool:
        return bool(o.get("is_winner")) and o.get("resolution_source") is not None

    outcomes = drop_dominant_field_outcomes(
        outcomes,
        lambda o: o.get("name"),
        lambda o: o.get("probability"),
        is_winner_of=_is_graded_winner,
    )
    # The SAME predicate, and it has to be the same one: `leader_pick_order`
    # demotes a dominant field row to the END and then steps a named row over it,
    # so exempting the drop alone would have moved the champion of a finished race
    # from "deleted" to "last of 31, behind the page's fold". Half a carve-out.
    leader_pick_order(outcomes, is_winner_of=_is_graded_winner)

    # #2556: THE BADGES ARE NUMBERED HERE, FROM THE ORDER THE READER SEES, BECAUSE
    # THE STORED COLUMN IS NOT AN ORDERING. `rank` above is `o.rank` straight off
    # the row, and its fourteen ingest writers cannot keep it a permutation of the
    # board — the rule and its three mechanisms are on `assign_display_ranks`.
    # Production 2026-09-16: `/futures/40533` ran 11 inverted adjacent pairs of 31,
    # `/futures/1` printed `… 22, 19 …` in the tail Alex photographed five times,
    # and `/futures/113486` served **badge 1 twice on five rows**.
    #
    # LAST, and that is load-bearing in both directions. Every line above can still
    # change which rows are on the board (`drop_incoherent_near_certain`,
    # `drop_dominant_field_outcomes`) or where a tied row sits (`leader_pick_order`
    # reorders in place, and the client's stable sort preserves that order among
    # equal prices) — so numbering any earlier numbers a list the reader never
    # sees. And nothing below this line touches `outcomes`: the hook block reads
    # it, the return serves it.
    #
    # Prices and eligibility are untouched by design — this only overwrites the one
    # field whose whole job is to say where the row sits, using the list it sits in.
    assign_display_ranks(outcomes)

    # #5906: THE HOOK GOES THROUGH THE SAME GATE THE DISCOVER CARD HAS ALWAYS
    # USED. `routes/feed.py` has run every stored hook past `is_hook_stale`
    # since that module shipped; this serializer published `market.hook_
    # description` raw. One sentence, one reader, two answers — and nobody chose
    # that, which is why this is an adoption and not a new policy.
    #
    # WHAT A READER SAW. `/futures/8641774` (*Brazil Série B: Winner*) captioned
    # itself "Novorizontino has surged to the top" under a hero crowning
    # JUVENTUDE, over a table where Novorizontino's row read "—" because #5876
    # withheld its refuted midpoint. The stored hook is policy 1, 76 days old,
    # and names a superseded leader: it trips rules 0, 1 AND 2, and the feed had
    # been refusing it for months.
    #
    # REACH IS THE WHOLE POPULATION, MEASURED NOT ESTIMATED (production,
    # 2026-09-13): 11,444 open markets carry a hook, **0 are policy 2**, 10,629
    # are also past the 7-day age gate. So this empties the paragraph on
    # essentially every futures detail page, and that is the ship rather than a
    # side effect — every one of those sentences was written by the prompt #5461
    # retired for inventing developments our data does not support.
    #
    # THE COST WAS CHECKED ON THE CLIENTS BEFORE IT WAS TAKEN, and the two share
    # surfaces get BETTER: `app/futures/[id]/layout.tsx` (meta description) and
    # `opengraph-image.tsx` (share card) both already read
    # `market.hook_description || "<leader> leads <market> at <prob>"`, so a null
    # trades an invented sentence for a derived true one. The page body renders
    # the paragraph behind `{market.hook_description && ...}`, so nothing is left
    # to explain (notice 34 — never caption an emptiness).
    #
    # THE LEADER IS THE ONE THE HERO PRINTS, AND THAT IS NOT `outcomes[0]`.
    # Rules 2 and 3 compare the hook against the frontrunner THE READER SEES, so
    # the question has to be asked of the value the client crowns.
    #
    # This list is still in RAW `current_probability` order (the sort at the top
    # of this function); withholding nulls a price in place and never re-sorts,
    # so on the Brazil board `outcomes[0]` is Novorizontino — the withheld row,
    # carrying `probability: None`. Reading position 0 would hand rule 2 the
    # very leg the page refuses to price and report "no leader change".
    #
    # `app/futures/[id]/page.tsx:394` is explicit — *"The leader is always the
    # outcome with highest probability (independent of sort)"*, over
    # `(b.probability ?? 0) - (a.probability ?? 0)`. Mirrored here rather than
    # approximated: a withheld null reads as 0 and sinks, which is exactly the
    # behaviour the withhold block above already relies on.
    reader_leader = (
        max(outcomes, key=lambda o: o.get("probability") or 0) if outcomes else None
    )
    leader_name = reader_leader.get("name") if reader_leader else None
    leader_probability = reader_leader.get("probability") if reader_leader else None
    hook_description = market.hook_description
    hook_withheld = bool(hook_description) and (
        is_hook_stale(
            hook_description=hook_description,
            hook_generated_at=getattr(market, "hook_generated_at", None),
            hook_leader_at_generation=getattr(
                market, "hook_leader_at_generation", None
            ),
            current_leader_name=leader_name,
            current_leader_probability=leader_probability,
            market_metadata=getattr(market, "market_metadata", None),
        )
        # The caller supplies the names because only it knows which rows this
        # response refused — the same division of labour as `withheld` above.
        # Sourced from the FINAL list, so a leg dropped by the display pipeline
        # is not reported as "unpriced" on the strength of a row nobody serves.
        or hook_names_unpriced_outcome(
            hook_description=hook_description,
            unpriced_outcome_names=[
                o.get("name") for o in outcomes if o.get("probability") is None
            ],
        )
    )
    if hook_withheld:
        hook_description = None

    # B7 (L2-91): the up-link mesh. Resolve this market's event-concept key
    # (`event:<domain>:<slug>`, richer per-event page) and its competition hub slug
    # (`/hub/<slug>`) via the shared server-side resolver so the frontend breadcrumb
    # links UP without client-side slug guessing. Best-effort — a derivation slip
    # must never 500 the detail page (honest degrade to no breadcrumb).
    event_concept_key = None
    hub_slug = None
    category_page = None
    sport_page_key = None
    try:
        from app.utils.concept_links import (
            derive_market_category_page,
            derive_market_concept_key,
            derive_market_hub_slug,
            derive_market_sport_page_key,
        )

        event_concept_key = derive_market_concept_key(
            market.external_id,
            market.name,
            market.llm_sport_category,
            concept_outcome_count,  # UX-P164: pre-drop; see note above
        )
        hub_slug = derive_market_hub_slug(market.llm_sport_category)
        # L2-94: fallbacks below the hub — themed section page then hub-less sport
        # page. The frontend picks the first of concept/hub/category/sport that's set.
        category_page = derive_market_category_page(market.llm_sport_category)
        sport_page_key = derive_market_sport_page_key(
            market.sport.key if market.sport else None,
            market.llm_sport_category,
        )
    except Exception:
        pass

    return {
        "id": market.id,
        # #3513: the card and the page it links to must ask the SAME question.
        # `/api/feed` has served the cleaned name since #6267, so a reader who
        # tapped "Netflix (NFLX) closes week of Sep 14?" landed on an H1 reading
        # "…closes week of Sep 14 at ___?" — photographed on /futures/115349 at
        # 390px on 2026-09-15. This is the same display boundary, not a new one:
        # the clients that interpret this key (frontend `marketEventKey`,
        # `conceptDisplayLabel`) already receive the cleaned string from the feed
        # card payload, so the two surfaces now agree rather than diverge.
        "name": clean_market_display_name(market.name),
        "description": market.description,
        "sport": market.sport.key if market.sport else None,
        # #6444: `/api/futures/61182733` served `sport_name: "tennis_other"` —
        # the machine key printed where a league brand belongs. The web guards
        # this client-side (`servedSportNameIsRaw`), native does not, so the
        # only place the two tiers can be made to agree is here.
        "sport_name": (
            sport_display_name(market.sport.key, market.sport.name)
            if market.sport
            else None
        ),
        "category": market.category,
        "llm_sport_category": market.llm_sport_category,
        "status": market.status,
        "source": market.source,
        "external_id": market.external_id,
        # The shape field (#194 / market_shape.py). Every surface keys its render
        # kernel off this ONE value — see frontend/lib/marketShape.ts. It was
        # classified and stored but never served, so the detail page had no way to
        # dispatch and fell back to the generic ranked table for every shape.
        "market_type": market.market_type,
        "mutually_exclusive": market.mutually_exclusive,
        "commence_time": market.commence_time.isoformat() if hasattr(market, 'commence_time') and market.commence_time else None,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "outcomes": outcomes,
        "outcome_count": len(outcomes),
        # #5539: true when this field's openings were refused as incoherent, so a
        # probe can tell a withheld opening from one that never existed. Always
        # present so its absence means an old build, not a coherent field.
        "openings_withheld": openings_withheld,
        # #5611: how many outcomes had their price refused as unsupported by any
        # book or trade. A COUNT rather than a flag, so a probe can tell one
        # fabricated leg from a whole board of them without re-deriving the rule,
        # and so the 19 markets where this empties every price are findable.
        # Machine-readable only — notice 34 keeps diagnostics off the page.
        "prices_withheld": prices_withheld,
        # #7274: how many ladder rungs were dropped because their own deadline has
        # passed — the same rule and the same helper the Discover card applies, so
        # the two surfaces divide by one set. A COUNT rather than a flag, for
        # `prices_withheld`'s reason: an after-check can tell a board the rule
        # fired on from one that simply has no expired rung, without re-deriving
        # the rule. Machine-readable only — notice 34 keeps diagnostics off the
        # page. Always present, so its absence means an old build.
        "expired_rungs_dropped": expired_rungs_dropped,
        "bookmakers": bookmakers or [],
        "category_tags": market.category_tags or [],
        "created_at": market.created_at.isoformat() if market.created_at else None,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
        "group_id": market.group_id,
        "canonical_market_key": market.canonical_market_key,
        "hook_description": hook_description,
        # #5906: true when a stored hook existed and this response refused to
        # publish it, so a probe can tell suppression from a market that never
        # had prose. Machine-readable only — notice 34 keeps diagnostics off the
        # page, in a key like this, exactly as `prices_withheld` above.
        "hook_withheld": hook_withheld,
        "image_url": market.image_url,
        # B7 (L2-91): up-link mesh — concept page + competition hub (null where none).
        "event_concept_key": event_concept_key,
        "hub_slug": hub_slug,
        # L2-94: mesh fallbacks — themed section page then hub-less sport page.
        "category_page": category_page,
        "sport_page_key": sport_page_key,
    }


def _outcome_merge_key(outcome: FuturesOutcome) -> str:
    """
    Generate a merge key for cross-source outcome matching.

    Priority: team_id (most reliable) > normalized name (fallback).
    """
    if outcome.team_id:
        return f"team:{outcome.team_id}"
    # Normalize name for matching: lowercase, strip whitespace
    return f"name:{outcome.name.lower().strip()}"


def _outcome_merge_key_from_entry(entry: dict) -> str:
    """
    Reconstruct a merge key from a merged_outcomes entry dict.
    Used by cross-source-timeline to match entries back to merge keys.
    """
    if entry.get("team_id"):
        return f"team:{entry['team_id']}"
    return f"name:{entry['name'].lower().strip()}"


# ── Market Grouping Endpoints ──


@router.get("/groups/{group_id:path}")
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all markets in a specific group, with their outcomes.

    Returns markets sharing the same group_id, enriched with
    threshold detection and cross-source comparison data.
    """
    from app.utils.market_grouping import detect_threshold_groups

    # Fetch markets in this group
    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.group_id == group_id)
        .order_by(FuturesMarket.group_position.nulls_last(), FuturesMarket.id)
    )
    result = await db.execute(stmt)
    markets = result.scalars().all()

    if not markets:
        raise HTTPException(status_code=404, detail="Group not found")

    # Build market list
    market_list = []
    all_outcomes = []
    for m in markets:
        # #6993 — THE SAME REFUSAL THE DETAIL ROUTE SERVES FOR THIS MARKET. These
        # outcomes feed `threshold_groups` below, and for a threshold-shaped
        # market that ladder is the ONLY ladder the page draws (the detail
        # payload's own ladder stands down whenever `thresholdEntries` is
        # non-empty), so serving the raw column here did not duplicate the
        # withhold — it bypassed it. `/futures/109485` drew `≤ 24800  100%` off
        # this dict while the table beside it folded the same outcome away.
        #
        # `american_odds` is nulled with the price rather than recomputed from it
        # for the reason `WITHHELD_PRICE_FIELDS` states: it is the refused number
        # in another notation, and leaving it lets any consumer reconstruct
        # exactly the price this rule just refused.
        withheld = await _withheld_price_outcome_ids(db, m)
        outcomes = []
        # Sort on the SERVED value, not the stored one. Ordering by the raw column
        # would seat a withheld leg — `1597367` is a stored 1.0 — at the top of
        # the board with no number beside it, which is the withhold announcing
        # itself as a leader. Withheld rows sort as unpriced and sink, matching
        # `probability ?? 0` on the clients.
        for o in sorted(
            m.outcomes,
            key=lambda x: -(0 if x.id in withheld else (x.current_probability or 0)),
        ):
            od = {
                "id": o.id,
                "name": o.name,
                "probability": o.current_probability,
                "american_odds": probability_to_american(o.current_probability) if o.current_probability and 0 < o.current_probability < 1 else None,
                "market_id": m.id,
                "source": m.source,
            }
            if o.id in withheld:
                # Keyed on presence so the refusal covers any price field this
                # payload gains later, the way the detail arm's does.
                for field in WITHHELD_PRICE_FIELDS:
                    if field in od:
                        od[field] = None
            outcomes.append(od)
            all_outcomes.append(od)

        market_list.append({
            "id": m.id,
            "name": m.name,
            "source": m.source,
            "external_id": m.external_id,
            "group_type": m.group_type,
            "group_position": m.group_position,
            "canonical_market_key": m.canonical_market_key,
            # Shape field (#194) — same contract as the detail payload above.
            "market_type": m.market_type,
            "market_tier": m.market_tier,
            "llm_sport_category": m.llm_sport_category,
            "status": m.status,
            "market_metadata": m.market_metadata,
            "commence_time": m.commence_time.isoformat() if m.commence_time else None,
            "resolution_date": m.resolution_date.isoformat() if m.resolution_date else None,
            "outcomes": outcomes,
            "outcome_count": len(outcomes),
        })

    # Detect threshold groups across all outcomes
    threshold_groups = detect_threshold_groups(all_outcomes)

    # Determine group title from market metadata or market names
    group_title = None
    for m in markets:
        if m.market_metadata and m.market_metadata.get("event_title"):
            group_title = m.market_metadata["event_title"]
            break
    if not group_title and markets:
        group_title = markets[0].name

    return {
        "group_id": group_id,
        "group_title": group_title,
        "group_type": markets[0].group_type if markets else None,
        "market_count": len(market_list),
        "markets": market_list,
        "threshold_groups": {
            stem: [
                {
                    "outcome_id": o["id"],
                    "name": o["name"],
                    "probability": o["probability"],
                    "threshold_value": o["threshold_value"],
                    "threshold_unit": o["threshold_unit"],
                    "threshold_direction": o["threshold_direction"],
                    "source": o["source"],
                }
                for o in outcomes_list
            ]
            for stem, outcomes_list in threshold_groups.items()
        },
        "sources": list({m.source for m in markets}),
    }


@router.get("/groups")
async def list_groups(
    source: Optional[str] = Query(None, description="Filter by source (polymarket, kalshi)"),
    group_type: Optional[str] = Query(None, description="Filter by group type"),
    sport: Optional[str] = Query(None, description="Filter by sport category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List all market groups.

    Returns distinct group_ids with summary information.
    """
    # Subquery: get distinct group_ids with their first market's info
    filters = [FuturesMarket.group_id.isnot(None)]
    if source:
        filters.append(FuturesMarket.source == source)
    if group_type:
        filters.append(FuturesMarket.group_type == group_type)
    if sport:
        filters.append(FuturesMarket.llm_sport_category == sport)

    # Get distinct group_ids with count and representative market info
    stmt = (
        select(
            FuturesMarket.group_id,
            FuturesMarket.group_type,
            func.count(FuturesMarket.id).label("market_count"),
            func.min(FuturesMarket.name).label("representative_name"),
            func.min(FuturesMarket.id).label("representative_id"),
            func.array_agg(func.distinct(FuturesMarket.source)).label("sources"),
            func.max(FuturesMarket.updated_at).label("last_updated"),
        )
        .where(and_(*filters))
        .group_by(FuturesMarket.group_id, FuturesMarket.group_type)
        # Total order, same rule as `/browse` — but note this query is GROUPED,
        # so `FuturesMarket.id` is not available to break the tie (it is not in
        # the GROUP BY). The unique key of a grouped row is its grouping key,
        # which is why the tiebreak is the pair and not the PK.
        # No reader reaches this endpoint today — `fetchFuturesGroups` in
        # `frontend/lib/api.ts` has no callers — so it is fixed for the class,
        # not for a measured symptom, and it is the reason the recurrence guard
        # below can speak for the whole module instead of two routes.
        .order_by(
            func.max(FuturesMarket.updated_at).desc(),
            FuturesMarket.group_id,
            FuturesMarket.group_type,
        )
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Count total
    count_stmt = (
        select(func.count(func.distinct(FuturesMarket.group_id)))
        .where(and_(*filters))
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "groups": [
            {
                "group_id": row.group_id,
                "group_type": row.group_type,
                "market_count": row.market_count,
                "representative_name": row.representative_name,
                "representative_id": row.representative_id,
                "sources": row.sources or [],
                "last_updated": row.last_updated.isoformat() if row.last_updated else None,
            }
            for row in rows
        ],
    }
