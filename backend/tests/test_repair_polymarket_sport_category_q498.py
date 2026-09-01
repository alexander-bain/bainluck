"""Q498 — the CERT-673 follow-up: the cleanup after a failed unit is TWO steps,
and only one of them was bounded or counted.

PILLAR: TRUTH. SHIP (inherited from Q496/Q497 — a hardening queue riding an
already-shipped rail, NOT a new ship): the operator draining the Table Tennis
backlog gets a response with a cursor in it even when the database stops
answering mid-page.

WHY THIS FILE EXISTS
====================

CERT-673 granted Q497 r2 its token and named one follow-up:
``Q497-BOUND-INVALIDATE-CLEANUP`` — explicitly bound or account for
``session.invalidate()`` after a rollback timeout.

Measuring it turned the follow-up from "an unbounded await" into something
sharper, and the sharper version is what these guards are shaped around.
``AsyncSession.invalidate()`` is NOT an abrupt drop. SQLAlchemy's asyncpg
dialect routes pool invalidation to ``AsyncAdapt_terminate.terminate()``, which
— in a greenlet, which is exactly the invalidated-connection case — first
attempts a GRACEFUL close: ``await self._connection.close(timeout=2)``. So:

* it is a network round trip to a database we have already established is not
  answering, on the one path whose entire purpose is to return a cursor; and
* its ceiling was ~2.0s, a literal hardcoded inside a third-party dialect.

That second point is the one that made the arithmetic wrong rather than merely
loose. ``POST_LOOP_NON_COUNT_RESERVE_SECONDS`` was 2.5 and had already committed
1.5 of it to the derived write bound. The cleanup it also pays for could cost
0.5 + ~2.0, so the true worst case was ~4.0 against a 2.5 reserve — over-committed
by ~1.5s on the exact failure path CERT-670 widened the reserve *for*, and the
overrun arrives as the H12-with-no-body the whole rail exists to prevent.

🆕 **A BOUND SET BY SOMEONE ELSE'S LITERAL IS NOT A BOUND YOU CAN BUDGET
AGAINST.** Q497 r1's lesson was that a bound installed over the channel it
bounds is not yet a bound; this is one level along again — the bound existed, it
just was not ours, and no test of ours could see it move.

WHAT EACH GUARD HAS TO BE SHAPED LIKE TO BE WORTH ANYTHING
==========================================================

* The cleanup's cost is invisible from a passing run — it only elapses when the
  rollback has ALREADY failed — so the headline guard is BEHAVIOURAL against a
  session whose rollback and invalidate both hang forever, timed against the
  reserve that pays for them. Arithmetic alone would pass on a rail that never
  calls ``wait_for`` at all.
* Both directions of the cleanup are asserted. "The invalidate is bounded"
  passes on a rail that deleted the invalidate; "the invalidate happens" passes
  on a rail that never bounds it. The invalidate is load-bearing (``get_db_rw``
  commits after the handler returns, so a wedged connection turns the paused
  response back into the bare 500 it replaces) and so is the bound — neither may
  be traded for the other.
* The reason the constant is 0.5 lives in SQLAlchemy's source, so the guard that
  protects it READS SQLAlchemy's source rather than restating ~2.0 as a literal.
  A dialect upgrade that changed that number would otherwise silently invalidate
  the arithmetic here with nothing of ours able to notice.
* The module-wide AST form for the invalidate, matching the rollback guard next
  door: the point is to catch the NEXT failure arm someone writes, not to
  re-assert the one line that was fixed.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import time as _time

import pytest

from app.tasks import repair_polymarket_sport_category as rail

from tests.test_repair_polymarket_sport_category_q496 import _Session


# ---------------------------------------------------------------------------
# The arithmetic — on the DERIVED cleanup total, not on one of its halves
# ---------------------------------------------------------------------------


def test_the_cleanup_budget_counts_both_of_the_steps_that_run():
    """The cleanup is a rollback AND, when that fails, an invalidate.

    Charging a reserve for the rollback alone describes half of a path that
    executes as a whole — which is precisely how the invalidate came to be
    unaccounted for. The strict inequality against the rollback is the part that
    matters: it fails the moment someone re-collapses the total back onto one
    step.
    """
    assert rail.ROLLBACK_BUDGET_SECONDS > 0, "a zero rollback bound is not a bound"
    assert rail.INVALIDATE_BUDGET_SECONDS > 0, "a zero invalidate bound is not a bound"
    assert rail.cleanup_budget_seconds() == pytest.approx(
        rail.ROLLBACK_BUDGET_SECONDS + rail.INVALIDATE_BUDGET_SECONDS
    ), "the derived cleanup total is no longer the sum of the steps that run"
    assert rail.cleanup_budget_seconds() > rail.ROLLBACK_BUDGET_SECONDS, (
        "the cleanup total has collapsed back onto the rollback alone, which is "
        "the under-count CERT-673 found: the invalidate still runs and is still "
        "charged to the same reserve"
    )


def test_the_reserve_covers_the_write_and_the_WHOLE_cleanup_with_room_left():
    """The invariant the defect actually broke.

    ``POST_LOOP_NON_COUNT_RESERVE_SECONDS`` names three things: the last event's
    write, its cleanup, and the serialization plus the dependency's own commit
    that run after the handler returns. The third is unobservable from inside the
    request, so it is guarded as a REQUIRED MARGIN rather than left as whatever
    happens to be over — "it fits" with 0.0 to spare is how a reserve that has
    stopped covering its last named item still reads as passing.
    """
    charged = (
        rail.client_db_budget_seconds(rail.WRITE_BUDGET_SECONDS)
        + rail.cleanup_budget_seconds()
    )
    margin = rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS - charged
    assert margin > 0, (
        f"a failing write now costs {charged}s (derived write bound "
        f"{rail.client_db_budget_seconds(rail.WRITE_BUDGET_SECONDS)}s + cleanup "
        f"{rail.cleanup_budget_seconds()}s) out of a "
        f"{rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve — the request can "
        "pass the router wall and the operator gets H12 with no body and no cursor"
    )
    assert margin >= rail.POOL_ACQUIRE_SLACK_SECONDS, (
        f"only {margin}s is left of the reserve for response serialization and "
        "the dependency's own commit, which it also promises to cover"
    )


def test_bounding_the_cleanup_did_not_cost_the_working_loop_its_budget():
    """The fix is paid for by the terminal count, not by the drain.

    Raising the non-count slice while leaving ``POST_LOOP_RESERVE_SECONDS`` alone
    is what keeps that true, so it is asserted rather than described: if a later
    change pays for a cleanup step out of the total reserve instead, every
    healthy call quietly drains fewer events and no other guard here notices.
    """
    assert (
        rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS < rail.POST_LOOP_RESERVE_SECONDS
    ), "the non-count slice has swallowed the whole post-loop reserve"
    assert rail.budget_headroom_seconds() > 0, (
        "the rail's own worst case no longer fits under the router wall: "
        f"{rail.budget_headroom_seconds()}s of headroom"
    )


# ---------------------------------------------------------------------------
# Why 0.5 — read off SQLAlchemy, never restated as a literal
# ---------------------------------------------------------------------------


def _graceful_close_timeout_in_sqlalchemy() -> float:
    """The ``timeout=`` SQLAlchemy's asyncpg dialect gives its graceful close.

    RAISES rather than skipping or returning a default when it cannot find the
    number. A source-scan guard that shrugs when the source moves is worse than
    no guard: it keeps reporting green about a thing it has stopped reading.
    """
    from sqlalchemy.dialects.postgresql import asyncpg as _dialect

    tree = ast.parse(inspect.getsource(_dialect))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_terminate_graceful_close"
        ):
            for call in ast.walk(node):
                if isinstance(call, ast.Call):
                    for kw in call.keywords:
                        if kw.arg == "timeout" and isinstance(kw.value, ast.Constant):
                            return float(kw.value.value)
            raise AssertionError(
                "SQLAlchemy's `_terminate_graceful_close` no longer passes a "
                "literal `timeout=`; the ceiling this rail's invalidate bound is "
                "sized against has moved and this guard can no longer read it"
            )
    raise AssertionError(
        "SQLAlchemy's asyncpg dialect no longer defines "
        "`_terminate_graceful_close`. The invalidate path has been restructured, "
        "so `INVALIDATE_BUDGET_SECONDS` must be re-derived rather than trusted"
    )


def test_the_invalidate_bound_is_tighter_than_the_close_it_has_to_interrupt():
    """A bound looser than the thing it bounds is a decoration.

    ``session.invalidate()`` reaches a graceful ``close(timeout=N)`` inside
    SQLAlchemy's dialect. If this rail's own bound were >= N, the wait would
    always end on SQLAlchemy's terms and the constant here would buy nothing
    while reading as though it did.

    N is read out of SQLAlchemy's source rather than written here as ~2.0,
    because the entire point of owning this bound is that N is not ours to
    depend on — and a version bump that changes it should fail this, loudly,
    instead of silently re-breaking the reserve arithmetic.
    """
    ceiling = _graceful_close_timeout_in_sqlalchemy()
    assert rail.INVALIDATE_BUDGET_SECONDS < ceiling, (
        f"the rail bounds its invalidate at {rail.INVALIDATE_BUDGET_SECONDS}s but "
        f"SQLAlchemy's graceful close already ends at {ceiling}s, so the rail's "
        "bound never fires and the cleanup still costs whatever the dialect says"
    )


# ---------------------------------------------------------------------------
# The behaviour — a cleanup that cannot land must still hand back the response
# ---------------------------------------------------------------------------


class _CleanupWedged(_Session):
    """Both halves of the cleanup hang forever.

    The compounded case, deliberately: a rollback that does not land is the ONLY
    way the invalidate is reached, so a fake whose rollback succeeds could never
    exercise the bound at all.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.invalidates = 0

    async def rollback(self):
        self.rollbacks += 1
        await asyncio.Event().wait()  # never returns

    async def invalidate(self):
        self.invalidates += 1
        await asyncio.Event().wait()  # never returns


