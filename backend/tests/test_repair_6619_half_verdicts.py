"""#6619 — the repair that un-says 614 half verdicts written from the full-time score.

The producer fix (`_market_period`, PR #6621) stops the bleeding. This is the
other half: the stored rows, which are still telling a reader that Valencia won
a half we hold no score for — and telling them the Draw, priced most likely at
45%, LOST it.

Three properties carry the whole thing and all three are guarded here:

* **the repair owns no copy of the period grammar.** #4923's repair mirrored
  `_PERIOD_SERIES_RE` into Postgres ARE, the mirror drifted onto a day-of-month
  (`KXMLSSPREAD-26APR22HOUSD` → `22H`), and it deleted 70 CORRECT verdicts on
  production. This one imports `_ticker_period` and `_name_period` and asks
  them. The source-scan tests below are what keep it that way, because the
  drift they prevent is invisible in any single run's output.
* **the SQL prefilter is a SUPERSET of the Python decision.** SQL narrows for
  cost and classifies nothing. If the prefilter ever stopped being a superset,
  rows would leave the cohort silently — a repair that quietly does less is the
  failure mode with no symptom. The containment is re-derived from the live
  regex here rather than asserted in prose.
* **a plan below the sanity floor has two causes and needs a discriminator.**
  "The predicate broke" and "the backlog is drained" look identical from the
  count alone, and the wrong answer is either a silent no-op or a repair run
  with a broken WHERE. The manifest is the discriminator; there is deliberately
  no `--allow-small`.
"""
import argparse
import asyncio
import importlib.util
import pathlib

import pytest
from sqlalchemy import exc as sqlalchemy_exc

import app.tasks.backfill_winners as bw

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
_REPAIR_NAME = "repair_6619_half_verdicts_from_the_full_time_score"
_RESTORE_NAME = "restore_6619_half_verdicts_from_the_full_time_score"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load(_REPAIR_NAME)
restore = _load(_RESTORE_NAME)

_REPAIR_SRC = (_SCRIPTS / f"{_REPAIR_NAME}.py").read_text()
_RESTORE_SRC = (_SCRIPTS / f"{_RESTORE_NAME}.py").read_text()


def _cli_flags(src: str) -> set:
    """Every `--flag` the script actually accepts, read from its argparse calls.

    A substring scan of the source cannot answer this: BOTH scripts name the
    flags they deliberately do NOT have, in prose, to explain the absence — and
    a scan would then report the explanation as the flag. Read the sentences,
    never the substring (notice 32's lesson, in a different costume). The AST
    walk asks the only question that matters: what can a caller type?
    """
    import ast

    flags = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value)
    return flags


REPAIR_FLAGS = _cli_flags(_REPAIR_SRC)
RESTORE_FLAGS = _cli_flags(_RESTORE_SRC)


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
        repair._CANDIDATE_SQL,
        restore._PLAN_SQL,
        restore._RESTORE_SQL,
    ):
        sqlglot.parse_one(sql, dialect="postgres")


def test_the_forward_write_is_a_compare_and_swap_on_the_value_it_removes():
    """`resolution_source = 'game_score'` in the WHERE is the whole safety.

    Between the plan and the write the venue's own settlement can land — which
    is the outcome this repair exists to make possible. Without the CAS the
    clear would delete Polymarket's verdict and put the row back in the
    ungraded pool it had just left.
    """
    sql = " ".join(repair.SQL["clear"].split())
    assert "WHERE id = :oid AND resolution_source = 'game_score'" in sql


def test_the_repair_writes_no_column_the_undo_does_not_restore():
    """Two columns out, the same two back. A third would have no undo."""
    cleared = {"is_winner", "resolution_source"}
    forward = " ".join(repair.SQL["clear"].split())
    back = " ".join(restore._RESTORE_SQL.split())
    for col in cleared:
        assert f"{col} = NULL" in forward or f"{col} = NULL," in forward
        assert f"{col} = :was_" in back
    assert "last_updated" not in forward


def test_the_repair_does_not_bump_the_price_clock():
    """`last_updated` is the PRICE clock (LIVE-077 / CERT-1936).

    Three surfaces read it as "when did somebody last look at this number", and
    this script reads no venue price. The touch-stamp guard's `settled` class
    would PERMIT the stamp; a permission is not a reason.
    """
    assert "last_updated" not in repair.SQL["clear"]
    assert "last_updated" not in restore._RESTORE_SQL


