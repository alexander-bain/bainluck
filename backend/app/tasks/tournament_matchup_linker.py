"""Re-ask the question the draw census only asked once (Q426).

``ingest_tournament_draw.py`` wrote 96 US Open R128 fixtures into the register
at the ceremony and recorded ``status: "missing"`` against both sources,
because at that instant neither carried a match market.  That was true.  It
stopped being true the next morning and nothing noticed, so the R128 cards
rendered without probabilities while Kalshi quoted every one of them.

This task asks again, on a beat.  It reads the committed register, finds the
fixtures whose market is recorded as absent, looks for one in our own tables,
and writes what it finds to Redis for ``routes/tournaments.py`` to overlay.

**It does not write the register.**  That file is committed to git and reviewed
as code, and the register sentinel's doctrine — a task must not rewrite the
page's source of truth at 07:45 UTC — is unchanged.  What this writes is an
overlay with a TTL, applied only to blocks the register itself marked
``missing``, so the committed file remains the only thing that can pin, move or
retire an identity.  The overlay's whole power is to fill a blank.

The shape is deliberately the one this page already uses: ``sync_tournament_
results`` fetches into Redis and the route only ever reads.  No request pays for
this, and nothing about the register pattern's request-time guarantee changes.

Cheap by construction.  One indexed query per tournament bounded by an explicit
series list and a row cap, then pure in-memory resolution over at most a few
hundred candidates.  No third-party calls at all — the markets are already ours
by the time this runs.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.utils.tournament_link_resolver import (
    REFUSAL_CODES,
    apply_resolved_links,
    resolve_authority_links,
    resolve_matchup_links,
)
from app.utils.tournament_register import load_register

logger = logging.getLogger(__name__)

#: Where this writes and ``routes/tournaments.py`` reads.
LINKS_PREFIX = "bainluck:tournament-links:"

#: Long relative to the 5-minute beat, so one missed run never blanks a card
#: that was already lit, but finite so a genuinely dead task lets the links
#: expire rather than pinning yesterday's market forever. The register's own
#: `missing` state is what the page falls back to, which is exactly where it
#: was before this existed — the honest state, not a stale one.
LINKS_TTL_SECONDS = 3600

#: One entry per tournament whose register this may fill, with the Kalshi
#: series that carry its match markets.
#:
#: Explicit, not derived — the same posture as ``REGISTERED_TOURNAMENTS`` in the
#: route and ``WATCHED`` in the sentinel. A resolver that inferred its own
#: candidate pool from the register would be one bad inference away from
#: scanning ``futures_markets`` unbounded, and the series names are three words
#: a human can check against the exchange.
WATCHED: tuple[dict[str, Any], ...] = (
    {
        "tournament": "us-open",
        "season": "2026",
        # Measured 2026-08-28: 47 KXATPMATCH + 49 KXWTAMATCH open events for the
        # main draw, which is exactly the 96 registered R128 fixtures.
        "kalshi_series": ("KXATPMATCH", "KXWTAMATCH"),
    },
)

#: Hard cap on candidate market rows per tournament. The recency window below
#: already bounds this to the high hundreds; the cap is here so a series rename
#: upstream cannot quietly turn this into a table scan.
MAX_CANDIDATE_MARKETS = 2000

#: How far back a candidate match market may have been ingested (ux/1033).
#:
#: ═══ THE CAP WAS TRUNCATING THE WRONG END, AND SILENTLY ═══
#:
#: ``KXATPMATCH``/``KXWTAMATCH`` is not "the low hundreds": measured on
#: production 2026-09-02, the two series hold **5,113 rows going back to
#: 2026-02-19**.  The predicate above had no ``ORDER BY``, so ``LIMIT 2000`` took
#: whichever 2,000 the scan reached first — physical order, which is insertion
#: order, which is OLDEST FIRST.  Measured against the live table, the surviving
#: pool's newest ticker date was ``26MAR20``: **not one September market was in
#: it**, and the resolver's one-day window then refused every fixture of the
#: tournament actually being played.  Both halves of this task were affected —
#: the register's ``missing`` blocks and the authority links alike — and the
#: symptom was the one lane1/047 named as the worst a probability product has: a
#: card reading "nobody is quoting this match" over a market we hold open.
#:
#: That is gotcha #41 exactly: an unordered sweep over a growing population
#: processes the dead first.  The fix is a bound with a MEANING rather than a
#: bigger number — the resolver only ever matches a candidate within one day of
#: the fixture, so a market ingested a fortnight ago cannot be the answer to any
#: question this task asks.  Measured on the same table: 546 rows in the last 7
#: days, 589 in 14, 1,122 in 30 — so 14 days sits an order of magnitude inside
#: the cap while covering, four times over, the two-day lead Kalshi actually
#: publishes a slam's match markets on (26AUG30's tickers were created 26AUG28).
#:
#: The cap survives as the backstop it was meant to be, and hitting it is now
#: LOUD (gotcha #53): a truncated pool is reported and logged, never inferred
#: from a resolver that quietly refused everything.
CANDIDATE_WINDOW_DAYS = 14

#: Inner deadline, comfortably under the task's soft limit so the run always
#: reaches its own terminal rather than being SIGKILLed untracked (#966).
DEADLINE_SECONDS = 120.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _match_date(external_id: Optional[str]):
    """The calendar date a Kalshi match ticker embeds, or None.

    ``KXATPMATCH-26AUG30YIBWAL`` → ``2026-08-30``. Total: an unparseable ticker
    yields None and the resolver's window check then fails closed on it.
    """
    if not external_id:
        return None
    try:
        from app.utils.prediction_market_matching import extract_game_date_from_ticker

        parsed = extract_game_date_from_ticker(external_id)
    except Exception:  # noqa: BLE001 — a ticker parse must never fail a beat
        return None
    return parsed.date() if parsed is not None else None


def candidate_query(series: tuple[str, ...], *, now: datetime):
    """The one statement that decides which markets this task can ever see.

    Extracted from ``_load_candidates`` by ux/1033 so a guard can assert on the
    statement that RUNS rather than on a stubbed row list. Every existing test of
    this task monkeypatches ``_load_candidates`` whole, which is exactly why an
    unordered ``LIMIT`` over a 5,113-row table went six months unnoticed: no test
    had ever looked at the query, and every symptom downstream of it — refusals,
    ``resolved: 0``, an unpriced card — is indistinguishable from "the market
    does not exist".

    Three clauses and each is load-bearing:

    * the series prefix, which is the explicit pool ``WATCHED`` names;
    * ``created_at`` inside ``CANDIDATE_WINDOW_DAYS``, which is the bound with a
      MEANING — the resolver only matches within one day of the fixture, so an
      older row cannot be an answer;
    * ``ORDER BY id DESC``, so that if the cap ever does fire it truncates the
      dead tail and not the live head (gotcha #41).
    """
    from sqlalchemy import or_

    from app.models import FuturesMarket

    return (
        select(
            FuturesMarket.id,
            FuturesMarket.external_id,
            FuturesMarket.name,
        )
        .where(
            FuturesMarket.source == "kalshi",
            or_(*[FuturesMarket.external_id.like(f"{name}-%") for name in series]),
            FuturesMarket.created_at >= now - timedelta(days=CANDIDATE_WINDOW_DAYS),
        )
        .order_by(FuturesMarket.id.desc())
        .limit(MAX_CANDIDATE_MARKETS)
    )


async def _load_candidates(
    session, series: tuple[str, ...], *, now: datetime
) -> list[dict[str, Any]]:
    """Kalshi match markets for these series, as plain resolver candidates.

    Rows are copied to scalars here rather than handed on as ORM objects: this
    runs in a task session and the resolver is pure, so nothing downstream may
    hold a live row across a commit boundary (gotcha #6).

    Note what is NOT in the predicate: ``status``. Kalshi settled markets stay
    ``status='open'`` in our database (gotcha #33), so filtering on it would
    neither exclude finished matches nor include all live ones — it would just
    make the query look careful. The resolver's date window is the real bound
    and it is applied where it can be tested.

    What IS in the predicate, since ux/1033: a recency window, and an ordering.
    See ``CANDIDATE_WINDOW_DAYS`` for the measurement — without both, the row cap
    silently kept the oldest 2,000 of 5,113 rows and the pool ended six months
    before the tournament being played. ``ORDER BY id DESC`` is belt-and-braces
    behind the window: if a series ever does put more than the cap inside a
    fortnight, the rows that survive are the ones nearest today rather than an
    arbitrary slice, and the caller says so out loud.
    """
    from app.models import FuturesOutcome

    if not series:
        return []

    market_rows = (await session.execute(candidate_query(series, now=now))).all()
    if not market_rows:
        return []

    by_id: dict[int, dict[str, Any]] = {
        row.id: {
            "source": "kalshi",
            "market_id": row.id,
            "external_id": row.external_id,
            "name": row.name,
            "match_date": _match_date(row.external_id),
            "outcomes": [],
        }
        for row in market_rows
    }

    outcome_rows = (
        await session.execute(
            select(
                FuturesOutcome.market_id,
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.external_id,
            ).where(FuturesOutcome.market_id.in_(list(by_id)))
        )
    ).all()
    for row in outcome_rows:
        candidate = by_id.get(row.market_id)
        if candidate is not None:
            candidate["outcomes"].append(
                {
                    "outcome_id": row.id,
                    "name": row.name,
                    "external_id": row.external_id,
                }
            )

    return list(by_id.values())


#: Where ``sync_tournament_results`` publishes the ESPN scoreboard and where
#: ``routes/tournaments.py`` reads it. Read here too, and by the same key: the
#: authority pairing this resolves against must be the SAME one the slate
#: withheld the register's pairing on. Deriving it from a second fetch would
#: let the two disagree, and a link minted against a pairing the page is not
#: rendering is worse than no link at all.
RESULTS_PREFIX = "bainluck:tournament-results:"


async def _read_order_of_play(slug: str) -> dict[str, Any]:
    """ESPN's competition map for this tournament, or ``{}``.

    Read-only, from the cache another beat already fills. A cold or unreadable
    cache yields no authority competitions and therefore no authority links,
    which returns the page to exactly the unpriced row it renders today — the
    honest state, not a stale one.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(f"{RESULTS_PREFIX}{slug}")
        if raw:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                listed = payload.get("order_of_play")
                if isinstance(listed, dict):
                    return listed
    except Exception as exc:  # noqa: BLE001 — an overlay is never a gate
        logger.warning("order-of-play read failed for %s: %s", slug, exc)
    return {}


def _authority_competitions(
    order_of_play: dict[str, Any],
) -> list[dict[str, Any]]:
    """The scoreboard's competitions as resolver input, identity-gated.

    ``determined`` is the gate, and it is the same one ``authority_match_row``
    uses to decide whether it may draw the row at all. Two competitors, both
    with a positive athlete id and a name, or the competition is skipped —
    a doubles competition names a team and no athlete, and a qualifier slot
    names "TBD". Resolving either would be guessing at who a market is for.

    Keying on ``espn:athlete:<id>`` matches ``authority_match_row``'s own
    ``entity_key``, so the sides map this produces is looked up by the exact
    string the slate row carries.
    """
    out: list[dict[str, Any]] = []
    for comp_id, listed in (order_of_play or {}).items():
        if not isinstance(listed, dict):
            continue
        competitors = listed.get("competitors")
        if not isinstance(competitors, list) or len(competitors) != 2:
            continue
        if not all(
            isinstance(c, dict) and c.get("determined") and c.get("name")
            for c in competitors
        ):
            continue
        out.append({
            "espn_competition_id": listed.get("espn_competition_id") or comp_id,
            # ESPN's own scheduled start. `_as_date` in the resolver turns this
            # into the calendar date its one-day window compares; a midnight
            # placeholder start (`start_is_tbd`) is still the right DATE, which
            # is all the window reads.
            "scheduled_date": listed.get("start_at"),
            "players": [
                {
                    "entity_key": f"espn:athlete:{c.get('espn_athlete_id')}",
                    "display_name": c.get("name"),
                }
                for c in competitors
            ],
        })
    return out


async def _write_links(slug: str, payload: dict[str, Any]) -> bool:
    try:
        from app.tasks.redis_state import get_async_redis_client

        await get_async_redis_client().setex(
            f"{LINKS_PREFIX}{slug}", LINKS_TTL_SECONDS, json.dumps(payload, default=str)
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("tournament link write failed for %s: %s", slug, exc)
        return False


async def _link_tournament_matchups(
    watched: tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Resolve and publish match-market links for every watched tournament."""
    from app.tasks.base import get_task_session

    started = _time.monotonic()
    entries = WATCHED if watched is None else tuple(watched)
    now = _now()

    stats: dict[str, Any] = {
        "tournaments": 0,
        "needy": 0,
        "resolved": 0,
        "published": 0,
        # The authority half, counted separately (lane1/047). Rolled into the
        # register counters these would be unreadable: `resolved` would mix
        # "filled a blank the census left" with "priced a row the register
        # names wrong", and only the second one is a repair backlog.
        "authority_competitions": 0,
        "authority_resolved": 0,
        "authority_published": 0,
        "written": 0,
        # How many tournaments loaded a TRUNCATED candidate pool (ux/1033).
        # Zero is the healthy state and it is a measured one, not an assumption.
        "candidates_capped": 0,
        "deadline_hit": False,
        "by_tournament": {},
        **{code: 0 for code in REFUSAL_CODES},
    }

    for entry in entries:
        if _time.monotonic() - started > DEADLINE_SECONDS:
            stats["deadline_hit"] = True
            logger.warning(
                "tournament matchup linker hit its %.0fs deadline; %d of %d "
                "tournaments done",
                DEADLINE_SECONDS, stats["tournaments"], len(entries),
            )
            break

        slug = entry.get("tournament")
        season = entry.get("season")
        # One poison tournament must not starve its siblings — the isolation
        # property the register sentinel already holds itself to.
        try:
            register = load_register(slug, season)
            if register is None:
                stats["by_tournament"][slug] = {"error": "NO_REGISTER"}
                logger.error("matchup linker: no readable register for %s", slug)
                continue

            async with get_task_session() as session:
                candidates = await _load_candidates(
                    session, tuple(entry.get("kalshi_series") or ()), now=now
                )
            # A TRUNCATED POOL IS NOT A QUIET POOL (ux/1033, gotcha #53). The
            # cap fired for six months without a word, and every downstream
            # signal — refusals, `resolved: 0`, an unpriced card — reads exactly
            # the same whether the market is absent or merely unloaded. Only
            # this line can tell those apart.
            capped = len(candidates) >= MAX_CANDIDATE_MARKETS
            if capped:
                logger.warning(
                    "matchup linker: %s hit the %d-candidate cap inside a "
                    "%d-day window — the pool is truncated and some fixtures "
                    "cannot resolve",
                    slug, MAX_CANDIDATE_MARKETS, CANDIDATE_WINDOW_DAYS,
                )

            outcome = resolve_matchup_links(register, candidates, now=now)
            counters = outcome["counters"]
            links = outcome["links"]

            # THE FIXTURES THE REGISTER NAMES WRONG (lane1/047). Q503 withholds
            # those pairings and Q505 renders the scoreboard's instead; without
            # this, that substituted row can never carry a number, however
            # cleanly we hold its market. Resolved from the SAME candidate pool
            # by the SAME rule — the only difference is who named the two
            # people. Keyed `espn:<comp id>`, which is the row's own key.
            competitions = _authority_competitions(
                await _read_order_of_play(slug)
            )
            authority = resolve_authority_links(competitions, candidates, now=now)
            authority_links = authority["links"]

            # A resolver that resolved nothing must not read like one that had
            # nothing to do (gotcha #53). Both numbers are always reported.
            published = await _write_links(
                slug,
                {
                    "tournament": slug,
                    "season": season,
                    "generated_at": now.isoformat(),
                    "candidates": len(candidates),
                    "candidates_capped": capped,
                    "counters": counters,
                    "links": links,
                    # A SEPARATE KEY, NOT MERGED INTO `links`. `apply_resolved_
                    # links` may only ever replace a register block the register
                    # itself marked `missing`, and an authority link belongs to
                    # no register matchup — merging the two would hand a reader
                    # of `links` a key that path cannot mean anything by.
                    "authority_competitions": len(competitions),
                    "authority_counters": authority["counters"],
                    "authority_links": authority_links,
                },
            )

            stats["tournaments"] += 1
            stats["needy"] += counters.get("needy", 0)
            stats["resolved"] += counters.get("resolved", 0)
            stats["published"] += len(links)
            stats["authority_competitions"] += len(competitions)
            stats["authority_resolved"] += authority["counters"].get("resolved", 0)
            stats["authority_published"] += len(authority_links)
            stats["written"] += 1 if published else 0
            stats["candidates_capped"] += 1 if capped else 0
            for code in REFUSAL_CODES:
                stats[code] += counters.get(code, 0)
            stats["by_tournament"][slug] = {
                "candidates": len(candidates),
                "candidates_capped": capped,
                "written": published,
                "authority_competitions": len(competitions),
                "authority": authority["counters"],
                **counters,
            }

            if counters.get("needy") and not counters.get("resolved"):
                logger.warning(
                    "matchup linker: %s has %d fixtures with no pinned market "
                    "and resolved NONE of them from %d candidates — refusals %s",
                    slug, counters["needy"], len(candidates),
                    {c: counters.get(c, 0) for c in REFUSAL_CODES},
                )
            elif counters.get("resolved"):
                logger.info(
                    "matchup linker: %s resolved %d/%d unpinned fixtures",
                    slug, counters["resolved"], counters["needy"],
                )
        except Exception as exc:  # noqa: BLE001 — isolation, per tournament
            logger.exception("matchup linker failed for %s: %s", slug, exc)
            stats["by_tournament"][slug] = {"error": type(exc).__name__}

    stats["duration_s"] = round(_time.monotonic() - started, 2)
    return stats


async def read_links(slug: str) -> dict[str, Any]:
    """What the route reads. A cold or dead cache yields no links, never an error.

    An absent overlay is not a failure state: it returns the page to exactly the
    register's own committed truth, which is where it was before this task
    existed.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(f"{LINKS_PREFIX}{slug}")
        if raw:
            payload = json.loads(raw)
            if isinstance(payload, dict) and isinstance(payload.get("links"), dict):
                return payload
    except Exception as exc:  # noqa: BLE001 — an overlay is never a gate
        logger.warning("tournament link read failed for %s: %s", slug, exc)
    return {"links": {}}


__all__ = [
    "CANDIDATE_WINDOW_DAYS",
    "LINKS_PREFIX",
    "LINKS_TTL_SECONDS",
    "MAX_CANDIDATE_MARKETS",
    "candidate_query",
    "WATCHED",
    "_link_tournament_matchups",
    "apply_resolved_links",
    "read_links",
]
