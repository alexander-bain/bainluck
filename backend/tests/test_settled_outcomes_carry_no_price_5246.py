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
this repo is env-gated (`CALIBRATION_TEST_DATABASE_URL`, `SEARCH_TEST_DATABASE_URL`
and friends) and SKIPS in CI, which has no Postgres service. A skipped guard is
not a guard. So these read the composed statement the task actually executes —
`settled_grade_update_sql` and `ELIGIBLE_OUTCOMES_SQL` are the objects passed to
`text()` at the call site, not re-derivations of them — which is the only form
that can fail in CI when the producer regresses.
"""

import pytest


# --- the producer: the grade and the price are one settlement ----------------


@pytest.mark.parametrize(
    "result,expected_winner,expected_price",
    [("no", "is_winner=false", "current_probability=0.0"),
     ("yes", "is_winner=true", "current_probability=1.0")],
)
def test_settlement_writes_the_price_beside_the_verdict(
    result, expected_winner, expected_price
):
    """The statement that grades a settled Kalshi leg also prices it.

    This is the whole of #5246's producer half: before the fix these UPDATEs set
    `is_winner` and `resolution_source` and left `current_probability` holding a
    dead player's last quote.
    """
    from app.tasks.backfill_winners import settled_grade_update_sql

    sql = settled_grade_update_sql(result)
    assert expected_winner in sql
    assert expected_price in sql
    assert "current_american_odds=NULL" in sql
    assert "resolution_source='api_settlement'" in sql


def test_the_two_results_do_not_write_the_same_price():
    """A winner settles at 1.0 and a loser at 0.0, and they are not each other.

    Pinned as its own assertion because the parametrised test above passes on a
    mutant that returns the loser statement for both arguments — each case only
    ever reads its own substring, and `current_probability=0.0` is present in a
    statement that also wrongly says `is_winner=true`.
    """
    from app.tasks.backfill_winners import settled_grade_update_sql

    yes_sql = settled_grade_update_sql("yes")
    no_sql = settled_grade_update_sql("no")
    assert yes_sql != no_sql
    assert "current_probability=1.0" in yes_sql
    assert "current_probability=0.0" not in yes_sql
    assert "current_probability=0.0" in no_sql
    assert "current_probability=1.0" not in no_sql


def test_the_change_stamp_compares_against_the_price_being_written():
    """`price_changed_at` stamps only when the write moves the stored value.

    The CASE must test the SAME literal the SET writes. A mutant that hardcodes
    one side — comparing against 0.0 while writing 1.0 — stamps every crowned
    leg as freshly moved on every sweep, reproducing #2024 in the column added
    to fix it. Both sides are cast to the stored `Numeric(7, 6)` for the reason
    `app/utils/price_change_stamp.py` exists: a provider float and its rounded
    stored form are otherwise never equal.
    """
    from app.tasks.backfill_winners import settled_grade_update_sql

    for result, price in (("yes", "1.0"), ("no", "0.0")):
        sql = settled_grade_update_sql(result)
        assert (
            f"IS DISTINCT FROM CAST({price} AS numeric(7,6))" in sql
        ), f"{result}: change stamp must compare against the price it writes"
        assert "ELSE fo.price_changed_at END" in sql


def test_settlement_never_widens_past_the_venues_own_two_answers():
    """The price literal is interpolated, so the set of legal literals is closed.

    `_SETTLED_PRICE_SET_SQL` builds SQL by f-string. That is safe only while the
    argument cannot be anything but `"0.0"` or `"1.0"`, and the raise is what
    keeps it that way — including against a future caller that decides to pass a
    "probability we are fairly confident about".
    """
    from app.tasks.backfill_winners import (
        _SETTLED_PRICE_SET_SQL,
        settled_grade_update_sql,
    )

    for bad in ("0.5", "0", "1", "", "0.0; DROP TABLE futures_outcomes"):
        with pytest.raises(ValueError):
            _SETTLED_PRICE_SET_SQL(bad)
    for bad in ("YES", "won", "", "no'"):
        with pytest.raises(ValueError):
            settled_grade_update_sql(bad)


def test_settlement_still_refuses_to_overwrite_a_better_verdict():
    """The pre-existing WHERE survives the fix.

    #5246 adds columns to the SET clause; it must not loosen who is eligible.
    An already-`api_settlement` row is not in `OVERWRITABLE_WINNER_SOURCES_SQL`,
    which is also why the repair script and this producer are independent of
    each other — the fix cannot reach the 11,740 rows already carrying residue,
    and the repair cannot be undone by the fix.
    """
    from app.tasks.backfill_winners import settled_grade_update_sql
    from app.utils.resolution_authority import OVERWRITABLE_WINNER_SOURCES_SQL

    for result in ("yes", "no"):
        sql = settled_grade_update_sql(result)
        assert "fo.resolution_source IS NULL" in sql
        assert OVERWRITABLE_WINNER_SOURCES_SQL in sql
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
