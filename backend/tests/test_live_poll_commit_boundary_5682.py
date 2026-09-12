"""One deadlock stops costing the whole live beat (#5682).

## the ship

A live match page shows a prediction-market price that is hours old. Measured
on production 2026-09-12 17:17Z, against live events only, comparing each
event's own `win_probability_sources` stamp with the freshest `last_updated` of
its outcome rows: **kalshi 7 of 78 events, polymarket 2 of 19, worst −335 min**
(5 h 35 m). The direction is the tell — the OUTCOME rows were fresh and the
EVENT entry was stale. The fetch reached the market; the write never landed.

## the defect these arms are pointed at

`_poll_live_prediction_market_prices` ran the entire population — ~100 venue
fetches, their 0.3 s rate-limit sleeps, every price update, every snapshot,
every `win_probability_sources` stamp and every pregame pin — inside ONE
transaction with a single `commit()` at the end. So one database error cost the
beat twice:

* everything already priced was rolled back, and
* the session stayed poisoned, so every later statement raised
  `PendingRollbackError` — caught by the per-item handlers, which only appended
  to `stats["errors"]` — until the closing `commit()` raised and took the task
  down with it.

`/api/admin/task-metrics?task=prediction_market_live`, read 17:06Z:
`successes_24h 30 / failures_24h 102 / starts_24h 111` — **92% of starts
thrown**, `last_error` an asyncpg `DeadlockDetectedError ... waits for ShareLock
on transaction -> PendingRollbackError`. Ninety minutes earlier the same
counters read 72/79: it was getting worse, not better.

The repair is Phase 2's discipline (gotcha #13) carried onto the price path: a
commit boundary per item, and — because `rollback()` expires every persistent
instance in the session whatever `expire_on_commit` says (gotcha #6) — every
loop owning IDS rather than rows, with the population re-read after a rollback.

## how the harness discriminates

`_Session` is a FAITHFUL fake of the failure, not a recorder: once a statement
raises, it marks itself aborted and raises on every subsequent `execute` AND on
`commit`, exactly as a Postgres transaction does after a deadlock — and it
clears that state only on `rollback`. That is what makes these arms a
regression gate: run against the pre-repair function, the first three fail on
the aborted session (the tail is never written and the closing commit throws),
not on a bookkeeping assertion.

Verified by mutation rather than assumed — the sweep is recorded in
`artifacts-lane1-271/`: dropping the commit, dropping the rollback, dropping the
re-read, dropping `expunge_all`, pinning `terminal` to "complete", and resolving
markets from a captured list instead of the re-read population each kill an arm
below.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.sql.elements import TextClause

from app.services.kalshi_api import KalshiAPIService
from app.tasks import prediction_market_matching as pmm

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.

#: NEVER a module-level clock in a row's default. CI runs this file eleven
#: minutes into a suite, so an anchor frozen at import is eleven minutes stale
#: by the time the pin arm reads it — which is exactly how that arm passed here
#: and failed in CI (gotcha #44: the anchor must not be a different distance
#: from `now` depending on when the test runs). Every time below is derived
#: from the clock AT CALL TIME, with the offset carrying the meaning.
def _now() -> datetime:
    return datetime.now(timezone.utc)

#: The production error verbatim enough to be classified by the same substring
#: the task uses. A generic `RuntimeError` would pass the "did the pass
#: survive" arms while proving nothing about the deadlock counter.
DEADLOCK = (
    "DeadlockDetectedError: deadlock detected DETAIL: process 42 waits for "
    "ShareLock on transaction 1234; blocked by process 43"
)


class _Aborted(Exception):
    """What every statement raises after an error, until someone rolls back.

    Named for `PendingRollbackError`'s role rather than imported from
    SQLAlchemy: the arms must not depend on the driver's class, only on the
    behaviour — a transaction that refuses further work.
    """


# --------------------------------------------------------------------------
# the rows
# --------------------------------------------------------------------------


class _Outcome:
    def __init__(self, oid: int, market_id: int, external_id: str, name: str):
        self.id = oid
        self.market_id = market_id
        self.external_id = external_id
        self.name = name
        self.rank = 1
        self.current_probability = None
        self.current_american_odds = None
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.probability_change_24h = None
        self.is_winner = None
        self.calibration_probability = None
        self.last_updated = None


class _Market:
    def __init__(self, mid: int, source: str, external_id: str, *, metadata=None):
        self.id = mid
        self.source = source
        self.external_id = external_id
        self.name = f"market {mid}"
        self.market_type = "game_winner"
        self.market_metadata = metadata


class _Event:
    def __init__(self, eid: int, *, commence: Optional[datetime] = None, status="live"):
        self.id = eid
        self.status = status
        self.home_team_name = "Los Angeles R"
        self.away_team_name = "New York G"
        # Far enough out that the pregame-pin loop declines — the lead window
        # is `_PREGAME_MARK_LEAD_MINUTES` (15), so hours out is outside it by
        # any clock — and arms aimed at the fetch loops are therefore not also
        # exercising the pin. The pin has its own arm below, which moves this
        # deliberately, INSIDE the window.
        self.commence_time = commence or (_now() + timedelta(hours=2, minutes=30))


@dataclass
class _Population:
    """What the fake's population read hands back, generation by generation."""

    rows: list
    outcomes: list


