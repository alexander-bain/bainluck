"""#7987 — a board the venue answered stops offering a live price on the question.

THE DEFECT THESE GUARD. `https://bainluck.com/events/14780545`, six and a half
hours after Rams 28 – Giants 6, FINAL. Under Additional Markets the *1st
Touchdown* board served:

    Davante Adams                            Won
    Puka Nacua                    last quote  9%
    Jordan Whittington            last quote  3%
    CJ Daniels                    last quote  1%
    Blake Corum                             Lost
    ... 23 more, all Lost, all with no price

A question that has been answered still offered three players a live-looking
chance of scoring the touchdown Adams had already scored.

THE RENDER IS RIGHT, WHICH IS WHY THIS IS A WRITER FIX. `outcomeRowVerdict`
withholds a verdict it was never given (#4788/#6138) — inventing `Lost` there
would be the worse bug. The three legs read `finalized` / `result: "scalar"` at
Kalshi with `yes_bid: None`: the venue answered on a NUMBER, so there is no side
to grade, and #1852 established that grading a scalar as a loss poisons the
calibration curve. That refusal is correct and is untouched. The residual it
leaves is the price, and the price is what a reader actually reads.

All four Kalshi graders in `backfill_winners` had the same shape: ask
`kms.gradeable_winner`, correctly refuse on None, count it, `continue` — and the
fossil survives. That is "a gate that only refuses to WRITE leaves the old number
exactly where it was", the lesson #5031, #5273 and #5771 each paid for.

WHY THESE ARE PREDICATE + STRING GUARDS AND NOT DATABASE GUARDS. Every
real-Postgres gate in this repo is env-gated and SKIPS in CI, and a skipped guard
is not a guard — `test_settled_outcomes_carry_no_price_5246` says so at length and
this file follows it. So the decision (WHICH legs) is guarded behaviourally
through the real predicate, where a fake cannot flatter it, and the statement
(WHAT happens to them) is pinned on the real composed SQL the call sites splice.

🔴 THE ONE ASSERTION THIS FILE REFUSES TO MAKE is "the withdrawal ran and the row
is NULL now". Nothing here owns a database, so such a test could only assert
against a fake session that returns whatever it was told to — a property of the
fixture, not of the ship. `test_the_leg_is_withheld_not_dropped` in #7747's file
was exactly that mistake (CodeQL found it as two unused locals), and the lesson is
recorded rather than repeated.
"""

import ast
import importlib
import inspect
import re

import pytest

from app.utils.kalshi_market_status import (
    RESULT_CARRYING_STATUSES,
    settled_without_verdict,
)
from app.utils.settled_price import ungraded_settlement_withdraw_sql


# ── 1. THE PREDICATE: which legs the venue has actually answered ─────────────
#
# Behavioural, on the real function. Every case below is a state Kalshi's own
# measured status table (`kalshi_market_status`, MEASURED_ON 2026-08-13) says
# exists.


@pytest.mark.parametrize("status", sorted(RESULT_CARRYING_STATUSES))
def test_a_declared_status_on_a_scalar_result_is_the_shipped_population(status):
    """`finalized`/`determined` + `scalar` — the specimen, and both its statuses.

    Parametrized off the frozenset rather than spelled, so a future widening of
    `RESULT_CARRYING_STATUSES` is covered the day it lands instead of silently
    leaving a status unguarded.
    """
    assert settled_without_verdict(status, "scalar") is True


@pytest.mark.parametrize("result", ["yes", "no", "YES", " No "])
def test_a_gradeable_result_is_not_withdrawn_because_the_grader_handles_it(result):
    """A leg the venue graded is the GRADER's row, not this one's.

    If this returned True the withdrawal would race the settling UPDATE for the
    same leg in the same pass. It delegates to `gradeable_winner` rather than
    re-deriving "is this a side", so the case-folding and stripping are proved to
    be the same ones, from one implementation.
    """
    assert settled_without_verdict("finalized", result) is False


def test_a_closed_market_with_no_result_is_still_trading_and_is_left_alone():
    """`closed` = "trading over, outcome NOT yet called" — the measured table.

    This is the single most important refusal in the file. `closed` is in
    `TERMINAL_STATUSES` but carries no result, and its presence there is #1818's
    open question, deliberately untouched by this ship. Withdrawing here would
    blank the price on markets the venue has simply not called yet.
    """
    assert settled_without_verdict("closed", "") is False


