"""live/039 — the ONE-TIME drain: every attached event of the last 30 days.

Alex: *"if we had Polymarket integration we could backfill all the events we
don't have probabilities for from the last 30 days."* We do, so this runs it.

WHAT THIS IS NOT. It is not a second nightly. `backfill_thin_event_charts`
(live/036) pre-warms the ±7-day reader window on reader-reachable sports, and
`plan_on_demand_fill` catches whatever a person actually opens. Both are
steady-state. This is a one-off drain of the 30-day backlog those two were
explicitly told to stop chasing, and when it is done it is done — no beat entry,
no schedule. It is triggered, it checkpoints, it is re-triggered until it reports
`exhausted`.

MEASURED POPULATION, production 2026-09-02:

    events with commence_time in the last 30d and >=1 Kalshi/Polymarket market
                                                              19,646
    ... of which hold fewer than 20 Kalshi/Polymarket points  18,460
    ... of which hold NONE at all                             14,240

THE ORDER IS THE SHIP. 13,591 of those 19,646 are `soccer_other`, `esports` and
`americanfootball_other` — the half live/036 called "February soccer". Draining
in id or time order would spend the first several hours there and reach the US
Open last. So the sweep walks PRIORITY TIERS: the US Open cohort first, then
everything else a reader can reach, then the remainder. Each tier keeps its own
keyset cursor, and a tier is finished before the next one starts. A drain that
delivers the named ship in its first hour is worth more than one that delivers
everything in its eighth.

THE CURSOR IS A KEYSET ON (commence_time, event_id), for the reason live/035
learned the hard way: `futures_markets.created_at` is transaction-time and a
poll commits hundreds of rows inside one `now()`, so a cursor keyed on a
timestamp alone steps over the tail of any tied cohort larger than one page and
loses it permanently. `events.commence_time` ties just as readily — 438 events
share one value in this very window — so the id half is load-bearing here too.

GRANULARITY. The queue asked for a flat hourly fill as a cost bound. This uses
:func:`granularity_floor_minutes` instead, which is the same bound where it
matters (hourly past `COARSE_GRANULARITY_AGE_DAYS`) and finer where a reader
benefits (1-minute inside it) — a two-day-old US Open match drawn as 48 hourly
dots loses exactly the in-match swing the chart is opened for. `min_period_minutes`
overrides it for an operator who wants the cheap pass regardless.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import NamedTuple, Optional, Sequence

logger = logging.getLogger(__name__)


#: The window Alex named. Not Kalshi's retention floor (~74-86 days, gotcha #35)
#: — that is where history STOPS being available, and this is a deliberately
#: smaller, finishable bite inside it.
THIRTY_DAY_WINDOW_DAYS = 30

#: A chart is worth filling below this many points. The queue's number, and it is
#: deliberately a FLAT threshold rather than `is_thin_chart`'s lifetime-scaled
#: one: this pass is about the events that are a dot or a stub, not about topping
#: up a curve that already has a shape. Bounded inside the SQL by a `LIMIT`, so
#: the count costs at most this many index rows per event rather than a full
#: count over a very large table — the shape that made live/035's first
#: selection query time out.
THIRTY_DAY_THIN_POINTS = 20

#: Politeness between events. Both venues are being asked for history nobody is
#: paying us for, across tens of thousands of events. At ~2-3 requests per event
#: this holds the sweep near 3 req/s, which is far under either venue's limit and
#: still drains a 900s batch's worth of work.
INTER_EVENT_SLEEP_SECONDS = 0.25

#: Consecutive per-event failures before a batch gives up. A venue that has
#: started refusing us will refuse the next 200 events too, and burning the batch
#: to discover that costs the checkpoint nothing but costs the venue goodwill.
CONSECUTIVE_ERROR_ABORT = 25

#: Redis checkpoint. One key per tier, so finishing the US Open tier cannot be
#: undone by the remainder tier's progress and vice versa. Same reasoning as
#: live/035's sweep cursor: a hint, never a fact, so an evicted key costs one
#: re-scan and never a wrong row.
CHECKPOINT_KEY = "chart_backfill_30d:cursor:{tier}"
#: Set once a tier's scan has reached the end of its population. Without it a
#: re-trigger after exhaustion restarts the tier from the top and re-judges
#: thousands of now-thick charts before it can reach the next tier.
#:
#: The VALUE is the marker, not just presence: `drained` (every event in this
#: tier was asked and answered) or `drained_with_failures` (the retry budget ran
#: out with events still unreachable). The two must not read the same.
TIER_DONE_KEY = "chart_backfill_30d:done:{tier}"

#: 🔴 A FAILED EVENT IS RETRIED, NOT MARKED DONE — and the retry is per EVENT,
#: not per tier. A Redis HASH of `event_id -> attempts so far`. An event whose
#: venue refused us goes in here; the next trigger drains this hash BEFORE it
#: scans new ground, so a failure at the tail of a tier costs a handful of
#: re-fetches rather than a re-walk of 13,591 events (most of which are
#: genuinely empty, would stay thin, and would be re-asked on every lap).
#:
#: The cursor may therefore keep advancing past a failure without stranding it:
#: the hash is what remembers, and the tier cannot be marked done while it is
#: non-empty.
#:
#: 🔴 KNOWN BOUND, stated rather than hidden. Redis here is one shared 100MB LRU,
#: so this key CAN be evicted. If it is, the owed retries are forgotten and the
#: next exhausted scan marks the tier `drained` — the same false-`drained` shape
#: CERT-753 blocked, arriving by eviction instead of by logic. It is not
#: defended against with new durable state because the events remain thin and
#: therefore remain findable: the two steady-state rails still reach them, and
#: `reset=true` re-scans the window from the top. What is NOT acceptable is
#: leaving that unsaid, so it is said here and in the report.
RETRY_KEY = "chart_backfill_30d:retry:{tier}"
#: How many events in this tier blew their retry budget. Non-zero at the end is
#: the difference between `drained` and `drained_with_failures`.
GAVE_UP_KEY = "chart_backfill_30d:gaveup:{tier}"

#: Terminal done-markers. `drained_with_failures` is terminal too — the drain
#: stopped, and it says so by name rather than by looking finished.
DONE_CLEAN = "drained"
DONE_WITH_FAILURES = "drained_with_failures"

#: Attempts per event before the drain gives up on it. Bounded because an event
#: that can never be fetched — a token the venue has dropped, a market whose
#: history 500s forever — would otherwise hold its tier open indefinitely. When
#: the budget runs out the event is dropped from the retry hash and counted in
#: :data:`GAVE_UP_KEY`, which is what turns the tier's ending into
#: `drained_with_failures`. Neither strands the failures silently nor spins.
MAX_EVENT_RETRIES = 3

#: Source statuses that mean "we never got an answer", as opposed to "we got an
#: answer and it was empty". Only these make an event retryable.
FAILED_SOURCE_STATUSES = frozenset({"error", "fetch_failed"})


class Tier(NamedTuple):
    """One priority band of the drain."""

    name: str
    #: Human-readable reason this band goes where it goes, echoed into the verdict.
    why: str


#: Ordered. Tier 0 is Alex's addendum ("prioritize POLYMARKET history for US Open
#: matches"); tier 1 is live/036's reader-reachable set; tier 2 is the remainder,
#: which is the bulk and which nobody is waiting on.
TIERS: tuple[Tier, ...] = (
    Tier("us_open", "Alex's addendum — the US Open cohort is the named ship"),
    Tier("reachable", "live/036's reader-reachable sports"),
    Tier("remainder", "everything else attached inside the window"),
)


def is_us_open_sport_key(sport_key: Optional[str]) -> bool:
    """Whether this sport key can hold a US Open match row.

    🔴 Both spellings, and the second one is the trap live/036 already documented.
    The tournament-keyed rows (`tennis_atp_us_open`, `tennis_wta_us_open`) are the
    obvious half. The other half carries the PLAIN tour key: measured 2026-09-02,
    28 of that day's and the day before's US Open singles matches exist as two
    event rows — a Kalshi-native one on `tennis_atp`/`tennis_wta` with a
    ticker-derived midnight `commence_time` (gotcha #14), and a Polymarket-native
    one on `tennis_*_us_open`. The specimen this whole rail was built for
    (15300759, Vallejo v Monfils) is plain `tennis_atp`. A tier that matched only
    the tournament keys would drain the Polymarket half of each split pair and
    leave the Kalshi half — which is the row most readers actually land on —
    for tier 2.

    `tennis_atp`/`tennis_wta` also carry non-US-Open tour and Challenger matches
    in this window. That is accepted: this is an ORDERING, not a filter, and
    every event in every tier is drained eventually.

    🔴 SEGMENTS, NOT A SUBSTRING. `"us_open" in key` is the obvious spelling and
    it is wrong twice over on the real sports table: it matches
    `tennis_atp_aus_open_singles` — the AUSTRALIAN Open, because `us_open` is a
    substring of `aus_open` — and it matches `golf_us_open_winner`, a different
    sport's tournament entirely. Neither belongs in the tier that exists to put
    Alex's tennis cohort first.
    """
    if not sport_key:
        return False
    key = sport_key.lower()
    if key in ("tennis_atp", "tennis_wta"):
        return True
    if not key.startswith("tennis"):
        return False
    segments = key.split("_")
    return any(
        segments[i] == "us" and segments[i + 1] == "open"
        for i in range(len(segments) - 1)
    )


async def tier_sport_ids(session) -> dict[str, list[int]]:
    """`sports.id` for each tier, partitioned so no event is drained twice.

    The whole table is ~176 rows, so this is one trivial scan and the rules stay
    in tested pure functions rather than being re-expressed as a `LIKE` ladder in
    SQL that would drift away from them — the same discipline (and the same
    reason) as live/035's :func:`reachable_sport_ids`.
    """
    from sqlalchemy import select

    from app.models.models import Sport
    from app.tasks.event_chart_backfill import is_reader_reachable_sport_key

    rows = (await session.execute(select(Sport.id, Sport.key))).all()
    buckets: dict[str, list[int]] = {tier.name: [] for tier in TIERS}
    for sport_id, key in rows:
        if is_us_open_sport_key(key):
            buckets["us_open"].append(int(sport_id))
        elif is_reader_reachable_sport_key(key):
            buckets["reachable"].append(int(sport_id))
        else:
            buckets["remainder"].append(int(sport_id))
    return buckets


#: MEASURED at 3.9s over the full 19,646-event window on production 2026-09-02.
#:
#: The point-count subquery is wrapped in an inner `LIMIT :thin_points`, and that
#: is the whole reason this returns at all. live/035's first attempt counted every
#: point for every candidate and hit `statement_timeout`; counting a bounded
#: prefix answers the only question being asked — "are there fewer than N?" — for
#: at most N index rows per event. `>= :thin_points` is not distinguishable from
#: "far more", and nothing here needs to distinguish them.
THIRTY_DAY_CANDIDATES_SQL = """
    SELECT
        e.id                AS event_id,
        e.commence_time     AS commence_time,
        (
            SELECT COUNT(*) FROM (
                SELECT 1 FROM win_prob_snapshots w
                WHERE w.event_id = e.id
                  AND w.source IN ('kalshi', 'polymarket')
                LIMIT :thin_points
            ) capped
        )                   AS point_count
    FROM events e
    WHERE e.commence_time >= NOW() - make_interval(days => :window_days)
      AND e.commence_time <= NOW() + INTERVAL '1 day'
      AND e.sport_id IN :sport_ids
      -- EXISTS, not a JOIN + GROUP BY. The join form multiplies an event by its
      -- market count before the DISTINCT can collapse it, and a US Open event
      -- carries up to 14 Polymarket rows.
      AND EXISTS (
          SELECT 1 FROM futures_markets fm
          WHERE fm.event_id = e.id
            AND fm.source IN ('kalshi', 'polymarket')
      )
      -- The keyset. See the module docstring: `commence_time` ties in bulk
      -- (a ticker-derived midnight is shared by every match on a card), so the
      -- id half is what stops a tied cohort larger than one page from being
      -- stepped over and lost.
      AND (
          CAST(:after_ts AS timestamptz) IS NULL
          OR (e.commence_time, e.id)
               > (CAST(:after_ts AS timestamptz), CAST(:after_id AS bigint))
      )
    ORDER BY e.commence_time ASC, e.id ASC
    LIMIT :scan
"""


class DrainPage(NamedTuple):
    """One page of candidates judged inside one tier."""

    event_ids: list[int]
    #: `(commence_time, event_id)` of the last candidate LOOKED AT, thin or not.
    next_cursor: Optional[tuple]
    #: True when the scan reached the end of this tier's population.
    exhausted: bool
    scanned: int


async def select_thirty_day_page(
    session, *, sport_ids: Sequence[int], limit: int,
    scan_multiple: int = 4, after: Optional[tuple] = None,
) -> DrainPage:
    """One page of fillable events inside one tier, after the keyset position."""
    from sqlalchemy import bindparam, text

    if not sport_ids:
        return DrainPage([], after, True, 0)

    after_ts, after_id = (after or (None, None))
    scan = max(1, limit * max(1, scan_multiple))
    # `expanding=True` renders a literal IN list at execution time, so the REAL
    # statement is the one the guards can run — live/035 lost a day to a phantom
    # required bind that no stubbed-session test could see.
    statement = text(THIRTY_DAY_CANDIDATES_SQL).bindparams(
        bindparam("sport_ids", expanding=True)
    )
    rows = (
        await session.execute(
            statement,
            {
                "thin_points": THIRTY_DAY_THIN_POINTS,
                "window_days": THIRTY_DAY_WINDOW_DAYS,
                "sport_ids": list(sport_ids),
                "after_ts": after_ts,
                "after_id": after_id,
                "scan": scan,
            },
        )
    ).fetchall()

    fillable: list[int] = []
    cursor: Optional[tuple] = None
    judged = 0
    for row in rows:
        # Advance over every row JUDGED, not only the ones picked — a thick chart
        # the cursor did not pass would be re-counted on every re-trigger.
        judged += 1
        if row.commence_time is not None:
            cursor = (row.commence_time, int(row.event_id))
        if int(row.point_count or 0) < THIRTY_DAY_THIN_POINTS:
            fillable.append(int(row.event_id))
        if len(fillable) >= limit:
            break

    # 🔴 EXHAUSTED MEANS THE LOOP RAN OUT OF ROWS, NOT THE QUERY.
    # `len(rows) < scan` alone says only that the SQL had nothing more to give
    # — it says nothing about whether this Python loop actually LOOKED at what
    # it was given. The loop stops early the moment `limit` fillable events are
    # collected, so with 250 thin rows and limit=200 the scan (800) came back
    # short, `len(rows) < scan` was True, the tier was marked permanently done,
    # and the 50 rows past the break were never judged and never will be. Both
    # halves are required: the query ran out AND we consumed everything it
    # returned.
    consumed_every_row = judged >= len(rows)
    exhausted = consumed_every_row and len(rows) < scan
    return DrainPage(fillable, cursor, exhausted, judged)


# ---------------------------------------------------------------------------
# Checkpoint — a hint in Redis, never a fact in a column
# ---------------------------------------------------------------------------


class TierState(NamedTuple):
    """What Redis remembers about one tier between triggers."""

    cursor: Optional[tuple]
    #: `None`, :data:`DONE_CLEAN` or :data:`DONE_WITH_FAILURES`.
    done: Optional[str]
    #: `event_id -> attempts already spent` for events that FAILED and are owed
    #: a retry. The tier cannot be marked done while this is non-empty.
    retry: dict
    #: How many events this tier has already given up on.
    gave_up: int


def _read_checkpoint(tier: str) -> TierState:
    """The tier's remembered position, done-marker, retry hash and give-up count.

    Every failure mode — no Redis, evicted key, half-written value — answers
    "start this tier from the top", which wastes a scan and never writes a wrong
    row. Routed through `get_redis_client()` so a socket with no timeout cannot
    freeze the worker's event loop (gotcha #39).
    """
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        done_raw = client.get(TIER_DONE_KEY.format(tier=tier))
        gave_up_raw = client.get(GAVE_UP_KEY.format(tier=tier))
        retry_raw = client.hgetall(RETRY_KEY.format(tier=tier))
        raw = client.get(CHECKPOINT_KEY.format(tier=tier))
    except Exception:  # noqa: BLE001 — a hint that cannot be read is no hint
        return TierState(None, None, {}, 0)

    done = _decode(done_raw)
    if done:
        # An older marker wrote a bare "1". Read it as the clean verdict it meant
        # at the time; nothing has to be migrated for the new one to work.
        done = DONE_WITH_FAILURES if done == DONE_WITH_FAILURES else DONE_CLEAN
    else:
        done = None
    try:
        gave_up = int(_decode(gave_up_raw) or 0)
    except (TypeError, ValueError):
        gave_up = 0

    retry: dict = {}
    for key, value in (retry_raw or {}).items():
        try:
            retry[int(_decode(key))] = int(_decode(value) or 0)
        except (TypeError, ValueError):
            continue  # a half-written entry is no entry

    cursor: Optional[tuple] = None
    text_cursor = _decode(raw)
    if text_cursor:
        stamp, _, event_id = text_cursor.partition("|")
        try:
            parsed = datetime.fromisoformat(stamp)
            # Half a keyset is not a position — refuse it rather than key on the
            # timestamp alone and step over a tied cohort.
            parsed_id = int(event_id)
        except (TypeError, ValueError):
            parsed = None  # type: ignore[assignment]
            parsed_id = 0
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            cursor = (parsed, parsed_id)
    return TierState(cursor, done, retry, gave_up)


def _decode(raw) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    return str(raw) or None


def _write_cursor(tier: str, cursor: Optional[tuple]) -> None:
    """Persist the position this tier reached. Nothing else."""
    if cursor is None:
        return
    stamp, event_id = cursor
    _with_redis(
        tier,
        lambda client: client.set(
            CHECKPOINT_KEY.format(tier=tier), f"{stamp.isoformat()}|{int(event_id)}"
        ),
    )


def _mark_done(tier: str, marker: str) -> None:
    """Mark the tier terminal. `drained` and `drained_with_failures` are BOTH
    terminal and are deliberately distinguishable — the second one means the
    retry budget ran out with events still unreachable, and a reader of the
    verdict has to be able to tell that from a clean finish (gotcha #53)."""
    _with_redis(tier, lambda client: client.set(TIER_DONE_KEY.format(tier=tier), marker))


class AttemptOutcome(NamedTuple):
    """What one pass did to the tier's retry state.

    Both fields are the POST-attempt values. `_settle_tier` turns on them, and
    handing it either one from before the pass is the CERT-764 defect: the
    third failure empties `owed` and increments the give-up counter in the same
    breath, so a settlement reading the entering count sees "no retries owed,
    nobody given up" and writes a permanent clean `drained` over a tier that
    just abandoned an event.
    """

    #: `event_id -> attempts spent`, after this pass.
    owed: dict
    #: The tier's TOTAL give-up count after this pass — the persisted value
    #: `INCRBY` returned, so it is what a later trigger will read back.
    gave_up_total: int


def _record_attempts(
    tier: str, attempted: Sequence[int], failed: Sequence[int], prior: dict,
    prior_gave_up: int = 0,
) -> AttemptOutcome:
    """Fold one pass's outcomes into the tier's retry hash and give-up count.

    🔴 THE RETRY ITSELF. An event that FAILED goes in (or has its attempt count
    bumped); an event that was attempted and did NOT fail comes out, because it
    has been answered. An event that has spent :data:`MAX_EVENT_RETRIES` comes
    out too and is counted as given up — that count, not the empty hash, is what
    makes the tier's ending `drained_with_failures` rather than `drained`.

    That count is RETURNED, not just written. It is written to Redis and read
    back at the top of the NEXT trigger, which is one trigger too late for the
    settlement that happens seconds later in this one.
    """
    failed_set = set(failed)
    still_owed: dict = dict(prior)
    gave_up: list[int] = []

    for event_id in attempted:
        if event_id not in failed_set:
            still_owed.pop(event_id, None)
            continue
        attempts = still_owed.get(event_id, 0) + 1
        if attempts >= MAX_EVENT_RETRIES:
            still_owed.pop(event_id, None)
            gave_up.append(event_id)
        else:
            still_owed[event_id] = attempts

    if gave_up:
        logger.warning(
            "30d chart drain: giving up on %d event(s) in tier %s after %d "
            "attempts each — they stay thin and are counted, not hidden: %s",
            len(gave_up), tier, MAX_EVENT_RETRIES, gave_up[:10],
        )

    # The arithmetic answer, used when Redis cannot be reached or answers with
    # something unreadable. Never fewer than the events this pass abandoned:
    # under-reporting here is the exact shape of the defect, so the fallback
    # errs toward `drained_with_failures`.
    computed_total = int(prior_gave_up) + len(gave_up)
    persisted: list = []

    def _apply(client):
        key = RETRY_KEY.format(tier=tier)
        dropped = [e for e in prior if e not in still_owed]
        if dropped:
            client.hdel(key, *[str(e) for e in dropped])
        added = {
            str(e): str(n) for e, n in still_owed.items() if prior.get(e) != n
        }
        if added:
            client.hset(key, mapping=added)
        if gave_up:
            # INCRBY returns the value it just stored, so the settlement below
            # turns on the same number the next trigger will read back.
            persisted.append(
                client.incrby(GAVE_UP_KEY.format(tier=tier), len(gave_up))
            )

    _with_redis(tier, _apply)

    gave_up_total = computed_total
    if persisted:
        try:
            gave_up_total = max(computed_total, int(persisted[0]))
        except (TypeError, ValueError):
            gave_up_total = computed_total
    return AttemptOutcome(still_owed, gave_up_total)


def _with_redis(tier: str, apply) -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        apply(get_redis_client())
    except Exception:  # noqa: BLE001 — losing the hint costs a re-scan, not a row
        logger.warning(
            "30d chart drain: checkpoint for tier %s not persisted", tier,
            exc_info=True,
        )


def reset_checkpoints() -> dict:
    """Forget every tier's position, done-marker, retries and give-ups. By hand."""
    cleared = []
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        for tier in TIERS:
            client.delete(CHECKPOINT_KEY.format(tier=tier.name))
            client.delete(TIER_DONE_KEY.format(tier=tier.name))
            client.delete(RETRY_KEY.format(tier=tier.name))
            client.delete(GAVE_UP_KEY.format(tier=tier.name))
            cleared.append(tier.name)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:160], "cleared": cleared}
    return {"status": "reset", "cleared": cleared}


