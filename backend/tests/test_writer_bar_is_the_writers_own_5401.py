"""#5401 — the curve may not publish an opening the Kalshi writer would refuse.

The ship is one predicate: an outcome whose snapshots never met
``app/tasks/kalshi.py``'s own ``has_real_trading`` condition leaves the published
calibration population. Everything that can go wrong with a predicate like that
is a separate arm here:

* **it must BE the writer's rule** — the bar is a literal in two files, so an AST
  read of the writer pins them together rather than a comment asking nicely;
* **it must RUN** — the SQL is executed against SQLite on a book matrix and
  compared row-for-row with the Python twin, because a source scan proves the
  text is present and nothing about what it does;
* **it must be WIRED** — the flag is asserted inside the generated population
  SQL at every clause its siblings appear in, since a flag computed and never
  filtered on is a column, not an exclusion;
* **it must be COUNTED** — a new ``deduped`` filter with no coverage rung lands
  silently in the ``representative_not_selected`` catch-all and restates an
  established number as a regression.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from app.tasks.precompute_calibration import (
    KALSHI_WRITER_BAR_MET,
    KALSHI_WRITER_MAX_SPREAD,
    _COVERAGE_RUNG_PREDICATES,
    _calibration_population_ctes,
    kalshi_writer_bar_met_sql,
    snapshot_meets_kalshi_writer_bar,
)
from app.utils.calibration_coverage_bridge import EXCLUSION_RUNGS, RUNG_KEYS

WRITER = Path(__file__).resolve().parents[1] / "app" / "tasks" / "kalshi.py"

RUNG = "opening_below_writer_bar"

#: (yes_bid, yes_ask, the writer would store an opening from this snapshot).
#: The boundary rows are the point: a spread of EXACTLY the maximum is refused
#: (the writer's comparison is ``<``, not ``<=``), and a missing ask is not a
#: zero ask.
BOOK_MATRIX: tuple[tuple[float | None, float | None, bool], ...] = (
    (0.40, 0.60, True),        # tight two-sided book — the ordinary accept
    (0.01, 0.02, True),        # a real book at a tiny price is still a book
    (0.40, 0.90, False),       # spread exactly 0.50 -> refused, `<` not `<=`
    (0.40, 0.8999, True),      # a hair inside the bar -> accepted
    (0.40, 0.91, False),       # a hair outside -> refused
    (0.0, 0.10, False),        # no bid: a lone ask is not a discovered price
    (None, 0.10, False),       # no bid recorded at all
    (0.40, None, False),       # no ask recorded: NOT the tightest spread
    (None, None, False),       # no book whatsoever
    (0.95, 0.96, True),        # near-certainty WITH a book stays published
    # A CROSSED book (ask below bid) is incoherent, and the writer stores an
    # opening from it anyway: its spread is negative, so it passes `< 0.50`.
    # Mirrored here on purpose. This rule's whole claim is "the bar is the
    # writer's own"; second-guessing the writer on one shape would make it a
    # new threshold of our own, which is the thing #5401 rejected. If crossed
    # books turn out to matter they are their own ship, with their own count.
    (0.40, 0.0, True),
)


class TestTheBarIsTheWritersOwn:
    """The two literals are in two files; this is what keeps them one rule."""

    def _writer_condition(self) -> ast.BoolOp:
        """The ``has_real_trading`` assignment in the Kalshi poller, as AST.

        Read from source rather than imported: the value is built per-market
        inside the poll loop, so there is no symbol to import, and a regex over
        the file would match the comment above it as happily as the code.
        """
        tree = ast.parse(WRITER.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "has_real_trading"
                    for t in node.targets
                )
            ):
                assert isinstance(node.value, ast.BoolOp), (
                    "has_real_trading stopped being a boolean expression; "
                    "re-derive the curve-side bar against whatever replaced it"
                )
                return node.value
        pytest.fail(
            "no `has_real_trading = ...` assignment in app/tasks/kalshi.py — "
            "the writer's opening bar moved, so KALSHI_WRITER_BAR_MET is now "
            "measuring a rule nobody writes"
        )

    def test_the_writer_still_gates_on_bid_ask_and_a_spread(self) -> None:
        cond = self._writer_condition()
        src = ast.unparse(cond)
        assert "yes_bid" in src and "yes_ask" in src

    def test_the_curve_uses_the_writers_own_spread_literal(self) -> None:
        """The one number that must not drift between the two files."""
        cond = self._writer_condition()
        literals = {
            node.value
            for node in ast.walk(cond)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert KALSHI_WRITER_MAX_SPREAD in literals, (
            f"the Kalshi writer's spread literals are {literals}, and the curve "
            f"is excluding on {KALSHI_WRITER_MAX_SPREAD}. A writer that widens "
            "its bar without widening this one makes the curve refuse rows the "
            "writer accepts."
        )

    def test_the_writer_refuses_a_spread_equal_to_the_bar(self) -> None:
        """`<` and `<=` differ by a whole cohort at exactly 0.50."""
        cond = self._writer_condition()
        ops = [
            type(op).__name__
            for node in ast.walk(cond)
            if isinstance(node, ast.Compare)
            for op in node.ops
        ]
        assert "LtE" not in ops, (
            "the writer now accepts a spread EQUAL to its maximum; "
            "snapshot_meets_kalshi_writer_bar still uses a strict `<`"
        )


class TestThePythonTwin:
    @pytest.mark.parametrize("yes_bid,yes_ask,expected", BOOK_MATRIX)
    def test_the_matrix(
        self, yes_bid: float | None, yes_ask: float | None, expected: bool
    ) -> None:
        assert snapshot_meets_kalshi_writer_bar(yes_bid, yes_ask) is expected

    def test_a_missing_ask_is_not_a_zero_ask(self) -> None:
        """The coalescing bug this predicate's sibling can afford and it cannot.

        ``outcome_is_calibration_liquid`` may write ``(ever_yes_bid or 0) > 0``
        because it only compares against zero. Doing the same here would turn a
        bookless row into ``0 - 0.4 = -0.4``, the tightest spread imaginable,
        and admit the exact cohort #5401 removes.
        """
        assert snapshot_meets_kalshi_writer_bar(0.40, None) is False
        # And the coalescing form really would have admitted it:
        assert ((0.40 or 0) - (None or 0)) < KALSHI_WRITER_MAX_SPREAD


class TestTheSqlIsTheSameRule:
    """Executed, not read. A source scan cannot tell a live clause from a dead one."""

    def _rows_admitted_by_sql(
        self, books: list[tuple[int, float | None, float | None]]
    ) -> set[int]:
        con = sqlite3.connect(":memory:")
        con.execute(
            "CREATE TABLE outcomes (id INTEGER PRIMARY KEY, source TEXT)"
        )
        con.execute(
            "CREATE TABLE futures_odds_snapshots ("
            "  outcome_id INTEGER, yes_bid REAL, yes_ask REAL)"
        )
        seen: set[int] = set()
        for outcome_id, bid, ask in books:
            if outcome_id not in seen:
                con.execute(
                    "INSERT INTO outcomes (id, source) VALUES (?, 'kalshi')",
                    (outcome_id,),
                )
                seen.add(outcome_id)
            con.execute(
                "INSERT INTO futures_odds_snapshots "
                "(outcome_id, yes_bid, yes_ask) VALUES (?, ?, ?)",
                (outcome_id, bid, ask),
            )
        predicate = kalshi_writer_bar_met_sql(source="o.source", outcome_id="o.id")
        cur = con.execute(
            f"SELECT o.id FROM outcomes o WHERE {predicate}"  # noqa: S608
        )
        return {row[0] for row in cur.fetchall()}

    def test_the_sql_and_the_twin_agree_on_every_book(self) -> None:
        books = [
            (idx, bid, ask) for idx, (bid, ask, _) in enumerate(BOOK_MATRIX)
        ]
        expected = {
            idx for idx, (_, _, ok) in enumerate(BOOK_MATRIX) if ok
        }
        assert self._rows_admitted_by_sql(books) == expected

    def test_one_qualifying_snapshot_in_a_life_of_bad_ones_admits_the_leg(
        self,
    ) -> None:
        """EXISTS, deliberately: the bar is 'ever', matching the writer's chance.

        The writer stores an opening the FIRST time it sees a qualifying book,
        so a leg that ever had one is a leg whose opening it would have stored.
        """
        admitted = self._rows_admitted_by_sql(
            [
                (1, 0.0, 0.99),
                (1, 0.0, 0.98),
                (1, 0.45, 0.55),   # the one good look
                (2, 0.0, 0.99),
                (2, None, None),
            ]
        )
        assert admitted == {1}

    def test_a_leg_with_no_snapshots_at_all_is_below_the_bar(self) -> None:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE outcomes (id INTEGER PRIMARY KEY, source TEXT)")
        con.execute(
            "CREATE TABLE futures_odds_snapshots ("
            "  outcome_id INTEGER, yes_bid REAL, yes_ask REAL)"
        )
        con.execute("INSERT INTO outcomes VALUES (1, 'kalshi')")
        predicate = kalshi_writer_bar_met_sql(source="o.source", outcome_id="o.id")
        cur = con.execute(f"SELECT o.id FROM outcomes o WHERE {predicate}")  # noqa: S608
        assert cur.fetchall() == []

    def test_the_bar_is_kalshi_only(self) -> None:
        """It is transcribed from ONE writer, so it may only judge that writer."""
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE outcomes (id INTEGER PRIMARY KEY, source TEXT)")
        con.execute(
            "CREATE TABLE futures_odds_snapshots ("
            "  outcome_id INTEGER, yes_bid REAL, yes_ask REAL)"
        )
        con.execute("INSERT INTO outcomes VALUES (1, 'polymarket')")
        con.execute("INSERT INTO outcomes VALUES (2, 'kalshi')")
        # Neither has a single snapshot; only the Kalshi row may be refused.
        predicate = kalshi_writer_bar_met_sql(source="o.source", outcome_id="o.id")
        cur = con.execute(f"SELECT o.id FROM outcomes o WHERE {predicate}")  # noqa: S608
        assert {r[0] for r in cur.fetchall()} == {1}


class TestTheFlagIsWiredIntoThePopulation:
    """A computed flag nobody filters on is a column, not an exclusion."""

    def test_the_flag_is_computed_in_the_population_chain(self) -> None:
        sql = _calibration_population_ctes()
        assert "AS is_below_writer_bar" in sql

    def test_the_representative_selection_filters_on_it(self) -> None:
        """`deduped` is the clause that decides what a reader sees."""
        sql = _calibration_population_ctes()
        deduped = sql.split("deduped AS (", 1)
        assert len(deduped) == 2, "the `deduped` CTE was renamed"
        body = deduped[1]
        assert "NOT ro.is_below_writer_bar" in body.split("),", 1)[0]

    def test_field_completeness_counts_it_as_a_published_exclusion(self) -> None:
        """A field that loses a member to it is PARTIAL, not renormalised.

        Both FILTERs — the survivor count and the winner-survived count — or a
        field whose winner is below the bar reads as complete-with-a-winner and
        is normalised over rows that are no longer all there.
        """
        sql = _calibration_population_ctes()
        block = sql.split("field_completeness AS (", 1)[1].split("normalized AS (", 1)[0]
        assert block.count("NOT ro.is_below_writer_bar") == 2

    def test_the_predicate_reaches_the_sql_verbatim(self) -> None:
        """The module constant is what the chain runs, not a lookalike."""
        sql = _calibration_population_ctes()
        assert KALSHI_WRITER_BAR_MET.split("EXISTS", 1)[1][:40] in sql


class TestTheExclusionIsCounted:
    def test_the_rung_exists_and_is_an_exclusion(self) -> None:
        assert RUNG in RUNG_KEYS
        assert RUNG in EXCLUSION_RUNGS

    def test_the_rung_reads_the_flag_this_ship_added(self) -> None:
        predicates = dict(_COVERAGE_RUNG_PREDICATES)
        assert RUNG in predicates, (
            "the coverage bridge has no rung for the writer-bar exclusion, so "
            "every row it removes lands in the representative_not_selected "
            "catch-all and reads as a representative-rule regression"
        )
        assert "is_below_writer_bar" in predicates[RUNG]

    def test_the_rung_is_ordered_before_the_catch_all(self) -> None:
        keys = [key for key, _ in _COVERAGE_RUNG_PREDICATES]
        assert keys.index(RUNG) < keys.index("representative_not_selected")

    def test_the_catch_all_is_still_last(self) -> None:
        """Inserting a rung after the terminal ELSE would make it unreachable."""
        assert _COVERAGE_RUNG_PREDICATES[-1] == ("representative_not_selected", "")
