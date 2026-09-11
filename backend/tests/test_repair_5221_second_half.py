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
import collections
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
          sport="basketball_nba", market_id=1, foreign_locker=False):
    """One market's legs in the shape `_PLAN_SQL` returns.

    `foreign_locker` mirrors the per-market EXISTS the scan carries: does this
    market hold a TRUE, non-overwritable verdict from a source other than
    `game_score`? Defaults False because that is the ordinary case; the one
    fixture that sets it is the `api_settlement` refusal (CERT-2631).
    """
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
            "foreign_locker": foreign_locker,
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
    """The source is NOT the whole safety, and this test used to say it was.

    🔴 CERT-2649. The old assertion was the docstring's claim written out as a
    substring, and it passed against a statement that swapped on nothing this
    repair had decided: the FIXED producer re-grades under `game_score` too, so
    the source is unchanged by exactly the event the CAS exists to detect. The
    winner bit read at plan time is the value being removed, so it is the value
    the swap has to key on.
    """
    sql = " ".join(repair.SQL["clear"].split())
    assert "WHERE id = :oid AND resolution_source = 'game_score'" in sql
    assert "is_winner IS NOT DISTINCT FROM CAST(:was AS boolean)" in sql, (
        "the swap must key on the winner bit the plan read, not only the source"
    )


def _sqlite_clear(sql, *, stored_now, planned, source_now="game_score"):
    """Execute the repair's REAL `clear` statement and report (rowcount, row).

    Not a re-implementation of the predicate: the statement text is taken from
    the script, transpiled by `sqlglot` and run by SQLite, which implements
    `IS NOT DISTINCT FROM` itself. Deleting the winner-bit clause from the
    script therefore changes what this executes, which is the whole point —
    a guard that merely greps for the clause cannot tell a live predicate from
    a decorative one (the CERT-2648 lesson, applied to SQL instead of Python).
    """
    sqlglot = pytest.importorskip("sqlglot")
    import sqlite3

    stmt = sqlglot.transpile(sql, read="postgres", write="sqlite")[0]
    stmt = stmt.replace(":oid", "?").replace(":was", "?")
    named_binds = sql.count(":was")

    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE futures_outcomes "
                "(id int, is_winner, resolution_source text)")
    con.execute("INSERT INTO futures_outcomes VALUES (1, ?, ?)",
                (stored_now, source_now))
    params = (1, planned) if named_binds else (1,)
    cur = con.execute(stmt, params)
    row = con.execute("SELECT is_winner, resolution_source "
                      "FROM futures_outcomes WHERE id = 1").fetchone()
    return cur.rowcount, row


def test_a_same_source_regrade_of_the_winner_bit_declines_the_clear_and_survives():
    """🔴 THE BLOCK THIS ANSWERS (CERT-2649), and it was a DESTRUCTIVE race.

    A leg planned as a wrong TRUE, re-graded to a correct FALSE by the fixed
    producer between the plan and the write — under the same `game_score`
    source, because that is the source the producer writes. The old statement
    matched it, nulled it, and returned rowcount 1, so:

      * the correct verdict this repair exists to make possible was ERASED, and
      * the clear did not register as declined, so the market counted as fully
        cleared and was UNLOCKED on a premise the database had already denied.

    Both halves are asserted here. The survival is read back off the row rather
    than inferred from the rowcount, because "it declined" and "it declined and
    left the row alone" are different claims.
    """
    # The race: planned TRUE, the producer has since written the correct FALSE.
    rowcount, row = _sqlite_clear(repair.SQL["clear"], stored_now=False, planned=True)
    assert rowcount == 0, "a same-source regrade must decline, not overwrite"
    assert row == (0, "game_score"), (
        "the producer's correct verdict must survive the declined clear intact"
    )

    # The NO leg of the same race: planned FALSE, re-graded to TRUE.
    rowcount, row = _sqlite_clear(repair.SQL["clear"], stored_now=True, planned=False)
    assert rowcount == 0
    assert row == (1, "game_score")

    # Unchanged since the plan — both legs still clear, or the repair is inert.
    for stored in (True, False):
        rowcount, row = _sqlite_clear(
            repair.SQL["clear"], stored_now=stored, planned=stored)
        assert rowcount == 1, "an unchanged row is exactly what this repair clears"
        assert row == (None, None)

    # A row another run already cleared is NULL, not the planned value: it
    # declines rather than being counted a second time.
    rowcount, _ = _sqlite_clear(
        repair.SQL["clear"], stored_now=None, planned=True, source_now=None)
    assert rowcount == 0

    # AND THE DECLINE WITHHOLDS THE UNLOCK. This is the second half of the
    # required repair: the market whose clear declined is not fully cleared, so
    # it is never unlocked around the survivor.
    planned_by_market = collections.Counter({7: 2})
    cleared_by_market = collections.Counter({7: 1})   # one declined
    assert repair.markets_fully_cleared(planned_by_market, cleared_by_market) == set()


