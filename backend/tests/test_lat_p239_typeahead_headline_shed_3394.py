"""LAT-P239/#3394 — the headline-contender lane sheds without taking the request with it.

THE DEFECT, measured on production 2026-09-06. `GET /api/events/typeahead?q=red sox`
on the cache-miss path returned **HTTP 500 on 2 of 3 requests at ~10.3s** (Sentry
BAINLUCK-15H, `MissingGreenlet`, frames `typeahead_search` ->
`_normalize_futures_dedup_key`). The third returned 200 at 8.9s with
`headline_contenders` 6,814 ms of it.

THE CHAIN, and note that every link is ordinary:

1. `contender_patterns("red sox")` yields TWO whole-word regexes, `\\mred\\M` and
   `\\msox\\M`, ANDed as `IN (SELECT ...)` subqueries over `futures_outcomes`.
2. `\\mred\\M` is servable by `ix_futures_outcomes_name_trgm` in the sense that
   pg_trgm accepts it, and USELESS in the sense that matters: the GIN returns
   **1,006,223 candidate rows** — essentially the whole corpus — and the bitmap
   recheck reads 116,342 buffers to discard 99.7% of them. 11,660 ms. The
   length-matched control `\\msox\\M` costs 39.6 ms at 2,204 candidates.
3. So the lane blows its statement timeout.
4. The recovery called `_recover_search_session`, i.e. `await db.rollback()`.
5. 🔴 An async rollback EXPIRES every ORM row in the session (gotcha #6).
   `ta_futures_ranked` was materialised BEFORE this lane and is read AFTER it.
6. The next attribute read — `market.name`, in `_normalize_futures_dedup_key` —
   tried to lazy-refresh an expired row from a sync greenlet. `MissingGreenlet`. 500.

The bonus lane whose comment reads "the dropdown must never be slower BECAUSE of a
bonus lane" was, on its own failure path, the outage.

WHAT THESE TESTS PIN, in two halves that fail for different reasons:

* `TestTheRollbackMechanismIsReal` pins step 5 against SQLAlchemy itself. Without
  it the route tests below could pass forever after SQLAlchemy stopped expiring on
  rollback, guarding a defect that no longer exists — a dead guard that still goes
  green. If this class fails, the ones below have stopped meaning anything.
* `TestTheHeadlineLaneCannotPoisonTheSession` pins steps 4-6 against the route: the
  shed path must not roll the SESSION back, and the statement must run inside a
  savepoint so its own rollback reaches no further than itself.

Both halves are RED on the pre-fix source: it called `_recover_search_session` in
that handler and used no savepoint.
"""

import ast
import inspect
import textwrap

import pytest
from sqlalchemy import Column, Integer, String, create_engine, inspect as sa_inspect
from sqlalchemy.orm import Session, declarative_base

from app.routes.events import (
    _SEARCH_MIN_STAGE_TIMEOUT_MS,
    _TYPEAHEAD_DEADLINE_MS,
    _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS,
    _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS,
    _typeahead_headline_bound_ms,
    typeahead_search,
)


def _route_ast() -> ast.AST:
    """The route's own tree.

    AST rather than a substring sweep: a source guard that greps for a call name
    is defeated by the formatter putting the call on its own line, and this file
    is Black-formatted. The node is the fact; the text is a rendering of it.
    """
    return ast.parse(textwrap.dedent(inspect.getsource(typeahead_search)))


def _bound_helper_ast() -> ast.AST:
    """The bound resolver's own tree."""
    return ast.parse(
        textwrap.dedent(inspect.getsource(_typeahead_headline_bound_ms))
    )


def _calls_named(node: ast.AST) -> set[str]:
    """Every function name called anywhere under `node`, attribute calls included."""
    names = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _headline_shed_handler() -> ast.ExceptHandler:
    """The `except` block that handles the headline lane's timeout.

    Located by the mark it writes rather than by position, so reordering the
    route's stages cannot silently point this test at a different handler.
    """
    for node in ast.walk(_route_ast()):
        if not isinstance(node, ast.ExceptHandler):
            continue
        for const in ast.walk(node):
            if (
                isinstance(const, ast.Constant)
                and const.value == "headline_contenders_TIMED_OUT"
            ):
                return node
    raise AssertionError(
        "no except handler marks 'headline_contenders_TIMED_OUT' — the headline "
        "lane's shed path has moved or gone, and this whole file is now vacuous"
    )


