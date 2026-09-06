"""LAT-P255/#3731 — `/api/events/search` sheds its headline lane without 500ing.

THE DEFECT, measured on production 2026-09-06 23:37-23:41Z. `GET
/api/events/search?q=Red Sox` returned **HTTP 500 at 20.28s, reproduced 2/2**, as
did `Boston Red Sox` (20.34s) and `Red` (20.26s), while `Sox` (3.70s), `Boston`
(4.83s) and `Yankees` (3.87s) answered normally. The dyno log carries both halves
of it 70 ms apart:

    23:38:16.412 WARNING app.routes.events: search headline-contender lane timed
                 out for 'Boston Red Sox' — shipping the page unchanged
    23:38:16.426 INFO:   GET /api/events/search?q=Boston%20Red%20Sox 500
    23:38:16.483 sqlalchemy.exc.MissingGreenlet ... events.py line 4967, in
                 search_events: `_formatted_by_id = {m.id: ...}`

The lane that logs "shipping the page unchanged" is the lane that ships a 500.

THE CHAIN is #3394's, one endpoint over — that fix landed on `/typeahead` and the
identical lane on `/search` was left alone:

1. `contender_patterns("Boston Red Sox")` yields whole-word regexes ANDed as
   `IN (SELECT ...)` subqueries over `futures_outcomes`.
2. `\\mred\\M` is EXTRACTABLE by `ix_futures_outcomes_name_trgm` and not
   SELECTIVE: 1,006,223 GIN candidate rows, 116,342 buffers, 11,660 ms (#3394's
   measurement). The length-matched control `\\msox\\M` costs 39.6 ms.
3. Here the lane had **no bound of its own** — it was armed with whatever was
   left of the 20 s request deadline, and it spent all of it.
4. Its recovery called `_recover_search_session`, i.e. `await db.rollback()`.
5. 🔴 An async rollback EXPIRES every ORM row in the session (gotcha #6).
   `deduped_futures` and `futures_markets` are materialised BEFORE this lane and
   read AFTER it.
6. The next attribute read — `m.id` in the `_formatted_by_id` dict comprehension
   — lazy-refreshed an expired row from a sync greenlet. `MissingGreenlet`. 500.

WHAT THESE TESTS PIN, in three halves that fail for different reasons:

* `TestASavepointRollbackDoesNotExpireTheCallersRows` pins the fix's load-bearing
  claim against SQLAlchemy itself — that swapping the session rollback for a
  savepoint rollback really does leave rows loaded before it readable. #3394
  proved the defect half (a session rollback expires); this proves the repair
  half. If it fails, the route guards below are routing around nothing.
* `TestTheSearchHeadlineLaneCannotPoisonTheSession` pins steps 4-6 against the
  route: the shed must not roll the SESSION back, the statement must sit inside a
  savepoint, and the savepoint must be released on the happy path.
* `TestThePremiseIsStillTrue` pins step 5's precondition — that live ORM rows
  really are held across this lane. A guard whose premise has quietly gone away
  is a guard that passes for the wrong reason.

Every test in the middle class is RED on the pre-fix source, which called
`_recover_search_session` in that handler and used no savepoint.
"""

import ast
import inspect
import textwrap

import pytest
from sqlalchemy import Column, Integer, String, create_engine, inspect as sa_inspect
from sqlalchemy.orm import Session, declarative_base

from app.routes.events import (
    _SEARCH_DEADLINE_MS,
    _SEARCH_HEADLINE_ARM_TIMEOUT_MS,
    _SEARCH_MIN_STAGE_TIMEOUT_MS,
    _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS,
    _headline_arm_bound_ms,
    _search_headline_bound_ms,
    search_events,
)

# The log strings each shed handler writes. Handlers are located by these rather
# than by position, so reordering the route's stages cannot silently point a test
# at a different handler — the failure would be a vacuous pass otherwise.
#
# Matched as a SUBSTRING, not for equality: Black wraps these calls, and adjacent
# string literals are concatenated by the parser into one `Constant` whose value
# is the joined line. An equality match against either fragment finds nothing and
# every test reading the handler errors out rather than passing vacuously — which
# is the safe direction, but not a useful one.
_HEADLINE_SHED_MARK = "search headline-contender lane timed out"
_REFILL_SHED_MARK = "search futures REFILL timed out"


