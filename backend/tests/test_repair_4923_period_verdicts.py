"""#4923 — the repair that un-says ~1,800 period verdicts written from the final score.

The producer fix (`_ticker_period`, PR #4944) stops the bleeding. This is the
other half: the stored rows, which are still telling a reader that both teams
scored in a first half that finished 1–0.

Two properties carry the whole thing and both are guarded here:

* **the cohort SQL and the producer's regex must agree.** They are two spellings
  of one question — "does this ticker name a period the final score cannot
  answer?" — in two languages, because Postgres ARE has no lookbehind. Two
  readings of one question is exactly what #4923 IS, and shipping a repair whose
  predicate has drifted from the guard would either miss rows or clear correct
  ones.
* **a plan below the sanity floor has two causes and needs a discriminator.**
  "The predicate broke" and "the backlog is drained" look identical from the
  count alone, and the wrong answer to that question is either a silent no-op or
  a repair run with a broken WHERE. The manifest is the discriminator; there is
  deliberately no `--allow-small`.
"""
import argparse
import asyncio
import importlib.util
import pathlib
import re

import pytest
from sqlalchemy import exc as sqlalchemy_exc

import app.tasks.backfill_winners as bw

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_4923_period_verdicts_from_the_final_score")
restore = _load("restore_4923_period_verdicts_from_the_final_score")


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
        repair._CENSUS_SQL,
        restore._PLAN_SQL,
        restore._RESTORE_SQL,
    ):
        sqlglot.parse_one(sql, dialect="postgres")


