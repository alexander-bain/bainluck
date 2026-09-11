"""#5246 — a settled outcome carries its settlement, not the last price anyone paid.

THE DEFECT THESE GUARD. On US Open men's semifinal day the winner card offered
48 names with four players alive, and priced Alexander Zverev at 34% while
Kalshi said 49.5%. The four survivors' stored probabilities were exactly right
(sum 1.0100); the 44 eliminated players were already graded
`is_winner=false, resolution_source='api_settlement'` and still carried the last
number anyone paid for them, so the column summed to 1.4800 and the rail's
renormalisation taxed every live outcome by a third.

The grade landed and the price did not. Three things had to be true at once:

  1. the settling statement wrote the verdict and not the price,
  2. the price poller's settled refusal tested for a CROWN, not for a GRADE, so
     a resolved-NO leg stayed eligible for re-pricing forever, and
  3. no poll could correct either, because the venue quotes nothing on a
     `finalized` market and every price site refuses a None.

WHY THESE ARE STRING GUARDS AND NOT DATABASE GUARDS. Every real-Postgres gate in
this repo is env-gated (`CALIBRATION_TEST_DATABASE_URL` in 24 files,
`SEARCH_TEST_DATABASE_URL` in 122) and SKIPS in CI, which has no Postgres
service. A skipped guard is not a guard. So these read the real objects the call
sites splice — `_SETTLED_PRICE_SET_SQL`'s return value and `ELIGIBLE_OUTCOMES_SQL`
— never a re-derivation of them.

🔴 AND THEY ARE NOT WHOLE-STATEMENT GUARDS, WHICH THEY WERE FOR ONE CI RUN. The
first draft hoisted both settling UPDATEs into a `settled_grade_update_sql()`
helper precisely so a test could read the composed string. Three of this repo's
existing guards went red at once, and every one of them was right:

  * `test_kalshi_forward_capture_grade_p1004` — the helper needed a
    `won = result == "yes"` line to pick a branch, and that is the two-state
    grade CAL-P1004 exists to keep out of this file (it maps `""` and `"scalar"`
    onto "this outcome lost", at the top authority rung).
  * `test_touch_stamp_provenance_live077` — moving `last_updated=NOW()` inside a
    helper put it where that scan cannot classify it.
  * `test_duplicate_condition_leg_never_wins_q487` — its positive control counts
    the in-class SQL concatenations by hand-classified site, and merging two into
    one shrank the population, which is how a source-scan guard goes vacuous.

The statements are inline because this repo READS them inline. So the
composition is proved where the repo already proves it, and the guard below
asserts only what is genuinely new: the clause's content, and that both call
sites splice it with DIFFERENT prices.
"""

import re

import pytest


# --- the producer: the grade and the price are one settlement ----------------


def _task_module_source():
    """The source of the `backfill_winners` MODULE — never the Celery task.

    🔴 `from app.tasks import backfill_winners` does NOT reliably give the
    module. `app/tasks/__init__.py` defines a Celery task of the same name, so
    the attribute on the package is a `celery.local.PromiseProxy` whose
    `inspect.getsource` is the 427-character task wrapper — in which every
    pattern below finds nothing and every `not in` assertion passes.

    It is worse than a plain bug because it is ORDER-DEPENDENT: importing the
    module anywhere earlier in the process also binds it as an attribute of the
    package, so the `from` form yields the real module in a full run and the
    proxy when the file runs alone. That is a guard that passes both ways —
    green in CI, vacuous under sharding, and unfalsifiable by re-running it.

    `importlib.import_module` names the module and cannot resolve to the task.
    """
    import importlib
    import inspect

    return inspect.getsource(importlib.import_module("app.tasks.backfill_winners"))


def _task_module_code():
    """`_task_module_source()` with comments stripped.

    A source scan that reads PROSE grades the prose. This file's own first
    version of the CAL-P1004 assertion below failed on the comment that
    *explains* the fix — the string `rs == "yes"` appears there describing what
    the code used to be. Mirrors `test_kalshi_forward_capture_grade_p1004`'s
    `_code_lines`, which strips for the same reason and says so.
    """
    out = []
    for line in _task_module_source().splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line.split("  #")[0])
    return "\n".join(out)


def _price_set(price):
    from app.tasks.backfill_winners import _SETTLED_PRICE_SET_SQL

    return _SETTLED_PRICE_SET_SQL(price)