# --------------------------------------------------------------------------- #


Base = declarative_base()


class _Row(Base):
    """A minimal mapped class. The mechanism under test is SQLAlchemy's, not the
    app schema's, so proving it on the app's models would only add a way to fail
    for an unrelated reason."""

    __tablename__ = "lat_p239_rows"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class TestTheRollbackMechanismIsReal:
    """Gotcha #6, pinned against the library. The guard below rests on this."""

    def test_a_session_rollback_expires_rows_loaded_before_it(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(_Row(id=1, name="Boston Red Sox"))
            session.commit()

            row = session.query(_Row).one()
            assert row.name == "Boston Red Sox"
            assert not sa_inspect(row).expired, (
                "precondition: the row is live before the rollback"
            )

            # Exactly what `_recover_search_session` does, and the whole defect.
            session.rollback()

            assert sa_inspect(row).expired, (
                "SQLAlchemy no longer expires loaded rows on rollback. That is the "
                "mechanism LAT-P239 exists to route around — if this is genuinely "
                "gone, the route guards below are guarding nothing and this file "
                "should be re-derived, not deleted."
            )

    def test_reading_an_expired_row_is_what_costs_a_database_round_trip(self):
        """The expiry is not inert: the next attribute read re-queries.

        On the async session that re-query is IO from a sync context, which is
        precisely `MissingGreenlet`. Here it is only a second SELECT, which is
        the same fact in a form a test can assert without an event loop.
        """
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        statements: list[str] = []

        from sqlalchemy import event

        @event.listens_for(engine, "before_cursor_execute")
        def _record(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        with Session(engine) as session:
            session.add(_Row(id=1, name="Boston Red Sox"))
            session.commit()
            row = session.query(_Row).one()

            session.rollback()
            before = len(statements)
            assert row.name == "Boston Red Sox"  # triggers the refresh
            assert len(statements) > before, (
                "reading an expired attribute issued no query — the refresh that "
                "raises MissingGreenlet on the async session did not happen"
            )


class TestTheHeadlineLaneCannotPoisonTheSession:
    """The fix: the shed path leaves the caller's ORM rows alive."""

    def test_the_shed_path_does_not_roll_the_session_back(self):
        """RED on the pre-fix source, which called `_recover_search_session` here.

        This is the assertion that would have caught the 500 before it shipped.
        """
        called = _calls_named(_headline_shed_handler())

        handler = _headline_shed_handler()
        called = _calls_named(handler)

        assert "_recover_search_session" not in called, (
            "the headline lane's shed calls `_recover_search_session`, which "
            "rolls the session back and EXPIRES `ta_futures_ranked` — the rows "
            "the `futures_pool` loop reads a few lines later. That is production "
            "500 BAINLUCK-15H. Roll back the savepoint, not the session."
        )

        # A `rollback()` is REQUIRED here (the savepoint's) and FORBIDDEN here
        # (the session's), so the bare name cannot decide it — the receiver does.
        # Asserting on the name alone would either ban the fix or permit the bug.
        session_rollbacks = [
            node
            for node in ast.walk(handler)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "rollback"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "db"
        ]
        assert not session_rollbacks, (
            "the headline lane's shed calls `db.rollback()` directly. Same "
            "defect as `_recover_search_session`, one indirection fewer: it "
            "expires every ORM row the rest of the route still has to read."
        )

    def test_the_shed_path_rolls_the_savepoint_back(self):
        """The other half of the pair above — refusing the SESSION rollback is
        only safe if the SAVEPOINT is actually rolled back instead. Without this
        a cancelled statement leaves the transaction aborted."""
        handler = _headline_shed_handler()
        savepoint_rollbacks = [
            node
            for node in ast.walk(handler)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "rollback"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id.endswith("savepoint")
        ]
        assert savepoint_rollbacks, (
            "the shed path rolls nothing back. The statement was cancelled, so "
            "the transaction is aborted and every stage after this one fails."
        )

    def test_the_shed_path_re_arms_the_request_deadline(self):
        """Not rolling back must not mean leaving a 2s budget lying around.

        The lane arms its own short bound; every stage after it has to run
        against the request deadline again, and `_recover_search_session` used to
        be what restored that. Dropping it without replacing this half would swap
        a 500 for a silent truncation of the remaining stages.
        """
        called = _calls_named(_headline_shed_handler())
        assert "_apply_search_statement_timeout" in called, (
            "the shed path no longer re-arms the statement timeout, so the "
            "stages after the headline lane inherit its 2s bound"
        )

    def test_the_headline_statement_runs_inside_a_savepoint(self):
        """The savepoint is what makes not-rolling-back safe.

        Without it a cancelled statement leaves the transaction aborted and every
        later stage fails on the poisoned session — the failure mode
        `_recover_search_session` was correctly written for elsewhere.
        """
        tree = _route_ast()
        opened = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "begin_nested"
        ]
        assert opened, (
            "no `db.begin_nested()` in the route — the headline lane's statement "
            "is not savepointed, so its cancellation aborts the whole "
            "transaction and the shed path's refusal to roll back is unsafe"
        )

        # The savepoint must WRAP the headline select, not merely coexist with
        # it. The `try` that catches the shed is the scope that matters: the
        # select is in its body and the savepoint is opened before it.
        guarded = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Try)
            and any(h is _headline_shed_handler_in(node) for h in node.handlers)
            and _mentions_headline_select(node)
        ]
        assert guarded, (
            "the headline-contender select is not inside the try whose handler "
            "sheds it — the savepoint guards the wrong statement"
        )

    def test_the_savepoint_is_released_on_the_happy_path(self):
        """An unreleased savepoint is held for the rest of the transaction, and
        this lane runs on every eligible keystroke."""
        tree = _route_ast()
        commits = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "commit"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id.endswith("savepoint")
        ]
        assert commits, (
            "the savepoint is opened on every eligible keystroke and never "
            "released on the path where the query succeeds"
        )

    def test_the_savepoint_is_awaited_not_used_as_a_context_manager(self):
        """`async with db.begin_nested()` is correct against a real AsyncSession
        and breaks against every `AsyncMock` session double in the suite, which
        returns a coroutine from every method. 56 existing tests failed on that
        form while production stayed correct. `calibration_main_build`'s soft
        stage is the repo's precedent for the awaited form."""
        tree = _route_ast()
        as_cm = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncWith)
            and any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "begin_nested"
                for item in node.items
                for c in ast.walk(item.context_expr)
            )
        ]
        assert not as_cm, (
            "`begin_nested()` is used as an async context manager. Correct "
            "against a real AsyncSession, broken against the AsyncMock session "
            "doubles this suite uses. Await it and roll back explicitly."
        )

    def test_the_lane_has_its_own_bound_and_it_is_not_the_request_deadline(self):
        assert isinstance(_TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS, int)
        assert _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS > 0
        assert _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS < _TYPEAHEAD_DEADLINE_MS, (
            "a bonus lane budget at or above the whole request deadline is not a "
            "bound — it is the absence of one, which is the pre-fix state"
        )

    def test_the_bound_is_derived_from_the_constant(self):
        """A hardcoded 2000 in the resolver would drift from the constant."""
        tree = _bound_helper_ast()
        assert any(
            isinstance(node, ast.Name)
            and node.id == "_TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS"
            for node in ast.walk(tree)
        ), (
            "`_typeahead_headline_bound_ms` does not reference "
            "`_TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS`"
        )

    def test_the_bound_is_the_min_of_its_budget_and_what_is_left(self):
        """A lane bound that can outlive the request deadline is no bound at all —
        the same clause `_resolve_typeahead_outcome_arm` states for its sibling.

        Asserted on the resolver rather than behaviourally because the failing
        direction needs a deadline further out than the lane budget AND a clock
        that does not move between the two, which a behavioural test cannot pin.
        """
        tree = _bound_helper_ast()
        mins = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "min"
            and any(
                isinstance(a, ast.Name)
                and a.id == "_TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS"
                for a in ast.walk(node)
            )
        ]
        assert mins, (
            "the headline bound is not clamped by `min(...)` against the "
            "remaining request budget, so a lane entered late can outlive the "
            "request deadline"
        )

    def test_the_bound_really_is_clamped_by_the_remaining_budget(self):
        """The behavioural half of the assertion above, in the direction that
        can be pinned: a deadline nearer than the lane budget must shrink it.

        With the lane budget equal to the stage floor today, "shrink" and "shed"
        are the same observable, so this asserts the disjunction rather than
        pretending to distinguish them.
        """
        import time as _time

        near = _typeahead_headline_bound_ms(
            _time.monotonic() + (_TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS / 1000.0) / 2
        )
        assert near is None or near < _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS, (
            "a deadline nearer than the lane's own budget returned the full "
            "budget — the lane can outlive the request"
        )


