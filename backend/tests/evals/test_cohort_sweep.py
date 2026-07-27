import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evals import cohort_sweep
from scripts.evals.cohort_sweep import (
    load_from_session,
    load_rows,
    sweep,
    sweep_by_sport_shape,
    wilson_interval,
)


FIXTURE = Path(__file__).parent / "fixtures/cohort_sweep.json"


def expanded_fixture():
    data = json.loads(FIXTURE.read_text())
    anti = data["rows"][:5] * data["fixture_expansion"]["anti_repeat"]
    small = data["rows"][5:] * data["fixture_expansion"]["small_repeat"]
    return [{**row, "id": f"{row['id']}-{index}"} for index, row in enumerate(anti + small)]


def test_planted_anti_calibrated_cohort_is_flagged():
    report = sweep(expanded_fixture())
    cohort = next(row for row in report["drill_down"] if row["source"] == "kalshi")
    assert cohort["n"] == 40
    assert cohort["sufficient"] is True
    assert cohort["direction"] == "systematic_over"
    assert cohort["anti_calibration"]["flag"] is True
    assert report["worst_20"][0]["source"] == "kalshi"
    assert len(cohort["examples"]) == 10


def test_small_n_trap_is_explicitly_insufficient_and_unranked():
    report = sweep(expanded_fixture())
    cohort = next(row for row in report["drill_down"] if row["source"] == "polymarket")
    assert cohort["n"] == 20
    assert cohort["sufficient"] is False
    assert cohort["direction"] == "insufficient"
    assert cohort["severity"] is None
    assert cohort["anti_calibration"]["flag"] is False
    assert all(row["source"] != "polymarket" for row in report["worst_20"])


@pytest.mark.asyncio
async def test_loader_accepts_json_and_sqlalchemy_session(monkeypatch):
    assert len(await load_rows(FIXTURE)) == 7
    fake_result = MagicMock()
    fake_result.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=fake_result)
    monkeypatch.setattr("scripts.evals.cohort_sweep.load_from_session", AsyncMock(return_value=[]))
    assert await load_rows(session) == []


def test_by_sport_shape_collapses_source_into_one_cell_per_sport_shape():
    # #254 Item 2: each (league_category, market_type) becomes ONE source-
    # collapsed reliability cell (Alex's golf catch — a sport's shapes deserve
    # their own curve, not to be split by source or averaged into the field).
    report = sweep(expanded_fixture())
    cells = report["by_sport_shape"]
    assert all(c["source"] == "_all_sources" for c in cells)
    nfl = next(c for c in cells if c["league_category"] == "NFL" and c["market_type"] == "claim")
    assert nfl["n"] == 40
    assert nfl["sufficient"] is True
    # standalone helper matches the embedded output
    assert sweep_by_sport_shape(expanded_fixture()) == cells


def test_wilson_interval_contains_observed_rate():
    low, high = wilson_interval(20, 40)
    assert low < 0.5 < high


# ---------------------------------------------------------------------------
# Queue #257 Item 2: consume the CANONICAL population + independent-question N.
# ---------------------------------------------------------------------------
def test_loader_delegates_to_the_one_shared_population_builder():
    # Queue #259 Item 2 (C14 P1): the loader no longer HAND-TYPES the population —
    # it builds on the ONE shared canonical CTE producer and selects the final
    # ``deduped`` rows, so serving/audit are row-identical by construction and
    # cannot drift. The predicates therefore live in the shared module, not here.
    src = inspect.getsource(load_from_session)
    assert "_calibration_population_ctes()" in src
    assert "FROM deduped" in src
    assert "vm_id AS question_id" in src
    assert "adj_opening_probability AS probability" in src


