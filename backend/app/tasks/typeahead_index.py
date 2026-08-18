"""Option D (#1866): build and police the narrow typeahead index.

WHAT THIS IS FOR, in one line: ``/typeahead``'s trigram surface is **688.6 MB**
against a **1 GiB** ``shared_buffers`` (67.2 % of the pool, shared with every
other query in the product), so the pages it needs are evicted continuously and
the tail pays a cold read. This module projects the same searchable content into
ONE narrow table so the working set FITS. The full mechanism, the three
measurements that closed the alternatives, and the registered D1-D4 predictions
are in ``docs/audits/latency/lat-p063-option-d-mechanism-and-prediction.md``.

THIS MODULE IS TWO TASKS, AND THE SECOND ONE IS NOT OPTIONAL.

``rebuild_typeahead_index``
    Bounded, resumable projector. Walks each source table in id order, writes
    the projection, and remembers where it stopped. Safe to run repeatedly; a
    second pass over unchanged rows writes nothing.

``typeahead_index_sentinel``
    D4. Samples live source rows, RE-PROJECTS them, and compares against what
    the index holds. Reports drift and, above a threshold, says so loudly.

**Why D4 ships with the table or the table does not ship.** This is a second
copy of truth, and #1866's entire history is instruments that reported success
while doing nothing — a trade backfill that recorded SUCCESS every 6 h for ten
weeks while recovering nothing (gotcha #53), a warmer whose ``fresh`` skip could
never fire, two tests that passed while asserting a model production had
refuted. A denormalised index that silently goes stale is a WORSE defect than
the slow query it replaces, because the slow query was at least correct. Both
tasks are enrolled in :data:`app.utils.task_verdict.ENFORCED_TASKS` and both
return a real ``terminal`` — enrolling without one is a no-op (the summary
classifies as a non-authoritative unknown and still reads GREEN).

NOTHING READS THIS TABLE YET. That is a registered gate, not an unfinished job:
D3 says "> 350 MB ⇒ the sizing model is wrong; re-derive **before building the
read path**", and D3 cannot be measured until the table exists and is populated
in production. The read path is the next queue, after D3 grades.

THE PROJECTIONS ARE THE RECALL CONTRACT. ``search_text`` is the ONLY column
matching will read, so "does this table find what the trigram surface found" is
a property of :func:`project_team` and its siblings and of nothing else. That is
what D2's 46 armed gold probes exist to prove, and why ANY movement in
``entity_top_1_rate`` (0.9130434782608695) or MRR (0.9347826086956522) HALTS the
rollout: an inequivalent index is a correctness bug wearing a latency fix's
clothes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

# --- Entity vocabulary -------------------------------------------------------
#: The searchable families, in the order the builder sweeps them. Stable
#: strings: they are stored in the table and a rename is a data migration, not a
#: refactor.
TEAM = "team"
EVENT = "event"
FUTURES_MARKET = "futures_market"
FUTURES_OUTCOME = "futures_outcome"

ENTITY_TYPES: tuple[str, ...] = (TEAM, EVENT, FUTURES_MARKET, FUTURES_OUTCOME)

# --- Bounds ------------------------------------------------------------------
#: Rows read per source page. Small enough that one page is a sub-second read
#: even cold, so the budget check below has fine granularity.
PAGE_SIZE = 2_000

#: The longest single uninterrupted operation, not the loop bound. Bounding only
#: the loop boundary is the `project_budget_guard_inner_op` mistake: a task can
#: honour a 90 s budget at every check and still be SIGKILLed inside one page.
PAGE_TIMEOUT_SECONDS = 25

#: Default wall budget for a scheduled incremental pass. The beat entry runs at
#: :23/:53 on the `heavy` lane; 90 s twice an hour is ~2.5 % of ONE of heavy's
#: two slots, which is the number that made adding it to that lane defensible at
#: all after #1609 put 45.9 % of a slot there.
DEFAULT_BUDGET_SECONDS = 90

#: Redis key holding the per-entity-type resume cursor.
CURSOR_KEY = "bainluck:typeahead_index:cursor"

#: How many rows per family the sentinel re-projects. Sampled, not exhaustive —
#: an exhaustive comparison is a second full build and would cost what the table
#: is trying to save.
SENTINEL_SAMPLE_SIZE = 250

#: Drift above this fraction of the sample is REAL and must not read GREEN.
#: Deliberately NOT zero: a row legitimately changes between the builder's last
#: visit and the sentinel's read, and an alarm that fires on normal operation is
#: an alarm nobody reads (the retired grid health score, verbatim).
SENTINEL_DRIFT_THRESHOLD = 0.02


# --- Content hashing ---------------------------------------------------------
def content_hash_for(
    display_text: str,
    search_text: str,
    sport_key: str | None,
    rank_hint: float,
) -> int:
    """A stable SIGNED 64-bit digest of a projection's content.

    Signed, and that is not incidental: PostgreSQL ``BIGINT`` is signed, so an
    unsigned 64-bit digest overflows on insert for half of all inputs — a bug
    that shows up on ~50 % of rows, which is frequent enough to look like
    corruption and rare enough to survive a small test fixture.

    BIGINT rather than the sha256 hex a hash column usually is, because 64 hex
    characters cost 64 B/row = **24 MB** across this table — more than a third of
    its heap, spent on drift detection for a table whose entire justification is
    heap width (see the model docstring).

    ``rank_hint`` is rounded before hashing. It is a float, and an unrounded
    float in a digest means a bit of representation noise rewrites a row that
    did not change — which would show up as permanent phantom drift on the
    sentinel and make the one instrument that is supposed to detect real drift
    useless.
    """
    payload = "\x1f".join(
        (
            display_text or "",
            search_text or "",
            sport_key or "",
            f"{round(float(rank_hint or 0.0), 4):.4f}",
        )
    )
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=8).digest()
    unsigned = int.from_bytes(digest, "big", signed=False)
    # Fold into the signed range PostgreSQL BIGINT actually holds.
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


@dataclass(frozen=True)
class Projection:
    """One row's worth of searchable content, before it touches the database."""

    entity_type: str
    entity_id: str
    display_text: str
    search_text: str
    sport_key: str | None
    rank_hint: float

    @property
    def content_hash(self) -> int:
        return content_hash_for(
            self.display_text, self.search_text, self.sport_key, self.rank_hint
        )

    def as_row(self, now: datetime) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "display_text": self.display_text[:300],
            "search_text": self.search_text,
            "sport_key": self.sport_key,
            "rank_hint": self.rank_hint,
            "content_hash": self.content_hash,
            "is_active": True,
            "refreshed_at": now,
        }


