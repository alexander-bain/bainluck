"""CAL-P086A item 2 — `status='resolved'` requires a winner or a NAMED reason.

`C-WINNER-WRITER-1` (codex, 2026-08-21) verdict BLOCK, finding [P0]: "Two live
producers declare resolution without proving a winner."

    update(FuturesMarket).where(
        FuturesMarket.status == "open",
        FuturesMarket.resolution_date < now,
    ).values(status="resolved")

    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)

`status='resolved'` is the calibration census DENOMINATOR and the gate into
every winner backfill, and neither producer required a venue result, a terminal
price, exactly one winner, or an explicit void. Because the outcome insert omits
`is_winner` and the model default is a non-null `False`, an ungraded field does
not read as ungraded — it reads as an all-loser field. Codex's executable
specimen: a closed Polymarket event with nonterminal prices `[0.60, 0.40]`
driven through the real `_sync_polymarket_resolved_status` produced
`markets_resolved: 1`, `outcomes_updated: 0`, one commit. 305,660 markets are
missing a winner and every task that made them reported success.

This is gotcha #53 with the state machine as the API: "resolved with a winner"
and "resolved because the clock passed" are DIFFERENT FACTS that were writing
the same byte. The gate does not forbid the second one — it forbids writing it
*silently*. A resolved market now carries, in `market_metadata.resolution_gate`,
either the winner proof or one of an ENUMERATED set of reasons. "No winner
available" becomes a recorded fact rather than an absence, and the calibration
population builder can finally tell the two apart with a query.

Deliberately NOT done here, and flagged for Alex instead: codex's stronger
fix-sketch, "stop the generic clock task from resolving prediction-market
sources". That is a coverage change to a live producer during a deploy freeze,
and it is a ruling, not a repair. The gate makes the class visible and countable
first; whether to stop writing it is the next decision, now takeable on numbers.

These tests EXECUTE both producers (gotcha #152 — a source-string assertion
proves the text, not the behaviour; codex's coverage note records that the three
existing settlement-sync tests do exactly that and never reach this boundary).
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

import app.tasks.futures as futures_mod
import app.tasks.polymarket as poly_mod
import app.tasks.redis_state as redis_state
import app.services.polymarket_api as poly_api_mod

from app.utils.resolved_write_gate import (
    ALLOWED_REASONS,
    PROOF_NAMED_REASON,
    PROOF_WINNER,
    REASON_CLOSED_WITHOUT_TERMINAL_PRICE,
    REASON_RESOLUTION_DATE_ELAPSED,
    GATE_KEY,
    classify_resolved_write,
    gate_stamp,
)


# ---------------------------------------------------------------------------
# The pure gate
# ---------------------------------------------------------------------------


class TestClassifyResolvedWrite:
    def test_a_winner_permits_the_write(self):
        v = classify_resolved_write(has_winner_proof=True)
        assert v.permitted is True
        assert v.proof_kind == PROOF_WINNER

    def test_a_named_reason_permits_the_write(self):
        v = classify_resolved_write(
            has_winner_proof=False, named_reason=REASON_RESOLUTION_DATE_ELAPSED
        )
        assert v.permitted is True
        assert v.proof_kind == PROOF_NAMED_REASON
        assert v.reason == REASON_RESOLUTION_DATE_ELAPSED

    def test_neither_proof_nor_reason_is_refused(self):
        # The defect itself: a bare state transition, asserting nothing.
        v = classify_resolved_write(has_winner_proof=False)
        assert v.permitted is False
        assert v.reason is None

    def test_an_unenumerated_reason_is_refused(self):
        """The escape hatch must not become a rubber stamp.

        If any string counted, the gate would be satisfied by `reason="ok"` and
        would measure nothing. A reason is only NAMED if the enumeration names
        it — that is what makes the resulting population queryable.
        """
        v = classify_resolved_write(
            has_winner_proof=False, named_reason="because the task said so"
        )
        assert v.permitted is False

    def test_a_blank_reason_is_not_a_reason(self):
        for blank in (None, "", "   "):
            assert (
                classify_resolved_write(
                    has_winner_proof=False, named_reason=blank
                ).permitted
                is False
            ), blank

    def test_winner_proof_outranks_a_reason(self):
        v = classify_resolved_write(
            has_winner_proof=True, named_reason=REASON_RESOLUTION_DATE_ELAPSED
        )
        assert v.proof_kind == PROOF_WINNER

    def test_every_allowed_reason_is_accepted(self):
        # A constant exported but missing from the allowlist would refuse at
        # runtime inside a producer, i.e. exactly where it is hardest to see.
        assert REASON_RESOLUTION_DATE_ELAPSED in ALLOWED_REASONS
        assert REASON_CLOSED_WITHOUT_TERMINAL_PRICE in ALLOWED_REASONS
        for reason in ALLOWED_REASONS:
            assert classify_resolved_write(
                has_winner_proof=False, named_reason=reason
            ).permitted is True, reason


class TestGateStamp:
    def test_the_stamp_records_the_reason_and_its_writer(self):
        stamp = gate_stamp(reason=REASON_RESOLUTION_DATE_ELAPSED, task="t")
        assert GATE_KEY in stamp
        assert stamp[GATE_KEY]["reason"] == REASON_RESOLUTION_DATE_ELAPSED
        assert stamp[GATE_KEY]["task"] == "t"
        assert stamp[GATE_KEY]["proof_kind"] == PROOF_NAMED_REASON

    def test_the_stamp_is_json_serialisable(self):
        # It is written into a JSONB column through a bind param.
        json.dumps(gate_stamp(reason=REASON_RESOLUTION_DATE_ELAPSED, task="t"))

    def test_a_winner_stamp_names_the_winner_proof(self):
        stamp = gate_stamp(proof_kind=PROOF_WINNER, task="t")
        assert stamp[GATE_KEY]["proof_kind"] == PROOF_WINNER

    def test_an_unenumerated_reason_cannot_be_stamped(self):
        with pytest.raises(ValueError):
            gate_stamp(reason="whatever", task="t")


# ---------------------------------------------------------------------------
# Producer 1 — the generic clock task (futures.py)
# ---------------------------------------------------------------------------


class _Recorder:
    """Records SQL plus its binds.

    A SQLAlchemy Core `update()` carries its values as internal bind params, so
    `session.execute(stmt)` is called with `params=None` and the interesting
    content is only reachable by compiling. Reading the raw `params` argument
    alone would make a Core statement look empty — and would have let this test
    pass against a statement that stamped nothing at all.
    """

    def __init__(self):
        self.statements = []

    def record(self, stmt, params=None):
        binds = dict(params or {})
        try:
            compiled = stmt.compile()
            binds.update(compiled.params or {})
        except Exception:
            pass
        self.statements.append((str(stmt), binds))


def _clock_session(monkeypatch, rec, rowcount=3):
    session = AsyncMock()

    async def _execute(stmt, params=None):
        rec.record(stmt, params)
        return MagicMock(rowcount=rowcount)

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(futures_mod, "get_task_session", lambda: _CM())
    return session


@pytest.mark.asyncio
class TestClockTaskRecordsItsReason:
    async def test_the_clock_resolve_stamps_a_named_reason(self, monkeypatch):
        rec = _Recorder()
        _clock_session(monkeypatch, rec)

        stats = await futures_mod._mark_resolved_impl()

        assert stats["marked_resolved"] == 3, stats
        sql = " ".join(s for s, _ in rec.statements)
        assert "market_metadata" in sql, (
            "the clock task set status='resolved' without recording WHY — "
            f"statements={rec.statements}"
        )

    async def test_the_reason_it_records_is_the_enumerated_one(self, monkeypatch):
        rec = _Recorder()
        _clock_session(monkeypatch, rec)

        await futures_mod._mark_resolved_impl()

        blob = json.dumps([p for _, p in rec.statements], default=str)
        assert REASON_RESOLUTION_DATE_ELAPSED in blob, rec.statements

    async def test_the_run_reports_the_reason_it_wrote_under(self, monkeypatch):
        """A number in the log is the only thing anyone will ever read."""
        rec = _Recorder()
        _clock_session(monkeypatch, rec)

        stats = await futures_mod._mark_resolved_impl()

        assert stats["resolution_gate_reason"] == REASON_RESOLUTION_DATE_ELAPSED
        assert stats["marked_resolved_without_winner_proof"] == 3, stats


# ---------------------------------------------------------------------------
# Producer 2 — the Polymarket closed-status sync (codex's specimen)
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, key):
        self.store.pop(key, None)
        return 1


def _poly_harness(monkeypatch, events_pages, rec, open_count=5):
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: _FakeRedis())

    class _Scalar:
        def __init__(self, v):
            self._v = v

        def scalar(self):
            return self._v

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "COUNT(*)" in sql:
            return _Scalar(open_count)
        rec.record(sql, params)
        return MagicMock(rowcount=1)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(poly_mod, "get_task_session", lambda: _CM())

    pages = list(events_pages)

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_events(self, **kw):
            return pages.pop(0) if pages else []

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)
    return session


NONTERMINAL_EVENT = [
    {
        "id": "ev1",
        "markets": [
            {"conditionId": "0xdeadbeef", "outcomePrices": '["0.60", "0.40"]'}
        ],
    }
]

TERMINAL_EVENT = [
    {
        "id": "ev2",
        "markets": [
            {"conditionId": "0xfeedface", "outcomePrices": '["0.99", "0.01"]'}
        ],
    }
]


@pytest.mark.asyncio
class TestClosedSyncCannotResolveSilently:
    async def test_a_nonterminal_close_records_that_it_has_no_winner(
        self, monkeypatch
    ):
        """Codex's specimen, and the regression they asked for: a closed,
        0.60/0.40, eventless PM market must not end as `resolved` + zero winner
        + zero explanation."""
        rec = _Recorder()
        _poly_harness(monkeypatch, [NONTERMINAL_EVENT], rec)

        await poly_mod._sync_polymarket_resolved_status()

        resolve_stmts = [
            (s, p)
            for s, p in rec.statements
            if "UPDATE futures_markets" in s and "status = 'resolved'" in s
        ]
        assert resolve_stmts, rec.statements
        blob = json.dumps([p for _, p in resolve_stmts], default=str)
        assert REASON_CLOSED_WITHOUT_TERMINAL_PRICE in blob, (
            "a market with a 0.60/0.40 envelope was marked resolved with no "
            f"recorded reason; params={[p for _, p in resolve_stmts]}"
        )

    async def test_the_gate_stamp_reaches_the_metadata_column(self, monkeypatch):
        rec = _Recorder()
        _poly_harness(monkeypatch, [NONTERMINAL_EVENT], rec)

        await poly_mod._sync_polymarket_resolved_status()

        resolve_sql = " ".join(
            s for s, _ in rec.statements if "UPDATE futures_markets" in s
        )
        assert "market_metadata" in resolve_sql, resolve_sql
        # asyncpg drops a bind immediately followed by `::cast`; the CAST()
        # spelling is the one that binds (the project's standing JSONB gotcha).
        assert "::jsonb" not in resolve_sql.replace("'{}'::jsonb", ""), resolve_sql

    async def test_a_terminal_close_is_recorded_as_winner_proof(self, monkeypatch):
        """The falsifier. If everything were stamped 'no winner available' the
        gate would be a constant, and a constant measures nothing.

        Asserting `PROOF_WINNER in <the params>` would NOT do it: both stamps
        are bound on every statement and the CASE picks between them in the
        database, so that assertion is true whatever the prices are — a control
        that cannot fail (ruling 050). The discriminating fact is the CASE's
        own predicate list, `terminal_raw`.
        """
        rec = _Recorder()
        _poly_harness(monkeypatch, [TERMINAL_EVENT], rec)

        await poly_mod._sync_polymarket_resolved_status()

        resolve = [
            p
            for s, p in rec.statements
            if "UPDATE futures_markets" in s and "status = 'resolved'" in s
        ]
        assert resolve, rec.statements
        assert resolve[0]["terminal_raw"] == ["0xfeedface"], resolve[0]
        assert PROOF_WINNER in json.dumps(resolve[0]["proof_stamp"])

    async def test_a_nonterminal_close_is_absent_from_the_winner_branch(
        self, monkeypatch
    ):
        """The other half of the same discrimination: 0.60/0.40 must NOT be
        routed to the winner-proof branch."""
        rec = _Recorder()
        _poly_harness(monkeypatch, [NONTERMINAL_EVENT], rec)

        await poly_mod._sync_polymarket_resolved_status()

        resolve = [
            p
            for s, p in rec.statements
            if "UPDATE futures_markets" in s and "status = 'resolved'" in s
        ]
        assert resolve[0]["terminal_raw"] == [], resolve[0]
        assert resolve[0]["raw_cids"] == ["0xdeadbeef"], resolve[0]

    async def test_the_run_counts_the_two_classes_separately(self, monkeypatch):
        rec = _Recorder()
        _poly_harness(monkeypatch, [NONTERMINAL_EVENT], rec)

        stats = await poly_mod._sync_polymarket_resolved_status()

        assert "resolved_without_winner_proof" in stats, stats
        assert stats["resolved_without_winner_proof"] >= 1, stats