def test_the_apply_loop_really_passes_the_planned_winner_bit():
    """A bound parameter the caller never supplies is a swap on a constant.

    The statement can carry `:was` and still be keyed on nothing if the call
    site passes a literal, or passes the row's CURRENT value instead of the one
    the plan read. Asserted against the call's own AST rather than a substring,
    because `"stored_is_winner"` appears in this script's printing code too.
    """
    import ast

    src = pathlib.Path(repair.__file__).read_text()
    calls = [
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and any(
            isinstance(a, ast.Call)
            and isinstance(a.func, ast.Name) and a.func.id == "text"
            and any(
                isinstance(s, ast.Subscript)
                and isinstance(s.value, ast.Name) and s.value.id == "SQL"
                and isinstance(s.slice, ast.Constant) and s.slice.value == "clear"
                for s in ast.walk(a)
            )
            for a in node.args
        )
    ]
    assert len(calls) == 1, f"expected one apply site for SQL['clear'], got {len(calls)}"

    params = next(a for a in calls[0].args if isinstance(a, ast.Dict))
    was = {
        ast.unparse(v)
        for k, v in zip(params.keys, params.values)
        if isinstance(k, ast.Constant) and k.value == "was"
    }
    assert was == {"leg['stored_is_winner']"}, (
        f"`was` must be the winner bit the PLAN read; got {was or 'nothing'}"
    )


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
    clear, _unlock, spare, refuse = repair.classify(_bosgsw())
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
    clear, _unlock, spare, refuse = repair.classify(correct)
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
    clear, _unlock, spare, refuse = repair.classify(odd)
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
    clear, _u, _s, _r = repair.classify(ncaab)
    assert clear == []


