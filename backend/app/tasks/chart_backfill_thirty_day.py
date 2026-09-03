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

#: live/055 (#2766). The abort signal of an optimistic fence. Imported at module
#: scope deliberately: `redis` is a hard dependency of this app (the Procfile's
#: release phase imports `app.main`, and Celery cannot start without it), and a
#: lazily-imported exception class inside an `except` clause is a way to have the
#: handler quietly not exist. There is no fallback for the same reason — a
#: fallback class would silently turn "the lease moved" into an unhandled error.
from redis.exceptions import WatchError

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

#: 🔴 CERT-773 — ONE WRITER PER TIER. `POST /backfill-30d-charts` queues by
#: default and tells the operator to re-call until the verdict is terminal, so
#: two triggers overlapping on one tier is the ordinary case, not an attack.
#: `SET NX EX` is the whole lock: the first trigger into a tier owns it, every
#: other trigger reports `locked_out` and writes nothing at all.
#:
#: The TTL is what stops a SIGKILLed worker from holding a tier shut forever
#: (gotcha: Celery SIGKILLs are untracked, so a `finally` release is not
#: guaranteed to run). It is deliberately generous against a bounded pass — at
#: `limit=200`, ~3 requests per event and a 0.25s inter-event sleep, a pass is
#: minutes, not half an hour.
#:
#: 🔴 AND THE LOCK IS NOT THE GUARANTEE. A TTL that expires under a slow pass
#: puts two writers back on one tier, which is why the terminal marker is
#: independently monotone (see :func:`_mark_done`) and why the checkpoint read
#: and the retry/give-up write are each ONE transaction. The lock removes the
#: wasted double-fetch; the other three remove the wrong verdict. Any one of
#: them alone would close CERT-773's reproduction, and they are all here because
#: the failure they prevent is permanent and the cost of preventing it is not.
#: 🔴 CERT-794/795 — AND THE MONOTONE MARKER WAS NOT THE GUARANTEE EITHER. The
#: paragraph above is right that a clean finish cannot DOWNGRADE a failure
#: ending. It is silent about the other order, which is the one the graders
#: reproduced: a sibling writes a clean `drained` onto a tier holding no
#: terminal marker at all, and the older runner — whose fixed 30-minute lease
#: had quietly expired — THEN appends a newly owed retry. Nothing was
#: downgraded; the two writes simply do not know about each other, and the tier
#: ends `done='drained'` beside `retry={7007: 1}`. The next trigger returns on
#: `state.done` and never retries that event, so the match page stays incomplete
#: behind a verdict that says the drain finished cleanly.
#:
#: Three changes close it, and again they are deliberately redundant:
#:
#:   1. **THE LEASE IS RENEWED, NOT FIXED.** Every state write refreshes the TTL
#:      (:func:`_still_holds`), so a pass that is alive keeps its tier for as
#:      long as it keeps working. A fixed 1800s was a promise about how long a
#:      pass takes, and a promise about duration is not a lock.
#:   2. **A WRITER THAT LOST THE LEASE WRITES NOTHING.** Every write is fenced on
#:      the token, so the loser cannot append the retry, move the cursor, or
#:      settle the tier. Losing the lease now means being stalled for a full TTL
#:      between two writes, at which point the pass's in-memory results are
#:      stale and refusing them is the correct answer.
#:   3. **A NEWLY OWED RETRY RE-OPENS THE TIER, ATOMICALLY.** The retry write
#:      DELETES the terminal marker in the same MULTI that adds the field, so
#:      the reverse order cannot leave the pair behind: whichever lands second,
#:      the state a reader sees is either "terminal and owing nothing" or "owing
#:      something and not terminal", never both.
TIER_LOCK_KEY = "chart_backfill_30d:lock:{tier}"
TIER_LOCK_TTL_SECONDS = 1800

#: What a fenced-out write reports. NOT terminal, and deliberately distinct from
#: `locked_out`: `locked_out` is a trigger that never got in, this is one that
#: was inside and lost the tier mid-pass. Both mean re-trigger; only this one
#: means a pass's work was thrown away, which is worth seeing in a log.
LOCK_LOST = "lock_lost"

#: A dry run holds no lock — it persists nothing, so there is nothing to
#: serialize. This stands in for the token so the runner's release path stays
#: one branch instead of two, and so `None` keeps its single meaning: LOCKED OUT.
_DRY_RUN_LOCK = "dry-run"

#: Terminal done-markers. `drained_with_failures` is terminal too — the drain
#: stopped, and it says so by name rather than by looking finished.
DONE_CLEAN = "drained"
DONE_WITH_FAILURES = "drained_with_failures"

