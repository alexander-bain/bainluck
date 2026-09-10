"""#4586 — guards for the stranded-market repair.

The repair's whole safety argument is its GATE: a market moves only when
`resolution_date` equals the candidate's `commence_time` exactly AND both team
tokens appear in the market name on a word boundary AND exactly one candidate
survives. On production those three together took 279 markets-with-a-candidate
down to 178 with **zero** ties, where time alone left 209 ambiguous.

Most of that gate is SQL, so these guards grade it two ways: the statements are
parsed as real Postgres (a syntax error is otherwise found only by a dyno whose
stdout nobody can read, gotcha #48), and the shipped SQL text is asserted
structurally for the clauses that ARE the safety argument. The apply loop's
Python — the compare-and-swap skip and the receipt it must not write — is driven
end to end against a fake session.
"""
import argparse
import asyncio
import importlib.util
import inspect
import pathlib

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_4586_stranded_voided_event_markets")
restore = _load("restore_4586_stranded_voided_event_markets")


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
        repair.SQL["repoint"],
        repair._PLAN_SQL,
        repair._RESIDUAL_SQL,
        restore._PLAN_SQL,
        restore._RESTORE_SQL,
        restore._TABLE_EXISTS_SQL,
    ):
        sqlglot.parse_one(sql, dialect="postgres")


def test_the_plan_refuses_more_than_one_candidate():
    """`HAVING count(*) = 1` is what turns "a candidate exists" into "the
    candidate is known".

    Without it the plan would resolve a tie by `min(e2.id)` — a coin flip
    dressed as a resolution, and on this population it would have decided 209
    of them. The aggregate is already `min(e2.id)`, so deleting the HAVING
    would not fail anywhere; it would just start guessing.
    """
    normalised = " ".join(repair._PLAN_SQL.split()).lower()
    assert "having count(*) = 1" in normalised


def test_the_gate_needs_both_team_names_and_not_just_one():
    """Two independent signals, per notice 40 — a title match alone is only a
    candidate.

    Measured: time alone → 279 with a candidate, 70 unambiguous. Time + BOTH
    names → 178, all 178 unambiguous. One name would put the second team's
    identity on trust.
    """
    agrees = repair._AGREES
    assert agrees.count("home_team_name") >= 2, "home token unused"
    assert agrees.count("away_team_name") >= 2, "away token unused"
    assert "e2.commence_time = fm.resolution_date" in " ".join(agrees.split())


def test_the_name_match_is_word_bounded_and_never_a_bare_substring():
    """`ILIKE '%'||token||'%'` also returns 178 today, and that is exactly why
    this guard exists.

    A predicate that happens not to be broken by today's rows is not the one to
    ship: a bare substring matches "Sox" inside a longer word, the `%yank%` /
    `Mayank` class of defect. The boundary costs nothing and cannot break.
    """
    agrees = " ".join(repair._AGREES.split())
    assert agrees.count(r"'\y'") >= 4, "word-boundary anchors missing"
    assert "ilike" not in agrees.lower(), "a bare substring match came back"


def test_a_degenerate_short_token_cannot_match_everything():
    """The >= 3 floor. A one- or two-character last token is the class that
    looks safe and is not — it would pair a real timestamp with a name signal
    carrying almost no information.
    """
    agrees = " ".join(repair._AGREES.split())
    assert agrees.count(">= 3") == 2, "the length floor is not on both tokens"


def test_only_espn_anchored_and_unretired_rows_can_be_a_target():
    """The destination must be a real fixture that is not itself retired.

    Re-pointing onto another voided row would move the market from one
    unreachable page to another and read as a successful repair.
    """
    agrees = " ".join(repair._AGREES.split())
    assert "e2.espn_id is not null" in agrees.lower()
    assert "e2.status not in ('voided', 'merged')" in agrees.lower()


def test_the_population_excludes_a_real_cancelled_fixture():
    """Zero of the 304 sit on an ESPN-anchored row, and the predicate is what
    keeps it that way.

    A genuinely cancelled game's markets belong where they are; only a phantom's
    do not. Scoping on `status='voided'` alone would put real postponements in
    range of a repair that has no standing to move them.
    """
    stranded = " ".join(repair._STRANDED.split()).lower()
    assert "e.espn_id is null" in stranded
    assert "e.external_id is null" in stranded
    assert "e.status = 'voided'" in stranded
    assert "fm.status = 'open'" in stranded


def test_the_write_is_a_compare_and_swap_on_the_link_it_planned():
    """`AND event_id = :old` is the difference between a repair and a race.

    The plan and the write are separate statements; the matcher runs every 15
    minutes. Without the old-value check, a market the matcher correctly
    re-linked in between would be dragged back to a decision made from stale
    state.
    """
    assert "event_id = :old" in " ".join(repair.SQL["repoint"].split())


