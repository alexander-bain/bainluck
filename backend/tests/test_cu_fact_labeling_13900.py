"""Tests for #13900 Content Understanding dual-rater fact labeling & agreement."""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.models import CuFactLabel
from app.utils.cu_fact_labeling import (
    build_answer_key_rows,
    compute_cu_fact_agreement,
    extract_subject_candidates,
    order_queue_markets,
    select_shared_100_ids,
    validate_label_submission,
    visible_labels_for_rater,
)


def _sample_label(
    *,
    market_id: int = 101,
    rater: str = "rater-one",
    role: str = "primary",
    geography: str = "us",
    event_date: str | None = "2026-06-15",
    no_single_day: bool = False,
    structure: str = "neither",
    stakes: int | None = 3,
    breadth: int | None = 3,
    evidence_note: str | None = None,
) -> dict:
    return {
        "dataset_split": "sealed",
        "market_id": market_id,
        "rater": rater,
        "role": role,
        "subjects_answer": {"selection_kind": "candidate", "selected": ["Boston Celtics"]},
        "event_date_answer": event_date,
        "no_single_day": no_single_day,
        "geography_answer": geography,
        "structure_answer": structure,
        "claim_frame": {"measure": "wins", "comparison": "gte", "value": "50", "unit": "wins"},
        "stakes": stakes,
        "breadth": breadth,
        "evidence_note": evidence_note,
    }


def test_blindness_hides_peer_answers_while_labeling():
    rows = [
        _sample_label(rater="labeler-a", role="primary", geography="local"),
        _sample_label(rater="labeler-b", role="second", geography="us"),
    ]
    vis_a = visible_labels_for_rater(rows, role="primary", rater="labeler-a")
    assert vis_a["own_label"] is not None
    assert vis_a["pair_complete"] is True
    assert vis_a["peer_labels"] == []
    assert vis_a["disagreeing_fact_fields"] == []

    # Tiebreak sees both raters' fact answers (stakes/breadth stripped) when facts differ
    vis_tb = visible_labels_for_rater(rows, role="tiebreak", rater="reviewer-c")
    assert vis_tb["disagreeing_fact_fields"] == ["geography"]
    assert len(vis_tb["peer_labels"]) == 2
    assert all("stakes" not in peer and "breadth" not in peer for peer in vis_tb["peer_labels"])


def test_tiebreak_rejects_taste_and_requires_written_evidence():
    pair = [
        _sample_label(rater="labeler-a", role="primary", geography="local"),
        _sample_label(rater="labeler-b", role="second", geography="us"),
    ]
    # Taste fields are forbidden in tiebreak mode
    with pytest.raises(ValueError, match="stakes and breadth"):
        validate_label_submission(
            _sample_label(
                rater="reviewer-c",
                role="tiebreak",
                stakes=2,
                breadth=None,
                evidence_note="Title names a state house district.",
            ),
            existing_market_rows=pair,
        )

    # Written evidence is mandatory in tiebreak mode
    with pytest.raises(ValueError, match="evidence_note"):
        validate_label_submission(
            _sample_label(
                rater="reviewer-c",
                role="tiebreak",
                stakes=None,
                breadth=None,
                evidence_note="",
            ),
            existing_market_rows=pair,
        )

    ok = validate_label_submission(
        _sample_label(
            rater="reviewer-c",
            role="tiebreak",
            geography="local",
            stakes=None,
            breadth=None,
            evidence_note="Vermont House Orleans-3 is a state house seat.",
        ),
        existing_market_rows=pair,
    )
    assert ok["stakes"] is None and ok["breadth"] is None and ok["geography_answer"] == "local"