# ---------------------------------------------------------------------------
# The drain
# ---------------------------------------------------------------------------


class DrainPass(NamedTuple):
    """The outcome of one batch of events."""

    #: Why the loop ended: ``page_complete`` or ``consecutive_errors``.
    stopped: str
    #: Ids we actually reached (an id whose row is gone is not attempted).
    attempted: list[int]
    #: Of those, the ones that FAILED — never asked and answered. These are the
    #: ids the tier owes a retry, and the reason it cannot be marked done.
    failed: list[int]
    #: Ids whose event row no longer exists. Reported SEPARATELY because they are
    #: neither attempted nor failed, and an owed retry for one of them would sit
    #: in the retry hash forever holding its tier at `awaiting_retries` — the
    #: false-`drained` defect wearing its opposite face.
    missing: list[int]


async def _drain_events(
    session, event_ids: Sequence[int], *,
    kalshi_service, polymarket_service,
    min_period_minutes: Optional[int], dry_run: bool, summary: dict,
) -> DrainPass:
    """Fill each event, committing per event. Reports what it reached and failed.

    Per-event commit, not one transaction over the page: a network drain that
    dies on item 40 must keep the 39 curves it already drew (gotcha #13's shape).
    One bad event never costs its siblings (gotcha #42) — the per-source guard is
    inside `backfill_event_chart`, and this adds the per-EVENT one around it.
    """
    from sqlalchemy import select

    from app.models.models import Event
    from app.tasks.event_chart_backfill import backfill_event_chart

    consecutive_errors = 0
    attempted: list[int] = []
    failed: list[int] = []
    missing: list[int] = []
    for event_id in event_ids:
        event = (
            await session.execute(select(Event).where(Event.id == event_id))
        ).scalar_one_or_none()
        if event is None:
            summary["not_found"] += 1
            missing.append(event_id)
            continue
        attempted.append(event_id)
        try:
            verdict = await backfill_event_chart(
                session, event,
                kalshi_service=kalshi_service,
                polymarket_service=polymarket_service,
                dry_run=dry_run,
                min_period_minutes=min_period_minutes,
            )
        except Exception as exc:  # noqa: BLE001 — one event, not the drain
            consecutive_errors += 1
            # An event that threw was never asked and answered. It counts as
            # FAILED, which is what keeps the tier from being marked done over it.
            summary["failed"] += 1
            failed.append(event_id)
            summary["errors"].append(f"{event_id}: {str(exc)[:120]}")
            logger.warning("30d chart drain: event %s failed", event_id, exc_info=True)
            if consecutive_errors >= CONSECUTIVE_ERROR_ABORT:
                return DrainPass(
                    "consecutive_errors", attempted, failed, missing,
                )
            continue

        consecutive_errors = 0
        summary["events_processed"] += 1
        summary["points_written"] += verdict["points_written"]
        if verdict["points_written"]:
            summary["events_written"] += 1
        if _tally(summary, verdict):
            failed.append(event_id)
        if verdict["errors"]:
            summary["errors"].extend(verdict["errors"][:2])

        if not dry_run:
            await session.commit()
        if INTER_EVENT_SLEEP_SECONDS:
            await asyncio.sleep(INTER_EVENT_SLEEP_SECONDS)
    return DrainPass("page_complete", attempted, failed, missing)


