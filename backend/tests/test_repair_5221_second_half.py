"""#5221 — the repair that un-says 2H verdicts computed as final-minus-Q1.

The producer fix (`_first_half_period_count`, PR #5225) stops the bleeding. This
is the other half: the stored rows, 250 of which are telling a reader that
Portland won a second half Indiana won 57-48.

Three properties carry the whole thing and each is guarded here:

* **the admission test is the safety.** A row is clearable only when the BUGGY
  formula reproduces what is stored and the correct one does not. Once the
  producer fix deploys, correctly-graded 2H rows carry `game_score` too and are
  structurally identical to the broken ones — so a structural-only cohort would
  start eating correct verdicts. Nothing about that hazard is visible in a test
  that only feeds the repair broken rows, so the correct-row case is tested
  explicitly.
* **the filter never mirrors the producer.** The verdict a row SHOULD carry is
  asked of `_decide_three_way_winner` / `_spread_outcome_is_winner` /
  `_total_outcome_is_winner`. A copy that "improves" on their tokenising grades
  markets they refuse, which is #5023's 70 wrongly-cleared rows in a new suit.
* **a plan below the sanity floor has two causes and needs a discriminator.**
  "The filter broke" and "the backlog is drained" look identical from the count
  alone. The manifest is the discriminator; there is deliberately no
  `--allow-small`.
"""
import importlib.util
import pathlib
import re

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_5221_second_half_graded_from_the_first_quarter")
restore = _load("restore_5221_second_half_graded_from_the_first_quarter")


# ---------------------------------------------------------------------------
# fixtures — real production rows, so a change of mind about the arithmetic
# fails against the game that was actually played
# ---------------------------------------------------------------------------

def _legs(ticker, names, stored, *, home, away, final, periods,
          sport="basketball_nba", market_id=1):
    """One market's legs in the shape `_PLAN_SQL` returns."""
    return [
        {
            "outcome_id": 100 + i,
            "outcome_name": name,
            "stored_is_winner": won,
            "market_id": market_id,
            "ticker": ticker,
            "home_team_name": home,
            "away_team_name": away,
            "final_home": final[0],
            "final_away": final[1],
            "home_periods": periods[0],
            "away_periods": periods[1],
            "sport_key": sport,
        }
        for i, (name, won) in enumerate(zip(names, stored))
    ]


#: KXNBA2HWINNER-26FEB19BOSGSW, live on production 2026-09-11. Golden State are
#: home and outscored Boston 59-47 after the interval; the served verdict says
#: Boston. final-minus-Q1 gives 78-85, which is where "Boston" came from.
BOSGSW = dict(
    ticker="KXNBA2HWINNER-26FEB19BOSGSW",
    names=["Golden State", "Boston", "Tie"],
    stored=[False, True, False],
    home="Golden State Warriors", away="Boston Celtics",
    final=(110, 121), periods=([32, 19, 22, 37], [36, 38, 28, 19]),
)


def _bosgsw(**over):
    return _legs(**{**BOSGSW, **over})


# ---------------------------------------------------------------------------
# the statements
# ---------------------------------------------------------------------------

def test_every_statement_parses_as_postgres():
    """A syntax error in a repair is otherwise found by a dyno nobody can read."""
    sqlglot = pytest.importorskip("sqlglot")
    for sql in (
        repair.SQL["bak_create"],
        repair.SQL["bak_index"],
        repair.SQL["bak_copy"],
        repair.SQL["bak_missing"],
        repair.SQL["man_create"],
        repair.SQL["man_record"],
        repair.SQL["clear"],
        repair._PLAN_SQL,
        restore._PLAN_SQL,
        restore._RESTORE_SQL,
    ):
        sqlglot.parse_one(sql, dialect="postgres")


def test_the_forward_write_is_a_compare_and_swap_on_the_value_it_removes():
    """`resolution_source = 'game_score'` in the WHERE is the whole safety.

    Between the plan and the write the fixed producer can re-grade the row —
    which is the outcome this repair exists to make possible. Without the CAS
    the clear would delete that correct verdict and put the row back in the
    ungraded pool it just left.
    """
    sql = " ".join(repair.SQL["clear"].split())
    assert "WHERE id = :oid AND resolution_source = 'game_score'" in sql


def test_the_repair_writes_no_column_the_undo_does_not_restore():
    """An undo that restores less than the repair wrote is not an undo."""
    written = set(re.findall(r"SET\s+(.*?)\s+WHERE", repair.SQL["clear"], re.S)[0]
                  .replace("\n", " ").split(","))
    written = {w.split("=")[0].strip() for w in written}
    restored = set(re.findall(r"SET\s+(.*?)\s+WHERE", restore._RESTORE_SQL, re.S)[0]
                   .replace("\n", " ").split(","))
    restored = {r.split("=")[0].strip() for r in restored}
    assert written == restored == {"is_winner", "resolution_source"}


