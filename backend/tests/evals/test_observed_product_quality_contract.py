import json
from pathlib import Path

from backend.scripts.evals.observed_product_quality_contract import (
    observed_staleness,
    temporal_interestingness_split,
)


FIXTURES = Path(__file__).parent / "fixtures" / "observed_product_quality_contract.json"


def test_staleness_counts_observed_impressions_including_duplicates():
    pack = json.loads(FIXTURES.read_text())
    assert observed_staleness(pack["impressions"], pack["lifecycle"]) == pack["expected"]


def test_unmatched_rendered_card_is_unknown_not_clean():
    result = observed_staleness([{"card_id": "x", "surface": "web"}], {})
    assert result["unknown"] == 1
    assert result["stale_rate_known"] is None
    assert result["unknown_rate"] == 1.0


def test_empty_render_capture_is_not_a_zero_stale_claim():
    result = observed_staleness([], {})
    assert result["impressions"] == 0
    assert result["stale_rate_known"] is None
    assert result["unknown_rate"] is None


def _rows(train=60, holdout=60):
    rows = [
        {"item_id": f"train-{i}", "labeled_at": "2026-07-31T12:00:00Z", "label": i % 2}
        for i in range(train)
    ]
    rows += [
        {"item_id": f"hold-{i}", "labeled_at": "2026-08-02T12:00:00Z", "label": i % 2}
        for i in range(holdout)
    ]
    return rows


def test_clean_temporal_holdout_is_evaluable():
    result = temporal_interestingness_split(_rows(), cutoff="2026-08-01T00:00:00Z")
    assert result["verdict"] == "EVALUATE"
    assert result["train_rows"] == result["holdout_rows"] == 60
    assert result["holdout_positives"] == result["holdout_negatives"] == 30


def test_cutoff_boundary_belongs_to_holdout():
    rows = _rows()
    rows.append({"item_id": "boundary", "labeled_at": "2026-08-01T00:00:00Z", "label": 1})
    result = temporal_interestingness_split(rows, cutoff="2026-08-01T00:00:00Z")
    assert "boundary" in result["holdout_item_ids"]


def test_same_item_across_time_is_refused_as_leakage():
    rows = _rows()
    rows.append({"item_id": "train-1", "labeled_at": "2026-08-03T00:00:00Z", "label": 1})
    result = temporal_interestingness_split(rows, cutoff="2026-08-01T00:00:00Z")
    assert result["verdict"] == "REFUSE"
    assert result["reasons"] == ["ITEM_ID_LEAKAGE"]


def test_small_or_one_class_holdout_is_refused():
    rows = _rows(60, 10)
    for row in rows:
        if row["item_id"].startswith("hold-"):
            row["label"] = 1
    result = temporal_interestingness_split(rows, cutoff="2026-08-01T00:00:00Z", min_holdout=50)
    assert set(result["reasons"]) == {"HOLDOUT_ONE_CLASS", "HOLDOUT_TOO_SMALL"}


def test_invalid_timestamp_and_missing_label_fail_closed():
    rows = _rows()
    rows.append({"item_id": "bad-time", "labeled_at": "yesterday", "label": 1})
    rows[-2].pop("label")
    result = temporal_interestingness_split(rows, cutoff="2026-08-01T00:00:00Z")
    assert set(result["reasons"]) == {"HOLDOUT_LABELS_INCOMPLETE", "INVALID_LABEL_TIMESTAMPS"}
