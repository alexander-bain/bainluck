"""CAL-P1081 (#938) — the parts of the golf round closing-line repair that need no database.

The write itself is guarded by
``tests/integration/test_repair_golf_round_closing_line_1081_real_postgres.py``,
which only runs where CI provides a server. **These run everywhere**, and they
cover the three things that rot without one:

1. **the rail must not become a second pricing rule.** The whole safety
   argument is that every decision it makes is ``backfill_winners`` Part A2's
   decision. The realistic decay is somebody adding "just one" threshold here —
   a floor, a cap, a band — after which the repair and the pipeline quietly
   disagree about what a closing line is and nothing notices.
2. **the bound must stay anchored.** The published ``golfround`` dimension tests
   a bare ``R[0-9]`` anywhere in the ticker's first segment, which would also
   match the ``R2`` inside a year. The two agree on production's 286 markets
   TODAY; they are not the same predicate, and the anchored one is the one that
   is allowed to select a row for a write.
3. **the restore line must be runnable SQL.** ``repair_kalshi_senate_category``
   shipped a version that interpolated the before-value *map* where a value
   belongs. A D51 grant assumes a restore that pastes and runs.
"""

from __future__ import annotations

import ast
import inspect
import re

import pytest

from app.tasks import repair_golf_round_closing_line as rail


def _parsed() -> ast.Module:
    """The module's AST with every docstring removed.

    Docstrings are excluded because this file's whole subject is discussed in
    prose there — ``0.99``, ``0.4269`` and ``0.1524`` all appear in the module
    docstring by necessity, so a naive substring scan over raw source fails on
    its own explanation. ``ast`` rather than a regex for the reason the sibling
    rail records: a regex that strips ``#`` to end-of-line also eats a ``#``
    inside a string literal.
    """
    source = inspect.getsource(rail)
    assert source.strip(), "getsource returned nothing — the scan would be vacuous"

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
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
        and not isinstance(n.value, bool)
    ]


def test_the_rail_holds_no_price_rule_of_its_own():
    """No probability constant may appear in the code — in SQL or in Python.

    A price rule needs a number to compare against. Part A2 owns the only ones
    this repair is entitled to (``probability > 0 AND probability < 1``, and the
    ``LIMIT 1`` that picks the last snapshot), and those are the integer bounds
    of the unit interval, not a policy. Anything with a decimal point is a
    threshold somebody chose, and choosing one here is the failure this guard
    exists for.
    """
    decimals_in_sql = sorted(
        {m for s in _code_strings() for m in re.findall(r"\d+\.\d+", s)}
    )
    assert not decimals_in_sql, (
        f"{decimals_in_sql} appear as decimal literals inside this rail's SQL. "
        "Every pricing decision here must be Part A2's; a threshold of its own "
        "is a second closing-line rule that will drift from the pipeline."
    )

    fractional = sorted({n for n in _code_numbers() if n != int(n)})
    assert not fractional, (
        f"{fractional} appear as float literals in the rail's Python. Same rule: "
        "this module transcribes a snapshot, it does not judge one."
    )


def _assigned_columns(sql: str) -> set[str]:
    """Every column name on the LEFT of an ``=`` inside a ``SET`` clause.

    🔴 THE FIRST VERSION OF THIS SCAN LOOKED FOR THE LITERAL ``"set <column>"``
    AND A MUTATION WALKED STRAIGHT THROUGH IT. ``SET calibration_probability =
    x, opening_probability = x`` contains no ``set opening_probability``
    substring, so the guard passed while the rail wrote a second column — and
    ``opening_probability`` is the one column whose loss is unrecoverable here
    (it is the curve's COALESCE fallback and the restore's own source of truth).
    A prefix check is not a scan of the SET clause; this parses it.
    """
    columns: set[str] = set()
    for match in re.finditer(
        r"\bSET\b(.*?)(?=\bFROM\b|\bWHERE\b|$)", sql, re.IGNORECASE | re.DOTALL
    ):
        for assignment in match.group(1).split(","):
            name, sep, _ = assignment.partition("=")
            if sep:
                columns.add(name.strip().split(".")[-1].lower())
    return columns