# --------------------------------------------------------------------------
# the session: a transaction that behaves like Postgres after an error
# --------------------------------------------------------------------------


def _classify(stmt) -> str:
    if isinstance(stmt, TextClause):
        return "text"
    if isinstance(stmt, Select):
        names = [c.get("name") for c in stmt.column_descriptions]
        if "FuturesMarket" in names:
            return "population"
        if names == ["FuturesOutcome"]:
            return "outcomes"
        return "select:" + ",".join(str(n) for n in names)
    if isinstance(stmt, Update):
        return "update"
    return "insert"


class _Result:
    def __init__(self, rows=(), scalar_value=None):
        self._rows = list(rows)
        self._scalar = scalar_value
        self.rowcount = len(self._rows)

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Answers reads by statement TYPE; aborts like a real transaction.

    `generations` is a list of populations: the first is what the beat loads,
    and each recovery's re-read takes the next one (the last repeats). That is
    how the arms below prove the pass resolves ids against the population it
    has NOW rather than against instances captured before the rollback.
    """

    def __init__(self, generations: list[_Population], *, journal=None, on_execute=None):
        self._generations = generations
        self._gen = 0
        self.journal = journal if journal is not None else []
        self._on_execute = on_execute or (lambda kind, n, stmt: None)
        self._n = 0
        self.aborted = False
        self.reload_should_raise = False
        self.commit_should_raise = False
        self.expunged = 0
        self.added = []

    @property
    def population(self) -> _Population:
        return self._generations[min(self._gen, len(self._generations) - 1)]

    async def execute(self, stmt, params=None):
        kind = _classify(stmt)
        if self.aborted:
            self.journal.append(("refused", kind))
            raise _Aborted("current transaction is aborted, commands ignored")
        self._n += 1
        self.journal.append(("execute", kind))
        exc = self._on_execute(kind, self._n, stmt)
        if exc is not None:
            self.aborted = True
            raise exc
        if kind == "population":
            if self.reload_should_raise and self._gen > 0:
                self.aborted = True
                raise RuntimeError("the re-read could not reach the database")
            return _Result(self.population.rows)
        if kind == "outcomes":
            return _Result(self.population.outcomes)
        return _Result()

    async def commit(self):
        if self.aborted:
            raise _Aborted("this session is in 'prepared' state; no further commands")
        if self.commit_should_raise:
            self.aborted = True
            raise RuntimeError("the commit itself failed")
        self.journal.append(("commit", None))

    async def rollback(self):
        self.aborted = False
        self._gen += 1
        self.journal.append(("rollback", None))

    def expunge_all(self):
        self.expunged += 1
        self.journal.append(("expunge_all", None))

    def add(self, obj):
        self.added.append(obj)


# --------------------------------------------------------------------------
# the venues
# --------------------------------------------------------------------------


def _leg(ticker: str, event_ticker: str, *, bid=0.22, ask=0.23) -> dict:
    """A tight two-sided book in the venue's CURRENT dialect (#3569)."""
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "title": "Los Angeles R wins",
        "yes_sub_title": "Los Angeles R",
        "status": "active",
        "yes_bid_dollars": f"{bid:.4f}",
        "yes_ask_dollars": f"{ask:.4f}",
        "last_price_dollars": f"{(bid + ask) / 2:.4f}",
        "volume_fp": "1000",
    }


