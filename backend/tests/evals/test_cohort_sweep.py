import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evals.cohort_sweep import (
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