def test_the_status_clause_is_required_a_stray_scalar_on_closed_is_refused():
    """THE CONTROL FOR CLAUSE ONE, and it fails if the status test is dropped.

    A `closed` market does not carry a result — the measured table says so — so a
    non-empty one here is data we do not understand. Trusting it would make the
    result field alone sufficient, which is the widening this test exists to stop.
    """
    assert settled_without_verdict("closed", "scalar") is False


@pytest.mark.parametrize("result", ["", "   ", None])
def test_the_result_clause_is_required_a_declared_status_with_no_result_is_refused(
    result,
):
    """THE CONTROL FOR CLAUSE TWO, and it fails if the result test is dropped.

    `finalized` with no result is a combination the measured table says does not
    occur; if the venue ever produces one it is ambiguous, not evidence, and
    gotcha #53's rule is that an absence is never recorded as a fact.
    """
    assert settled_without_verdict("finalized", result) is False


@pytest.mark.parametrize("status", ["active", "inactive", "", None, "settled"])
def test_an_undeclared_status_is_refused_whatever_the_result_says(status):
    """Includes `settled` — in `TERMINAL_STATUSES`, never observed, never declares.

    `is_terminal` would admit it; `has_declared_result` does not, and this
    predicate is built on the narrower one. A test that only covered `active`
    would pass against the wrong helper.
    """
    assert settled_without_verdict(status, "scalar") is False


def test_an_unknown_future_result_value_is_withdrawn_not_guessed():
    """A result we have never seen, on a declared status, is still an answer.

    The venue has spoken and the contract is not trading; we cannot name the
    side. That is precisely the population. Pinned so a later `GRADEABLE_RESULTS`
    reader cannot narrow this to the literal string "scalar" and quietly drop
    whatever Kalshi invents next.
    """
    assert settled_without_verdict("finalized", "range") is True


# ── 2. THE STATEMENT: what happens to those legs ─────────────────────────────


def _withdraw_sql() -> str:
    return " ".join(ungraded_settlement_withdraw_sql().split())


def test_the_withdrawal_never_grades_and_never_ungrades():
    """NOT ONE VERDICT COLUMN IS IN THE SET LIST.

    The whole licence for this write is that it touches the price and nothing
    else: #1852's refusal to grade a scalar stands, so writing `is_winner` here
    — in either direction — would overturn a standing ruling from inside a price
    fix. Asserted on the SET list alone, because `is_winner` legitimately appears
    in the WHERE.
    """
    sql = _withdraw_sql()
    set_list = sql.split("SET", 1)[1].split("FROM", 1)[0]
    assert "is_winner" not in set_list
    assert "resolution_source" not in set_list


def test_the_withdrawal_refuses_any_leg_that_carries_a_verdict():
    """`is_winner IS NULL` — stricter than #5246's "not a winner".

    A leg graded between the venue read and this write must survive untouched,
    and a graded LOSER carries a real settlement price (0.0) that is a result,
    not a fossil. Dropping this clause would un-price settled rows — gotcha #21,
    and the exact harm #5246 exists to prevent.
    """
    assert "fo.is_winner IS NULL" in _withdraw_sql()


def test_the_withdrawal_is_idempotent_on_a_leg_already_cleared():
    """A board stays in band 1 for three days and is re-read every few hours.

    Without this the statement would restamp `last_updated` and `price_changed_at`
    on every pass, advertising a price change that is not happening — and
    `last_updated` is a liveness gate other code reads.
    """
    assert "fo.current_probability IS NOT NULL" in _withdraw_sql()


def test_the_withdrawal_cannot_reach_another_venues_rows():
    """Kalshi's status vocabulary decided this; only Kalshi's rows may be written.

    The predicate upstream reads Kalshi statuses. Polymarket legs share the
    `futures_outcomes` table and a ticker collision is not hypothetical (Q487:
    `external_id` is NOT unique), so the join is the scope.
    """
    assert "fm.source = 'kalshi'" in _withdraw_sql()


@pytest.mark.parametrize("column", ["calibration_probability", "opening_probability"])
def test_no_calibration_input_is_written(column):
    """Gotcha #144: the curve price is COALESCE(calibration_probability, opening_probability).

    Neither is in the statement at all — not in the SET list and not in the
    WHERE. The population is 100% `resolution_source IS NULL` (measured on
    production 2026-09-22), which `precompute_calibration` states never reaches
    `ranked_outcomes`; this guard makes that independent of the measurement
    staying true.
    """
    assert column not in _withdraw_sql()