class _RollbackFailsFast(_Session):
    """The rollback raises immediately; the invalidate is fine."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.invalidates = 0

    async def rollback(self):
        self.rollbacks += 1
        raise RuntimeError("connection is wedged")

    async def invalidate(self):
        self.invalidates += 1


class _RollbackLands(_Session):
    """The healthy path: the rollback works, and an invalidate is COUNTABLE.

    Counting rather than absent, and the distinction is the whole guard. A fake
    with no ``invalidate`` at all cannot distinguish "the rail did not call it"
    from "the rail called it and the AttributeError was swallowed by the failure
    arm's own ``except Exception``" — which is exactly what a mutant that
    invalidates on the happy path does. Asserting on an attribute the fake never
    defines is a guard that passes for a reason unrelated to the rail.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.invalidates = 0

    async def invalidate(self):
        self.invalidates += 1


@pytest.mark.asyncio
async def test_a_cleanup_that_never_lands_still_fits_inside_its_reserve():
    """THE headline guard: the defect, measured.

    Both cleanup steps hang forever. Before the bound, this coroutine did not
    return until SQLAlchemy's own ~2.0s close gave up — and on production the
    reserve paying for it was 2.5s with 1.5s already spent, so the request went
    past the router wall and the operator lost the cursor.

    Timed against ``POST_LOOP_NON_COUNT_RESERVE_SECONDS`` rather than against
    ``cleanup_budget_seconds()`` because the reserve is the thing that must not
    be exceeded; asserting the tighter number would make the guard fail on
    ordinary scheduler jitter while telling us nothing more about the defect.
    """
    s = _CleanupWedged()

    began = _time.monotonic()
    try:
        await asyncio.wait_for(rail._safe_rollback(s), timeout=10.0)
    except asyncio.TimeoutError:  # pragma: no cover — the failure this guards
        raise AssertionError(
            "_safe_rollback never returned while both cleanup steps hung. "
            "Nothing in the rail can end that wait, so on production the Heroku "
            "router ends it instead: H12, no body, no cursor."
        ) from None
    elapsed = _time.monotonic() - began

    assert s.rollbacks == 1, "the rollback was not even attempted"
    assert s.invalidates == 1, (
        "the invalidate was never reached, so this guard proved nothing about "
        "the bound on it — the rollback must fail first for it to run at all"
    )
    assert elapsed < rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, (
        f"the cleanup took {elapsed:.2f}s, which does not fit the "
        f"{rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve that also owes a "
        "write, response serialization and the dependency's commit"
    )