def test_the_undo_compare_and_swaps_on_still_ungraded_not_merely_on_difference():
    """`resolution_source IS NULL`, because "differs from its backup" is also
    true of a row the VENUE has settled since — and that undo would revert the
    venue's correct verdict to our invented one."""
    sql = " ".join(restore._RESTORE_SQL.split())
    assert "resolution_source IS NULL" in sql
    assert ":was_source = 'game_score'" in sql


def test_the_undo_reads_the_manifest_and_not_only_the_row_snapshot():
    """The manifest is the only record of what the repair DID (CERT-2439)."""
    sql = " ".join(restore._PLAN_SQL.split())
    assert sql.index(restore.MANIFEST_TABLE) < sql.index(restore.BAK_TABLE)
    assert f"JOIN {restore.BAK_TABLE} b ON b.id = m.outcome_id" in sql


def test_the_two_scripts_agree_on_the_table_names():
    """A restore pointed at a table the repair never wrote is a silent no-op."""
    assert repair.BAK_TABLE == restore.BAK_TABLE
    assert repair.MANIFEST_TABLE == restore.MANIFEST_TABLE


# ---------------------------------------------------------------------------
# THE DEPARTURE FROM #4923: the repair owns no copy of the grammar
# ---------------------------------------------------------------------------

def test_the_cohort_is_decided_by_the_producers_own_classifier():
    """`in_scope` must delegate, not re-implement.

    This is the single most important property in the file. #4923 answered
    "which period is this market about?" a SECOND time, in SQL, and the second
    answer drifted from the first and deleted 70 correct verdicts. Binding the
    decision to the imported functions means there is one answer by
    construction — so this test asserts the delegation by OBSERVING it, via a
    swap of the producer's own function.
    """
    assert repair.in_scope("977353", "Alavés vs. Valencia CF - Halftime Result") == "1h"

    # Swap the producer's classifier; the repair's decision must follow it.
    saved = bw._name_period
    try:
        bw._name_period = lambda name: None
        # The repair imported the name at module scope, so rebinding the
        # producer's attribute must still be visible through the import for the
        # delegation to be real — if `in_scope` had its own regex, this would
        # keep returning "1h".
        repair._name_period = bw._name_period
        assert repair.in_scope("977353", "Alavés vs. Valencia CF - Halftime Result") is None
    finally:
        bw._name_period = saved
        repair._name_period = saved


def test_the_repair_source_contains_no_period_regex_of_its_own():
    """THE ANTI-DRIFT SCAN, and it grades code no single run can reveal.

    A local `re.compile` in this file would be a second reading of the question
    `_NAME_PERIOD_RE` already answers, which is exactly the #4923 defect. The
    scan is on the SOURCE because a drifted copy produces correct-looking output
    right up until the day it does not.
    """
    assert "re.compile" not in _REPAIR_SRC, "the repair grew its own regex"
    assert "import re" not in _REPAIR_SRC
    # …and the same for the SQL: no period token may be classified in Postgres.
    for smell in ("~*", "SIMILAR TO", "split_part"):
        assert smell not in _REPAIR_SRC, f"the cohort is being classified in SQL ({smell})"


def test_the_classifier_import_is_the_deploy_gate():
    """The repair cannot start on a dyno that would re-write what it clears.

    `_name_period` exists only in the fixed producer (PR #6621), and it is
    imported at MODULE scope to decide the cohort — so on an unpatched dyno this
    script raises ImportError before argparse, before any session, before any
    write. #4923 could only ask a human to sequence this; here it is structural,
    and it matters because the beat re-runs every six hours.
    """
    head = _REPAIR_SRC.split("BAK_TABLE =")[0]
    assert "from app.tasks.backfill_winners import" in head
    assert "_name_period" in head and "_ticker_period" in head
    assert hasattr(bw, "_name_period"), "the producer fix is not present"


# ---------------------------------------------------------------------------
# the prefilter is a SUPERSET of the decision
# ---------------------------------------------------------------------------

#: Every alternative branch of `_NAME_PERIOD_RE`, spelled the way a market name
#: spells it. The containment argument is that each CONTAINS the literal "half".
_SPELLINGS = [
    "Halftime Result", "Half-time Result", "Half Time Result",
    "1st Half Winner", "First Half Total Goals",
    "2nd Half Winner", "Second Half Spread",
    "HALFTIME RESULT", "second half btts",
]


