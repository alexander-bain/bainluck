"""#4745 (CAL-P1086) — the parts of the empty-book withdrawal that need no database.

The write itself is guarded by
``tests/integration/test_repair_kalshi_empty_book_openings_1086_real_postgres.py``,
which runs where CI provides a server. **These run everywhere**, and they cover
the five things that rot without one:

1. **the blast radius.** This rail writes three columns and can NULL two of
   them. ``is_winner``/``resolution_source`` are truth (gotcha #21) and
   ``last_updated`` is a poller touch-stamp another surface reads as liveness
   (#2024); a widening SET clause is the realistic decay, and the sibling rail
   proved a prefix-matching scan walks straight through one.
2. **the predicate stays the SHIPPED one.** The whole safety argument is that
   this rail invents no price policy: it reuses
   ``lone_ask_on_empty_book_sql``, which is the SQL dialect of the guard
   ``_kalshi_yes_probability`` has enforced on the write since 2026-07-13. A
   restatement here — even a correct one — is the drift the shared module
   exists to prevent.
3. **the provenance clause.** ``fo.opening_probability = bad.probability`` is
   what makes this a repair rather than an opinion: the only number it
   overwrites is one it can prove was copied from the discredited book. It is
   also what makes the result a FIXED POINT — a repaired row no longer
   satisfies its own bound.
4. **Phase 0c must remain executable by the gate.** The "no re-promotion" claim
   is a claim about the shipped statement, so ``backfill_winners`` has to keep
   exposing it as a constant rather than inlining it back into the task body,
   or the integration gate silently starts asserting agreement with a copy.
5. **the D51 refusals.** An apply whose backup does not cover every planned id
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

from app.tasks import repair_kalshi_empty_book_openings as rail
from app.utils.kalshi_empty_book import (
    ASK_ONLY_TRUSTED_MAX,
    lone_ask_on_empty_book_sql,
)


# ---------------------------------------------------------------------------
# source scanning
# ---------------------------------------------------------------------------


def _parsed() -> ast.Module:
    """The module's AST with every docstring removed.

    Docstrings are excluded because this file's whole subject is discussed in
    prose there — ``0.98``, ``0.904`` and ``0.9805`` all appear in the module
    docstring by necessity, so a naive substring scan over raw source fails on
    its own explanation.

    🔴 ``inspect.getsource`` IS NOT SAFE ON EVERY ``app.tasks`` MODULE, and
    CAL-P1085 lost an hour to it: ``from app.tasks import backfill_winners``
    returns the celery TASK that shadows the module name, so ``getsource``
    yields twelve lines with no SQL and the scan becomes vacuous. It is safe
    here — nothing shadows this name — and the emptiness assertion below is
    what proves that rather than assumes it.
    """
    source = inspect.getsource(rail)
    assert len(source) > 5000, (
        "getsource returned a stub — a task or a shim is shadowing the module "
        "name and every scan in this file would be vacuous (CAL-P1085)"
    )

    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
    return tree


def _code_strings() -> list[str]:
    return [
        n.value
        for n in ast.walk(_parsed())
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _code_numbers() -> list[float]:
    return [
        float(n.value)
        for n in ast.walk(_parsed())
        if isinstance(n, ast.Constant)
        and isinstance(n.value, (int, float))
        and not isinstance(n.value, bool)
    ]


def _sql() -> str:
    """Every SQL statement this rail actually executes, as it will be sent.

    Assembled from the module's RUNTIME constants, not from the AST. The bound
    is an f-string that interpolates the shipped predicate, and an f-string is a
    ``JoinedStr`` — its interpolated text exists nowhere in the source. A
    content scan over the parsed source would therefore report the guard
    missing from a rail that carries it, and would report it present in a rail
    that had hard-coded a copy. The AST scan above stays for the LITERAL checks,
    where "what somebody typed" is the question.
    """
    return " ".join(
        getattr(rail, name)
        for name in dir(rail)
        if name.startswith("_") and isinstance(getattr(rail, name), str)
        and ("SELECT" in getattr(rail, name) or "UPDATE" in getattr(rail, name))
    )


def _assigned_columns(sql: str) -> set[str]:
    """Every column name on the LEFT of an ``=`` inside a ``SET`` clause.

    Parsed per assignment, not prefix-matched. ``SET a = x, b = x`` contains no
    ``set b`` substring, so a prefix check passes while the rail writes a second
    column — the exact mutant that walked through the sibling rail's first
    version of this scan.

    ``CASE WHEN … THEN … ELSE … END`` inside a value would confuse a naive comma
    split, so the terminator set includes ``FROM``/``WHERE`` and the positive
    control below is written on this rail's real, CASE-bearing statement.
    """
    columns: set[str] = set()
    for match in re.finditer(
        r"\bSET\b(.*?)(?=\bFROM\b|\bWHERE\b|$)", sql, re.IGNORECASE | re.DOTALL
    ):
        depth = 0
        current = ""
        parts = []
        for char in match.group(1):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char == "," and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += char
        parts.append(current)
        for assignment in parts:
            name, sep, _ = assignment.partition("=")
            if sep:
                columns.add(name.strip().split(".")[-1].lower())
    return columns


def test_the_rail_writes_only_the_three_price_columns():
    """The blast radius, proved per assignment rather than by prefix.

    ``opening_probability`` and ``calibration_probability`` are the curve's
    COALESCE pair and are what this ship is about. ``opening_source`` is cleared
    with the value it labels — leaving ``'first_snapshot'`` on a row that no
    longer has an opening would be a provenance claim about a number that is
    gone.

    Everything else is out of bounds: ``is_winner`` and ``resolution_source``
    are truth and are never re-graded by a price repair (gotcha #21), and
    ``last_updated`` is read elsewhere as evidence that a poll ran (#2024), so
    writing it would forge an observation.
    """
    assigned = _assigned_columns(_sql())

    assert assigned == {
        "opening_probability",
        "opening_source",
        "calibration_probability",
    }, f"this rail assigns {sorted(assigned)}"


def test_the_set_clause_scan_can_see_a_second_assignment():
    """Positive control: the scan is only worth its line if it catches a mutant.

    Run over a widening of this rail's OWN statement — CASE expressions,
    parenthesised commas and all — because a scan validated on a toy string is
    not validated on the thing it guards.
    """
    widened = rail._APPLY_SQL.replace(
        "    FROM scope s", "        is_winner = true\n    FROM scope s"
    ).replace(
        "        END\n", "        END,\n"
    )
    assert "is_winner" in _assigned_columns(widened), (
        "the scan cannot see a second assignment added to the real statement"
    )


def test_the_rail_holds_no_price_rule_of_its_own():
    """No probability constant may appear here — in SQL or in Python.

    A price rule needs a number to compare against, and this rail is entitled to
    exactly one: ``ASK_ONLY_TRUSTED_MAX``, which belongs to
    ``app.utils.kalshi_empty_book`` and arrives inside the interpolated
    predicate rather than being typed here. Anything else with a decimal point
    is a threshold somebody chose, and choosing one here forks the policy from
    the poller that has enforced it since 2026-07-13.

    The interpolated guard legitimately contains ``0.5``, so the scan is run
    over the source with that exact rendered text removed — subtracting the
    shipped predicate, not whitelisting a number.
    """
    guard_text = " ".join(
        lone_ask_on_empty_book_sql(alias) for alias in ("fos", "bad")
    )
    sql_without_the_shipped_guard = _sql()
    for alias in ("fos", "bad"):
        sql_without_the_shipped_guard = sql_without_the_shipped_guard.replace(
            lone_ask_on_empty_book_sql(alias), " "
        )

    assert str(ASK_ONLY_TRUSTED_MAX) in guard_text, (
        "premise of this test: the shipped predicate is where the threshold lives"
    )

    decimals = sorted(set(re.findall(r"\d+\.\d+", sql_without_the_shipped_guard)))
    assert not decimals, (
        f"{decimals} appear as decimal literals in this rail's SQL outside the "
        "shipped predicate — a second empty-book policy"
    )

    fractional = sorted({n for n in _code_numbers() if n != int(n)})
    assert not fractional, (
        f"{fractional} appear as float literals in the rail's Python. Same rule: "
        "this module moves a stored number, it does not judge one."
    )


def test_the_bound_uses_the_shipped_predicate_verbatim():
    """Both laterals must carry the SHIPPED expression, character for character."""
    sql = _sql()
    for alias in ("fos", "bad"):
        assert lone_ask_on_empty_book_sql(alias) in sql, (
            f"the bound no longer carries the shipped predicate for `{alias}`"
        )


def test_the_predicate_is_CALLED_and_not_transcribed():
    """Text equality cannot tell an import from a hand-copy, so read the AST.

    🔴 THE MUTATION BATTERY FOUND THIS. ``M4 the shipped predicate is restated
    instead of imported`` replaced
    ``lone_ask_on_empty_book_sql("bad")`` with a string literal spelling out the
    same four clauses — and the test above stayed GREEN, because a faithful copy
    IS character-for-character identical to the thing it copies. The guard was
    asserting the only property a transcription cannot fail.

    What the shared module actually buys is that ``ASK_ONLY_TRUSTED_MAX`` has
    ONE definition: change it and the poller's write rule, Phase 0c's promotion
    rule and this withdrawal move together. A transcribed copy agrees today and
    silently stops agreeing on the day the constant moves — which is the day
    nobody is looking at this file. So the property to assert is the CALL.
    """
    calls: dict[str, str] = {}
    for node in ast.walk(_parsed()):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id.startswith("_GUARD_ON_")):
                continue
            value = node.value
            assert isinstance(value, ast.Call), (
                f"{target.id} is assigned a {type(value).__name__}, not a call. "
                "A transcribed predicate agrees with the shipped one until "
                "ASK_ONLY_TRUSTED_MAX moves, and then only this copy is wrong."
            )
            assert isinstance(value.func, ast.Name), f"{target.id} calls something odd"
            calls[target.id] = value.func.id

    assert calls, "no `_GUARD_ON_*` assignment found — this scan has nothing to check"
    assert set(calls.values()) == {"lone_ask_on_empty_book_sql"}, (
        f"the bound's predicates come from {sorted(set(calls.values()))}"
    )


def test_the_replacement_lateral_is_the_negation_and_the_earliest_wins():
    """The replacement is Phase 0c's own re-derivation, not a new selector.

    ``NOT <guard>`` with ``captured_at ASC LIMIT 1`` is exactly what the live
    Phase 0c does for a NULL opening. If this drifted to ``DESC`` the rail would
    be writing a closing line into an opening column and silently disagreeing
    with the phase whose fixed point it claims to be.
    """
    sql = _sql()
    assert f"NOT {lone_ask_on_empty_book_sql('fos')}" in sql
    assert "ORDER BY fos.captured_at ASC" in sql
    assert "ORDER BY fos.captured_at DESC" not in sql, (
        "the replacement selector must take the EARLIEST honest snapshot; DESC "
        "would write a closing line into `opening_probability`"
    )


def test_the_provenance_clause_is_in_the_bound():
    """The clause that makes this a repair and not an opinion.

    Without ``fo.opening_probability = bad.probability`` the rail would rewrite
    any row that merely HAS a bad earliest snapshot, including rows something
    else legitimately priced. With it, the only number overwritten is one that
    can be shown to have been copied from the discredited book.

    It is also the fixed-point clause: after the write the stored opening is
    either the honest value or NULL, so the row no longer satisfies its own
    bound and cannot be repaired twice.
    """
    sql = _sql()
    assert "fo.opening_probability = bad.probability" in sql
    assert "fo.opening_probability IS NOT NULL" in sql
    assert "fo.opening_source = 'first_snapshot'" in sql
    assert "fm.status = 'resolved'" in sql


# ---------------------------------------------------------------------------
# the decision, on its three arms
# ---------------------------------------------------------------------------


def _row(*, honest, bad=0.98, before_opening=0.98, before_calibration=None):
    return SimpleNamespace(
        outcome_id=1,
        honest_value=honest,
        bad_value=bad,
        before_opening=before_opening,
        before_calibration=before_calibration,
        before_opening_source="first_snapshot",
    )


def test_a_leg_with_a_later_honest_price_is_corrected():
    action, new_opening, refusal = rail.classify(_row(honest=0.21))
    assert (action, new_opening, refusal) == ("correct", 0.21, None)


def test_a_leg_that_never_had_a_price_is_withdrawn():
    action, new_opening, refusal = rail.classify(_row(honest=None))
    assert (action, new_opening, refusal) == ("withdraw", None, None)


def test_a_replacement_equal_to_the_stored_value_is_refused_by_name():
    """9 of 1,756 sampled production legs are this, so it is a real arm.

    A later snapshot carried a real book at the same number. Writing it changes
    nothing; counting it as repaired would overstate the ship by exactly the
    rows that did not move.
    """
    action, new_opening, refusal = rail.classify(_row(honest=0.98, bad=0.98))
    assert action == "refused"
    assert refusal == rail.REASON_REPLACEMENT_EQUALS_STORED


@pytest.mark.parametrize(
    "before_calibration, visible",
    [
        # arm a — no calibration price, so the curve reads the bad opening
        (None, True),
        # arm b — calibration is a verbatim copy of the bad opening
        (0.98, True),
        # arm c — calibration is independent; the reader never sees the opening
        (0.34, False),
    ],
)
def test_reader_visibility_follows_the_coalesce_not_the_column(
    before_calibration, visible
):
    """``COALESCE(calibration_probability, opening_probability)`` decides the ship.

    A coalesce, not an exclusion (gotcha #144 / ruling 103). The directive that
    staged this queue counted all three arms as "published at 0.94"; measured,
    arm c publishes 0.392 and is 52% of the cohort. The rail repairs arm c too —
    the stored number is just as false — but the ship counts only what a reader
    can see, and this is where that distinction is computed.
    """
    record = rail._record(_row(honest=None, before_calibration=before_calibration))
    assert record["reader_visible"] is visible
    assert record["published_now"] == (
        0.98 if before_calibration is None else before_calibration
    )


# ---------------------------------------------------------------------------
# D51
# ---------------------------------------------------------------------------


def test_the_backup_never_overwrites_an_existing_row():
    """A leg may be repaired, restored and repaired again.

    The FIRST backup is the one that predates the rail. Re-copying after an
    apply would back up the repaired value and turn the undo into a no-op —
    silently, and only discoverably by needing it.
    """
    assert "ON CONFLICT (outcome_id) DO NOTHING" in rail._BAK_COPY


def test_the_backup_inherits_the_column_types_it_mirrors():
    """`CREATE TABLE AS … WHERE false`, never a hand-typed DDL.

    ``opening_probability`` is ``NUMERIC(7,6)``. A spelled-out backup schema is
    a second declaration of that type, and the day the column widens the backup
    silently truncates every value it is supposed to preserve.
    """
    assert "CREATE TABLE IF NOT EXISTS" in rail._BAK_CREATE
    assert "WHERE false" in rail._BAK_CREATE
    assert "NUMERIC" not in rail._BAK_CREATE.upper()


def test_the_backup_gate_counts_uncovered_rows_not_two_totals():
    """Two totals can agree while naming different rows.

    The gate has to be "how many in-scope rows have no backup row", which is
    zero only when the copy covers the population it is about to overwrite.
    """
    assert "NOT EXISTS" in rail._BAK_MISSING
    assert "count(*)" in rail._BAK_MISSING


def test_the_restore_is_one_statement_and_idempotent():
    """D51's grant is for a repair that ships a ONE-command restore.

    ``IS DISTINCT FROM`` is what makes a second run report zero rather than
    re-writing every row: the count then means "rows actually put back", which
    is the only number an operator can act on.
    """
    assert rail._RESTORE_SQL.count(";") == 0
    assert rail._RESTORE_SQL.upper().count("UPDATE ") == 1
    assert rail._RESTORE_SQL.count("IS DISTINCT FROM") == 3

    command = rail.restore_command()
    assert "kalshi-empty-book-openings-restore" in command
    assert "apply=true" in command
    assert command.count("curl") == 1


def test_the_restore_puts_back_all_three_columns():
    """Restoring two of three would leave a row nobody can reason about.

    A withdrawn row has ``opening_probability`` NULL and ``opening_source``
    NULL; restoring only the probability would resurrect a value labelled by
    nothing, and restoring only the source would label a NULL.
    """
    assigned = _assigned_columns(rail._RESTORE_SQL)
    assert assigned == {
        "opening_probability",
        "opening_source",
        "calibration_probability",
    }


@pytest.mark.asyncio
async def test_apply_rolls_back_when_the_backup_does_not_cover_the_plan():
    """The D51 refusal, exercised — not merely present in the source.

    A partial backup is the one state in which this rail must not write: the
    rows it cannot restore are precisely the rows it is about to destroy.
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
            if "NOT EXISTS" in sql:
                # Seven in-scope rows have no backup row.
                return _Result(value=7)
            if sql.lstrip().startswith("UPDATE") or "WITH scope AS" in sql:
                return _Result(rowcount=999)
            if sql.lstrip().startswith("SELECT fo.id AS outcome_id"):
                # One planned row, so the apply path is entered at all.
                return _Result(rows=[_row(honest=None)])
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
    assert not any("WITH scope AS" in c for c in calls), (
        "the write ran despite an incomplete backup"
    )


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
# the ordering this rail depends on
# ---------------------------------------------------------------------------


def _backfill_winners_module():
    """The MODULE, not the celery task that shadows its name.

    ``from app.tasks import backfill_winners`` returns the task — the package
    attribute is rebound by the ``@shared_task`` decoration — so the constant
    this file is about is simply absent from it, and `getsource` on it yields
    twelve lines with no SQL. CAL-P1085 shipped a source-scan guard that could
    never fail for exactly this reason. ``sys.modules`` holds the real module.
    """
    import importlib
    import sys

    importlib.import_module("app.tasks.backfill_winners")
    module = sys.modules["app.tasks.backfill_winners"]
    assert hasattr(module, "PHASE_0C_REPAIR_SQL"), (
        "sys.modules is handing back the shadowing task, not the module"
    )
    return module


def test_phase_0c_is_exposed_as_a_constant_the_gate_can_execute():
    """The "no re-promotion" claim must be testable against the SHIPPED statement.

    Phase 0c-repair used to be 24 lines of f-string inside a 700-line task
    function, unreachable by any test that was not the task. The integration
    gate runs THIS constant against a real Postgres immediately after the
    repair; if somebody inlines it back, that gate starts asserting agreement
    with its own copy and the claim becomes unfalsifiable.
    """
    sql = _backfill_winners_module().PHASE_0C_REPAIR_SQL
    assert "fo2.opening_probability IS NULL" in sql, (
        "Phase 0c's key is what makes a corrected (non-null) row untouchable"
    )
    assert f"NOT {lone_ask_on_empty_book_sql('fos')}" in sql, (
        "Phase 0c lost the guard that makes a withdrawn row stay withdrawn"
    )
    assert "CROSS JOIN LATERAL" in sql, (
        "a LEFT JOIN here would promote NULL onto a withdrawn row instead of "
        "dropping the outcome"
    )
    assert "opening_source = 'first_snapshot'" in sql


def test_the_task_body_no_longer_carries_its_own_copy_of_phase_0c():
    """Hoisting is only worth it if the task actually uses the constant.

    A hoist that leaves the original in place ships two statements that agree
    today, and the gate proves nothing about the one that runs.
    """
    with open(_backfill_winners_module().__file__) as handle:
        body = handle.read()

    assert body.count("WITH first_snaps AS (") == 1, (
        "Phase 0c's statement appears more than once — the task and the "
        "constant have been allowed to drift apart"
    )
    assert "text(PHASE_0C_REPAIR_SQL)" in body, (
        "the task no longer executes the hoisted constant"
    )


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

    assert mod._REPAIRS["kalshi-empty-book-openings"] == (
        "app.tasks.repair_kalshi_empty_book_openings",
        "repair",
    )
    assert mod._REPAIRS["kalshi-empty-book-openings-restore"] == (
        "app.tasks.repair_kalshi_empty_book_openings",
        "restore",
    )

    catalog = _catalog_names()
    missing = sorted(set(mod._REPAIRS) - catalog)
    assert not missing, f"{missing} registered but missing from the catalog block"


def test_the_dispatcher_passes_the_paging_bounds_this_rail_declares():
    """A keyset cursor the dispatcher drops is a rail that always walks page one.

    The dispatcher forwards only parameters a repair's signature NAMES, so the
    contract is between this signature and that allowlist — and a rail whose
    ``after_id`` is silently discarded would repair its first page forever while
    reporting progress.
    """
    import inspect as _inspect

    import app.routes.admin_repairs as mod

    declared = set(_inspect.signature(rail.repair).parameters)
    assert {"limit", "after_id"} <= declared

    dispatcher = set(_inspect.signature(mod.run_repair).parameters)
    assert {"limit", "after_id", "apply"} <= dispatcher


def test_neither_name_is_wired_to_a_beat():
    """This is a terminating drain, not maintenance.

    Scheduling it would re-run a bounded historical correction forever, and the
    restore name would be worse: a beat that undoes the repair.
    """
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    wired = [
        name
        for name, entry in schedule.items()
        if "empty_book_openings" in str(entry.get("task", ""))
    ]
    assert not wired, f"{wired} scheduled a one-off repair rail"