def _tally(summary: dict, verdict: dict) -> bool:
    """Fold one event's verdict into the census. Returns whether it FAILED.

    This is the half of the report Alex asked for by name — "events still empty
    and WHY". A drain that reports only its successes cannot tell a resolver gap
    from a purged venue from a market we cannot orient, and those three want
    three different owners.

    🔴 THREE OUTCOMES, NOT TWO. Every event lands in exactly one of `filled`,
    `empty_with_no_history` and `failed`, and the third is the one that used to
    be missing: an event whose venue refused us was counted alongside an event
    the venue genuinely holds nothing for, under a single `still_empty`. They are
    not the same event. The first must be retried; the second is done. Only
    `failed` keeps a tier from being marked drained.

    The return value is that third bucket, handed back so the caller can owe the
    event a retry by id rather than re-walking the whole tier to find it again.
    """
    if verdict.get("status") == "no_linked_markets":
        summary["reasons"]["no_linked_markets"] += 1
        return False
    filled_any = False
    failed_any = False
    for source, stats in verdict.get("sources", {}).items():
        status = stats.get("status")
        if status == "written":
            filled_any = True
            summary["by_source"][source] = summary["by_source"].get(source, 0) + (
                stats.get("points_written") or 0
            )
            continue
        if status in FAILED_SOURCE_STATUSES:
            failed_any = True
        if status:
            summary["reasons"][f"{source}:{status}"] += 1
        for signal in ("purged", "api_empty", "no_token_id", "fetch_errors",
                       "window_errors"):
            if stats.get(signal):
                summary["reasons"][f"{source}:{signal}"] += stats[signal]
    if filled_any:
        summary["filled"] += 1
    if failed_any:
        # An event whose OTHER source filled is still not done: the failed half
        # of its chart is missing and is worth another attempt.
        summary["failed"] += 1
    elif not filled_any:
        summary["empty_with_no_history"] += 1
    if not filled_any:
        # Kept for continuity with the pre-repair report. It is now strictly the
        # sum of the two honest buckets and is never the number a decision reads.
        summary["still_empty"] += 1
    return failed_any


