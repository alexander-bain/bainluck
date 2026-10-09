"""A finished Kalshi event holds no row lock across the next event's venue call (#10732). Real Postgres.

## the defect

`_poll_kalshi_markets` writes each event inside its own SAVEPOINT (#9460) and
releases it when the event finishes. Releasing a savepoint releases no lock: the
OUTER transaction committed only every 200 events, so every row a finished event
wrote stayed locked while the loop awaited the next event's series metadata, a
venue round trip. The live socket's price UPDATE on those rows waited out its
lock budget and rolled back. Root reproduced exactly that on real Postgres with
two events (CATALOG-ROOT-ACCEPTANCE-91688): baseline LOCK_TIMEOUT_ROLLED_BACK at
the metadata seam, candidate committed before the provider returned.

## the seam

`_resolve_series_tag_result` is the first await of every event and the one that
can go to the venue. Each arm wraps it and, at that moment, asks the database
from a SECOND connection: is the previous event committed (visible), and can a
plain price UPDATE take its rows (`FOR NO KEY UPDATE NOWAIT`, the lock an UPDATE
takes)? Only a separate connection can answer either question. A savepoint
release, a counter or the poll's own session state cannot.

## the arms

* ship: at each later seam, every earlier event is committed with its outcome
  and snapshot, and (on a second beat over existing rows) none of its rows is
  locked. RED before #10732.
* failed COMMIT: rolled back before the next venue call, reported once in
  `errors`, never replayed. The earlier event stays committed, the failed one
  is absent, the beat continues.
* non-SQL failure (#9460's keep-what-it-wrote policy): its partial rows are kept
  AND released before the next venue call. If THAT commit is refused, the beat
  ends through the top-level error; no further event starts on the session.
* a SQL failure with no savepoint rolls the whole transaction back, which can no
  longer take an earlier, finished event with it.
* interruptions at the new boundaries: the deadline still stops before the next
  venue call; a soft limit at either new commit keeps #150's flag-commit-stop;
  cancellation propagates through the REAL `get_task_session`, leaves the
  finished event committed, the unfinished one absent, and no transaction open.

A lost COMMIT reply (server committed, client saw an error) is not modelled: the
injected refusal never reaches the server, so this file proves control flow, not
what an ambiguous transport failure leaves behind. That stays UNKNOWN.

Rig: #9460's single-leg Overtime events and seams (network, `get_task_session`,
Redis raised). CI job `search-recall`.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from contextlib import ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError

from tests.integration.test_kalshi_poll_survives_one_failed_event_real_postgres_9460 import (
    _ot_event,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10732 gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

#: One series, so the loop keeps list order (#9460's reasoning).
_A = "KXNCAAFOT-26OCT03VANUGA"
_B = "KXNCAAFOT-26OCT03CINARIZ"
_C = "KXNCAAFOT-26OCT03OSUMICH"


def _events():
    return [
        _ot_event(_A, "Vanderbilt vs Georgia: Overtime"),
        _ot_event(_B, "Cincinnati vs Arizona: Overtime"),
        _ot_event(_C, "Ohio State vs Michigan: Overtime"),
    ]


_LOCK_NOT_AVAILABLE = "55P03"


async def _observe(observer, ticker):
    """(committed, lockable) for one event, read from a separate connection.

    ``committed`` is ``None`` when the market is not visible, else
    ``(outcomes, snapshots)``. ``lockable`` is whether a plain price UPDATE could
    take its market and outcome rows right now.
    """
    async with observer.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM futures_outcomes o "
                    "        WHERE o.market_id = m.id), "
                    "       (SELECT count(*) FROM futures_odds_snapshots s "
                    "        JOIN futures_outcomes o ON o.id = s.outcome_id "
                    "        WHERE o.market_id = m.id) "
                    "FROM futures_markets m "
                    "WHERE m.source = 'kalshi' AND m.external_id = :t"
                ),
                {"t": ticker},
            )
        ).first()
        committed = None if row is None else (row[0], row[1])
        try:
            await conn.execute(
                text(
                    "SELECT o.id FROM futures_markets m "
                    "LEFT JOIN futures_outcomes o ON o.market_id = m.id "
                    "WHERE m.source = 'kalshi' AND m.external_id = :t "
                    "FOR NO KEY UPDATE OF m NOWAIT"
                ),
                {"t": ticker},
            )
            await conn.execute(
                text(
                    "SELECT o.id FROM futures_outcomes o "
                    "JOIN futures_markets m ON m.id = o.market_id "
                    "WHERE m.source = 'kalshi' AND m.external_id = :t "
                    "FOR NO KEY UPDATE OF o NOWAIT"
                ),
                {"t": ticker},
            )
            lockable = True
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) != _LOCK_NOT_AVAILABLE:
                raise
            lockable = False
    return committed, lockable


class _Rig:
    """The poll's seams, and what the database said at each venue call."""

    def __init__(self, observer):
        self.observer = observer
        self.session = None
        self.seen: list[str] = []
        self.current: str | None = None
        #: ticker → {earlier ticker → (committed, lockable)} at its venue call
        self.at_seam: dict[str, dict] = {}
        #: ticker → whether the poll's session had a transaction open then
        self.open_txn_at_seam: dict[str, bool] = {}
        self.on_seam = None
        self.on_rerank = None
        self.on_commit = None
        self.service = None

    async def seam(self, real, service, event_ticker):
        self.current = event_ticker
        self.at_seam[event_ticker] = {
            t: await _observe(self.observer, t) for t in self.seen
        }
        if self.session is not None:
            self.open_txn_at_seam[event_ticker] = self.session.in_transaction()
        self.seen.append(event_ticker)
        if self.on_seam is not None:
            self.on_seam(event_ticker)
        return await real(service, event_ticker)

    def rerank(self, real, market_id):
        if self.on_rerank is not None:
            self.on_rerank(self.current)
        return real(market_id)

    async def run(self, events, *, session=None, real_task_session=False):
        """The REAL `_poll_kalshi_markets`; returns its stats.

        ``session`` is lent through #9460's `get_task_session` seam, with its
        ``commit`` wrapped so an arm can refuse one. ``real_task_session`` runs
        the production context manager against the gate's database instead.
        """
        import app.tasks.kalshi as kalshi_mod

        service = MagicMock()
        service.get_all_events = AsyncMock(return_value=events)
        service.close = AsyncMock()
        self.service = service
        real_resolve = kalshi_mod._resolve_series_tag_result
        real_rerank = kalshi_mod.rerank_market_field_stmt

        async def _seam(svc, event_ticker):
            return await self.seam(real_resolve, svc, event_ticker)

        with ExitStack() as es:
            es.enter_context(
                patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
            )
            es.enter_context(
                patch("app.tasks.kalshi._resolve_series_tag_result", _seam)
            )
            es.enter_context(
                patch(
                    "app.tasks.kalshi.rerank_market_field_stmt",
                    lambda market_id: self.rerank(real_rerank, market_id),
                )
            )
            es.enter_context(
                patch(
                    "app.tasks.redis_state.get_redis_client",
                    side_effect=RuntimeError("no Redis in this gate"),
                )
            )
            es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
            if real_task_session:
                es.enter_context(patch("app.tasks.base.DATABASE_URL", DB_URL))
            else:
                self.session = session
                real_commit = session.commit

                async def _commit():
                    if self.on_commit is not None:
                        self.on_commit(self.current)
                    await real_commit()

                @asynccontextmanager
                async def _session_cm(**_budget):
                    yield session

                es.enter_context(patch.object(session, "commit", _commit))
                es.enter_context(
                    patch("app.tasks.kalshi.get_task_session", _session_cm)
                )
            return await kalshi_mod._poll_kalshi_markets()