def _norm(value: Any) -> str:
    """Lowercase, collapse whitespace. The ONLY normalisation applied.

    Deliberately does NOT case-fold or NFC-normalise beyond ``lower()``. The
    candidate-base work (#1459/#1475) established that identity v2 is
    collision-free precisely because it dedupes and sorts and does NOT fold —
    folding merges entities that are genuinely distinct. The same restraint
    applies here: this is a recall surface, and a fold that merges two teams is
    a recall bug that D2's gold probes would catch as a top-1 change.
    """
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def _search_text(*parts: Any) -> str:
    """Join the match haystack, de-duplicated, order-stable.

    Duplicate aliases are common (a team whose ``alternate_names`` repeats its
    own ``name``) and every duplicate is bytes in a table whose whole argument
    is bytes. Order is preserved rather than sorted so the text stays readable
    when a human is debugging a recall miss.
    """
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        text = _norm(part)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return " ".join(out)


def _alias_strings(raw: Any) -> list[str]:
    """Pull alias text out of the JSONB shapes ``alternate_names`` really has.

    It is a list in most rows, a dict in some, and occasionally a JSON string
    that was never decoded. Guarded on type rather than assumed, because the
    typeahead route's own alias arm casts this column to String and matches the
    raw JSON — so a shape this function silently skips is recall the trigram
    surface HAS and the table would not, which is exactly the D2 failure.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:  # noqa: BLE001 — a malformed alias blob is not fatal
            return [raw]
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(v) for v in raw if isinstance(v, (str, int, float))]


# --- Projections -------------------------------------------------------------
def project_team(row: Any, sport_key: str | None) -> Projection:
    """A team/player row.

    The haystack carries name + abbreviation + aliases + location because the
    live typeahead's team arm matches all four (``Team.name``,
    ``Team.abbreviation``, ``cast(Team.alternate_names, String)``). Dropping any
    one of them here would be a recall regression that only shows up on the
    queries that used it — which is precisely the class D2 arms 46 probes
    against.
    """
    aliases = _alias_strings(getattr(row, "alternate_names", None))
    return Projection(
        entity_type=TEAM,
        entity_id=str(row.id),
        display_text=str(row.name or "")[:300],
        search_text=_search_text(
            row.name,
            getattr(row, "abbreviation", None),
            getattr(row, "location", None),
            *aliases,
        ),
        sport_key=sport_key,
        rank_hint=1.0,
    )


def project_event(row: Any, sport_key: str | None) -> Projection:
    """A game. Both team names, because the live arm matches both."""
    display = f"{row.away_team_name} @ {row.home_team_name}"
    return Projection(
        entity_type=EVENT,
        entity_id=str(row.id),
        display_text=display[:300],
        search_text=_search_text(row.home_team_name, row.away_team_name),
        sport_key=sport_key,
        rank_hint=0.8,
    )


def project_futures_market(row: Any) -> Projection:
    return Projection(
        entity_type=FUTURES_MARKET,
        entity_id=str(row.id),
        display_text=str(row.name or "")[:300],
        search_text=_search_text(row.name),
        sport_key=getattr(row, "llm_sport_category", None),
        rank_hint=0.6,
    )


def project_futures_outcome(row: Any, market_name: str | None) -> Projection:
    """An outcome — the family that owns the 411 MB index this table replaces.

    The haystack is the outcome name AND its market's name. The live path
    reaches an outcome through ``FuturesOutcome.name ILIKE`` alone, but a user
    typing "best picture oppenheimer" is naming both, and the two-word case is
    the one the current surface answers worst. Recording the widening here
    because it is a deliberate recall CHANGE, and D2 must be read knowing it:
    if a gold disposition moves, this line is the first suspect.
    """
    return Projection(
        entity_type=FUTURES_OUTCOME,
        entity_id=str(row.id),
        display_text=str(row.name or "")[:300],
        search_text=_search_text(row.name, market_name),
        sport_key=None,
        rank_hint=0.4,
    )


# --- Drift (D4's core, kept pure so it is testable without a database) -------
@dataclass(frozen=True)
class DriftReport:
    """What a sentinel sample proves about the index."""

    sampled: int
    missing: int          # source row has no index row at all
    stale: int            # index row exists, content_hash disagrees
    inactive: int         # index row is tombstoned but the source is live
    clean: int

    @property
    def drifted(self) -> int:
        return self.missing + self.stale + self.inactive

    @property
    def drift_rate(self) -> float:
        return (self.drifted / self.sampled) if self.sampled else 0.0

    @property
    def is_clean(self) -> bool:
        return self.drift_rate <= SENTINEL_DRIFT_THRESHOLD

    def as_dict(self) -> dict[str, Any]:
        return {
            "sampled": self.sampled,
            "missing": self.missing,
            "stale": self.stale,
            "inactive": self.inactive,
            "clean": self.clean,
            "drifted": self.drifted,
            "drift_rate": round(self.drift_rate, 6),
            "is_clean": self.is_clean,
        }


def compare_projections(
    expected: Iterable[Projection],
    indexed: dict[tuple[str, str], tuple[int, bool]],
) -> DriftReport:
    """Compare freshly-projected sources against what the index holds.

    ``indexed`` maps ``(entity_type, entity_id) -> (content_hash, is_active)``.

    Pure on purpose. D4 requires proving the sentinel DETECTS an injected drift,
    and a detector that can only be exercised against a live database is a
    detector whose one interesting property is untested — which is how #1866
    accumulated a warmer whose skip branch could never fire and two tests that
    passed while asserting a refuted model.
    """
    sampled = missing = stale = inactive = clean = 0
    for projection in expected:
        sampled += 1
        key = (projection.entity_type, projection.entity_id)
        found = indexed.get(key)
        if found is None:
            missing += 1
            continue
        stored_hash, is_active = found
        if not is_active:
            inactive += 1
        elif stored_hash != projection.content_hash:
            stale += 1
        else:
            clean += 1
    return DriftReport(
        sampled=sampled, missing=missing, stale=stale, inactive=inactive, clean=clean
    )


# --- Cursor ------------------------------------------------------------------
def _load_cursor() -> dict[str, int]:
    """Resume point per entity type. A missing/❨unreadable❩ cursor restarts at 0.

    Restarting at 0 is safe and is the deliberate choice over failing: the pass
    is idempotent (unchanged rows write nothing), so the worst case of a lost
    cursor is wasted reads, while the worst case of trusting a corrupt one is a
    permanently unvisited tail — and gotcha #41's lesson, in both directions, is
    that the tail is what never gets reached.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(CURSOR_KEY)
        if not raw:
            return {}
        data = json.loads(raw)
        return {k: int(v) for k, v in data.items() if k in ENTITY_TYPES}
    except Exception:  # noqa: BLE001
        return {}