def _new_summary() -> dict:
    import collections

    return {
        "events_processed": 0,
        "events_written": 0,
        "points_written": 0,
        # The three honest outcomes. `filled` + `empty_with_no_history` + `failed`
        # is what "drained" has to be judged against; `still_empty` is the old
        # combined number, kept only so an existing reader does not break.
        "filled": 0,
        "empty_with_no_history": 0,
        "failed": 0,
        "still_empty": 0,
        "not_found": 0,
        "by_source": {},
        "reasons": collections.Counter(),
        "errors": [],
        "tiers": {},
    }


async def run_thirty_day_chart_drain(
    *,
    limit: int = 200,
    dry_run: bool = False,
    min_period_minutes: Optional[int] = None,
    only_tier: Optional[str] = None,
) -> dict:
    """Drain up to ``limit`` fillable events, highest-priority tier first.

    Resumable and idempotent. Re-trigger until the verdict is TERMINAL, and
    there are exactly two terminal verdicts:

      ``drained``                 every event in scope was asked and answered.
      ``drained_with_failures``   it stopped, having given up on events the
                                  venue would not serve after
                                  ``MAX_EVENT_RETRIES`` attempts each. Terminal,
                                  and deliberately not the same word.

    Anything else — ``in_progress``, or a tier at ``awaiting_retries``, or a
    clean-looking page that wrote zero points — means there is more behind it
    (gotcha #53 / `task_verdict`: "it returned" is not "it worked").
    """
    from app.services.kalshi_api import KalshiAPIService
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.base import get_task_session

    summary = _new_summary()
    summary["window_days"] = THIRTY_DAY_WINDOW_DAYS
    summary["thin_below_points"] = THIRTY_DAY_THIN_POINTS
    summary["dry_run"] = dry_run

    remaining = max(1, limit)
    kalshi_service = KalshiAPIService()
    polymarket_service = PolymarketAPIService()
    stopped = None
    try:
        async with get_task_session() as session:
            buckets = await tier_sport_ids(session)
            for tier in TIERS:
                if only_tier and tier.name != only_tier:
                    continue
                if remaining <= 0:
                    break
                stopped = None
                state = _read_checkpoint(tier.name)
                if state.done:
                    summary["tiers"][tier.name] = {
                        "status": state.done, "already_done": True,
                        "gave_up": state.gave_up,
                    }
                    continue

                tier_report = {
                    "why": tier.why,
                    "sports": len(buckets[tier.name]),
                    "resumed_from": _label(state.cursor),
                    # The count ENTERING this trigger. `owed_retries` below is
                    # the count LEAVING it, and they are different numbers the
                    # moment a retry succeeds.
                    "retries_owed_on_entry": len(state.retry),
                    "gave_up": state.gave_up,
                }

                # 🔴 RETRIES FIRST, before any new ground. These are events a
                # previous trigger could not reach at all; the point of holding
                # their ids is that the retry costs a handful of re-fetches
                # instead of a re-walk of the tier.
                owed = state.retry
                # The give-up total this tier will SETTLE on. It starts at what
                # Redis remembers and is replaced by the post-attempt total
                # every time a pass records attempts — never read back from
                # `state`, which is a snapshot taken before any of that.
                gave_up_total = state.gave_up
                retried = sorted(owed)[:remaining]
                if retried:
                    result = await _drain_events(
                        session, retried,
                        kalshi_service=kalshi_service,
                        polymarket_service=polymarket_service,
                        min_period_minutes=min_period_minutes,
                        dry_run=dry_run, summary=summary,
                    )
                    remaining -= len(retried)
                    tier_report["retried"] = len(retried)
                    tier_report["retried_still_failing"] = len(result.failed)
                    if not dry_run:
                        outcome = _record_attempts(
                            tier.name,
                            result.attempted + result.missing,
                            result.failed,
                            owed,
                            gave_up_total,
                        )
                        owed, gave_up_total = outcome.owed, outcome.gave_up_total
                    stopped = result.stopped
                    if stopped == "consecutive_errors":
                        summary["tiers"][tier.name] = dict(
                            tier_report, status="in_progress",
                        )
                        summary["aborted"] = "consecutive_errors"
                        break

                if remaining > 0:
                    page = await select_thirty_day_page(
                        session, sport_ids=buckets[tier.name],
                        limit=remaining, after=state.cursor,
                    )
                else:
                    # The retries ate the budget. New ground was not looked at,
                    # so this tier is emphatically NOT exhausted.
                    page = DrainPage([], state.cursor, False, 0)
                tier_report["scanned"] = page.scanned
                tier_report["fillable"] = len(page.event_ids)

                if page.event_ids:
                    result = await _drain_events(
                        session, page.event_ids,
                        kalshi_service=kalshi_service,
                        polymarket_service=polymarket_service,
                        min_period_minutes=min_period_minutes,
                        dry_run=dry_run, summary=summary,
                    )
                    remaining -= len(page.event_ids)
                    tier_report["failed"] = len(result.failed)
                    if not dry_run:
                        outcome = _record_attempts(
                            tier.name,
                            result.attempted + result.missing,
                            result.failed,
                            owed,
                            gave_up_total,
                        )
                        owed, gave_up_total = outcome.owed, outcome.gave_up_total
                    stopped = result.stopped
                tier_report["advanced_to"] = _label(page.next_cursor)
                tier_report["exhausted"] = page.exhausted
                settled = _settle_tier(
                    tier.name, page, tier_report,
                    owed=owed, gave_up=gave_up_total, dry_run=dry_run,
                )
                # The verdict this trigger PERSISTED, carried on the report
                # rather than re-derived. `_verdict` and the next trigger's
                # `_read_checkpoint` must agree with it, and the only way to be
                # sure they do is for all three to come from one decision.
                if settled is not None:
                    tier_report["persisted_done_marker"] = settled
                summary["tiers"][tier.name] = tier_report
                if stopped == "consecutive_errors":
                    summary["aborted"] = "consecutive_errors"
                    break
    finally:
        for service in (kalshi_service, polymarket_service):
            try:
                await service.close()
            except Exception:  # noqa: BLE001 — closing must never mask the run
                pass

    summary["reasons"] = dict(summary["reasons"])
    summary["errors"] = summary["errors"][:20]
    summary["status"] = _verdict(summary, only_tier=only_tier)
    if summary["status"] == DONE_WITH_FAILURES:
        logger.warning(
            "30d chart drain: STOPPED with failures — %s filled, %s genuinely "
            "empty, %s FAILED. The failed events are still thin and were not "
            "reachable inside the retry budget; they need a named owner, not a "
            "re-trigger.",
            summary["filled"], summary["empty_with_no_history"], summary["failed"],
        )
    elif summary["status"] != DONE_CLEAN:
        logger.info(
            "30d chart drain: %s events, %s points, %s filled, %s empty, %s "
            "FAILED — RE-TRIGGER, the window is not drained yet",
            summary["events_processed"], summary["points_written"],
            summary["filled"], summary["empty_with_no_history"], summary["failed"],
        )
    return summary


