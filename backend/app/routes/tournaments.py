"""Tournament hub endpoint — the US Open championship boards.

``GET /api/tournaments/{slug}``

The register is the single source of page truth (US Open charter, 2026-08-25).
This route therefore does exactly three things: resolve the slug to a committed
register, load prices for the identities that register pins, and hand both to
``app.utils.tournament_board``.  There is no matching, no fuzzy lookup and no
name normalization on this path — which is the entire point of the register
pattern, and what makes the page immune to the ``llm_sport_category`` /
``llm_gender`` contamination the Day-1 census measured (#2200).

**The slug does not infer.**  An unregistered slug is a 404, never a
best-effort nearest tournament.  Ruling 031's disease — choosing a different
tournament because its draw was bigger — cost the US Open its own page once
already (#1793); the floor that prevents it is the absence of a fallback, not a
cleverer scorer.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuturesOddsSnapshot, FuturesOutcome
from app.services import get_db
from app.utils.tournament_board import TREND_DAYS, build_boards
from app.utils.tournament_grid import build_grids
from app.utils.tournament_register import TournamentRegister, load_register
from app.utils.tournament_slate import (
    build_bracket,
    build_props,
    build_results,
    build_slate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Explicit, not derived. A tournament is servable because someone committed a
# register for it and wrote the season down here — never because a slug parsed.
REGISTERED_TOURNAMENTS: dict[str, dict[str, str]] = {
    "us-open": {
        "season": "2026",
        "title": "US Open 2026",
        "subtitle": "Flushing Meadows",
        # ESPN's own name for this tournament on the tennis scoreboard, used to
        # select it out of a day that also carries Winston-Salem and Monterrey.
        # Named here rather than matched: same posture as the slug itself.
        "espn_event_name": "US Open",
        # The main-draw ceremony, in the tournament's own local time. Alex's
        # item 1: the pre-draw panel must say WHEN, not just that it has not
        # happened. Register-adjacent rather than register-owned because it is
        # a fact about the calendar, not about a market identity.
        "draw_release_at": "2026-08-27T12:00:00-04:00",
        "draw_release_label": "Thursday 27 August, 12:00 ET",
        "main_draw_starts_at": "2026-08-30T11:00:00-04:00",
        "main_draw_label": "Sunday 30 August",
    },
}

# Where `sync_tournament_results` writes and this route reads. The TTL is
# generous relative to the 3-minute refresh so a single missed task run does not
# blank the section; a genuinely dead task lets it expire, which is the honest
# outcome (an empty section with a stated reason beats an hour-old result
# presented as current).
RESULTS_TTL_SECONDS = 900
RESULTS_PREFIX = "bainluck:tournament-results:"

# Short, and deliberately not a 24h mirror. #1767 shipped a league route that
# rebuilt once per 24h and served the stale copy for the other 23h55m; a page
# whose whole subject is freshness must not inherit that shape. Sixty seconds
# absorbs a burst without ever being the reason a number is old.
CACHE_TTL_SECONDS = 60
CACHE_PREFIX = "bainluck:tournament:"

# Bounds the per-request series scan. The register pins ~160 outcomes; at hourly
# capture over TREND_DAYS that is well inside this, and the cap is here so a
# capture-rail change cannot silently turn this route into a table scan.
MAX_SERIES_ROWS = 20000


def _cache_key(slug: str) -> str:
    return f"{CACHE_PREFIX}{slug}"


async def _cache_get(slug: str) -> Optional[dict[str, Any]]:
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(_cache_key(slug))
        if raw:
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — cache is an optimisation, never a gate
        logger.warning("tournament cache read failed for %s: %s", slug, exc)
    return None


async def _cache_set(slug: str, payload: dict[str, Any]) -> None:
    try:
        from app.tasks.redis_state import get_async_redis_client

        await get_async_redis_client().setex(
            _cache_key(slug), CACHE_TTL_SECONDS, json.dumps(payload, default=str)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tournament cache write failed for %s: %s", slug, exc)


async def _espn_results(slug: str) -> dict[str, Any]:
    """ESPN tennis results for one tournament — READ FROM CACHE, never fetched.

    THE SHAPE MATTERS MORE THAN THE FEATURE.  Everything else on this page comes
    out of our own database; results do not, because nothing in our database
    holds the result of a tennis match (checked 2026-08-26: zero ``events`` rows
    for any of the register's matchups).  So there is a fetch — and it does not
    live here.

    The first draft fetched inside the request, with a Redis cache in front of
    it.  That is the same shape the feed's standing rule forbids by name
    ("never run LLM calls inside ``GET /api/feed``"), and for the same reasons:
    the first request after every TTL expiry pays a third-party round trip, a
    slow ESPN makes a slow page for somebody, and a route contract test starts
    making live network calls.  ``sync_tournament_results`` (every 3 minutes,
    background queue) does the fetching; this only reads.

    A cold or empty cache yields an empty results section and the rest of the
    page.  Never a partial page, never a 503, and never a fabricated score.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(f"{RESULTS_PREFIX}{slug}")
        if raw:
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — a results section is not a gate
        logger.warning("tournament results cache read failed for %s: %s", slug, exc)
    return {"draws": {}, "stats": {}, "errors": []}


async def _load_prices(
    session: AsyncSession, outcome_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """Current price + the time it was last actually OBSERVED, per outcome.

    Freshness comes from ``futures_odds_snapshots.captured_at`` and never from
    ``futures_outcomes.last_updated``.  The Day-1 census measured the latter at
    a month stale on the Polymarket men's field while its snapshots ran current
    — a page that trusted it would report confidence it does not have.
    """
    if not outcome_ids:
        return {}

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
                # The SCRIPT. Loaded here rather than in a second query because
                # the slate's move is only meaningful against the same row's own
                # opening price.
                FuturesOutcome.opening_probability,
            ).where(FuturesOutcome.id.in_(outcome_ids))
        )
    ).all()

    observed = (
        await session.execute(
            select(
                FuturesOddsSnapshot.outcome_id,
                sqlfunc.max(FuturesOddsSnapshot.captured_at).label("observed_at"),
            )
            .where(
                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                FuturesOddsSnapshot.probability.isnot(None),
            )
            .group_by(FuturesOddsSnapshot.outcome_id)
        )
    ).all()
    observed_by_id = {row.outcome_id: row.observed_at for row in observed}

    return {
        row.id: {
            "probability": (
                float(row.current_probability)
                if row.current_probability is not None
                else None
            ),
            "opening_probability": (
                float(row.opening_probability)
                if row.opening_probability is not None
                else None
            ),
            "observed_at": observed_by_id.get(row.id),
            "source_name": row.name,
        }
        for row in rows
    }


