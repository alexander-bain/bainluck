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
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Text, and_, any_, literal, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team, FuturesMarket, FuturesOutcome
from app.services import get_db
from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    ENVELOPE_FIELD,
    LOSS_PARTIAL,
    QUALITY_FULL,
    ConceptCacheKeys,
    acquire_refresh_lock,
    cache_keys,
    get_client,
    note_build_loss,
    publish_mirror_if_unchanged,
    read_slot,
    read_slot_raw,
    release_refresh_lock,
    stamp_envelope,
    take_build_quality,
    with_availability,
    write_payload,
)
from app.utils.prop_families import group_prop_families
from app.utils.statement_timeout import is_statement_timeout

logger = logging.getLogger(__name__)

router = APIRouter()

# Terminal statuses we still want to surface so a settled prop can be
# labelled WHAT-HIT (bug b) rather than dropped.
_INCLUDED_STATUSES = ["open", "resolved", "closed", "settled", "suspended"]

_MAX_ROSTER_PATTERNS = 40

#: How long ONE branch may run. Unchanged in value and in meaning from the
#: `SET LOCAL statement_timeout = '12000'` this route has carried since #1197 —
#: LAT-P145 changed who survives the expiry, deliberately not how long the
#: expiry takes, so no team that completes today starts failing tomorrow.
_BRANCH_TIMEOUT_MS = 12000

#: What a READER may spend on a whole cold build, across all branches. `None`
#: means "no reader is waiting" and restores the per-branch budget exactly.
#:
#: LAT-P164 (#2383) — WHY A TOTAL BUDGET AND NOT A SMALLER PER-BRANCH ONE.
#: `_BRANCH_TIMEOUT_MS` bounds ONE statement, so four branches bound at 12 s
#: each is a 48-second reader. What the ring actually recorded is the middle of
#: that range: nine slow events on this endpoint in 24 h, **six of them clustered
#: at 12,376-12,969 ms**, every one `cache=none`. That cluster is not a cost, it
#: is the timeout — a reader waiting out an expiry and then being handed the page
#: without the content they waited for.
#:
#: 2,500 ms is sized from the branches that stay on the reader's path, measured
#: on production 2026-08-31 (`EXPLAIN ANALYZE`, Virginia Cavaliers' own patterns):
#: the FK branch is 7 ms and a SINGLE-pattern trigram probe is 222 ms warm, so
#: the budget is roughly 5x what the retained work costs and still 5x better than
#: the 12.4 s median it replaces.
_READER_BUDGET_MS = 2500

#: A branch is SKIPPED rather than started when less than this remains. Starting
#: a statement you have already computed cannot finish costs the reader the whole
#: remaining wait and returns nothing — the budget guard would become the new
#: failure mode it exists to prevent (`backfill_winners::_run_bounded`, gotcha
#: #42 in another costume — the same sentence LAT-P145 quoted one level up).
_MIN_BRANCH_MS = 250

#: The two loss vocabularies this module writes into `quality_reasons`, as
#: PREFIXES, because the difference between them is now load-bearing twice over
#: (CERT-557). `branch_timeout:` means the database was asked and ran out of
#: time; `branch_deferred:` means a budgeted reader chose not to ask. Only the
#: second is an IOU somebody still owes — see `_deferral_reasons`.
_REASON_TIMEOUT = "branch_timeout:"
_REASON_DEFERRED = "branch_deferred:"

#: The criteria, named. LAT-P145 made the names load-bearing: a branch that
#: times out is now REPORTED, by name, in the envelope's `quality_reasons`, so a
#: reader of the payload can tell "this team has no player props" from "we could
#: not read the player props in time".
#:
#: LAT-P164 SPLIT THE TWO NAME BRANCHES BY PATTERN CLASS, and the split is the
#: ship. The team-name pattern and the roster patterns were one query per column,
#: so they shared one fate and one cost — and they have neither in common:
#:
#:     Virginia Cavaliers, production, EXPLAIN ANALYZE 2026-08-31
#:       outcome branch, 41 patterns   11,830 ms   <- trips the 12 s expiry
#:       outcome branch,  1 pattern       222 ms   <- returns all 6 real rows
#:
#: Cost is linear in probe count (this module's header measured it, and LAT-P164
#: re-measured the curve: 1/2/5/10/20/41 patterns -> 222/107/646/768/1,990/4,752
#: ms warm), so 40 of the 41 probes are 97% of the bill. Splitting them buys two
#: separate things: the roster probe can be left off the reader's path, and — the
#: independent correctness win — a roster expiry no longer discards the
#: team-name rows that were already fetched beside it. That is LAT-P145's own
#: finding applied one level down: it stopped a branch erasing its SIBLINGS, and
#: this stops the expensive HALF of a branch erasing the cheap half.
_BRANCH_TEAM_ID = "team_id"
_BRANCH_OUTCOME_NAME = "outcome_name"
_BRANCH_MARKET_NAME = "market_name"
_BRANCH_OUTCOME_ROSTER = "outcome_roster"
_BRANCH_MARKET_ROSTER = "market_roster"


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

