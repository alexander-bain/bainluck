"""Kalshi WebSocket consumer task.

Long-running process that streams live prices and settlement events from
Kalshi's WebSocket API. Replaces the 2-minute REST polling for linked markets
with sub-second latency updates.

Channels:
  - ticker: price updates → batch-write FuturesOutcome.current_probability
  - market_lifecycle_v2: settlement → mark FuturesMarket as resolved
"""

import asyncio
import contextlib
import functools
import logging
import os
import time
from collections.abc import Collection, Iterator, Mapping
from datetime import datetime, timezone

from app.utils.kalshi_market_status import is_terminal
from app.tasks.ws_consumer_sessions import owns_consumer_sessions  # #2471
from app.utils.market_quote_push import queue_market_change
from app.utils.market_settlement import settled_values
from app.utils.repair_lock_budget import (
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)

logger = logging.getLogger(__name__)


#: Q460 / #10090 — reread the full eligible subscription scope every ten
#: minutes. An unchanged scope keeps its healthy sockets and buffered inputs;
#: changed mappings/policy still use the existing drain/rebuild path.
SUBSCRIPTION_REFRESH_SECONDS = int(
    os.getenv("WS_SUBSCRIPTION_REFRESH_SECONDS", "600")
)

#: Q491 — the interval between flush STARTS (#10090: start to start, so a
#: flush's own work is not added to it; `run_flush_cadence`). Both sockets share
#: it, as they share the recycle timer above, so the two cannot drift to
#: different write cadences on the same dyno. Named rather than inlined because
#: it is also the RETRY interval: a flush that fails re-queues its batch, and
#: this is how long after the failure the price waits for the next attempt.
PRICE_FLUSH_SECONDS = float(os.getenv("WS_PRICE_FLUSH_SECONDS", "2"))

# #10737: leave one of the task engine's existing 3+2 slots outside this
# grade class. Other consumer operations can still contend for that slot.
OPEN_CONTRACT_GRADE_CONCURRENCY = 4

# Q491 repair (CERT-654 BLOCK). The periodic flush can afford to requeue a failed
# batch because another flush is `PRICE_FLUSH_SECONDS` away. **The final flush has
# no successor** — after it the consumer returns and the buffer is garbage — so
# requeueing there discarded the batch exactly as the pre-Q491 code did, and the
# recycle path runs it every `SUBSCRIPTION_REFRESH_SECONDS`, not just at shutdown.
# The last drain therefore RETRIES instead of requeueing.
#
# No sleep between attempts, deliberately: this runs inside a `finally` that is
# also reached via `CancelledError`, and awaiting a sleep during cancellation
# raises immediately and would abandon the drain. Each attempt opens a FRESH
# session (and so a fresh connection), which is what a connection-level transient
# actually needs in order to clear.
FINAL_FLUSH_ATTEMPTS = int(os.getenv("WS_FINAL_FLUSH_ATTEMPTS", "3"))

#: #10661 — how long one periodic flush phase may WAIT for any single row lock.
#: A sibling writer holding a game's rows used to stall every later game in the
#: flush; past this the phase rolls back with SQLSTATE 55P03, keeps its prices
#: buffered for the next flush, and the independent phases after it proceed.
#: Transaction-local (`SET_LOCK_TIMEOUT_SQL`), so a pooled connection never
#: carries it. It bounds each lock acquisition, not the phase or pool checkout.
#: The final drain does NOT use it: `FINAL_FLUSH_ATTEMPTS` back-to-back attempts
#: would otherwise give up on a lock held ~1.5 s and drop the last prices.
PRICE_PHASE_LOCK_TIMEOUT_MS = 500

#: #10090 — how long one periodic flush may keep STARTING phases that hold no
#: live game. Production 2026-10-08 00:25–00:35Z (run b47fefde): a flush on the
#: 2 s cadence took 1.5–3.3 min, because it wrote every game that ticked since
#: the last one — ~55 s of per-game phases across ~976 subscribed events — and
#: then one ~1,300-row futures/props transaction, so a live game's moving price
#: waited minutes for its turn. Live games are now planned first and always
#: written (`linked_first_phases`); past this budget the remaining phases stay
#: buffered, at the front, for the next flush. Never applied to the final drain.
FLUSH_BUDGET_SECONDS = 2 * PRICE_FLUSH_SECONDS

#: #10090 — opt-in Kalshi cadence, the #10662 Polymarket shape. Unset, the
#: consumer keeps the shared 2 s timer and the refresher's 2 s per-event floor,
#: which together cap a held game at one Kalshi stamp per 2 s (production
#: 2026-10-08 17:05–17:12Z: 20–28 flushes a minute, most ~1 s of work then idle
#: until the next 2 s start). Set, it is the timer and the blend floor. The
#: failed-write retry keeps `PRICE_FLUSH_SECONDS` and the non-live budget keeps
#: `FLUSH_BUDGET_SECONDS`: the budget counts live-phase time too, so halving it
#: would starve non-live phases whenever live work takes 2-4 s.
KALSHI_FLUSH_PERIOD_ENV = "KALSHI_WS_PRICE_FLUSH_SECONDS"


def kalshi_flush_cadence():
    """``(period, blend_floor, failed_retry, budget)`` for one consumer run.

    ``failed_retry`` is ``None`` without the override, so the unset path calls
    the cadence exactly as before; ``budget`` is always ``None`` (the module
    `FLUSH_BUDGET_SECONDS`, read at call time). Raises
    ValueError for anything but a positive finite number.
    """
    import math

    from app.tasks.live_blend_refresh import DEFAULT_MIN_REFRESH_INTERVAL_S

    override = os.getenv(KALSHI_FLUSH_PERIOD_ENV)
    if override is None:
        return PRICE_FLUSH_SECONDS, DEFAULT_MIN_REFRESH_INTERVAL_S, None, None
    try:
        period = float(override)
    except ValueError as invalid:
        raise ValueError(
            f"{KALSHI_FLUSH_PERIOD_ENV} must be a positive finite number"
        ) from invalid
    if not math.isfinite(period) or period <= 0:
        raise ValueError(f"{KALSHI_FLUSH_PERIOD_ENV} must be a positive finite number")
    return period, period, PRICE_FLUSH_SECONDS, None

#: #10090 — the most rows one non-live phase packs. Pre-game games are packed
#: whole, several per transaction, and futures/props whole MARKETS at a time, so
#: the budget can stop between phases instead of behind one unbounded one. A
#: single game or market larger than this is still one phase, never cut.
NONLIVE_PHASE_MAX_ROWS = 200

#: #10090 — the most games one non-live phase packs. The phase's blend refresh
#: stamps each of its games, so its cost grows per game, and the longest phase
#: a flush starts before its budget runs out is what the next flush's live games
#: wait behind. Production's ~0.5 s per game phase puts eight at a few seconds.
NONLIVE_PHASE_MAX_GAMES = 8


def flush_budget_spent(
    flush_started, phase, event_id_by_outcome, live_events, budget_seconds=None,
):
    """#10090 — True when a periodic flush should leave ``phase`` buffered.

    Never for a phase holding a live game's outcome, never without a start
    (the final drain, a direct call) and never without a live set (the
    pre-#10090 plan). Read on the refresher's clock, which `flush_started` is.
    ``budget_seconds`` is the run's (`kalshi_flush_cadence`); ``None`` reads
    `FLUSH_BUDGET_SECONDS` at call time.
    """
    if flush_started is None or live_events is None:
        return False
    if any(event_id_by_outcome.get(oid) in live_events for oid in phase):
        return False
    from app.tasks.live_blend_refresh import _mono

    budget = FLUSH_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    return _mono() - flush_started >= budget


def kalshi_non_speaking_ticker(external_id: str | None) -> bool:
    """Suppress blend triggers only for a known series rejected by admission.

    Classify the MARKET ticker, just like LiveBlendRefresher._read_groups.
    Missing/empty/unknown series retain refresh rather than guess at new rules.
    """
    from app.utils.prediction_market_matching import feeds_win_prob_blend
    from app.utils.sport_keys import (
        KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
        KALSHI_TICKER_TO_SPORT_KEY,
    )

    if not isinstance(external_id, str) or not external_id:
        return False
    prefix, separator, suffix = external_id.lower().partition("-")
    if not separator or not suffix or feeds_win_prob_blend(external_id):
        return False
    return (
        prefix in KALSHI_TICKER_TO_SPORT_KEY
        or prefix in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
    )


class _KalshiHeadlineEvents(Mapping[int, int]):
    """Live view of existing event admission, omitting known non-speakers.

    Unknown identities retain their full event cohort. Admission may bridge an
    outcome while a flush awaits publication; read the owner maps in place so
    the existing unfinished-event fences see that bridge immediately.
    """

    def __init__(self, events: Mapping[int, int], non_speakers: Collection[int]):
        self.events = events
        self.non_speakers = non_speakers

    def __getitem__(self, outcome_id: int) -> int:
        if outcome_id in self.non_speakers:
            raise KeyError(outcome_id)
        return self.events[outcome_id]

    def __iter__(self) -> Iterator[int]:
        return (oid for oid in self.events if oid not in self.non_speakers)

    def __len__(self) -> int:
        return sum(1 for _ in self)


def live_input_waiting(buffer, batch, event_id_by_outcome, live_events):
    """#10090 — True when ``buffer`` holds input for a live game that
    ``batch`` (this flush's snapshot) does not: a new outcome, or a value that
    changed since the snapshot. An entry still equal to its snapshot (a phase
    this flush has not reached, or one a lock timeout kept) is not new input.
    """
    if not live_events:
        return False
    return any(
        entry != batch.get(oid) and event_id_by_outcome.get(oid) in live_events
        for oid, entry in buffer.items()
    )


def yield_written_nonlive_tail(
    buffer, phase, written_outcome_ids, event_id_by_outcome, live_events,
    final_drain,
):
    """A served nonlive cohort's newer quotes yield to untouched tail work.

    Called under the buffer lock after commit and ordinary removal. Never
    moves live quotes, failed/unwritten rows, or final-drain work. The retained
    entry is still the newest one; only its scheduling position changes.
    """
    if final_drain or not live_events or any(
        event_id_by_outcome.get(oid) in live_events for oid in phase
    ):
        return
    written = set(written_outcome_ids)
    for oid, entry in phase.items():
        if oid in written and oid in buffer and buffer[oid] != entry:
            newest = buffer.pop(oid)
            buffer[oid] = newest


def live_preempts_tail(
    flush_started, period, nonlive_started, buffer, batch, event_id_by_outcome,
    live_events,
):
    """#10090 — True when a periodic flush should stop before a non-live phase
    because a live game has new input waiting (see `flush_prices`).

    Only after ``period`` on the refresher's clock and once at least one
    non-live phase has started (``nonlive_started``), so preemption permits
    nonlive work before yielding. Never without a start (the final drain, a direct
    call) or without a live set.
    """
    if flush_started is None or not live_events or not nonlive_started:
        return False
    from app.tasks.live_blend_refresh import _mono

    if _mono() - flush_started < period:
        return False
    return live_input_waiting(buffer, batch, event_id_by_outcome, live_events)


class _FlushTimings:
    """#10090 — where the Kalshi flush time went, per stats-line minute.

    `save` is the price pipeline (rows written, including their lock waits),
    `publish` the market invalidations, `stamp` the event blend refresh, and
    `rank_commit` the rest of the flush: re-rank, commit, session checkout and
    bookkeeping. One flush's phases are the transactions it opened.

    A flush's bucket time is held IN FLIGHT and joins the minute only with
    that flush's total (`flushed`), so a stats-line reset mid-flush cannot
    split the two and misattribute `rank_commit` (CERT-4016 follow-up).

    Pipelined stamps (#10090): `stamp` overlaps the next phase's write, so the
    buckets can sum past `total` and `rank_commit`, the floored remainder,
    reads low. `total` below `save + publish + stamp` is that overlap.
    """

    BUCKETS = ("save", "publish", "stamp")

    def __init__(self):
        self.in_flight = dict.fromkeys(self.BUCKETS, 0.0)
        self.in_flight_phases = 0
        self.reset()

    def reset(self):
        """Start a new minute. In-flight time stays with its flush."""
        self.flushes = 0
        self.phases = 0
        self.total = 0.0
        self.longest = 0.0
        self.spent = dict.fromkeys(self.BUCKETS, 0.0)

    def add(self, bucket, seconds, *, phase=False):
        self.in_flight[bucket] += seconds
        self.in_flight_phases += int(phase)

    def flushed(self, seconds):
        self.flushes += 1
        self.total += seconds
        self.longest = max(self.longest, seconds)
        self.phases += self.in_flight_phases
        for bucket, spent in self.in_flight.items():
            self.spent[bucket] += spent
        self.in_flight = dict.fromkeys(self.BUCKETS, 0.0)
        self.in_flight_phases = 0

    def timed(self, bucket, method):
        """``method`` (a coroutine function) with its duration added to ``bucket``."""

        @functools.wraps(method)
        async def run(*args, **kwargs):
            started = time.monotonic()
            try:
                return await method(*args, **kwargs)
            finally:
                self.add(bucket, time.monotonic() - started)

        return run

    def line(self):
        rank_commit = max(0.0, self.total - sum(self.spent.values()))
        return (
            f"flush n={self.flushes} total={self.total:.1f}s "
            f"max={self.longest:.1f}s phases={self.phases} "
            f"save={self.spent['save']:.1f}s rank_commit={rank_commit:.1f}s "
            f"publish={self.spent['publish']:.1f}s stamp={self.spent['stamp']:.1f}s"
        )