async def _load_series(
    session: AsyncSession, outcome_ids: list[int], *, now: datetime
) -> dict[int, list[tuple[str, float]]]:
    """Daily mean per outcome — the raw material for an unsmoothed trend line.

    Meaning within one outcome-day is a summary of *one source's own readings*,
    which is not a cross-source blend and does not touch the blend rule. The
    cross-source step happens once, in ``tournament_board``, so there is exactly
    one place where "the number" is decided.
    """
    if not outcome_ids:
        return {}

    cutoff = now - timedelta(days=TREND_DAYS)
    day = sqlfunc.date_trunc("day", FuturesOddsSnapshot.captured_at).label("day")
    rows = (
        await session.execute(
            select(
                FuturesOddsSnapshot.outcome_id,
                day,
                sqlfunc.avg(FuturesOddsSnapshot.probability).label("probability"),
            )
            .where(
                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                FuturesOddsSnapshot.captured_at >= cutoff,
                FuturesOddsSnapshot.probability.isnot(None),
            )
            .group_by(FuturesOddsSnapshot.outcome_id, day)
            .order_by(FuturesOddsSnapshot.outcome_id, day)
            .limit(MAX_SERIES_ROWS)
        )
    ).all()

    series: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        if row.probability is None or row.day is None:
            continue
        series[row.outcome_id].append((row.day.date().isoformat(), float(row.probability)))
    return dict(series)