def _save_cursor(cursor: dict[str, int]) -> bool:
    """Persist the resume point. Returns False if it could not be written."""
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().set(CURSOR_KEY, json.dumps(cursor))
        return True
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_index: cursor write failed; next pass restarts")
        return False


# --- The builder -------------------------------------------------------------
async def _upsert(session, rows: Sequence[dict[str, Any]]) -> int:
    """Insert-or-refresh a page. Returns rows actually written.

    ``WHERE content_hash IS DISTINCT FROM excluded.content_hash`` is what makes
    a repeat pass nearly free and makes ``refreshed_at`` mean something: an
    unchanged row is not rewritten, so no dead tuple, no index churn, and the
    write count is a real measure of change rather than of activity.

    The cost, stated because it is a real trade: ``refreshed_at`` then does NOT
    advance on an unchanged row, so it is "last time this row CHANGED", not
    "last time it was verified". The sentinel therefore reads drift by
    re-projecting sources, never by reading ``refreshed_at`` — an age-based
    staleness check over this column would flag every stable row in the table.
    """
    if not rows:
        return 0
    from app.models.models import TypeaheadIndex

    stmt = pg_insert(TypeaheadIndex).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        constraint="uq_typeahead_index_entity",
        set_={
            "display_text": stmt.excluded.display_text,
            "search_text": stmt.excluded.search_text,
            "sport_key": stmt.excluded.sport_key,
            "rank_hint": stmt.excluded.rank_hint,
            "content_hash": stmt.excluded.content_hash,
            "is_active": stmt.excluded.is_active,
            "refreshed_at": stmt.excluded.refreshed_at,
        },
        where=TypeaheadIndex.content_hash.is_distinct_from(stmt.excluded.content_hash),
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def _page_teams(session, after_id: int, limit: int) -> list[Projection]:
    from app.models.models import Sport, Team

    rows = (
        await session.execute(
            select(Team, Sport.key)
            .join(Sport, Team.sport_id == Sport.id, isouter=True)
            .where(Team.id > after_id)
            .order_by(Team.id)
            .limit(limit)
        )
    ).all()
    return [project_team(team, sport_key) for team, sport_key in rows]