def test_the_cohort_matches_the_series_family_and_never_the_whole_ticker():
    """#5023: a day-of-month runs into a club code, so `2H` appears inside dates.

    `KXMLSSPREAD-26APR22HOUSD` is day 22 + HOUston, a whole-game spread. Matching
    the period grammar against the whole `external_id` cleared 70 correct
    verdicts on this very table. The regex may only ever meet the part before
    the first dash.
    """
    for line in repair._PLAN_SQL.splitlines():
        if "~*" in line:
            assert repair._SERIES in line or "{" in line, line
    assert "split_part(fm.external_id, '-', 1)" == repair._SERIES
    # and the restore's CAS must not reintroduce a whole-ticker match either
    assert "~*" not in restore._PLAN_SQL


def test_the_cohort_excludes_events_that_hold_a_first_half_scoring_play():
    """Those never reached the buggy branch — `_get_halftime_score` returns first.

    Without this the plan would carry rows whose halftime came from
    `scoring_plays` and is right, and the admission test would be doing all the
    work alone.
    """
    sql = " ".join(repair._PLAN_SQL.split())
    assert "NOT EXISTS" in sql and "scoring_plays" in sql
    for period in ("'q1'", "'q2'", "'1st half'", "'1h'"):
        assert period in sql


# ---------------------------------------------------------------------------
# the admission test — the property that makes this safe to run at any time
# ---------------------------------------------------------------------------

def test_a_refuted_verdict_is_cleared():
    """The ship: Boston is served as the 2H winner of a half Golden State won."""
    clear, spare, refuse = repair.classify(_bosgsw())
    assert {leg["outcome_name"] for leg in clear} == {"Golden State", "Boston"}
    assert not refuse
    # "Tie" is False under both readings, so it is right for the wrong reason.
    assert [leg["outcome_name"] for leg in spare] == ["Tie"]


def test_a_correct_verdict_is_never_cleared_even_though_it_looks_identical():
    """The post-deploy hazard, and the reason the admission test exists.

    Once the producer fix is live it writes CORRECT 2H verdicts carrying the
    same `resolution_source='game_score'`, on the same quarter-scored sports,
    on events with the same missing first-half plays. Structurally these rows
    are indistinguishable from the broken ones. Only the arithmetic separates
    them, and a repair that cannot tell them apart eats the fix's own output.
    """
    correct = _bosgsw(stored=[True, False, False])  # Golden State really won 2H
    clear, spare, refuse = repair.classify(correct)
    assert clear == []
    assert len(spare) + len(refuse) == 3


def test_a_row_the_buggy_formula_does_not_explain_is_refused_not_cleared():
    """Whatever is wrong with it, it is not the defect this repair was measured on.

    All 992 production rows were reproduced exactly by final-minus-Q1. A row
    that is not is a DIFFERENT defect, and clearing it here would hide it inside
    this repair's manifest.
    """
    # final-minus-Q1 gives 78-85, so it says Boston won. A stored `False` on
    # Boston is therefore a value this bug did not write.
    odd = _bosgsw(stored=[False, False, False])
    clear, spare, refuse = repair.classify(odd)
    assert [leg["outcome_name"] for leg in refuse] == ["Boston"]
    assert "Boston" not in {leg["outcome_name"] for leg in clear}


def test_a_two_half_sport_can_never_be_cleared_by_this_repair():
    """`basketball_ncaab` plays halves, so `[0]` WAS the first half and is right.

    `_first_half_period_count` returns 1 there, which makes the buggy and
    correct readings the same expression — so no ncaab row can ever be refuted.
    A future edit that makes one clearable has broken the sport map, and this is
    the test that says so.
    """
    ncaab = _bosgsw(sport="basketball_ncaab")
    clear, _, _ = repair.classify(ncaab)
    assert clear == []


def test_an_unmapped_sport_refuses_rather_than_inventing_a_half():
    ice = _bosgsw(sport="icehockey_nhl")
    clear, spare, refuse = repair.classify(ice)
    assert clear == [] and spare == [] and len(refuse) == 3


# ---------------------------------------------------------------------------
# the filter delegates, and refuses what the producer refuses
# ---------------------------------------------------------------------------

def test_the_two_leg_winner_shape_is_refused_and_stays_refused():
    """The stated residue: the producer grades it inline, so there is nothing to ask.

    `KXNBA2HWINNER-26MAR18PORIND` carries two legs and one of them is wrong.
    Repairing it needs that branch extracted into a pure function first; until
    then this repair must leave all eight production rows alone rather than
    mirror the resolver. If a later change starts clearing them, it has either
    done the extraction (update this test) or invented a second reading.
    """
    porind = _legs(
        "KXNBA2HWINNER-26MAR18PORIND",
        ["Portland wins 2nd half", "Indiana wins 2nd half"],
        [True, False],
        home="Indiana Pacers", away="Portland Trail Blazers",
        final=(112, 105), periods=([26, 33, 29, 24], [24, 23, 33, 25]),
    )
    clear, spare, refuse = repair.classify(porind)
    assert clear == [] and spare == []
    assert len(refuse) == 2