@pytest.mark.asyncio
async def test_composed_sql_is_the_full_published_population(monkeypatch):
    # The COMPOSED sweep SQL must carry the entire canonical population — every
    # exclusion, the field-completeness gate, AND (the C14 P1 fix) the production
    # mode/tail dedup + rn=1 binary-side selection that the old loader lacked, so
    # the sweep measures exactly what /api/calibration publishes.
    captured = {}

    class _Result:
        def all(self):
            return []

    class _Sess:
        async def execute(self, statement):
            captured["sql"] = str(statement)
            return _Result()

    await load_from_session(_Sess())
    sql = captured["sql"]
    # Canonical eligibility + resolution-authority calibration-truth allowlist.
    assert "fo.opening_probability > 0 AND fo.opening_probability < 1" in sql
    assert "COALESCE(fo.volume, -1) != 0" in sql
    # Queue #261 Item 1: the population now uses the eligibility ALLOWLIST, so
    # independent-authority sources are named IN, and guess-family / price-derived
    # are excluded by omission (never named). The sweep stays row-identical to
    # /api/calibration because both compose the same _calibration_population_ctes.
    assert "resolution_source IN (" in sql and "'api_settlement'" in sql
    assert "'pass2_guess'" not in sql
    assert "'clean_resolution'" not in sql and "'settlement_sync'" not in sql
    # Every published exclusion (resolved from the shared predicate constants).
    assert "futures_odds_snapshots" in sql  # liquidity / poly-placeholder
    assert "is_kalshi_prop_threshold" in sql
    assert "is_weather_wide_spread" in sql
    # Field-completeness normalization gate.
    assert "field_completeness" in sql
    assert "survivor_n = fc.eligible_n" in sql
    # C14 P1 #2: the production dedup the old loader was MISSING.
    assert "mode_prices" in sql
    assert "ro.adj_opening_probability > 0.005" in sql
    assert "ELSE ro.rn = 1" in sql
    # C14 P1 Item 1 invariant fix: complete normalized fields exempt from tail/mode.
    assert "WHEN ro.is_mex_normalized THEN true" in sql
    # Size-gated production virtual-question identity (C14 P2).
    assert "vm_id AS question_id" in sql


def test_independent_question_n_is_the_honest_sample_size():
    # A single field of 40 candidate outcomes is ONE question, not 40 independent
    # samples — so a cohort of 40 correlated outcomes sharing one question_id is
    # NOT sufficient (independent_questions == 1), even though outcome n == 40.
    rows = [
        {
            "id": f"o-{i}",
            "question_id": "g:one-field",  # all the same question
            "source": "kalshi",
            "llm_sport_category": "politics",
            "market_type": "field",
            "probability": 0.80,
            "is_winner": (i == 0),
        }
        for i in range(40)
    ]
    report = sweep(rows)
    cohort = next(c for c in report["drill_down"] if c["market_type"] == "field")
    assert cohort["n"] == 40
    assert cohort["independent_questions"] == 1
    assert cohort["sufficient"] is False  # 1 question is not a sample of 40
    assert cohort["severity"] is None


def test_distinct_questions_count_as_independent_samples():
    # 40 outcomes across 40 DISTINCT questions ARE 40 independent samples.
    rows = [
        {
            "id": f"o-{i}",
            "question_id": f"m:{i}",  # each its own question
            "source": "kalshi",
            "llm_sport_category": "politics",
            "market_type": "binary",
            "probability": 0.80,
            "is_winner": (i % 2 == 0),
        }
        for i in range(40)
    ]
    report = sweep(rows)
    cohort = next(c for c in report["drill_down"] if c["market_type"] == "binary")
    assert cohort["n"] == 40
    assert cohort["independent_questions"] == 40
    assert cohort["sufficient"] is True


# ---------------------------------------------------------------------------
# Queue #259 Item 3: question-clustered uncertainty. Correlated outcomes of one
# field/question are NOT independent samples, so CIs and the anti-calibration
# gate must key off distinct questions, not the outcome count.
# ---------------------------------------------------------------------------
def _high_all_losers(n_questions, per_question, question_prefix, market_type):
    return [
        {
            "id": f"{question_prefix}-{q}-{k}",
            "question_id": f"{question_prefix}:{q}",
            "source": "kalshi",
            "llm_sport_category": "politics",
            "market_type": market_type,
            "probability": 0.90,
            "is_winner": False,
        }
        for q in range(n_questions)
        for k in range(per_question)
    ]