async def _page_events(session, after_id: int, limit: int) -> list[Projection]:
    """Recent + upcoming games only.

    The horizon is the same shape the live typeahead uses — it has never offered
    a game from three years ago — and it is the difference between ~22 k rows
    and every event ever recorded. An unbounded events arm would blow the D3
    sizing model on its own.
    """
    from datetime import timedelta

    from app.models.models import Event, Sport

    floor = datetime.now(timezone.utc) - timedelta(days=120)
    rows = (
        await session.execute(
            select(Event, Sport.key)
            .join(Sport, Event.sport_id == Sport.id, isouter=True)
            .where(Event.id > after_id, Event.commence_time >= floor)
            .order_by(Event.id)
            .limit(limit)
        )
    ).all()
    return [project_event(event, sport_key) for event, sport_key in rows]


async def _page_futures_markets(session, after_id: int, limit: int) -> list[Projection]:
    from app.models.models import FuturesMarket

    rows = (
        await session.execute(
            select(FuturesMarket)
            .where(FuturesMarket.id > after_id, FuturesMarket.status == "open")
            .order_by(FuturesMarket.id)
            .limit(limit)
        )
    ).scalars().all()
    return [project_futures_market(row) for row in rows]


async def _page_futures_outcomes(session, after_id: int, limit: int) -> list[Projection]:
    from app.models.models import FuturesMarket, FuturesOutcome

    rows = (
        await session.execute(
            select(FuturesOutcome, FuturesMarket.name)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .where(FuturesOutcome.id > after_id, FuturesMarket.status == "open")
            .order_by(FuturesOutcome.id)
            .limit(limit)
        )
    ).all()
    return [project_futures_outcome(row, market_name) for row, market_name in rows]