@router.get("/{slug}")
async def get_tournament(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    spec = REGISTERED_TOURNAMENTS.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"No registered tournament '{slug}'")

    cached = await _cache_get(slug)
    if cached is not None:
        return cached

    register = load_register(slug, spec["season"])
    if register is None:
        # A slug we claim to serve whose register will not load. Honest empty,
        # never a partial page assembled from whatever the database happened to
        # have — that is precisely what the register pattern replaces.
        logger.error("registered tournament %s has no readable register", slug)
        raise HTTPException(status_code=503, detail="Tournament register unavailable")

    reg = TournamentRegister(register)
    board_outcome_ids = sorted(
        {
            block["outcome_id"]
            for player in reg.players
            for block in (player.get("sources") or [])
            if isinstance(block, dict) and isinstance(block.get("outcome_id"), int)
        }
    )
    # The slate's identities are pinned on the MATCHUPS, not on player entries —
    # a qualifying participant has no player-level source by construction. Both
    # sets are bounded by the register, so this stays two id-list lookups rather
    # than becoming a scan.
    slate_outcome_ids = reg.matchup_outcome_ids()
    prop_outcome_ids = reg.prop_outcome_ids()
    # The playoff grid's 336 pinned reach identities (UX-P139). Bounded by the
    # register like every other set here, so adding a whole grid to this page
    # adds one more id list to an `IN (...)` and never a scan.
    reach_outcome_ids = reg.reach_outcome_ids()

    now = datetime.now(timezone.utc)
    prices = await _load_prices(
        db,
        sorted(
            set(board_outcome_ids)
            | set(slate_outcome_ids)
            | set(prop_outcome_ids)
            | set(reach_outcome_ids)
        ),
    )
    # Trend lines are a board feature. Loading series for the slate's ~130
    # outcomes would triple the per-request scan to draw nothing.
    series = await _load_series(db, board_outcome_ids, now=now)

    # Re-key the loaded prices onto the register's identity tuple. Anything the
    # query returned that the register does not pin simply has no key here and
    # cannot reach a board.
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

    payload = build_boards(
        register, prices=by_identity, series_by_outcome=series, now=now
    )
    payload["slate"] = build_slate(register, prices=prices, now=now)
    payload["props"] = build_props(register, prices=prices, now=now)
    # THE PLAYOFF GRID (UX-P139). Built server-side, from `reaches` and the
    # boards, because the amendment makes cell provenance a correctness
    # property: the grid must read the register and only the register, and a
    # client assembling cells from three payload sections cannot be held to
    # that. It also puts the two evals — column sums and monotonicity — next to
    # the data they judge instead of in a component.
    payload["grids"] = build_grids(
        register, boards=payload.get("boards") or [], prices=prices, now=now
    )
    # THE FIXTURE SWAP (UX-P134). Empty until the draw ceremony latches
    # `draw_released`; populated by the same `ingest_tournament_draw.py` run, so
    # Thursday is a data change and not a deploy.
    payload["bracket"] = {
        draw: build_bracket(register, prices=prices, draw=draw)
        for draw in ("mens-singles", "womens-singles")
    }
    # Where to watch — a static per-tournament mapping, register-owned so it can
    # be corrected without a deploy. Served verbatim; there is nothing to
    # compute and nothing to get wrong at request time.
    # DECIDED MATCHES, WITH THE SCORE (UX-P139, Alex's item 9). A separate
    # section rather than a field on the slate, because a slate structurally
    # cannot hold a finished match — see `build_results`.
    payload["results"] = build_results(register, results=await _espn_results(slug))
    payload["broadcasts"] = reg.broadcasts
    payload["slug"] = slug
    payload["title"] = spec["title"]
    payload["subtitle"] = spec["subtitle"]
    # WHEN THE DRAW HAPPENS (Alex's item 1). The pre-draw panel says the date
    # and the time, not just that it has not happened yet.
    payload["draw_release_at"] = spec["draw_release_at"]
    payload["draw_release_label"] = spec["draw_release_label"]
    payload["main_draw_starts_at"] = spec["main_draw_starts_at"]
    payload["main_draw_label"] = spec["main_draw_label"]

    await _cache_set(slug, payload)
    return payload
