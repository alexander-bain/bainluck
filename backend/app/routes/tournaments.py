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

from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
from app.tasks.tournament_matchup_linker import apply_resolved_links, read_links
from app.services import get_db
from app.utils.tournament_advancement import build_advancement
from app.utils.tournament_board import TREND_DAYS, build_boards
from app.utils.tournament_event_link import resolve_matchup_events
from app.utils.tournament_grid import build_grids
from app.utils.tournament_match import build_match_detail
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
REGISTERED_TOURNAMENTS: dict[str, dict[str, Any]] = {
    "us-open": {
        "season": "2026",
        "title": "US Open 2026",
        "subtitle": "Flushing Meadows",
        # ESPN's own name for this tournament on the tennis scoreboard, used to
        # select it out of a day that also carries Winston-Salem and Monterrey.
        # Named here rather than matched: same posture as the slug itself.
        "espn_event_name": "US Open",
        # WHICH `events` ROWS BELONG TO THIS CONTAINER (UX-P152). Named, never
        # inferred from the slug — same posture as `espn_event_name` above.
        # This is what makes the "is this event in a tournament" question cost
        # one indexed read for the ~99.99% of events whose answer is no; an
        # event page for a Lakers game must not pay for the US Open being on.
        # Measured 2026-08-28: 47 + 47 main-draw singles events under these two
        # keys, created by the Odds API ingest on 2026-08-27.
        "sport_keys": ("tennis_atp_us_open", "tennis_wta_us_open"),
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

#: Bounds one match page's sibling scan. A Polymarket tennis event carries ~12
#: sub-markets and ~33 outcome rows; 400 is generous by an order of magnitude
#: and exists so a source that starts listing hundreds cannot turn a page
#: request into an unbounded read. Truncation is reported, never silent —
#: `build_match_detail` counts it as `OVER_CAP`.
MAX_MATCH_GROUP_ROWS = 400


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


async def _with_link_overlay(
    slug: str, register: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """The Q426 link overlay, for callers other than the hub.

    Same read the hub does inline, in one place, because a surface that did not
    apply it would contradict the list it was reached from: on the 96 R128
    fixtures the hub would print a probability and the other surface would say
    no market exists — two surfaces disagreeing about one question, which is
    the divergence the standing ruling exists to prevent.

    Never a gate. A linker outage falls back to the committed register, which
    is where the page stood before the overlay existed.

    Returns the register (never mutated in place — gotcha #6: a module-level
    cached dict edited in place leaks one request's overlay into the next) and
    how many blocks were filled.
    """
    try:
        links = (await read_links(slug)).get("links") or {}
        return apply_resolved_links(register, links)
    except Exception as exc:  # noqa: BLE001 — an overlay is never a gate
        logger.warning("tournament link overlay unavailable for %s: %s", slug, exc)
        return register, 0


async def _load_match_group(
    session: AsyncSession, *, winner_market_id: int
) -> tuple[Optional[str], list[dict[str, Any]]]:
    """The sibling markets that share this match's group — id-anchored, no matching.

    ONE HOP, AND IT IS AN INDEX LOOKUP ON A PRIMARY KEY FOLLOWED BY ONE ON
    ``group_id`` (indexed).  The register pins the match-winner market's id; the
    source has already put every prop for that match in the same group.  There
    is no name comparison, no time window and no category test on this path,
    which is the same posture as the register and the reason lane1 could hand
    the surface over without handing over a matching problem with it.

    TWO MARKETS ARE EXCLUDED, FOR DIFFERENT REASONS:

    * **The match-winner market itself** — it is the hero above, not a prop.
    * **The event container.**  Every Polymarket event carries a synthetic
      parent holding one outcome per member, so rendering it would print the
      whole page a second time as a single field.  It is identified by the id
      equality ``group_id == "{source}:{external_id}"`` — exact, and immune to
      the classifier drift that makes ``market_type == 'field'`` the wrong
      test (a genuine Exact Score prop is also a field).
    """
    group_id = (
        await session.execute(
            select(FuturesMarket.group_id).where(FuturesMarket.id == winner_market_id)
        )
    ).scalar_one_or_none()
    if not group_id:
        return None, []

    rows = (
        await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.source,
                FuturesMarket.external_id,
                FuturesOutcome.id.label("outcome_id"),
                FuturesOutcome.name.label("outcome_name"),
                FuturesOutcome.external_id.label("outcome_external_id"),
            )
            .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
            .where(FuturesMarket.group_id == group_id)
            .order_by(FuturesMarket.id, FuturesOutcome.id)
            .limit(MAX_MATCH_GROUP_ROWS)
        )
    ).all()

    markets: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.id == winner_market_id:
            continue
        if group_id == f"{row.source}:{row.external_id}":
            continue
        entry = markets.setdefault(
            row.id, {"market_id": row.id, "name": row.name, "outcomes": []}
        )
        entry["outcomes"].append({
            "outcome_id": row.outcome_id,
            "name": row.outcome_name,
            "external_id": row.outcome_external_id,
        })
    return group_id, list(markets.values())


@router.get("/by-event/{event_id}")
async def get_event_tournament(
    event_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """A standard event's tournament extensions — advancement, and the props.

    ``GET /api/tournaments/by-event/{event_id}``

    ═══ WHY THIS REPLACED A MATCH-PAGE ROUTE ═══

    Alex, 2026-08-28, on the UX-P149 artifact: *"It seems like we're reinventing
    the event page here"*, and then the architecture note: *"I thought that
    tournaments were containers for related events."*

    That is the ruled model and it is what the database holds.  UX-P149 built a
    bespoke match surface on the premise that a tennis matchup has no ``events``
    row; that premise expired at **2026-08-27 21:05 UTC**, when the Odds API
    began carrying US Open main-draw singles and 94 standard events appeared for
    the 96 registered R128 fixtures.  So there is no match page: a match is an
    event, it renders on ``/events/{id}`` with the probability-over-time graph
    and every other thing an event page does, and the tournament adds two
    sections **to** that page.  This endpoint is those two sections.

    ═══ THE CHEAP NO ═══

    The event page asks this about every event it renders, so the ``no`` has to
    cost almost nothing.  One indexed read of the event's sport key answers it:
    a sport key no registered tournament claims returns ``{"tournament": null}``
    without loading a register, building a hub payload, or touching Redis.  A
    Lakers game must not pay for the US Open being on.

    ``{"tournament": null}`` and not a 404: "this event is not part of a
    tournament" is the ordinary answer for almost every event on the site, and
    an error status for the ordinary answer is how a health check learns to
    ignore a real one.
    """
    from app.models.models import Event, Sport  # noqa: PLC0415

    row = (
        await db.execute(
            select(Sport.key, Event.home_team_name, Event.away_team_name)
            .join(Event, Event.sport_id == Sport.id)
            .where(Event.id == event_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    sport_key, home_team_name, away_team_name = row

    slug = next(
        (
            s for s, spec in REGISTERED_TOURNAMENTS.items()
            if sport_key in spec.get("sport_keys", ())
        ),
        None,
    )
    if slug is None:
        return {"event_id": event_id, "tournament": None}

    spec = REGISTERED_TOURNAMENTS[slug]
    hub = await _hub_payload(slug, spec, db)

    matchup_key = ((hub.get("event_links") or {}).get("by_event") or {}).get(
        str(event_id)
    )
    if not matchup_key:
        # The tournament is on and this event is one of its sport keys, but no
        # registered fixture dereferences to it. An honest null: the register
        # pins identity and this event is not one of the things it pins. Never
        # a name match on the two player names sitting right there — that is
        # precisely the shortcut `tournament_event_link` exists to refuse.
        return {"event_id": event_id, "tournament": None, "reason": "NOT_IN_REGISTER"}

    register = load_register(slug, spec["season"])
    if register is None:
        logger.error("registered tournament %s has no readable register", slug)
        raise HTTPException(status_code=503, detail="Tournament register unavailable")
    register, _linked = await _with_link_overlay(slug, register)

    reg = TournamentRegister(register)
    matchup = next(
        (m for m in reg.matchups if str(m.get("matchup_key")) == matchup_key), None
    )
    if matchup is None:
        # The cached hub and the freshly loaded register disagree — the register
        # was replaced between the two reads. Not an error and not a guess.
        logger.warning(
            "event %s maps to matchup %s which the register no longer holds",
            event_id, matchup_key,
        )
        return {"event_id": event_id, "tournament": None, "reason": "REGISTER_MOVED"}

    # ── EACH PLAYER'S CHANCE OF REACHING EACH LATER ROUND (Alex's item 2) ──
    # A slice of the hub's own `grids`, so this strip and the tournament page's
    # playoff grid cannot print different numbers for one cell.
    advancement = build_advancement(
        hub.get("grids") or {},
        matchup=matchup,
        event_id=event_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        tournament_title=spec["title"],
        tournament_slug=slug,
    )

    # ── THE MATCH'S OTHER QUESTIONS (Alex's item 3) ──
    # UX-P149's grouping, kept whole: the register pins the match-winner
    # market's id, the source has already put every prop for the match in the
    # same `group_id`, and one indexed lookup returns them. No name comparison,
    # no time window, no category test.
    block = next(
        (
            b for b in (matchup.get("sources") or [])
            if isinstance(b, dict) and b.get("status") == "live"
        ),
        None,
    )
    winner_market_id = (block or {}).get("market_id")

    prop_markets: list[dict[str, Any]] = []
    if isinstance(winner_market_id, int):
        _group_id, prop_markets = await _load_match_group(
            db, winner_market_id=winner_market_id
        )

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
            if isinstance(outcome.get("outcome_id"), int)
        }
    )
    now = datetime.now(timezone.utc)
    prices = await _load_prices(db, outcome_ids)

    decided = build_results(
        register, results=await _espn_results(slug), prices=prices
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

    return {
        "event_id": event_id,
        "tournament": {
            "slug": slug,
            "title": spec["title"],
            "url": f"/tournaments/{slug}",
        },
        "matchup_key": matchup_key,
        "round": matchup.get("round"),
        "draw_label": (hub.get("grids") or {}).get(matchup.get("draw"), {}).get("label"),
        "advancement": advancement,
        # `detail` is None only when the register holds the matchup but cannot
        # render it as a row (an unmapped side). The extensions then carry the
        # advancement alone rather than 404-ing a page that is otherwise fine —
        # this is a SECTION of an event page, not the page.
        "props": (detail or {}).get("props") or [],
        "props_count": (detail or {}).get("props_count") or 0,
        "props_dropped": (detail or {}).get("props_dropped") or {},
        "decided": bool((detail or {}).get("decided")),
        "result": (detail or {}).get("result"),
        "broadcasts": reg.broadcasts,
        "generated_at": now.isoformat(),
    }


async def _hub_payload(
    slug: str, spec: dict[str, Any], db: AsyncSession
) -> dict[str, Any]:
    """The tournament hub payload — built once, read by every tournament surface.

    Extracted from ``get_tournament`` by UX-P152 so the event page's tournament
    extensions come out of **the same object** the hub renders, rather than out
    of a second assembly that agrees today.  The advancement strip on
    ``/events/{id}`` is a slice of ``payload["grids"]``; if it were built from a
    second read of the register, one surface could print a cell the other did
    not, which is the divergence the standing ruling exists to prevent.

    It also means the extensions endpoint costs a dict lookup on a warm cache
    instead of a second full build.
    """
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

    # THE FIXTURES THE CENSUS FOUND NO MARKET FOR, LINKED SINCE (Q426), AND
    # THE FIRST HOP OF THE ROUTE TO AN EVENT PAGE (UX-P152).
    #
    # The draw census ran once, at the ceremony, and recorded `status:
    # "missing"` against all 96 R128 fixtures because nobody quotes a first
    # round before qualifying finishes. By the next morning Kalshi quoted every
    # one of them and the register still said there was no market, so the cards
    # rendered blank while we held the prices.
    #
    # `tournament_matchup_linker` re-asks that question on a beat and writes
    # what it finds; this reads it. Two properties make it safe to apply here
    # rather than being the fuzzy request-time matching this module's docstring
    # forbids: the resolution already happened in a task (this is a dict lookup
    # of a pinned `(market_id, outcome_id)`, the same kind of read as the
    # committed file), and `apply_resolved_links` may only replace a block the
    # register itself marked `missing`. A curated pin is untouchable from here.
    #
    # UX-P152 gave the overlay a SECOND job. The `market_id` it fills in is the
    # first hop of the id-anchored path to an `events` row
    # (`tournament_event_link`), so without it every R128 fixture resolves
    # `NO_PINNED_MARKET` and the whole main draw loses its click-through in the
    # week it starts. That does not change the posture below: an overlay outage
    # costs some cards their numbers and their link, never the page.
    #
    # Wrapped, and the bare `except` is the point: the overlay is an
    # optimisation over the committed truth and must never be a gate. Falling
    # back leaves the page exactly as the register wrote it, which is where it
    # stood before this existed.
    linked = 0
    try:
        links = (await read_links(slug)).get("links") or {}
        register, linked = apply_resolved_links(register, links)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tournament link overlay failed for %s: %s", slug, exc)

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

    # WHICH `events` ROW EACH FIXTURE IS (UX-P152, Alex's architecture note:
    # "I thought that tournaments were containers for related events"). One
    # id-anchored query, resolved BEFORE the slate is built so a match row
    # carries its event id and the card can route to the standard event page
    # like any other game card. Never a name match — see
    # `utils/tournament_event_link`.
    event_links = await resolve_matchup_events(db, register)

    payload = build_boards(
        register, prices=by_identity, series_by_outcome=series, now=now
    )
    payload["slate"] = build_slate(
        register, prices=prices, now=now, event_ids=event_links["by_matchup"]
    )
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
    # `prices` so a finished match can print what the market said BEFORE it
    # (UX-P146, Alex on the UX-P145 artifact). No extra query: the matchup
    # outcome ids are already in the one `IN (...)` above, and the number used
    # is `opening_probability`, which is loaded on the same row.
    payload["results"] = build_results(
        register, results=await _espn_results(slug), prices=prices
    )
    payload["broadcasts"] = reg.broadcasts
    # How many blank fixtures the overlay filled this request. Reported rather
    # than inferred: a page whose cards are dark because no market exists and
    # one whose cards are dark because the linker died look identical from the
    # outside, and that is the exact confusion that let this ship broken for a
    # day (gotcha #53).
    payload["auto_linked_matchups"] = linked
    payload["slug"] = slug
    payload["title"] = spec["title"]
    payload["subtitle"] = spec["subtitle"]
    # WHEN THE DRAW HAPPENS (Alex's item 1). The pre-draw panel says the date
    # and the time, not just that it has not happened yet.
    payload["draw_release_at"] = spec["draw_release_at"]
    payload["draw_release_label"] = spec["draw_release_label"]
    payload["main_draw_starts_at"] = spec["main_draw_starts_at"]
    payload["main_draw_label"] = spec["main_draw_label"]
    # NO SILENT CAPS. `by_event` is what `/by-event/{id}` reads; the reason
    # counts are what makes a fixture with no click-through a named gap rather
    # than a row that quietly stopped being a link.
    payload["event_links"] = {
        # JSON has no integer keys and this payload round-trips through Redis,
        # so the id side is stringified HERE rather than at each reader.
        "by_event": {str(k): v for k, v in event_links["by_event"].items()},
        "by_matchup": event_links["by_matchup"],
        "linked": len(event_links["by_matchup"]),
        "unresolved": event_links["reason_counts"],
    }

    await _cache_set(slug, payload)
    return payload


@router.get("/{slug}")
async def get_tournament(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    spec = REGISTERED_TOURNAMENTS.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"No registered tournament '{slug}'")
    return await _hub_payload(slug, spec, db)