def _settle_tier(
    tier: str, page: DrainPage, tier_report: dict, *,
    owed: dict, gave_up: int, dry_run: bool,
) -> Optional[str]:
    """Decide, and persist, what this tier's page means for the tier.

    Returns the terminal marker it persisted, or `None` if the tier is not
    terminal — so the caller holds the same verdict that went to Redis instead
    of inferring it a second way.

    🔴 THE RULE THE CERT BLOCKED ON: reaching the end of the scan is not the same
    as finishing. A tier is marked done ONLY when its scan ran out AND it owes no
    retries — `owed` is the per-event retry hash, and an event lands in it
    precisely when the venue could not be asked. Marking done regardless is what
    let a permanent checkpoint step past events that had merely been refused,
    with the verdict reading `drained` and the pages staying blank.

    Bounded by :data:`MAX_EVENT_RETRIES` inside :func:`_record_attempts`, so an
    event that can never be fetched drains out of `owed` rather than holding the
    tier open forever — and increments the give-up count, which is what makes the
    ending `drained_with_failures` instead of `drained`.

    🔴 CERT-764, AND IT IS THE SAME MISTAKE ONE LAYER DOWN. `gave_up` must be the
    count LEAVING the trigger. The third failure is the one that both empties
    `owed` and increments the counter, so a settlement handed the ENTERING count
    sees "no retries owed, nobody given up" on precisely the pass that abandoned
    an event, and writes a permanent clean `drained` over it. The caller now
    threads `_record_attempts`' returned post-attempt total here; nothing in this
    function may read the counter back from Redis, because the retry hash and
    the counter are only consistent as a pair at the moment the pass produced
    them.
    """
    # Both counts LEAVING this trigger. `gave_up` is stamped unconditionally —
    # reporting it only when non-zero is what let a stale zero look like an
    # answer rather than an absence.
    tier_report["owed_retries"] = len(owed)
    tier_report["gave_up"] = gave_up

    if not page.exhausted:
        # The cursor is written even when the page filled nothing: those
        # candidates WERE judged, and not advancing past them is how a drain
        # re-reads the same head forever. Advancing past a FAILED event is safe
        # here only because its id is held in `owed`.
        tier_report["status"] = "in_progress"
        if not dry_run:
            _write_cursor(tier, page.next_cursor)
        return None

    if owed:
        tier_report["status"] = "awaiting_retries"
        logger.info(
            "30d chart drain: tier %s reached the end of its scan but owes %d "
            "retry/retries — NOT marking it drained; re-trigger to retry them",
            tier, len(owed),
        )
        if not dry_run:
            _write_cursor(tier, page.next_cursor)
        return None

    marker = DONE_WITH_FAILURES if gave_up else DONE_CLEAN
    tier_report["status"] = marker
    if gave_up:
        logger.warning(
            "30d chart drain: tier %s ends as %s — %d event(s) could not be "
            "fetched in %d attempts each and remain thin.",
            tier, DONE_WITH_FAILURES, gave_up, MAX_EVENT_RETRIES,
        )
    if not dry_run:
        _write_cursor(tier, page.next_cursor)
        _mark_done(tier, marker)
    return marker


