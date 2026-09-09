"""#4253 reach arm — the delisted sweep can now see an actively traded market.

## The defect these arms exist to catch

The shipped sweep retires a delisted Kalshi leg only for markets handed to it by
`_scan_kalshi_frozen_certain`, and that scan is passed the ids of
`_CANDIDATE_SQL`'s batch. `_CANDIDATE_SQL` ends in a six-hour price-staleness
anti-join, so a market enters it only after six hours of price silence. An
actively traded market is re-priced continuously, never goes stale, and its
delisted legs were therefore never checked — **not "later": never.**

Measured on production 2026-09-09: of 35 open Kalshi markets holding
frozen-certain legs, 15 were unreachable this way, all of them `KXIPO*` "When
will X officially announce an IPO?" ladders, 54 stuck legs between them. The
biggest, OpenAI (`108559`, $1,083,106 volume), served a HERO number of `100%` /
"Yes" off a leg for "Before Sep 1, 2025" — ten months after that date passed,
with the market's own live legs at 41/63/73%. `KXIPOOPENAI-25SEP01` and
`-25NOV01` answered **404**; `KXIPOOPENAI-27JUN01` answered **200**.

The pass's own telemetry said it plainly: `delisted_checks: 0` with
`delisted_check_budget_hit: false` — zero checks attempted with budget to spare.
That pair is the signature of a population that never arrives, and it is why
`unreached_markets_found` is reported unconditionally.

## The arm that carries the safety argument

`test_a_market_whose_control_is_gone_is_refused_whole` and its two siblings. The
batched arm gets its venue-reachability proof for free — it retires only after a
successful price read on that same market, so a 404 cannot be the venue being
down. This arm prices nothing, so it must BUY that proof, per market, before any
404 is allowed to mean anything. `False`/`None` on the control decline the whole
market (gotcha #53: "we could not reach it" is never evidence of absence).

**The ordering is the property, not the count.** A control probed *after* the
candidates would license nothing, so `test_the_control_is_probed_before_any_candidate`
asserts the call sequence rather than the call set — that is the arm a
plausible-looking refactor breaks first.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks import futures_price_refresh as mod


def _stats() -> dict:
    """The task's own stats shape, so a missing key fails here and not in prod."""
    return {
        "kalshi_legs_retired": 0,
        "delisted_checks": 0,
        "delisted_still_listed": 0,
        "delisted_indeterminate": 0,
        "delisted_refused_market_graded": 0,
        "delisted_check_budget_hit": False,
        "unreached_markets_found": 0,
        "unreached_markets_checked": 0,
        "unreached_legs_retired": 0,
        "unreached_no_control": 0,
        "unreached_control_delisted": 0,
        "unreached_control_indeterminate": 0,
        "unreached_budget_exhausted": False,
        "errors": [],
    }


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    """Dispatches on the SQL object itself, so a renamed constant cannot pass."""

    def __init__(self, unreached, candidates, control, retired_rows=None, graded=False):
        self._unreached = unreached
        self._candidates = candidates
        self._control = control
        self._retired_rows = retired_rows
        self._graded = graded
        self.commits = 0
        self.rollbacks = 0
        self.retire_calls = []

    async def execute(self, stmt, params=None):
        if stmt is mod._KALSHI_UNREACHED_FROZEN_SQL:
            return _Result(self._unreached)
        if stmt is mod._KALSHI_FROZEN_CERTAIN_SQL:
            return _Result(self._candidates)
        if stmt is mod._KALSHI_RETIRE_DELISTED_SQL:
            self.retire_calls.append(params)
            rows = self._retired_rows
            if rows is None:
                rows = [(i,) for i in range(len(params["tickers"]))]
            return _Result(rows)
        raise AssertionError(f"unexpected statement: {stmt}")

    async def scalar(self, stmt, params=None):
        if stmt is mod._KALSHI_CONTROL_LEG_SQL:
            return self._control
        if stmt is mod._KALSHI_MARKET_NOW_GRADED_SQL:
            return self._graded
        raise AssertionError(f"unexpected scalar: {stmt}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _FakeKalshi:
    def __init__(self, answers):
        self._answers = answers
        self.calls = []

    async def market_exists(self, ticker):
        self.calls.append(ticker)
        return self._answers.get(ticker)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


def _run(session, service, stats, exclude_ids=()):
    asyncio.run(
        mod._sweep_unreached_kalshi_frozen(session, service, list(exclude_ids), stats)
    )
    return stats


# The production specimen, kept as data so every arm argues about one market.
OPENAI = 108559
CONTROL = "KXIPOOPENAI-27JUN01"
DEAD = ["KXIPOOPENAI-25SEP01", "KXIPOOPENAI-25NOV01"]


class TestTheArmReachesWhatTheBatchNeverDid:
    def test_a_live_control_licenses_retiring_the_delisted_legs(self):
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            control=CONTROL,
        )
        service = _FakeKalshi({CONTROL: True, DEAD[0]: False, DEAD[1]: False})
        stats = _run(session, service, _stats())

        assert stats["unreached_markets_found"] == 1
        assert stats["unreached_markets_checked"] == 1
        assert stats["unreached_legs_retired"] == 2
        # The shared counter moves too: the ledger the operator reads is one number.
        assert stats["kalshi_legs_retired"] == 2
        assert session.retire_calls == [{"market_id": OPENAI, "tickers": DEAD}]

    def test_the_control_is_probed_before_any_candidate(self):
        """The ordering IS the safety argument — a control probed after proves nothing."""
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            control=CONTROL,
        )
        service = _FakeKalshi({CONTROL: True, DEAD[0]: False, DEAD[1]: False})
        _run(session, service, _stats())

        assert service.calls[0] == CONTROL, service.calls
        assert service.calls == [CONTROL] + DEAD

    def test_a_still_listed_leg_is_never_retired(self):
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            control=CONTROL,
            retired_rows=[(1,)],
        )
        service = _FakeKalshi({CONTROL: True, DEAD[0]: False, DEAD[1]: True})
        stats = _run(session, service, _stats())

        assert session.retire_calls == [{"market_id": OPENAI, "tickers": [DEAD[0]]}]
        assert stats["delisted_still_listed"] == 1