def test_an_unmapped_sport_refuses_rather_than_inventing_a_half():
    ice = _bosgsw(sport="icehockey_nhl")
    clear, _unlock, spare, refuse = repair.classify(ice)
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
    clear, _unlock, spare, refuse = repair.classify(porind)
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
    clear, _unlock, spare, refuse = repair.classify(totals)
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
    clear, unlock, spare, refuse = repair.classify(totals)
    assert [leg["outcome_name"] for leg in clear] == ["Over 125.5 2H points scored"]
    # Over 100.5 is CORRECT and stored TRUE, so it is the leg that would hold
    # this market out of the producer's scan. It moves to `unlock`, not `spare`
    # (CERT-2631) — it is still not a leg the repair judged wrong.
    assert [leg["outcome_name"] for leg in unlock] == ["Over 100.5 2H points scored"]
    assert spare == []
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
    clear, _unlock, spare, refuse = repair.classify(partial)
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

    TWO UPDATEs are permitted now (CERT-2631) — the clear and the unlock — and
    the count is pinned so a third cannot appear unread. Both may only ever
    write NULLs: the moment either one sets `is_winner =` to anything else, this
    script has started grading and the whole safety argument is gone.
    """
    src = (_SCRIPTS / "repair_5221_second_half_graded_from_the_first_quarter.py"
           ).read_text()
    assert src.count("UPDATE futures_outcomes") == 2
    for key in ("clear", "unlock"):
        assert "is_winner = NULL" in repair.SQL[key]
        assert "resolution_source = NULL" in repair.SQL[key]
        assert not re.search(r"is_winner\s*=\s*(TRUE|FALSE|true|false)",
                             repair.SQL[key])


def test_the_plan_groups_by_market_before_it_classifies():
    """`_decide_three_way_winner` needs the whole triple; a per-row loop cannot ask it."""
    rows = _bosgsw() + _legs(
        "KXNBA2HTOTAL-26FEB19BOSGSW", ["Over 125.5 2H points scored"], [True],
        home="Golden State Warriors", away="Boston Celtics",
        final=(110, 121), periods=([32, 19, 22, 37], [36, 38, 28, 19]),
        market_id=2,
    )
    clear, _unlock, spare, refuse = repair.plan(rows)
    assert len(clear) + len(spare) + len(refuse) == 4
    assert {leg["outcome_name"] for leg in clear} == {
        "Golden State", "Boston", "Over 125.5 2H points scored"}


# ===========================================================================
# #5236 — the FIRST-half half of the same helper, four times the population
#
# `_get_halftime_score` has two callers. #5221 was opened on the 2H one, where
# the bug reads as "final minus three quarters"; the 1H one hands the same
# number back unsubtracted and reads as "the first quarter IS the first half".
# Every fixture below is a production row, so a change of mind about the
# arithmetic fails against the game that was actually played.
# ===========================================================================

#: KXNBA1HSPREAD-26MAR18PORIND. Indiana at home. Q1 is 33-37, so at the quarter
#: Portland lead by 4 and no line above 5.5 has been crossed; the real first
#: half is 62-79 and Portland lead by SEVENTEEN. A reader is told Portland
#: failed to cover 5.5 in a half they won by 17.
PORIND_1H_SPREAD = dict(
    ticker="KXNBA1HSPREAD-26MAR18PORIND",
    names=["Portland wins the 1H by over 5.5 points",
           "Portland wins the 1H by over 8.5 points",
           "Portland wins the 1H by over 2.5 points",
           "Indiana wins the 1H by over 1.5 points"],
    stored=[False, False, True, False],
    home="Indiana Pacers", away="Portland Trail Blazers",
    final=(119, 127), periods=([33, 29, 24, 33], [37, 42, 26, 22]),
)

#: KXNBA1HWINNER-26FEB19ORLSAC and KXNBA1HTOTAL-26FEB19ORLSAC — one game, two
#: shapes. Sacramento at home. Q1 is 28-18 to Sacramento; the first half is
#: 55-64 to Orlando, and 119 points were scored in it against 46 in the quarter.
ORLSAC = dict(
    home="Sacramento Kings", away="Orlando Magic",
    final=(94, 131), periods=([28, 27, 29, 10], [18, 46, 38, 29]),
)


def test_a_first_half_spread_the_first_quarter_flattered_is_cleared():
    """The #5236 ship: Portland won the half by 17 and we say they missed 5.5."""
    clear, _unlock, spare, refuse = repair.classify(_legs(**PORIND_1H_SPREAD))
    assert {leg["outcome_name"] for leg in clear} == {
        "Portland wins the 1H by over 5.5 points",
        "Portland wins the 1H by over 8.5 points",
    }
    assert not refuse
    # Over 2.5 was cleared by the quarter too, and Indiana never led — right for
    # the wrong reason. Neither is a verdict this repair judged WRONG, but
    # "Portland over 2.5" is stored TRUE with a non-overwritable `game_score`
    # source, so it is precisely what would hold this market out of the
    # producer's re-grade. It is unlocked; the FALSE one is simply spared.
    assert {leg["outcome_name"] for leg in _unlock} == {
        "Portland wins the 1H by over 2.5 points",
    }
    assert {leg["outcome_name"] for leg in spare} == {
        "Indiana wins the 1H by over 1.5 points",
    }


def test_a_first_half_winner_names_the_team_that_led_at_the_quarter():
    """Sacramento is served as the 1H winner of a half Orlando won 64-55."""
    legs = _legs(ticker="KXNBA1HWINNER-26FEB19ORLSAC",
                 names=["Orlando", "Sacramento", "Tie"],
                 stored=[False, True, False], **ORLSAC)
    clear, _unlock, spare, refuse = repair.classify(legs)
    assert {leg["outcome_name"] for leg in clear} == {"Orlando", "Sacramento"}
    assert [leg["outcome_name"] for leg in spare] == ["Tie"]
    assert not refuse


