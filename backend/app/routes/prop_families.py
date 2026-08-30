"""Prop-family API: grouped prop families for a team.

``GET /api/teams/{identifier}/prop-families`` loads a team's futures/prop
markets and returns them grouped into prop families (Next Team, award
races, threshold ladders) via ``app.utils.prop_families``.

The team → props matching mirrors the pattern in ``app.routes.user``
``_query_team_futures`` (team_id FK + full team-name ILIKE + roster player
name ILIKE), reproduced here rather than shared to avoid coupling — this
route is public read-only and does not need the round-robin/coherence
post-processing that ``_query_team_futures`` applies for the "Your Teams'
Odds" surface.

LAT-P138 (2026-08-30) — WHAT A TEAM PAGE COST BEFORE THIS FILE HAD A CACHE.
First touch per team, production ``64b7a034``, ``x-timing-split`` server time,
seven teams, every one of them a page reachable in one tap from search:

    kansas-city-chiefs  16,797 ms   los-angeles-dodgers  9,448 ms
    boston-red-sox      10,962 ms   dallas-cowboys       8,756 ms
    new-york-yankees     7,518 ms   los-angeles-lakers   2,910 ms
    boston-celtics       2,627 ms

Three consecutive Chiefs reads went 16,797 -> 11,342 -> 3,992 ms: there was no
response cache of any kind, so what looked like warming was Postgres buffer
warming and every visitor paid a fresh build. `EXPLAIN (ANALYZE)` on the Chiefs'
own patterns says where it goes — **41 separate GIN trigram probes, of which 35
match nothing**:

    fk branch            1.5 ms   (index scan, 32 rows)
    outcome-name branch 13,107 ms (BitmapOr of 41 bitmap index scans, 96 rows)
    market-name branch   2,990 ms (BitmapOr of 41 bitmap index scans, 76 rows)

Cost is LINEAR IN PROBE COUNT (41 patterns 13.4 s vs the same 10 patterns
2.2 s), and probe count is the roster: 65 Chiefs, capped at
``_MAX_ROSTER_PATTERNS``. Only 367 of 9,625 teams carry a roster at all, so this
is a ~367-team population, not a long tail — and those are exactly the teams a
person searches for.

Two changes, both here:

1. ``ILIKE ANY (ARRAY[...])`` instead of an N-way ``OR`` of ``ILIKE``. Same
   predicate by definition (``x ILIKE ANY (ARRAY[a,b])`` IS ``x ILIKE a OR x
   ILIKE b``), and measured to return the same rows — 96 and 76 for the Chiefs
   on both spellings — but Postgres plans it as ONE index scan with a
   ScalarArrayOp rather than a 41-way ``BitmapOr``. Four paired trials,
   interleaved so buffer warming could not pick the winner: outcome branch
   8,200 -> 4,821 and 7,018 -> 4,759 ms; market branch 6,733 -> 6,217 and
   4,830 -> 1,837 ms.
2. The response cache tier this route never had, adopted (not invented) from
   ``utils/event_concept_cache`` exactly as ``routes/hub.py`` adopted it.

⚠️ The pre-measurement above rendered the patterns as SQL literals (``db-query``
takes no parameters). The route BINDS them, as it already did for the ``OR``
form — so both spellings depend on the same custom-plan behaviour that
production demonstrably has today (a generic plan could not use the trigram
index for either form, and the ``OR`` form is measurably using it). The
post-deploy first-touch read on this endpoint is the falsifier.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Text, and_, any_, literal, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team, FuturesMarket, FuturesOutcome
from app.services import get_db
from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    ConceptCacheKeys,
    acquire_refresh_lock,
    cache_keys,
    get_client,
    read_slot,
    release_refresh_lock,
    stamp_envelope,
    with_availability,
    write_payload,
)
from app.utils.prop_families import group_prop_families

logger = logging.getLogger(__name__)

router = APIRouter()

# Terminal statuses we still want to surface so a settled prop can be
# labelled WHAT-HIT (bug b) rather than dropped.
_INCLUDED_STATUSES = ["open", "resolved", "closed", "settled", "suspended"]

_MAX_ROSTER_PATTERNS = 40


def _escape_like(s: str) -> str:
    """Escape special LIKE/ILIKE characters for safe pattern matching."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _roster_player_names(team: Team) -> list[str]:
    """Extract roster player names for player-prop family matching."""
    names: list[str] = []
    roster = getattr(team, "roster_players", None)
    if roster and isinstance(roster, list):
        for item in roster:
            if isinstance(item, dict):
                nm = item.get("name")
            elif isinstance(item, str):
                nm = item
            else:
                nm = None
            if isinstance(nm, str) and len(nm.strip()) >= 4:
                names.append(nm.strip())
            if len(names) >= _MAX_ROSTER_PATTERNS:
                break
    return names