def _route_ast() -> ast.AST:
    """The route's own tree.

    AST rather than a substring sweep: a source guard that greps for a call name
    is defeated by the formatter putting the call on its own line, and this file
    is Black-formatted. The node is the fact; the text is a rendering of it.
    """
    return ast.parse(textwrap.dedent(inspect.getsource(search_events)))


def _bound_helper_ast() -> ast.AST:
    """This lane's bound resolver — the delegate AND the shared arithmetic."""
    return ast.parse(
        textwrap.dedent(inspect.getsource(_search_headline_bound_ms))
        + "\n"
        + textwrap.dedent(inspect.getsource(_headline_arm_bound_ms))
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


def _writes_mark(node: ast.AST, mark: str) -> bool:
    return any(
        isinstance(c, ast.Constant) and isinstance(c.value, str) and mark in c.value
        for c in ast.walk(node)
    )


def _handler_marked(mark: str) -> ast.ExceptHandler:
    for node in ast.walk(_route_ast()):
        if isinstance(node, ast.ExceptHandler) and _writes_mark(node, mark):
            return node
    raise AssertionError(
        f"no except handler in `search_events` writes {mark!r} — that shed path "
        f"has moved or gone, and the tests reading it are now vacuous"
    )


def _session_rollbacks_in(node: ast.AST) -> list[ast.Call]:
    """`db.rollback()` calls — the SESSION's, never a savepoint's.

    A `rollback()` is REQUIRED here (the savepoint's) and FORBIDDEN here (the
    session's), so the bare name cannot decide it — the receiver does. Asserting
    on the name alone would either ban the fix or permit the bug.
    """
    return [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "rollback"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "db"
    ]


def _names_opened_by_begin_nested() -> set[str]:
    """Every local name in the route bound to the result of `db.begin_nested()`.

    Asserting only that SOME `begin_nested()` exists in the route is not enough
    once there are two savepointed lanes: deleting one lane's savepoint leaves
    the other's call in the tree and the check goes green over a lane that no
    longer has one. So the name the shed handler rolls back has to be a name this
    set contains.
    """
    names: set[str] = set()
    for node in ast.walk(_route_ast()):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "begin_nested"
            for c in ast.walk(node.value)
        ):
            names.add(target.id)
    return names


def _savepoint_calls_in(node: ast.AST, attr: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attr
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id.endswith("savepoint")
    ]


# --------------------------------------------------------------------------- #


Base = declarative_base()