def _settlement_call_sites():
    """The two `_SETTLED_PRICE_SET_SQL(...)` arguments in the settled-events sweep.

    A source scan, deliberately, and in the same form the three guards that
    already police this file use (`test_duplicate_condition_leg_never_wins_q487`
    reads it with `ast`, `test_touch_stamp_provenance_live077` and
    `test_kalshi_forward_capture_grade_p1004` read it as text). The first draft
    of this ship hoisted both UPDATEs into a helper so a test could read the
    composed string, and all three of those guards went red — the statements are
    inline because this repo reads them inline. So the composition is proved
    where the repo proves it, and this asserts only that both call sites exist
    and ask for DIFFERENT prices.
    """
    return re.findall(r'_SETTLED_PRICE_SET_SQL\("([01]\.0)"\)', _task_module_source())


@pytest.mark.parametrize("price", ["0.0", "1.0"])
def test_the_settlement_price_clause_writes_the_price(price):
    """The clause the settling UPDATEs splice in writes the settlement price.

    This is #5246's producer half: before the fix those UPDATEs set `is_winner`
    and `resolution_source` and left `current_probability` holding a dead
    player's last quote.
    """
    sql = _price_set(price)
    assert f"current_probability={price}" in sql
    assert "current_american_odds=NULL" in sql


def test_the_two_settlement_prices_are_not_each_other():
    """A winner settles at 1.0 and a loser at 0.0.

    Pinned separately because the parametrised test above passes on a mutant
    that returns the same clause for both arguments — each case only ever reads
    its own substring.
    """
    assert _price_set("1.0") != _price_set("0.0")
    assert "current_probability=1.0" in _price_set("1.0")
    assert "current_probability=0.0" not in _price_set("1.0")
    assert "current_probability=0.0" in _price_set("0.0")
    assert "current_probability=1.0" not in _price_set("0.0")


def test_both_settlement_call_sites_ask_for_the_price():
    """The YES branch and the NO branch each splice the clause, with DIFFERENT prices.

    The positive control for the source scan above: a refactor that drops one
    call site, or points both at the same price, fails here rather than shipping
    a sweep that prices only half of what it grades.
    """
    sites = _settlement_call_sites()
    assert sorted(sites) == ["0.0", "1.0"], sites


def test_the_change_stamp_compares_against_the_price_being_written():
    """`price_changed_at` stamps only when the write moves the stored value.

    The CASE must test the SAME literal the SET writes. A mutant that hardcodes
    one side — comparing against 0.0 while writing 1.0 — stamps every crowned
    leg as freshly moved on every sweep, reproducing #2024 in the column added
    to fix it. Both sides are cast to the stored `Numeric(7, 6)` for the reason
    `app/utils/price_change_stamp.py` exists: a provider float and its rounded
    stored form are otherwise never equal.
    """
    for price in ("1.0", "0.0"):
        sql = _price_set(price)
        assert (
            f"IS DISTINCT FROM CAST({price} AS numeric(7,6))" in sql
        ), f"{price}: change stamp must compare against the price it writes"
        assert "ELSE fo.price_changed_at END" in sql


def test_settlement_never_widens_past_the_venues_own_two_answers():
    """The price literal is interpolated, so the set of legal literals is closed.

    `_SETTLED_PRICE_SET_SQL` builds SQL by f-string. That is safe only while the
    argument cannot be anything but `"0.0"` or `"1.0"`, and the raise is what
    keeps it that way — including against a future caller that decides to pass a
    "probability we are fairly confident about".
    """
    for bad in ("0.5", "0", "1", "", "0.0; DROP TABLE futures_outcomes"):
        with pytest.raises(ValueError):
            _price_set(bad)


def test_the_settling_sweep_still_refuses_to_overwrite_a_better_verdict():
    """#5246 adds columns to the SET clause; it must not loosen who is eligible.

    An already-`api_settlement` row is not in `OVERWRITABLE_WINNER_SOURCES_SQL`,
    which is also why the repair script and this producer are independent of
    each other — the fix cannot reach the rows already carrying residue, and the
    repair cannot be undone by the fix.
    """
    from app.utils.resolution_authority import OVERWRITABLE_WINNER_SOURCES_SQL

    assert "api_settlement" not in OVERWRITABLE_WINNER_SOURCES_SQL


# --- the durability guard: a graded leg is not a quotable leg ----------------


def test_the_price_poll_refuses_a_leg_the_venue_resolved_no():
    """The settled refusal tests the GRADE as well as the CROWN.

    Before #5246 this predicate was `is_winner IS NOT TRUE` alone, which is a
    test for a crown: a leg the venue resolved NO carries `is_winner = FALSE`
    and passed it. Nothing had re-priced one only because Kalshi returns
    `yes_bid: null, yes_ask: null, last_price: null` on a `finalized` market —
    the venue's grace, not our guard.
    """
    from app.tasks.futures_price_refresh import ELIGIBLE_OUTCOMES_SQL

    assert "is_winner IS NOT TRUE" in ELIGIBLE_OUTCOMES_SQL
    assert "resolution_source IS DISTINCT FROM 'api_settlement'" in ELIGIBLE_OUTCOMES_SQL


