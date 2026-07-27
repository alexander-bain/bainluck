import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evals.shape_semantics_v2 import (
    CLASSIFIER_VERSION,
    canonical_population_crosswalk,
    census,
    classify,
    input_fingerprint,
    load_from_session,
    load_file,
)


FIXTURE = Path(__file__).parent / "fixtures" / "shape_semantics_v2.json"


def by_id():
    return {row["id"]: row for row in load_file(FIXTURE)}


def test_structured_semantics_cover_adversarial_market_types():
    rows = by_id()
    assert classify(rows[1])["outcome_relation"] == "complements"
    assert classify(rows[1])["display_shape"] == "claim"
    assert classify(rows[2])["outcome_relation"] == "competitors"
    assert classify(rows[3])["push_void_capable"] is True
    assert classify(rows[4])["expected_winners"] == 1
    assert classify(rows[5])["outcome_relation"] == "independent_participation"
    assert classify(rows[5])["expected_winners"] == 5
    assert classify(rows[7])["outcome_relation"] == "exclusive_ranges"
    assert classify(rows[8])["outcome_relation"] == "cumulative_thresholds"
    assert "draw_capable" in classify(rows[9])["evidence"]
    assert classify(rows[10])["outcome_relation"] == "conditional"
    assert classify(rows[12])["outcome_relation"] == "unknown"


def test_incomplete_top_n_and_other_risks_are_counted_without_interpretation():
    report = census(load_file(FIXTURE))
    assert report["classifier_version"] == CLASSIFIER_VERSION
    assert report["markets"] == 12
    assert report["risk_flags"]["linked_yes_no"] == 1
    assert report["risk_flags"]["top_n_as_field"] == 2
    assert report["risk_flags"]["incomplete_multi_winner_grading"] == 1
    assert report["risk_flags"]["conditional"] == 1
    assert report["risk_flags"]["exclusive_range"] == 1
    assert report["risk_flags"]["cumulative_ladder"] == 1
    assert report["risk_flags"]["input_fingerprint_changed"] == 1
    assert report["calibration_eligible_risk_flags"]["top_n_as_field"] == 2


def test_fingerprint_changes_when_late_group_or_link_inputs_change():
    base = {
        "source": "polymarket",
        "group_id": "p:x",
        "group_size": 1,
        "outcomes": [{"name": "Yes"}, {"name": "No"}],
    }
    same = json.loads(json.dumps(base))
    assert input_fingerprint(base) == input_fingerprint(same)
    later_group = {**base, "group_size": 4}
    later_link = {**base, "event_id": 88}
    assert input_fingerprint(base) != input_fingerprint(later_group)
    assert input_fingerprint(base) != input_fingerprint(later_link)


def test_canonical_population_crosswalk_is_explicitly_optional():
    rows = load_file(FIXTURE)
    classified = [
        {"input": row, "semantics_v2": classify(row), "risk_flags": []}
        for row in rows
    ]
    assert canonical_population_crosswalk(classified)["status"] == "not_provided"
    result = canonical_population_crosswalk(classified, {"101", "501", "502"})
    assert result == {"status": "provided", "markets": 2, "outcomes": 3, "by_risk": {}}


def test_jsonl_input_matches_json_input(tmp_path):
    rows = load_file(FIXTURE)
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert load_file(path) == rows


@pytest.mark.asyncio
async def test_session_loader_is_read_only_and_returns_mappings():
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = [MagicMock(_mapping={"id": 1, "outcomes": []})]
    session.execute = AsyncMock(return_value=result)
    rows = await load_from_session(session, limit=10)
    assert rows == [{"id": 1, "outcomes": []}]
    statement = str(session.execute.await_args.args[0])
    assert statement.lstrip().startswith("WITH group_sizes")
    assert all(word not in statement.upper() for word in ("UPDATE ", "DELETE ", "INSERT "))


def test_census_output_is_deterministic():
    rows = load_file(FIXTURE)
    first = json.dumps(census(rows), sort_keys=True)
    second = json.dumps(census(rows), sort_keys=True)
    assert first == second