class _KalshiPriceOwner:
    """#10693 — one consumer run's Kalshi price pipeline, installed lazily.

    The first price phase installs the pipeline on the engine its session is
    bound to (the run's one `ConsumerSessions` engine, #2471) and every later
    phase of the run reuses it; the utility refuses a session from any other
    engine. A run that never writes a price never installs a listener.
    """

    def __init__(self):
        self.pipeline = None
        # Only a successful outer commit pays first-observation admission.
        # Values are always compared in SQL, including after external writers.
        self.committed_outcome_ids: set[int] = set()
        # The existing failed-price delay belongs to the failed whole cohort,
        # not unrelated inputs sharing the consumer's normal flush timer.
        self.lock_retry_until: dict[int, float] = {}
        # #10090: the consumer's `_FlushTimings`, when it keeps one.
        self.timings = None

    async def phase(self, session, phase, *, force_observation=False):
        """Yield `PriceRunResult`s for one phase. Consume in `aclosing`.

        A successful phase is exhausted by its caller. A caller error closes
        this iterator (and the utility's) before the session rolls back.
        """
        from app.utils.kalshi_price_pipeline import install_kalshi_price_pipeline

        started = time.monotonic()
        try:
            if self.pipeline is None:
                self.pipeline = install_kalshi_price_pipeline(session.bind)
            async with contextlib.aclosing(
                self.pipeline.iter_phase(
                    session,
                    {
                        oid: (
                            *values,
                            force_observation or oid not in self.committed_outcome_ids,
                        )
                        for oid, values in phase.items()
                    },
                )
            ) as results:
                async for result in results:
                    yield result
        finally:
            if self.timings is not None:
                self.timings.add("save", time.monotonic() - started, phase=True)

    def close(self):
        if self.pipeline is not None:
            self.pipeline.close()


def _owns_kalshi_price_lifetime(consumer):
    """#10693 — close the run's price listener after the consumer has returned.

    Sits INSIDE `owns_consumer_sessions`: the consumer's whole body — its final
    drain, hand-off and loop reaping — finishes first, then the listener is
    removed, then the outer owner disposes the engine. Reversed, the engine
    would be disposed with the listener still installed on it.
    """

    @functools.wraps(consumer)
    async def run(*args, **kwargs):
        prices = _KalshiPriceOwner()
        try:
            return await consumer(*args, prices=prices, **kwargs)
        finally:
            prices.close()

    return run


def _kalshi_slate_event_window():
    """The events whose Kalshi markets the socket subscribes to.

    Live, scheduled within 6 h, and (#9484) an open market on a recently
    suspended event — see `app.tasks.ws_slate`. A function rather than inline
    so the real-Postgres contract reads the shipped expression.
    """
    from sqlalchemy import and_, or_, text

    from app.models.models import Event
    from app.tasks.ws_slate import suspended_open_market_arm

    return or_(
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time.isnot(None),
            Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
        ),
        suspended_open_market_arm(),
    )


#: #10090 — how long a replacement client must have been connected before its
#: predecessor stops reading. Both carry the shared tickers meanwhile; ticker
#: ownership (`_KalshiClient`) keeps one writer per ticker at every instant.
SUCCESSOR_OVERLAP_SECONDS = 5.0

#: #10090 — how long a retiring client may take to drain callbacks it already
#: accepted before it is cancelled like the old recycle did.
RETIRE_DRAIN_SECONDS = 30.0

#: #10090 — how long a connected client may go without Kalshi acknowledging
#: every channel it subscribed before the next refresh rebuilds the run. A
#: rejected subscription rebuilds at once; either way the socket may be silent.
SUBSCRIBE_ACK_DEADLINE_SECONDS = 30.0


def kalshi_direct_book_enabled() -> bool:
    """#10090 — ``KALSHI_WS_DIRECT_BOOK=1`` streams order books for the live
    winner legs (`KalshiWebSocket.set_book_tickers`). Off by default; unset or
    ``0`` is the undo, back to ticker summaries alone."""
    return os.getenv("KALSHI_WS_DIRECT_BOOK", "0").strip() == "1"


def kalshi_book_max_tickers() -> int:
    """#10090 — the bound on order books streamed at once. A live tennis
    match alone sent ~60 book deltas a second (Zverev–Wu, 10/09), so the
    population is the LIVE events' winner legs, capped here."""
    try:
        return max(0, int(os.getenv("KALSHI_WS_BOOK_MAX_TICKERS", "200")))
    except ValueError:
        return 200

#: #10090 — open-contract connections a changed scope may hold beyond the
#: packed minimum before the run takes the full rebuild instead.
OPEN_CONTRACT_EXTRA_CONNECTIONS = 2


class _KalshiClient:
    """#10090 — one Kalshi connection and the exact tickers it subscribed.

    ``predecessor`` is the client a make-before-break replacement takes over
    from; until it retires the two are each other's ``pair`` and share
    ``lifecycle_seen`` and ``pair_lock``, so a settlement both deliver is
    handled once and sibling settlements never run concurrently.
    """

    __slots__ = (
        "sock", "task", "tickers", "kind", "predecessor", "pair", "lifecycle_seen",
        "pair_lock",
    )

    def __init__(self, sock, tickers, kind):
        self.sock = sock
        self.task = None
        self.tickers = frozenset(tickers)
        self.kind = kind
        self.predecessor = None
        self.pair = None
        self.lifecycle_seen = None
        # Serializes the pair's settlement writes, as one socket's dispatch did.
        self.pair_lock = None


def plan_stable_shards(current, scope, per_connection=None, extra=0, busy=()):
    """#10090 — keep, replace, start or retire clients for a changed scope.

    ``current`` lists each steady client's subscribed tickers. A client whose
    tickers left scope keeps its connection while any of them remain (their
    frames are no longer mapped) and is retired once none do. New tickers go
    to ONE replacement — the client with the most room, which also sheds its
    dead tickers — and any overflow to new connections, so a removal never
    re-deals every shard. ``per_connection=None`` is the single game client.
    ``busy`` clients are mid-handoff and are never replaced or retired.

    Returns ``(keep, replace, start, retire)`` — indexes, ``{index: tickers}``,
    new ticker sets, indexes — or None when the result would exceed the packed
    minimum by more than ``extra`` connections (the caller rebuilds instead).
    """
    import math

    scope = frozenset(scope)
    live = [frozenset(tickers) & scope for tickers in current]
    carried = frozenset().union(*live) if live else frozenset()
    added = sorted(scope - carried)
    retire = [index for index, tickers in enumerate(live) if not tickers]
    if any(index in busy for index in retire):
        return None
    candidates = [index for index, tickers in enumerate(live) if tickers]
    replace, start = {}, []
    if added:
        size = None if per_connection is None else max(1, int(per_connection))
        choices = [
            index for index in candidates
            if index not in busy and (size is None or len(live[index]) < size)
        ]
        if size is None and candidates and not choices:
            return None
        rest = added
        if choices:
            index = min(choices, key=lambda i: (len(live[i]), i)) if size else max(
                choices, key=lambda i: (len(live[i]), -i),
            )
            room = len(rest) if size is None else size - len(live[index])
            replace[index] = live[index] | frozenset(rest[:room])
            rest = rest[room:]
        step = size or max(1, len(rest))
        start = [frozenset(rest[i:i + step]) for i in range(0, len(rest), step)]
    keep = [index for index in candidates if index not in replace]
    if per_connection is None:
        needed = 1 if scope else 0
    else:
        needed = math.ceil(len(scope) / max(1, int(per_connection)))
    if len(keep) + len(replace) + len(start) > needed + extra:
        return None
    return keep, replace, start, retire


def _packed(groups, max_rows, max_groups=None):
    """Consecutive whole ``groups`` merged into phases of at most ``max_rows``
    rows and ``max_groups`` groups."""
    phases, current, count = [], {}, 0
    for group in groups:
        if current and (
            len(current) + len(group) > max_rows
            or (max_groups is not None and count >= max_groups)
        ):
            phases.append(current)
            current, count = {}, 0
        current.update(group)
        count += 1
    if current:
        phases.append(current)
    return phases


def linked_first_phases(
    batch, market_id_by_outcome, event_id_by_outcome, pending_events=(),
    live_events=None, pending_events_fenced=False,
):
    """Publish independent games separately, followed by unrelated contracts.

    #10640 put all linked games before futures/props. #10655 also lets a
    completed game's phase commit and refresh before a different game's
    later writes. A phase contains whole markets and every market connected
    through a shared event, transitively: never publish a partial game cut.

    Use the known subscription map, including siblings without a buffered
    tick, so sparse arrivals cannot split an event's markets. Preserve batch
    order within each component and first-seen order between components.
    Unknown market membership retains the original single transaction.
    If a refresh is already owed for an event this batch writes, retain the
    all-games phase: refresh() also drains that debt, so splitting could stamp
    a later game before its new price is written and throttle its actual new
    reading. #10728 — debt owed ONLY to events with no price in this batch (a
    quiet game's held stamp) keeps the split: its price is already stored, so
    the first phase's refresh paying it early stamps nothing unwritten, and
    joining would put every game behind the slowest one and defeat the live
    first plan and its budget below. Any overlap, mixed or not, joins unless
    the caller fences unfinished cohorts out of each refresh explicitly.
    This only plans phases; the existing flush owns SQL, retry and publish.

    #10090 — with ``live_events`` (the run's live event ids; ``None`` keeps
    the plan above), each game holding a live event is its own phase, FIRST,
    in batch order. Every other game is packed whole (at most
    `NONLIVE_PHASE_MAX_GAMES` per phase), and futures/props whole markets at a
    time, into phases of at most `NONLIVE_PHASE_MAX_ROWS` rows, in
    batch order — oldest buffered first, so a budget-deferred tail
    (`flush_budget_spent`) is the head of the next flush's non-live work.
    """
    if not batch or any(market_id_by_outcome.get(oid) is None for oid in batch):
        return [batch]

    parent = {}

    def root(market):
        parent.setdefault(market, market)
        while parent[market] != market:
            parent[market] = parent[parent[market]]
            market = parent[market]
        return market

    first_market_by_event = {}
    for oid, event in event_id_by_outcome.items():
        market = market_id_by_outcome.get(oid)
        if event is None or market is None:
            continue
        first = first_market_by_event.setdefault(event, market)
        parent[root(market)] = root(first)

    games, rest = {}, {}
    for oid, entry in batch.items():
        market = market_id_by_outcome[oid]
        if market in parent:
            games.setdefault(root(market), {})[oid] = entry
        else:
            rest[oid] = entry
    if games and not pending_events_fenced and not set(pending_events).isdisjoint(
        event_id_by_outcome.get(oid) for oid in batch
    ):
        # Preserve batch order in the original single game transaction.
        games = {None: {oid: entry for oid, entry in batch.items() if oid not in rest}}
    if live_events is None:
        phases = list(games.values())
        if rest:
            phases.append(rest)
        return phases

    live, other = [], []
    for game in games.values():
        holds_live = any(event_id_by_outcome.get(oid) in live_events for oid in game)
        (live if holds_live else other).append(game)
    markets = {}
    for oid, entry in rest.items():
        markets.setdefault(market_id_by_outcome[oid], {})[oid] = entry
    return (
        live
        + _packed(other, NONLIVE_PHASE_MAX_ROWS, NONLIVE_PHASE_MAX_GAMES)
        + _packed(markets.values(), NONLIVE_PHASE_MAX_ROWS)
    )