def test_the_refusal_is_tri_state_safe_and_not_a_plain_inequality():
    """`IS DISTINCT FROM`, never `!=`.

    `resolution_source` is nullable and an ungraded outcome holds NULL.
    `resolution_source != 'api_settlement'` evaluates to NULL for those rows —
    falsy — so the plain inequality would make EVERY ungraded outcome ineligible
    and the poller would write nothing at all, for every market, permanently.
    That is #2199's failure mode inverted: the same predicate's `is_winner` leg
    carries the same warning for the same reason.
    """
    from app.tasks.futures_price_refresh import ELIGIBLE_OUTCOMES_SQL

    assert "!=" not in ELIGIBLE_OUTCOMES_SQL
    assert "<>" not in ELIGIBLE_OUTCOMES_SQL


def test_the_refusal_does_not_reach_the_revisable_grades():
    """Only the venue's own settlement is refused, not every non-NULL source.

    Most `resolution_source` values are inferences the system is allowed to
    revise, and a live quote is better evidence than a guess. Widening this to
    `resolution_source IS NOT NULL` would freeze the price of every row a
    guessing pass has ever touched — 71,050 `pass2_loser` rows and 42,517
    `pass2_guess` rows on production alone.
    """
    from app.tasks.futures_price_refresh import ELIGIBLE_OUTCOMES_SQL

    assert "resolution_source IS NOT NULL" not in ELIGIBLE_OUTCOMES_SQL
    for revisable in ("pass2_guess", "multi_max_prob", "binary_higher_wins",
                      "box_score", "game_score", "clean_resolution"):
        assert revisable not in ELIGIBLE_OUTCOMES_SQL


# --- the repair: what it clears, and what it refuses to clear ----------------


def _leg(market_id, outcome_id, survives, residue=0.01):
    return {
        "market_id": market_id,
        "outcome_id": outcome_id,
        "outcome_name": f"player {outcome_id}",
        "residue": residue,
        "live_field_survives": survives,
    }


def test_the_repair_clears_a_market_that_still_has_a_live_field():
    """The US Open shape: 44 dead legs beside four live ones."""
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    rows = [_leg(34277822, i, True) for i in range(44)]
    clear, refuse = plan(rows)
    assert len(clear) == 44
    assert refuse == []


def test_the_repair_refuses_to_blank_a_card():
    """Where no live priced leg survives, zeroing every candidate is refused.

    An open market whose entire field has been graded a loser is a different
    defect — its status is wrong — and replacing a wrong card with an all-zero
    card would hide it. This clause refuses 4,613 of 11,740 production
    candidates across 1,139 markets, so it is not decoration.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    rows = [_leg(999, i, False) for i in range(6)]
    clear, refuse = plan(rows)
    assert clear == []
    assert len(refuse) == 6


def test_the_refusal_is_decided_per_market_not_per_leg():
    """One market's verdict never leaks into another's, and never splits.

    The question — *does a live priced field survive here?* — is a property of
    the MARKET. A per-leg answer would clear a market's legs one at a time and
    blank the card on the last one, which is the exact outcome the refusal
    exists to prevent.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    rows = [_leg(1, 10, True), _leg(2, 20, False), _leg(1, 11, True),
            _leg(2, 21, False)]
    clear, refuse = plan(rows)
    assert {leg["outcome_id"] for leg in clear} == {10, 11}
    assert {leg["outcome_id"] for leg in refuse} == {20, 21}


def test_a_market_whose_legs_disagree_fails_closed():
    """Disagreement within a market refuses the market, it does not clear it.

    The scan's `EXISTS` is keyed on `market_id` alone, so no production row can
    reach this today — which is precisely why it is worth pinning. Reading the
    first leg's answer instead of requiring all of them would let a future
    per-leg scan clear a whole market off one row, silently, in the one function
    whose job is to refuse.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    clear, refuse = plan([_leg(7, 70, True), _leg(7, 71, False)])
    assert clear == []
    assert {leg["outcome_id"] for leg in refuse} == {70, 71}


def test_an_empty_reconciliation_is_not_a_clean_backup():
    """gotcha #53: `all()` over an empty mapping is True.

    Without the emptiness test, a reconciliation that inspected nothing — the
    first run, before the backup table exists — reads as a clean pass and
    `--apply` proceeds with no undo.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        backup_is_exact,
    )

    assert backup_is_exact({}) is False
    assert backup_is_exact({"futures_outcomes": 1}) is False
    assert backup_is_exact({"futures_outcomes": 0}) is True