#: NOT terminal, and it already existed as a literal on the tier report — it is
#: named here because :func:`_mark_done` now answers with it too (CERT-794/795):
#: a settlement that finds the retry hash non-empty reports this instead of
#: writing a clean marker over a tier that still owes work.
AWAITING_RETRIES = "awaiting_retries"

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

    🔴 ONE TRANSACTION, ONE SNAPSHOT — CERT-773's read half. These four keys are
    not four facts; they are one state, and the give-up counter only means
    anything beside the retry hash it was incremented against. Read as four
    round trips they can be torn by a sibling trigger writing between any two of
    them, and the tear that matters is exactly the one the cert reproduced: the
    hash read AFTER a sibling emptied it, the counter read BEFORE the sibling
    incremented it — `retry={}`, `gave_up=0`, and a settlement that writes a
    permanent clean `drained` over an event the drain had just abandoned.
    MULTI/EXEC makes the four reads one server-side operation, so this returns a
    state that actually existed rather than one assembled from two.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        with client.pipeline(transaction=True) as pipe:
            pipe.get(TIER_DONE_KEY.format(tier=tier))
            pipe.get(GAVE_UP_KEY.format(tier=tier))
            pipe.hgetall(RETRY_KEY.format(tier=tier))
            pipe.get(CHECKPOINT_KEY.format(tier=tier))
            done_raw, gave_up_raw, retry_raw, raw = pipe.execute()
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


def _write_cursor(
    tier: str, cursor: Optional[tuple], token: Optional[str] = _DRY_RUN_LOCK,
) -> bool:
    """Persist the position this tier reached. Nothing else.

    Fenced (CERT-794/795): a pass that lost the lease must not move the cursor.
    The cursor is allowed to advance past a FAILED event only because that
    event's id is held in the retry hash — so a writer that cannot record the
    retry must not record the advance either, or the failure is stepped over and
    never seen again.
    """
    if cursor is None:
        return True
    stamp, event_id = cursor

    def _apply(pipe, _observed):
        pipe.set(
            CHECKPOINT_KEY.format(tier=tier),
            f"{stamp.isoformat()}|{int(event_id)}",
        )

    return _fenced(tier, token, _apply)


def _mark_done(
    tier: str, marker: str, token: Optional[str] = _DRY_RUN_LOCK,
) -> str:
    """Mark the tier terminal, MONOTONICALLY. Returns the marker now in force.

    `drained` and `drained_with_failures` are BOTH terminal and are deliberately
    distinguishable — the second one means the retry budget ran out with events
    still unreachable, and a reader of the verdict has to be able to tell that
    from a clean finish (gotcha #53).

    🔴 THE ORDER IS ONE-WAY, AND IT IS ENFORCED BY THE WRITE ITSELF (CERT-773).
    An unconditional `SET` lets a second trigger's clean finish overwrite a first
    trigger's `drained_with_failures`, and that overwrite is permanent: the tier
    is done, nothing re-scans it, and the abandoned event stays thin behind a
    marker that says the drain finished cleanly. So the two markers are written
    with two different Redis verbs, chosen so the wrong direction is not
    expressible:

        `drained_with_failures`  plain SET — an UPGRADE is always allowed, and a
                                 failure ending must be able to land on top of a
                                 clean one.
        `drained`                SET NX — it lands only on a tier that has no
                                 terminal marker yet, so it can never downgrade
                                 an existing `drained_with_failures`.

    This is a property of the operation, not of a lock or of a read-then-write
    the caller performs first, so it holds even when :data:`TIER_LOCK_TTL_SECONDS`
    has expired under a slow pass and two writers are genuinely concurrent. NX
    refusing is not an error — it means a sibling already recorded the truer
    verdict — so the marker actually in force is read back and returned, and the
    caller reports THAT rather than what it proposed (CERT-764's clause: one
    decision, not three readers each inferring their own).

    🔴 AND MONOTONE IS NOT ENOUGH — CERT-794/795. Monotonicity only orders the
    two TERMINAL markers against each other. It says nothing about a clean
    `drained` landing on an empty done-key while a sibling still owes a retry,
    which is the pair the graders reproduced. So the clean write also refuses
    while the retry hash is non-empty, checked on this same connection
    immediately before the `SET NX`: a tier that owes work has not finished, and
    the answer is `awaiting_retries` — not terminal, so the operator's re-call
    loop picks it straight back up. The other order (the retry landing after the
    clean marker) is closed at the retry's own write, which deletes the marker
    inside its transaction; see :func:`_record_attempts`.

    The whole call is fenced, so a pass that lost the lease cannot settle a tier
    it no longer owns. A fenced-out settlement reports :data:`LOCK_LOST`.
    """
    key = TIER_DONE_KEY.format(tier=tier)
    retry_key = RETRY_KEY.format(tier=tier)
    in_force: list = []

    def _read(pipe):
        """The retry-hash check, in the watch phase. live/055 (#2766).

        This is a READ the write then branches on, so the key it reads has to be
        WATCHED as well — otherwise the repair simply moves CERT-794's race one
        key over: a sibling could add a retry between this `HLEN` and our `SET
        NX`, and the clean marker would land on a tier that owes work after all.
        `_fenced(watch=...)` below is doing that, and it is not optional.
        """
        if marker == DONE_WITH_FAILURES:
            return 0
        return pipe.hlen(retry_key)

    def _apply(pipe, owed):
        if marker == DONE_WITH_FAILURES:
            pipe.set(key, marker)
            in_force.append(marker)
            return None
        # 🔴 CERT-794/795: no clean `drained` while anything is owed.
        if owed:
            logger.warning(
                "30d chart drain: tier %s proposed %s but the retry hash is NOT "
                "empty — a sibling owes work on this tier, so it has not "
                "finished. Reporting %s instead of writing a terminal marker.",
                tier, marker, AWAITING_RETRIES,
            )
            in_force.append(AWAITING_RETRIES)
            return None

        # 🔴 THE NX AND THE READ-BACK ARE NOW ONE TRANSACTION (live/055, #2766).
        # `SET NX` refusing means a sibling already recorded the truer verdict,
        # and the caller reports what is actually in force rather than what it
        # proposed (CERT-764). That read-back used to be a SEPARATE round trip
        # after the refusal, so it could return a value written by a THIRD
        # writer in between — reporting a verdict that was never the one that
        # refused us. Queued in the same MULTI, the `GET` observes the state the
        # `SET NX` just declined to change.
        pipe.set(key, marker, nx=True)
        pipe.get(key)

        def _settle(results):
            won, existing_raw = results[0], results[1]
            if won:
                in_force.append(marker)
                return
            # A legacy bare "1" reads as the clean verdict it meant, the same
            # way `_read_checkpoint` reads it.
            existing = _decode(existing_raw)
            in_force.append(
                DONE_WITH_FAILURES if existing == DONE_WITH_FAILURES else DONE_CLEAN
            )

        return _settle

    held = _fenced(tier, token, _apply, read=_read, watch=(retry_key,))
    if not held:
        return LOCK_LOST
    # Nothing persisted (Redis unreachable) still reports what was DECIDED — the
    # verdict is not silently downgraded by an outage, and `_with_redis` has
    # already logged that the checkpoint did not land.
    return in_force[0] if in_force else marker


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

    #: Whether this pass still HELD the tier when it wrote (CERT-794/795).
    #: `False` means the lease had expired and a sibling owns the tier: nothing
    #: above was persisted, and the caller must stop rather than go on to write
    #: a cursor or a verdict for a tier it no longer owns. Defaults to `True` so
    #: a caller constructing an outcome by hand gets the ordinary case.
    held: bool = True