def _once(exc, when):
    """A hook that raises ``exc`` the first time it is called for ``when``."""
    fired = []

    def hook(ticker):
        if ticker == when and not fired:
            fired.append(ticker)
            raise exc

    hook.fired = fired
    return hook


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def rig(pg_session):
    from sqlalchemy.ext.asyncio import create_async_engine

    observer = create_async_engine(DB_URL, isolation_level="AUTOCOMMIT")
    yield _Rig(observer)
    await observer.dispose()


async def _seed(pg_session):
    """One clean beat, so the next beat UPDATEs existing rows (and locks them)."""
    seeder = _Rig(None)
    seeder.at_seam = {}

    async def _no_observe(real, service, event_ticker):
        return await real(service, event_ticker)

    seeder.seam = _no_observe
    stats = await seeder.run(_events(), session=pg_session)
    assert stats["errors"] == [], stats["errors"]
    await pg_session.commit()


async def _final(rig, ticker):
    return (await _observe(rig.observer, ticker))[0]


class TestAFinishedEventIsReleasedBeforeTheNextVenueCall:
    async def test_each_finished_event_is_committed_whole_before_the_next_call(
        self, pg_session, rig
    ):
        stats = await rig.run(_events(), session=pg_session)

        assert stats["errors"] == [], stats["errors"]
        assert rig.seen == [_A, _B, _C], rig.seen
        for later, earlier in ((_B, [_A]), (_C, [_A, _B])):
            for t in earlier:
                committed, _ = rig.at_seam[later][t]
                assert committed is not None and committed[0] == 1 and committed[1] >= 1, (
                    f"at {later}'s venue call, {t} was {committed} from another "
                    "connection: a finished event must be committed with its "
                    "outcome and snapshot BEFORE the next event's provider IO"
                )
            assert rig.open_txn_at_seam[later] is False, (
                f"the poll's session had a transaction open at {later}'s venue call"
            )

    async def test_no_row_of_a_finished_event_is_locked_during_the_next_call(
        self, pg_session, rig
    ):
        """The production shape: a beat over EXISTING rows, a price UPDATE waiting."""
        await _seed(pg_session)
        stats = await rig.run(_events(), session=pg_session)

        assert stats["errors"] == [], stats["errors"]
        assert sorted(rig.seen) == sorted([_A, _B, _C]), rig.seen
        for i, later in enumerate(rig.seen[1:], start=1):
            for t in rig.seen[:i]:
                committed, lockable = rig.at_seam[later][t]
                assert committed is not None and lockable, (
                    f"at {later}'s venue call, {t}'s rows were "
                    f"{'locked' if not lockable else 'missing'}: a live price "
                    "UPDATE on them would wait out its lock budget (#10732)"
                )