# ---------------------------------------------------------------------------
# Cache tier (LAT-P138) — policy lives in `utils/event_concept_cache.py`
# ---------------------------------------------------------------------------
#
# The THIRD customer of that module, adopted the way `routes/hub.py` adopted it
# (ruling 005, extract-on-touch; contract in `docs/contracts/cache-envelope.md`).
# Nothing about the policy is re-implemented here: same envelope, same 24h
# mirror, same single-flight refresh lock, same "an empty build never overwrites
# a good mirror" ordering.

PROP_FAMILIES_CACHE_PREFIX = "bainluck:prop_families:"

#: How fresh a *live* hit is. Prop families are season-long questions ("Next
#: Team", MVP races, threshold ladders) whose probabilities move on the futures
#: poll cadence, not on a game clock — 15 minutes is the freshness this surface
#: needs. Expiry no longer costs the reader a rebuild, so this is not a latency
#: knob: past it a reader gets the mirror in milliseconds and one background
#: rebuild is scheduled behind them.
PROP_FAMILIES_PRIMARY_TTL = 900


def prop_families_cache_keys(team_id: int, cap: int) -> ConceptCacheKeys:
    """The four Redis keys one team's prop-family answer owns.

    🔴 KEYED ON THE RESOLVED TEAM ID, NEVER ON THE URL IDENTIFIER. The route
    accepts a slug OR an integer id for the same team, and #1204 registers
    retired legacy slugs that resolve to the same row — three spellings, one
    answer. Keying on the raw identifier would give one team up to three cache
    entries, and a producer that warmed the slug would leave the id spelling
    cold forever.

    `cap` is in the key because it SHAPES THE ANSWER (it is the per-branch
    LIMIT). This is the `search_cache` rule — one key builder, and its
    parameters are exactly the answer-shaping parameters — applied here so a
    `?limit=` reader can never be served a differently-bounded payload.
    """
    return cache_keys(f"{int(team_id)}:{int(cap)}", prefix=PROP_FAMILIES_CACHE_PREFIX)


def _resolve_cap(limit: int) -> int:
    """The per-branch LIMIT, bounded. One implementation, because it is half of
    the cache key and the route and the warmer must agree on it exactly."""
    return max(1, min(limit, 2000))


def _schedule_refresh(rc, keys: ConceptCacheKeys, team_id: int, cap: int) -> None:
    """Kick exactly one background rebuild for this team and return immediately.

    Single-flight: a burst of readers behind one TTL expiry produces one rebuild,
    not one per reader — which matters more here than anywhere else in the repo,
    because one rebuild is seconds of database time.

    The owner token travels WITH the dispatch because this request acquires the
    lock and the worker releases it (#1678 finding 1). Best-effort throughout: the
    caller has already decided to serve the mirror, and nothing here may turn a
    served page into an error.
    """
    token = acquire_refresh_lock(rc, keys)
    if not token:
        return
    try:
        from app.tasks import celery_app

        celery_app.send_task(
            "app.tasks.refresh_prop_families",
            args=[int(team_id), int(cap), token],
            queue="background",
        )
    except Exception:
        logger.warning(
            "prop-families: refresh dispatch failed for team %s", team_id, exc_info=True
        )
        release_refresh_lock(rc, keys, token)


async def resolve_team(db: AsyncSession, identifier: str) -> Team | None:
    """Resolve a team by integer id or slug. Shared with the warmer so the two
    cannot disagree about which row an identifier names."""
    team_filter = Team.slug == identifier
    try:
        team_id = int(identifier)
        team_filter = or_(Team.id == team_id, Team.slug == identifier)
    except ValueError:
        pass
    result = await db.execute(select(Team).where(team_filter))
    return result.scalars().first()