def test_a_small_plan_names_which_of_its_two_causes_happened():
    """A sanity floor that names two causes needs a discriminator, not an override.

    "The filter broke" and "the job is already done" both present as a plan
    below the floor, and `--allow-small` would let the first through wearing the
    second's clothes. The manifest is the discriminator: only a successful
    forward write puts a row in it.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        SANITY_FLOOR,
        explain_small_plan,
    )

    assert explain_small_plan(SANITY_FLOOR, 0) == ""
    assert "ALREADY APPLIED" in explain_small_plan(10, SANITY_FLOOR)
    assert "FILTER BROKE" in explain_small_plan(10, 10)


def test_the_repair_writes_only_the_price_columns():
    """No verdict moves, and no calibration input moves.

    The grade is already correct — this repair stops the price contradicting it.
    `opening_probability` and `calibration_probability` are the curve's inputs
    (gotcha #144) and `last_updated` is the poll-touch clock three surfaces read
    as liveness; none of them belong to a script that reads no venue price.

    The assertion is made against the SET clause alone. `is_winner` and
    `resolution_source` DO appear in the statement — in the WHERE, as the
    compare-and-swap premise — and a whole-statement substring test would
    either fail on that or, written the other way, pass on a mutant that moved
    a column from the WHERE into the SET.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import SQL

    clear = SQL["clear"]
    set_clause, where_clause = clear.split("WHERE", 1)
    assert "current_probability = 0" in set_clause
    assert "current_american_odds = NULL" in set_clause
    assert "price_changed_at = NOW()" in set_clause
    for untouched in ("opening_probability", "calibration_probability",
                      "last_updated", "is_winner", "resolution_source"):
        assert untouched not in set_clause, f"{untouched} must not be written"
    # ...and the grade columns are still READ, which is the next test's subject.
    assert "is_winner" in where_clause


def test_the_forward_write_is_a_compare_and_swap_on_its_own_premise():
    """If the row moved between the plan and the write, the write no-ops.

    The plan is a snapshot and the apply loop is a network round trip per row.
    Re-asserting every clause of the premise in the UPDATE means a row that has
    since been re-graded, re-priced or already cleared is declined rather than
    overwritten with a zero — which is why a decline is reported as the good
    case rather than an error.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        RESIDUE_FLOOR,
        SETTLED_SOURCE,
        SQL,
    )

    clear = SQL["clear"]
    assert "WHERE id = :oid" in clear
    assert "is_winner = false" in clear
    assert f"resolution_source = '{SETTLED_SOURCE}'" in clear
    assert f"current_probability > {RESIDUE_FLOOR}" in clear


def test_the_repair_stays_inside_open_markets():
    """Scope stops where the defect stops.

    963,492 markets are `resolved` and are not rendered as live winner cards;
    51,762 are `open` and are. A repair that widened to the resolved side would
    rewrite a million terminal prices to buy no reader anything.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import SQL

    assert "status = 'open'" in SQL["scan"]


# --- CAL-P1004, found from #5246: an undeclared market is not a loss ---------


def test_the_settled_sweep_grades_through_the_three_state_helper():
    """The settled-events sweep asks `gradeable_winner`, not `rs == "yes"`.

    This was the last of this file's four Kalshi graders still carrying the
    two-state form, and it escaped `test_kalshi_forward_capture_grade_p1004`'s
    scan on a NAME — that pattern is `result\\w* == "yes"` and the local here was
    called `rs`. Pinned by behaviour rather than by that pattern so the next
    rename cannot slip through the same gap.
    """
    src = _task_module_code()
    assert 'rs == "yes"' not in src
    assert 'rs is not None' not in src
    assert "kms.gradeable_winner(" in src
    # The skip is COUNTED, not silent — gotcha #53.
    assert 'settled_stats["undeclared"] += 1' in src


@pytest.mark.parametrize(
    "status,result,expected",
    [
        ("finalized", "yes", True),
        ("finalized", "no", False),
        ("determined", "yes", True),
        # The two that used to be graded as LOSSES at the top authority rung.
        ("finalized", "scalar", None),
        ("closed", "", None),
        ("active", "", None),
        ("inactive", "", None),
        # A stray result on a status the measured table says carries none.
        ("closed", "yes", None),
    ],
)
def test_only_a_declared_result_reaches_a_verdict(status, result, expected):
    """`""` and `"scalar"` are absences, and an absence is not a loss.

    Measured on CAL-P053's sample, `scalar` was 39 of 204 results — roughly one
    settled market in five. Every one of them was recorded as "this outcome
    lost". #5246 made that worse before it made it better: the sweep now writes
    `current_probability = 0` beside the verdict, so an undeclared market would
    have had its price zeroed on a grade the venue never gave.
    """
    from app.utils import kalshi_market_status as kms

    assert kms.gradeable_winner(status, result) is expected