class TestFailuresAtTheNewBoundary:
    async def test_a_refused_commit_is_rolled_back_reported_and_not_replayed(
        self, pg_session, rig
    ):
        refusal = OperationalError(
            "COMMIT", None, Exception("injected: commit refused")
        )
        rig.on_commit = _once(refusal, _B)
        stats = await rig.run(_events(), session=pg_session)

        assert rig.on_commit.fired == [_B], "the refusal never fired: no commit ran in B"
        assert len(stats["errors"]) == 1 and stats["errors"][0].startswith(_B), (
            stats["errors"]
        )
        assert rig.seen == [_A, _B, _C], (
            f"venue calls {rig.seen}: B must be attempted exactly once (no "
            "replay) and the beat must go on to C"
        )
        at_c = rig.at_seam[_C]
        assert at_c[_A][0] is not None and at_c[_A][1], at_c
        assert at_c[_B][0] is None, (
            f"B read {at_c[_B][0]} at C's call: a refused commit must never "
            "leave the event looking durable"
        )
        assert rig.open_txn_at_seam[_C] is False, (
            "the rollback had not finished before the next event's provider IO"
        )
        assert await _final(rig, _A) is not None
        assert await _final(rig, _B) is None
        assert await _final(rig, _C) is not None

    async def test_a_non_sql_failure_keeps_what_it_wrote_and_commits_it(
        self, pg_session, rig
    ):
        """#9460's policy: a non-SQL failure keeps its partial rows."""
        rig.on_rerank = _once(ValueError("injected after the event's writes"), _B)
        stats = await rig.run(_events(), session=pg_session)

        assert rig.on_rerank.fired == [_B]
        assert len(stats["errors"]) == 1 and stats["errors"][0].startswith(_B)
        assert rig.seen == [_A, _B, _C], rig.seen
        committed, _ = rig.at_seam[_C][_B]
        assert committed is not None and committed[0] == 1, (
            f"B read {committed} at C's call: the market and outcome B wrote "
            "before failing must be kept (#9460) and committed before C's IO"
        )
        assert rig.open_txn_at_seam[_C] is False

    async def test_a_non_sql_failures_rows_are_not_locked_during_the_next_call(
        self, pg_session, rig
    ):
        await _seed(pg_session)
        rig.on_rerank = _once(ValueError("injected after the event's writes"), _B)
        await rig.run(_events(), session=pg_session)

        assert rig.on_rerank.fired == [_B]
        after_b = rig.seen[rig.seen.index(_B) + 1 :]
        assert after_b, f"B was the last event ({rig.seen}); nothing to observe"
        _, lockable = rig.at_seam[after_b[0]][_B]
        assert lockable, (
            "the failed event's kept rows were still locked at the next venue "
            "call: the error path bypassed the event commit (#10732)"
        )

    async def test_a_refused_error_tail_commit_ends_the_beat(self, pg_session, rig):
        """The session is not trusted for another event after this commit fails."""
        rig.on_rerank = _once(ValueError("injected after the event's writes"), _B)
        rig.on_commit = _once(
            OperationalError("COMMIT", None, Exception("injected: commit refused")),
            _B,
        )
        stats = await rig.run(_events(), session=pg_session)

        assert rig.on_rerank.fired == [_B] and rig.on_commit.fired == [_B]
        assert rig.seen == [_A, _B], (
            f"venue calls {rig.seen}: no event may start on a session whose "
            "commit just failed"
        )
        assert stats["errors"][0].startswith(_B), stats["errors"]
        assert any(e.startswith("Top-level error") for e in stats["errors"]), (
            stats["errors"]
        )
        assert await _final(rig, _A) is not None
        assert await _final(rig, _B) is None

    async def test_a_full_rollback_cannot_erase_an_event_already_finished(
        self, pg_session, rig
    ):
        """A SQL failure before B's savepoint rolls back the whole transaction."""
        rig.on_seam = _once(
            OperationalError("SELECT", None, Exception("injected before any write")),
            _B,
        )
        stats = await rig.run(_events(), session=pg_session)

        assert len(stats["errors"]) == 1 and stats["errors"][0].startswith(_B)
        assert await _final(rig, _A) is not None, (
            "A finished before B failed, and B's full rollback erased it"
        )
        assert await _final(rig, _B) is None
        assert await _final(rig, _C) is not None