class TestTheControlGateRefuses:
    def test_a_market_whose_control_is_gone_is_refused_whole(self):
        """Control 404 ⇒ the SERIES may be purged, so a candidate 404 proves nothing."""
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            control=CONTROL,
        )
        service = _FakeKalshi({CONTROL: False, DEAD[0]: False, DEAD[1]: False})
        stats = _run(session, service, _stats())

        assert session.retire_calls == []
        assert stats["unreached_control_delisted"] == 1
        assert stats["unreached_legs_retired"] == 0
        # and it never spent a call on a candidate it had no licence to judge
        assert service.calls == [CONTROL]

    def test_an_unreachable_venue_is_refused_and_counted_apart(self):
        """None is not False — gotcha #53. Same refusal, different news."""
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0])],
            control=CONTROL,
        )
        service = _FakeKalshi({CONTROL: None, DEAD[0]: False})
        stats = _run(session, service, _stats())

        assert session.retire_calls == []
        assert stats["unreached_control_indeterminate"] == 1
        assert stats["unreached_control_delisted"] == 0

    def test_a_market_with_no_control_leg_left_is_refused(self):
        """Every leg a candidate = the wholly purged series. Must not retire."""
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            control=None,
        )
        service = _FakeKalshi({DEAD[0]: False, DEAD[1]: False})
        stats = _run(session, service, _stats())

        assert session.retire_calls == []
        assert stats["unreached_no_control"] == 1
        assert service.calls == []