def test_a_first_half_total_ladder_clears_only_the_lines_the_half_crosses():
    """46 points in Q1, 119 in the half — the ladder splits at 119, not at 46.

    The rungs above 119 are served `False` and that is CORRECT; a repair that
    cleared the whole ladder because the market was mis-graded would un-say
    three right answers to fix five.
    """
    lines = [105.5, 108.5, 111.5, 114.5, 117.5, 120.5, 123.5, 126.5]
    legs = _legs(ticker="KXNBA1HTOTAL-26FEB19ORLSAC",
                 names=[f"Over {x} 1H points scored" for x in lines],
                 stored=[False] * len(lines), **ORLSAC)
    clear, _unlock, spare, refuse = repair.classify(legs)
    assert [leg["outcome_name"] for leg in clear] == [
        f"Over {x} 1H points scored" for x in (105.5, 108.5, 111.5, 114.5, 117.5)]
    assert [leg["outcome_name"] for leg in spare] == [
        f"Over {x} 1H points scored" for x in (120.5, 123.5, 126.5)]
    assert not refuse


def test_the_total_fixtures_are_not_vacuous():
    """`_TOTAL_RE` needs the full grammar; a bare `Over 105.5` parses to None.

    Three fixtures in this file's #5221 half were written short and passed
    GREEN because an unparseable leg refuses the market, which looks like a
    deliberate refusal. Assert the producer's own parser actually reads the
    names above, so the ladder test is measuring grading and not parsing.
    """
    from app.tasks.backfill_winners import _total_outcome_is_winner

    assert _total_outcome_is_winner("Over 105.5 1H points scored", 55, 64) is True
    assert _total_outcome_is_winner("Over 126.5 1H points scored", 55, 64) is False
    assert _total_outcome_is_winner("Over 105.5", 55, 64) is None


def test_a_correct_first_half_verdict_is_never_cleared():
    """The post-deploy hazard on the 1H path, which is the bigger population.

    Once the fix is live it writes CORRECT 1H verdicts carrying the same
    `game_score`, on the same sports, on events with the same missing plays.
    Only the arithmetic separates them.
    """
    legs = _legs(ticker="KXNBA1HWINNER-26FEB19ORLSAC",
                 names=["Orlando", "Sacramento", "Tie"],
                 stored=[True, False, False], **ORLSAC)  # Orlando really won it
    clear, _unlock, spare, refuse = repair.classify(legs)
    assert clear == []


def test_a_two_half_sport_is_untouchable_on_the_first_half_path_too():
    """1,998 correct NCAAB rows sit in the 1H cohort and none may be cleared.

    Not by an exclusion list: `_first_half_period_count` is 1 for `ncaab` and
    the bug WAS the constant 1, so the two readings are the same expression and
    the admission test can never be satisfied. Measured control: 0 clears in
    2,008 production NCAAB rows.
    """
    legs = _legs(ticker="KXNCAAMB1HSPREAD-26MAR07VTUVA",
                 names=["Portland wins the 1H by over 5.5 points"],
                 stored=[False],
                 home="Indiana Pacers", away="Portland Trail Blazers",
                 final=(119, 127), periods=([33, 29, 24, 33], [37, 42, 26, 22]),
                 sport="basketball_ncaab")
    clear, _u, _s, _r = repair.classify(legs)
    assert clear == []


@pytest.mark.parametrize("period", ["1h", "2h"])
@pytest.mark.parametrize("periods,final", [
    ([33, 29, 24, 33], 119),
    ([28, 27, 29, 10], 94),
    ([10, 0, 0, 0], 10),
    ([7, 7, 3, 7, 6], 30),      # overtime
    ([50, 41], 91),             # a genuine two-entry linescore
])
def test_the_bug_is_the_constant_one_and_that_is_a_property(period, periods, final):
    """`buggy(x) == correct(x, n=1)` — the whole argument in one line.

    This is why two-half sports are safe without an exclusion list, why the
    same fix repairs both callers, and why the repair's 2H numbers did not move
    when the scan widened. If this identity ever breaks, the docstring's
    reasoning is wrong and every claim resting on it needs re-deriving.
    """
    assert (repair.buggy_period_score(period, periods, final)
            == repair.correct_period_score(period, 1, periods, final))


def test_the_buggy_reading_keeps_the_old_len_two_guard():
    """The pre-fix code refused a one-entry linescore, so the reproduction must.

    Admitting it would let the admission test claim this bug wrote a row it
    never touched — and a wrongly-admitted row is a wrongly-cleared verdict.
    """
    assert repair.buggy_period_score("1h", [33], 119) is None
    assert repair.buggy_period_score("2h", [33], 119) is None
    assert repair.buggy_period_score("1h", [33, 29], 119) == 33