class _Row(Base):
    """A minimal mapped class. The mechanism under test is SQLAlchemy's, not the
    app schema's, so proving it on the app's models would only add a way to fail
    for an unrelated reason."""

    __tablename__ = "lat_p255_rows"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class TestASavepointRollbackDoesNotExpireTheCallersRows:
    """The repair half of gotcha #6, pinned against the library.

    #3394 proved that a SESSION rollback expires rows loaded before it. That is
    the defect. This proves the other half — that a SAVEPOINT rollback does not —
    which is the only reason swapping one for the other is a fix rather than a
    relocation of the same crash.
    """

    def _seeded(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = Session(engine)
        session.add(_Row(id=1, name="Boston Red Sox"))
        session.commit()
        return session

    def test_a_savepoint_rollback_leaves_a_row_loaded_before_it_live(self):
        with self._seeded() as session:
            row = session.query(_Row).one()
            assert not sa_inspect(row).expired, "precondition: the row is live"

            savepoint = session.begin_nested()
            savepoint.rollback()

            assert not sa_inspect(row).expired, (
                "a savepoint rollback expired a row loaded before it. The fix "
                "for #3731 rests on it not doing that — if this is genuinely "
                "SQLAlchemy's behaviour now, the route needs a different repair "
                "(materialise the futures rows into dicts before the lane), not "
                "a weaker test."
            )

    def test_the_row_is_readable_after_the_savepoint_rollback_without_a_refresh(self):
        """The expiry is not the point; the RE-QUERY it forces is.

        On the async session that re-query is IO from a sync context, which is
        precisely `MissingGreenlet`. Here it is a second SELECT, which is the same
        fact in a form a test can assert without an event loop — and the assertion
        is that it does NOT happen.
        """
        from sqlalchemy import event

        statements: list[str] = []
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)

        @event.listens_for(engine, "before_cursor_execute")
        def _record(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        with Session(engine) as session:
            session.add(_Row(id=1, name="Boston Red Sox"))
            session.commit()
            row = session.query(_Row).one()

            savepoint = session.begin_nested()
            savepoint.rollback()

            before = len(statements)
            assert row.name == "Boston Red Sox"
            assert len(statements) == before, (
                "reading the row after a savepoint rollback issued a query — the "
                "refresh that raises MissingGreenlet on the async session still "
                "happens, so the savepoint did not buy what #3731 says it buys"
            )

    def test_the_contrast_holds_a_session_rollback_still_expires(self):
        """The control. Without it this class could go green because SQLAlchemy
        stopped expiring on rollback at all, which would mean the guards below
        are protecting against a defect that no longer exists."""
        with self._seeded() as session:
            row = session.query(_Row).one()
            session.rollback()
            assert sa_inspect(row).expired, (
                "a session rollback no longer expires loaded rows — the #3731 "
                "defect mechanism is gone and this file should be re-derived"
            )


class TestTheSearchHeadlineLaneCannotPoisonTheSession:
    """The fix: the shed path leaves the caller's futures rows alive."""

    def test_the_shed_path_does_not_roll_the_session_back(self):
        """RED on the pre-fix source, which called `_recover_search_session` here.

        This is the assertion that would have caught the production 500 before it
        shipped — and it is the assertion the #3394 suite already makes about the
        OTHER endpoint, which is why this defect survived a day past its fix.
        """
        handler = _handler_marked(_HEADLINE_SHED_MARK)

        assert "_recover_search_session" not in _calls_named(handler), (
            "the search headline lane's shed calls `_recover_search_session`, "
            "which rolls the session back and EXPIRES `deduped_futures` and "
            "`futures_markets` — the rows `_formatted_by_id` reads a few lines "
            "later. That is the production 500. Roll back the savepoint, not the "
            "session."
        )
        assert not _session_rollbacks_in(handler), (
            "the shed calls `db.rollback()` directly. Same defect as "
            "`_recover_search_session`, one indirection fewer."
        )

    def test_the_shed_path_rolls_the_savepoint_back(self):
        """The other half of the pair above — refusing the SESSION rollback is
        only safe if the SAVEPOINT is actually rolled back instead. Without this a
        cancelled statement leaves the transaction aborted and every stage after
        the lane fails on it."""
        rolled = _savepoint_calls_in(_handler_marked(_HEADLINE_SHED_MARK), "rollback")
        assert rolled, "the shed path rolls nothing back"

        # …and the thing it rolls back is a real savepoint. Without this, naming
        # a variable `_x_savepoint` and never opening one passes: the statement's
        # cancellation still aborts the whole transaction and the shed's refusal
        # to roll the session back becomes the new outage.
        opened = _names_opened_by_begin_nested()
        assert {call.func.value.id for call in rolled} <= opened, (
            "the headline shed rolls back a name that `db.begin_nested()` never "
            f"opened (opened: {sorted(opened)}). The statement is not inside a "
            "savepoint, so its cancellation aborts the transaction."
        )

    def test_the_shed_path_re_arms_the_request_deadline(self):
        """Not rolling back must not mean leaving a 2s budget lying around.

        The lane arms its own short bound; every stage after it has to run against
        the request deadline again, and `_recover_search_session` used to be what
        restored that. Dropping it without replacing this half would swap a 500
        for a silent truncation of the stages that follow.
        """
        called = _calls_named(_handler_marked(_HEADLINE_SHED_MARK))
        assert "_apply_search_statement_timeout" in called, (
            "the shed path no longer re-arms the statement timeout, so the "
            "stages after the headline lane inherit its 2s bound"
        )

    def test_the_headline_statement_is_inside_the_savepointed_try(self):
        """The savepoint must WRAP the headline select, not merely coexist with it."""
        tree = _route_ast()
        wanted = {"HEADLINE_MARKET_TIER", "MIN_CONTENDER_VOLUME"}
        guarded = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Try)
            and any(_writes_mark(h, _HEADLINE_SHED_MARK) for h in node.handlers)
            and wanted
            <= {c.id for c in ast.walk(node) if isinstance(c, ast.Name)}
        ]
        assert guarded, (
            "the headline-contender select is not inside the try whose handler "
            "sheds it — the savepoint guards the wrong statement"
        )

    def test_the_savepoint_is_released_on_the_happy_path(self):
        """An unreleased savepoint is held for the rest of the transaction."""
        assert _savepoint_calls_in(_route_ast(), "commit"), (
            "no savepoint is released on the path where the query succeeds"
        )

    def test_the_savepoint_is_awaited_not_used_as_a_context_manager(self):
        """`async with db.begin_nested()` is correct against a real AsyncSession
        and breaks against every `AsyncMock` session double in the suite, which
        returns a coroutine from every method. #3394 measured 56 existing tests
        failing on that form while the production path stayed correct in both."""
        as_cm = [
            node
            for node in ast.walk(_route_ast())
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


class TestTheRefillLaneShedsTheSameWay:
    """The sibling latent defect, fixed on the headline lane's evidence.

    The futures REFILL lane runs a few lines earlier, holds the same
    `deduped_futures` rows across the same kind of failure, and had the same
    `_recover_search_session` shed. It has not been seen in production only
    because a paged re-read of a query that already ran is far cheaper than an
    unselective regex — which is a statement about likelihood, not about safety.
    """

    def test_the_refill_shed_does_not_roll_the_session_back(self):
        handler = _handler_marked(_REFILL_SHED_MARK)
        assert "_recover_search_session" not in _calls_named(handler), (
            "the futures refill shed rolls the session back, expiring the "
            "`deduped_futures` rows `_formatted_by_id` reads below"
        )
        assert not _session_rollbacks_in(handler)

    def test_the_refill_shed_rolls_its_savepoint_back_and_re_arms(self):
        handler = _handler_marked(_REFILL_SHED_MARK)
        rolled = _savepoint_calls_in(handler, "rollback")
        assert rolled, (
            "the refill shed rolls nothing back, so a cancelled refill leaves "
            "the transaction aborted for every stage after it"
        )
        opened = _names_opened_by_begin_nested()
        assert {call.func.value.id for call in rolled} <= opened, (
            "the refill shed rolls back a name `db.begin_nested()` never opened "
            f"(opened: {sorted(opened)})"
        )
        assert "_apply_search_statement_timeout" in _calls_named(handler)


class TestThePremiseIsStillTrue:
    """Step 5's precondition: live ORM rows really are held across this lane.

    If the route is ever changed to materialise the futures rows into plain dicts
    before the lane runs, the defect disappears and the guards above become
    ceremony. That is a fine outcome — but it must be NOTICED, not discovered by a
    later reader wondering what these tests are for.
    """

    def test_the_futures_rows_are_read_after_the_headline_lane(self):
        source = textwrap.dedent(inspect.getsource(search_events))
        lane = source.index(_HEADLINE_SHED_MARK)
        formatter = source.index("_formatted_by_id = {")
        assert formatter > lane, (
            "`_formatted_by_id` no longer runs after the headline lane. If the "
            "futures rows are now formatted BEFORE the lane, the session-rollback "
            "defect is structurally gone and this file should be re-derived "
            "rather than kept green."
        )

    def test_the_formatter_reads_an_orm_attribute_and_not_a_dict(self):
        """`m.id` on an expired instance is the exact line that raised."""
        source = textwrap.dedent(inspect.getsource(search_events))
        head = source[source.index("_formatted_by_id = {") :][:200]
        assert "m.id" in head, (
            "the crash site no longer reads an ORM attribute — the premise of "
            "the guards above has changed"
        )


class TestTheLaneHasABoundOfItsOwn:
    def test_the_bound_exists_and_is_below_the_request_deadline(self):
        assert isinstance(_SEARCH_HEADLINE_ARM_TIMEOUT_MS, int)
        assert _SEARCH_HEADLINE_ARM_TIMEOUT_MS > 0
        assert _SEARCH_HEADLINE_ARM_TIMEOUT_MS < _SEARCH_DEADLINE_MS, (
            "a bonus lane budget at or above the whole request deadline is not a "
            "bound — it is the absence of one, which is the pre-fix state: the "
            "lane was handed the remainder of a 20s deadline and spent it"
        )

    def test_the_bound_is_derived_from_the_constant(self):
        assert any(
            isinstance(node, ast.Name) and node.id == "_SEARCH_HEADLINE_ARM_TIMEOUT_MS"
            for node in ast.walk(_bound_helper_ast())
        ), "`_search_headline_bound_ms` does not reference its own constant"

    def test_this_lanes_budget_reaches_the_clamp(self):
        """A lane bound that can outlive the request deadline is no bound at all.

        Two halves, because the resolver is two functions: the clamp has to exist,
        and THIS lane's budget has to be what is handed to it. A shared helper
        that clamps something the delegate never passes is the unbounded lane.
        """
        tree = _bound_helper_ast()
        mins = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "min"
        ]
        assert mins, "the bound is not clamped against the remaining request budget"
        clamped = {
            a.id for node in mins for a in ast.walk(node) if isinstance(a, ast.Name)
        }
        delegated = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_headline_arm_bound_ms"
            and any(
                isinstance(a, ast.Name) and a.id == "_SEARCH_HEADLINE_ARM_TIMEOUT_MS"
                for a in node.args
            )
            for node in ast.walk(tree)
        )
        assert "_SEARCH_HEADLINE_ARM_TIMEOUT_MS" in clamped or (
            delegated and "budget_ms" in clamped
        ), (
            "`_SEARCH_HEADLINE_ARM_TIMEOUT_MS` does not reach the `min(...)` "
            "clamp — the lane has a constant nobody applies"
        )

    def test_a_nearer_deadline_shrinks_or_sheds_the_bound(self):
        import time as _time

        near = _search_headline_bound_ms(
            _time.monotonic() + (_SEARCH_HEADLINE_ARM_TIMEOUT_MS / 1000.0) / 2
        )
        assert near is None or near < _SEARCH_HEADLINE_ARM_TIMEOUT_MS, (
            "a deadline nearer than the lane's own budget returned the full "
            "budget — the lane can outlive the request"
        )

    def test_a_generous_deadline_gets_the_lane_budget_not_the_remainder(self):
        import time as _time

        assert (
            _search_headline_bound_ms(_time.monotonic() + 60.0)
            == _SEARCH_HEADLINE_ARM_TIMEOUT_MS
        )

    def test_the_route_resolves_the_bound_exactly_once(self):
        """Two clock reads can disagree across the stage floor: the gate passes,
        the value comes back None, and the arming line raises TypeError."""
        calls = [
            node
            for node in ast.walk(_route_ast())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_search_headline_bound_ms"
        ]
        assert len(calls) == 1, (
            f"the route calls `_search_headline_bound_ms` {len(calls)} times; it "
            f"reads the clock, so two calls can straddle the stage floor"
        )

    def test_the_gate_is_the_bound_not_a_second_clock_read(self):
        """The pre-fix gate was `time.monotonic() < _deadline`, which admits a
        request with 1 ms left. The bound's `None` IS the gate now — reinstating
        the raw clock comparison alongside it would let a shed-worthy request
        through and arm `statement_timeout = 0`."""
        source = textwrap.dedent(inspect.getsource(search_events))
        gate = source.index("_headline_bound_ms = _search_headline_bound_ms(")
        window = source[gate : gate + 700]
        assert "_headline_bound_ms is not None" in window, (
            "the headline lane's gate is not the resolved bound — a request with "
            "microseconds left can still enter the lane"
        )