class TestTheBudgetIsSharedWithTheBatchedArm:
    def test_an_exhausted_budget_stops_the_arm_before_it_queries(self):
        """Runs last by design: when the budget binds, the batched arm keeps it all."""
        session = _FakeSession(unreached=[(OPENAI, 1)], candidates=[], control=CONTROL)
        service = _FakeKalshi({})
        stats = _stats()
        stats["delisted_checks"] = mod.KALSHI_DELISTED_CHECK_BUDGET
        _run(session, service, stats)

        assert stats["unreached_budget_exhausted"] is True
        # It did not even scan — an exhausted pass must cost nothing at all.
        assert stats["unreached_markets_found"] == 0
        assert service.calls == []

    def test_the_control_call_is_charged_to_the_budget(self):
        """A control is a venue round trip; an uncounted one uncaps the pass."""
        session = _FakeSession(
            unreached=[(OPENAI, 1083106)],
            candidates=[(OPENAI, DEAD[0])],
            control=CONTROL,
        )
        service = _FakeKalshi({CONTROL: True, DEAD[0]: False})
        stats = _run(session, service, _stats())

        # one control + one candidate
        assert stats["delisted_checks"] == 2

    def test_the_budget_stops_the_arm_between_markets(self):
        session = _FakeSession(
            unreached=[(OPENAI, 2), (108555, 1)],
            candidates=[(OPENAI, DEAD[0]), (108555, "KXIPOSTARLINK-25SEP01")],
            control=CONTROL,
        )
        service = _FakeKalshi(
            {CONTROL: True, DEAD[0]: False, "KXIPOSTARLINK-25SEP01": False}
        )
        stats = _stats()
        stats["delisted_checks"] = mod.KALSHI_DELISTED_CHECK_BUDGET - 2
        _run(session, service, stats)

        assert stats["unreached_markets_checked"] == 1
        assert stats["delisted_check_budget_hit"] is True


class TestItCannotCostThePassItsPrices:
    def test_a_failing_scan_is_swallowed_and_reported(self):
        class _Boom(_FakeSession):
            async def execute(self, stmt, params=None):
                if stmt is mod._KALSHI_UNREACHED_FROZEN_SQL:
                    raise RuntimeError("relation went away")
                return await super().execute(stmt, params)

        session = _Boom(unreached=[], candidates=[], control=CONTROL)
        stats = _run(session, _FakeKalshi({}), _stats())

        assert session.rollbacks == 1
        assert any("unreached scan" in e for e in stats["errors"])

    def test_an_empty_population_is_reported_as_a_drained_backlog(self):
        """0 found and 0 checked are different passes; both must be legible."""
        session = _FakeSession(unreached=[], candidates=[], control=CONTROL)
        stats = _run(session, _FakeKalshi({}), _stats())

        assert stats["unreached_markets_found"] == 0
        assert stats["unreached_markets_checked"] == 0
        assert stats["errors"] == []


class TestTheQueryIsShapedAsClaimed:
    def test_the_batch_is_excluded_so_no_leg_is_paid_for_twice(self):
        captured = {}

        class _Capture(_FakeSession):
            async def execute(self, stmt, params=None):
                if stmt is mod._KALSHI_UNREACHED_FROZEN_SQL:
                    captured.update(params)
                return await super().execute(stmt, params)

        session = _Capture(unreached=[], candidates=[], control=CONTROL)
        _run(session, _FakeKalshi({}), _stats(), exclude_ids=[1, 2, 3])

        assert captured["exclude_ids"] == [1, 2, 3]
        assert captured["market_limit"] == mod.KALSHI_UNREACHED_MARKET_LIMIT

    def test_it_orders_by_volume_so_the_budget_is_spent_where_readers_are(self):
        sql = " ".join(str(mod._KALSHI_UNREACHED_FROZEN_SQL).split())
        assert "ORDER BY fm.volume DESC NULLS LAST" in sql

    def test_it_admits_only_uncrowned_frozen_legs_on_live_markets(self):
        sql = " ".join(str(mod._KALSHI_UNREACHED_FROZEN_SQL).split())
        assert "fm.source = 'kalshi'" in sql
        assert "fo.current_probability = 1.0" in sql
        assert "fo.is_winner IS NOT TRUE" in sql
        # the crowned-sibling refusal, which is the whole safety argument (CERT-2394)
        assert "crowned.is_winner IS TRUE" in sql
        # and it must NOT carry the staleness anti-join that caused the defect
        assert "captured_at" not in sql