def test_the_rail_writes_only_the_calibration_price():
    """The blast radius is one column, and the scan proves it per assignment.

    ``is_winner`` and ``resolution_source`` are fragile by gotcha #21 and by
    #994's symmetric-exclusion doctrine; ``opening_probability`` is the curve's
    COALESCE fallback AND what the D51 restore reads back; ``last_updated`` is a
    poller touch-stamp another surface reads as liveness (#2024), so writing it
    would forge an observation.
    """
    assigned = _assigned_columns(" ".join(_code_strings()))

    assert assigned == {"calibration_probability"}, (
        f"this rail assigns {sorted(assigned)}. It is licensed to move "
        "`calibration_probability` and nothing else."
    )


def test_the_set_clause_scan_can_see_a_second_assignment():
    """The guard above is only worth its line if it catches the real mutant.

    Runs the scan over the exact multi-column SET a widening would produce. A
    scan that cannot see this is the scan this file shipped first.
    """
    widened = (
        "UPDATE futures_outcomes fo SET calibration_probability = t.p, "
        "opening_probability = t.p FROM targets t WHERE fo.id = t.outcome_id"
    )
    assert _assigned_columns(widened) == {
        "calibration_probability",
        "opening_probability",
    }


def test_the_closing_selector_is_strictly_before_commence():
    """Ruling 103: a price captured after the answer is not a price.

    The one clause in the borrowed selector that must never be relaxed to
    ``<=`` or dropped. A snapshot taken once the round is under way prices a
    partly-known result, and publishing it as a forecast is the defect the
    calibration curve exists to avoid.
    """
    sql = " ".join(_code_strings())
    assert "fos.captured_at < b.commence_time" in sql, (
        "the closing-line selector no longer bounds itself strictly before "
        "commence_time (ruling 103)"
    )
    assert "fos.captured_at <= b.commence_time" not in sql


@pytest.mark.parametrize(
    "segment,expected",
    [
        # The real production series, read off production 2026-09-10.
        ("KXDPWORLDTOURR1LEAD", True),
        ("KXCHAMPTOURR1LEAD", True),
        ("KXLIVR3LEAD", True),
        ("KXLPGAR1LEAD", True),
        ("KXPGAR1TOP5", True),
        ("KXPGAR2TOP10", True),
        ("KXPGAR1TOP20", True),
        # Tournament scope — measured at 2.12/2.42 ECE and explicitly OUT.
        ("KXPGATOURWINNER", False),
        ("KXUSOPENWINNER", False),
        ("KXMASTERSTOP10", False),
    ],
)
def test_the_anchored_pattern_selects_round_scope_only(segment, expected):
    assert bool(re.search(rail.ROUND_SERIES_PATTERN, segment)) is expected


def test_the_anchored_pattern_cannot_match_a_year():
    """The reason the rail does not reuse the published dimension's regex.

    ``golfround`` asks whether ``R[0-9]`` appears anywhere in the segment, which
    is fine for a diagnosis and is not fine for a predicate that selects rows
    for a WRITE: a season-bearing ticker satisfies it by accident. Both forms
    select the same 286 markets on production today — that equality is a
    measurement (``artifacts-calibration-1081``), and this test is what stops it
    being assumed for a ticker that does not exist yet.
    """
    year_bearing = "KXPGATOUR2026"
    assert re.search(rail.PUBLISHED_DIMENSION_PATTERN, year_bearing), (
        "premise of this test: the published dimension's looser form DOES match "
        "a year-bearing ticker"
    )
    assert not re.search(rail.ROUND_SERIES_PATTERN, year_bearing), (
        "the anchored bound must refuse a ticker whose only `R<digit>` is a season"
    )


def test_restore_sql_is_one_runnable_statement():
    """D51's grant is for a repair that ships a ONE-command restore.

    The 116-statement / 31 KB per-before-value form the first draft emitted was
    runnable and was not that. The single statement is exact for the same reason
    the gate exists: a planned row is one where ``calibration_probability =
    opening_probability``, so restoring from the opening column restores each
    row's own stored value.
    """
    planned = [
        {"outcome_id": 3, "before": 0.99, "closing": 0.07},
        {"outcome_id": 1, "before": 0.99, "closing": 0.38},
        {"outcome_id": 2, "before": 0.95, "closing": 0.22},
    ]
    sql = rail.restore_sql(planned)

    assert sql.count(";") == 1, "the undo must be one command"
    assert sql == (
        "UPDATE futures_outcomes SET calibration_probability = opening_probability "
        "WHERE id IN (1, 2, 3);"
    )
    # The failure the sibling rail shipped: a dict rendered where a value goes.
    assert "{" not in sql and "}" not in sql


def test_restore_sql_is_empty_when_nothing_is_planned():
    assert rail.restore_sql([]) == ""