class _KalshiService:
    """The venue, answered with RAW dicts through the REAL parser."""

    def __init__(self, payloads: dict, journal: list, raises: dict | None = None):
        self._payloads = payloads
        self._journal = journal
        self._raises = raises or {}
        self._real = KalshiAPIService()

    async def get_markets(self, event_ticker=None, status=None, limit=None):
        self._journal.append(("fetch", event_ticker))
        exc = self._raises.get(event_ticker)
        if exc is not None:
            raise exc
        return list(self._payloads.get(event_ticker, [])), None

    def parse_markets(self, raw):
        return self._real.parse_markets(raw)

    async def close(self):
        return None


class _PolyService:
    def __init__(self, payloads: dict, journal: list, raises: dict | None = None):
        self._payloads = payloads
        self._journal = journal
        self._raises = raises or {}

    async def get_event_by_id(self, external_id):
        self._journal.append(("fetch", external_id))
        exc = self._raises.get(external_id)
        if exc is not None:
            raise exc
        return self._payloads.get(external_id)

    async def close(self):
        return None


# --------------------------------------------------------------------------
# the runner
# --------------------------------------------------------------------------


async def _run(monkeypatch, session, *, kalshi=None, poly=None, blend=None):
    """Run the REAL poll against the fake session and the fake venues."""

    @asynccontextmanager
    async def _fake_session():
        yield session

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(pmm, "get_task_session", _fake_session)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    if kalshi is not None:
        monkeypatch.setattr(
            "app.services.kalshi_api.KalshiAPIService", lambda *a, **kw: kalshi
        )
    if poly is not None:
        monkeypatch.setattr(
            "app.services.polymarket_api.PolymarketAPIService", lambda *a, **kw: poly
        )
    if blend is None:
        # Off by default: these arms are aimed at the fetch loops, and a blend
        # that silently declined would be an invisible reason for a passing
        # arm. `None` from the primary selector is the documented "no market
        # can speak" path, not an error.
        monkeypatch.setattr(pmm, "_select_primary_market", lambda group: None)
    else:
        for name, fn in blend.items():
            monkeypatch.setattr(pmm, name, fn)
    return await pmm._poll_live_prediction_market_prices()


def _kalshi_beat(n: int, *, sources="kalshi") -> _Population:
    rows, outcomes = [], []
    for i in range(1, n + 1):
        market = _Market(i, sources, f"KXNFLGAME-EVT{i}")
        rows.append((market, _Event(100 + i)))
        outcomes.append(_Outcome(1000 + i, i, f"KXNFLGAME-EVT{i}-LAR", "Los Angeles R"))
    return _Population(rows, outcomes)


def _fail_nth(kind_wanted: str, nth: int, exc: Exception):
    """Fail the nth statement OF A KIND, inside the database.

    The deadlock these arms are about happens on a STATEMENT, not on a venue
    call: the venue is reached, the write is what dies. An injection at the
    fetch would leave the fake transaction healthy and every "the pass carried
    on" arm would pass against the pre-repair function — measured, on the first
    draft of this file.
    """
    seen = {"n": 0}

    def _hook(kind, n, stmt):
        if kind == kind_wanted:
            seen["n"] += 1
            if seen["n"] == nth:
                return exc
        return None

    return _hook


def _fetches(journal) -> list:
    return [t for kind, t in journal if kind == "fetch"]


def _kinds(journal) -> list:
    return [kind if kind != "execute" else f"execute:{payload}" for kind, payload in journal]


# --------------------------------------------------------------------------
# 1. the ship: one market's deadlock costs one market
# --------------------------------------------------------------------------


