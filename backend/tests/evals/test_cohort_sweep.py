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
def test_loader_consumes_canonical_population_not_raw():
    # load_from_session must apply the SAME exclusions as the published curve,
    # reusing the shared predicate constants (so it cannot drift), and carry a
    # question identity — not the old raw "calibration_probability IS NOT NULL".
    src = inspect.getsource(load_from_session)
    # Reuses the shared exclusion predicates (imported, not hand-typed).
    assert "KALSHI_LIQUIDITY_EXISTS" in src
    assert "POLY_PLACEHOLDER_EXCLUDE" in src
    assert "kalshi_prop_threshold_exclude_sql" in src
    assert "MEX_NORMALIZE_THRESHOLD" in src
    # Resolution-authority exclusion (guessed / void / heuristic dropped).
    assert "pass2_guess" in src and "pass2_loser" in src
    # Field-completeness normalization gate (same as the payload).
    assert "field_completeness" in src
    assert "survivor_n = fc.eligible_n" in src or "fc.survivor_n = fc.eligible_n" in src
    # Question identity carried; canonical eligibility (opening in (0,1) + volume)
    # replaces the old raw non-null-cp loader.
    assert "question_id" in src
    assert "fo.opening_probability > 0 AND fo.opening_probability < 1" in src
    assert "COALESCE(fo.volume, -1) != 0" in src


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