@owns_consumer_sessions("kalshi")
@_owns_kalshi_price_lifetime  # #10693: inside, so the engine is disposed last
async def _run_kalshi_ws_consumer(*, sessions, prices):
    """Main WebSocket consumer loop.

    1. Load linked Kalshi market tickers from DB
    2. Connect to WS and subscribe to ticker + lifecycle channels
    3. Buffer price updates, flush every 2s
    4. Process settlements immediately
    """
    from sqlalchemy import select, update, text, and_
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.kalshi_ws import KalshiWebSocket
    from app.tasks.kalshi import _kalshi_yes_probability  # #8753
    from app.tasks.live_blend_refresh import (
        LiveBlendRefresher, TailReceipts, adopt_handed_off, event_ids_for_outcomes,
        LOOP_REAP_TIMEOUT_S, hand_off_pending, reap_stopped_loops, run_flush_cadence,
    )
    from app.tasks import ws_open_contracts
    from app.tasks.ws_admission import (  # #9418
        unadmitted_live_events, watch_for_unadmitted_live_events,
    )
    from app.tasks.ws_liveness import report as _report_liveness
    from app.tasks.ws_open_contracts import (  # #9484
        grade_open_contract_leg, kalshi_open_contract_stmt,  # #10022
        lifecycle_state, lifecycle_verdict, open_contract_bridge_event_stmt,
        open_contract_channels, open_contract_event_bridge,
        open_contract_event_candidates, open_contract_prices_enabled,
        open_contract_settlement_enabled, open_contract_ticker_map,
        prepared_shard_indexes, shard_tickers,
    )
    from app.utils.futures_rank import rerank_market_fields_stmt  # #6598
    from app.utils.kalshi_exact_trace import ExactKalshiTrace

    # #10090: an invalid override fails here, before the slate or a socket.
    flush_period, blend_floor, failed_retry, flush_budget = kalshi_flush_cadence()

    # A START exists even when slate loading never finishes or selects nothing.
    exact_trace = None
    with contextlib.suppress(Exception):
        exact_trace = ExactKalshiTrace.from_env(os.environ, run=None)

    # #2471: one engine for this run, a fresh session per operation; the
    # decorator disposes it after the final drain. Same call shape as the
    # task factory, so every site below is unchanged.
    get_task_session = sessions.session

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    has_key = os.getenv("KALSHI_RSA_PRIVATE_KEY") or os.getenv("KALSHI_PRIVATE_KEY_PATH")

    if not api_key_id or not has_key:
        logger.warning("Kalshi WS: missing credentials, skipping")
        _report_liveness("kalshi", "no_credentials")
        return {"status": "skipped", "reason": "no_credentials"}

    # Q504-b: reported BEFORE the slate query, because a DB handshake that never
    # resolves is one of the two shapes "up and silent" can take, and the arm
    # cannot describe a state it is stuck inside.
    _report_liveness("kalshi", "loading_slate")

    # #9418: the admission floor is measured from here, the previous recycle.
    run_started_at = time.monotonic()

    # Same full admission read at startup and each routine refresh.
    async def read_linked_slate():
        async with get_task_session() as session:
            result = await session.execute(
                select(
                    FuturesMarket.external_id,
                    FuturesMarket.id,
                    FuturesMarket.event_id,
                )
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source == "kalshi",
                    FuturesMarket.event_id.isnot(None),
                    _kalshi_slate_event_window(),
                )
            )
            rows = result.all()
        market_ids = list({row[0]: row[1] for row in rows}.values())
        outcome_rows = []
        if market_ids:
            async with get_task_session() as session:
                outcome_rows = (
                    await session.execute(
                        select(
                            FuturesOutcome.external_id,
                            FuturesOutcome.market_id,
                            FuturesOutcome.id,
                        ).where(
                            FuturesOutcome.market_id.in_(market_ids),
                            FuturesOutcome.external_id.isnot(None),
                        )
                    )
                ).all()
        return rows, outcome_rows

    def linked_scope(rows, outcome_rows):
        return (frozenset(tuple(row) for row in rows),
                frozenset(tuple(row) for row in outcome_rows))

    def linked_maps(rows, outcome_rows):
        """(lifecycle market map, market → event, ticker → ids) for one read."""
        by_ext = {row[0]: row[1] for row in rows}
        # Q460: the linked event behind each market, so a flushed price can be
        # traced back to the card it belongs on and the blend re-stamped there.
        by_market = {row[1]: row[2] for row in rows if row[2] is not None}
        ids = {}
        for ext_id, market_id, outcome_id in outcome_rows:
            ids[ext_id.upper()] = (market_id, outcome_id)
        return by_ext, by_market, ids

    rows, outcome_rows = await read_linked_slate()
    # #10090: the scope this run currently streams. An in-place scope change
    # replaces these values; the maps below are always mutated in place,
    # because the handlers, flush and watchers read them through these objects.
    current = {"linked": linked_scope(rows, outcome_rows), "bridge": {},
               "open_policy": None}

    event_tickers = list({row[0] for row in rows})
    market_id_by_ext: dict[str, int]
    event_id_by_market: dict[int, int]
    ticker_to_ids: dict[str, tuple[int, int]]
    market_id_by_ext, event_id_by_market, ticker_to_ids = linked_maps(
        rows, outcome_rows,
    )

    market_tickers = list(ticker_to_ids.keys())
    if exact_trace is not None:
        with contextlib.suppress(Exception):
            exact_trace.admission(
                ticker_to_ids, {},
                {oid: event_id_by_market[mid] for mid, oid in ticker_to_ids.values()
                 if mid in event_id_by_market},
                phase="LINKED_SLATE", open_status="UNAVAILABLE_PENDING_ADMISSION",
            )

    # #9484 — every other unsettled Kalshi contract, for PRICES only, on its own
    # connections (`app.tasks.ws_open_contracts`). Never added to
    # `market_id_by_ext` (the lifecycle map) or to `ticker_to_ids` (which the
    # #9418 admission watcher reads as "this event is subscribed"). A failed read
    # costs the arm, never the game slate.
    #
    # Also returns the #9484 EVENT BRIDGE — outcome → event for the admitted
    # game winners whose event is still to be decided (`ws_open_contracts`), so
    # the flush re-stamps their event blend like a slate leg's. Its own read
    # fails on its own: a failed bridge costs the blend re-stamp, never the
    # prices.
    async def read_open_contracts(linked=None) -> tuple[
        dict[str, tuple[int, int]], dict[int, int], bool, bool,
    ]:
        # #10090: a changed-scope refresh excludes the slate it is about to
        # install, not the one the run is still streaming.
        if linked is None:
            linked = ticker_to_ids
        if not open_contract_prices_enabled():
            return {}, {}, False, False
        try:
            async with get_task_session() as session:
                open_rows = (
                    await session.execute(kalshi_open_contract_stmt())
                ).all()
        except Exception:
            logger.exception(
                "Kalshi WS: open-contract admission read failed; "
                "streaming the linked slate only this run"
            )
            return {}, {}, True, False
        ids = open_contract_ticker_map(open_rows, linked)
        candidates = open_contract_event_candidates(open_rows, linked)
        if not candidates:
            return ids, {}, False, False
        try:
            async with get_task_session() as session:
                admitted = (
                    await session.execute(
                        open_contract_bridge_event_stmt(candidates.values())
                    )
                ).scalars().all()
        except Exception:
            logger.exception(
                "Kalshi WS: open-contract event-bridge read failed; "
                "streaming their prices without the event blend this run"
            )
            return ids, {}, False, True
        return ids, open_contract_event_bridge(candidates, admitted), False, False

    # Read up front ONLY when there is no game slate for the read to delay:
    # production's read takes ~2.8 s, and on the recycle path that would be
    # 2.8 s more of every live game without a socket. Otherwise it runs beside
    # the game socket (`admit_open_contracts` below).
    preread = None
    if not market_tickers:
        preread = await read_open_contracts()
        if exact_trace is not None:
            with contextlib.suppress(Exception):
                exact_trace.admission(
                    ticker_to_ids, preread[0], preread[1], phase="OPEN_PREREAD",
                    open_status=("UNAVAILABLE_READ_FAILED" if preread[2]
                                 else "SELECTED" if open_contract_prices_enabled() else "DISABLED"),
                )
        if not preread[0]:
            logger.info("Kalshi WS: no live/upcoming linked markets")
            _report_liveness("kalshi", "no_markets", legs=0)
            return {"status": "no_markets"}

    logger.info(
        "Kalshi WS: %d tickers (%d events)", len(market_tickers), len(event_tickers),
    )

    stats = {
        "tickers_subscribed": len(market_tickers),
        "price_updates": 0,
        "flushes": 0,
        "settlements": 0,
        "errors": 0,
        # Q491: prices a failed flush put BACK on the buffer instead of dropping.
        # `errors` alone cannot distinguish a retried batch from a lost one.
        "requeued": 0,
        # Q491 repair: the final drain retries instead of requeueing, because
        # nothing runs after it. These two separate "we had to try again" from
        # "we gave up and a price is gone".
        "final_flush_retries": 0,
        "final_flush_dropped": 0,
        # #5411: buffered prices the settled-row guard REFUSED to write. Counted
        # separately from `price_updates` so a refusal is a number and not an
        # absence — "it returned" is not "it wrote" (gotcha #53). A refusal is
        # terminal, not an error: the entry leaves the buffer like any other.
        "settled_declined": 0,
        "repeat_or_settled_declined": 0,
        # #9484: rows a flush wrote whose price and book were already what it
        # stored — written (liveness), but no market invalidation sent.
        "quotes_unchanged": 0,
        # #6598 / CERT-3182: rows whose `rank` a flush corrected. This socket
        # moves `current_probability` faster than anything else in the system
        # and had never heard of the column derived from it, so a favourite
        # changing hands mid-game left the board ordered by the last REST poll.
        # Counted unconditionally — the re-derivation is a no-op on a field that
        # did not cross, so 0 is the healthy reading and absence is the failure.
        "ranks_rederived": 0,
        # #9484: the open-contract arm. `open_contract_prices_written` counts
        # rows that TOOK a price, so "the arm is subscribed" and "the arm is
        # moving stored prices" are two numbers, not one.
        "open_contract_tickers": 0,
        "open_contract_connections": 0,
        "open_contract_admission_error": False,
        "open_contract_prices_written": 0,
        # #10022: open-contract legs the socket GRADED from a lifecycle frame,
        # and boards that grade closed. Frames for an open contract that
        # declared no gradeable side (scalar, "", closed) are counted, not
        # silently skipped — they stay with the REST sweep.
        "open_contract_settlements": 0,
        "open_contract_markets_resolved": 0,
        "open_contract_lifecycle_unverdicted": 0,
        # #9484 event bridge: admitted game-winner outcomes (and their distinct
        # events) whose flushed price re-stamps the event blend. 0 with no
        # error is "no such contract this run", not a failure.
        "open_contract_bridged_outcomes": 0,
        "open_contract_bridged_events": 0,
        "open_contract_bridge_error": False,
        # #10090: buffered prices a periodic flush left for the next one after
        # spending `FLUSH_BUDGET_SECONDS` (non-live phases only). Deferred, not
        # dropped: they stay at the head of the buffer.
        "budget_deferred": 0,
        # #10090: buffered non-live prices a periodic flush left for the next
        # one because a live game had new input waiting (`live_input_waiting`).
        # Deferred like `budget_deferred`, never dropped.
        "live_preempted": 0,
    }

    # -- Buffered price updates --
    # outcome_id → (probability, yes_bid, yes_ask). #8753: the book travels WITH
    # the price it produced, so the row the flush writes is one instant's quote —
    # price and book together — and never a socket price beside a REST book.
    price_buffer: dict[int, tuple[float, float | None, float | None]] = {}
    buffer_lock = asyncio.Lock()
    # Q460: outcome → linked event, for the blend re-stamp after each flush.
    event_id_by_outcome: dict[int, int] = {
        outcome_id: event_id_by_market[market_id]
        for market_id, outcome_id in ticker_to_ids.values()
        if market_id in event_id_by_market
    }
    # #6598 / CERT-3182: outcome → its market, for the field re-rank after each
    # flush. Taken from the subscription map that is already in memory rather
    # than read back per flush — this runs every `PRICE_FLUSH_SECONDS`, and a
    # lookup query on that cadence is a cost the socket does not have to pay.
    market_id_by_outcome: dict[int, int] = {
        outcome_id: market_id for market_id, outcome_id in ticker_to_ids.values()
    }
    # #10090: full outcome/event/market maps still own every price write,
    # lifecycle and market invalidation. Known non-speakers can use the normal
    # tail without joining the event's headline cohort or live priority.
    # Derive from the market ticker already read for admission, with no query.
    _ticker_by_market = {
        market_id: ticker for ticker, market_id in market_id_by_ext.items()
    }
    non_blend_outcome_ids = {
        outcome_id for outcome_id, market_id in market_id_by_outcome.items()
        if kalshi_non_speaking_ticker(_ticker_by_market.get(market_id))
    }
    # #9484: filled IN PLACE by `admit_open_contracts`, which the handlers and
    # the flush read through these same objects.
    open_contract_ids: dict[str, tuple[int, int]] = {}
    open_contract_outcome_ids: set[int] = set()
    # #10090: the slate's live events, refilled IN PLACE by the #9418 live
    # reread (`load_unadmitted_live_event_ids`, at once and every 30 s). The
    # flush writes their games first and never defers them.
    live_event_ids: set[int] = set()
    flush_timings = _FlushTimings()
    prices.timings = flush_timings
    blend_refresher = LiveBlendRefresher(
        "kalshi", session_factory=get_task_session,  # #2471
        min_refresh_interval_s=blend_floor,
    )
    # #10090 — the receipt Polymarket has carried since #837: every accepted
    # input is marked (seq, receive instant) as it is buffered, so the
    # per-minute delivery receipt can say what this game received and which
    # published revision carried it. Keyed like `price_buffer`.
    tail_receipts = TailReceipts("kalshi")
    blend_refresher.receipts = tail_receipts
    # #10702: disabled without exact targets AND a short absolute expiry.
    # One budget for this run, including its existing open-contract sockets.
    if exact_trace is not None:
        tail_receipts.run = exact_trace.run
    tail_receipts.exact_trace = exact_trace
    input_marks: dict = {}
    # #9462 review: stamps the previous run still owed when it recycled. Its
    # prices are already stored; the first flush below stamps them.
    stats["blend_pending_adopted"] = adopt_handed_off(blend_refresher)

    async def flush_prices(flush_started=None, *, final_drain=False):
        """Write buffered price updates to DB — #10640: game markets first.

        Returns False for a non-lock failure (the cadence waits before retrying).
        Lock-failed whole cohorts stay buffered and retain that same retry delay,
        while unrelated phases keep the normal timer. #10090
        ``flush_started`` is this flush's start, for the refresher's floor.

        #10640 — the batch is split by `linked_first_phases`. The game phase is
        written, committed, published, acknowledged and its blends refreshed
        BEFORE the unrelated phase opens its transaction, so a held or failed
        futures/prop write can neither delay nor undo a committed game price.
        Each phase keeps every rule below on its own rows. #10655 separates
        independent games too. #10661: a lock timeout retains its phase and
        permits later independent phases; other failures retain the remaining
        tail. Earlier committed games stay done. ``final_drain`` waits for locks
        as long as Postgres does: the drain has no next flush to retry in.
        """
        from app.tasks.kalshi_ws import _KalshiHeadlineEvents

        # Winner/source questions commit together. Known props still write and
        # publish, but cannot hold their event's headline stamp or live priority.
        # Final drain retains its full original event-cohort contract.
        cohort_event_ids = _KalshiHeadlineEvents(
            event_id_by_outcome, () if final_drain else non_blend_outcome_ids,
        )
        exact_trace = getattr(tail_receipts, "exact_trace", None)
        from app.tasks.live_blend_refresh import _mono

        async with buffer_lock:
            batch = dict(price_buffer)
            prices.lock_retry_until = {
                oid: until for oid, until in prices.lock_retry_until.items()
                if oid in batch and until > _mono()
            }
            batch_marks = {
                oid: input_marks[oid] for oid in batch if oid in input_marks
            }
            if exact_trace is not None:
                with contextlib.suppress(Exception):
                    exact_trace.snapshot(batch_marks.values())
        if not batch:
            # #837 tail — a flush with no new prices still owes the stamps a row
            # lock deferred: those prices are already stored, so waiting for the
            # next venue tick would strand them on a quiet market. Free when
            # nothing is queued (no session is opened).
            await blend_refresher.refresh_pending(flush_started=flush_started)
            return True
        # Q491 repair 2 (CERT-659 BLOCK) — THE BUFFER IS DELIBERATELY *NOT*
        # CLEARED HERE. Draining first and putting the batch back on failure
        # only covers the failures you thought to catch, and two rounds of certs
        # found two we had not: `except Exception` never sees `CancelledError`
        # (it is a BaseException), so a recycle cancelling `flush_loop` between
        # the drain and the write lost the batch with `errors=0, requeued=0` —
        # invisible. Entries are now removed ONLY after the write lands, so no
        # failure mode — exception, cancellation, or a hard kill between the two
        # — can lose a price the buffer was holding. Nothing needs to be
        # "put back", because it was never taken away.
        phases = linked_first_phases(
            batch, market_id_by_outcome, cohort_event_ids,
            pending_events=blend_refresher.pending_event_ids(),
            live_events=live_event_ids,
            pending_events_fenced=True,
        )
        # Includes failed/budget-deferred phases until a whole phase commits.
        # Re-resolve through the current map at each launch for late bridges.
        unfinished_price_ids = set(batch)
        had_lock_failure = False
        flush_counted = False
        # #10090: one refresh may cover several committed whole-event phases.
        # Independent writes keep progressing while it runs; receipts are staged
        # only when that task starts, and no refresh outlives this flush.
        stamping = None
        stamping_events = set()
        stamping_fresh = set()
        queued_events = set()
        queued_marks = {}
        queued_refresh = False
        # A skipped/failed first phase must not starve unrelated prior debt.
        implicit_debt_queued = False
        cancelled = False
        # #10090 — LIVE INPUT PREEMPTS THE NON-LIVE TAIL. A live game's tick
        # that arrived after the snapshot used to wait for every later phase of
        # this flush (up to the whole non-live budget) before the next flush
        # could take it. Once one period has passed and at least one non-live
        # phase has started, a non-live phase is not started while such input
        # waits: the tail stays buffered, at the head, like a budget deferral,
        # and the cadence starts the next flush at once with live games first.
        # Preemption permits one non-live phase; the existing budget still
        # applies. Served hot non-live entries yield to the untouched tail.
        nonlive_started = 0

        async def stamp_done(*, cancel=False):
            nonlocal stamping, stamping_events, stamping_fresh
            if stamping is None:
                return
            if cancel and not stamping.cancelling():
                stamping.cancel()
            # Repeated cancellation cannot let a task escape beside the drain.
            interrupted = None
            while not stamping.done():
                try:
                    await asyncio.wait({stamping})
                except asyncio.CancelledError as exc:
                    interrupted = exc
                    if not stamping.cancelling():
                        stamping.cancel()
            task, stamping = stamping, None
            fresh, stamping_fresh = stamping_fresh, set()
            stamping_events = set()
            if task.cancelled() or task.exception() is not None:
                # Also covers cancellation before refresh's first turn, before
                # it has taken these committed IDs into its own debt sets.
                blend_refresher.adopt_pending(fresh)
                if not task.cancelled():
                    logger.error(
                        "Kalshi WS: blend refresh raised after its write committed",
                        exc_info=task.exception(),
                    )
            if interrupted is not None:
                raise interrupted

        async def stamp_start():
            nonlocal stamping, stamping_events, stamping_fresh, queued_refresh
            stamping_fresh = set(queued_events)
            unfinished_events = event_ids_for_outcomes(
                cohort_event_ids, unfinished_price_ids,
            )
            # refresh takes implicit debt too. Capture before its first turn.
            # Excluded cohorts remain owed but cannot read a partially written
            # board or hold unrelated whole-game price transactions together.
            stamping_events = (
                stamping_fresh | set(blend_refresher.pending_event_ids())
            ).difference(unfinished_events)
            with contextlib.suppress(Exception):
                tail_receipts.stage(list(queued_marks.values()))
            stamping = asyncio.create_task(blend_refresher.refresh(
                stamping_fresh, flush_started=flush_started,
                defer_event_ids=unfinished_events,
            ))
            queued_events.clear()
            queued_marks.clear()
            queued_refresh = False
            await asyncio.sleep(0)

        def queue_committed(index, phase, written_outcome_ids, *, registered=None):
            nonlocal queued_refresh, implicit_debt_queued
            blend_outcomes = (
                written_outcome_ids if final_drain else
                (oid for oid in written_outcome_ids if oid not in non_blend_outcome_ids)
            )
            linked_events = event_ids_for_outcomes(cohort_event_ids, blend_outcomes)
            new_events = linked_events if registered is None else linked_events - registered
            first_ack = registered is None and not implicit_debt_queued
            if first_ack:
                implicit_debt_queued = True
            if first_ack or new_events:
                queued_events.update(new_events)
                queued_marks.update({
                    oid: batch_marks[oid]
                    for oid in written_outcome_ids if oid in batch_marks
                    and (registered is None or cohort_event_ids.get(oid) in new_events)
                })
                queued_refresh = True
            return linked_events

        def keep_queued():
            nonlocal queued_refresh
            blend_refresher.adopt_pending(queued_events)
            queued_events.clear()
            queued_marks.clear()
            queued_refresh = False

        try:
            for index, phase in enumerate(phases):
                if not final_drain and any(
                    prices.lock_retry_until.get(oid, 0) > _mono() for oid in phase
                ):
                    # Keep the planner's whole group and unfinished-price fence.
                    # New ticks on the same game cannot bypass its held cohort.
                    continue
                # #10090: live games are first and never budget-deferred; past the
                # budget every later phase stays buffered for the next flush.
                if not final_drain and flush_budget_spent(
                    flush_started, phase, cohort_event_ids, live_event_ids,
                    flush_budget,
                ):
                    stats["budget_deferred"] += sum(len(p) for p in phases[index:])
                    break
                if live_event_ids and not final_drain and not any(
                    cohort_event_ids.get(oid) in live_event_ids for oid in phase
                ):
                    if live_preempts_tail(
                        flush_started, flush_period, nonlive_started, price_buffer,
                        batch, cohort_event_ids, live_event_ids,
                    ):
                        stats["live_preempted"] += sum(len(p) for p in phases[index:])
                        break
                    nonlive_started += 1
                if stamping is not None and stamping.done():
                    await stamp_done()
                    if queued_refresh:
                        await stamp_start()
                # Normally disjoint by the unchanged whole-event planner. A
                # late bridge may name an event in a later phase; implicit debt
                # captured by the active refresh must obey the same fence.
                if not stamping_events.isdisjoint(
                    event_ids_for_outcomes(cohort_event_ids, phase.keys())
                ):
                    await stamp_done()
                declined = 0
                written_outcome_ids: list[int] = []
                written_observations: dict = {}
                try:
                    async with get_task_session() as session:
                        # #10661: bound each lock acquisition in this transaction.
                        # Pool checkout and total phase duration have separate costs.
                        if not final_drain:
                            await session.execute(
                                SET_LOCK_TIMEOUT_SQL,
                                {"ms": lock_timeout_value(PRICE_PHASE_LOCK_TIMEOUT_MS)},
                            )
                        # The admitted whole-question phase keeps its IDs and
                        # ordering, but takes the newest eligible tuple and its
                        # matching receipt before writing. A concurrent open-leg
                        # settlement may remove an ID; retain its admitted tuple
                        # for the existing authoritative SQL refusal to judge.
                        async with buffer_lock:
                            phase = {
                                oid: price_buffer.get(oid, entry)
                                for oid, entry in phase.items()
                            }
                            for oid in phase:
                                if oid in input_marks:
                                    batch_marks[oid] = input_marks[oid]
                                else:
                                    batch_marks.pop(oid, None)
                        # #10693: the phase's rows go through the run's price pipeline,
                        # in batch order. A run of two or more consecutive rows of one
                        # shape (full book / no book, `utils/kalshi_price_statement.py`)
                        # is ONE driver round trip on the supported SQLAlchemy/asyncpg
                        # pair; a single row, or any other installed pair, is the
                        # ordinary one execute per row. Either way each row runs the
                        # same statement with the same binds, the phase stays one
                        # transaction, and a lock timeout or any error raises here with
                        # the whole phase rolled back. Nothing submitted is replayed.
                        #
                        # The statement (built once per process, #10689) carries:
                        #
                        # #8753: the book columns move only when the tick carried BOTH
                        # sides; otherwise each is set to itself (a no-op). Half a book
                        # beside the other half from an older REST poll is a quote
                        # nobody ever offered.
                        #
                        # #9484: the TABLE, not the entity. An ORM-enabled UPDATE ...
                        # RETURNING comes back as an ORM result with no `rowcount`;
                        # the Core form returns the rows that actually took the price.
                        #
                        # #5411 — A SETTLED CONTRACT HAS NO LIVE PRICE. It is worth
                        # exactly 1 or 0, and #5246 made every reachable settlement
                        # writer say so. This socket had never heard of settlement: it
                        # wrote `current_probability` unconditionally, so 189 of the
                        # 6,895 rows that repair cleared were re-priced within 55
                        # minutes (one burst, 22:48-22:52Z on 9/11) and eliminated
                        # players went back to showing a live number. The invariant
                        # was enforced on ENTRY and not on UPDATE.
                        #
                        # The refusal is the TIER-3 set, not `IS NOT NULL`, and the
                        # distinction is the whole correctness of it: the two live US
                        # Open finalists carry `ungradeable_result` (tier 1 — a
                        # RETRACTION meaning the venue never called it, explicitly
                        # reversible by evidence), so refusing every graded-looking
                        # row would have FROZEN the two rows that most need to move.
                        # Guess-family and NULL rows stay writable for the same
                        # reason. `or_` with an explicit NULL arm because the column
                        # is nullable and `NOT IN (...)` is NULL — not TRUE — for a
                        # NULL source. Mirrors `polymarket_ws`'s `is_authoritative`
                        # skip; that socket has always had this guard.
                        #
                        # This socket IS a live writer of this row, so it owes both
                        # stamps the polls owe (#2024). Without `last_updated` the
                        # playoff grid's liveness gate read actively-streaming rows as
                        # days stale — measured 2026-08-30 at up to 23 days on rows
                        # whose price had moved seconds earlier.
                        async with contextlib.aclosing(
                            prices.phase(session, phase, force_observation=final_drain)
                        ) as price_results:
                            async for result in price_results:
                                # #5411 — a settled row matches the id and fails the
                                # guard, so it returns no row. A fresh repeat can
                                # also return nothing. Only returned rows are writes;
                                # no local observation time substitutes for them.
                                declined += result.attempted - result.rowcount
                                # #9484: one market invalidation per row the UPDATE
                                # RETURNED, stamped with the stored `last_updated` —
                                # never the buffered id, never a local clock. A #5411
                                # refusal or a deleted row returns nothing, so it
                                # signals nothing. Staged against this transaction;
                                # published below only once the outer commit landed.
                                #
                                # And only when the write changed what a reader is
                                # served (price or book, `quote_moved_column`). A tick
                                # that only re-stamped `last_updated` (volume, open
                                # interest, a due liveness refresh) still writes —
                                # liveness reads that stamp — but a frame for it sends
                                # every held page to re-read an unchanged row (ux,
                                # #9526).
                                for row in result.all():
                                    written_outcome_ids.append(row.id)
                                    if exact_trace is not None:
                                        with contextlib.suppress(Exception):
                                            if exact_trace.tracks(batch_marks.get(row.id)):
                                                written_observations[row.id] = row.last_updated
                                    if not row.quote_moved:
                                        stats["quotes_unchanged"] += 1
                                        continue
                                    queue_market_change(
                                        session,
                                        market_id=row.market_id,
                                        source="kalshi",
                                        outcome_observed_at={row.id: row.last_updated},
                                    )

                        # #6598 / CERT-3182. `rank` is derived from the price this loop
                        # just moved, and nothing in this module has ever written it —
                        # so a favourite changing hands mid-game left the board numbered
                        # by whichever REST poll last saw it, on the exact rows this
                        # socket exists to keep current.
                        #
                        # KEYED ON THE ROWS THAT ACTUALLY WROTE, not on the batch: a
                        # settled row declined by the #5411 guard changed nothing, and
                        # re-deriving its market's field would be this socket reaching a
                        # board it was just refused. Same session, so it lands in the
                        # transaction that carries the prices.
                        reranked_markets = {
                            market_id_by_outcome[oid]
                            for oid in written_outcome_ids
                            if oid in market_id_by_outcome
                        }
                        if reranked_markets:
                            stats["ranks_rederived"] += (
                                await session.execute(
                                    rerank_market_fields_stmt(sorted(reranked_markets))
                                )
                            ).rowcount
                    if not flush_counted:
                        stats["flushes"] += 1
                        flush_counted = True
                    stats["price_updates"] += len(phase) - declined
                    # First observations are forced, so their missing rows still
                    # mean settled/deleted. Repeats may also be skipped by SQL.
                    first_declined = sum(
                        oid not in prices.committed_outcome_ids
                        and oid not in written_outcome_ids
                        for oid in phase
                    )
                    stats["settled_declined"] += first_declined
                    if declined > first_declined:
                        stats["repeat_or_settled_declined"] = (
                            stats.get("repeat_or_settled_declined", 0)
                            + declined
                            - first_declined
                        )
                    stats["open_contract_prices_written"] += sum(
                        1 for oid in written_outcome_ids
                        if oid in open_contract_outcome_ids
                    )
                except Exception as exc:
                    # Q491 — the batch is still in `price_buffer`, so the next flush
                    # retries it. Before Q491 the buffer was drained up front and a
                    # failed write discarded those prices outright: the socket only
                    # refills an outcome when that market ticks again, and 86.7% of open
                    # Polymarket markets never tick, so one transient error left the
                    # card on its old number with a stale `last_updated` (#2024).
                    #
                    # #10661: a lock timeout retains this component but permits later
                    # independent components. Other errors still stop the unpaid tail.
                    lock_timed_out = is_lock_timeout(exc)
                    unpaid = (
                        len(phase) if lock_timed_out
                        else sum(len(p) for p in phases[index:])
                    )
                    stats["errors"] += 1
                    stats["requeued"] += unpaid
                    if exact_trace is not None:
                        with contextlib.suppress(Exception):
                            exact_trace.write_failed(
                                [batch_marks[oid] for oid in phase if oid in batch_marks],
                                "LOCK_TIMEOUT" if lock_timed_out else "ROLLED_BACK",
                            )
                    logger.exception(
                        "Kalshi WS: flush error (%d updates retained for retry)", unpaid
                    )
                    if lock_timed_out:
                        # The transaction rolled back; all its prices remain buffered.
                        # Only proceed to phases the unchanged planner separated.
                        had_lock_failure = True
                        if not final_drain:
                            until = _mono() + PRICE_FLUSH_SECONDS
                            prices.lock_retry_until.update(dict.fromkeys(phase, until))
                        continue
                    return False

                # The transaction has committed. Register debt before any
                # publication/bookkeeping await can be interrupted.
                prices.committed_outcome_ids.update(written_outcome_ids)
                for oid in phase:
                    prices.lock_retry_until.pop(oid, None)
                unfinished_price_ids.difference_update(phase)
                registered = queue_committed(index, phase, written_outcome_ids)

                if exact_trace is not None:
                    with contextlib.suppress(Exception):
                        for oid, observed_at in written_observations.items():
                            exact_trace.committed(batch_marks.get(oid), observed_at)
                        exact_trace.write_failed(
                            [batch_marks[oid] for oid in phase
                             if oid not in written_outcome_ids and oid in batch_marks],
                            "NO_WRITE_UNCHANGED_SETTLED_OR_MISSING",
                        )

                # The event refresh uses its own session and committed prices.
                # Start it before awaiting the separate MARKET notification;
                # either delivery can progress while the other awaits Redis.
                if stamping is None or stamping.done():
                    await stamp_done()
                    if queued_refresh:
                        await stamp_start()

                # #9484: keep every committed MARKET notification, including
                # standalone futures/props which have no event blend.
                await blend_refresher.publish_market_changes(session)

                # Q491 repair 2 — the write landed, so and only so do these entries
                # leave the buffer. The `== prob` test is what used to be `setdefault`:
                # `handle_ticker` may have buffered a FRESHER price for the same outcome
                # while this write was in flight, and that newer value is the truth, so
                # it must survive to the next flush rather than be dropped as "already
                # written". Same contract, enforced at removal instead of at re-queue.
                async with buffer_lock:
                    for outcome_id, entry in phase.items():
                        if price_buffer.get(outcome_id) == entry:
                            del price_buffer[outcome_id]
                    if live_event_ids and not final_drain:
                        yield_written_nonlive_tail(
                            price_buffer, phase, written_outcome_ids,
                            cohort_event_ids, live_event_ids, final_drain,
                        )

                # Admission may fill an unknown bridge during the postcommit
                # awaits. Recheck at the original trigger boundary as well.
                queue_committed(index, phase, written_outcome_ids, registered=registered)
                # Only newly admitted bridge events need another launch. Known
                # events were already registered before MARKET publication.
                if stamping is None or stamping.done():
                    await stamp_done()
                    if queued_refresh:
                        await stamp_start()
            # Lock retries are bounded on their cohorts above. A handled lock
            # must not add two seconds after unrelated successful work.
            return not had_lock_failure if final_drain else True
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if cancelled:
                try:
                    await stamp_done(cancel=True)
                finally:
                    keep_queued()
            else:
                try:
                    await stamp_done()
                    if queued_refresh:
                        await stamp_start()
                        await stamp_done()
                except asyncio.CancelledError:
                    # Cancellation landing on the final/error join has the same
                    # precedence and debt preservation as one during a write.
                    try:
                        await stamp_done(cancel=True)
                    finally:
                        keep_queued()
                    raise

    async def drain_prices():
        """The LAST flush of this consumer's life — retry, never requeue.

        Q491 repair (CERT-654 BLOCK). `flush_prices` hands a failed batch back to
        `price_buffer` so the next periodic flush retries it. At recycle and at
        shutdown there IS no next flush, so that requeue is a silent drop — the
        certifier's exact-head probe read `writes=[]`, `errors=1`, `requeued=1`.
        Here we call `flush_prices` again instead, up to `FINAL_FLUSH_ATTEMPTS`,
        each attempt on a fresh session.

        Every attempt after the first is counted, so a dyno that routinely needs
        them is visible rather than merely quiet.

        #10661: without the periodic per-phase lock timeout. Three immediate
        attempts at 500 ms each would drop a price whose row is held ~1.5 s;
        waiting for the lock is what lets that price commit.
        """
        try:
            for attempt in range(FINAL_FLUSH_ATTEMPTS):
                await flush_prices(final_drain=True)
                async with buffer_lock:
                    if not price_buffer:
                        return
                if attempt + 1 < FINAL_FLUSH_ATTEMPTS:
                    stats["final_flush_retries"] += 1
        except asyncio.CancelledError:
            # Q491 repair 2: a hard cancel during the LAST drain. The
            # cancellation must keep travelling (CERT-491 — swallowing it makes
            # the runner relaunch a consumer the process is stopping), but the
            # prices it strands must be REPORTED on the way out rather than
            # vanishing at the silent `errors=0, requeued=0` CERT-659 measured.
            stranded = len(price_buffer)
            if stranded:
                stats["final_flush_dropped"] += stranded
                logger.error(
                    "Kalshi WS: %d price updates STRANDED by cancellation "
                    "during the final drain — these are lost, not deferred",
                    stranded,
                )
            raise
        async with buffer_lock:
            stranded = len(price_buffer)
        if stranded:
            # Loud: this is the one place a price genuinely cannot be retried
            # again, so it must never be inferable only from a silence.
            stats["final_flush_dropped"] += stranded
            logger.error(
                "Kalshi WS: %d price updates STRANDED after %d final-flush "
                "attempts — these are lost, not deferred",
                stranded, FINAL_FLUSH_ATTEMPTS,
            )

    async def join_flush_then_drain():
        """#10090 review: the cancelled periodic flush — and the stamp it joins
        on the way out — finishes before the final drain enters the refresher,
        so two refreshes never share its throttle/retry sets and receipts.

        Joined to COMPLETION, never to a timeout (Root 1648Z): a flush whose
        rollback outlasts the reap bound is still inside the refresher, so
        draining then would be the overlap this exists to prevent. Its own
        DB/socket bounds end it, and `loops_stop` ends a flush that lost its
        cancellation at its next turn. A second cancellation landing on the
        join is recorded, not obeyed early: the join and the drain both still
        run, then the cancellation propagates.
        """
        interrupted = None
        while not flush_task.done():
            try:
                await asyncio.wait({flush_task}, timeout=LOOP_REAP_TIMEOUT_S)
            except asyncio.CancelledError as exc:
                interrupted = exc
                continue
            if not flush_task.done():
                logger.error(
                    "Kalshi WS: cancelled flush still running after %.0fs; "
                    "the final drain waits for it",
                    LOOP_REAP_TIMEOUT_S,
                )
        try:
            await drain_prices()
        finally:
            if interrupted is not None:
                raise interrupted

    def _parse_dollar(val) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # #10090 — the one client whose frames may write each mapped ticker. A
    # replacement takes a shared ticker over at its first frame for it: it is
    # subscribed by then, so anything its predecessor still has unread is older
    # or also on the successor's ordered stream. One writer per ticker at every
    # instant, so an overlap never interleaves two streams into the buffer.
    ticker_owner: dict[str, _KalshiClient] = {}

    def lifecycle_admitted(client, msg) -> bool:
        """#10090 — True when ``client``'s lifecycle frame should be handled.

        A frame for a ticker another client owns is that client's, except
        between a replacement and its predecessor, which both deliver every
        shared settlement: there the first to run it handles it, once.
        """
        if client is None:
            return True
        ticker = (msg.get("market_ticker") or "").upper()
        owner = ticker_owner.get(ticker)
        if owner is not None and owner is not client and owner is not client.pair:
            return False
        seen = client.lifecycle_seen
        if seen is not None:
            key = (ticker, msg.get("status"), msg.get("event_type"), msg.get("result"))
            if key in seen:
                return False
            seen.add(key)
        return True

    async def handle_ticker(msg: dict, client=None):
        exact_trace = getattr(tail_receipts, "exact_trace", None)
        ticker = (msg.get("market_ticker") or msg.get("ticker", "")).upper()
        if client is not None:
            owner = ticker_owner.get(ticker)
            if owner is not None and owner is not client:
                if owner is client.predecessor and ticker in client.tickers:
                    ticker_owner[ticker] = client
                else:
                    if exact_trace is not None:
                        with contextlib.suppress(Exception):
                            exact_trace.decided(msg, reason="SUPERSEDED_CONNECTION")
                    return
        ids = ticker_to_ids.get(ticker) or open_contract_ids.get(ticker)
        if not ids:
            if exact_trace is not None:
                with contextlib.suppress(Exception):
                    exact_trace.decided(msg, reason="UNMAPPED")
            return

        market_id, outcome_id = ids
        # #10090 — a message for this game's contract, before the price policy.
        with contextlib.suppress(Exception):
            tail_receipts.note_raw(event_id_by_outcome.get(outcome_id))

        last_price = _parse_dollar(msg.get("price_dollars"))
        yes_bid = _parse_dollar(msg.get("yes_bid_dollars"))
        yes_ask = _parse_dollar(msg.get("yes_ask_dollars"))

        # #8753 — THE REST WRITER'S RULE, CALLED, NEVER RE-SPELLED. This used to
        # store the last trade whenever there was one, so a trade the live book
        # had already moved past became the stored price between polls: on
        # `/events/15315945` (Northwestern @ Indiana, live) the socket stored
        # Indiana "scores first TD" at 0.96 above its own 0.95 ask, and the
        # three exclusive legs of that card summed to 139%. The poll that wrote
        # the same row two minutes earlier would have stored the 0.77 midpoint;
        # the socket, being faster, won every time. One price policy per venue:
        # tight book → midpoint, else a trade the book does not refute, else a
        # longshot ask, else nothing (a wide book with no trade is not a price).
        prob = _kalshi_yes_probability(yes_bid, yes_ask, last_price)
        # The socket's historical open bounds, kept: a terminal 0 or 1 is
        # settlement's to write (`handle_lifecycle`), never a streamed tick's.
        if prob is None or not 0 < prob < 1:
            if exact_trace is not None:
                with contextlib.suppress(Exception):
                    exact_trace.decided(
                        msg, reason=("MISSING_OR_INVALID_DOLLAR_FIELDS"
                                     if last_price is None and yes_bid is None and yes_ask is None
                                     else "PRICE_POLICY_REFUSED" if prob is None else "TERMINAL_OR_INVALID"),
                        market=market_id, outcome=outcome_id,
                        event=event_id_by_outcome.get(outcome_id), probability=prob,
                    )
            return

        async with buffer_lock:
            price_buffer[outcome_id] = (prob, yes_bid, yes_ask)
            # Under the lock, so seq order is buffer order. Never raises into
            # the socket: a receipt is evidence about the price, not the price.
            try:
                mark = tail_receipts.note_input(
                    event_id_by_outcome.get(outcome_id), outcome_id, prob, "ticker",
                )
            except Exception:
                mark = None
            if mark is not None:
                input_marks[outcome_id] = mark
            if exact_trace is not None:
                with contextlib.suppress(Exception):
                    exact_trace.decided(
                        msg, reason="ACCEPTED", market=market_id, outcome=outcome_id,
                        event=event_id_by_outcome.get(outcome_id), probability=prob, mark=mark,
                    )

    # Shared by every auxiliary socket and the main/fallback open-leg route.
    # Wait before opening a session; unwind the transaction before the permit.
    open_grade_admission = asyncio.Semaphore(OPEN_CONTRACT_GRADE_CONCURRENCY)

    async def handle_open_contract_lifecycle(ticker: str, msg: dict, ids=None):
        """#10022: one open-contract leg, graded by its own frame — never the
        two-sided write below (see `ws_open_contracts`). #10090: ``ids`` were
        captured when the frame was accepted, before any scope change."""
        if not open_contract_settlement_enabled():
            return  # the undo line: prices only, settlement left to REST
        verdict = lifecycle_verdict(msg)
        if verdict is None:
            stats["open_contract_lifecycle_unverdicted"] += 1
            return
        market_id, outcome_id = ids if ids is not None else open_contract_ids[ticker]
        try:
            async with open_grade_admission, get_task_session() as session:
                graded, resolved = await grade_open_contract_leg(
                    session, market_id=market_id, outcome_id=outcome_id,
                    state=lifecycle_state(msg), result=msg.get("result"),
                )
                if graded is not None:
                    queue_market_change(
                        session,
                        market_id=market_id,
                        source="kalshi",
                        outcome_observed_at={graded.id: graded.last_updated},
                    )
                if resolved is not None:
                    queue_market_change(
                        session,
                        market_id=resolved.id,
                        source="kalshi",
                        outcome_observed_at={},
                        terminal=True,
                        updated_at=resolved.settled_at,
                    )
            if graded is None:
                return
            # A tick still buffered for this leg would be refused by the
            # #5411 guard anyway; dropping it keeps the count honest.
            async with buffer_lock:
                price_buffer.pop(outcome_id, None)
            stats["open_contract_settlements"] += 1
            if resolved is not None:
                stats["open_contract_markets_resolved"] += 1
            await blend_refresher.publish_market_changes(session)
            logger.info(
                "Kalshi WS: open contract %s graded (won=%s, market %d%s)",
                ticker, verdict[1], market_id,
                " resolved" if resolved is not None else "",
            )
        except Exception:
            stats["errors"] += 1
            logger.exception("Kalshi WS: open-contract settlement error for %s", ticker)

    _UNCAPTURED = object()

    async def handle_shard_lifecycle(msg: dict, *, client=None, ids=_UNCAPTURED):
        """An open-contract connection grades its own legs and nothing else: a
        linked-slate frame is the game socket's to handle, exactly once."""
        if client is not None:
            if not lifecycle_admitted(client, msg):
                return
            if client.pair_lock is not None:
                async with client.pair_lock:
                    return await handle_shard_lifecycle(msg, ids=ids)
        ticker = (msg.get("market_ticker") or "").upper()
        if ids is not _UNCAPTURED:
            if ids is not None:
                await handle_open_contract_lifecycle(ticker, msg, ids=ids)
            return
        if ticker in open_contract_ids and ticker not in ticker_to_ids:
            await handle_open_contract_lifecycle(ticker, msg)

    async def prepare_shard_lifecycle(msg: dict, *, client=None):
        """Defer the per-leg grader; it has no buffer-derived closing input.

        #10090: the leg's identity is captured here, at acceptance, so a scope
        change before the deferred grade runs cannot re-route or lose it.
        """
        ticker = (msg.get("market_ticker") or "").upper()
        ids = (
            open_contract_ids.get(ticker) if ticker not in ticker_to_ids else None
        )
        return functools.partial(handle_shard_lifecycle, client=client, ids=ids)

    async def prepare_lifecycle(msg: dict, *, client=None):
        """Capture closing inputs before deferring slow settlement work (#10667)."""
        from functools import partial

        ticker = (msg.get("market_ticker") or "").upper()
        parts = ticker.rsplit("-", 1)
        closing_price = _UNCAPTURED
        # #10090: and the route, so a scope change before the deferred write
        # runs cannot re-route or drop a frame already accepted.
        # #10090: as in `handle_lifecycle`, a connection's frame takes the
        # two-sided write only for a ticker the slate still maps.
        if ticker in open_contract_ids and ticker not in ticker_to_ids:
            route = ("open", open_contract_ids[ticker])
        elif (
            len(parts) == 2 and parts[0] in market_id_by_ext
            and (client is None or ticker in ticker_to_ids)
        ):
            route = ("linked", market_id_by_ext[parts[0]])
        else:
            route = None
        if (
            not (ticker in open_contract_ids and ticker not in ticker_to_ids)
            and is_terminal(msg.get("status", ""))
            and len(parts) == 2
            and parts[0] in market_id_by_ext
        ):
            async with buffer_lock:
                ids = ticker_to_ids.get(ticker)
                buffered = price_buffer.get(ids[1]) if ids else None
                closing_price = buffered[0] if buffered else None
        return partial(
            handle_lifecycle, closing_price=closing_price, client=client, route=route,
        )

    async def handle_lifecycle(
        msg: dict, *, closing_price=_UNCAPTURED, client=None, route=_UNCAPTURED,
    ):
        ticker = (msg.get("market_ticker") or "").upper()
        # #10022: an open contract is never in the lifecycle map (its event
        # ticker is not the linked slate's), so it is routed before the
        # two-sided handler can see it. `open_contract_ids` already excludes
        # every ticker the linked slate carries.
        if route is _UNCAPTURED:
            parts = ticker.rsplit("-", 1)
            # #10090: a connection keeps the tickers that left scope until it
            # retires, so its frames take the two-sided write only for a
            # ticker the slate still maps, as every subscribed ticker was.
            if ticker in open_contract_ids and ticker not in ticker_to_ids:
                route = ("open", open_contract_ids[ticker])
            elif (
                len(parts) == 2 and parts[0] in market_id_by_ext
                and (client is None or ticker in ticker_to_ids)
            ):
                route = ("linked", market_id_by_ext[parts[0]])
            else:
                route = None
        if client is not None:
            if not lifecycle_admitted(client, msg):
                return
            if client.pair_lock is not None:
                async with client.pair_lock:
                    return await handle_lifecycle(
                        msg, closing_price=closing_price, route=route,
                    )
        status = msg.get("status", "")
        result = msg.get("result")

        if route is not None and route[0] == "open":
            await handle_open_contract_lifecycle(ticker, msg, ids=route[1])
            return

        # CAL-P049 (#1818): this writes FuturesMarket.status='resolved', so it is
        # the same class as the poll's inverted tuple — it missed ``determined``.
        # Reads the one measured set now (app/utils/kalshi_market_status.py).
        if not is_terminal(status):
            return

        if route is None:
            return
        market_id = route[1]

        # Direct callers retain the original capture path. Prepared callbacks
        # carry an explicit value, including None, captured before offloading.
        if closing_price is _UNCAPTURED:
            async with buffer_lock:
                ids = ticker_to_ids.get(ticker)
                buffered = price_buffer.get(ids[1]) if ids else None
                closing_price = buffered[0] if buffered else None

        try:
            async with get_task_session() as session:
                settled = (
                    await session.execute(
                        update(FuturesMarket)
                        .execution_options(synchronize_session=False)
                        .where(FuturesMarket.id == market_id)
                        .values(
                            status="resolved",
                            **settled_values(FuturesMarket.settled_at),
                        )
                        .returning(FuturesMarket.id, FuturesMarket.settled_at)
                    )
                ).first()
                # #9484: the terminal invalidation carries the stored
                # `settled_at` this write returned, and only if it returned
                # one. It mirrors exactly what REST will now serve for the
                # market; clients refetch and apply their settlement guards.
                if settled is not None:
                    queue_market_change(
                        session,
                        market_id=settled.id,
                        source="kalshi",
                        outcome_observed_at={},
                        terminal=True,
                        updated_at=settled.settled_at,
                    )

                if result in ("yes", "no"):
                    is_winner = result == "yes"
                    # Set is_winner on the settling outcome
                    await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.market_id == market_id,
                            FuturesOutcome.external_id == ticker,
                        )
                        .values(
                            is_winner=is_winner,
                            calibration_probability=closing_price,
                        )
                    )
                    # Set is_winner=False on the opposite outcome
                    await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.market_id == market_id,
                            FuturesOutcome.external_id != ticker,
                        )
                        .values(
                            is_winner=not is_winner,
                            calibration_probability=(
                                1.0 - closing_price if closing_price else None
                            ),
                        )
                    )

            stats["settlements"] += 1
            await blend_refresher.publish_market_changes(session)
            logger.info(
                "Kalshi WS: %s settled (result=%s, closing=%.3f)",
                ticker, result, closing_price or 0,
            )
        except Exception:
            stats["errors"] += 1
            logger.exception("Kalshi WS: settlement error for %s", ticker)

    # -- Connections (#10090) --
    # Steady clients by kind; a replaced or retired client leaves these lists
    # at once and stays in `retiring` until its reader has stopped and drained.
    game_clients: list[_KalshiClient] = []
    open_clients: list[_KalshiClient] = []
    retiring: list[_KalshiClient] = []
    handoff_tasks: set[asyncio.Task] = set()
    retired_messages = {"game": 0, "open": 0}

    def start_client(tickers, kind, *, prepared=True, predecessor=None):
        sock = KalshiWebSocket()
        sock.exact_trace = exact_trace
        client = _KalshiClient(sock, tickers, kind)
        if kind == "game":
            sock.book_tickers = client.tickers & book_population()
        sock.on_ticker = functools.partial(handle_ticker, client=client)
        if kind == "game":
            sock.on_lifecycle = functools.partial(handle_lifecycle, client=client)
            sock.on_lifecycle_prepare = functools.partial(prepare_lifecycle, client=client)
        else:
            sock.on_lifecycle = functools.partial(handle_shard_lifecycle, client=client)
            set_prepared(client, prepared)
        if predecessor is not None:
            # Both deliver every shared settlement until the predecessor stops.
            client.predecessor = predecessor
            client.pair, predecessor.pair = predecessor, client
            client.lifecycle_seen = predecessor.lifecycle_seen = set()
            client.pair_lock = predecessor.pair_lock = asyncio.Lock()
            if predecessor.kind != "game":
                # Inline on both while they overlap; recomputed at retirement.
                set_prepared(predecessor, False)
                set_prepared(client, False)
        # A replacement's set subscribes sorted; startup keeps the read's order.
        tickers = list(tickers) if isinstance(tickers, list) else sorted(tickers)
        if kind == "game":
            run = sock.run(market_tickers=tickers)
        else:
            run = sock.run(market_tickers=tickers, channels=open_contract_channels())
        client.task = asyncio.create_task(run, name=f"kalshi-{kind}-client")
        return client

    def set_prepared(client, prepared):
        """An open shard defers lifecycle only when it alone owns each market
        key (`prepared_shard_indexes`); otherwise inline, the original order."""
        client.sock.on_lifecycle_prepare = (
            functools.partial(prepare_shard_lifecycle, client=client)
            if prepared else None
        )

    async def retire_client(client, successor=None):
        """Stop ``client`` once ``successor`` (if any) has held an acknowledged
        subscription for the overlap, without cancelling callbacks it already
        accepted. Ownership of their shared tickers moves only after it has
        stopped delivering. A successor whose subscription is rejected or never
        acknowledged never retires its predecessor: the refresh rebuilds
        (`refresh_subscription_scope`), which ends both."""
        try:
            if successor is not None:
                subscribed_since = None
                while True:
                    if successor.sock.is_subscribed:
                        if subscribed_since is None:
                            subscribed_since = time.monotonic()
                        if time.monotonic() - subscribed_since >= SUCCESSOR_OVERLAP_SECONDS:
                            break
                    else:
                        subscribed_since = None
                    await asyncio.sleep(min(0.25, SUCCESSOR_OVERLAP_SECONDS))
            await client.sock.retire()
            done, _ = await asyncio.wait({client.task}, timeout=RETIRE_DRAIN_SECONDS)
            if not done:
                logger.error(
                    "Kalshi WS: retiring %s connection still draining after %.0fs; "
                    "cancelling it", client.kind, RETIRE_DRAIN_SECONDS,
                )
                client.task.cancel()
                await asyncio.gather(client.task, return_exceptions=True)
            elif not client.task.cancelled() and client.task.exception() is not None:
                logger.warning(
                    "Kalshi WS: retired %s connection ended with an error",
                    client.kind, exc_info=client.task.exception(),
                )
        finally:
            for ticker, owner in list(ticker_owner.items()):
                if owner is client:
                    if successor is not None and ticker in successor.tickers:
                        ticker_owner[ticker] = successor
                    else:
                        del ticker_owner[ticker]
            if successor is not None:
                successor.predecessor = successor.pair = None
                successor.lifecycle_seen = successor.pair_lock = None
            client.pair = client.lifecycle_seen = client.pair_lock = None
            if client in retiring:
                retiring.remove(client)
            retired_messages[client.kind] += client.sock.stats.get("messages", 0)
            if client.kind != "game":
                with contextlib.suppress(Exception):
                    refresh_prepared(open_contract_ids)

    def launch_retire(client, successor=None):
        retiring.append(client)
        task = asyncio.create_task(
            retire_client(client, successor), name="kalshi-client-handoff",
        )
        handoff_tasks.add(task)
        task.add_done_callback(handoff_tasks.discard)

    def claim_tickers(client, scope):
        """Point each in-scope ticker ``client`` carries at its writer: still
        the predecessor for a ticker both carry, until the successor's first
        frame for it (`handle_ticker`) or the predecessor's retirement."""
        pred = client.predecessor
        for ticker in client.tickers & scope:
            if (
                pred is not None and ticker in pred.tickers
                and ticker_owner.get(ticker) in (None, pred)
            ):
                ticker_owner[ticker] = pred
            else:
                ticker_owner[ticker] = client

    def game_messages():
        return retired_messages["game"] + sum(
            c.sock.stats.get("messages", 0)
            for c in (*game_clients, *retiring) if c.kind == "game"
        )

    def game_connected():
        return any(c.sock.is_connected for c in game_clients)

    def book_population() -> frozenset:
        """#10090 — the linked winner legs (the blend's own eligibility) of
        events live now, independent of who is reading them, within the cap."""
        if not kalshi_direct_book_enabled():
            return frozenset()
        eligible = sorted(
            ticker for ticker, (_market_id, outcome_id) in ticker_to_ids.items()
            if outcome_id not in non_blend_outcome_ids
            and event_id_by_outcome.get(outcome_id) in live_event_ids
        )
        cap = kalshi_book_max_tickers()
        if len(eligible) > cap:
            stats["book_over_cap"] = len(eligible) - cap
        return frozenset(eligible[:cap])

    async def refresh_books():
        population = book_population()
        stats["book_tickers"] = len(population)
        for client in list(game_clients):
            try:
                await client.sock.set_book_tickers(client.tickers & population)
            except Exception:
                logger.warning(
                    "Kalshi WS: order book membership update failed; ticker "
                    "summaries carry on", exc_info=True,
                )

    # -- Periodic flush task --
    # #10090: start to start, so the flush's own work is not added to the
    # interval; see `run_flush_cadence` for what it preserves.
    # #10657: set before the loop is cancelled, so a cancellation lost inside
    # a flush still ends the loop at its next turn (`run_flush_cadence`).
    loops_stop = asyncio.Event()

    # #10090: each flush's duration, and its publish and stamp time, for the
    # stats line (`_FlushTimings`; the price save is timed by `prices`).
    # `refresh_pending` stamps through `self.refresh`, so it is timed there.
    for name, bucket in (
        ("publish_market_changes", "publish"),
        ("refresh", "stamp"),
    ):
        method = getattr(blend_refresher, name, None)
        if method is not None:
            setattr(blend_refresher, name, flush_timings.timed(bucket, method))

    # #10090: an in-place scope change swaps the maps between flushes, never
    # under one that planned its phases from the previous maps.
    flush_gate = asyncio.Lock()

    async def timed_flush(flush_started):
        async with flush_gate:
            started = time.monotonic()
            try:
                return await flush_prices(flush_started)
            finally:
                flush_timings.flushed(time.monotonic() - started)

    async def flush_loop():
        if failed_retry is None:
            await run_flush_cadence(timed_flush, flush_period, stop=loops_stop)
        else:
            await run_flush_cadence(
                timed_flush, flush_period, stop=loops_stop,
                failed_retry_interval_s=failed_retry,
            )

    # -- Periodic stats logging --
    async def stats_loop():
        while True:
            await asyncio.sleep(60)
            # Q504-b: the blend counters ride along. `stamped` and `no_reading`
            # are the difference between "the socket is delivering prices" and
            # "the number on the card is moving", and on 2026-09-01 only the
            # first of those was observable — the fast lane was streaming
            # 10,098 prices into `futures_outcomes` while every tennis event's
            # last mile returned None, invisibly, for hours.
            blend = blend_refresher.stats
            logger.info(
                "Kalshi WS: %d updates, %d flushes, %d settlements, %d errors, "
                "%d msgs | blend stamped=%d no_reading=%d throttled=%d errors=%d "
                "lock_skipped=%d unobserved=%d stale=%d | %s deferred=%d "
                "preempted=%d live=%d book=%d quotes=%d resnapshots=%d",
                stats["price_updates"], stats["flushes"],
                stats["settlements"], stats["errors"],
                game_messages(),
                blend["stamped"], blend["no_reading"],
                blend["throttled"], blend["errors"],
                blend.get("lock_skipped", 0),
                blend.get("unobserved_skipped", 0),
                # #8910: readings refused as older than the stored observation.
                blend.get("stale_readings_refused", 0),
                # #10090: this minute's flush phases, then cumulative deferrals.
                flush_timings.line(), stats["budget_deferred"],
                stats["live_preempted"], len(live_event_ids),
                # #10090 direct book: tickers carried, quotes taken, resyncs.
                stats.get("book_tickers", 0),
                sum(c.sock.stats.get("book_quotes", 0) for c in game_clients),
                sum(c.sock.stats.get("book_resnapshots", 0) for c in game_clients),
            )
            flush_timings.reset()
            _report_liveness(
                "kalshi", "streaming" if game_connected() else "disconnected",
                legs=len(market_tickers),
                msgs=game_messages(),
                stamped=blend["stamped"],
                no_reading=blend["no_reading"],
            )

    flush_task = asyncio.create_task(flush_loop(), name="kalshi-flush-loop")
    stats_task = asyncio.create_task(stats_loop(), name="kalshi-stats-loop")

    # #9484: the open-contract connections, admitted beside the game socket and
    # torn down in the `finally` on every exit path. #10022: they also carry
    # `market_lifecycle_v2`, routed to the PER-LEG grader (never the two-sided
    # handler — see `ws_open_contracts`). #10090: `open_clients`.

    def open_policy():
        # Callback/subscription policy. A switch takes the full rebuild.
        return (
            open_contract_prices_enabled(), open_contract_settlement_enabled(),
            tuple(open_contract_channels()),
        )

    def refresh_prepared(scope_ids):
        layout = [sorted(c.tickers & frozenset(scope_ids)) for c in open_clients]
        prepared = prepared_shard_indexes(scope_ids, layout)
        for index, client in enumerate(open_clients):
            if client.predecessor is None:
                set_prepared(client, index in prepared)

    async def admit_open_contracts():
        ids, bridge, failed, bridge_failed = (
            preread if preread is not None else await read_open_contracts()
        )
        current["open_policy"] = open_policy()
        current["bridge"] = dict(bridge)
        stats["open_contract_admission_error"] = failed
        stats["open_contract_bridge_error"] = bridge_failed
        # #9484: their event is re-stamped after a flush exactly like a slate
        # leg's (`event_ids_for_outcomes` in `flush_prices`). Never overwrites a
        # slate entry — the map excluded every ticker the slate carries.
        for outcome_id, event_id in bridge.items():
            event_id_by_outcome.setdefault(outcome_id, event_id)
            # Bridge candidates passed canonical winner admission; keep this
            # new/refreshed map member speaking even if an old entry existed.
            non_blend_outcome_ids.discard(outcome_id)
        stats["open_contract_bridged_outcomes"] = len(bridge)
        stats["open_contract_bridged_events"] = len(set(bridge.values()))
        # An open contract's field is re-ranked like a linked one's.
        market_id_by_outcome.update(
            (outcome_id, market_id) for market_id, outcome_id in ids.values()
        )
        open_contract_outcome_ids.update(oid for _, oid in ids.values())
        open_contract_ids.update(ids)
        if exact_trace is not None:
            with contextlib.suppress(Exception):
                exact_trace.admission(
                    ticker_to_ids, open_contract_ids, event_id_by_outcome, phase="OPEN_ADMISSION",
                    open_status=("UNAVAILABLE_READ_FAILED" if failed
                                 else "SELECTED" if open_contract_prices_enabled() else "DISABLED"),
                )
        shards = shard_tickers(ids)
        stats["open_contract_tickers"] = len(ids)
        stats["open_contract_connections"] = len(shards)
        prepared_shards = prepared_shard_indexes(ids, shards)
        for shard_index, shard in enumerate(shards):
            client = start_client(
                shard, "open", prepared=shard_index in prepared_shards,
            )
            open_clients.append(client)
            claim_tickers(client, frozenset(ids))
        if ids:
            logger.info(
                "Kalshi WS: %d open-contract tickers over %d connection(s)",
                len(ids), len(shards),
            )

    admission_task = asyncio.create_task(admit_open_contracts())

    def apply_scope(linked, maps, ids, bridge, game_plan, open_plan):
        """#10090 — install a changed scope without tearing down the run.

        Synchronous from the first map write to the last task start, so no
        handler, flush or watcher ever reads half of it. Buffered prices whose
        outcome left scope keep their event/market identities until written:
        that is debt the flush still owes, exactly as the final drain paid it.
        """
        new_by_ext, new_by_market, new_ids = maps
        buffered = set(price_buffer)
        by_outcome = {
            oid: new_by_market[mid] for mid, oid in new_ids.values()
            if mid in new_by_market
        }
        market_by_outcome = {oid: mid for mid, oid in new_ids.values()}
        ticker_by_market = {mid: ticker for ticker, mid in new_by_ext.items()}
        non_blend = {
            oid for oid, mid in market_by_outcome.items()
            if kalshi_non_speaking_ticker(ticker_by_market.get(mid))
        }
        for oid, event_id in bridge.items():
            by_outcome.setdefault(oid, event_id)
            non_blend.discard(oid)
        market_by_outcome.update((oid, mid) for mid, oid in ids.values())
        open_oids = {oid for _, oid in ids.values()}
        fresh = set(market_by_outcome) | set(by_outcome)
        for oid in buffered - fresh:
            if oid in event_id_by_outcome:
                by_outcome[oid] = event_id_by_outcome[oid]
            if oid in market_id_by_outcome:
                market_by_outcome[oid] = market_id_by_outcome[oid]
            if oid in non_blend_outcome_ids:
                non_blend.add(oid)
            if oid in open_contract_outcome_ids:
                open_oids.add(oid)

        for target, value in (
            (market_id_by_ext, new_by_ext), (event_id_by_market, new_by_market),
            (ticker_to_ids, new_ids), (event_id_by_outcome, by_outcome),
            (market_id_by_outcome, market_by_outcome), (open_contract_ids, ids),
        ):
            target.clear()
            target.update(value)
        for target, value in (
            (non_blend_outcome_ids, non_blend), (open_contract_outcome_ids, open_oids),
            (legged_market_ids, {mid for mid, _ in new_ids.values()}),
        ):
            target.clear()
            target.update(value)
        market_tickers[:] = list(new_ids)
        current["linked"] = linked
        current["bridge"] = dict(bridge)

        changed = {"kept": 0, "replaced": 0, "started": 0, "retired": 0}
        for kind, clients, plan, scope in (
            ("game", game_clients, game_plan, frozenset(new_ids)),
            ("open", open_clients, open_plan, frozenset(ids)),
        ):
            keep, replace, start, retire = plan
            steady = []
            for index, client in enumerate(clients):
                if index in replace:
                    successor = start_client(replace[index], kind, predecessor=client)
                    launch_retire(client, successor)
                    steady.append(successor)
                elif index in retire:
                    launch_retire(client)
                else:
                    steady.append(client)
            steady.extend(start_client(tickers, kind) for tickers in start)
            clients[:] = steady
            changed["kept"] += len(keep)
            changed["replaced"] += len(replace)
            changed["started"] += len(start)
            changed["retired"] += len(retire)
        game_scope, open_scope = frozenset(new_ids), frozenset(ids)
        # Built once: inside the comprehension it was rebuilt per owned ticker,
        # quadratic in ~44k tickers — a ~93 s frozen loop in production (v5614).
        in_scope = game_scope | open_scope
        for ticker in [t for t in ticker_owner if t not in in_scope]:
            del ticker_owner[ticker]
        # Each client claims only within its own arm: a kept open shard still
        # physically carries a ticker that moved to the game arm, and must not
        # take it back from the game connection that now streams it.
        for client in game_clients:
            claim_tickers(client, game_scope)
        for client in open_clients:
            claim_tickers(client, open_scope)
        refresh_prepared(ids)

        stats["tickers_subscribed"] = len(new_ids)
        stats["open_contract_tickers"] = len(ids)
        stats["open_contract_connections"] = len(open_clients)
        stats["open_contract_bridged_outcomes"] = len(bridge)
        stats["open_contract_bridged_events"] = len(set(bridge.values()))
        stats["scope_in_place"] = stats.get("scope_in_place", 0) + 1
        for key, count in changed.items():
            stats[f"clients_{key}"] = stats.get(f"clients_{key}", 0) + count
        if exact_trace is not None:
            with contextlib.suppress(Exception):
                exact_trace.admission(
                    ticker_to_ids, open_contract_ids, event_id_by_outcome,
                    phase="SCOPE_IN_PLACE", open_status="SELECTED",
                )
        return changed

    async def refresh_subscription_scope():
        """``"keep"``, ``"applied"`` or ``"rebuild"`` (the old full recycle).

        #10090: an unchanged scope keeps everything; a changed one is applied
        in place when the policy is unchanged and the connection bound holds.
        Ended clients, an unfinished or failed admission, a policy switch, a
        busy handoff, or a failed read of a changed slate keep the rebuild.
        """
        if any(client.task.done() for client in open_clients):
            # The old unconditional recycle also repaired an ended auxiliary
            # client. An unchanged mapping cannot certify its lifetime.
            return "rebuild"
        if any(
            client.sock.subscription_failed(SUBSCRIBE_ACK_DEADLINE_SECONDS)
            for client in (*game_clients, *open_clients, *retiring)
        ):
            # A rejected or never-acknowledged subscription may be a silent
            # socket; keeping it would retain exactly what the recycle repaired.
            stats["recycle_reason"] = "subscription"
            return "rebuild"
        # A stalled initial open/bridge read has no working arm to retain.
        # Preserve the old deadline's bounded cleanup/rebuild repair.
        if not admission_task.done():
            return "rebuild"
        if admission_task.cancelled() or admission_task.exception() is not None:
            return "rebuild"  # rebuild a partially admitted arm through the safe path
        try:
            refreshed_rows, refreshed_outcomes = await read_linked_slate()
            linked = linked_scope(refreshed_rows, refreshed_outcomes)
            maps = linked_maps(refreshed_rows, refreshed_outcomes)
            ids, bridge, failed, bridge_failed = await read_open_contracts(maps[2])
        except Exception:
            logger.warning(
                "Kalshi WS: subscription refresh read failed, keeping the subscription",
                exc_info=True,
            )
            return "keep"
        if failed or bridge_failed:
            # No successful full-scope observation: keep working sockets unless
            # the slate itself moved, which the rebuild re-reads in full.
            return "rebuild" if linked != current["linked"] else "keep"
        if open_policy() != current["open_policy"]:
            return "rebuild"
        if not maps[2] and not ids:
            # Nothing left to stream: the rebuild reports `no_markets` exactly
            # as a startup with this scope does.
            return "rebuild"
        if (
            linked == current["linked"] and ids == open_contract_ids
            and bridge == current["bridge"]
        ):
            return "keep"
        game_plan = plan_stable_shards(
            [c.tickers for c in game_clients], maps[2],
            busy={i for i, c in enumerate(game_clients) if c.predecessor is not None},
        )
        open_plan = plan_stable_shards(
            [c.tickers for c in open_clients], ids,
            per_connection=ws_open_contracts.OPEN_CONTRACT_TICKERS_PER_CONNECTION,
            extra=OPEN_CONTRACT_EXTRA_CONNECTIONS,
            busy={i for i, c in enumerate(open_clients) if c.predecessor is not None},
        )
        if game_plan is None or open_plan is None:
            return "rebuild"
        async with flush_gate:
            changed = apply_scope(linked, maps, ids, bridge, game_plan, open_plan)
        logger.info(
            "Kalshi WS: scope changed in place — %d linked / %d open tickers; "
            "connections kept=%d replaced=%d started=%d retired=%d",
            len(ticker_to_ids), len(open_contract_ids), changed["kept"],
            changed["replaced"], changed["started"], changed["retired"],
        )
        return "applied"

    _report_liveness("kalshi", "subscribing", legs=len(market_tickers))

    # #9462 review: the markets with a ticker on the wire. A market row that
    # exists without an outcome ticker (or gained its winner market after the
    # slate was read) is not among them. #10090: refilled in place by a scope
    # change.
    legged_market_ids = {market_id for market_id, _ in ticker_to_ids.values()}

    # #9418: the slate's live arm, re-read while the socket runs. Same source,
    # same join and same status test as the slate above, so it can only name an
    # event that turned live after the slate was read.
    # #9462 review: read per MARKET, beside the reading the card renders, so
    # an event counts as subscribed only when the leg that feeds its displayed
    # number has a ticker here (`unadmitted_live_events`).
    async def load_unadmitted_live_event_ids():
        async with get_task_session() as session:
            result = await session.execute(
                select(
                    FuturesMarket.event_id,
                    FuturesMarket.id,
                    Event.win_probability_sources["kalshi"],
                )
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source == "kalshi",
                    FuturesMarket.event_id.isnot(None),
                    Event.status == "live",
                )
                .distinct()
            )
            rows = list(result.all())
        # #10090: the same read names the live games the flush writes first.
        live_event_ids.clear()
        live_event_ids.update(row[0] for row in rows)
        # #10090: the same read moves the order books onto the live games.
        await refresh_books()
        return unadmitted_live_events(rows, legged_market_ids)

    def start_watcher():
        # The events this slate tried are held to the timer, as at startup:
        # a scope change re-ran their lookup, so it restarts the baseline.
        return asyncio.create_task(
            watch_for_unadmitted_live_events(
                load_unadmitted_live_event_ids,
                list(event_id_by_market.values()),
                arm="Kalshi",
                started_at=run_started_at,
            ),
            name="kalshi-admission-watch",
        )

    # The game client(s) and admission watcher live across routine refreshes;
    # a changed scope is applied in place (#10090). An admission miss, a policy
    # switch or an ended client still returns to the runner, which rebuilds.
    # #9484: an EMPTY ticker list means "every market, both channels" to
    # `KalshiWebSocket.run`, so an open-only run opens no game socket.
    if market_tickers:
        game_clients.append(start_client(market_tickers, "game"))
        claim_tickers(game_clients[0], frozenset(ticker_to_ids))
    watch_task = start_watcher()
    interrupted = None
    admitted = None
    try:
        next_refresh = time.monotonic() + SUBSCRIPTION_REFRESH_SECONDS
        while True:
            waits = {c.task for c in game_clients}
            if watch_task is not None:
                waits.add(watch_task)
            timeout = max(0.0, next_refresh - time.monotonic())
            if waits:
                done, _ = await asyncio.wait(
                    waits, timeout=timeout, return_when=asyncio.FIRST_COMPLETED,
                )
            else:
                await asyncio.sleep(timeout)
                done = set()
            if watch_task is not None and watch_task in done:
                finished, watch_task = watch_task, None
                if not finished.cancelled() and finished.exception() is None:
                    admitted = finished.result()
                    # A newly live leg need not tear down every working socket.
                    # Reuse the bounded, ACK-gated scope handoff; only keep it
                    # when the same admission read confirms the leg is mapped.
                    # Failed/unchanged/unadmittable scopes retain the old recycle.
                    if not any(c.task.done() for c in game_clients):
                        verdict = await refresh_subscription_scope()
                        if verdict == "applied":
                            try:
                                remaining = await load_unadmitted_live_event_ids()
                            except Exception:
                                logger.warning(
                                    "Kalshi WS: in-place admission unconfirmed; "
                                    "keeping the admission recycle", exc_info=True,
                                )
                            else:
                                if admitted.isdisjoint(remaining):
                                    stats["admission_in_place"] = (
                                        stats.get("admission_in_place", 0) + 1
                                    )
                                    logger.info(
                                        "Kalshi WS: admitted live events in place: %s",
                                        sorted(admitted)[:20],
                                    )
                                    admitted = None
                                    watch_task = start_watcher()
                                    next_refresh = (
                                        time.monotonic() + SUBSCRIPTION_REFRESH_SECONDS
                                    )
                                    continue
                    break
                logger.error(
                    "WS admission watcher failed; the subscription recycles on its timer",
                    exc_info=None if finished.cancelled() else finished.exception(),
                )
            ended = [c.task for c in game_clients if c.task in done]
            if ended:
                ended[0].result()  # a socket error propagates as it always did
                break
            if time.monotonic() < next_refresh:
                continue
            verdict = await refresh_subscription_scope()
            if verdict == "rebuild":
                stats["status"] = "resubscribe"
                stats.setdefault("recycle_reason", "scope")
                break
            if verdict == "applied":
                await refresh_books()
                # #9418: restart the watcher on the slate this run now streams.
                if watch_task is not None:
                    watch_task.cancel()
                    await asyncio.gather(watch_task, return_exceptions=True)
                watch_task = start_watcher()
            next_refresh = time.monotonic() + SUBSCRIPTION_REFRESH_SECONDS
        if admitted:
            stats["status"] = "resubscribe"
            stats["recycle_reason"] = "admission"
            stats["admitted_event_ids"] = sorted(admitted)[:20]
            logger.info(
                "Kalshi WS: %d live event(s) without a mapped leg for their rendered "
                "price, recycling early: %s",
                len(admitted), sorted(admitted)[:20],
            )
    except asyncio.CancelledError:
        # This is a real shutdown, so it
        # must keep travelling: swallowing it would make `run_kalshi_ws.py`
        # sleep and relaunch a consumer the process is trying to stop. The
        # `finally` below still drains the buffer first.
        raise
    finally:
        # Like the old wait_for recycle, stop and join the game/watcher before
        # draining. Repeated cancellation cannot leave callbacks beside a drain.
        # #10090: handoffs and every game connection, retiring ones included.
        # Snapshot first: a cancelled handoff takes its client out of `retiring`.
        every_client = [*game_clients, *open_clients, *retiring]
        lifetime = [*handoff_tasks]
        if watch_task is not None:
            lifetime.append(watch_task)
        lifetime.extend(c.task for c in every_client if c.kind == "game")
        for task in lifetime:
            if not task.done():
                task.cancel()
        while not all(task.done() for task in lifetime):
            try:
                await asyncio.wait(lifetime)
            except asyncio.CancelledError as exc:
                interrupted = exc
        for task in lifetime:
            if not task.cancelled():
                task.exception()
        loops_stop.set()
        flush_task.cancel()
        stats_task.cancel()
        # #9484: cancelled here, awaited only after the drain below, so a
        # second cancellation landing on that await can never skip the drain.
        admission_task.cancel()
        open_tasks = [c.task for c in every_client if c.kind != "game"]
        for task in open_tasks:
            task.cancel()
        # Q491 repair (CERT-654 BLOCK): the last flush has no successor, so it
        # must RETRY rather than requeue into a buffer nobody will read again.
        try:
            await join_flush_then_drain()
        finally:
            # #9462 review: the drain returns once the price BUFFER is empty,
            # but a price it (or the last flush) committed inside the 2 s
            # throttle is still owed its blend stamp. The next run adopts it.
            stats["blend_pending_carried"] = hand_off_pending(blend_refresher)
            stats["open_contract_messages"] = retired_messages["open"] + sum(
                c.sock.stats.get("messages", 0)
                for c in (*open_clients, *retiring) if c.kind != "game"
            )  # a client retired during teardown is already in `retired_messages`
            # #10090: after the drain and hand-off, so the run's last stamps
            # are in the final minute's line.
            with contextlib.suppress(Exception):
                tail_receipts.close_all(
                    "recycle_reset" if stats.get("status") == "resubscribe"
                    else "exit"
                )
            await asyncio.gather(admission_task, *open_tasks, return_exceptions=True)
            # #10657: reaped after the drain like the tasks above — a loop
            # that lost its cancellation must end here, not outlive the run
            # and keep calling into its closed sessions.
            stats["loops_unreaped"] = await reap_stopped_loops(
                "kalshi", (flush_task, stats_task),
            )
        if interrupted is not None:
            raise interrupted

    logger.info("Kalshi WS consumer exiting: %s", stats)
    return stats


