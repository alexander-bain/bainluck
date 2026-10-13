"""#938 — wiring and gate guards for the Kalshi golf round-timing rule.

The ROW behaviour is proved against real Postgres in
``tests/integration/test_calibration_golf_round_timing_pg.py``. These guard the
parts a row test cannot see without a fixture per surface:

* "round-scoped" has one definition: the curve's pattern is the repair rail's
  ``ROUND_SERIES_PATTERN``, so the two can never disagree about a ticker;
* the rule keys on structure only — source, category, ticker — and on no price
  or resolution column, so it cannot select on the answer;
* it renders in every caller (a horizon snapshot is bounded on the same
  round-close ``commence_time``), is withheld in ``deduped`` and in both
  field-completeness survivor counters, and has its own coverage rung ordered
  before the golf-placeholder arm;
* its disclosure counts are declared to the staged merge in the commit that
  emits them (CAL-P162);
* the predicate move is DECLARED to the publish gate by its exact digest pair,
  and the declaration holds to what it says (#8458's mechanism, as #5355).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

import app.tasks.precompute_calibration as pc
from app.tasks.repair_golf_round_closing_line import ROUND_SERIES_PATTERN
from app.utils.calibration_coverage_bridge import RUNG_KEYS
from app.utils.calibration_publish_gate import (
    DECLARED_PREDICATE_SUCCESSIONS,
    PREDICATE_FIELD,
    census,
    evaluate_publish,
    gate_ledger_record,
)
from app.utils.calibration_staged_futures import (
    DEFAULT_CENSUS_COLUMNS,
    DISTINCT_CENSUS_COLUMNS,
)

FLAG = "is_golf_round_price_unanchored"
RUNG = "golf_round_price_unanchored"


def _headline() -> str:
    return pc._calibration_population_ctes()


def _horizon() -> str:
    return pc._calibration_population_ctes(
        curve_price="hp.horizon_prob",
        curve_price_join="JOIN horizon_price hp ON hp.outcome_id = fo.id",
        rn_order="ABS(hp.horizon_prob - 0.5)",
    )


def _flag_sql(sql: str) -> str:
    end = sql.index(f" AS {FLAG}")
    start = sql.rindex("(cv.source = 'kalshi'", 0, end)
    return sql[start:end]


class TestTheRule:
    def test_the_curve_and_the_repair_rail_share_one_round_pattern(self):
        assert f"~ '{ROUND_SERIES_PATTERN}'" in _flag_sql(_headline())

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXPGAR3TOP10-THOC26",  # the specimen
            "KXPGAR1TOP5-THOC26",
            "KXPGAR1TOP20-PGC26",
            "KXPGAR2LEAD-THOC26",
            "KXDPWORLDTOURR1LEAD-HEIO26",
            "KXLPGAR3LEAD-JODC26",
            "KXLIVR1LEAD-X26",
            "KXCHAMPTOURR1LEAD-X26",
        ],
    )
    def test_every_round_series_on_production_matches(self, ticker):
        # The production series list (one bounded read, 2026-10-13): every
        # round-scoped LEAD/TOPn series in the golf cell.
        assert re.search(ROUND_SERIES_PATTERN, ticker.split("-", 1)[0])

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXPGATOP10-THOC26",  # the specimen's tournament sibling
            "KXPGATOUR-THOC26",
            "KXPGAMAKECUT-THOC26",
            "KXPGAROUNDSCORE-THOC26",  # an R that is not a round
            "KXPGAROUNDLOW-THOC26",
            "KXOWGRRANK-26",
            "KXPGATOUR2026-THOC26",  # R2 inside a year
            "KXPGAR1LEADMARGIN-THOC26",  # mentions a round lead, is a prop
        ],
    )
    def test_no_tournament_long_series_matches(self, ticker):
        assert not re.search(ROUND_SERIES_PATTERN, ticker.split("-", 1)[0])

    def test_it_keys_on_structure_never_on_a_price_or_the_result(self):
        """A rule that read a price or ``is_winner`` could select on the answer
        (0.99 winners, 0.01 losers) — the very defect it removes."""
        flag = _flag_sql(_headline())
        for column in (
            "probability",
            "is_winner",
            "resolution",
            "captured_at",
            "commence_time",
        ):
            assert column not in flag, column
        assert "cv.source = 'kalshi'" in flag
        assert "cv.category = 'golf'" in flag
        assert "fm_grt.id = fo.market_id" in flag

    def test_it_renders_in_every_caller(self):
        """The horizon price is a snapshot bounded on the same round-close
        ``commence_time``, so it is no better placed than the headline's."""
        assert _flag_sql(_horizon()) == _flag_sql(_headline())

    def test_the_rule_is_written_inside_the_hashed_builder(self):
        import inspect

        assert "golf_round_price_unanchored = " in inspect.getsource(
            pc._calibration_population_ctes
        )


