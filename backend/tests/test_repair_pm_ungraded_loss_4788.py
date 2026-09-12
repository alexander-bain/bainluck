"""#4788 (CAL-P1088) — the parts of the ungraded-loss withdrawal that need no database.

The write itself is guarded by
``tests/integration/test_repair_pm_ungraded_loss_4788_pg.py``, which runs where
CI provides a server. **These run everywhere**, and they cover the four things
that rot without one:

1. **the blast radius.** This rail exists to write ONE column. ``is_winner`` is
   truth (gotcha #21), ``resolution_source`` is the cohort's own key, and
   ``last_updated`` is a poller touch-stamp another surface reads as liveness
   (#2024). A widening SET clause is the realistic decay and it is silent — the
   rail would still report the same row count.
2. **the rail crowns nobody.** The entire argument for running this without a
   venue call (notice 26) is that withdrawing a verdict we never made is a fact
   about our own row. The moment a ``TRUE`` appears on the write side, that
   argument is void and the rail needs the venue.
3. **the MARKET-level gate.** 854 resolved Polymarket markets DO have a crowned
   winner; their ``false`` legs genuinely lost and are merely un-badged. The
   anti-join is the only thing standing between this rail and manufacturing the
   opposite defect on them, and it is one ``NOT EXISTS`` deep in an f-string.
4. **the D51 refusals.** An apply whose backup does not cover every planned id
   must roll back, and a restore that cannot find its backup table must say so
   rather than report zero rows restored (gotcha #53: an empty result is a
   response shape, not an absence).
"""

from __future__ import annotations

import ast
import inspect
import re
from types import SimpleNamespace

import pytest

from app.tasks import repair_pm_ungraded_loss as rail


# ---------------------------------------------------------------------------
# source scanning
# ---------------------------------------------------------------------------


def _parsed() -> ast.Module:
    """The module's AST with every docstring removed.

    Docstrings are excluded because this file's whole subject is discussed in
    prose there — ``is_winner``, ``true`` and ``resolution_source`` all appear
    in the module docstring by necessity, so a naive substring scan over raw
    source fails on its own explanation.

    ``inspect.getsource`` is not safe on every ``app.tasks`` module — a celery
    task can shadow the module name and yield a stub with no SQL in it, which
    makes a scan vacuously green (CAL-P1085 lost an hour to exactly that). It is
    safe here, and the non-emptiness assertion below is what PROVES that rather
    than assuming it.
    """
    source = inspect.getsource(rail)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            body.pop(0)
    return tree