def test_the_bind_name_is_honoured_so_a_call_site_cannot_bind_two_lists():
    """One call site already binds `:t`; the rest bind `:tickers`.

    A helper that hard-coded `:tickers` would force that site to pass BOTH names
    or rename its existing binds — the shape in which a statement quietly
    executes against the wrong list.
    """
    assert "ANY(:t)" in " ".join(ungraded_settlement_withdraw_sql("t").split())
    assert ":tickers" not in ungraded_settlement_withdraw_sql("t")
    assert "ANY(:tickers)" in _withdraw_sql()


# ── 3. THE POPULATION: one clause, inherited by every grader ─────────────────


def _module_code() -> str:
    """`backfill_winners`' source with comments stripped.

    Two traps, both already paid for in this repo. (1) `from app.tasks import
    backfill_winners` can yield a Celery `PromiseProxy` whose source is a
    427-character wrapper in which every pattern below finds nothing and every
    assertion passes — `importlib.import_module` cannot resolve to the task.
    (2) A source scan counts the COMMENT that explains the fix, so a guard
    counting call sites would count the prose describing them.
    """
    src = inspect.getsource(importlib.import_module("app.tasks.backfill_winners"))
    return "\n".join(
        line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        for line in src.splitlines()
    )


def test_every_grader_that_refuses_to_grade_also_withdraws_the_price():
    """THE "POPULATION, NOT A PLACE" GUARD — the one that catches a FIFTH grader.

    `settled_price`'s own docstring records why this file exists in this shape:
    the first version of #5246 fixed one settling statement and was inert on
    every path a reader's row actually travels. The same trap is open here — four
    graders, one shape — so the invariant is stated as a count rather than as
    four separate assertions that a new site would simply not be added to.

    Deliberately `==` and not `>=`: a new `gradeable_winner` reader that does not
    withdraw is the regression, and `>=` would pass for it.
    """
    code = _module_code()
    asks = len(re.findall(r"\bgradeable_winner\s*\(", code))
    withdraws = len(re.findall(r"\bsettled_without_verdict\s*\(", code))
    assert asks >= 4, f"expected the four known Kalshi graders, found {asks}"
    assert withdraws == asks, (
        f"{asks} call sites ask `gradeable_winner` but only {withdraws} withdraw "
        "the price when it refuses — a grader that refuses to grade and leaves "
        "the fossil standing is #7987 reopening on that path"
    )


def test_the_forward_capture_sweep_does_not_count_a_withdrawal_as_a_grade():
    """`page_resolved` drives `empty_pages`, which ends the sweep and moves its cursor.

    A page that only withdrew a fossil must not read as a page that graded
    something: that would reset the termination heuristic and change how far the
    sweep walks, which is a behaviour change well outside this ship. The
    withdrawal therefore lands in its own counter.
    """
    code = _module_code()
    assert "settled_stats[\"ungraded_price_withdrawn\"]" in code
    withdraw_block = code.split("if withdraw_t:", 1)[1].split("await sess.commit()", 1)[0]
    assert "page_resolved" not in withdraw_block


def test_no_withdrawal_is_gated_on_anything_but_having_legs_to_withdraw():
    """FOUND BY A SURVIVING MUTANT, which is the only reason this test exists.

    The mutation pass added `and False` to one withdrawal's condition — the ship
    switched off in place — and every guard in this file stayed green, because
    they all read the statement and its position and none read the condition that
    decides whether it runs at all. A disabled ship and a shipped ship are
    textually almost identical, and that is exactly the shape nobody notices in
    review.

    `not dry_run` is the one permitted conjunct: it is the call site's own
    existing contract, shared with every other write in that function.
    """
    conditions = [
        line.strip()
        for line in _module_code().splitlines()
        if re.match(r"\s*if\b.*\bwithdraw_t(ickers)?\b.*:\s*$", line)
    ]
    # The two session-OPENERS are a separate, equally load-bearing fact: a batch
    # in which the venue graded nothing and answered everything on a number must
    # still open a session. Were they left reading `yes_tickers or no_tickers`,
    # the withdrawal below them would be unreachable on exactly the boards this
    # ship is for.
    openers = [c for c in conditions if "yes_tickers" in c]
    guards = [c for c in conditions if "yes_tickers" not in c]

    assert len(openers) == 2, f"expected two session-openers, found {openers}"
    for opener in openers:
        assert "withdraw_tickers" in opener

    allowed = {
        "if not dry_run and withdraw_tickers:",
        "if withdraw_tickers:",
        "if withdraw_t:",
    }
    assert len(guards) == 4, f"expected four withdrawal sites, found {guards}"
    assert set(guards) <= allowed, f"a withdrawal is gated on something else: {guards}"