def test_the_repair_writes_no_column_the_undo_does_not_restore():
    """One column out, one column back. A repair that writes more than its
    restore reads is an undo that silently does not undo.
    """
    written = {"event_id", "updated_at"}
    assert "set event_id = :new" in " ".join(repair.SQL["repoint"].split()).lower()
    restored = " ".join(restore._RESTORE_SQL.split()).lower()
    for col in written:
        assert col in restored, f"{col} is written but never restored"


# ---------------------------------------------------------------------------
# CERT-2439's required repair: 4586-RESTORE-CAS-PRESERVES-LATER-RELINKS
# ---------------------------------------------------------------------------
#
# THE DEFECT, IN ONE SENTENCE: the forward write compare-and-swaps on the link
# it planned, and the restore did not — it reverted every backed-up row whose
# live link differed from its backup, which is true both for a row the repair
# moved AND for a row the live matcher relinked afterwards. So the undo dragged
# a market the repair had CORRECTLY SKIPPED back onto the voided phantom.
#
# Reproduced by the grader against the exact predicate: market 1 on target 20
# (backup 10) and market 2 independently relinked to 30 (backup 11) restored to
# `[(1, 10), (2, 11)]` where `[(1, 10), (2, 30)]` is required.
#
# The behavioural proof lives in
# `tests/integration/test_restore_4586_manifest_cas_pg.py`, on a real server.
# These are the cheap structural halves that fail in one second rather than one
# CI job.


def test_the_undo_compare_and_swaps_on_the_target_not_merely_on_difference():
    """The clause the block was raised on.

    `event_id = :target` is the whole repair. Restoring on "differs from the
    backup" cannot tell a row this repair moved from a row something else moved,
    and reverting the second is a destructive write the undo never earned.
    """
    sql = " ".join(restore._RESTORE_SQL.split()).lower()
    assert "event_id = :target" in sql, (
        "the restore no longer requires the row to be on the repair's target — "
        "it can clobber a later, legitimate relink"
    )
    assert "is distinct from" not in sql, (
        "the difference-based predicate is back; see CERT-2439"
    )


def test_the_undo_reads_the_manifest_and_not_only_the_row_snapshot():
    """A backup records where a row CAME FROM; only a manifest records where
    this repair PUT it, and the CAS above needs the second one.
    """
    assert repair.MANIFEST_TABLE == restore.MANIFEST_TABLE
    assert repair.MANIFEST_TABLE not in ("futures_markets", repair.BAK_TABLE)
    assert restore.MANIFEST_TABLE in restore._PLAN_SQL
    assert "target_event_id" in restore._PLAN_SQL


def test_the_manifest_records_the_move_that_is_currently_in_force():
    """A market can be repaired, restored and repaired again.

    `ON CONFLICT DO NOTHING` would leave the restore CASing against a target two
    moves stale, which is the same class of defect one level down.
    """
    sql = " ".join(repair.SQL["man_record"].split()).lower()
    assert "on conflict (market_id) do update" in sql, sql
    assert "target_event_id = excluded.target_event_id" in sql


def test_the_manifest_is_written_in_the_same_transaction_as_the_move():
    """One commit, or the manifest can outlive a rolled-back write.

    Asserted on the source rather than on behaviour because the property is
    "there is no commit between them" — a fake session that counts commits
    cannot see a `commit()` that was never added.
    """
    body = inspect.getsource(repair.run)
    move = body.index('SQL["repoint"]')
    record = body.index('SQL["man_record"]')
    commit = body.index("await s.commit()")
    assert move < record < commit, (
        "the manifest is not written between the move and the single commit"
    )
    assert body.count("await s.commit()") == 1, (
        "a second commit split the move from its manifest"
    )


def test_a_skipped_forward_move_is_never_manifested(monkeypatch):
    """THE MUTANT THIS WHOLE REPAIR EXISTS FOR.

    Manifesting a market whose CAS declined recreates the block exactly: the
    restore would then revert a market this repair never moved. Same rule as the
    receipt — a record of a write that did not land is worse than no record.
    """
    s = _FakeSession([_Row(1, 10, 20), _Row(2, 11, 20)], rowcounts={1: 0})
    _run(s, monkeypatch, apply=True)

    assert len(s.repoints) == 2, "the CAS must be attempted for both"
    assert [p["mid"] for p in s.manifested] == [2], (
        "manifested a move that no-oped — the restore will clobber market 1"
    )