class TestTheTwoEndpointsAgree:
    def test_both_headline_lanes_carry_a_budget_of_their_own(self):
        """`/search` was the one without one. Pinning the pair is what stops the
        next endpoint being added by copying whichever of the two is unfixed —
        the exact way this defect outlived #3394."""
        assert _TYPEAHEAD_HEADLINE_ARM_TIMEOUT_MS > 0
        assert _SEARCH_HEADLINE_ARM_TIMEOUT_MS > 0

    def test_neither_bound_can_invert_to_no_bound(self):
        """`statement_timeout = 0` means NO TIMEOUT in Postgres. Swept rather than
        spot-checked, over both lanes, because the naive `min(budget, remaining)`
        evaluates to 0 for a request entering with under a millisecond to spare."""
        import time as _time

        now = _time.monotonic()
        for resolver in (_search_headline_bound_ms,):
            for remaining_s in [i / 1000.0 for i in range(0, 25000, 11)]:
                got = resolver(now + remaining_s)
                assert got is None or got >= _SEARCH_MIN_STAGE_TIMEOUT_MS, (
                    f"remaining={remaining_s}s produced bound {got!r} — below the "
                    f"stage floor, or 0, which Postgres reads as no bound"
                )

    def test_a_deadline_already_passed_sheds_rather_than_arming_zero(self):
        import time as _time

        assert _search_headline_bound_ms(_time.monotonic() - 1.0) is None

    def test_a_sub_millisecond_remainder_sheds(self):
        import time as _time

        assert _search_headline_bound_ms(_time.monotonic() + 0.0004) is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