@pytest.mark.asyncio
async def test_a_wedged_cleanup_is_not_raised_at_the_caller():
    """Every call site treats ``_safe_rollback`` as cleanup that always returns.

    It is awaited on failure arms that go on to build the paused response, so an
    exception escaping here would replace a cursor-carrying answer with the bare
    500 the arm exists to avoid — turning a bounded cleanup back into the defect
    it was written to fix.
    """
    s = _CleanupWedged()
    out = await asyncio.wait_for(rail._safe_rollback(s), timeout=10.0)
    assert out is None


@pytest.mark.asyncio
async def test_the_connection_is_still_invalidated_when_the_rollback_fails():
    """The negative arm, and it is not a formality.

    The invalidate is load-bearing: ``get_db_rw`` commits after the handler
    returns, so a session still holding a wedged connection turns the carefully
    built paused response into a bare 500. "Bound the invalidate" must never be
    satisfied by deleting it, and the timing guard above cannot tell those two
    apart.
    """
    s = _RollbackFailsFast()

    await rail._safe_rollback(s)

    assert s.rollbacks == 1
    assert s.invalidates == 1, (
        "a rollback that failed left the connection un-invalidated; the session "
        "still holds it and `get_db_rw`'s commit will fail on it"
    )


@pytest.mark.asyncio
async def test_a_rollback_that_lands_never_reaches_the_invalidate():
    """The healthy path must not throw connections away.

    Invalidating discards a pooled connection, so doing it after a rollback that
    worked would quietly shrink a pool of 20 on every recoverable timeout —
    turning a bounded failure into pool starvation, which is the failure CERT-670
    was about.

    The session here COUNTS invalidates instead of lacking the method, because
    the first version of this guard asserted ``not hasattr(s, "invalidates")``
    against a fake that never had the attribute — vacuous, and a mutation that
    moved the invalidate onto the happy path walked straight through it. The
    stray call raised AttributeError, the arm's own ``except Exception``
    swallowed it, and nothing observable changed. **An assertion about a fake is
    not an assertion about the rail.**
    """
    s = _RollbackLands()

    await rail._safe_rollback(s)

    assert s.rollbacks == 1
    assert s.invalidates == 0, (
        "a rollback that LANDED still had its connection invalidated. That "
        "discards a healthy pooled connection on every recoverable timeout, "
        "shrinking the pool toward the starvation CERT-670 bounded the rail for"
    )