def test_a_first_half_needs_no_final_score_and_a_second_half_does():
    """A 1H score is the linescore's own prefix; a 2H one is a subtraction."""
    assert repair.correct_period_score("1h", 2, [33, 29, 24, 33], None) == 62
    assert repair.correct_period_score("2h", 2, [33, 29, 24, 33], None) is None
    assert repair.correct_period_score("2h", 2, [33, 29, 24, 33], 119) == 57


def test_a_short_linescore_cannot_answer_for_a_two_quarter_half():
    """`>= n`, not `>= 2` — the old guard admitted one quarter as a whole half."""
    assert repair.correct_period_score("1h", 2, [33], 119) is None
    assert repair.correct_period_score("1h", 1, [33], 119) == 33


# ---------------------------------------------------------------------------
# which period a ticker asks about is the PRODUCER's call, not this script's
# ---------------------------------------------------------------------------

def test_the_period_is_decided_by_the_producers_own_classifier():
    """`_PLAN_SQL`'s regex is a candidate net; `_ticker_period` is the authority.

    Two readings of "is this a period market" is the drift `_ticker_period` was
    extracted to end (#4923). Widening the SQL must not be able to change what
    gets graded, so the Python side refuses anything the producer does not call
    a reconstructable half — including a quarter, which has no reconstructor at
    all (`_RECONSTRUCTABLE_PERIODS`).
    """
    for ticker in ("KXEPLH2H-26MAR18ARSCHE",     # head-to-head, a whole game
                   "KXNBA1QSPREAD-26MAR18PORIND",  # a quarter, never rebuilt
                   "KXMLBF5TOTAL-26MAR18BOSNYY"):  # first five innings
        legs = _legs(ticker=ticker,
                     names=["Portland wins the 1H by over 5.5 points"],
                     stored=[False], **{k: v for k, v in
                                        PORIND_1H_SPREAD.items()
                                        if k in ("home", "away", "final",
                                                 "periods")})
        clear, _unlock, spare, refuse = repair.classify(legs)
        assert clear == [] and spare == [], ticker
        assert "_ticker_period" in refuse[0]["refuse_reason"], ticker


def test_the_candidate_regex_admits_both_halves_and_still_carves_out_h2h():
    """Tested against the string the script actually ships, not a copy of it."""
    found = re.search(r"~\* '([^']+)'", repair._PLAN_SQL)
    assert found, "the candidate scan no longer has a period regex"
    pattern = re.compile(found.group(1), re.IGNORECASE)

    for series in ("KXNBA1HSPREAD", "KXNBA2HTOTAL", "KXNCAAMB1HWINNER",
                   "KXNFL1HSPREAD", "KXNCAAF2HSPREAD"):
        assert pattern.search(series), series
    for series in ("KXEPLH2H", "KXMLSSPREAD", "KXNBAGAME"):
        assert not pattern.search(series), series


# ---------------------------------------------------------------------------
# a refusal reported only as a count is where the next defect hides
# ---------------------------------------------------------------------------

def _every_refusal():
    """One market down each refusal path in `classify`."""
    base = {k: v for k, v in PORIND_1H_SPREAD.items()
            if k in ("home", "away", "final", "periods")}
    name = ["Portland wins the 1H by over 5.5 points"]
    yield "not a half", _legs(ticker="KXEPLH2H-26MAR18ARSCHE", names=name,
                              stored=[False], **base)
    yield "no half for the sport", _legs(
        ticker="KXNBA1HSPREAD-26MAR18PORIND", names=name, stored=[False],
        **{**base, }, sport="icehockey_nhl")
    yield "unreadable linescore", _legs(
        ticker="KXNBA1HSPREAD-26MAR18PORIND", names=name, stored=[False],
        **{**base, "periods": (None, None)})
    yield "unreconstructable", _legs(
        ticker="KXNBA1HSPREAD-26MAR18PORIND", names=name, stored=[False],
        **{**base, "periods": ([33], [37])})
    yield "no grader", _legs(
        ticker="KXNBA1HSPREAD-26MAR18PORIND", names=["a name nothing parses"],
        stored=[False], **base)
    yield "a different defect", _legs(
        ticker="KXNBA1HSPREAD-26MAR18PORIND", names=name, stored=[True], **base)
    # CERT-2642's survivor: clearable legs AND a TRUE the bug cannot explain, so
    # the market is refused whole rather than cleared behind a standing blocker.
    yield "a surviving TRUE locker", _legs(
        **{**PORIND_1H_SPREAD,
           "names": PORIND_1H_SPREAD["names"]
                    + ["Portland wins the 1H by over 20.5 points"],
           "stored": PORIND_1H_SPREAD["stored"] + [True]})