async def build_prop_families(team: Team, db: AsyncSession, cap: int) -> tuple[dict, bool]:
    """Build one team's prop-family payload. Returns ``(payload, degraded)``.

    `degraded` is True when the branch queries failed or tripped the statement
    timeout, i.e. when the empty `families` list is an ARTEFACT rather than an
    answer. The caller must never cache a degraded payload — a 24h mirror
    holding a timeout's empty page would freeze an empty section for a day
    (gotcha #53: an empty 200 is a response shape, not an absence).

    Never raises: every failure lands on the degrade path.
    """
    # Match a team's props by three criteria: team_id FK, full team-name ILIKE
    # (on outcome AND market names), and roster player-name ILIKE. These MUST be
    # run as SEPARATE, per-index queries rather than a single or_() over the join.
    #
    # #1249 / #1197 (r262): a single `or_(team_id == X, name ILIKE '%…%', …)`
    # mixing the FK branch with many leading-wildcard ILIKE patterns (team name +
    # up to 40 roster players, on BOTH outcome and market names) defeats every
    # index and seq-scans the ~1.2M-row futures_outcomes ⋈ futures_markets join.
    # Measured live at ~12.5s for the Yankees — tripping the statement_timeout
    # below into an empty degrade, which zeroed team yield and blocked the cohort
    # card (L2-167). Mirror _query_team_futures's proven fix (routes/user.py
    # r259): run each criterion as its OWN query so it hits its OWN index
    # (ix_futures_outcomes_team_id for the FK branch; the GIN trigram indexes
    # ix_futures_outcomes_name_trgm and ix_futures_markets_name_trgm for the two
    # name branches), then merge/dedup by outcome id. Same rows, each branch
    # index-served.
    #
    # LAT-P138: the two name branches say `ILIKE ANY (ARRAY[...])`, not an N-way
    # `or_()`. Identical predicate — `x ILIKE ANY (ARRAY[a,b])` IS
    # `x ILIKE a OR x ILIKE b` — and measured to return identical rows, but the
    # planner reads it as ONE index scan with a ScalarArrayOp instead of a 41-way
    # BitmapOr of 41 bitmap index scans, 35 of which matched nothing. The header
    # carries the four interleaved paired trials.
    _cap = _resolve_cap(cap)
    _base_filters = (
        FuturesMarket.event_id.is_(None),
        FuturesMarket.status.in_(_INCLUDED_STATUSES),
    )

    def _branch(cond):
        return (
            select(FuturesOutcome, FuturesMarket)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .where(and_(*_base_filters, cond))
            .order_by(FuturesOutcome.current_probability.desc().nulls_last())
            .limit(_cap)
        )

    # Name patterns (team full name + roster players) drive the two trigram
    # branches; the FK branch needs no pattern.
    _name_pats: list[str] = []
    if team.name:
        _name_pats.append(f"%{_escape_like(team.name.strip())}%")
    for player in _roster_player_names(team):
        _name_pats.append(f"%{_escape_like(player)}%")

    branch_conds = [FuturesOutcome.team_id == team.id]  # FK branch (indexed)
    if _name_pats:
        # One ScalarArrayOp per column → a single GIN trigram index scan for that
        # column, NOT one bitmap index scan per pattern and NOT a join-wide seq
        # scan. `literal(..., ARRAY(Text))` binds the patterns as one text[]
        # parameter, exactly as the `or_()` form bound them one at a time.
        _pats = literal(_name_pats, ARRAY(Text))
        branch_conds.append(FuturesOutcome.name.ilike(any_(_pats)))
        branch_conds.append(FuturesMarket.name.ilike(any_(_pats)))

    # #1197 / #1239: statement_timeout stays as a backstop so any pathological
    # branch fails fast and the endpoint degrades to an empty families list (200)
    # rather than hanging the dyno to a 503.
    rows: list = []
    _seen_oids: set[int] = set()
    try:
        await db.execute(text("SET LOCAL statement_timeout = '12000'"))
        for _cond in branch_conds:
            for r in (await db.execute(_branch(_cond))).all():
                oid = r[0].id
                if oid not in _seen_oids:
                    _seen_oids.add(oid)
                    rows.append(r)
    except Exception:
        logger.exception(
            "prop-families: query failed/timed out for team %s — empty degrade",
            team.id,
        )
        return (
            {
                "team": {
                    "id": team.id,
                    "name": team.name,
                    "slug": getattr(team, "slug", None),
                },
                "families": [],
                "total_families": 0,
            },
            True,
        )

    # Reassemble outcomes onto their market dicts.
    by_market: dict[int, dict] = {}
    for outcome, market in rows:
        entry = by_market.get(market.id)
        if entry is None:
            entry = {
                "market_id": market.id,
                "name": market.name,
                "source": market.source,
                "group_id": market.group_id,
                "status": market.status,
                "resolution_date": (
                    market.resolution_date.isoformat()
                    if market.resolution_date else None
                ),
                "market_metadata": market.market_metadata,
                "outcomes": [],
            }
            by_market[market.id] = entry
        prob = (
            float(outcome.current_probability)
            if outcome.current_probability is not None else None
        )
        entry["outcomes"].append(
            {
                "outcome_id": outcome.id,
                "name": outcome.name,
                "probability": prob,
                "is_winner": bool(outcome.is_winner),
            }
        )

    families = group_prop_families(list(by_market.values()))

    return (
        {
            "team": {
                "id": team.id,
                "name": team.name,
                "slug": getattr(team, "slug", None),
            },
            "families": families,
            "total_families": len(families),
        },
        False,
    )


