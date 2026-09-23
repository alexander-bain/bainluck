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

🔴 ROUND TWO — CERT-674 CAME BACK **BLOCK**, AND IT WAS RIGHT
=============================================================

Round one drew the obvious conclusion from all of the above and CAPPED the
invalidate at 0.5s with ``asyncio.wait_for``, arguing the cancellation was safe
because SQLAlchemy's ``_terminate_handled_exceptions()`` names ``CancelledError``
and force-closes the driver before re-raising.

The driver half of that argument is true. It is not the half that matters. The
certifier reproduced the real thing against an actual ``AsyncSession`` and
``QueuePool``: the helper returned in 1.012s, asyncpg's terminate ran — and
``pool.checkedout()`` was **1 before, 1 after, and still 1** after a
dependency-equivalent ``commit()`` + ``close()``. Cancellation unwinds SQLAlchemy
between the driver terminate and the point where ``_ConnectionRecord`` is cleared
and ``_ConnectionFairy`` checks back in, and nothing later repairs it. Every
failure cycle permanently costs one of the 20 app pool slots — pool starvation,
which is *exactly* the failure CERT-670 widened this rail's bounds to prevent,
re-entered through the cleanup meant to protect against it.

🆕 **CANCELLING AN AWAIT DOES NOT ROLL BACK THE BOOKKEEPING IT WAS IN THE MIDDLE
OF.** "The resource is released either way" is a claim about the resource, never
about the ledger that tracks it.

🆕 **AND: A FAKE THAT IS MORE HOSTILE THAN REALITY ARGUES FOR A FIX THE REAL
SYSTEM DOES NOT NEED.** Round one's ``_CleanupWedged`` had the invalidate hang
*forever*, which made a cap look necessary. A real ``session.invalidate()``
cannot hang forever — the dialect's own ``close(timeout=2)`` bounds it. The fake
was the argument for the defect.

So the cleanup is now PAID FOR rather than interrupted: ``INVALIDATE_BUDGET_
SECONDS`` stopped being a timeout and became an accounted bill, sized from
SQLAlchemy's ceiling, and the reserves that charge it grew to fit.

WHAT EACH GUARD HAS TO BE SHAPED LIKE TO BE WORTH ANYTHING
==========================================================

* The cleanup's cost is invisible from a passing run — it only elapses when the
  rollback has ALREADY failed — so the headline guard is BEHAVIOURAL against a
  session whose rollback hangs and whose invalidate is slow but self-limiting,
  timed against the reserve that pays for it. Arithmetic alone proves nothing
  about what runs.
* That guard asserts the invalidate **COMPLETED**, not merely that it was called.
  Timing alone passed on the round-one code that leaked a slot — cancelling a
  cleanup early is a very effective way to make it fast. "It finished in time"
  says nothing about whether it finished. The pool-slot leak itself is invisible
  to every fake here (it needs a real ``QueuePool``), so completion is the
  strongest observable this file can carry, and the AST guard covers the shape.
* Both directions of the cleanup are asserted. "The invalidate is accounted for"
  passes on a rail that deleted the invalidate; "the invalidate happens" passes
  on a rail that cancels it. The invalidate is load-bearing (``get_db_rw``
  commits after the handler returns, so a wedged connection turns the paused
  response back into the bare 500 it replaces) — neither may be traded away.
* The reason the constant is 2.0 lives in SQLAlchemy's source, so the guard that
  protects it READS SQLAlchemy's source rather than restating ~2.0 as a literal —
  and now asserts our number **covers** that ceiling rather than undercutting it.
  A dialect upgrade that raised it would otherwise silently make every reserve
  downstream too small, with nothing of ours able to notice.
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


def test_paying_for_the_cleanup_did_not_cost_the_working_loop_its_budget():
    """The drain still drains as much as before, and the wall still fits.

    🔴 CERT-674 CHANGED THIS GUARD'S PREMISE, so the old version of it would now
    be a lie. Round one could assert that ``POST_LOOP_RESERVE_SECONDS`` was
    UNCHANGED, because capping the invalidate kept the whole cost inside the
    non-count slice. Paying the invalidate's real price does not fit there, so
    the total reserve had to move too — and a guard still asserting "unchanged"
    would simply fail, while a guard quietly deleted would hide the trade.

    What actually has to hold is narrower and is what is asserted here:

    * the terminal count keeps a real slice (the non-count reserve has not eaten
      the whole thing) — it is degradable, not deletable;
    * ``DEADLINE_SECONDS`` is what decides how many events a healthy call drains,
      and nothing in this repair touches it;
    * the worst case still fits under the router wall, which is the invariant
      separating "a partial answer WITH its cursor" from "H12 with no body".
    """
    assert (
        rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS < rail.POST_LOOP_RESERVE_SECONDS
    ), "the non-count slice has swallowed the whole post-loop reserve"

    count_slice = (
        rail.POST_LOOP_RESERVE_SECONDS - rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS
    )
    assert count_slice >= 1.0, (
        f"the terminal count is down to {count_slice}s. It is explicitly "
        "degradable — it reports itself unmeasured rather than reporting zero — "
        "but squeezing it to nothing means it can never once succeed, which is a "
        "different thing from degrading"
    )

    assert rail.budget_headroom_seconds() > 0, (
        "the rail's own worst case no longer fits under the router wall: "
        f"{rail.budget_headroom_seconds()}s of headroom. Paying for the cleanup "
        "has to come out of the reserve, not out of the wall."
    )