#: Tier statuses that mean the tier has STOPPED. `awaiting_retries` and
#: `in_progress` are not here, by design — both mean re-trigger.
TERMINAL_TIER_STATUSES = frozenset({DONE_CLEAN, DONE_WITH_FAILURES})


def _verdict(summary: dict, *, only_tier: Optional[str]) -> str:
    """`drained` ONLY when every tier in scope finished CLEANLY.

    A page that returned cleanly having written nothing looks exactly like a
    finished drain unless something asserts the difference, so this asserts it.
    And a tier that ran out of RETRY budget with events still unreachable is
    terminal but is NOT `drained` — it reports `drained_with_failures` so the
    difference reaches whoever reads the verdict (gotcha #53).
    """
    if summary.get("aborted"):
        return "aborted"
    scope = [t.name for t in TIERS if not only_tier or t.name == only_tier]
    seen = summary.get("tiers", {})
    statuses = [seen.get(name, {}).get("status") for name in scope]
    # A legacy marker: pre-repair runs recorded a finished tier as
    # `already_drained`, and a summary carrying one still means the clean thing.
    statuses = [DONE_CLEAN if s == "already_drained" else s for s in statuses]
    if not all(s in TERMINAL_TIER_STATUSES for s in statuses):
        return "in_progress"
    if any(s == DONE_WITH_FAILURES for s in statuses):
        return DONE_WITH_FAILURES
    return DONE_CLEAN


def _label(cursor: Optional[tuple]) -> Optional[str]:
    """A keyset position, readable in a verdict. Both halves or neither."""
    if not cursor:
        return None
    stamp, event_id = cursor
    return f"{stamp.isoformat()}|{event_id}"