@pytest.mark.parametrize("name", _SPELLINGS)
def test_every_name_the_regex_accepts_is_caught_by_the_prefilter(name):
    """The superset property, derived from the live regex rather than asserted.

    SQL says `name ILIKE '%half%'`. If a spelling the classifier accepts did not
    contain "half", the prefilter would drop it and the repair would silently do
    less — the failure mode with no symptom.
    """
    assert bw._name_period(name) is not None, "fixture no longer exercises the regex"
    assert "half" in name.lower(), "the ILIKE prefilter would not see this row"


def test_the_prefilter_is_the_documented_pair_and_classifies_nothing():
    sql = " ".join(repair._PREFILTER.split())
    assert "fo.resolution_source = 'game_score'" in sql
    assert "fm.name ILIKE '%half%'" in sql


# ---------------------------------------------------------------------------
# disjointness from #4923, on the series production actually holds
# ---------------------------------------------------------------------------

#: The COMPLETE set of non-Polymarket series carrying a half-named `game_score`
#: outcome, measured on production 2026-09-17 (8,991 outcomes, 12 families, the
#: grouped query was not truncated). Every one classifies on its ticker, so the
#: two cohorts are measured disjoint and not merely intended to be.
_PRODUCTION_KALSHI_SERIES = [
    "KXNBA1HSPREAD", "KXNBA1HTOTAL", "KXNCAAF1HSPREAD", "KXNCAAMB1HSPREAD",
    "KXNCAAMB1HTOTAL", "KXNCAAF1HTOTAL", "KXNBA1HWINNER", "KXNBA2HWINNER",
    "KXNCAAMB1HWINNER", "KXNBA2HSPREAD", "KXNBA2HTOTAL", "KXNFL2HTOTAL",
]


@pytest.mark.parametrize("series", _PRODUCTION_KALSHI_SERIES)
def test_a_ticker_that_classifies_is_never_in_this_repairs_scope(series):
    """#4923's rows went through the INTENDED path and may be correct.

    A first half reached `_get_halftime_score`, a second reached
    `_period_scores`. Clearing one of those would delete a verdict that was
    computed from a real half score — the expensive direction of this mistake.
    """
    ticker = f"{series}-26SEP16BOSNYY"
    assert bw._ticker_period(ticker) is not None, "fixture no longer classifies"
    assert repair.in_scope(ticker, "First Half Spread") is None


def test_the_polymarket_specimen_is_in_scope():
    """60040627 — the row in the issue, and the reason the cohort exists."""
    assert bw._ticker_period("977353") is None
    assert repair.in_scope(
        "977353", "Deportivo Alavés vs. Valencia CF - Halftime Result") == "1h"


#: The COMPLETE set of non-segment uses of the word "half" in `futures_markets`
#: (19 markets, measured while building the producer fix). A bare `half` token
#: would have swept all of them in; the prefilter DOES catch them, which is
#: exactly why the Python decision re-filters.
_NON_SEGMENT_NAMES = [
    "Men's Halfpipe Winner", "Women's Ski Halfpipe Gold",
    "Half-Life 3 released in 2026", "Top Half Finish",
    "Bottom Half of the Draw", "EPL Top Half Finishers",
    "halfway-house opens", "Snowboard Halfpipe Medalist",
]


@pytest.mark.parametrize("name", _NON_SEGMENT_NAMES)
def test_a_non_segment_use_of_half_is_caught_by_the_prefilter_and_refused(name):
    """Both halves of the design in one assertion.

    The SQL prefilter is deliberately loose, so these rows DO reach Python — and
    Python refuses them. A repair that trusted the prefilter would clear a
    Halfpipe market's verdict.
    """
    assert "half" in name.lower(), "fixture is not a prefilter candidate"
    assert repair.in_scope("977353", name) is None


def test_a_name_with_no_period_at_all_is_refused():
    assert repair.in_scope("977353", "Alavés vs. Valencia CF") is None
    assert repair.in_scope("977353", None) is None


# ---------------------------------------------------------------------------
# the sanity floor and its discriminator
# ---------------------------------------------------------------------------

def test_a_healthy_plan_says_nothing():
    assert repair.explain_small_plan(repair.SANITY_FLOOR, 0) == ""


def test_a_small_plan_with_a_full_manifest_is_a_drained_backlog():
    msg = repair.explain_small_plan(3, repair.SANITY_FLOOR)
    assert msg.startswith("ALREADY APPLIED")


def test_a_small_plan_with_an_empty_manifest_is_a_broken_predicate():
    msg = repair.explain_small_plan(3, 0)
    assert msg.startswith("PREDICATE BROKE")