_PAGERS = {
    TEAM: _page_teams,
    EVENT: _page_events,
    FUTURES_MARKET: _page_futures_markets,
    FUTURES_OUTCOME: _page_futures_outcomes,
}


async def _rebuild_typeahead_index(
    budget_seconds: int = DEFAULT_BUDGET_SECONDS,
    page_size: int = PAGE_SIZE,
    entity_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Bounded, resumable projection pass.

    TERMINAL SEMANTICS, and they are the point of enrolling this task:

    * ``complete`` — every family reached its end within the budget. The index
      is caught up as of this pass.
    * ``partial`` — the budget ran out first. Real progress, resumable, and it
      must NEVER read GREEN, because "the sweep is behind" and "the sweep is
      done" are the two states this task exists to distinguish and they look
      identical from the outside (gotcha #53).
    * ``failed`` — the cursor could not be persisted. Progress was made but is
      unresumable, so the next pass silently redoes it; that is a real defect
      even though every row written was correct.
    """
    import asyncio

    from app.services.database import async_session_maker

    families = tuple(entity_types or ENTITY_TYPES)
    started = time.monotonic()
    deadline = started + budget_seconds
    cursor = _load_cursor()
    written = 0
    scanned = 0
    exhausted: list[str] = []
    stopped_at: str | None = None

    async with async_session_maker() as session:
        for family in families:
            pager = _PAGERS[family]
            after = int(cursor.get(family, 0))
            while True:
                if time.monotonic() >= deadline:
                    stopped_at = family
                    break
                try:
                    projections = await asyncio.wait_for(
                        pager(session, after, page_size),
                        timeout=PAGE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # Bound the INNER op, not just the loop boundary. A page that
                    # cannot be read inside 25 s is a page that would have taken
                    # the whole budget and then been SIGKILLed into `no_data`.
                    logger.warning("typeahead_index: %s page timed out after %s", family, after)
                    stopped_at = family
                    break
                if not projections:
                    # End of this family. Reset so the next pass re-verifies it
                    # from the top: this is a RECONCILE, and a cursor parked at
                    # the end would mean rows 1..N are never looked at again.
                    exhausted.append(family)
                    cursor[family] = 0
                    break
                now = datetime.now(timezone.utc)
                written += await _upsert(session, [p.as_row(now) for p in projections])
                await session.commit()
                scanned += len(projections)
                after = max(int(p.entity_id) for p in projections)
                cursor[family] = after
            if stopped_at:
                break

    persisted = _save_cursor(cursor)
    elapsed = round(time.monotonic() - started, 2)

    if not persisted:
        terminal = "failed"
    elif stopped_at:
        terminal = "partial"
    else:
        terminal = "complete"

    summary = {
        "terminal": terminal,
        "scanned": scanned,
        "written": written,
        "elapsed_seconds": elapsed,
        "families_exhausted": exhausted,
        "cursor_persisted": persisted,
        "budget_seconds": budget_seconds,
    }
    if stopped_at:
        summary["stopped_at"] = stopped_at
    logger.info("typeahead_index rebuild: %s", summary)
    return summary


# --- The sentinel (D4) -------------------------------------------------------
async def _sample_sources(session, family: str, limit: int) -> list[Projection]:
    """A pseudo-random sample of live source rows, re-projected.

    ``ORDER BY random()`` is fine at this size and is the honest choice over a
    cheaper "newest N": drift concentrates in rows the builder has not revisited
    recently, and newest-first is exactly the sample that would MISS them —
    gotcha #41's failure, applied to an alarm instead of a backfill.
    """
    pager = _PAGERS[family]
    # Page from a random offset rather than ORDER BY random() over the whole
    # table: the pagers are id-ordered and cheap, and a random id floor gives a
    # spread sample for one index scan instead of a full sort.
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Team

    model = {
        TEAM: Team,
        EVENT: Event,
        FUTURES_MARKET: FuturesMarket,
        FUTURES_OUTCOME: FuturesOutcome,
    }[family]
    max_id = (await session.execute(select(func.max(model.id)))).scalar() or 0
    if max_id <= 0:
        return []
    import random

    floor = random.randint(0, max(0, max_id - 1))
    sample = await pager(session, floor, limit)
    if len(sample) < limit:
        # Near the top of the id range: wrap so a small tail never under-samples.
        sample = sample + await pager(session, 0, limit - len(sample))
    return sample[:limit]


async def _run_typeahead_index_sentinel(
    sample_size: int = SENTINEL_SAMPLE_SIZE,
) -> dict[str, Any]:
    """D4. Re-project live sources and prove the index still agrees with them.

    Reports per-family drift and an overall verdict. ``terminal`` is
    ``complete`` when a sample was actually taken and the index agreed, and
    ``failed`` when drift exceeded the threshold — a loud, not-GREEN state, on
    purpose. A sentinel that reports its own findings as a healthy run is the
    defect it was built to catch.
    """
    from app.models.models import TypeaheadIndex
    from app.services.database import async_session_maker

    per_family: dict[str, Any] = {}
    totals = {"sampled": 0, "missing": 0, "stale": 0, "inactive": 0, "clean": 0}

    async with async_session_maker() as session:
        # An EMPTY index is not drift — it is "the backfill has not run yet".
        # Reporting 100 % drift for that state would make the sentinel scream
        # through the whole initial build and train everyone to ignore it.
        indexed_total = (
            await session.execute(select(func.count()).select_from(TypeaheadIndex))
        ).scalar() or 0
        if indexed_total == 0:
            return {
                "terminal": "no_work",
                "reason": "index_empty",
                "indexed_rows": 0,
                "note": "backfill has not populated the table yet; not drift",
            }

        for family in ENTITY_TYPES:
            expected = await _sample_sources(session, family, sample_size)
            if not expected:
                per_family[family] = {"sampled": 0, "note": "no source rows"}
                continue
            keys = [p.entity_id for p in expected]
            rows = (
                await session.execute(
                    select(
                        TypeaheadIndex.entity_id,
                        TypeaheadIndex.content_hash,
                        TypeaheadIndex.is_active,
                    ).where(
                        TypeaheadIndex.entity_type == family,
                        TypeaheadIndex.entity_id.in_(keys),
                    )
                )
            ).all()
            indexed = {
                (family, entity_id): (content_hash, is_active)
                for entity_id, content_hash, is_active in rows
            }
            report = compare_projections(expected, indexed)
            per_family[family] = report.as_dict()
            for key in totals:
                totals[key] += getattr(report, key)

    overall = DriftReport(**totals)
    summary = {
        "terminal": "complete" if overall.is_clean else "failed",
        "indexed_rows": indexed_total,
        "threshold": SENTINEL_DRIFT_THRESHOLD,
        "overall": overall.as_dict(),
        "families": per_family,
    }
    if not overall.is_clean:
        summary["errors"] = [
            f"typeahead_index drift {overall.drift_rate:.4f} exceeds "
            f"{SENTINEL_DRIFT_THRESHOLD} ({overall.drifted}/{overall.sampled} rows)"
        ]
        logger.error("typeahead_index sentinel DRIFT: %s", summary)
    else:
        logger.info("typeahead_index sentinel clean: %s", overall.as_dict())
    return summary