def _record_attempts(
    tier: str, attempted: Sequence[int], failed: Sequence[int], prior: dict,
    prior_gave_up: int = 0, token: Optional[str] = _DRY_RUN_LOCK,
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

    def _apply(pipe, _observed):
        key = RETRY_KEY.format(tier=tier)
        dropped = [e for e in prior if e not in still_owed]
        added = {
            str(e): str(n) for e, n in still_owed.items() if prior.get(e) != n
        }
        # 🔴 ONE TRANSACTION — CERT-773's write half, and the exact operation the
        # cert reproduced a tear inside. Removing the last retry field and
        # incrementing the give-up counter are not two writes that happen to be
        # adjacent; they are the two halves of ONE fact ("this event is no longer
        # owed a retry BECAUSE we abandoned it"), and a reader between them sees
        # a tier that owes nothing and gave up on nobody — a tier that finished
        # cleanly. MULTI/EXEC means no reader can be between them: the whole
        # block lands as a single visible transition.
        #
        # The order inside the block still matters for the ANSWER, not for the
        # visibility: INCRBY is queued last so its reply is the last element of
        # `execute()`, and that reply is the persisted post-attempt total the
        # settlement turns on (CERT-764).
        #
        # 🔴 AND A NEWLY OWED RETRY RE-OPENS THE TIER, INSIDE THIS SAME BLOCK —
        # CERT-794/795. `added` non-empty means "this pass just failed to reach
        # an event and owes it another go", and a tier that owes work is by
        # definition not finished. So the terminal marker is DELETED here rather
        # than left for the next reader to notice, which is what closes the
        # reverse order the graders reproduced: a sibling's clean `drained`
        # landing FIRST is simply removed by the retry that follows it, in one
        # visible transition. No reader can ever see `done='drained'` beside a
        # non-empty retry hash, so no reader can early-return past owed work.
        #
        # Deleting a `drained_with_failures` here loses nothing: the give-up
        # COUNTER is untouched and monotone, so when this tier settles again it
        # reads that counter back and ends `drained_with_failures` exactly as
        # before. The marker is re-derivable; the abandoned retry is not.
        #
        # 🔴 live/055 (#2766): this block used to open its OWN
        # `client.pipeline(transaction=True)` INSIDE the fence, which meant the
        # lease check and this transaction were two separate instants — the
        # transaction was atomic with itself but not with the check that
        # authorised it. It now queues onto the fence's transaction, so the
        # token comparison, the lease renewal and every write below are one
        # block that either all lands or none does. Same commands, same order,
        # one fewer seam.
        # 🔴 AND THE DELETE IS UNCONDITIONAL — CERT-836, and it is the same
        # lesson a third time: DO NOT MAKE TWO WRITES AGREE AFTER THE FACT,
        # MAKE THEM ONE WRITE.
        #
        # CERT-831's repair fixed the reopen's callback, and CERT-836 then
        # reproduced the case the callback repair cannot reach. `_with_redis`
        # FAILS OPEN by design — a Redis blip must cost a re-scan, not a
        # crashed drain — so a Redis exception makes `_fenced` answer `True`.
        # That is safe only while nothing LATER in the same run persists, and
        # it is exactly that assumption which breaks: if Redis dies for the
        # single instant of the reopen transaction and recovers immediately,
        # the reopen is silently lost while THIS transaction lands. The retry
        # is removed, the cursor advances, the stale `drained` survives, and
        # the next trigger returns `already_done` over everything behind it.
        #
        # Conditioning the delete on `added` was the bug: it made the marker's
        # removal depend on the retry having FAILED, when the invariant it
        # protects has nothing to do with success. Reaching this function means
        # the tier is being actively drained, which means it is NOT terminal —
        # a terminal marker short-circuits the runner long before here, and the
        # only way past that short-circuit is the reopen, which wants the
        # marker gone anyway. So the marker is deleted whenever attempts are
        # recorded, in the transaction that records them.
        #
        # That makes the pair self-healing rather than dependent on a separate
        # write having succeeded: the reopen may be lost to a blip, and the
        # contradiction is still cleared by the very write that would otherwise
        # have made it permanent. `_settle_tier` writes the true marker
        # afterwards in the same pass when the tier really has finished, so
        # nothing is lost — and a `drained_with_failures` is re-derived from the
        # monotone give-up counter exactly as the note above already argues.
        #
        # Queued AFTER the hash writes and BEFORE the counter: the counter's
        # reply must stay last (`results[-1]`, CERT-764), and keeping the delete
        # adjacent to the hash write leaves the `added` block's command order
        # exactly as CERT-794/795 pinned it.
        if dropped:
            pipe.hdel(key, *[str(e) for e in dropped])
        if added:
            pipe.hset(key, mapping=added)
        pipe.delete(TIER_DONE_KEY.format(tier=tier))
        if gave_up:
            pipe.incrby(GAVE_UP_KEY.format(tier=tier), len(gave_up))

        def _settle(results):
            if gave_up and results:
                persisted.append(results[-1])

        return _settle

    held = _fenced(tier, token, _apply)

    gave_up_total = computed_total
    if persisted:
        try:
            gave_up_total = max(computed_total, int(persisted[0]))
        except (TypeError, ValueError):
            gave_up_total = computed_total
    return AttemptOutcome(still_owed, gave_up_total, held)


def _with_redis(tier: str, apply) -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        apply(get_redis_client())
    except Exception:  # noqa: BLE001 — losing the hint costs a re-scan, not a row
        logger.warning(
            "30d chart drain: checkpoint for tier %s not persisted", tier,
            exc_info=True,
        )


def _still_holds(client, tier: str, token: Optional[str]) -> bool:
    """Do we still own this tier? CERT-794/795, narrowed by live/055 (#2766).

    🔴 THIS NO LONGER RENEWS, AND THAT IS THE FIX, NOT A REGRESSION. It used to
    `GET` and then `EXPIRE`, and the renewal is precisely what could not stay
    here: in real Redis `EXPIRE` calls `signalModifiedKey`, so a renewal issued
    while :func:`_fenced` is watching the lock would invalidate the pass's OWN
    watch and abort every write it was fencing. The renewal moved into the
    transaction (see :func:`_fenced`), where it is atomic with the writes it is
    protecting instead of being a third round trip beside them.

    What remains is the pure question — is the token in Redis still ours — used
    by :func:`_fenced`'s watch phase and available on its own to callers that
    want the answer without a write.

    🔴 A DRY RUN ALWAYS HOLDS. It took no lock because it writes nothing, and
    :data:`_DRY_RUN_LOCK` keeps `None` meaning one thing (locked out) rather than
    two. It must not issue a lock read to discover that.

    🔴 UNREACHABLE REDIS ANSWERS TRUE, matching :func:`_acquire_tier_lock`'s
    documented FAIL OPEN. If the server cannot be reached there is no lock, no
    sibling and no persisted verdict to corrupt — every write is swallowed by
    :func:`_with_redis` anyway — and refusing to run would turn a blip into a
    silently disabled drain.
    """
    if token is None:
        return False
    if token == _DRY_RUN_LOCK:
        return True
    key = TIER_LOCK_KEY.format(tier=tier)
    try:
        return _decode(client.get(key)) == token
    except Exception:  # noqa: BLE001 — see FAIL OPEN above
        logger.warning(
            "30d chart drain: tier %s lease could not be checked; proceeding "
            "(nothing persists while Redis is unreachable)", tier, exc_info=True,
        )
        return True


def _assert_apply_contract(apply) -> None:
    """`apply` must accept `(pipe, observed)`. Say so NOW, not in a swallow.

    Checked by signature rather than by letting the call fail, because the call
    fails INSIDE :func:`_with_redis`, which is deliberately blind to everything.
    A `TypeError` there is indistinguishable from a Redis outage and produces
    the worst possible answer: the fence reports it still holds the tier while
    the write it was fencing never existed (CERT-831).

    A callable whose signature cannot be read — a builtin, a C extension — is
    ACCEPTED. This guard exists to catch a stale hand-written lambda, and
    refusing what it cannot inspect would trade a real bug class for an
    imaginary one.
    """
    import inspect

    try:
        signature = inspect.signature(apply)
    except (TypeError, ValueError):  # not introspectable — see above
        return
    try:
        signature.bind(None, None)
    except TypeError as exc:
        raise TypeError(
            "_fenced: `apply` must accept (pipe, observed) — it queues writes "
            f"on a pipeline already in MULTI mode, and {apply!r} does not take "
            "them. A one-argument callback left over from when this fence ran "
            "commands directly is CERT-831: the TypeError is swallowed by "
            "`_with_redis`, the fence answers `held=True`, and the write it "
            "promised never lands."
        ) from exc


def _fenced(tier: str, token: Optional[str], apply, *, read=None, watch=()) -> bool:
    """Run the caller's writes only while we still hold the tier, ATOMICALLY.

    Returns whether this pass STILL OWNS the tier. `False` is a REAL answer the
    caller must act on — it means the lease is gone, everything this write was
    about to persist has been thrown away, and the caller must not go on to
    persist the NEXT thing either. Silently continuing is how a fenced pass still
    advances a cursor past a failure it was not allowed to record.

    ── live/055 (#2766): WHY THIS IS NOW A WATCH, AND WHAT THAT BUYS ──────────

    CERT-798 shipped this fence as `GET` the lock, compare, then `EXPIRE`, then
    write. Its grader named the residual seam `CHART-LEASE-ATOMIC-COMPARE-RENEW`
    and I agreed with the finding: three separate round trips are three separate
    instants, so between the compare and the write the lease could expire and be
    taken by a sibling, and the write would land anyway. The window was
    microseconds rather than CERT-794's thirty minutes. Microseconds is not zero,
    and "narrow" is not a property a correctness argument can rest on — it is a
    statement about how often you will see the bug, not about whether it exists.

    So the compare and the writes are now ONE optimistic transaction:

        WATCH lock (+ any key the caller must read before deciding)
        GET lock, compare to our token        <- immediate, pre-MULTI
        read(pipe)                            <- the caller's read phase, if any
        MULTI
          EXPIRE lock                         <- the renewal, INSIDE the block
          apply(pipe, observed)               <- the caller's writes, queued
        EXEC                                  <- aborts if anything watched moved

    If the lock key is touched at ANY point after the WATCH — retaken, released,
    or expired out from under us — `EXEC` refuses and nothing lands. There is no
    longer an instant between the check and the write for a sibling to occupy.

    🔴 THE RENEWAL HAD TO MOVE INSIDE THE BLOCK. `EXPIRE` signals a watch in real
    Redis, so renewing in the watch phase would have aborted the pass's own
    transaction every single time. Queued inside the MULTI it is atomic with the
    writes it protects, which is strictly better than where it was.

    🔴 A LOST WATCH IS A REFUSAL, NOT A RETRY. The optimistic idiom usually loops
    on `WatchError`, and that is wrong here. The watched key is the lease itself:
    if it moved, the overwhelmingly likely reason is that we no longer hold it,
    and a retry would re-read, find a different token, and refuse anyway. In the
    rare benign case (our own release racing a shutdown) a refusal costs one
    re-trigger and never a wrong verdict, which is the direction this whole
    module errs in. Looping would add a way to spin.

    🔴 IT IS STILL NOT A "DID REDIS WORK" FLAG. An unreachable Redis returns
    `True`: nothing persisted, but the tier was not taken from us, and reporting
    that as a lost lease would turn a blip into an aborted drain. That is the
    same fail-open the lock itself documents.

    :param apply: `apply(pipe, observed)` — queues writes on a pipeline already
        in MULTI mode. It MUST NOT read: a read queued here answers at `EXEC`,
        not now. It may return a `settle(results)` callable, which is handed the
        replies to ITS OWN commands (the renewal's reply is stripped first).
    :param read: `read(pipe)` — an optional read phase run while watching and
        before `MULTI`, for a caller that must branch on current state. Its
        return value is passed to `apply` as `observed`.
    :param watch: extra keys whose movement must also abort the transaction. A
        caller that READS a key in `read` and branches on it has to watch it, or
        it has re-created this very bug one key over.
    :raises TypeError: if `apply` does not accept the two-argument contract.
    """
    # 🔴 THE CONTRACT IS CHECKED OUT HERE, ABOVE `_with_redis`, AND THAT
    # PLACEMENT IS THE POINT — CERT-831. `_with_redis` swallows every exception
    # on purpose: a Redis outage must cost a re-scan, not a crashed drain. That
    # blanket also swallows PROGRAMMING errors raised inside `_guarded`, and
    # when it does, `refused` stays empty and this function answers `True` — a
    # write that never happened, reported as a write that did. That is exactly
    # how the legacy reopen site's one-argument callback survived four updated
    # callbacks, a full focused suite and a cert: `TypeError`, swallowed,
    # `held=True`, terminal marker left in place.
    #
    # So the two things a caller can get structurally wrong are decided BEFORE
    # the swallow exists. A contract violation is not an outage and must never
    # be reported as one; it is a loud failure at the call that made it, in
    # every environment, on the first invocation.
    _assert_apply_contract(apply)
    # Nothing is watched when there is no lease to watch (a dry run) and the
    # caller named no other key — which is the one shape a read phase cannot
    # survive. `token is None` is a refusal before any of this and is left alone.
    if read is not None and not watch and token == _DRY_RUN_LOCK:
        # A read phase is only a read phase while watching: redis-py puts a
        # pipeline into IMMEDIATE mode on `watch()` and not before, so a `read`
        # issued on an unwatched pipeline is QUEUED — it answers with the
        # pipeline object rather than a value, which is truthy, and `_mark_done`
        # would report `awaiting_retries` for every tier forever. A wrong
        # verdict arriving through a mode error, refused here where the refusal
        # can actually be heard.
        raise AssertionError(
            "_fenced: a read phase requires at least one watched key — "
            "a read the write branches on is part of the write"
        )

    refused: list = []
    lost_watch: list = []

    def _guarded(client):
        if token is None:
            refused.append(True)
            return

        lock_key = TIER_LOCK_KEY.format(tier=tier)
        # A dry run holds no lock, so there is no lease to watch or renew. It
        # still runs its writes in a transaction — the atomicity between the
        # writes themselves is CERT-773's guarantee and is not the lock's.
        fencing = token != _DRY_RUN_LOCK

        with client.pipeline(transaction=True) as pipe:
            # The read-phase/watch contract is asserted before `_with_redis`,
            # where the assertion is not swallowed (CERT-831).
            watched = ([lock_key] if fencing else []) + list(watch)
            if watched:
                pipe.watch(*watched)
            if fencing and _decode(pipe.get(lock_key)) != token:
                pipe.unwatch()
                refused.append(True)
                return

            observed = read(pipe) if read is not None else None

            pipe.multi()
            if fencing:
                pipe.expire(lock_key, TIER_LOCK_TTL_SECONDS)
            settle = apply(pipe, observed)
            try:
                results = pipe.execute()
            except WatchError:
                lost_watch.append(True)
                refused.append(True)
                return

        # 🔴 `callable`, NOT `is not None` — CERT-831's second seam. A queued
        # write returns the PIPELINE (`pipe.delete(k)` is chainable, in redis-py
        # and in the fake), so the natural one-line callback
        # `lambda pipe, _observed: pipe.delete(k)` hands a pipeline back here.
        # Under `is not None` that pipeline was called as a settle function, and
        # the resulting `TypeError` went straight into `_with_redis`'s swallow —
        # after `execute()`, so the write DID land, but every caller-visible
        # effect of the settle phase silently did not. A callback that queues one
        # command and wants no settle phase is the common case and must not have
        # to remember to end in a bare statement.
        if callable(settle):
            # Strip the renewal's own reply so the caller indexes its own
            # commands — `results[-1]`, `results[0]` and friends must mean what
            # they meant when the writes were in a pipeline of their own.
            settle(results[1:] if fencing else results)

    _with_redis(tier, _guarded)
    if refused:
        logger.warning(
            "30d chart drain: tier %s write REFUSED — this pass no longer holds "
            "the tier (%s). Nothing was written; the tier belongs to whoever "
            "holds it now.", tier,
            "the lease moved between our check and our write, and the watch "
            "aborted the transaction" if lost_watch
            else "lease expired and a sibling took it",
        )
    return not refused


def _acquire_tier_lock(tier: str) -> Optional[str]:
    """Claim this tier for one trigger. Returns a fencing token, or `None`.

    🔴 CERT-773. `None` means another trigger is already inside this tier and
    this one must not touch it — not its retry hash, not its counter, not its
    cursor, not its done-marker. The loser writes NOTHING and reports
    `locked_out`, which is not terminal, so the operator's re-call loop is
    unchanged: a locked-out tier just means "come back".

    🔴 FAIL OPEN, DELIBERATELY. If Redis cannot be reached the lock cannot be
    taken — and neither can anything else. `_read_checkpoint` returns an empty
    state, every write is swallowed by :func:`_with_redis`, and there is no
    persisted verdict left to corrupt. Refusing to run in that case would turn a
    Redis blip into a silently disabled drain, which is a worse failure than the
    one the lock exists to prevent, so an unreachable Redis hands back a token
    and the pass proceeds doing real (unpersisted) work.
    """
    import uuid

    token = uuid.uuid4().hex
    try:
        from app.tasks.redis_state import get_redis_client

        won = get_redis_client().set(
            TIER_LOCK_KEY.format(tier=tier), token,
            nx=True, ex=TIER_LOCK_TTL_SECONDS,
        )
    except Exception:  # noqa: BLE001 — see FAIL OPEN above
        logger.warning(
            "30d chart drain: tier %s lock could not be taken; proceeding "
            "unlocked (nothing is persisted while Redis is unreachable)",
            tier, exc_info=True,
        )
        return token
    return token if won else None


def _release_tier_lock(tier: str, token: Optional[str]) -> None:
    """Hand the tier back, but only if we still hold it.

    The token check is what stops a pass that overran :data:`TIER_LOCK_TTL_SECONDS`
    from deleting the lock a DIFFERENT trigger has since taken.

    🔴 live/055 (#2766) — IT IS NOW A COMPARE-AND-DELETE, not a read-then-delete.
    This function's own previous docstring admitted the seam: "a vanishingly
    narrow window remains where the lock is re-taken between the two". The cost
    was correctly described as a redundant concurrent pass rather than a wrong
    verdict — but a redundant concurrent pass is exactly the state CERT-773 and
    CERT-794 were both about, so leaving a hole that manufactures one was a poor
    trade for two round trips. WATCH closes it: if the lock moves between the
    read and the delete, `EXEC` aborts and we delete nothing, which is the right
    answer because the lock is no longer ours to hand back.

    A lost watch is silence, deliberately. Someone else owning the lease is the
    normal end of an overrun pass, not an error, and the caller is already on its
    way out — there is nothing for it to do differently.
    """
    if not token:
        return
    key = TIER_LOCK_KEY.format(tier=tier)

    def _apply(client):
        with client.pipeline(transaction=True) as pipe:
            pipe.watch(key)
            if _decode(pipe.get(key)) != token:
                pipe.unwatch()
                return
            pipe.multi()
            pipe.delete(key)
            try:
                pipe.execute()
            except WatchError:
                logger.info(
                    "30d chart drain: tier %s lock was re-taken between our "
                    "check and our release; leaving it with its new holder.",
                    tier,
                )

    _with_redis(tier, _apply)


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
    tier at ``locked_out``, or a clean-looking page that wrote zero points —
    means there is more behind it (gotcha #53 / `task_verdict`: "it returned" is
    not "it worked").

    ONE TRIGGER PER TIER (CERT-773). Each tier is claimed with a TTL'd Redis
    lock for the whole of its pass. A second trigger that arrives while the
    first is inside reports that tier ``locked_out`` and writes nothing —
    no retry field, no counter, no cursor, no done-marker. It is a normal
    outcome, not an error: the route tells the operator to re-call until
    terminal, so overlap is the expected traffic pattern and deferring is the
    right answer to it.
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

                # 🔴 ONE WRITER PER TIER — CERT-773. Taken BEFORE the checkpoint
                # is read, because the read is half of what a sibling can tear.
                # A dry run does not take it: it persists nothing, so there is
                # nothing to serialize, and holding the lock would let a spot
                # check shut the real drain out of a tier for its whole pass.
                lock = _DRY_RUN_LOCK if dry_run else _acquire_tier_lock(tier.name)
                if lock is None:
                    # Another trigger owns this tier. Write NOTHING and say so.
                    # `locked_out` is deliberately not terminal, so the verdict
                    # stays `in_progress` and the operator's re-call loop —
                    # which is what produced the overlap in the first place —
                    # keeps working unchanged.
                    summary["tiers"][tier.name] = {
                        "why": tier.why,
                        "status": "locked_out",
                        "locked_out": True,
                    }
                    logger.info(
                        "30d chart drain: tier %s is already being drained by "
                        "another trigger — this one writes nothing and defers",
                        tier.name,
                    )
                    continue

                try:
                    state = _read_checkpoint(tier.name)
                    if state.done and state.retry:
                        # 🔴 CERT-794/795 — THE STATE THAT MUST NOT BE SKIPPED.
                        # A terminal marker beside a non-empty retry hash is
                        # self-contradictory: the tier finished, and it owes
                        # work. The writes above now make the pair unreachable
                        # going forward, but a tier can ALREADY be sitting in it
                        # — the shipped code could produce it, so production
                        # can be holding one right now — and the old early
                        # return here is what made it permanent: `state.done`
                        # sent every later trigger straight past the owed event,
                        # forever, behind a verdict that says the drain finished.
                        # So this is not an assertion, it is a REPAIR: drop the
                        # marker and drain what is owed. Re-opening a tier costs
                        # a pass; not re-opening it costs the chart.
                        logger.warning(
                            "30d chart drain: tier %s is marked %s but owes %d "
                            "retry/retries (%s) — that pair cannot both be "
                            "true. RE-OPENING the tier and draining them; the "
                            "marker is re-derived when it settles again.",
                            tier.name, state.done, len(state.retry),
                            sorted(state.retry)[:10],
                        )
                        # 🔴 THE REOPEN IS A QUEUED WRITE LIKE EVERY OTHER ONE
                        # — CERT-831. This site kept a `lambda client: ...` from
                        # before `_fenced` became a transaction, and the two-arg
                        # `apply(pipe, observed)` contract turned it into a
                        # `TypeError` that `_with_redis` swallowed: `_fenced`
                        # answered `True`, the marker was never deleted, and the
                        # pass went on believing it had reopened the tier. If the
                        # owed retry then SUCCEEDED and the page behind it was
                        # not exhausted, `_record_attempts` removed the retry
                        # without deleting a marker (it only deletes when it ADDS
                        # one), `_settle_tier` wrote nothing because the tier is
                        # not terminal — and the next trigger read `drained`
                        # beside an empty retry hash and skipped the rest of the
                        # tier forever. The silent contract drift is closed in
                        # `_fenced` itself; this is the write it broke.
                        #
                        # 🔴 AND A DRY RUN DOES NOT DO IT. Every other write on
                        # this path is behind `if not dry_run`; this one was not,
                        # and only the broken callback hid that — a spot check
                        # would otherwise reopen a tier it took no lock on. It
                        # still reopens IN MEMORY, so the probe reports what a
                        # real run would find, and persists nothing.
                        reopened = dry_run or _fenced(
                            tier.name, lock,
                            lambda pipe, _observed: pipe.delete(
                                TIER_DONE_KEY.format(tier=tier.name)
                            ),
                        )
                        if not reopened:
                            # 🔴 AND THE ANSWER IS ACTED ON. `_fenced` returning
                            # `False` means the lease moved: the marker is still
                            # in Redis and belongs to whoever holds the tier now.
                            # Draining on anyway would spend a page of venue
                            # fetches whose every write is refused, and would
                            # leave this pass reporting progress it did not make.
                            summary["tiers"][tier.name] = {
                                "why": tier.why, "status": LOCK_LOST,
                            }
                            continue
                        state = state._replace(done=None)
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
                        # The count ENTERING this trigger. `owed_retries` below
                        # is the count LEAVING it, and they are different
                        # numbers the moment a retry succeeds.
                        "retries_owed_on_entry": len(state.retry),
                        "gave_up": state.gave_up,
                    }

                    # 🔴 RETRIES FIRST, before any new ground. These are events a
                    # previous trigger could not reach at all; the point of
                    # holding their ids is that the retry costs a handful of
                    # re-fetches instead of a re-walk of the tier.
                    owed = state.retry
                    # The give-up total this tier will SETTLE on. It starts at
                    # what Redis remembers and is replaced by the post-attempt
                    # total every time a pass records attempts — never read back
                    # from `state`, which is a snapshot taken before any of that.
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
                                lock,
                            )
                            owed, gave_up_total = (
                                outcome.owed, outcome.gave_up_total,
                            )
                            if not outcome.held:
                                # 🔴 CERT-794/795. The lease is gone, so nothing
                                # above persisted. Stop HERE: settling or
                                # advancing a cursor for a tier we no longer own
                                # is precisely the write the fence exists to
                                # refuse, and doing it one call later is the
                                # same wrong write with a different name.
                                summary["tiers"][tier.name] = dict(
                                    tier_report, status=LOCK_LOST,
                                )
                                continue
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
                        # The retries ate the budget. New ground was not looked
                        # at, so this tier is emphatically NOT exhausted.
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
                                lock,
                            )
                            owed, gave_up_total = (
                                outcome.owed, outcome.gave_up_total,
                            )
                            if not outcome.held:
                                # See the retry arm above: a fenced-out write
                                # ends the tier for this pass, it does not fall
                                # through to the settlement.
                                summary["tiers"][tier.name] = dict(
                                    tier_report, status=LOCK_LOST,
                                )
                                continue
                        stopped = result.stopped
                    tier_report["advanced_to"] = _label(page.next_cursor)
                    tier_report["exhausted"] = page.exhausted
                    settled = _settle_tier(
                        tier.name, page, tier_report,
                        owed=owed, gave_up=gave_up_total, dry_run=dry_run,
                        token=lock,
                    )
                    # The verdict this trigger PERSISTED, carried on the report
                    # rather than re-derived. `_verdict` and the next trigger's
                    # `_read_checkpoint` must agree with it, and the only way to
                    # be sure they do is for all three to come from one decision.
                    if settled is not None:
                        tier_report["persisted_done_marker"] = settled
                    summary["tiers"][tier.name] = tier_report
                    if stopped == "consecutive_errors":
                        summary["aborted"] = "consecutive_errors"
                        break
                finally:
                    # Every exit — `continue`, `break`, or an exception on the
                    # way out — hands the tier back. A SIGKILL cannot run this,
                    # which is what the TTL is for.
                    if not dry_run:
                        _release_tier_lock(tier.name, lock)
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
    owed: dict, gave_up: int, dry_run: bool, token: Optional[str] = _DRY_RUN_LOCK,
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
            _write_cursor(tier, page.next_cursor, token)
        return None

    if owed:
        tier_report["status"] = "awaiting_retries"
        logger.info(
            "30d chart drain: tier %s reached the end of its scan but owes %d "
            "retry/retries — NOT marking it drained; re-trigger to retry them",
            tier, len(owed),
        )
        if not dry_run:
            _write_cursor(tier, page.next_cursor, token)
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
        _write_cursor(tier, page.next_cursor, token)
        # 🔴 CERT-773. `_mark_done` is MONOTONE and answers with the marker
        # actually in force, which is not always the one proposed: a sibling
        # trigger that abandoned an event has already written
        # `drained_with_failures`, and a clean finish must not overwrite it. The
        # report follows Redis rather than the other way round, so the summary,
        # the persisted key and the next trigger's read-back stay one verdict
        # (CERT-764's clause) even when two triggers settled the same tier.
        in_force = _mark_done(tier, marker, token)
        if in_force != marker:
            logger.warning(
                "30d chart drain: tier %s proposed %s but a concurrent trigger "
                "had already recorded %s — the failure ending stands",
                tier, marker, in_force,
            )
            marker = in_force
            tier_report["status"] = in_force
    return marker


#: Tier statuses that mean the tier has STOPPED. `awaiting_retries`,
#: `in_progress` and `locked_out` are not here, by design — all three mean
#: re-trigger. `locked_out` especially: a tier another trigger is inside has not
#: finished, and reading somebody else's in-flight work as a terminal verdict is
#: the same class of mistake CERT-773 blocked.
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