def test_every_manifested_move_is_also_receipted(monkeypatch):
    """The two records of the same act must not be able to disagree.

    A manifest without a receipt is an undo nobody can audit; a receipt without
    a manifest is an undo that cannot run. Both are written from the same
    successful-CAS branch, and this is what pins them together.
    """
    s = _FakeSession([_Row(1, 10, 20), _Row(2, 11, 21), _Row(3, 12, 22)],
                     rowcounts={2: 0})
    written = _run(s, monkeypatch, apply=True)
    assert [p["mid"] for p in s.manifested] == [r.market_id for r in written]


def test_the_manifest_carries_both_ends_of_the_move(monkeypatch):
    """`old` alone is the backup's job; the target is what the CAS needs."""
    s = _FakeSession([_Row(7, 10, 20)])
    _run(s, monkeypatch, apply=True)
    assert s.manifested == [{"mid": 7, "old": 10, "new": 20,
                             "now": s.manifested[0]["now"]}]


def test_the_undo_receipts_only_the_rows_it_actually_moved():
    """The reverse half of
    `test_a_market_that_moved_since_the_plan_is_skipped_and_never_receipted`.

    The forward direction was mutation-tested for this and the backward
    direction was not written at all — CERT-2439 also found that the restore
    appended NO receipt of any kind, and that its docstring's claim that "a
    later matcher pass" would add one is false: gotcha #15 says an already-
    linked market is never time-window re-matched, so no pass would ever visit
    these rows.
    """
    body = inspect.getsource(restore.run)
    skip = body.index('moved since the plan — skipped')
    append = body.index("receipts.append(")
    assert skip < append, "a skipped restore falls through into the receipt"
    assert "continue" in body[skip:append], "the skip does not short-circuit"
    assert "flush_receipts" in body, "the restore writes no receipt at all"


# ---------------------------------------------------------------------------
# the pure gates
# ---------------------------------------------------------------------------

def test_apply_gate_rejects_an_empty_reconciliation():
    """`all()` over an empty mapping is True — without the emptiness test a
    reconciliation that inspected NOTHING reads as a clean pass and `--apply`
    proceeds with no undo (gotcha #53).
    """
    assert repair.backup_is_exact({"futures_markets": 0})
    assert not repair.backup_is_exact({})
    assert not repair.backup_is_exact({"futures_markets": 4})


def test_the_python_side_re_asserts_the_ambiguity_refusal():
    """The SQL already guarantees it. This catches the one thing the SQL
    cannot: somebody widening the HAVING later without re-checking the write.
    """
    one = [type("R", (), {"candidates": 1})()]
    two = [type("R", (), {"candidates": 1})(), type("R", (), {"candidates": 2})()]
    assert repair.plan_is_unambiguous(one)
    assert not repair.plan_is_unambiguous(two)
    assert repair.plan_is_unambiguous([])


# ---------------------------------------------------------------------------
# the apply loop, end to end against a fake session
# ---------------------------------------------------------------------------

class _Row:
    def __init__(self, mid, old, new, name="Patriots vs. Seahawks"):
        self.market_id, self.old_event_id, self.new_event_id = mid, old, new
        self.market_name, self.source, self.market_external_id = name, "polymarket", "x"
        self.candidates = 1


class _Result:
    def __init__(self, rows=None, rowcount=0, one=None):
        self._rows, self.rowcount, self._one = rows or [], rowcount, one

    def all(self):
        return self._rows

    def one(self):
        return self._one

    def scalar_one(self):
        return self._one


class _FakeSession:
    """Answers by statement shape. Records every repoint it was asked for."""

    def __init__(self, plan, *, rowcounts=None, missing=0):
        self.plan, self.missing = plan, missing
        self.rowcounts = rowcounts or {}
        self.repoints, self.commits = [], 0
        #: CERT-2439. Recorded separately from `repoints` because the whole
        #: finding is that the two can disagree: the CAS may decline while the
        #: manifest still claims the move.
        self.manifested = []

    async def execute(self, stmt, params=None, *_a, **_kw):
        sql = " ".join(str(stmt).split())
        params = dict(params or {})
        # `stranded_total` FIRST: the residual query also contains
        # `HAVING count(*) = 1`, inside its `resolvable` CTE, so the looser
        # test matches both statements and the order is load-bearing.
        if "stranded_total" in sql:
            return _Result(one=type("C", (), {
                "stranded_total": 304, "resolvable": len(self.plan),
                "no_resolution_date": 0})())
        if "HAVING count(*) = 1" in sql:
            return _Result(rows=self.plan)
        if sql.startswith("SELECT count(*) FROM futures_markets s"):
            return _Result(one=self.missing)
        if sql.startswith(f"INSERT INTO {repair.MANIFEST_TABLE}"):
            self.manifested.append(params)
            return _Result(rowcount=1)
        if sql.startswith("UPDATE futures_markets SET event_id"):
            self.repoints.append(params)
            return _Result(rowcount=self.rowcounts.get(params["mid"], 1))
        return _Result()

    async def commit(self):
        self.commits += 1