async def build_and_cache_prop_families(
    team: Team, db: AsyncSession, cap: int, rc=None
) -> tuple[dict, bool]:
    """Build one team's families, stamp the envelope, write both slots.

    One implementation for the route's cold path and the background refresh, so
    the two cannot drift in WHAT they store or WHERE.

    **A degraded build never writes.** The route's degrade path returns an empty
    `families` list on a statement timeout, and that empty list is indistinguishable
    from "this team genuinely has no families" once it is bytes in Redis. Writing
    it would put a timeout artefact behind a 24h mirror — the exact inversion of
    the tier's purpose. It is returned to the caller (a served empty section beats
    a 500) and dropped on the floor.
    """
    payload, degraded = await build_prop_families(team, db, cap)
    if degraded:
        return payload, True
    stamped = stamp_envelope(
        payload,
        created_at=datetime.now(timezone.utc),
        # An explicit allowed unknown per the contract: a prop-family answer is a
        # composition over many markets with no single lifecycle event of its own,
        # and claiming a watermark we cannot compute is a fabrication (#1678
        # finding 3).
        lifecycle_watermark=None,
    )
    write_payload(
        rc,
        prop_families_cache_keys(team.id, _resolve_cap(cap)),
        stamped,
        primary_ttl=PROP_FAMILIES_PRIMARY_TTL,
    )
    return stamped, False


@router.get("/{identifier}/prop-families")
async def get_team_prop_families(
    identifier: str,
    limit: int = 400,
    db: AsyncSession = Depends(get_db),
):
    """Detect and return prop families over a team's futures/prop markets.

    Response shape::

        {
          "team": {"id": int, "name": str, "slug": str | None},
          "families": [ {family_key, label, entity_count, sources, rows: [...]}, ... ],
          "total_families": int,
          "cache": {...},   # LAT-P138: the envelope contract, additive. Carries
                            # `availability` ("live" | "stale_ok") and
                            # `created_at` — the age of the CONTENT, not of the
                            # read, so a mirror serve declares itself.
        }

    The one shape that does NOT carry `cache` is the degraded build: a statement
    timeout is served (an empty section beats a 500) and is deliberately neither
    stamped nor stored, so a consumer can tell a real empty answer from a
    timeout's by the envelope's absence.
    """
    team = await resolve_team(db, identifier)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    cap = _resolve_cap(limit)
    keys = prop_families_cache_keys(team.id, cap)
    rc = get_client()

    # 1. A live hit inside the primary TTL.
    primary = read_slot(rc, keys.primary)
    if primary is not None:
        return with_availability(primary, AVAILABILITY_LIVE)

    # 2. A miss serves the 24h mirror and schedules ONE rebuild behind it. This
    #    is the whole ship: a rebuild here is 2.6-16.8 s of database time, and
    #    before this tier existed every reader paid one.
    stale = read_slot(rc, keys.stale)
    if stale is not None:
        _schedule_refresh(rc, keys, team.id, cap)
        return with_availability(stale, AVAILABILITY_STALE_OK)

    # 3. Nothing usable cached — build inline. A cold miss must still SERVE, so
    #    this path stays synchronous and is never gated on the refresh task.
    payload, degraded = await build_and_cache_prop_families(team, db, cap, rc)
    if degraded:
        # Re-read the mirror rather than trusting step 2: a concurrent refresh may
        # have landed one while we were building. A real snapshot beats a timeout's
        # empty page.
        rescued = read_slot(rc, keys.stale)
        if rescued is not None:
            logger.warning(
                "prop-families: build degraded for team %s — serving stale", team.id
            )
            return with_availability(rescued, AVAILABILITY_STALE_OK)
        return payload

    return with_availability(payload, AVAILABILITY_LIVE)