def test_the_forward_write_is_a_compare_and_swap_on_the_value_it_removes():
    """`resolution_source = 'game_score'` in the WHERE is the whole safety.

    Between the plan and the write, the venue's own settlement can land — which
    is the outcome this repair exists to make possible. Without the CAS the
    clear would delete Kalshi's verdict and put the row back in the ungraded
    pool it just left.
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


def test_the_repair_does_not_bump_the_price_clock():
    """`last_updated` is the PRICE stamp three surfaces read (CERT-1936).

    This script changes winner metadata and reads no venue price. The
    touch-stamp guard's `settled` class would permit the stamp; a permission is
    not a reason, and a repair that quietly refreshes a freshness clock is the
    #3243 defect from the other direction.
    """
    assert "last_updated" not in repair.SQL["clear"]
    assert "last_updated" not in restore._RESTORE_SQL


def test_the_undo_compare_and_swaps_on_still_ungraded_not_merely_on_difference():
    """CERT-2439's lesson, inherited rather than re-learned.

    On THIS cohort the likely post-repair state is "the venue graded it", so an
    undo keyed on "differs from the backup" would systematically overwrite real
    settlements with the invented ones.
    """
    sql = " ".join(restore._RESTORE_SQL.split())
    assert "resolution_source IS NULL" in sql
    assert ":was_source = 'game_score'" in sql


def test_the_undo_reads_the_manifest_and_not_only_the_row_snapshot():
    """The backup says what a row WAS; only the manifest says what we DID."""
    assert repair.MANIFEST_TABLE in restore._PLAN_SQL
    assert repair.BAK_TABLE in restore._PLAN_SQL


# ---------------------------------------------------------------------------
# the cohort, against the producer's own classifier
# ---------------------------------------------------------------------------

#: The SQL cohort's four alternatives, lifted out of the statement itself so the
#: test cannot drift from the text it is checking. They are valid Python regexes
#: as well as Postgres AREs for these constructs, which is what makes this a
#: parity test rather than a re-implementation. (It certifies the transcription,
#: not Postgres's engine — the statements' own syntax is covered above.)
_SQL_ALTERNATIVES = re.findall(r"~\*\s+'([^']+)'", repair._COHORT)


def _sql_says_in_cohort(ticker: str) -> bool:
    """What the cohort says about a ticker, matched the way the SQL matches it.

    #5023: the SQL applies its grammar to `split_part(external_id, '-', 1)`, so
    this helper must too. It used to match the whole ticker — which is exactly
    what the statement itself did, and both were wrong together, so every case
    in `COHORT_CASES` passed while production lost 70 correct verdicts. A parity
    helper that mirrors the bug is not a parity helper, so the assertion below
    pins the statement to the split rather than trusting this function to
    remember it.
    """
    assert len(_SQL_ALTERNATIVES) == 4, _SQL_ALTERNATIVES
    assert repair._SERIES in repair._COHORT, (
        "the cohort no longer matches on the series family — the ticker suffix "
        "is a date and two club codes and WILL produce period tokens (#5023)"
    )
    series = ticker.split("-", 1)[0]
    return any(re.search(a, series, re.I) for a in _SQL_ALTERNATIVES)


#: Real event-linked Kalshi series (production, 2026-09-10), each with what the
#: repair must do. `in_cohort` is NOT simply "is a period market": first-half
#: SPREAD and TOTAL rows went through `_get_halftime_score`, which reconstructs
#: a real half score, so they may be right and are deliberately left alone. Only
#: 1H **BTTS** is cleared, because that branch never consulted a half score.
COHORT_CASES = [
    # (series, in_cohort)
    ("KXMLS1HBTTS", True),
    ("KXMLS2HBTTS", True),
    ("KXWC1HBTTS", True),
    ("KXNFL1QBTTS", True),
    ("KXMLS2HTOTAL", True),
    ("KXNBA2HSPREAD", True),
    ("KXNBA2HWINNER", True),
    ("KXNCAAF2HSPREAD", True),
    ("KXNBA1QWINNER", True),
    ("KXNCAAF4QTOTAL", True),
    ("KXMLBF5SPREAD", True),
    ("KXMLBF5TOTAL", True),
    # left alone: a real halftime score was available to grade these
    ("KXNBA1HSPREAD", False),
    ("KXNBA1HTOTAL", False),
    ("KXNCAAMB1HWINNER", False),
    ("KXEPL1H", False),
    # left alone: whole-game questions the final score really does answer
    ("KXEPLH2H", False),
    ("KXEPLH2HFINISH", False),
    ("KXMLSBTTS", False),
    ("KXMLBTOTAL", False),
    ("KXMLBSPREAD", False),
    ("KXLIGUE1SPREAD", False),
    ("KXNBA3PT", False),
    ("KXNCAAF2PT", False),
    ("KXBUNDESLIGA2GAME", False),
]


@pytest.mark.parametrize("series,in_cohort", COHORT_CASES)
def test_the_cohort_matches_the_production_series_it_claims(series, in_cohort):
    assert _sql_says_in_cohort(f"{series}-26SEP09CHIMIA") is in_cohort


@pytest.mark.parametrize("series,in_cohort", COHORT_CASES)
def test_the_cohort_and_the_producer_guard_agree(series, in_cohort):
    """One question, two languages — and they must give the same answer.

    The producer refuses every period; the repair clears every period EXCEPT
    the first halves it could grade honestly. So the expected relation is not
    equality, it is: in the cohort ⇒ the producer also calls it a period, and a
    producer period is out of the cohort only when it is a 1H that is not BTTS.
    """
    ticker = f"{series}-26SEP09CHIMIA"
    period = bw._ticker_period(ticker)
    if in_cohort:
        assert period is not None, (
            f"{series} is cleared by the repair but the producer would still "
            f"grade it — the two predicates have drifted"
        )
    elif period is not None:
        assert period == "1h" and "BTTS" not in series.upper(), (
            f"{series} is a period the producer refuses, and the repair leaves "
            f"its stored rows alone for no stated reason"
        )


def test_the_head_to_head_carve_out_is_the_reason_the_cohort_is_a_regex():
    """`KXEPLH2H` contains "2H" and is about the whole game.

    Python expresses this as a lookbehind and Postgres cannot, so the SQL says
    "a character that is not H, or the start of the string". If that clause is
    ever simplified away, this is the row that pays: clearing it would delete a
    correct verdict, which no reader would ever notice.
    """
    assert _sql_says_in_cohort("KXEPLH2H-26SEP09ARSCHE") is False
    assert _sql_says_in_cohort("KXEPL2H-26SEP09ARSCHE") is True


#: The twelve production tickers the 2026-09-11 01:37Z run cleared and should
#: not have (#5023), verbatim. Every one is a WHOLE-GAME or halftime-derived
#: market whose verdict was correct; every one was matched on its date suffix,
#: where a day-of-month runs straight into a club code. The `COHORT_CASES`
#: fixtures above all carry the benign suffix `-26SEP09CHIMIA`, which is why
#: they were green throughout — a hostile fixture is the only kind that tests
#: this.
DATE_SUFFIX_FALSE_POSITIVES = [
    ("KXMLSSPREAD-26APR22HOUSD", "22H: day 22 + HOUston"),
    ("KXMLSTOTAL-26APR22HOUSD", "22H: day 22 + HOUston"),
    ("KXMLSBTTS-26APR22HOUSD", "22H: day 22 + HOUston"),
    ("KXMLSBTTS-26MAY02HOUCOL", "02H: day 02 + HOUston"),
    ("KXNCAAMBGAME-26FEB22HCBUCK", "22H: day 22 + Holy Cross"),
    ("KXNCAAMBSPREAD-26FEB22HCBUCK", "22H: day 22 + Holy Cross"),
    ("KXNCAAMBTOTAL-26FEB22HCBUCK", "22H: day 22 + Holy Cross"),
    ("KXNCAAMBGAME-26MAR01QUINCAN", "01Q: day 01 + QUINnipiac"),
    ("KXNCAAMBSPREAD-26MAR01QUINCAN", "01Q: day 01 + QUINnipiac"),
    ("KXNCAAMBTOTAL-26MAR01QUINCAN", "01Q: day 01 + QUINnipiac"),
    # 1H spread/winner: real period markets, but graded from the real halftime
    # score, so they are out of the cohort on their own terms — and this suffix
    # dragged them in regardless of that.
    ("KXNBA1HSPREAD-26MAR02HOUWAS", "02H: day 02 + HOUston"),
    ("KXNBA1HWINNER-26MAR02HOUWAS", "02H: day 02 + HOUston"),
]


@pytest.mark.parametrize("ticker,why", DATE_SUFFIX_FALSE_POSITIVES)
def test_a_date_suffix_never_puts_a_market_in_the_cohort(ticker, why):
    """The suffix is a date and two club codes. It is not a period. (#5023)"""
    assert _sql_says_in_cohort(ticker) is False, (
        f"{ticker} is back in the cohort via its suffix ({why}) — clearing it "
        f"deletes a correct verdict, silently"
    )


@pytest.mark.parametrize("ticker,why", DATE_SUFFIX_FALSE_POSITIVES)
def test_the_producer_always_read_these_tickers_correctly(ticker, why):
    """`_ticker_period` splits on the first dash and always did.

    The resolver shipped in #4923 never had this bug — only the repair's SQL
    mirror of it did. If this ever fails, the producer has acquired the bug the
    repair had, and 6,116 correct first-half grades are the population at risk.
    """
    period = bw._ticker_period(ticker)
    if "1H" in ticker.split("-", 1)[0].upper():
        assert period == "1h"          # a real period, refused for a real reason
    else:
        assert period is None, (
            f"{ticker} is a whole-game market and the producer now calls it a "
            f"period ({period}) — it would stop grading it at all"
        )


def test_the_undos_false_positive_scope_is_the_negation_of_the_cohort():
    """`--outside-declared-cohort` must ask the repair's own question. (#5023)

    Two files, one grammar. If the repair widens its cohort and the restore's
    scope does not follow, the undo silently stops covering rows the repair
    silently started clearing.
    """
    assert restore._DECLARED_COHORT.count("~*") == len(_SQL_ALTERNATIVES)
    for alternative in _SQL_ALTERNATIVES:
        assert alternative in restore._DECLARED_COHORT, alternative
    assert restore._SERIES == repair._SERIES
    assert restore._OUTSIDE_SCOPE.startswith("WHERE NOT ")


# ---------------------------------------------------------------------------
# the floor, and its discriminator
# ---------------------------------------------------------------------------

def test_a_healthy_plan_says_nothing():
    assert repair.explain_small_plan(repair.SANITY_FLOOR, 0) == ""


def test_a_small_plan_with_a_full_manifest_is_a_drained_backlog():
    msg = repair.explain_small_plan(3, repair.SANITY_FLOOR)
    assert msg.startswith("ALREADY APPLIED")


def test_a_small_plan_with_an_empty_manifest_is_a_broken_predicate():
    msg = repair.explain_small_plan(3, 0)
    assert msg.startswith("PREDICATE BROKE")
    assert "allow-small" not in msg, "the override flag is the wrong answer here"


def test_the_apply_gate_rejects_an_empty_reconciliation():
    """`all()` over an empty mapping is True — the emptiness test is the guard.

    Without it, a reconciliation that inspected nothing reads as a clean pass
    and `--apply` proceeds with no undo (gotcha #53).
    """
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"futures_outcomes": 0}) is True
    assert repair.backup_is_exact({"futures_outcomes": 1}) is False