class TestTheWiring:
    def test_deduped_and_both_survivor_counters_name_the_flag(self):
        sql = _headline()
        deduped = sql[sql.index("deduped AS (") :]
        assert f"AND NOT ro.{FLAG}" in deduped
        completeness = sql[sql.index("field_completeness AS (") : sql.index("normalized AS (")]
        assert completeness.count(f"AND NOT ro.{FLAG}") == 2

    def test_the_rung_is_its_own_and_precedes_the_golf_placeholder_arm(self):
        keys = list(RUNG_KEYS)
        i = keys.index(RUNG)
        assert keys[i - 1] == "datagolf_opening_after_start"
        assert keys.index("structural_artifact") > i
        predicates = dict(pc._COVERAGE_RUNG_PREDICATES)
        assert predicates[RUNG] == f"COALESCE(n.{FLAG}, false)"
        assert [k for k, _sql in pc._COVERAGE_RUNG_PREDICATES] == keys

    def test_the_disclosure_counts_are_declared_to_the_staged_merge(self):
        for column in (f"{RUNG}_excluded", f"{RUNG}_markets"):
            assert column in DEFAULT_CENSUS_COLUMNS
            assert f"AS {column}" in pc._main_futures_sql()
        assert f"{RUNG}_markets" in DISTINCT_CENSUS_COLUMNS
        assert f"{RUNG}_excluded" not in DISTINCT_CENSUS_COLUMNS

    def test_the_payload_discloses_the_one_cell_it_can_touch(self):
        import inspect

        src = inspect.getsource(pc.compute_calibration_payload)
        section = src[src.index('"golf_round_timing_filter": {') :]
        section = section[: section.index("},") + 2]
        assert '"applies_to": "kalshi"' in section
        assert '"rule": GOLF_ROUND_TIMING_RULE_TEXT' in section
        assert f'"excluded": {RUNG}_excluded' in section
        assert f'"excluded_markets": {RUNG}_markets' in section
        assert '"excluded_cells": [["kalshi", "golf"]]' in section


# --- the declared predicate succession ---------------------------------------

#: Master's pin since #1011, and the predicate the 2026-10-13 09:17Z served
#: artifact states.
PUBLISHED_PREDICATE = "598e0ed820277a9748363a4d7a276a63"
CANDIDATE_PREDICATE = "ea3ef49d2a15568e11d7d8e54240bfdb"
PAIR = (PUBLISHED_PREDICATE, CANDIDATE_PREDICATE)

#: The served artifact's population, and a rebuild's worth of growth past 5%.
PUBLISHED_POP = 1_160_981
CANDIDATE_POP = 1_260_000

#: Not a measured figure — the real count is read off the candidate at evaluate
#: time. Sized under the Kalshi golf cell's whole published share (17,302).
NARROWING = 6_000