# ---------------------------------------------------------------------------
# The module-wide forms — aimed at the NEXT failure arm, not the fixed line
# ---------------------------------------------------------------------------


def test_every_invalidate_in_this_rail_is_a_bounded_one():
    """Same shape as the rollback guard next door, for the same reason.

    A bare ``session.invalidate()`` is a graceful network close to a database
    that is not answering. The next person writing a failure arm will reach for
    it exactly as this rail did, so the guard is module-wide rather than pinned
    to the one call that was fixed.
    """
    tree = ast.parse(inspect.getsource(rail))

    bare: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "invalidate"):
            continue
        # Bounded == the invalidate is an ARGUMENT to `asyncio.wait_for`, so
        # walking wait_for's own subtree is what "wrapped" has to mean here.
        # Checking the enclosing line, or that `wait_for` appears somewhere in
        # the function, would be satisfied by a sibling call that is bounded
        # while this one is not.
        bare.append(f"line {node.lineno}")

    wrapped: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "wait_for"
        ):
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "invalidate"
                ):
                    wrapped.add(f"line {inner.lineno}")

    assert bare, (
        "no `invalidate()` call remains in this rail. It is load-bearing — "
        "without it a wedged connection turns the paused response into a bare "
        "500 — so its disappearance is a regression, not a simplification"
    )
    offenders = [site for site in bare if site not in wrapped]
    assert not offenders, (
        "these invalidates are unbounded, and an invalidate is a GRACEFUL close "
        "under the hood — a network round trip to the database that just stopped "
        f"answering: {offenders}"
    )


def test_the_response_publishes_the_cleanup_budget_it_now_enforces():
    """The operator reading a paused response has to be able to see the bound.

    Published as the derived total rather than as its two halves for the same
    reason the guards assert the total: the halves are only meaningful summed,
    and printing one of them is what made the other easy to forget.
    """
    source = inspect.getsource(rail)
    assert '"cleanup_budget_s": cleanup_budget_seconds()' in source, (
        "the diagnostics block no longer publishes the derived cleanup budget"
    )