def _grading_pass_code() -> str:
    """`_backfill_kalshi_winners`' own body, comments stripped.

    MODULE source order is not a proxy for execution order, and this guard used
    to assume it was. `_module_code().index('status="resolved"')` finds the FIRST
    such write anywhere in a 4,000-line module — not the one inside the pass it
    means to constrain. Any helper DEFINED near the top of the file that happens
    to contain that string moves the anchor tens of thousands of characters and
    the guard reports the ordering reversed while the order that actually matters
    has not moved at all. That is not hypothetical: it reddened CI shard 4 as
    `assert 54755 < 11371` on a branch that never touched the sequence, and #8022
    reaches the same state from the other direction — it adds
    `_resolve_purge_confirmed_markets`, defined near the top beside its sibling
    cursor readers but CALLED at the very end of the pass, which puts that
    helper's write 68,000 characters BEFORE the withdrawal it is meant to follow.

    A guard whose anchor can be relocated by an unrelated DEFINITION is aimed at
    the file, not at the behaviour. So scope it to the one function whose
    STATEMENT order IS its execution order, and assert every way a board can
    become settled against it (the two arms below). Inside that body the real
    sequence is withdrawal, then #7870's in-loop flip, then #8022's post-loop
    call — which is what those two arms pin.

    THE AST RUNS ON THE RAW SOURCE, AND THE STRIPPING HAPPENS AFTER. Not a style
    choice: `_module_code`'s comment stripper is a plain `line.split("#", 1)[0]`,
    which is right for counting call sites and WRONG as parser input — it cuts
    inside any string literal containing a `#`, and this module has one
    (`"Polymarket total score resolution (#…"`), so `ast.parse` on the stripped
    text dies with an unterminated-string SyntaxError 4,000 lines in. Parse what
    Python would parse, then strip what a reader would ignore.
    """
    raw = inspect.getsource(importlib.import_module("app.tasks.backfill_winners"))
    fn = next(
        node
        for node in ast.walk(ast.parse(raw))
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == "_backfill_kalshi_winners"
    )
    segment = ast.get_source_segment(raw, fn)
    assert segment, "could not recover `_backfill_kalshi_winners` from its own module"
    return "\n".join(
        line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        for line in segment.splitlines()
    )


def test_the_withdrawal_precedes_the_status_flip_to_resolved():
    """A board must never BECOME settled while still holding a live-looking number.

    The flip at `#7870` is what makes the frontend treat the board as settled
    (`gradedWinner()` returns null unless `status === "resolved"`), so ordering is
    not cosmetic: reversed, every newly-resolved board would serve the fossil for
    one full cycle before the next pass cleared it.
    """
    code = _grading_pass_code()
    withdraw_at = code.index("ungraded_settlement_withdraw_sql()")
    flip_at = code.index('status="resolved"')
    assert withdraw_at < flip_at


def test_the_purge_confirm_rail_obeys_the_same_ordering():
    """#8022 is a SECOND way a board becomes settled, and the rule binds it too.

    The arm above would not notice it: that one anchors on `status="resolved"`,
    which appears inside the purge rail's own helper rather than at its call
    site, so the ordering of the call is invisible there. `_resolve_purge_…` runs
    after the whole grading pass — including every withdrawal — and this pins
    that rather than leaving it to the reader.

    (The rail additionally cannot settle a board holding a fossil at all: its
    precondition requires EVERY leg to carry an authoritative resolution source,
    and a leg the venue settled on a number carries none. This arm guards the
    ordering; that is the belt to its braces.)
    """
    code = _grading_pass_code()
    withdraw_at = code.index("ungraded_settlement_withdraw_sql()")
    purge_at = code.index("_resolve_purge_confirmed_markets(")
    assert withdraw_at < purge_at