#: How often ONE key may spend a background build trying to settle its deferrals.
#:
#: 🔴 THE SINGLE-FLIGHT LOCK IS NOT A RATE BOUND, AND CERT-557 IS WHY THIS EXISTS.
#: `REFRESH_LOCK_TTL` is 120 s and it answers "how many builders at once", not
#: "how often". A live primary that carries a deferral is served for a whole
#: `PROP_FAMILIES_PRIMARY_TTL`, so a completion dispatch gated only by the lock
#: would fire up to `900 // 120` = 7 times per team per window — seven
#: unbudgeted builds, 2.6-16.8 s each, on a database `pg:diagnose` rates RED on
#: hit rate. One attempt per window is the retry the deferral needs and the most
#: the database should be asked for: the reader is already being served in
#: milliseconds from the primary either way, so a second attempt inside the same
#: window buys the page nothing it is not already getting.
COMPLETION_ATTEMPT_TTL = PROP_FAMILIES_PRIMARY_TTL


def _completion_attempt_key(keys: ConceptCacheKeys) -> str:
    """The marker naming "this key has already spent a completion attempt".

    Derived from the primary key rather than added to `ConceptCacheKeys`: the
    four-key layout is shared with the competition hub (#1651) and this is one
    tier's own bookkeeping, not a policy every adopter of the layout inherits.
    """
    return f"{keys.primary}:completing"


def _claim_completion_attempt(rc, keys: ConceptCacheKeys) -> bool:
    """Take this window's one completion attempt, or report that it is spent.

    `SET NX EX` — the same primitive as the refresh lock, a different question.
    Fails CLOSED (returns False) when Redis cannot be reached: an unreachable
    Redis is not a licence to dispatch an unbounded number of unbudgeted builds,
    and the reader is being served from the primary regardless. The marker is
    never released; it is a rate bound, not a lock, and releasing it would
    restore exactly the seven-attempts-per-window shape it exists to prevent.
    """
    if rc is None:  # no client, so no bound can be taken — decline (see above)
        return False
    try:
        return bool(
            rc.set(
                _completion_attempt_key(keys), "1", nx=True, ex=COMPLETION_ATTEMPT_TTL
            )
        )
    except Exception:
        return False


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


def envelope_quality(payload: Any) -> tuple[str | None, list[str]]:
    """The stamped quality and its reasons, from a payload that may be anything.

    ONE reader of the envelope, exported, because CERT-557 found the route and
    the background task disagreeing about what a build had achieved: the route
    inspected `quality` and the task inspected only the `degraded` boolean, so a
    build that kept the cheap rows and lost the roster was `partial` to one and
    a completed rebuild to the other. Two callers reading one field two ways is
    how a false green is built; there is now one function and both call it.

    Returns `(None, [])` for anything without a readable envelope — the shape a
    total loss returns, deliberately unstamped, and the shape a caller must not
    mistake for `full`.
    """
    if not isinstance(payload, dict):
        return None, []
    envelope = payload.get(ENVELOPE_FIELD)
    if not isinstance(envelope, dict):
        return None, []
    quality = envelope.get("quality")
    reasons = envelope.get("quality_reasons")
    return (
        quality if isinstance(quality, str) else None,
        [r for r in reasons if isinstance(r, str)] if isinstance(reasons, list) else [],
    )