def _payload(*, outcomes: int, predicate: str, excluded=None) -> dict:
    payload = {
        "buckets": [
            {
                "bucket_idx": i,
                "n": max(1, outcomes // 20),
                "winners": max(1, outcomes // 40),
                "sum_prob": max(1, outcomes // 40) * 1.0,
                "price_moved": i % 2 == 0,
            }
            for i in range(10)
        ],
        "by_category": [
            {"category": "soccer", "outcomes": int(outcomes * 0.4), "ece": 1.5},
            {"category": "golf", "outcomes": int(outcomes * 0.04), "ece": 1.5},
        ],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes - 100,
        "total_winners": outcomes // 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applied": True},
        "truth_evidence": {"rungs": []},
        "population_version": "q271",
        PREDICATE_FIELD: predicate,
    }
    if excluded is not None:
        # The shape `compute_calibration_payload` emits for #938.
        payload["golf_round_timing_filter"] = {
            "applies_to": "kalshi",
            "rule": "r",
            "excluded": excluded,
            "excluded_markets": max(0, excluded // 120),
            "excluded_cells": [["kalshi", "golf"]],
        }
    return payload


def _published() -> dict:
    return _payload(outcomes=PUBLISHED_POP, predicate=PUBLISHED_PREDICATE)


def _candidate(**kw) -> dict:
    kw.setdefault("outcomes", CANDIDATE_POP)
    kw.setdefault("predicate", CANDIDATE_PREDICATE)
    kw.setdefault("excluded", NARROWING)
    return _payload(**kw)


class TestTheDeclaredSuccession:
    def test_this_tree_states_the_declared_candidate(self):
        assert pc.population_predicate_fingerprint() == CANDIDATE_PREDICATE
        assert PAIR in DECLARED_PREDICATE_SUCCESSIONS

    def test_the_chain_is_contiguous_from_the_1011_widening(self):
        landed = {b for (_a, b) in DECLARED_PREDICATE_SUCCESSIONS}
        assert PUBLISHED_PREDICATE in landed

    def test_the_pair_is_declared_with_a_bounded_cap(self):
        entry = DECLARED_PREDICATE_SUCCESSIONS[PAIR]
        assert entry["narrowing"] == "golf_round_timing"
        assert entry["issue"] == 938
        assert entry["listed"] is False
        # The Kalshi golf cell was 1.49% of the served population; the cap may
        # not be loose enough to admit a rule that removed another cell's rows.
        assert 1.49 < entry["max_narrowing_pct"] <= 5.0

    def test_the_declared_pair_publishes_across_growth(self):
        verdict = evaluate_publish(_candidate(), _published())

        assert verdict.ok, verdict.summary()
        assert verdict.observation_codes == [
            "population_growth_acknowledged",
            "population_predicate_succession_declared",
        ]
        record = gate_ledger_record(verdict)["predicate_succession"]
        assert record["admitted"] is True
        assert record["narrowing"] == NARROWING
        assert record["narrowing_listed"] is None
        assert "#938" in record["cause"]

    def test_control_the_same_growth_without_the_declaration_refuses(self):
        """Non-vacuity: the pair, not the numbers, is what admits the build."""
        verdict = evaluate_publish(_candidate(predicate="0" * 32), _published())
        assert verdict.codes == ["population_drift"]
        assert verdict.predicate_succession is None

    @pytest.mark.parametrize("excluded", [None, 0])
    def test_an_absent_or_zero_narrowing_refuses(self, excluded):
        verdict = evaluate_publish(_candidate(excluded=excluded), _published())
        assert verdict.codes == ["population_drift"]
        assert verdict.predicate_succession["admitted"] is False

    def test_a_narrowing_past_the_cap_refuses(self):
        cap = DECLARED_PREDICATE_SUCCESSIONS[PAIR]["max_narrowing_pct"]
        too_many = int(CANDIDATE_POP * (cap / 100) * 1.2)
        verdict = evaluate_publish(_candidate(excluded=too_many), _published())
        assert verdict.codes == ["population_drift"]
        assert "cap" in verdict.summary()

    def test_the_census_reads_the_section_and_states_no_second_figure(self):
        assert census(_candidate())["golf_round_timing"] == {
            "excluded": NARROWING,
            "listed_outcomes": None,
            "section_present": True,
        }
        assert census(None)["golf_round_timing"] is None

    def test_the_datagolf_census_does_not_read_this_section(self):
        """Two rules, two statements: a candidate carrying only this section
        must not satisfy the #5355 entry's narrowing."""
        assert census(_candidate())["datagolf_opening_timing"]["excluded"] is None