# ---------------------------------------------------------------------------
# Why 2.0 — read off SQLAlchemy, never restated as a literal
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


def test_the_invalidate_budget_COVERS_the_close_it_must_not_interrupt():
    """CERT-674 inverted this guard, and the inversion is the whole repair.

    Round one asserted ``INVALIDATE_BUDGET_SECONDS < ceiling`` — that the rail's
    bound was TIGHTER than SQLAlchemy's graceful close, so it would actually fire.
    It fired, and firing is what broke it: the cancellation unwinds SQLAlchemy
    between asyncpg's terminate and the pool check-in, so the connection dies with
    its pool slot still checked out and 20 failures starve the app.

    So the constant stopped being a bound and became a bill, and the guard has to
    assert the opposite thing: that the number we CHARGE covers the cost we will
    actually incur. Under-charging here does not leak a slot — it silently
    re-opens the reserve over-commitment CERT-673 closed, which arrives as the
    H12-with-no-body instead.

    N is still read out of SQLAlchemy's source rather than written here as ~2.0,
    for the same reason as before and one new one: this rail now DEPENDS on that
    number instead of racing it, so a version bump that raises it must fail here
    loudly rather than quietly making every reserve downstream too small.
    """
    ceiling = _graceful_close_timeout_in_sqlalchemy()
    assert rail.INVALIDATE_BUDGET_SECONDS >= ceiling, (
        f"the rail budgets {rail.INVALIDATE_BUDGET_SECONDS}s for an invalidate whose "
        f"graceful close alone can take {ceiling}s. Do NOT fix this by bounding the "
        "invalidate — that is CERT-674's pool-slot leak. Raise this constant and the "
        "reserves that charge it."
    )


def test_the_invalidate_is_never_wrapped_in_a_cancelling_wait():
    """The defect CERT-674 blocked, guarded at the shape that caused it.

    A pool-slot leak is invisible to every fake session in this file — the
    certifier needed a real ``AsyncSession``/``QueuePool`` to see
    ``pool.checkedout()`` stick at 1 — so the guard that can run here has to
    assert the *cause* rather than the symptom: no ``invalidate()`` call in this
    rail sits inside an ``asyncio.wait_for``.

    Deliberately an AST walk over the real module and not a substring search: a
    grep for "wait_for" would go green the moment someone reformatted the call
    across two lines, and this has to survive being re-broken by a well-meaning
    edit that "just adds a timeout for safety".

    BOTH cancellation forms are rejected, and the second one is the reason this
    guard is not just the first one. ``asyncio.wait_for(session.invalidate(), t)``
    is the shape round one used, but ``async with asyncio.timeout(t):`` cancels
    the body in exactly the same way and would sail past a guard that only knew
    about ``wait_for`` — a mutant that evades the guard while reproducing the
    defect is the one worth writing the guard against.
    """
    tree = ast.parse(inspect.getsource(rail))

    # `async with asyncio.timeout(...)` / `asyncio.timeout_at(...)` around an
    # invalidate cancels it just as `wait_for` does.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        guards_a_timeout = any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr in {"timeout", "timeout_at"}
            for item in node.items
        )
        if not guards_a_timeout:
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "invalidate"
            ):
                raise AssertionError(
                    f"`session.invalidate()` at line {inner.lineno} is inside an "
                    "`asyncio.timeout()` block. That cancels it exactly as "
                    "`wait_for` does, and CERT-674's pool-slot leak is a property "
                    "of the CANCELLATION, not of which API delivered it."
                )

    invalidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "invalidate"
    ]
    assert invalidates, (
        "no `invalidate()` call found in the rail at all — the cleanup's second "
        "step has been removed or renamed, so this guard is no longer reading "
        "the thing it was written to protect"
    )

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "wait_for"
        ):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "invalidate"
            ):
                raise AssertionError(
                    "`session.invalidate()` is wrapped in `asyncio.wait_for` again. "
                    "CERT-674 reproduced this against a real QueuePool: the driver "
                    "terminates but `pool.checkedout()` stays at 1 forever, because "
                    "cancellation unwinds SQLAlchemy before `_ConnectionFairy` checks "
                    "the record back in. Each failure cycle leaks one of 20 slots. "
                    "The cost is ACCOUNTED for in POST_LOOP_NON_COUNT_RESERVE_SECONDS; "
                    "it must not be interrupted."
                )