def _deferral_reasons(reasons: list[str]) -> list[str]:
    """The subset of `reasons` that are IOUs — branches nobody asked for yet.

    🔴 THE DISTINCTION IS THE BOUND, AND THAT IS WHY IT IS A FUNCTION (CERT-557).
    A partial we OWE and a partial the database CANNOT SERVE want opposite
    treatment from the completion path:

    * `branch_deferred:` — a budgeted reader skipped this branch to hand the page
      over in 2.5 s. Nothing has established the content is unreachable; we
      simply did not ask. Somebody must ask, unbudgeted, or the courtesy becomes
      a silent narrowing of the page.
    * `branch_timeout:` — the branch was started with the full 12 s ceiling and
      expired. Re-dispatching that immediately buys nothing and costs another
      twelve seconds on a database `pg:diagnose` already rates RED; it is the hot
      loop, not the fix. It is reported (see the refresh task's terminal) and
      left for the residual structural work named on #2383.

    Collapsing the two would either strand the deferral or hammer the timeout.
    """
    return [r for r in reasons if r.startswith(_REASON_DEFERRED)]


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


async def build_prop_families(
    team: Team, db: AsyncSession, cap: int, budget_ms: int | None = None
) -> tuple[dict, bool]:
    """Build one team's prop-family payload. Returns ``(payload, unusable)``.

    ``budget_ms`` is the TOTAL wall-clock a caller may spend across all branches,
    or ``None`` for "nobody is waiting" — the background rebuild, where the
    per-branch bound is the only bound and the behaviour is unchanged. It
    defaults to ``None`` so that a caller must ASK to be bounded: a producer that
    silently inherited a reader's budget would quietly stop producing the
    complete answer the reader is being deferred to.

    `unusable` is True only when EVERY branch failed, i.e. when the empty
    `families` list is entirely an ARTEFACT rather than an answer. The caller must
    never cache that — a 24h mirror holding a timeout's empty page would freeze an
    empty section for a day (gotcha #53: an empty 200 is a response shape, not an
    absence).

    🔴 LAT-P145 — ONE BRANCH'S TIMEOUT NO LONGER ERASES THE OTHER TWO.
    The three criteria used to run inside ONE transaction under ONE
    ``SET LOCAL statement_timeout``, and the handler that caught the expiry
    returned an empty payload. Postgres aborts a transaction whose statement is
    cancelled, so the expiry of branch 2 did three things at once: it lost branch
    2's rows, it made branch 3 unrunnable, and it threw away branch 1's rows,
    which had already been fetched and were sitting in memory. Measured on
    production ``944c466e``, 2026-08-30, three NFL team pages:

        new-york-giants      12,638 ms   q=3  unfinished=1  families 0  no envelope
        green-bay-packers    12,658 ms   q=3  unfinished=1  families 0  no envelope
        pittsburgh-steelers  12,908 ms   q=3  unfinished=1  families 0  no envelope

    ``q=3`` is the tell: `after_cursor_execute` does not fire for a cancelled
    cursor, so the three COMPLETED statements are `resolve_team`, the `SET LOCAL`
    and **the team_id branch** — which had returned its rows (27, 29 and 31
    respectively, counted in the same minute) before the discard. And because a
    build that returns nothing is deliberately never cached, the next reader
    repeated the whole thing: 13 requests in one four-minute window at 12.06-12.19 s
    each, all on the same permanently-uncacheable page.

    This is `backfill_winners::_run_bounded`'s lesson in another costume, and that
    file says it in as many words: *"A budget guard that takes down the parts AFTER
    it is not a budget guard, it is a new failure mode (gotcha #42 in another
    costume)."* Here it took down the part BEFORE it as well.

    So each branch now runs bounded, materialised and contained:

    * its own ``SET LOCAL``, in its own transaction, at the SAME 12 s — the
      completeness of a build that succeeds today is untouched;
    * its rows copied to plain dicts BEFORE the next branch can roll back, because
      a rollback expires every ORM object in the session and `expire_on_commit`
      does not prevent it (gotcha #6);
    * an expiry recorded as ``LOSS_PARTIAL`` against the envelope contract and the
      loop CONTINUED, so branch 3 gets its turn.

    Only a real error is loud. `is_statement_timeout` keeps the containment narrow
    on purpose: a genuine query defect must not be filed as "ran out of time".
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

    # Name patterns drive the trigram branches; the FK branch needs no pattern.
    # LAT-P164: the team's own name and its roster are kept APART, because they
    # have different costs (1 probe vs up to 40) and different yields, and the
    # branch order below spends the reader's budget on the cheap one first.
    _team_pats: list[str] = []
    if team.name:
        _team_pats.append(f"%{_escape_like(team.name.strip())}%")
    _roster_pats: list[str] = [
        f"%{_escape_like(player)}%" for player in _roster_player_names(team)
    ]

    def _ilike_any(col, pats: list[str]):
        # One ScalarArrayOp per column → a single GIN trigram index scan for that
        # column, NOT one bitmap index scan per pattern and NOT a join-wide seq
        # scan. `literal(..., ARRAY(Text))` binds the patterns as one text[]
        # parameter, exactly as the `or_()` form bound them one at a time.
        return col.ilike(any_(literal(pats, ARRAY(Text))))

    # ORDERED CHEAPEST-AND-SUREST FIRST, because a budget spends itself in order
    # and whatever it cannot reach is what gets deferred. The FK branch is the
    # team's own futures (7 ms, indexed); the team-name probes are one pattern
    # each; the roster probes are the 40 that cost 97% of the build.
    branches: list[tuple[str, object]] = [
        (_BRANCH_TEAM_ID, FuturesOutcome.team_id == team.id)  # FK branch (indexed)
    ]
    if _team_pats:
        branches.append((_BRANCH_OUTCOME_NAME, _ilike_any(FuturesOutcome.name, _team_pats)))
        branches.append((_BRANCH_MARKET_NAME, _ilike_any(FuturesMarket.name, _team_pats)))
    if _roster_pats:
        branches.append(
            (_BRANCH_OUTCOME_ROSTER, _ilike_any(FuturesOutcome.name, _roster_pats))
        )
        branches.append(
            (_BRANCH_MARKET_ROSTER, _ilike_any(FuturesMarket.name, _roster_pats))
        )

    # 🔴 SCALARS BEFORE THE FIRST BRANCH RUNS. A branch that times out rolls its
    # transaction back, and a rollback EXPIRES every ORM object in the session —
    # `expire_on_commit=False` does not prevent it (gotcha #6). `team` is read
    # again when the payload is assembled, several branches later, and re-reading
    # an expired attribute inside a route is the lazy-load crash class. Copy now,
    # while the instance is still live.
    _team_id = int(team.id)
    _team_name = team.name
    _team_slug = getattr(team, "slug", None)

    def _payload(families: list) -> dict:
        return {
            "team": {"id": _team_id, "name": _team_name, "slug": _team_slug},
            "families": families,
            "total_families": len(families),
        }

    # #1197 / #1239: statement_timeout stays as a backstop so any pathological
    # branch fails fast and the endpoint degrades rather than hanging the dyno to
    # a 503. LAT-P145: it is now set per branch, so the expiry ends ITS OWN branch
    # and nothing else.
    by_market: dict[int, dict] = {}
    _seen_oids: set[int] = set()
    lost: list[str] = []
    deferred: list[str] = []

    # LAT-P164: the reader's TOTAL budget, spent in branch order. `budget_ms is
    # None` is the background path — nobody is waiting, so the per-branch bound
    # is the only bound and behaviour is byte-for-byte what it was.
    _t0 = time.monotonic()

    for _name, _cond in branches:
        _timeout_ms = _BRANCH_TIMEOUT_MS
        if budget_ms is not None:
            _remaining = budget_ms - int((time.monotonic() - _t0) * 1000)
            if _remaining < _MIN_BRANCH_MS:
                # NOT started. A cancelled statement still costs its full wait,
                # so a branch we already know cannot finish is skipped outright
                # and reported — the reader gets the page now and the background
                # rebuild scheduled behind them fills this in for everyone after.
                deferred.append(_name)
                continue
            _timeout_ms = min(_remaining, _BRANCH_TIMEOUT_MS)
        try:
            await db.execute(text(f"SET LOCAL statement_timeout = '{_timeout_ms}'"))
            _result = (await db.execute(_branch(_cond))).all()
        except Exception as exc:  # noqa: BLE001 — classified below, then contained
            # The transaction is aborted by the cancellation; roll it back so the
            # NEXT branch gets a usable session instead of "current transaction is
            # aborted". This is `_run_bounded`'s recovery, read-only.
            try:
                await db.rollback()
            except Exception:
                logger.warning(
                    "prop-families: rollback after %s branch failed for team %s",
                    _name, _team_id, exc_info=True,
                )
            if is_statement_timeout(exc):
                logger.warning(
                    "prop-families: %s branch timed out for team %s after %d ms — "
                    "serving the branches that landed",
                    _name, _team_id, _timeout_ms,
                )
            else:
                # Narrow containment (gotcha #45): a real query defect is not a
                # budget expiry and must not be filed as one.
                logger.exception(
                    "prop-families: %s branch FAILED for team %s", _name, _team_id
                )
            lost.append(_name)
            continue

        # Materialise inside the loop: a later branch's rollback would expire these
        # instances, and by then they are plain dicts and cannot be expired.
        for outcome, market in _result:
            oid = outcome.id
            if oid in _seen_oids:
                continue
            _seen_oids.add(oid)
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
                    "outcome_id": oid,
                    "name": outcome.name,
                    "probability": prob,
                    "is_winner": bool(outcome.is_winner),
                }
            )

    # Every branch gone is the old whole-request degrade, and it keeps the old
    # answer: an empty payload the caller must not store. A branch DEFERRED by
    # the budget counts here for the same reason a branch lost to an expiry
    # does: nothing ran, so an empty `families` is an artefact of the bound and
    # not an answer about this team (gotcha #53).
    if len(lost) + len(deferred) == len(branches):
        return _payload([]), True

    payload = _payload(group_prop_families(list(by_market.values())))
    for _name in lost:
        # LOSS_PARTIAL, not LOSS_DEGRADED: the headline answer — this team's own
        # futures, via the FK branch — survived; what is missing is real content
        # beside it. The severity is declared HERE, at the swallow point, because
        # this is the only place that knows which branch was lost.
        note_build_loss(payload, f"{_REASON_TIMEOUT}{_name}", LOSS_PARTIAL)
    for _name in deferred:
        # A DIFFERENT REASON STRING, deliberately. `branch_timeout` means we
        # tried and the database ran out of time; `branch_deferred` means we
        # chose not to spend the reader's wait on it. Collapsing the two would
        # hide a real regression — a branch that starts timing out — inside a
        # reason that is expected and benign.
        note_build_loss(payload, f"{_REASON_DEFERRED}{_name}", LOSS_PARTIAL)
    return payload, False


def _stored_mirror(rc, keys: ConceptCacheKeys) -> tuple[Any, bool]:
    """The 24h mirror's exact bytes, and whether they hold a COMPLETE answer.

    Both halves come from ONE read, and that is the whole point of the function
    (CERT-480 finding 1). The bytes are what the caller hands to
    `publish_mirror_if_unchanged` as its precondition, so the value that was
    JUDGED here and the value that is COMPARED there are guaranteed to be the
    same observation. Re-reading to get the bytes would leave a window between
    the two reads and put the race straight back.

    Read through `read_slot_raw`, never a bare `rc.get` — a payload from a retired
    generation, or one that fails envelope validation, reads as a miss there and
    must read as "no mirror worth protecting" here too. Anything unreadable is
    False, which routes to "write the mirror": the safe direction, because the
    alternative is declining to store the only answer we have. The BYTES are still
    returned in that case, so the conditional write stays anchored to whatever is
    actually sitting in the slot.
    """
    try:
        raw, stored = read_slot_raw(rc, keys.stale)
    except Exception:
        return None, False
    if not isinstance(stored, dict):
        return raw, False
    envelope = stored.get(ENVELOPE_FIELD)
    if not isinstance(envelope, dict):
        return raw, False
    return raw, envelope.get("quality") == QUALITY_FULL


def _mirror_is_full(rc, keys: ConceptCacheKeys) -> bool:
    """Is the 24h mirror already holding a COMPLETE answer for this key?

    The predicate on its own, for callers that only want the verdict. A WRITER
    must not use this: by the time it acts on the answer, the answer can be
    false, and that is precisely CERT-480 finding 1. Writers take both halves
    from `_stored_mirror` and let the compare-and-set settle it.
    """
    return _stored_mirror(rc, keys)[1]


async def build_and_cache_prop_families(
    team: Team, db: AsyncSession, cap: int, rc=None, budget_ms: int | None = None
) -> tuple[dict, bool]:
    """Build one team's families, stamp the envelope, write both slots.

    One implementation for the route's cold path and the background refresh, so
    the two cannot drift in WHAT they store or WHERE.

    **An EMPTY build never writes.** The route's degrade path returns an empty
    `families` list on a statement timeout, and that empty list is indistinguishable
    from "this team genuinely has no families" once it is bytes in Redis. Writing
    it would put a timeout artefact behind a 24h mirror — the exact inversion of
    the tier's purpose. It is returned to the caller (a served empty section beats
    a 500) and dropped on the floor.

    🔴 LAT-P145 — THE THREE OUTCOMES, AND WHY A PARTIAL IS ONE OF THEM.
    A build that lost a branch but kept content is not the same event as a build
    that lost everything, and the difference is exactly what made the Giants' page
    slow forever: 27 real markets were fetched, then discarded, then not cached,
    so the next reader paid the same 12 s to be shown the same nothing.

    ==================  ===========================  ===================================
    build               stored                       served
    ==================  ===========================  ===================================
    full                primary + 24h mirror         `quality: full`
    partial, has rows   primary; mirror ONLY if the  `quality: partial`, with
                        stored mirror is not `full`  `quality_reasons` naming the branch
    nothing at all      NOTHING                      empty, no envelope (unchanged)
    ==================  ===========================  ===================================

    The mirror rule is the module's own "an empty build never overwrites a good
    mirror", one notch further out. A partial is worth serving for a TTL and worth
    caching when there is nothing better — it is not worth freezing for 24 hours
    on top of a complete answer that is already there. The primary write is what
    ends the loop; the mirror guard is what stops the fix from costing a warmed
    team its content.
    """
    payload, unusable = await build_prop_families(team, db, cap, budget_ms=budget_ms)
    # Pop the private loss list FIRST and unconditionally — it must not reach
    # Redis or the wire on any path, including the ones that return early.
    quality, reasons = take_build_quality(payload)
    if unusable:
        return payload, True

    keys = prop_families_cache_keys(team.id, _resolve_cap(cap))
    stamped = stamp_envelope(
        payload,
        created_at=datetime.now(timezone.utc),
        # An explicit allowed unknown per the contract: a prop-family answer is a
        # composition over many markets with no single lifecycle event of its own,
        # and claiming a watermark we cannot compute is a fabrication (#1678
        # finding 3).
        lifecycle_watermark=None,
        quality=quality,
        quality_reasons=reasons,
    )

    if quality == QUALITY_FULL:
        write_payload(rc, keys, stamped, primary_ttl=PROP_FAMILIES_PRIMARY_TTL)
        return stamped, False

    if not payload.get("families"):
        # A partial that produced no content is, to a reader, the same blank
        # section a timeout produces — and gotcha #53 says a blank is a response
        # shape, not an absence. Serve it with its envelope so the blankness is
        # attributable, but do not store it.
        logger.warning(
            "prop-families: partial build for team %s produced no families (%s) — "
            "served, not stored",
            team.id, ",".join(reasons),
        )
        return stamped, True

    # 🔴 A DEFERRAL IS AN IOU AND AN IOU DOES NOT GET THE 24-HOUR SLOT (CERT-557).
    # The table above was written when the only way to be `partial` was to lose a
    # branch to the database, and for that case it is still right: a timeout
    # partial is the best answer anyone can get, so it is worth the mirror when
    # nothing better is stored. A DEFERRED partial is a different object. Nothing
    # has established that its missing branch is unreachable — a budgeted reader
    # declined to wait for it, to hand the page over in 2.5 s. Freezing that
    # choice into a slot that outlives it by 24 hours converts a courtesy owed to
    # ONE reader into a day of narrowed pages for everyone, and it is precisely
    # the "deferral becomes a permanent narrowing" failure this queue's own
    # docstring promises the background dispatch prevents. So it takes the
    # 15-minute primary — the page stays fast — and leaves the long-lived slot to
    # the unbudgeted completion that is scheduled behind it.
    #
    # A build carrying BOTH a deferral and a timeout is treated as a timeout
    # partial: it contains a fact about the database, not only about our budget.
    if _deferral_reasons(reasons) and not any(
        r.startswith(_REASON_TIMEOUT) for r in reasons
    ):
        write_payload(
            rc, keys, stamped, primary_ttl=PROP_FAMILIES_PRIMARY_TTL, mirror=False
        )
        return stamped, False

    # The primary write is what ends the rebuild loop, so it is unconditional and
    # goes first. The mirror is the CONTESTED slot: it is settled separately, by a
    # compare-and-set against the very bytes the read above judged, so that a
    # complete build landing in between cannot be overwritten (CERT-480 finding 1).
    mirror_raw, mirror_is_full = _stored_mirror(rc, keys)
    write_payload(
        rc,
        keys,
        stamped,
        primary_ttl=PROP_FAMILIES_PRIMARY_TTL,
        mirror=False,
    )
    if not mirror_is_full and not publish_mirror_if_unchanged(
        rc, keys, stamped, mirror_raw
    ):
        # Somebody published to this key between the read and the write. On this
        # path that is a COMPLETE build racing a partial, and LOSING that race is
        # the correct outcome, not an error — so the response is unaffected.
        # Logged at info because it is this fix's only observable footprint: it
        # should be rare, and a flood of it means same-key cold builds have
        # stopped being single-flighted.
        logger.info(
            "prop-families: mirror for team %s changed under a partial build — "
            "declined to publish (%s)",
            team.id, ",".join(reasons),
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

    The one shape that does NOT carry `cache` is the build that lost EVERY branch:
    it is served (an empty section beats a 500) and is deliberately neither
    stamped nor stored, so a consumer can tell a real empty answer from a
    timeout's by the envelope's absence.

    LAT-P145: a build that lost SOME branches does carry the envelope, with
    `quality: "partial"` and `quality_reasons` naming the branch that expired
    (e.g. `["branch_timeout:outcome_name"]`). That is the shape an NFL team page
    returns today while the season is more than a fortnight out — and it is
    cached, so it is paid for once rather than by every reader.

    LAT-P164: a cold build is BUDGETED, so `quality_reasons` may also carry
    `branch_deferred:<name>` — a branch this reader was not asked to wait for.
    Any such build schedules the same single-flight rebuild a mirror serve does,
    which runs unbudgeted and publishes the complete answer for everyone after.
    Without that dispatch the deferral would not be a deferral: it would be a
    silent, permanent narrowing of the page for one primary TTL at a time.
    """
    team = await resolve_team(db, identifier)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    cap = _resolve_cap(limit)
    keys = prop_families_cache_keys(team.id, cap)
    rc = get_client()

    # 1. A live hit inside the primary TTL.
    #
    #    🔴 AND A LIVE HIT IS NOT AUTOMATICALLY A COMPLETE ANSWER (CERT-557). This
    #    return used to be unconditional, which is what turned a deferral into a
    #    loss: the cold build wrote a partial to the primary and dispatched the
    #    completion, the completion could itself fall short, and every reader for
    #    the next fifteen minutes hit THIS line and went home — the one path that
    #    inspects quality is the one path a warm reader never reaches. The content
    #    was missing, nothing was scheduled, and nothing said so.
    #
    #    So a live hit that carries an IOU takes this window's one completion
    #    attempt (`_claim_completion_attempt`) before it returns. It is two Redis
    #    round-trips on a path already doing one, it is bounded to a single
    #    unbudgeted build per key per TTL, and it never changes what this reader
    #    is served or when — the payload is returned either way.
    primary = read_slot(rc, keys.primary)
    if primary is not None:
        _quality, _reasons = envelope_quality(primary)
        if (
            _quality != QUALITY_FULL
            and _deferral_reasons(_reasons)
            and _claim_completion_attempt(rc, keys)
        ):
            _schedule_refresh(rc, keys, team.id, cap)
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
    #
    #    LAT-P164: and it is BUDGETED, because this is the only path on which a
    #    person is holding a blank section open while Postgres works. It is the
    #    path the ring caught nine times in 24 h, six of them at 12.4-13.0 s.
    payload, degraded = await build_and_cache_prop_families(
        team, db, cap, rc, budget_ms=_READER_BUDGET_MS
    )

    # LAT-P164: a budgeted build that did not get everything hands the rest to
    # the background. This is the SAME single-flight dispatch step 2 makes, for
    # the same reason, and it is what makes a deferral a WAIT rather than a LOSS:
    # the rebuild runs unbudgeted and publishes the complete answer for every
    # reader after this one. It covers the `degraded` case too — a build that
    # got nothing is the case that most needs somebody to try again — which is
    # why it is computed from the envelope BEFORE that branch returns.
    #
    # CERT-557: this reads the envelope through `envelope_quality`, the same
    # function the refresh task now uses, so the dispatcher and the destination
    # cannot form different opinions about what the build achieved. It is NOT
    # gated on `_claim_completion_attempt`: a cold build is already the rare path
    # (nothing cached at all), it is the moment the deferral is INCURRED rather
    # than merely observed, and gating it would let the marker left by a previous
    # window suppress the only dispatch this build gets.
    _quality, _ = envelope_quality(payload)
    if _quality != QUALITY_FULL:
        _schedule_refresh(rc, keys, team.id, cap)

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