# ---------------------------------------------------------------------------
# the apply loop, end to end against a fake session
# ---------------------------------------------------------------------------

class _Row:
    def __init__(self, oid, mid=900, name="Yes", ticker="KXMLS1HBTTS-26SEP09CHIMIA"):
        self.outcome_id, self.market_id = oid, mid
        self.outcome_name, self.ticker = name, ticker
        self.market_name, self.is_winner = "First Half BTTS", True


class _Census:
    cohort, outcomes, markets, affirmative = "half_btts", 2, 2, 2


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
        if "GROUP BY 1" in sql and "cohort" in sql:
            return _Result(rows=[_Census()])
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
    it at 1,500 here would mean every end-to-end test exercised the refusal
    path and nothing exercised the writes.
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


def test_a_dry_run_writes_nothing(monkeypatch, tiny_floor):
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


def test_a_declined_clear_is_never_manifested(monkeypatch, tiny_floor):
    """THE MUTANT THIS SCRIPT'S UNDO EXISTS FOR.

    Manifesting a row whose CAS declined tells the restore to write a verdict
    onto a row this repair never touched — and on this cohort that row is
    declining precisely because the VENUE graded it. The undo would replace
    Kalshi's settlement with our invented one.
    """
    s = _FakeSession([_Row(1), _Row(2)], rowcounts={1: 0})
    _run(s, monkeypatch, apply=True)
    assert [p["oid"] for p in s.cleared] == [1, 2], "the CAS must be attempted for both"
    assert [p["oid"] for p in s.manifested] == [2]


def test_a_first_run_with_no_backup_table_still_plans(monkeypatch, tiny_floor):
    """The documented FIRST invocation is plan-only, before any backup exists.

    `bak_missing` names the backup table in a subquery, so it raises on that
    database (#4669). Asking `to_regclass` first keeps the dry run readable —
    and `backup_is_exact({})` is False, so `--apply` still refuses.
    """
    s = _FakeSession([_Row(1)], has_backup_table=False)
    _run(s, monkeypatch)
    assert s.cleared == []
    _run(s, monkeypatch, apply=True)
    assert s.cleared == [], "applied with no backup table at all"