# ---------------------------------------------------------------------------
# The behaviour — a cleanup that cannot land must still hand back the response
# ---------------------------------------------------------------------------


#: How long the fake invalidate takes, and the number is load-bearing in a way
#: that is easy to get wrong — I got it wrong once on the way here.
#:
#: It must EXCEED the 0.5s bound Q498 round one put on the invalidate, so that
#: re-introducing that bound cancels this fake mid-flight and
#: `invalidate_completed` stays False. At 0.6 it does. **A fake that finishes
#: faster than the bound under test cannot observe that bound at all** — the
#: first version of this constant was small enough that the completion assertion
#: passed against the very defect it was written for, which is the same vacuous
#: -guard trap this file's round-one battery caught in `hasattr`.
#:
#: It is deliberately NOT raised to ~2.0 to also catch a bound set at the
#: ACCOUNTED cost. That would add two seconds to the suite to cover a case the
#: AST guard above already rejects outright, and a bound at the accounted cost is
#: not the historical defect — the tight one is.
_SLOW_INVALIDATE_SECONDS = 0.6


class _CleanupWedged(_Session):
    """The rollback hangs forever; the invalidate is SLOW BUT SELF-LIMITING.

    The compounded case, deliberately: a rollback that does not land is the ONLY
    way the invalidate is reached, so a fake whose rollback succeeds could never
    exercise this path at all.

    🔴 CERT-674 CHANGED WHAT THIS FAKE MODELS, and the change is load-bearing.
    Round one had the invalidate hang forever too, which made a bound look
    necessary — but a real ``session.invalidate()`` CANNOT hang forever: it
    reaches SQLAlchemy's graceful ``close(timeout=2)``, so the dialect bounds it
    for us at ~2.0s. Modelling it as unbounded justified the 0.5s cap, and the cap
    is what leaked the pool slot. A fake that is more hostile than reality is not
    a stricter test; it is a test of a different system, and it argues for fixes
    the real one does not need.

    ``invalidate_completed`` is the observable that matters. It is set at the END,
    so a cancelled invalidate leaves it False — which is the only way a fake in
    this file can see CERT-674's defect at all (the pool-slot leak itself needs a
    real ``QueuePool``).
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.invalidates = 0
        self.invalidate_completed = False

    async def rollback(self):
        self.rollbacks += 1
        await asyncio.Event().wait()  # never returns

    async def invalidate(self):
        self.invalidates += 1
        await asyncio.sleep(_SLOW_INVALIDATE_SECONDS)
        self.invalidate_completed = True


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

    🔴 CERT-674 added the second assertion, and it is the one with teeth. The
    timing assertion alone passed for the 0.5s-capped version that leaked a pool
    slot on every failure — it would, because cancelling the cleanup early is a
    very effective way to make it fast. "It finished in time" says nothing about
    whether it finished.
    """
    s = _CleanupWedged()

    began = _time.monotonic()
    try:
        await asyncio.wait_for(rail._safe_rollback(s), timeout=10.0)
    except asyncio.TimeoutError:  # pragma: no cover — the failure this guards
        raise AssertionError(
            "_safe_rollback never returned while the rollback hung. Nothing in "
            "the rail can end that wait, so on production the Heroku router ends "
            "it instead: H12, no body, no cursor."
        ) from None
    elapsed = _time.monotonic() - began

    assert s.rollbacks == 1, "the rollback was not even attempted"
    assert s.invalidates == 1, (
        "the invalidate was never reached, so this guard proved nothing about "
        "the cleanup — the rollback must fail first for it to run at all"
    )
    assert s.invalidate_completed, (
        "the invalidate was STARTED but never finished, which means something "
        "cancelled it — CERT-674's pool-slot leak. The connection is discarded "
        "either way, but SQLAlchemy never checks its record back into the pool, "
        "so each failure cycle permanently costs one of 20 slots. The invalidate "
        "must be allowed to complete and PAID FOR in the reserve, not interrupted."
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


# 🔴 REMOVED BY CERT-674: `test_every_invalidate_in_this_rail_is_a_bounded_one`.
# It asserted that every `invalidate()` in this rail IS wrapped in
# `asyncio.wait_for` — the precise shape that leaks a pool slot. Its replacement
# is `test_the_invalidate_is_never_wrapped_in_a_cancelling_wait` above, which
# asserts the inverse and carries this one's "the invalidate still exists"
# assertion too, so nothing is lost by deleting rather than weakening it.
#
# Recorded rather than silently dropped: a guard that has to be INVERTED is the
# most interesting artefact a blocked round produces. It is the point where the
# previous round's model of the system was wrong, written down and executable.


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