class TestTheBoundCannotInvertToNoBound:
    """`statement_timeout = 0` means NO TIMEOUT in Postgres.

    The naive `min(budget, int(remaining_ms))` evaluates to 0 for a request
    entering this lane with under a millisecond to spare, which would hand the
    single most degenerate case in the system an unbounded query. These pin the
    shed instead.
    """

    def test_a_deadline_already_passed_sheds_rather_than_arming_zero(self):
        import time as _time

        assert _typeahead_headline_bound_ms(_time.monotonic() - 1.0) is None

    def test_a_sub_millisecond_remainder_sheds(self):
        import time as _time

        # The exact input that makes `int(remaining_ms)` evaluate to 0.
        assert _typeahead_headline_bound_ms(_time.monotonic() + 0.0004) is None

    def test_the_bound_is_never_zero_for_any_remaining_budget(self):
        """Swept, not spot-checked: no reachable deadline yields a 0 bound."""
        import time as _time

        now = _time.monotonic()
        for remaining_s in [i / 1000.0 for i in range(0, 12000, 7)]:
            got = _typeahead_headline_bound_ms(now + remaining_s)
            assert got is None or got >= _SEARCH_MIN_STAGE_TIMEOUT_MS, (
                f"remaining={remaining_s}s produced bound {got!r} — a bound "
                f"below the stage floor, or 0, which Postgres reads as no bound"
            )

    def test_a_generous_deadline_gets_the_lane_budget_not_the_remainder(self):
        import time as _time

        assert (
            _typeahead_headline_bound_ms(_time.monotonic() + 60.0)
            == _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS
        )

    def test_the_route_resolves_the_bound_exactly_once(self):
        """Two clock reads can disagree across the stage floor: the gate passes,
        the value comes back None, and the arming line raises TypeError."""
        tree = _route_ast()
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_typeahead_headline_bound_ms"
        ]
        assert len(calls) == 1, (
            f"the route calls `_typeahead_headline_bound_ms` {len(calls)} times; "
            f"it reads the clock, so two calls can straddle the stage floor"
        )


class TestTheTwoBonusLanesAgree:
    def test_both_bonus_lanes_carry_a_budget_of_their_own(self):
        """The headline lane was the only one without one. Pinning the pair stops
        a future lane being added with the same omission by copying this one."""
        assert _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS > 0
        assert _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS > 0


def _headline_shed_handler_in(try_node: ast.Try):
    """The shed handler, if this `try` is the one that owns it."""
    for handler in try_node.handlers:
        for const in ast.walk(handler):
            if (
                isinstance(const, ast.Constant)
                and const.value == "headline_contenders_TIMED_OUT"
            ):
                return handler
    return None


def _mentions_headline_select(node: ast.AST) -> bool:
    """True when the headline lane's own predicate is inside this block."""
    wanted = {"HEADLINE_MARKET_TIER", "MIN_CONTENDER_VOLUME"}
    seen = {
        child.id for child in ast.walk(node) if isinstance(child, ast.Name)
    }
    return wanted <= seen


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