def test_one_huge_correlated_field_cannot_flag_anti_calibration():
    # ONE field question with 100 high-price losing outcomes. Outcome n=100 would
    # trivially clear the >=30 anti gate under outcome-count Wilson, but it is ONE
    # question — so it is insufficient and cannot flag anti-calibration or claim a
    # systematic-bias direction on its own.
    rows = _high_all_losers(1, 100, "g:one-field", "field")
    cohort = next(
        c for c in sweep(rows)["drill_down"] if c["market_type"] == "field"
    )
    assert cohort["n"] == 100
    assert cohort["independent_questions"] == 1
    assert cohort["anti_calibration"]["high_price_n"] == 100
    assert cohort["anti_calibration"]["high_price_questions"] == 1
    assert cohort["sufficient"] is False
    assert cohort["anti_calibration"]["flag"] is False
    assert cohort["direction"] == "insufficient"
    assert cohort["severity"] is None


def test_many_independent_high_price_questions_do_flag_anti_calibration():
    # 40 DISTINCT high-price questions, each a real losing forecast -> a genuine
    # anti-calibrated cohort that SHOULD flag (contrast with the single field).
    rows = _high_all_losers(40, 1, "m", "binary")
    cohort = next(
        c for c in sweep(rows)["drill_down"] if c["market_type"] == "binary"
    )
    assert cohort["independent_questions"] == 40
    assert cohort["anti_calibration"]["high_price_questions"] == 40
    assert cohort["sufficient"] is True
    assert cohort["anti_calibration"]["flag"] is True
    assert cohort["direction"] == "systematic_over"


def test_mixed_field_sizes_gate_on_distinct_high_price_questions():
    # 29 distinct high-price binary questions + ONE 100-outcome field. Outcome
    # high_price_n = 129 (>=30), but distinct high-price QUESTIONS = 30, and the
    # field contributes just one question — the honest sample size is 30 questions,
    # not 129 outcomes, so the anti gate keys off the question count.
    rows = _high_all_losers(29, 1, "m", "binary") + _high_all_losers(1, 100, "g:mixed", "binary")
    cohort = next(
        c for c in sweep(rows)["drill_down"] if c["market_type"] == "binary"
    )
    assert cohort["anti_calibration"]["high_price_n"] == 129
    assert cohort["anti_calibration"]["high_price_questions"] == 30
    assert cohort["independent_questions"] == 30


def test_cluster_ci_widens_as_questions_shrink_for_equal_outcomes():
    # Same 60 outcomes, same 50% actual rate, but clustered into FEWER questions ->
    # a WIDER question-clustered interval (fewer independent samples). Each question
    # resolves as a UNIT (all-win or all-lose) so the between-question variance the
    # cluster bootstrap measures is real; a whole-win / whole-lose alternation keeps
    # the overall actual rate at 0.5 for both. Proves the CI keys off question
    # count, not outcome count.
    def cohort_for(questions):
        per = 60 // questions
        rows = [
            {
                "id": f"o-{q}-{k}",
                "question_id": f"m:{q}",
                "source": "kalshi",
                "llm_sport_category": "politics",
                "market_type": "binary",
                "probability": 0.50,
                "is_winner": (q % 2 == 0),  # each question wholly wins or loses
            }
            for q in range(questions)
            for k in range(per)
        ]
        return next(c for c in sweep(rows)["drill_down"] if c["market_type"] == "binary")

    many = cohort_for(60)   # 60 questions x 1 outcome
    few = cohort_for(4)     # 4 questions x 15 outcomes
    assert many["actual_rate"] == 0.5 and few["actual_rate"] == 0.5
    many_lo, many_hi = many["actual_rate_ci95"]
    few_lo, few_hi = few["actual_rate_ci95"]
    assert (few_hi - few_lo) > (many_hi - many_lo)
    assert many["actual_rate_ci95_method"] == "question_cluster_bootstrap"


def test_cluster_bootstrap_is_deterministic():
    rows = _high_all_losers(40, 2, "m", "binary")
    a = sweep(rows)["drill_down"]
    b = sweep(rows)["drill_down"]
    assert a == b


@pytest.mark.asyncio
async def test_load_from_session_executes_canonical_query(monkeypatch):
    # The real loader issues ONE text() query and maps rows to dicts (the shape
    # normalize_rows/analyze_cohort consume). Verified without a live Postgres.
    captured = {}

    class _Result:
        def all(self):
            return []

    class _Sess:
        async def execute(self, statement):
            captured["sql"] = str(statement)
            return _Result()

    out = await load_from_session(_Sess())
    assert out == []
    assert "question_id" in captured["sql"]
    assert "field_completeness" in captured["sql"]