def _run(session, monkeypatch, **kw):
    import contextlib

    import app.tasks.base as base
    import app.utils.match_receipts as mr

    written = []

    @contextlib.asynccontextmanager
    async def _sess():
        yield session

    async def _flush(_s, receipts, **_kw):
        written.extend(receipts)
        return len(receipts)

    monkeypatch.setattr(base, "get_task_session", _sess)
    monkeypatch.setattr(mr, "flush_receipts", _flush)
    args = argparse.Namespace(**{"backup": False, "apply": False, "limit": 0, **kw})
    asyncio.run(repair.run(args))
    return written


def test_a_dry_run_writes_nothing(monkeypatch):
    s = _FakeSession([_Row(1, 10, 20)])
    written = _run(s, monkeypatch)
    assert s.repoints == [] and written == []


def test_apply_refuses_when_the_backup_is_incomplete(monkeypatch):
    """D51: no undo, no apply. The refusal is the feature."""
    s = _FakeSession([_Row(1, 10, 20)], missing=1)
    written = _run(s, monkeypatch, apply=True)
    assert s.repoints == [], "applied without a complete backup"
    assert written == []


def test_apply_moves_the_planned_markets_and_receipts_each_one(monkeypatch):
    s = _FakeSession([_Row(1, 10, 20), _Row(2, 11, 20)])
    written = _run(s, monkeypatch, apply=True)

    assert [(p["mid"], p["old"], p["new"]) for p in s.repoints] == [
        (1, 10, 20), (2, 11, 20)]
    assert len(written) == 2
    for r, (old, new) in zip(written, [(10, 20), (11, 20)]):
        assert r.previous_event_id == old, "a move that cannot name where it came from"
        assert r.linked_event_id == new
        assert r.actor == "admin_repair"


def test_a_market_that_moved_since_the_plan_is_skipped_and_never_receipted(
        monkeypatch):
    """The compare-and-swap declined, so nothing happened — and a receipt
    claiming otherwise is worse than no receipt.

    This is the arm that makes the repair safe to run beside a live matcher: the
    receipt table is read as the record of what the system did, so a row written
    for a write that did not land turns an audit trail into a fiction.
    """
    s = _FakeSession([_Row(1, 10, 20), _Row(2, 11, 20)], rowcounts={1: 0})
    written = _run(s, monkeypatch, apply=True)

    assert len(s.repoints) == 2, "the CAS must be attempted for both"
    assert [r.market_id for r in written] == [2], "receipted a write that no-oped"


def test_limit_applies_a_prefix_and_not_a_sample(monkeypatch):
    """`--apply --limit 10` is the rehearsal step, so it must be the first ten
    of the printed plan — an arbitrary ten cannot be checked against the ledger.
    """
    s = _FakeSession([_Row(i, i + 10, 20) for i in range(1, 6)])
    _run(s, monkeypatch, apply=True, limit=2)
    assert [p["mid"] for p in s.repoints] == [1, 2]


def test_receipts_carry_the_repair_phase_and_are_not_ordinary_matcher_passes(
        monkeypatch):
    """The link-loss census is a GROUP BY actor/phase. A repair that files
    itself as a matcher pass disappears into the noise of the thing it is
    correcting.
    """
    s = _FakeSession([_Row(1, 10, 20)])
    written = _run(s, monkeypatch, apply=True)
    assert written[0].phase == "admin_repair"
    assert written[0].outcome == "superseded_by_twin_merge"


def test_the_restore_says_so_when_there_is_nothing_to_restore_from(monkeypatch):
    """A missing backup table is "this cannot be answered", not "nothing to do".

    An empty 200 is a response shape, not an absence (gotcha #53) — and a
    restore that prints a clean no-op when no backup was ever taken is exactly
    the reassuring wrong answer.
    """
    import contextlib

    import app.tasks.base as base

    class _NoTable:
        async def execute(self, stmt, params=None, *_a, **_kw):
            return _Result(one=False)

        async def commit(self):
            raise AssertionError("committed with no backup table")

    @contextlib.asynccontextmanager
    async def _sess():
        yield _NoTable()

    monkeypatch.setattr(base, "get_task_session", _sess)
    asyncio.run(restore.run(True))  # must not raise, must not commit


def test_the_backup_table_is_not_the_live_table(monkeypatch):
    """Belt and braces: a `.format` slip that pointed the backup at
    `futures_markets` would make `--apply` reconcile against itself and pass.
    """
    assert repair.BAK_TABLE == restore.BAK_TABLE
    assert repair.BAK_TABLE != "futures_markets"
    assert repair.BAK_TABLE in repair.SQL["bak_copy"]
