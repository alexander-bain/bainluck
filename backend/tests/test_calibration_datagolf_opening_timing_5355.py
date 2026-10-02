"""#5355 — wiring guards for the DataGolf opening-timing rule.

The ROW behaviour is proved against real Postgres in
``tests/integration/test_calibration_datagolf_post_start_opening_pg.py``. These
guard the parts a row test cannot see without a fixture per surface:

* the rule judges the OPENING, so a horizon caller (priced on a snapshot) renders
  it off, while the headline renders the snapshot predicate;
* a DataGolf win field that loses a member is dropped whole, not normalized over
  its survivors (both survivor counters name the flag);
* the coverage bridge claims the rows on their own rung, in an order where no
  earlier rung can claim a DataGolf row first;
* the disclosure count is declared to the staged merge in the commit that emits
  it (CAL-P162: an undeclared column blocks every publish).
"""

from __future__ import annotations

import app.tasks.precompute_calibration as pc
from app.utils.calibration_coverage_bridge import RUNG_KEYS
from app.utils.calibration_staged_futures import (
    DEFAULT_CENSUS_COLUMNS,
    DISTINCT_CENSUS_COLUMNS,
)

FLAG = "is_datagolf_opening_after_start"


def _headline() -> str:
    return pc._calibration_population_ctes()


def _horizon() -> str:
    return pc._calibration_population_ctes(
        curve_price="hp.horizon_prob",
        curve_price_join="JOIN horizon_price hp ON hp.outcome_id = fo.id",
        rn_order="ABS(hp.horizon_prob - 0.5)",
    )


def test_the_headline_renders_the_snapshot_predicate():
    sql = _headline()
    assert "fos_dgo.bookmaker = 'datagolf_model'" in sql
    assert "fos_dgo.captured_at < fm_dgo.commence_time" in sql
    assert "fos_dgo.probability = fo.opening_probability" in sql
    assert f"END) AS {FLAG}" in sql


def test_a_horizon_caller_renders_the_rule_off():
    sql = _horizon()
    assert f"false AS {FLAG}" in sql
    assert "fos_dgo" not in sql


def test_the_headline_price_is_written_inside_the_hashed_builder():
    """The headline's COALESCE must live in ``_calibration_population_ctes``'s
    own source: ``inspect.getsource`` (every fingerprint) never sees a module
    constant's value, so a constant default would let the curve price change
    while no digest moved."""
    import inspect

    sig = inspect.signature(pc._calibration_population_ctes)
    assert sig.parameters["curve_price"].default is None
    assert (
        '"COALESCE(fo.calibration_probability, fo.opening_probability)"'
        in inspect.getsource(pc._calibration_population_ctes)
    )
    assert "COALESCE(fo.calibration_probability, fo.opening_probability) AS raw_cp" in _headline()


def test_deduped_and_both_survivor_counters_name_the_flag():
    sql = _headline()
    deduped = sql[sql.index("deduped AS (") :]
    assert f"AND NOT ro.{FLAG}" in deduped
    completeness = sql[sql.index("field_completeness AS (") : sql.index("normalized AS (")]
    assert completeness.count(f"AND NOT ro.{FLAG}") == 2


def test_the_rung_is_ordered_where_no_earlier_rung_claims_a_datagolf_row():
    keys = list(RUNG_KEYS)
    i = keys.index("datagolf_opening_after_start")
    assert keys[i - 1] == "opening_below_writer_bar"
    assert keys[i + 1] == "structural_artifact"
    predicates = dict(pc._COVERAGE_RUNG_PREDICATES)
    assert predicates["datagolf_opening_after_start"] == f"COALESCE(n.{FLAG}, false)"


def test_the_disclosure_count_is_declared_to_the_staged_merge():
    for column in (
        "datagolf_opening_after_start_excluded",
        "datagolf_opening_after_start_markets",
    ):
        assert column in DEFAULT_CENSUS_COLUMNS
    assert "datagolf_opening_after_start_markets" in DISTINCT_CENSUS_COLUMNS
    assert "datagolf_opening_after_start_excluded" not in DISTINCT_CENSUS_COLUMNS