class TestOneDeadlockCostsOneMarket:
    async def test_the_markets_before_the_failure_are_already_committed(self, monkeypatch):
        journal = []
        beat = _kalshi_beat(3)
        session = _Session(
            [beat, beat],
            journal=journal,
            # Market 2's snapshot INSERT deadlocks — the write, not the fetch.
            on_execute=_fail_nth("insert", 2, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        # The pass survived the deadlock at all — before the repair this
        # returned through a raised PendingRollbackError at the closing commit.
        assert stats["session_recoveries"] == 1
        # Market 1's write is durable BEFORE market 2 is even fetched.
        order = _kinds(journal)
        first_commit = order.index("commit")
        second_fetch = [i for i, (k, t) in enumerate(journal)
                        if k == "fetch" and t == "KXNFLGAME-EVT2"][0]
        assert first_commit < second_fetch, (
            "market 1's price was still losable when market 2's fetch began: "
            f"{order}"
        )

    async def test_the_market_after_the_failure_is_still_written_and_committed(
        self, monkeypatch
    ):
        journal = []
        beat = _kalshi_beat(3)
        session = _Session(
            [beat, beat],
            journal=journal,
            on_execute=_fail_nth("insert", 2, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        assert _fetches(journal) == [
            "KXNFLGAME-EVT1", "KXNFLGAME-EVT2", "KXNFLGAME-EVT3",
        ], "the pass stopped at the deadlock instead of carrying on"
        # In-memory state is not the claim — DURABILITY is. After the rollback
        # there must be another insert, and a commit after it; an unpriced
        # market 3 and a market 3 priced into a transaction that never commits
        # look identical on the row object.
        after = _kinds(journal)[_kinds(journal).index("rollback"):]
        assert "execute:insert" in after, (
            f"nothing was written after the deadlock: {after}"
        )
        assert "commit" in after[after.index("execute:insert"):], (
            f"the post-deadlock write was never committed: {after}"
        )
        # Markets 1 and 3. Market 2's in-memory update was rolled back with its
        # snapshot, and a counter that still claimed it would report a price
        # the database does not hold.
        assert stats["kalshi_outcomes_updated"] == 2
        assert stats["futures_snapshots_written"] == 2

    async def test_the_beat_does_not_read_green_when_it_lost_a_market(self, monkeypatch):
        journal = []
        beat = _kalshi_beat(2)
        session = _Session(
            [beat, beat],
            journal=journal,
            on_execute=_fail_nth("insert", 1, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")],
             "KXNFLGAME-EVT2": [_leg("KXNFLGAME-EVT2-LAR", "KXNFLGAME-EVT2")]},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        # "it returned" is not "it worked" (gotcha #53). A beat that rolled a
        # market back is `partial`, which can never read GREEN.
        assert stats["terminal"] == "partial"
        assert stats["deadlocks"] == 1

    async def test_a_clean_beat_earns_complete(self, monkeypatch):
        journal = []
        session = _Session([_kalshi_beat(2)], journal=journal)
        service = _KalshiService(
            {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")],
             "KXNFLGAME-EVT2": [_leg("KXNFLGAME-EVT2-LAR", "KXNFLGAME-EVT2")]},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        assert stats["terminal"] == "complete"
        assert stats["session_recoveries"] == 0
        assert stats["deadlocks"] == 0
        # One boundary per market, plus the closing one. A pass that committed
        # only at the end would satisfy every counter above and none of this.
        assert stats["commits"] == 3

    async def test_a_failure_that_is_not_a_deadlock_is_not_counted_as_one(self, monkeypatch):
        journal = []
        session = _Session([_kalshi_beat(2)], journal=journal)
        service = _KalshiService(
            {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")],
             "KXNFLGAME-EVT2": [_leg("KXNFLGAME-EVT2-LAR", "KXNFLGAME-EVT2")]},
            journal,
            raises={"KXNFLGAME-EVT1": Exception("connection reset by peer")},
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        assert stats["session_recoveries"] == 1
        assert stats["deadlocks"] == 0, (
            "every venue hiccup counted as a deadlock would make the counter "
            "useless for judging whether this repair worked"
        )

    async def test_the_error_names_the_market_without_reading_an_expired_row(
        self, monkeypatch
    ):
        journal = []
        beat = _kalshi_beat(2)
        session = _Session(
            [beat, beat],
            journal=journal,
            on_execute=_fail_nth("insert", 1, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")],
             "KXNFLGAME-EVT2": [_leg("KXNFLGAME-EVT2-LAR", "KXNFLGAME-EVT2")]},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        assert any(e.startswith("kalshi_KXNFLGAME-EVT1:") for e in stats["errors"]), (
            f"the failure is unattributable: {stats['errors']}"
        )
        # ONE error: the deadlocked market. A pass that carries a poisoned
        # session forward reports the same failure once per statement it then
        # cannot run, which is how 102 thrown starts looked like many bugs.
        assert len(stats["errors"]) == 1, stats["errors"]


# --------------------------------------------------------------------------
# 2. a pass owns ids, never rows (gotcha #6)
# --------------------------------------------------------------------------


class TestThePassOwnsIdsNeverRows:
    async def test_the_write_after_a_rollback_lands_on_the_RE_READ_instance(
        self, monkeypatch
    ):
        """The rollback expires the first generation; the pass must not use it.

        Both generations describe the same three markets. Only the second one's
        instances are attached to the session after the rollback, so a pass
        still holding the first generation's objects would write a price into
        rows nothing will ever flush — which is how "we fixed the deadlock"
        becomes "we stopped writing prices" with every counter still green.
        """
        journal = []
        first, second = _kalshi_beat(3), _kalshi_beat(3)
        session = _Session(
            [first, second],
            journal=journal,
            on_execute=_fail_nth("insert", 2, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        await _run(monkeypatch, session, kalshi=service)

        stale = [o for o in first.outcomes if o.market_id == 3][0]
        fresh = [o for o in second.outcomes if o.market_id == 3][0]
        assert fresh.current_probability is not None, (
            "market 3 was priced on the EXPIRED instance from before the "
            "rollback — in production that read raises MissingGreenlet"
        )
        assert stale.current_probability is None

    async def test_the_recovery_re_reads_the_population(self, monkeypatch):
        journal = []
        session = _Session(
            [_kalshi_beat(2), _kalshi_beat(2)],
            journal=journal,
            on_execute=_fail_nth("insert", 1, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")],
             "KXNFLGAME-EVT2": [_leg("KXNFLGAME-EVT2-LAR", "KXNFLGAME-EVT2")]},
            journal,
        )

        await _run(monkeypatch, session, kalshi=service)

        kinds = _kinds(journal)
        assert kinds.count("execute:population") == 2, (
            f"the population was not re-read after the rollback: {kinds}"
        )
        # Implementation assertion, deliberately: a fake session cannot raise
        # MissingGreenlet, so the only way to guard the expunge is to watch for
        # it. Its CONSEQUENCE is the arm above.
        assert session.expunged == 1
        assert kinds.index("rollback") < kinds.index("expunge_all")

    async def test_a_market_that_vanished_from_the_re_read_is_skipped(self, monkeypatch):
        """A row unlinked between the plan and the attempt is not an error."""
        journal = []
        first = _kalshi_beat(3)
        second = _Population(
            [r for r in _kalshi_beat(3).rows if r[0].id != 3],
            [o for o in _kalshi_beat(3).outcomes if o.market_id != 3],
        )
        session = _Session(
            [first, second],
            journal=journal,
            on_execute=_fail_nth("insert", 2, Exception(DEADLOCK)),
        )
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        assert _fetches(journal) == ["KXNFLGAME-EVT1", "KXNFLGAME-EVT2"]
        assert len(stats["errors"]) == 1, (
            f"the vanished market was reported as a failure: {stats['errors']}"
        )


# --------------------------------------------------------------------------
# 3. the same boundary on every writer in the beat
# --------------------------------------------------------------------------


def _poly_event(condition_id: str) -> dict:
    return {
        "markets": [
            {
                "conditionId": condition_id,
                "outcomePrices": '["0.62", "0.38"]',
                "outcomes": '["Yes", "No"]',
                "lastTradePrice": 0.62,
                "bestBid": 0.61,
                "bestAsk": 0.63,
            }
        ]
    }


class TestEveryWriterInTheBeatHasABoundary:
    async def test_polymarket_carries_on_past_one_events_deadlock(self, monkeypatch):
        journal = []
        beat = _Population(
            [(_Market(i, "polymarket", f"poly-evt-{i}"), _Event(200 + i)) for i in (1, 2, 3)],
            [_Outcome(2000 + i, i, f"cond-{i}", "Los Angeles R") for i in (1, 2, 3)],
        )
        session = _Session(
            [beat, beat],
            journal=journal,
            on_execute=_fail_nth("insert", 2, Exception(DEADLOCK)),
        )
        poly = _PolyService(
            {f"poly-evt-{i}": _poly_event(f"cond-{i}") for i in (1, 2, 3)},
            journal,
        )

        stats = await _run(monkeypatch, session, poly=poly)

        assert _fetches(journal) == ["poly-evt-1", "poly-evt-2", "poly-evt-3"]
        third = [o for o in beat.outcomes if o.market_id == 3][0]
        assert third.current_probability == pytest.approx(0.62, abs=0.0001)
        assert stats["session_recoveries"] == 1
        assert stats["outcomes_updated"] == 2

    async def test_the_hero_stamp_carries_on_past_one_events_deadlock(self, monkeypatch):
        """`win_probability_sources` is the statement that deadlocks most.

        The matcher and the WebSocket fast lane write the same event row, so
        this is the one that most needs its own boundary — and it is the one
        whose loss the reader sees, because it IS the hero's number.
        """
        journal = []
        beat = _kalshi_beat(3)
        stamped: list[int] = []

        def _primary(group):
            return group[0] if group else None

        # Built here rather than monkeypatched away: the loop reads
        # `reading.market`, `.outcome`, `.eligibility` and both probabilities,
        # so a stub that omitted one would fail for the wrong reason.
        from app.utils.live_blend import BlendReading

        def _compute(group, home, away):
            entry = group[0]
            outcome = entry.outcomes[0] if entry.outcomes else None
            if outcome is None:
                return None
            return BlendReading(
                home_probability=0.61,
                market=entry.market,
                outcome=outcome,
                yes_probability=0.61,
                devigged=False,
                eligibility=None,
            )

        async def _inversion(session_, event_id, home_prob, source):
            return home_prob

        async def _snapshot(session_, **kwargs):
            stamped.append(kwargs["event_id"])
            return object(), True

        monkeypatch.setattr(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot", _snapshot
        )
        monkeypatch.setattr(pmm, "_check_and_fix_inversion", _inversion)

        def _on_execute(kind, n, stmt):
            # The SECOND event's `win_probability_sources` update deadlocks.
            if kind == "update" and len([k for k, _ in journal if k == "execute"]) > 0:
                if stamped[-1:] == [102]:
                    return Exception(DEADLOCK)
            return None

        session = _Session([beat, beat], journal=journal, on_execute=_on_execute)
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        stats = await _run(
            monkeypatch,
            session,
            kalshi=service,
            blend={
                "_select_primary_market": _primary,
                "_compute_source_home_probability": _compute,
            },
        )

        assert stamped == [101, 102, 103], (
            f"the blend stopped at the deadlocked event: {stamped}"
        )
        assert stats["session_recoveries"] == 1
        assert any(e.startswith("snapshot_102_kalshi:") for e in stats["errors"]), (
            f"the failed event is unattributable: {stats['errors']}"
        )
        # Durability, not just continuation: event 101's hero number must be
        # committed before event 102's write is attempted, or the deadlock two
        # events later still un-writes it. (Mutation M3: without this the
        # missing boundary in the blend loop survived every other arm.)
        kinds = _kinds(journal)
        updates = [i for i, k in enumerate(kinds) if k == "execute:update"]
        assert len(updates) >= 2, kinds
        assert "commit" in kinds[updates[0]:updates[1]], (
            f"event 101's stamp was still losable when 102's write began: {kinds}"
        )

    async def test_the_pregame_pin_carries_on_past_one_markets_deadlock(self, monkeypatch):
        journal = []
        beat = _kalshi_beat(3)
        from app.tasks.prediction_market_matching import _PREGAME_MARK_LEAD_MINUTES

        for market, event in beat.rows:
            # Inside the pin's lead window and not yet started, so the pin is
            # due for every market in the beat. Both bounds are live: the task
            # skips a market whose commence is beyond `now + LEAD`, and skips
            # one whose commence has PASSED by the time the write is reached.
            # Half the window, read off the production constant, sits clear of
            # both — and is re-derived here rather than frozen at import.
            event.commence_time = _now() + timedelta(
                minutes=_PREGAME_MARK_LEAD_MINUTES / 2
            )
        session = _Session([beat, beat], journal=journal)
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        # Precondition, so a future failure reads "the anchor went stale" and
        # not "the loop stopped": every seeded commence is inside the window
        # on BOTH sides at the moment this arm runs.
        for _m, _e in beat.rows:
            _gap_min = (_e.commence_time - _now()).total_seconds() / 60
            assert 0 < _gap_min < _PREGAME_MARK_LEAD_MINUTES, (
                f"the seeded commence is {_gap_min:.1f} min away, outside the "
                f"{_PREGAME_MARK_LEAD_MINUTES} min pin window — this arm would "
                "fail for the wrong reason"
            )

        pins: list[int] = []

        def _on_execute(kind, n, stmt):
            if kind == "text":
                pins.append(len(pins) + 1)
                if len(pins) == 2:
                    return Exception(DEADLOCK)
            return None

        session._on_execute = _on_execute

        stats = await _run(monkeypatch, session, kalshi=service)

        assert len(pins) == 3, (
            f"the pin loop stopped at the deadlocked market: {pins}"
        )
        assert stats["pregame_marks_written"] == 2
        assert stats["session_recoveries"] == 1


# --------------------------------------------------------------------------
# 4. the failure paths of the repair itself
# --------------------------------------------------------------------------


class TestTheRepairFailsClosed:
    async def test_a_re_read_that_itself_fails_ends_the_beat_quietly(self, monkeypatch):
        """Keeping what is already committed beats reporting a thrown beat."""
        journal = []
        beat = _kalshi_beat(3)
        session = _Session(
            [beat, beat],
            journal=journal,
            on_execute=_fail_nth("insert", 2, Exception(DEADLOCK)),
        )
        session.reload_should_raise = True
        service = _KalshiService(
            {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
             for i in (1, 2, 3)},
            journal,
        )

        stats = await _run(monkeypatch, session, kalshi=service)

        assert stats["kalshi_outcomes_updated"] == 1, (
            "the beat kept working against a population it could not read"
        )
        assert any(e.startswith("reload_after_kalshi_") for e in stats["errors"])
        assert stats["terminal"] == "partial"

    async def test_a_closing_commit_that_fails_is_not_a_thrown_beat(self, monkeypatch):
        journal = []
        session = _Session([_kalshi_beat(1), _kalshi_beat(1)], journal=journal)
        service = _KalshiService(
            {"KXNFLGAME-EVT1": [_leg("KXNFLGAME-EVT1-LAR", "KXNFLGAME-EVT1")]},
            journal,
        )

        async def _run_and_break():
            # Arm the closing commit only: the per-market boundary must land
            # first, or this arm would be proving the wrong commit.
            session.commit_should_raise = False
            original = session.commit

            calls = {"n": 0}

            async def _commit():
                calls["n"] += 1
                if calls["n"] == 2:
                    session.aborted = True
                    raise RuntimeError("the closing commit failed")
                await original()

            session.commit = _commit
            return await _run(monkeypatch, session, kalshi=service)

        stats = await _run_and_break()

        assert stats["terminal"] == "partial"
        assert any(e.startswith("final_commit:") for e in stats["errors"])

    async def test_an_empty_beat_is_complete_not_a_failure(self, monkeypatch):
        session = _Session([_Population([], [])])

        stats = await _run(monkeypatch, session)

        assert stats["terminal"] == "complete"
        assert stats["linked_markets"] == 0