def test_every_refusal_carries_a_stated_reason():
    """The report groups by `refuse_reason`; an unstamped path reads as "unstated".

    #5237 and #5243 were both found by reading that grouping rather than the
    clears, so a refusal path that forgets to say why is a defect this script
    would go on to bury once per run.
    """
    for label, legs in _every_refusal():
        clear, _unlock, spare, refuse = repair.classify(legs)
        assert refuse, f"{label}: expected a refusal, got clear={clear} spare={spare}"
        for leg in refuse:
            assert leg.get("refuse_reason"), label
            assert leg["refuse_reason"] != "unstated", label


def test_the_refusal_paths_are_distinguishable_from_each_other():
    """Seven paths, seven reasons — a shared string merges two defects into one bucket.

    6 -> 7 (CERT-2642): the surviving TRUE `game_score` locker. It is a distinct
    refusal from "a different defect" even though that is what puts the leg in
    the cohort — this one is about the MARKET being unrepairable, and reporting
    them under one string would hide which markets are merely observed from
    which are refused whole.
    """
    reasons = set()
    for _label, legs in _every_refusal():
        _c, _u2, _s, refuse = repair.classify(legs)
        reasons.add(refuse[0]["refuse_reason"])
    assert len(reasons) == 7, reasons


def test_a_missing_linescore_refuses_rather_than_being_skipped():
    """The #5243 specimen: six completed NFL events hold no box score at all.

    They carry a served `game_score` verdict anyway. This repair cannot say
    what wrote it, so it must neither clear it nor drop it silently.
    """
    legs = _legs(ticker="KXNFL1HSPREAD-26AUG06CARARI",
                 names=["Arizona wins 1H by over 2.5"], stored=[True],
                 home="Arizona Cardinals", away="Carolina Panthers",
                 final=(33, 30), periods=(None, None),
                 sport="americanfootball_nfl_preseason")
    clear, _unlock, spare, refuse = repair.classify(legs)
    assert clear == [] and spare == []
    assert "linescore" in refuse[0]["refuse_reason"]


# ---------------------------------------------------------------------------
# the floor moved with the cohort
# ---------------------------------------------------------------------------

def test_the_sanity_floor_would_catch_a_regression_to_the_2h_only_cohort():
    """If the scan ever narrows back to `2H`, the plan is 248 and must REFUSE.

    That is the failure mode the fold creates: a filter that still works
    perfectly on a fifth of the population, and whose output looks like a
    successful run. The floor is what turns it into a stop.
    """
    assert repair.SANITY_FLOOR > 248
    verdict = repair.explain_small_plan(248, 0)
    assert verdict.startswith("FILTER BROKE")


def test_a_drained_backlog_still_reads_as_drained_at_the_new_floor():
    """The discriminator must not become a false alarm just because the floor rose."""
    verdict = repair.explain_small_plan(8, 1550)
    assert verdict.startswith("ALREADY APPLIED")


# --- CERT-2631: clearing is only half a repair -------------------------------


def _having_gate_blockers(legs, cleared, unlocked):
    """The producer's HAVING clause, evaluated on a market after this repair.

    `_resolve_kalshi_spread_total_from_scores` admits a market only when

        SUM(CASE WHEN fo.is_winner
                 AND fo.resolution_source NOT IN <overwritable>
            THEN 1 ELSE 0 END) = 0

    Written out here rather than imported because the point is to check the
    repair against the producer's RULE, not against a helper the repair and the
    producer might both be wrong about. `game_score` — what every leg in this
    cohort carries — is not in `OVERWRITABLE_WINNER_SOURCES_SQL`, so any leg
    still stored TRUE after the repair is a blocker.
    """
    touched = {leg["outcome_id"] for leg in cleared} | {
        leg["outcome_id"] for leg in unlocked
    }
    return [
        leg["outcome_name"]
        for leg in legs
        if leg["stored_is_winner"] and leg["outcome_id"] not in touched
    ]