async def _run_kalshi_ws_shadow_consumer():
    """#836 Batch 2 (SHADOW): widened lifecycle-only grader that records its
    verdict to Redis (NEVER is_winner). Subscribes to ALL markets' settlement
    lifecycle (not the price `ticker` firehose) so every Kalshi settlement is
    graded in real time — into the shadow store, for the automated comparison.

    Runs ONLY when the `bainluck:ws_shadow_enabled` flag is on (deploy-dark).
    The authoritative `_run_kalshi_ws_consumer` is untouched and keeps owning
    `is_winner`.
    """
    from app.services.kalshi_ws import KalshiWebSocket
    from app.services.ws_shadow import (
        is_ws_shadow_enabled, verdict_from_lifecycle, record_shadow_verdict,
    )

    if not await is_ws_shadow_enabled():
        return {"status": "shadow_disabled"}

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    has_key = os.getenv("KALSHI_RSA_PRIVATE_KEY") or os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not api_key_id or not has_key:
        return {"status": "skipped", "reason": "no_credentials"}

    ws = KalshiWebSocket()
    stats = {"shadow_verdicts": 0, "errors": 0}

    async def handle_lifecycle_shadow(msg: dict):
        parsed = verdict_from_lifecycle(msg)
        if not parsed:
            return
        ticker, is_winner = parsed
        try:
            # SHADOW ONLY — keyed by the settled ticker's external_id; the
            # comparison joins FuturesOutcome.external_id == ticker exactly, so
            # no rsplit / event resolution is needed here.
            await record_shadow_verdict(ticker, is_winner)
            stats["shadow_verdicts"] += 1
        except Exception:
            stats["errors"] += 1

    ws.on_lifecycle = handle_lifecycle_shadow
    # lifecycle-only + all markets: settlement trickle, NOT the price ticker firehose
    try:
        await ws.run(channels=["market_lifecycle_v2"], subscribe_all=True)
    except asyncio.CancelledError:
        raise  # shutdown must stop the runner, not restart it (CERT-491)
    logger.info("Kalshi WS SHADOW consumer exiting: %s", stats)
    return stats