def test_one_unreadable_leg_refuses_the_whole_market():
    """CERT-499's all-or-nothing, for the same reason the producer writes that way.

    Clearing a market's siblings on a partial reading is how a repair invents a
    population.
    """
    totals = _legs(
        "KXNBA2HTOTAL-26FEB19BOSGSW",
        ["Over 100.5 2H points scored", "a name no total parser can read"],
        [True, False],
        home="Golden State Warriors", away="Boston Celtics",
        final=(110, 121), periods=([32, 19, 22, 37], [36, 38, 28, 19]),
    )
    clear, spare, refuse = repair.classify(totals)
    assert clear == [] and spare == []
    assert len(refuse) == 2


def test_a_total_is_graded_by_the_producers_own_total_grader():
    """The family the bug hit hardest: 126 of 153 production legs were wrong.

    True 2H total is 59+47=106; final-minus-Q1 gives 78+85=163. "Over 125.5"
    was served WON and lost.
    """
    totals = _legs(
        "KXNBA2HTOTAL-26FEB19BOSGSW",
        ["Over 125.5 2H points scored", "Over 100.5 2H points scored"],
        [True, True],
        home="Golden State Warriors", away="Boston Celtics",
        final=(110, 121), periods=([32, 19, 22, 37], [36, 38, 28, 19]),
    )
    clear, spare, refuse = repair.classify(totals)
    assert [leg["outcome_name"] for leg in clear] == ["Over 125.5 2H points scored"]
    assert [leg["outcome_name"] for leg in spare] == ["Over 100.5 2H points scored"]
    assert refuse == []


def test_market_verdicts_returns_none_for_a_family_it_has_no_grader_for():
    legs = _legs("KXNBA2HBTTS-26FEB19BOSGSW", ["Yes", "No"], [True, False],
                 home="Golden State Warriors", away="Boston Celtics",
                 final=(110, 121), periods=([32, 19, 22, 37], [36, 38, 28, 19]))
    assert repair.market_verdicts(legs[0]["ticker"], legs, 59, 47) is None


# ---------------------------------------------------------------------------
# linescores, floors and gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ([32, 19, 22, 37], [32, 19, 22, 37]),
    # gotcha #40: the admin db-query rail serialises JSONB as a Python repr
    ("[32, 19, 22, 37]", [32, 19, 22, 37]),
    ([], None),
    (None, None),
    ([32, None, 22], None),
    (["32", "19"], None),
    # bools are ints in Python and would sum to a plausible score
    ([True, False], None),
    ("not a list at all", None),
])
def test_linescore_refuses_everything_it_cannot_sum(raw, expected):
    assert repair.linescore(raw) == expected


def test_a_short_linescore_refuses_rather_than_summing_what_is_there():
    """A game that has not reached the interval cannot answer this (#816)."""
    partial = _bosgsw(periods=([32], [36]))
    clear, spare, refuse = repair.classify(partial)
    assert clear == [] and spare == [] and len(refuse) == 3


def test_an_empty_reconciliation_is_not_a_clean_backup():
    """`all()` over an empty mapping is True — gotcha #53 in one line."""
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"futures_outcomes": 0}) is True
    assert repair.backup_is_exact({"futures_outcomes": 1}) is False


def test_a_small_plan_names_which_of_its_two_causes_happened():
    assert repair.explain_small_plan(repair.SANITY_FLOOR, 0) == ""
    drained = repair.explain_small_plan(5, repair.SANITY_FLOOR)
    assert drained.startswith("ALREADY APPLIED")
    broke = repair.explain_small_plan(5, 0)
    assert broke.startswith("FILTER BROKE")


def test_there_is_no_override_flag_for_the_sanity_floor():
    """The discriminator replaces the flag; re-adding one re-opens #4923's trap."""
    src = (_SCRIPTS / "repair_5221_second_half_graded_from_the_first_quarter.py"
           ).read_text()
    declared = re.findall(r"add_argument\(\s*[\"']--([a-z-]+)", src)
    assert set(declared) == {"backup", "apply", "limit"}


def test_the_repair_never_writes_a_verdict():
    """It clears; the producer grades. Two writers of one number is the defect.

    The only UPDATE against `futures_outcomes` this file may carry is the clear.
    """
    src = (_SCRIPTS / "repair_5221_second_half_graded_from_the_first_quarter.py"
           ).read_text()
    assert src.count("UPDATE futures_outcomes") == 1
    assert "is_winner = NULL" in repair.SQL["clear"]
    assert "resolution_source = NULL" in repair.SQL["clear"]


def test_the_plan_groups_by_market_before_it_classifies():
    """`_decide_three_way_winner` needs the whole triple; a per-row loop cannot ask it."""
    rows = _bosgsw() + _legs(
        "KXNBA2HTOTAL-26FEB19BOSGSW", ["Over 125.5 2H points scored"], [True],
        home="Golden State Warriors", away="Boston Celtics",
        final=(110, 121), periods=([32, 19, 22, 37], [36, 38, 28, 19]),
        market_id=2,
    )
    clear, spare, refuse = repair.plan(rows)
    assert len(clear) + len(spare) + len(refuse) == 4
    assert {leg["outcome_name"] for leg in clear} == {
        "Golden State", "Boston", "Over 125.5 2H points scored"}