def test_repaired_market_is_reeligible_and_regrades_every_cleared_leg():
    """A market this repair touches must come out of it re-gradeable.

    🔴 THE BLOCK THIS ANSWERS (CERT-2631). The first version cleared the wrong
    legs and SPARED the correct ones — including the correct ones stored TRUE.
    `game_score` is not overwritable, so one spared TRUE leg keeps its whole
    market out of the producer's candidate scan forever, and the legs this
    repair had just cleared stayed blank permanently. The repair turned "the
    wrong verdict" into "no verdict, for good", which is worse than the defect.

    The specimen is the production-derived PORIND 1H spread the block named:
    2 legs clear, and the spared set contains a TRUE `game_score` leg.
    """
    legs = _legs(**PORIND_1H_SPREAD)
    clear, unlock, spare, refuse = repair.classify(legs)

    assert clear, "fixture must clear something or it proves nothing"
    assert unlock, "this market's correct TRUE leg is the locker; it must unlock"
    assert _having_gate_blockers(legs, clear, unlock) == [], (
        "the market is still locked out of the producer's scan, so every "
        "cleared leg would stay blank forever"
    )
    # And the unlocked leg really was correct — this is not a licence to clear
    # anything convenient.
    assert not any(leg in clear for leg in unlock)
    assert not any(leg in spare for leg in unlock)
    assert not refuse


def test_an_untouched_market_is_never_unlocked():
    """No clears, no unlock. The correct verdicts of a healthy market stand.

    The unlock exists to make a REPAIRED market re-gradeable. A market this
    filter finds nothing wrong with is not repaired, so removing a correct
    verdict there would be pure destruction — and it would hand the producer a
    market to re-grade for no reason.
    """
    correct = _legs(
        "KXNBA1HSPREAD-26MAR24NOPNYK",
        ["New York wins the 1H by over 2.5 points"],
        [True],
        home="New York Knicks", away="New Orleans Pelicans",
        final=(120, 100), periods=([30, 30, 30, 30], [25, 25, 25, 25]),
    )
    clear, unlock, spare, refuse = repair.classify(correct)
    assert clear == []
    assert unlock == [], "nothing was repaired here, so nothing may be unlocked"


def test_a_market_locked_by_a_venue_settlement_is_refused_whole():
    """We may not clear `api_settlement` to buy re-eligibility, so we clear nothing.

    A TRUE, non-overwritable verdict from a source other than `game_score` — the
    venue's own settlement above all — cannot be removed by this repair. Leaving
    it would strand every leg the repair cleared, so the only honest move is to
    refuse the market whole: a repair that cannot finish must not start.

    This is the one case where a market with genuinely wrong verdicts is left
    wrong on purpose, and it is reported as a refusal so the population stays
    visible rather than becoming a silent skip.
    """
    legs = _legs(**{**PORIND_1H_SPREAD, "foreign_locker": True})
    clear, unlock, spare, refuse = repair.classify(legs)
    assert clear == []
    assert unlock == []
    assert len(refuse) == len(legs)
    assert all("strand" in leg["refuse_reason"] for leg in refuse)


# --- CERT-2642: a market is the unit, and a survivor is a blocker ------------


