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

TASK = "_refresh_stale_futures_prices"


class _TaskResult(_Result):
    """`_Result`, plus the `.scalar()` the task's censuses call on it."""

    def __init__(self, rows=(), scalar=0):
        super().__init__(list(rows))
        self._scalar = scalar

    def scalar(self):
        return self._scalar


class _TaskSession(_FakeSession):
    """The arm's session widened to everything the whole task executes.

    Still dispatches the arm's four statements on IDENTITY, so a renamed
    constant cannot pass; everything else the task runs — the two `SET`s, the
    `remaining_stale` census — falls through to an empty result instead of the
    `AssertionError` the unit fake raises. The scans are monkeypatched out, so
    this deliberately does NOT have to know their SQL.
    """

    async def execute(self, stmt, params=None):
        try:
            return await super().execute(stmt, params)
        except AssertionError:
            return _TaskResult()


class _TaskRun:
    """Drives the real `_refresh_stale_futures_prices` with a chosen batch.

    The batch is injected at the SCAN boundary rather than through fake SQL,
    because what is under test is what the task does with an empty Kalshi
    selection — not whether `_CANDIDATE_SQL` can be made to return one.
    """

    def __init__(self, *, class_markets=(), unreached=(), candidates=(), answers=None):
        self.class_markets = list(class_markets)
        self.session = _TaskSession(
            unreached=list(unreached), candidates=list(candidates), control=CONTROL
        )
        self.kalshi = _FakeKalshi(answers or {})
        self.poly_closed = False
        # The query budget the task armed, captured from get_task_session's
        # kwargs. Recorded rather than swallowed: a double that accepts
        # anything is what let #4482's signature change reach the desk as a
        # composed-tree red instead of a red on this branch.
        self.session_budget: dict | None = None

    def run(self, monkeypatch, *, key="test-key"):
        import contextlib

        from app.utils.feed_served_markets import SERVED_EMPTY, ServedSignal

        if key is None:
            monkeypatch.delenv("KALSHI_API_KEY", raising=False)
        else:
            monkeypatch.setenv("KALSHI_API_KEY", key)

        @contextlib.asynccontextmanager
        async def _session(
            *, statement_timeout_ms: int | None = None,
            lock_timeout_ms: int | None = None,
        ):
            # Mirrors app.tasks.base.get_task_session as #4482 left it. The
            # kwargs are keyword-only there, so they are keyword-only here.
            self.session_budget = {
                "statement_timeout_ms": statement_timeout_ms,
                "lock_timeout_ms": lock_timeout_ms,
            }
            yield self.session

        outer = self

        class _Poly:
            async def close(self):
                outer.poly_closed = True

        monkeypatch.setattr("app.tasks.base.get_task_session", _session)
        monkeypatch.setattr(
            "app.services.kalshi_api.KalshiAPIService", lambda: self.kalshi
        )
        monkeypatch.setattr(
            "app.services.polymarket_api.PolymarketAPIService", lambda: _Poly()
        )
        monkeypatch.setattr(
            "app.utils.tournament_register.registered_market_ids", lambda: set()
        )
        monkeypatch.setattr(
            "app.utils.feed_served_markets.served_signal",
            lambda: ServedSignal(state=SERVED_EMPTY, ids=[], shapes=1),
        )
        monkeypatch.setattr(
            "app.utils.feed_served_markets.note_served_signal_healthy", lambda: None
        )
        monkeypatch.setattr(mod, "_load_attempt_skips", lambda ids: set())
        monkeypatch.setattr(mod, "_mark_attempted", lambda ids, ttl_seconds: None)

        async def _empty(session, **kwargs):
            return []

        async def _class(session, **kwargs):
            return list(self.class_markets)

        monkeypatch.setattr(mod, "_scan_served_candidates", _empty)
        monkeypatch.setattr(mod, "_scan_registered_candidates", _empty)
        monkeypatch.setattr(mod, "_scan_candidates", _class)
        return asyncio.run(mod._refresh_stale_futures_prices())


def _poly_market(market_id=99001):
    """A Polymarket row the poll cannot address, so the batch has NO Kalshi row.

    `poly_event_id=None` is a real production shape (`no_event_id` counts it) and
    it takes the Polymarket arm's first `continue`, which keeps this test about
    the Kalshi block and not about Polymarket pricing.
    """
    return {
        "id": market_id,
        "source": "polymarket",
        "external_id": "0xdead",
        "volume": 1_000,
        "poly_event_id": None,
        "venue_settled_since": None,
        "arm": "class",
        "registered": False,
        "served": False,
        "priority": False,
    }