def test_there_is_no_override_flag_for_the_floor():
    """`--allow-small` would let the broken-predicate case through wearing the
    completed-run case's clothes. The manifest is the discriminator."""
    assert REPAIR_FLAGS == {"--backup", "--apply", "--limit"}, REPAIR_FLAGS


def test_the_floor_is_below_the_measured_population():
    """614 outcomes measured 2026-09-17; the floor is a LOWER bound on a
    population that is still GROWING until the producer fix deploys."""
    assert repair.SANITY_FLOOR < 614


def test_the_apply_gate_rejects_an_empty_reconciliation():
    """`all()` over an empty mapping is True, so the emptiness test carries the
    gate: a reconciliation that inspected nothing must not read as a pass."""
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"futures_outcomes": 0}) is True
    assert repair.backup_is_exact({"futures_outcomes": 1}) is False


# ---------------------------------------------------------------------------
# the apply loop, end to end against a fake session
# ---------------------------------------------------------------------------

class _Row:
    """A Polymarket half row: numeric external_id, period only in the name."""

    def __init__(self, oid, mid=900, name="Draw", ticker="977353",
                 market_name="Alavés vs. Valencia CF - Halftime Result",
                 is_winner=True):
        self.outcome_id, self.market_id = oid, mid
        self.outcome_name, self.ticker = name, ticker
        self.market_name, self.is_winner = market_name, is_winner


class _Result:
    def __init__(self, rows=None, rowcount=0, one=None):
        self._rows, self.rowcount, self._one = rows or [], rowcount, one

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._one


class _FakeSession:
    """Answers by statement shape. Records every clear it was asked for."""

    def __init__(self, plan, *, rowcounts=None, missing=0,
                 has_backup_table=True, manifest_rows=0):
        self.plan, self.missing = plan, missing
        self.has_backup_table = has_backup_table
        self.manifest_rows = manifest_rows
        self.rowcounts = rowcounts or {}
        self.cleared, self.manifested, self.commits = [], [], 0

    async def execute(self, stmt, params=None, *_a, **_kw):
        sql = " ".join(str(stmt).split())
        params = dict(params or {})
        if sql.startswith("SELECT fo.id"):
            return _Result(rows=self.plan)
        if repair.MANIFEST_TABLE in sql and "to_regclass" in sql:
            return _Result(one=self.manifest_rows > 0)
        if "to_regclass" in sql:
            return _Result(one=self.has_backup_table)
        if sql.startswith(f"SELECT count(*) FROM {repair.MANIFEST_TABLE}"):
            return _Result(one=self.manifest_rows)
        if sql.startswith("SELECT count(*) FROM futures_outcomes s"):
            if not self.has_backup_table:
                # What Postgres actually does, not a stand-in: the statement
                # names the backup table in a NOT EXISTS subquery.
                raise sqlalchemy_exc.ProgrammingError(
                    sql, {}, Exception(
                        f'relation "{repair.BAK_TABLE}" does not exist'))
            return _Result(one=self.missing)
        if sql.startswith(f"INSERT INTO {repair.MANIFEST_TABLE}"):
            self.manifested.append(params)
            return _Result(rowcount=1)
        if sql.startswith("UPDATE futures_outcomes SET is_winner = NULL"):
            self.cleared.append(params)
            return _Result(rowcount=self.rowcounts.get(params["oid"], 1))
        return _Result()

    async def commit(self):
        self.commits += 1


@pytest.fixture
def tiny_floor(monkeypatch):
    """The apply loop is tested on two rows; the floor is a production fact.

    `SANITY_FLOOR` says something about the size of a real backlog, not about
    how the loop behaves, and its own refusal is tested directly above. Leaving
    it at 500 here would mean every end-to-end test exercised the refusal path
    and nothing exercised the writes.
    """
    monkeypatch.setattr(repair, "SANITY_FLOOR", 1)


def _run(session, monkeypatch, **kw):
    import contextlib

    import app.tasks.base as base

    @contextlib.asynccontextmanager
    async def _sess():
        yield session

    monkeypatch.setattr(base, "get_task_session", _sess)
    args = argparse.Namespace(**{"backup": False, "apply": False, "limit": 0, **kw})
    asyncio.run(repair.run(args))


def test_a_preview_writes_nothing(monkeypatch, tiny_floor):
    s = _FakeSession([_Row(1), _Row(2)])
    _run(s, monkeypatch)
    assert s.cleared == [] and s.manifested == []


def test_apply_refuses_without_an_exact_backup(monkeypatch, tiny_floor):
    s = _FakeSession([_Row(1), _Row(2)], missing=2)
    _run(s, monkeypatch, apply=True)
    assert s.cleared == [], "cleared rows with no undo behind them"