def test_market_with_clearable_rows_and_a_true_refusal_is_refused_whole_and_stays_untouched():
    """🔴 THE BLOCK THIS ANSWERS (CERT-2642), and it is the SECOND locker.

    `foreign_locker` asks only about a TRUE verdict from a source that is not
    `game_score`. But every leg the candidate scan returns IS `game_score`, and
    a leg can land in the REFUSAL cohort — "the bug does not explain the stored
    verdict", which is #5237's bucket — while still being stored TRUE.

    Such a leg is non-overwritable, is not cleared and is not unlocked, so it
    survives the repair sitting in the producer's HAVING blocker set. The market
    then comes out in exactly the state CERT-2631 blocked: legs cleared to
    blank, and no route back. Worse than the first version, because this one
    also spends a correct verdict on the unlock.

    We may not clear it either: the bug does not explain it, so this repair has
    no verdict to offer and blanking it would be destroying a verdict on a
    guess. Refusing the market whole is the only honest move — and the market
    must come out COMPLETELY untouched, not partially.
    """
    spec = dict(PORIND_1H_SPREAD)
    # A stored TRUE the buggy reading cannot produce: Q1 was Portland by 4, so
    # "by over 20.5" is False under the bug and False under the truth — yet it
    # is stored TRUE. A different defect, and a locker.
    spec["names"] = spec["names"] + ["Portland wins the 1H by over 20.5 points"]
    spec["stored"] = spec["stored"] + [True]
    legs = _legs(**spec)

    # The market really would have had clearable legs without the survivor.
    baseline_clear, baseline_unlock, _s, _r = repair.classify(_legs(**PORIND_1H_SPREAD))
    assert baseline_clear and baseline_unlock, "fixture proves nothing otherwise"

    clear, unlock, spare, refuse = repair.classify(legs)
    assert clear == [], "cleared legs would be stranded behind the survivor"
    assert unlock == [], "a correct verdict must not be spent on a blocked market"
    assert spare == []
    assert len(refuse) == len(legs), "the market is refused WHOLE or not at all"
    assert all("cannot explain" in leg["refuse_reason"] for leg in refuse)


def test_a_true_leg_the_bug_does_explain_is_still_unlockable():
    """The refusal above must not swallow the ordinary case.

    A TRUE leg the bug DOES explain and the truth agrees with is a correct
    verdict standing in the doorway — that is the `unlock` cohort, and it is the
    whole of CERT-2631's repair. If the new survivor check caught those too, the
    repair would refuse every market it exists to fix.
    """
    clear, unlock, _spare, refuse = repair.classify(_legs(**PORIND_1H_SPREAD))
    assert clear and unlock and not refuse


def test_limit_never_splits_a_market_before_unlock():
    """🔴 THE BLOCK'S SECOND FINDING (CERT-2642). `--limit` selects MARKETS.

    `clear[:limit]` cut across a market, and the unlock then fired on the
    partially-cleared remains. Under `--limit 1` a three-rung 2H total cleared
    one wrong TRUE, unlocked the correct TRUE, and left another wrong TRUE
    blocking — the run spent a correct verdict to buy re-eligibility that the
    surviving blocker denies.
    """
    def _leg(mid, oid):
        return {"market_id": mid, "outcome_id": oid}

    three_rungs = [_leg(7, 1), _leg(7, 2), _leg(7, 3)]
    second_market = [_leg(9, 4), _leg(9, 5)]
    clear = three_rungs + second_market

    # A market larger than the limit is taken WHOLE, never split.
    picked = repair.select_whole_markets(clear, 1)
    assert picked == three_rungs, (
        "a limit smaller than the first market must still take that market "
        "whole — a partial market is the state this repair prevents"
    )

    # And the boundary never lands mid-market.
    for limit in range(1, len(clear) + 2):
        picked = repair.select_whole_markets(clear, limit)
        by_market = collections.Counter(leg["market_id"] for leg in picked)
        for mid, n in by_market.items():
            whole = sum(1 for leg in clear if leg["market_id"] == mid)
            assert n == whole, (
                f"limit={limit} took {n} of market {mid}'s {whole} clears — "
                f"the unlock would then fire on a market still holding a "
                f"wrong TRUE"
            )

    # Zero means no limit, not "nothing".
    assert repair.select_whole_markets(clear, 0) == clear


def test_a_declined_clear_withholds_that_markets_unlock():
    """A CAS decline leaves a wrong TRUE standing, so the unlock is not owed.

    `--limit` being market-atomic is not enough on its own: the forward write is
    a compare-and-swap, so a leg re-graded between the plan and the write
    declines. The market is then still blocked, and unlocking around the
    survivor spends a correct verdict on re-eligibility it will not get.
    """
    planned = collections.Counter({7: 3, 9: 2})

    # Everything landed on 9; one clear declined on 7.
    fully = repair.markets_fully_cleared(planned, collections.Counter({7: 2, 9: 2}))
    assert fully == {9}, "market 7 kept a wrong TRUE, so it gets no unlock"

    # All landed.
    assert repair.markets_fully_cleared(
        planned, collections.Counter({7: 3, 9: 2})
    ) == {7, 9}

    # A market that cleared nothing at all is not "fully cleared" by vacuum.
    assert repair.markets_fully_cleared(planned, collections.Counter()) == set()