class TestTheArmRunsWhenTheStaleBatchIsEmpty:
    """🔴 CERT-2421's granted follow-up: the arm was scoped to somebody else's batch.

    The reach arm shipped inside the batched arm's `if kalshi_markets:`, and the
    task ALSO returns early when nothing at all is stale. Both suppressions have
    the same shape as the six-hour staleness gate the arm exists to defeat — the
    arm's population is live, actively traded markets, which are precisely the
    ones that never make a stale batch. A pass that selects nothing is not a
    pass with nothing for this arm to do; it is the pass where this arm is the
    only Kalshi reach there is.

    Each test asserts the batch really was empty before asserting the arm ran.
    Without that the tests would pass on a run that quietly priced a Kalshi
    market, which is the shape they exist to rule out.
    """

    def test_the_pass_arms_the_4482_query_budget(self, monkeypatch):
        """The double must track `get_task_session`'s real signature.

        Added after integrator-284 bounced `55f4a3f8`: calibration/1076
        (#4482, `e3cd444a`) moved the budget from a bare `SET statement_timeout`
        to keyword arguments on `get_task_session`, an hour after CERT-2424 was
        banked. This file's double took no kwargs, so the composed tree went red
        on six tests while both branches were independently green — a semantic
        conflict a clean textual merge cannot see.

        Asserting the VALUES, not just tolerating the kwargs, is the point: a
        double that silently accepts anything is what let the drift through.
        """
        run = _TaskRun(
            unreached=[(OPENAI, 1_083_106)],
            candidates=[(OPENAI, DEAD[0])],
            answers={CONTROL: True, DEAD[0]: False},
        )
        run.run(monkeypatch)

        assert run.session_budget == {
            "statement_timeout_ms": 60_000,
            "lock_timeout_ms": 15_000,
        }

    def test_a_wholly_empty_batch_still_sweeps(self, monkeypatch):
        run = _TaskRun(
            unreached=[(OPENAI, 1_083_106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            answers={CONTROL: True, DEAD[0]: False, DEAD[1]: False},
        )
        stats = run.run(monkeypatch)

        # The control: this really is the nothing-was-stale early return.
        assert stats["markets_attempted"] == 0
        assert stats["terminal"] == "complete"

        assert stats["unreached_markets_found"] == 1
        assert stats["unreached_markets_checked"] == 1
        assert stats["unreached_legs_retired"] == 2, (
            "the task returned early on an empty stale batch and never ran the "
            "reach arm — the OpenAI ladder's 100% legs stay on the page"
        )
        assert stats["errors"] == []

    def test_a_batch_with_no_kalshi_row_still_sweeps(self, monkeypatch):
        """The other suppression: a batch that is non-empty but all Polymarket."""
        run = _TaskRun(
            class_markets=[_poly_market()],
            unreached=[(OPENAI, 1_083_106)],
            candidates=[(OPENAI, DEAD[0]), (OPENAI, DEAD[1])],
            answers={CONTROL: True, DEAD[0]: False, DEAD[1]: False},
        )
        stats = run.run(monkeypatch)

        # The control: the batch was selected and held no Kalshi market at all,
        # so the old `if kalshi_markets:` scoping would have skipped the arm.
        assert stats["candidates"] == 1
        assert stats["no_event_id"] == 1
        assert stats["by_source"].get("kalshi", 0) == 0

        assert stats["unreached_legs_retired"] == 2, (
            "a Polymarket-only batch suppressed the Kalshi reach arm"
        )

    def test_the_empty_batch_is_not_excluded_from_its_own_sweep(self, monkeypatch):
        """`exclude_ids` is the batch, so an empty batch excludes nothing."""
        captured = {}

        class _Capture(_TaskSession):
            async def execute(self, stmt, params=None):
                if stmt is mod._KALSHI_UNREACHED_FROZEN_SQL:
                    captured.update(params)
                return await super().execute(stmt, params)

        run = _TaskRun()
        run.session = _Capture(unreached=[], candidates=[], control=CONTROL)
        run.run(monkeypatch)

        assert captured["exclude_ids"] == []

    def test_a_missing_key_is_reported_and_not_charged_to_the_pass(self, monkeypatch):
        """The zero that would otherwise be silent.

        Without a credential the arm cannot run, and `unreached_markets_found: 0`
        would read exactly like a drained backlog. It says so instead — and NOT
        through `errors`, which would turn every keyless pass `partial` and make
        this a verdict about the pricing run rather than about one arm.
        """
        run = _TaskRun(
            unreached=[(OPENAI, 1_083_106)],
            candidates=[(OPENAI, DEAD[0])],
            answers={CONTROL: True, DEAD[0]: False},
        )
        stats = run.run(monkeypatch, key=None)

        assert stats["unreached_skipped_no_key"] is True
        assert run.kalshi.calls == []
        assert stats["unreached_markets_found"] == 0
        assert stats["errors"] == []
        assert stats["terminal"] == "complete"

    def test_a_keyless_pass_with_no_kalshi_batch_is_still_not_an_error(
        self, monkeypatch
    ):
        """The batch's error stays the batch's, on the path that can reach it.

        Found by mutation: the sibling test above takes the empty-batch early
        return, which never reaches the credential branch at all, so it cannot
        see `elif kalshi_markets:` widened to `else:`. This one selects a batch
        — so the branch is reached — with no Kalshi row in it, which is the pass
        that must stay clean. "KALSHI_API_KEY not configured" is an error about
        markets that were selected and then not priced; appending it here would
        turn a keyless environment's every pass `partial` over an arm that
        already reports its own skip.
        """
        run = _TaskRun(class_markets=[_poly_market()])
        stats = run.run(monkeypatch, key=None)

        assert stats["candidates"] == 1, "the credential branch was never reached"
        assert stats["errors"] == []
        assert stats["unreached_skipped_no_key"] is True

    def test_a_present_key_leaves_the_skip_flag_down(self, monkeypatch):
        """THE CONTROL for the flag. Without it, always-True would pass above."""
        run = _TaskRun(
            unreached=[(OPENAI, 1_083_106)],
            candidates=[(OPENAI, DEAD[0])],
            answers={CONTROL: True, DEAD[0]: False},
        )
        stats = run.run(monkeypatch)

        assert stats["unreached_skipped_no_key"] is False
        assert run.kalshi.calls, "the arm never reached the venue"


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

    def test_it_is_actually_wired_into_the_task(self):
        """The mutation every other arm here misses: delete the call, stay green.

        Mutation-tested 2026-09-09 — eleven mutants of the arm's own logic were
        caught by the classes above, and replacing the ONE call site with a
        no-op left all fourteen passing. A ship nothing invokes is inert, and no
        behavioural test of a helper can see that.

        Parsed with `ast`, deliberately, not grepped: this module's docstrings
        name `_sweep_unreached_kalshi_frozen` several times, so a source scan for
        the string is satisfied by the prose ABOUT the call and would pass with
        the call itself deleted. The AST sees calls only.

        TWO HOPS since the reach arm was hoisted out of the batched arm's
        `if kalshi_markets:`, and the second one is counted: the task has two
        exits and both must run it, so a single call site here means one of them
        was dropped. Which exit is which is proved behaviourally by
        `TestTheArmRunsWhenTheStaleBatchIsEmpty` below — this only proves nothing
        went inert.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(mod))

        def _callers(name: str) -> list[str]:
            return [
                fn.name
                for fn in ast.walk(tree)
                if isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))
                for call in ast.walk(fn)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == name
            ]

        assert "_kalshi_reach_arm" in _callers("_sweep_unreached_kalshi_frozen"), (
            "the reach arm is not called by its own wrapper; #4253's reach half "
            "is inert"
        )
        task_calls = [c for c in _callers("_kalshi_reach_arm") if c == TASK]
        assert len(task_calls) == 2, (
            "the task must run the reach arm on BOTH of its exits — the normal "
            f"path and the nothing-was-stale early return; found {len(task_calls)}"
        )

    def test_it_admits_only_uncrowned_frozen_legs_on_live_markets(self):
        sql = " ".join(str(mod._KALSHI_UNREACHED_FROZEN_SQL).split())
        assert "fm.source = 'kalshi'" in sql
        assert "fo.current_probability = 1.0" in sql
        assert "fo.is_winner IS NOT TRUE" in sql
        # the crowned-sibling refusal, which is the whole safety argument (CERT-2394)
        assert "crowned.is_winner IS TRUE" in sql
        # and it must NOT carry the staleness anti-join that caused the defect
        assert "captured_at" not in sql