def test_agreement_metrics_exact_for_facts_within_one_for_taste_and_flags_below_80():
    rows = []
    # 5 paired markets:
    # - geography disagrees on 2/5 (60% < 80% -> flagged)
    # - stakes differs by 1 on all 5 (100% within-1 agreement)
    # - breadth differs by 2 on 2/5 (60% < 80% -> flagged)
    for idx in range(5):
        mid = 500 + idx
        rows.append(
            _sample_label(
                market_id=mid,
                rater="labeler-a",
                role="primary",
                geography="us",
                stakes=3,
                breadth=4,
            )
        )
        rows.append(
            _sample_label(
                market_id=mid,
                rater="labeler-b",
                role="second",
                geography="local" if idx < 2 else "us",
                stakes=4,
                breadth=1 if idx < 2 else 3,
            )
        )
    # Tiebreak resolved one of the two fact disagreements
    rows.append(
        _sample_label(
            market_id=500,
            rater="reviewer-c",
            role="tiebreak",
            geography="local",
            stakes=None,
            breadth=None,
            evidence_note="Confirmed district seat in title.",
        )
    )

    report = compute_cu_fact_agreement(rows, split="sealed")
    assert report["paired_markets"] == 5
    assert report["resolved_tiebreaks"] == 1
    assert report["needs_tiebreak"] == 1
    assert set(report["below_80_fields"]) == {"geography", "breadth"}
    by_field = {f["field"]: f for f in report["fields"]}
    assert by_field["stakes"]["metric"] == "within_1"
    assert by_field["stakes"]["agreement_rate"] == 1.0
    assert by_field["geography"]["metric"] == "exact"
    assert by_field["geography"]["agreement_rate"] == 0.6


def test_shared_100_selection_and_dev_priority_queue_ordering():
    sealed = [
        {"market_id": 1000 + i, "draw_bucket": "reader_weighted" if i < 200 else "roster_spread"}
        for i in range(300)
    ]
    shared = select_shared_100_ids(sealed)
    assert len(shared) == 100
    rw_count = sum(1 for mid in shared if mid < 1200)
    assert rw_count == 67

    dev = [{"market_id": 1}, {"market_id": 2}, {"market_id": 3}]
    ordered = order_queue_markets(dev, split="dev", scope="all", repeatability_priority_ids=[3, 1])
    assert [m["market_id"] for m in ordered] == [3, 1, 2]


def test_blind_subject_candidates_exclude_llm_metadata():
    candidates = extract_subject_candidates({
        "title": "Will Arsenal FC beat Chelsea FC on May 10?",
        "outcome_names": ["Arsenal FC", "Draw", "Yes"],
        "discover_llm": {"entities": [{"name": "LeakedLLMSubject", "type": "team"}]},
    })
    assert "Arsenal FC" in candidates
    assert "LeakedLLMSubject" not in candidates


def test_answer_key_export_respects_tiebreak_override():
    rows = [
        _sample_label(market_id=42, rater="a", role="primary", geography="us"),
        _sample_label(market_id=42, rater="b", role="second", geography="local"),
        _sample_label(
            market_id=42,
            rater="c",
            role="tiebreak",
            geography="local",
            stakes=None,
            breadth=None,
            evidence_note="State house seat in title.",
        ),
    ]
    exported = build_answer_key_rows(
        {42: {"market_id": 42, "source": "kalshi", "category": "politics", "outcome_names": ["Yes", "No"]}},
        rows,
        split="sealed",
    )
    assert len(exported) == 1
    assert exported[0]["resolution_source"] == "tiebreak"
    assert exported[0]["answers"]["geography"] == "local"


def test_migration_and_router_wiring():
    assert CuFactLabel.__tablename__ == "cu_fact_labels"
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "cu_fact_labels_13900.py"
    )
    text = mig_path.read_text(encoding="utf-8")
    assert 'revision = "cu_fact_labels_13900"' in text
    assert len("cu_fact_labels_13900") <= 32
    assert "def upgrade():" in text and "def downgrade():" in text

    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/api/admin/cu-labeling/queue" in routes
    assert "/api/admin/cu-labeling/label" in routes
    assert "/api/admin/cu-labeling/agreement" in routes
    assert "/api/admin/cu-labeling/export-answer-key" in routes

    client = TestClient(app)
    resp = client.get("/api/admin/cu-labeling/queue", params={"rater": "tester"})
    assert resp.status_code == 403