def test_apply_clears_and_manifests_each_row(monkeypatch, tiny_floor):
    s = _FakeSession([_Row(1), _Row(2)])
    _run(s, monkeypatch, apply=True)
    assert [p["oid"] for p in s.cleared] == [1, 2]
    assert [p["oid"] for p in s.manifested] == [1, 2]


def test_the_negative_legs_are_cleared_too(monkeypatch, tiny_floor):
    """`Draw · Lost` is as unfounded as `Valencia CF · Won`.

    Both were decided from a full-time score that cannot answer a half's
    question. A repair that cleared only the crowns would leave the market
    printing "Lost" against the outcome it had priced most likely.
    """
    s = _FakeSession([_Row(1, is_winner=True), _Row(2, is_winner=False)])
    _run(s, monkeypatch, apply=True)
    assert [p["oid"] for p in s.cleared] == [1, 2]


def test_a_row_the_classifier_refuses_is_never_cleared(monkeypatch, tiny_floor):
    """The prefilter is loose on purpose; Python is what protects the row.

    A Halfpipe market and a Kalshi 1H market both reach this loop from SQL. If
    the decision were not re-applied here, the repair would clear both.
    """
    s = _FakeSession([
        _Row(1),
        _Row(2, market_name="Men's Halfpipe Winner"),
        _Row(3, ticker="KXNBA1HSPREAD-26SEP16BOSNYY", market_name="First Half Spread"),
    ])
    _run(s, monkeypatch, apply=True)
    assert [p["oid"] for p in s.cleared] == [1]


def test_a_declined_clear_is_never_manifested(monkeypatch, tiny_floor):
    """THE MUTANT THIS SCRIPT'S UNDO EXISTS FOR.

    Manifesting a row whose CAS declined tells the restore to write a verdict
    onto a row this repair never touched — and on this cohort that row is
    declining precisely because the VENUE graded it. The undo would replace
    Polymarket's settlement with our invented one.
    """
    s = _FakeSession([_Row(1), _Row(2)], rowcounts={1: 0})
    _run(s, monkeypatch, apply=True)
    assert [p["oid"] for p in s.cleared] == [1, 2], "the CAS must be attempted for both"
    assert [p["oid"] for p in s.manifested] == [2]


def test_the_canary_limit_stops_after_n(monkeypatch, tiny_floor):
    """`--apply --limit 10` is the canary step in the attended runbook."""
    s = _FakeSession([_Row(1), _Row(2), _Row(3)])
    _run(s, monkeypatch, apply=True, limit=2)
    assert [p["oid"] for p in s.cleared] == [1, 2]


def test_a_first_run_with_no_backup_table_still_plans(monkeypatch, tiny_floor):
    """The documented FIRST invocation is preview-only, before any backup exists.

    `bak_missing` names the backup table in a subquery, so it raises on that
    database (#4669). Asking `to_regclass` first keeps the preview readable —
    and `backup_is_exact({})` is False, so `--apply` still refuses.
    """
    s = _FakeSession([_Row(1)], has_backup_table=False)
    _run(s, monkeypatch)
    assert s.cleared == []
    _run(s, monkeypatch, apply=True)
    assert s.cleared == [], "applied with no backup table at all"


def test_an_empty_scope_with_an_empty_manifest_is_reported_as_a_stop(
        monkeypatch, tiny_floor, capsys):
    """Gotcha #53: "it returned" is not "it worked".

    Nothing in scope and nothing ever applied is a predicate matching nothing,
    not a drained backlog, and the run must say so out loud.
    """
    s = _FakeSession([_Row(1, market_name="Men's Halfpipe Winner")])
    _run(s, monkeypatch, apply=True)
    assert s.cleared == []
    assert "STOP" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the undo
# ---------------------------------------------------------------------------

def test_the_undo_has_no_false_positive_scope_flag_and_says_why():
    """#4923's restore needed `--outside-declared-cohort` to rescue the 70
    verdicts its SQL mirror had wrongly deleted. This repair has no second copy
    of the grammar, so it has no such class — and the docstring says that,
    rather than the flag being quietly absent."""
    assert RESTORE_FLAGS == {"--apply"}, RESTORE_FLAGS
    assert "outside-declared-cohort" in _RESTORE_SRC, (
        "the absence must be EXPLAINED, not silent — a later reader copying "
        "#4923's restore will look for this flag and must find out why it is gone"
    )
    assert "drift" in _RESTORE_SRC
