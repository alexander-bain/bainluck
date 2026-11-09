"""#11649: delete, don't rename; and a second run gets its own backup tables.

The scoped preview on Nov 9 (one-off run.6522) planned all 146 Exact Margin /
First Touchdown Scorer fixtures as Branch B: rename the oldest row, delete the
rest. But each one's real game was already in the table under full names:
fake 15344441 "Lakers" vs "Pistons - Exact Margin" beside real 15343927
"Detroit Pistons" vs "Los Angeles Lakers", same start. Renaming would have left
"Lakers vs Pistons" beside the real game (CERT-880). ``--delete-unmatched``
deletes a Branch B fixture whole and unlinks its markets instead.

And the September run's ``bak_2871_*`` tables are still in production (12,266
events). The restore restores everything it finds, so ``--backup-prefix`` keeps a
second run's undo from also undoing September.
"""
import asyncio

import pytest

from tests.test_repair_2871_phantom_derivative_events import (
    THUN,
    _StmtRecorder,
    _alias,
    _plan,
    _row,
    repair,
    restore,
)


def _branch_b():
    g = _plan(THUN, alias=[_alias("FC Thun", "Lausanne-Sport", "2026-08-30",
                                  n3=0, n7=0, alias_id=None)])[0][0]
    assert g.branch == "B"
    return g


def _apply(group, **kw):
    rec = _StmtRecorder()
    counts = asyncio.run(repair.apply_group(rec, group, **kw))
    return rec.sql, counts


def test_delete_unmatched_deletes_every_member_and_renames_nothing():
    g = _branch_b()
    sql, counts = _apply(g, delete_unmatched=True)
    assert not [s for s in sql if "away_team_name = :clean" in s], "renamed a phantom"
    assert not [s for s in sql if "win_probability_sources = NULL" in s]
    deletes = [s for s in sql if s.startswith("DELETE FROM events")]
    assert len(deletes) == 1 and counts["deleted_events"] == 1
    assert counts["renamed"] == 0


def test_delete_unmatched_unlinks_markets_ledgered_first():
    g = _branch_b()
    sql, counts = _apply(g, delete_unmatched=True)
    ledger = [i for i, s in enumerate(sql) if "INSERT INTO" in s and "market_repoint" in s]
    unlink = [i for i, s in enumerate(sql) if "SET event_id = NULL" in s]
    assert ledger and unlink and ledger[0] < unlink[0], sql
    assert ", 0 FROM futures_markets" in sql[ledger[0]]  # 0 = "unlinked"
    assert counts["unlinked"] == 1


def test_delete_unmatched_deletes_children_before_their_events():
    g = _branch_b()
    sql, _ = _apply(g, delete_unmatched=True)
    child = [i for i, s in enumerate(sql)
             if s.startswith("DELETE FROM") and not s.startswith("DELETE FROM events")]
    event = [i for i, s in enumerate(sql) if s.startswith("DELETE FROM events")]
    assert len(child) == len(repair.CHILD_DELETE_TABLES)
    assert max(child) < event[0]


def test_without_the_flag_branch_b_still_renames():
    """The control arm: the default run is unchanged."""
    sql, counts = _apply(_branch_b())
    assert counts["renamed"] == 1
    assert not [s for s in sql if "SET event_id = NULL" in s]


def test_delete_unmatched_leaves_a_real_counterpart_merge_alone():
    """Branch A still re-points onto the real event; the flag only changes B."""
    rows = [_row(11, "Como 1907", "US Lecce - Exact Score", "US Lecce", real=900)]
    g = _plan(rows)[0][0]
    assert g.branch == "A"
    sql, counts = _apply(g, delete_unmatched=True)
    assert [s for s in sql if "SET event_id = :survivor" in s]
    assert not [s for s in sql if "SET event_id = NULL" in s]
    assert counts.get("unlinked", 0) == 0


@pytest.fixture
def prefix_restored():
    yield
    repair.use_backup_prefix("bak_2871_")
    restore.use_backup_prefix("bak_2871_")


def test_a_backup_prefix_moves_the_backup_and_the_ledger(prefix_restored):
    repair.use_backup_prefix("bak_11649_")
    assert repair.BAK_PREFIX == "bak_11649_"
    assert repair.LEDGER == "bak_11649_market_repoint"
    restore.use_backup_prefix("bak_11649_")
    assert restore.BAK_PREFIX == "bak_11649_"


@pytest.mark.parametrize("bad", ["bak_11649", "events_", "bak_; DROP TABLE x_", "BAK_X_", ""])
def test_a_backup_prefix_is_an_identifier_or_refused(bad, prefix_restored):
    with pytest.raises(ValueError):
        repair.use_backup_prefix(bad)
    with pytest.raises(ValueError):
        restore.use_backup_prefix(bad)


def test_the_restore_moves_an_unlinked_market_back():
    src = open(restore.__file__).read()
    assert src.count("OR (r.new_event_id = 0 AND f.event_id IS NULL)") == 2


def test_the_new_statements_parse_as_postgres():
    sqlglot = pytest.importorskip("sqlglot")
    for name in ("ledger_unlink_insert", "unlink"):
        sql = repair.SQL[name].format(ledger=repair.LEDGER)
        assert sqlglot.parse(sql, dialect="postgres")[0] is not None, name