class _FakeClock(types.ModuleType):
    """`time` with a `monotonic` that can jump; everything else is the real one."""

    def __init__(self):
        super().__init__("time")
        self._real = sys.modules["time"]
        self.offset = 0.0

    def monotonic(self):
        return self._real.monotonic() + self.offset

    def __getattr__(self, name):
        return getattr(self._real, name)


class TestInterruptionsAtTheNewBoundary:
    async def test_the_deadline_still_stops_before_the_next_venue_call(
        self, pg_session, rig
    ):
        clock = _FakeClock()

        def _expire(ticker):
            if ticker == _A:
                clock.offset = 1e6

        rig.on_rerank = _expire
        # The poll does a function-local `import time`; only that lookup sees
        # this. asyncio bound the real module long ago.
        with patch.dict(sys.modules, {"time": clock}):
            stats = await rig.run(_events(), session=pg_session)

        assert stats.get("deadline_hit") is True, stats
        assert rig.seen == [_A], f"venue calls after the deadline: {rig.seen}"
        assert stats["errors"] == [], stats["errors"]
        assert await _final(rig, _A) is not None
        assert await _final(rig, _B) is None

    async def test_a_soft_limit_at_the_event_commit_commits_and_stops(
        self, pg_session, rig
    ):
        rig.on_commit = _once(SoftTimeLimitExceeded(), _B)
        stats = await rig.run(_events(), session=pg_session)

        assert rig.on_commit.fired == [_B]
        assert stats.get("soft_limit_hit") is True, stats
        assert rig.seen == [_A, _B], f"venue calls after the soft limit: {rig.seen}"
        assert stats["errors"] == [], stats["errors"]
        assert await _final(rig, _A) is not None
        # #150's handler commits partial progress on its way out; B was whole.
        assert await _final(rig, _B) is not None
        assert await _final(rig, _C) is None

    async def test_a_soft_limit_at_the_error_tail_commit_commits_and_stops(
        self, pg_session, rig
    ):
        rig.on_rerank = _once(ValueError("injected after the event's writes"), _B)
        rig.on_commit = _once(SoftTimeLimitExceeded(), _B)
        stats = await rig.run(_events(), session=pg_session)

        assert rig.on_rerank.fired == [_B] and rig.on_commit.fired == [_B]
        assert stats.get("soft_limit_hit") is True, stats
        assert rig.seen == [_A, _B], f"venue calls after the soft limit: {rig.seen}"
        assert len(stats["errors"]) == 1 and stats["errors"][0].startswith(_B)
        assert not any(e.startswith("Top-level") for e in stats["errors"])
        assert await _final(rig, _A) is not None
        # The same flag-commit-stop as #150's handler: B's kept rows land.
        assert await _final(rig, _B) is not None
        assert await _final(rig, _C) is None

    async def test_cancellation_propagates_and_leaves_only_finished_events(
        self, pg_session, rig
    ):
        """Through the PRODUCTION `get_task_session`, not #9460's lent session."""
        rig.on_rerank = _once(asyncio.CancelledError(), _B)
        with pytest.raises(asyncio.CancelledError):
            await rig.run(_events(), real_task_session=True)

        assert rig.on_rerank.fired == [_B]
        assert rig.seen == [_A, _B], f"venue calls after cancellation: {rig.seen}"
        rig.service.close.assert_awaited()
        assert await _final(rig, _A) is not None, "A was committed before B began"
        assert await _final(rig, _B) is None, (
            "B was cancelled mid-write and must not have been committed"
        )
        async with rig.observer.connect() as conn:
            open_txns = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND pid <> pg_backend_pid() "
                        "AND state LIKE 'idle in transaction%'"
                    )
                )
            ).scalar_one()
        assert open_txns == 0, f"{open_txns} transaction(s) left open after cancel"