def _sql_literals() -> list[str]:
    """Every string constant in the module that reads like SQL."""
    out = []
    for node in ast.walk(_parsed()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if re.search(r"\b(SELECT|UPDATE|INSERT|CREATE|NOT EXISTS)\b", text):
                out.append(text)
    return out


def test_the_scan_has_something_to_scan():
    """A source scan that found no SQL is a passing test that proves nothing."""
    literals = _sql_literals()
    assert literals, "no SQL literals found — the scan below would be vacuous"
    assert any("UPDATE futures_outcomes" in s for s in literals)


def _assigned_columns(sql: str) -> set[str]:
    """The columns named on the left of ``=`` inside a SET clause."""
    match = re.search(r"\bSET\b(.*?)(?:\bFROM\b|\bWHERE\b|$)", sql, re.S | re.I)
    assert match, f"no SET clause found in:\n{sql}"
    return set(re.findall(r"(\w+)\s*=", match.group(1)))


def test_the_apply_writes_exactly_one_column():
    """`is_winner`, and nothing else.

    `resolution_source` must stay NULL — it is the cohort's key, and writing it
    would both destroy the bound's idempotence and claim a grader that does not
    exist. `last_updated` must stay untouched: `playoffs.py` reads it as "the
    poller is alive", so a repair that stamps it fakes liveness for 574,832 rows
    (#2024).
    """
    assert _assigned_columns(rail._APPLY_SQL) == {"is_winner"}


def test_the_restore_writes_exactly_one_column():
    """The undo is the mirror of the write, or it is not an undo."""
    assert _assigned_columns(rail._RESTORE_SQL) == {"is_winner"}


def test_the_rail_crowns_nobody():
    """No write in this module may set a leg TRUE.

    This is the whole reason the rail is allowed to run without asking
    Polymarket (notice 26). Crowning a winner is a claim ABOUT THE VENUE and
    belongs to `pm-never-graded`, which asks the CLOB. Withdrawing a verdict we
    never made is a claim about our own row and needs nobody's permission.
    """
    for sql in _sql_literals():
        set_match = re.search(
            r"\bSET\b(.*?)(?:\bFROM\b|\bWHERE\b|$)", sql, re.S | re.I
        )
        if not set_match:
            continue
        assert not re.search(r"is_winner\s*=\s*true", set_match.group(1), re.I), (
            f"a write in this module crowns a winner:\n{sql}"
        )


def test_the_write_is_a_withdrawal_and_not_a_reprice():
    """No price column may appear on the left of a SET anywhere in the module.

    The rail has no opinion about what the market thought — only about whether
    we graded it. `current_probability`, `opening_probability` and
    `calibration_probability` are the three a well-meaning extension would
    reach for.
    """
    prices = {
        "current_probability",
        "opening_probability",
        "calibration_probability",
        "current_yes_bid",
        "current_yes_ask",
    }
    for sql in (rail._APPLY_SQL, rail._RESTORE_SQL):
        assert not (_assigned_columns(sql) & prices)


def test_the_bound_is_gated_at_the_market():
    """The anti-join is load-bearing and it is easy to lose in an f-string.

    Without it this rail nulls the losing legs of the 854 markets whose winner
    IS crowned — legs that genuinely lost — which is the same defect with the
    sign flipped. Asserted on the composed bound, not on the fragment, because
    the fragment can exist while the interpolation that uses it is dropped.
    """
    bound = rail._BOUND_SQL
    assert "NOT EXISTS" in bound
    assert "g.resolution_source IS NOT NULL" in bound
    assert "g.is_winner IS TRUE" in bound
    assert "g.market_id = fo.market_id" in bound


def test_the_bound_selects_only_an_affirmative_false():
    """`is_winner = false`, never `IS NOT TRUE`.

    `IS NOT TRUE` also matches NULL, which would put every already-withdrawn leg
    back in the bound — the rail would re-back-up rows at their withdrawn value
    on a second pass and quietly turn its own undo into a no-op.
    """
    assert "fo.is_winner = false" in rail._BOUND_SQL
    assert "fo.resolution_source IS NULL" in rail._BOUND_SQL
    assert "fm.source = 'polymarket'" in rail._BOUND_SQL
    assert "fm.status = 'resolved'" in rail._BOUND_SQL


def test_the_bound_is_keyset_paged_in_a_stable_order():
    """`after_id` + ORDER BY id, or the walk can skip rows it never saw."""
    assert "fo.id > :after_id" in rail._BOUND_SQL
    assert "ORDER BY fo.id" in rail._BOUND_SQL
    assert "LIMIT :page_limit" in rail._BOUND_SQL


def test_the_backup_never_overwrites_an_earlier_row():
    """`ON CONFLICT DO NOTHING`.

    A leg may be withdrawn, restored and withdrawn again. The FIRST backup is
    the one that predates this rail; re-copying after an apply would back up the
    withdrawn value and make the undo restore NULL onto NULL.
    """
    assert "ON CONFLICT (outcome_id) DO NOTHING" in rail._BAK_COPY


# ---------------------------------------------------------------------------
# CERT-2524 — the page is frozen, and the write cannot outrun its backup
# ---------------------------------------------------------------------------


def test_only_the_plan_read_is_limited_and_keyset_paged():
    """The finding, as a source invariant: ONE moving read, and it is the first.

    `_BOUND_SQL` is `ORDER BY ... LIMIT`, so re-running it under a later
    snapshot returns a DIFFERENT set of rows — a grader that pushes a market out
    of the bound lets the `LIMIT` pull an unseen row in. The first cut of this
    rail re-ran it to back up, to check the backup, and again inside the
    `UPDATE`; the rows that entered on the third run were changed with no backup
    behind them. Every statement after the plan must therefore be keyed on the
    frozen id list and on nothing else.
    """
    for name in ("_BAK_COPY", "_BAK_MISSING", "_APPLY_SQL", "_BAK_PRUNE"):
        sql = getattr(rail, name)
        assert ":page_ids" in sql, f"{name} does not key on the frozen page"
        assert "LIMIT" not in sql.upper(), f"{name} re-derives a LIMITed scope"
        assert ":after_id" not in sql, f"{name} re-walks the keyset"


def test_the_write_can_only_reach_a_row_the_backup_already_holds():
    """`FROM <backup> b WHERE b.outcome_id = fo.id` — a join, not a check.

    A counting gate can be beaten by anything that changes between the count and
    the write. A join cannot: a row with no backup row has nothing to join to,
    so it is not merely rejected, it is unreachable. That is what makes the
    one-command D51 undo a property of the statement rather than a promise.
    """
    apply_sql = rail._APPLY_SQL
    assert f"FROM {rail.BAK_TABLE} b" in apply_sql
    assert "b.outcome_id = fo.id" in apply_sql


def test_the_write_re_tests_the_market_gate_it_was_planned_under():
    """The plan may be seconds old; the market may have been graded since.

    The gate has to be re-evaluated in the write's OWN snapshot, not inherited
    from the plan read, or a market graded in between is withdrawn from a stale
    reading of the world.
    """
    apply_sql = rail._APPLY_SQL
    assert "NOT EXISTS" in apply_sql
    assert "g.resolution_source IS NOT NULL" in apply_sql
    assert "g.is_winner IS TRUE" in apply_sql
    assert "fo.is_winner = false" in apply_sql
    assert "fo.resolution_source IS NULL" in apply_sql


def test_the_lock_covers_every_leg_of_the_market_not_just_the_page():
    """A market split across a page boundary leaves the grader an unlocked leg.

    Locking only the page's own legs would let a grader crown the sibling on the
    far side of the boundary at the same instant this rail withdraws the near
    side — the market ends up with a winner AND withdrawn losers, which is the
    reader-visible defect this rail exists to remove, re-created on a market
    that now has a genuine grade.
    """
    assert "fo.market_id = ANY(:market_ids)" in rail._LOCK_SQL
    assert "FOR UPDATE" in rail._LOCK_SQL
    assert "LIMIT" not in rail._LOCK_SQL.upper()


def test_the_lock_is_bounded_so_a_busy_row_refuses_instead_of_hanging():
    """An attended admin request must not wait on a lock for ever."""
    assert rail.LOCK_TIMEOUT_MS > 0
    assert rail._LOCK_TIMEOUT_SQLSTATE == "55P03"


def test_the_undo_will_not_overwrite_a_verdict_somebody_else_wrote():
    """`resolution_source IS NULL` on the restore.

    Every backed-up leg was source-less when it was withdrawn. If one carries a
    source now, `pm-never-graded` (or any grader) decided it in the meantime,
    and putting our remembered `false` back would re-fabricate the very `Lost`
    this rail removed — this time on a market that HAS been graded honestly.
    """
    assert "fo.resolution_source IS NULL" in rail._RESTORE_SQL
    assert "fo.resolution_source IS NULL" in rail._RESTORE_PENDING


# ---------------------------------------------------------------------------
# the decision, without a database
# ---------------------------------------------------------------------------


def _row(outcome_id=1, market_id=10, price=None):
    return SimpleNamespace(
        outcome_id=outcome_id,
        market_id=market_id,
        before_is_winner=False,
        last_price=price,
    )


def test_a_price_at_the_threshold_counts_as_contradicting():
    """The boundary, pinned. `>=`, not `>`."""
    assert rail._record(_row(price=rail.CONTRADICTION_PRICE))["price_contradicts"]
    assert not rail._record(
        _row(price=rail.CONTRADICTION_PRICE - 0.0001)
    )["price_contradicts"]


def test_a_leg_with_no_price_is_not_reported_as_contradicted():
    """NULL is "we never had a number", not "the number was low" (gotcha #53)."""
    assert not rail._record(_row(price=None))["price_contradicts"]


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing():
    """The default is read-only, and it is the default an operator hits first."""
    calls: list[str] = []

    class _Result:
        def all(self):
            return [_row(price=0.96)]

    class _Session:
        async def execute(self, statement, params=None):
            calls.append(str(statement))
            return _Result()

        async def commit(self):  # pragma: no cover — must never be reached
            calls.append("COMMIT")

    census = await rail.repair(_Session())

    assert census["terminal"] == "dry_run"
    assert census["changed"] == 0
    assert census["planned"] == 1
    assert census["price_contradicted"] == 1
    assert not any("UPDATE" in c for c in calls)
    assert "COMMIT" not in calls


@pytest.mark.asyncio
async def test_the_dry_run_carries_the_undo_command():
    """An operator reading the plan must not have to go and find the undo."""
    class _Result:
        def all(self):
            return []

    class _Session:
        async def execute(self, statement, params=None):
            return _Result()

    census = await rail.repair(_Session())
    assert "pm-ungraded-loss-restore" in census["restore_command"]
    assert census["backup_table"] == rail.BAK_TABLE


@pytest.mark.asyncio
async def test_an_underfull_page_reports_the_scan_exhausted():
    """A withdrawn row leaves its own bound, so a remaining count is fiction."""
    class _Result:
        def all(self):
            return [_row()]

    class _Session:
        async def execute(self, statement, params=None):
            return _Result()

    census = await rail.repair(_Session(), limit=10)
    assert census["scan_exhausted"] is True
    assert census["next_after_id"] == 1


@pytest.mark.asyncio
async def test_apply_rolls_back_when_the_backup_does_not_cover_the_plan():
    """The D51 refusal, exercised — not merely present in the source.

    A partial backup is the one state in which this rail must not write: the
    rows it cannot restore are precisely the rows it is about to change.
    """
    calls: list[str] = []

    class _Result:
        def __init__(self, rows=(), value=None, rowcount=0):
            self._rows = list(rows)
            self._value = value
            self.rowcount = rowcount

        def all(self):
            return self._rows

        def scalar_one(self):
            return self._value

    class _Session:
        async def execute(self, statement, params=None):
            sql = str(statement)
            calls.append(sql)
            if "WHERE NOT EXISTS (SELECT 1 FROM bak" in sql:
                # Seven in-scope rows have no backup row.
                return _Result(value=7)
            if sql.lstrip().startswith("UPDATE futures_outcomes"):
                return _Result(rows=[(1,)], rowcount=999)
            if sql.lstrip().startswith("SELECT fo.id AS outcome_id"):
                return _Result(rows=[_row()])
            return _Result()

        async def commit(self):
            calls.append("COMMIT")

        async def rollback(self):
            calls.append("ROLLBACK")

    census = await rail.repair(_Session(), apply=True)

    assert census["terminal"] == "refused_backup_incomplete"
    assert census["changed"] == 0
    assert census["backup_missing"] == 7
    assert "ROLLBACK" in calls
    assert "COMMIT" not in calls
    assert not any(c.lstrip().startswith("UPDATE futures_outcomes") for c in calls), (
        "the write ran despite an incomplete backup"
    )
    # The refusal must also come BEFORE the lock — an admin request that takes
    # `FOR UPDATE` on a market it has already decided not to write is holding
    # rows against every grader for nothing.
    assert not any("FOR UPDATE" in c for c in calls)


@pytest.mark.asyncio
async def test_restore_refuses_by_name_when_there_is_no_backup_table():
    """An empty 200 is not an absence — it is a response shape (gotcha #53).

    "0 rows restored" and "there is nothing here to restore from" read
    identically to an operator who is trying to undo a data repair, which is the
    worst possible moment for that ambiguity.
    """

    class _Result:
        def scalar_one(self):
            return False

    class _Session:
        async def execute(self, statement, params=None):
            return _Result()

    census = await rail.restore(_Session(), apply=True)

    assert census["terminal"] == "refused_no_backup"
    assert census["restored"] == 0
    assert census["backup_table"] == rail.BAK_TABLE


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def _catalog_names() -> set[str]:
    import app.routes.admin_repairs as mod

    doc = mod.__doc__ or ""
    start = doc.index("name ∈ {")
    end = doc.index("}", start)
    block = doc[start:end]
    return {part.strip() for part in block.split("{", 1)[1].split("|")}


def test_both_names_are_registered_and_the_catalog_did_not_drift():
    import app.routes.admin_repairs as mod

    assert mod._REPAIRS["pm-ungraded-loss"] == (
        "app.tasks.repair_pm_ungraded_loss",
        "repair",
    )
    assert mod._REPAIRS["pm-ungraded-loss-restore"] == (
        "app.tasks.repair_pm_ungraded_loss",
        "restore",
    )

    catalog = _catalog_names()
    missing = sorted(set(mod._REPAIRS) - catalog)
    assert not missing, f"{missing} registered but missing from the catalog block"


def test_the_dispatcher_passes_the_paging_bounds_this_rail_declares():
    """`limit` and `after_id` are useless unless the dispatcher forwards them.

    Read as a module attribute rather than imported directly: the route
    decorator returns the function unchanged today, but a future decorator that
    wrapped it would make a direct import test the wrapper's signature instead
    of the handler's.
    """
    import app.routes.admin_repairs as mod

    names = set(inspect.signature(mod.run_repair).parameters)
    assert {"limit", "after_id"} <= names

    rail_params = set(inspect.signature(rail.repair).parameters)
    assert {"limit", "after_id", "apply"} <= rail_params
