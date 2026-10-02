"""#6317 — the database-free half of the unpriced-field-winner rung.

The row-level proof is ``tests/integration/test_calibration_unpriced_field_winner_6317_pg.py``
(real ``_calibration_population_ctes`` on seeded rows, named in ``ci.yml``). This
file pins what that gate cannot see without a Postgres: the Python mirror, that
the SQL flag carries NO price-sum gate (the whole defect was a survivor test that
only ran above MEX_NORMALIZE_THRESHOLD), and that the flag reaches every place a
dropped row has to be accounted for.
"""

from __future__ import annotations

import re

import pytest

from app.tasks import precompute_calibration as pc
from app.tasks.precompute_calibration import (
    _COVERAGE_RUNG_PREDICATES,
    FIELD_WINNER_UNPUBLISHED_RULE_TEXT,
    _calibration_population_ctes,
    field_winner_is_unpublished,
)
from app.utils.calibration_staged_futures import DEFAULT_CENSUS_COLUMNS

FLAG = "is_field_winner_unpublished"


def _flag_expression(sql: str) -> str:
    """The SQL text that DEFINES the flag, from its opening paren to ``AS flag``."""
    end = sql.index(f"AS {FLAG}")
    start = sql.rindex("(ro.candidate_market_id IS NOT NULL", 0, end)
    return sql[start:end]


class TestTheMirror:
    @pytest.mark.parametrize(
        "is_candidate, survivor_win_n, expected",
        [
            (True, 0, True),  # proved field, winner did not survive -> drop whole
            (True, 1, False),  # proved field, winner survived -> keep
            (False, 0, False),  # not a proved field -> not this rung's business
            (False, 1, False),
        ],
    )
    def test_truth_table(self, is_candidate, survivor_win_n, expected):
        assert field_winner_is_unpublished(is_candidate, survivor_win_n) is expected


class TestTheSqlRung:
    def test_the_flag_is_not_gated_on_the_price_sum(self):
        """The defect in one line: a field missing its winner's price sums LOW.

        ``is_field_incomplete`` already asks whether the winner survived, but only
        when ``mnm_cp_sum > MEX_NORMALIZE_THRESHOLD``. If this flag reads the sum,
        the rung re-acquires the hole it exists to close.
        """
        expr = _flag_expression(_calibration_population_ctes())
        assert "survivor_win_n" in expr
        assert "mnm_cp_sum" not in expr, expr
        assert str(pc.MEX_NORMALIZE_THRESHOLD) not in expr, expr

    def test_the_flag_is_scoped_to_proved_fields(self):
        expr = _flag_expression(_calibration_population_ctes())
        assert "ro.candidate_market_id IS NOT NULL" in expr

    @pytest.mark.parametrize("cte", ["deduped", "mode_prices"])
    def test_the_flag_gates_every_consumer_of_normalized(self, cte):
        sql = _calibration_population_ctes()
        start = sql.index(f"\n            {cte} AS (")
        following = re.search(r"\n            [a-z_]+ AS \(", sql[start + 1 :])
        body = sql[start : start + 1 + following.start()] if following else sql[start:]
        assert f"NOT {FLAG}" in body or f"NOT ro.{FLAG}" in body, (
            f"{cte} does not refuse {FLAG}"
        )

    def test_the_horizon_path_judges_the_winner_on_its_own_price(self):
        """``survivor_win_n`` is counted over rows present at THIS price expression.

        The horizon builder reuses the canonical CTEs with its own curve price, so
        a winner with no snapshot at the horizon is absent from ``ranked_outcomes``
        there and the rung fires on that horizon even when the terminal price exists.
        """
        sql, _params = pc._build_time_horizon_sql(7)
        assert f"AS {FLAG}" in sql
        assert "JOIN horizon_price hp" in sql


class TestTheDisclosure:
    def test_the_coverage_bridge_assigns_the_rows_a_rung(self):
        """A ``deduped`` filter with no rung lands silently in the terminal ELSE."""
        predicates = dict(_COVERAGE_RUNG_PREDICATES)
        assert FLAG in predicates["field_incomplete"]

    def test_the_census_columns_are_declared(self):
        for column in ("field_winner_unpublished_markets", "field_winner_unpublished_outcomes"):
            assert column in DEFAULT_CENSUS_COLUMNS

    def test_the_payload_carries_the_rule_and_both_counts(self):
        import inspect

        source = inspect.getsource(pc)
        for key in (
            '"winner_unpublished_rule": FIELD_WINNER_UNPUBLISHED_RULE_TEXT',
            '"winner_unpublished_excluded_markets": field_winner_unpublished_markets',
            '"winner_unpublished_excluded_outcomes": field_winner_unpublished_outcomes',
        ):
            assert key in source, key

    def test_the_reader_copy_is_plain(self):
        """No internal vocabulary in what a reader can open (notice 34 / D102)."""
        for jargon in ("survivor", "mnm_cp_sum", "normaliz", "candidate", "price_moved"):
            assert jargon not in FIELD_WINNER_UNPUBLISHED_RULE_TEXT.lower()
