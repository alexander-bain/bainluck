"""Tests for #13900 Content Understanding dual-rater fact labeling & agreement."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.models import CuFactLabel
from app.routes import admin_cu_labeling
from app.services import get_db
from app.utils.cu_fact_labeling import (
    build_answer_key_bundle,
    build_answer_key_rows,
    extract_subject_candidates,
    get_claim_vocabulary,
    order_queue_markets,
    select_shared_100_ids,
    validate_label_submission,
    visible_labels_for_rater,
)


def _sample_label(
    *,
    dataset_split: str = "sealed",
    market_id: int = 101,
    rater: str = "rater-one",
    role: str = "primary",
    subjects_answer: dict | None = None,
    geography: str = "us",
    event_date: str | None = "2026-06-15",
    no_single_day: bool = False,
    structure: str = "neither",
    claim_frame: dict | None = None,
    stakes: int | None = 3,
    breadth: int | None = 3,
    evidence_note: str | None = None,
) -> dict:
    return {
        "dataset_split": dataset_split,
        "market_id": market_id,
        "rater": rater,
        "role": role,
        "subjects_answer": subjects_answer
        if subjects_answer is not None
        else {"selection_kind": "candidate", "selected": ["Boston Celtics"]},
        "event_date_answer": event_date,
        "no_single_day": no_single_day,
        "geography_answer": geography,
        "structure_answer": structure,
        "claim_frame": claim_frame
        if claim_frame is not None
        else {
            "measure": "wins",
            "comparator": "gte",
            "value": "50",
            "unit": "wins",
            "horizon_kind": "annual",
            "window_date": None,
        },
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


def test_claim_frame_uses_writer_vocabulary_and_none_of_these():
    vocab = get_claim_vocabulary()
    assert "wins" in vocab["measures"]
    assert "gte" in vocab["comparators"]
    assert "annual" in vocab["horizon_kinds"]
    assert vocab["special_options"] == ["none_of_these"]

    ok = validate_label_submission(
        _sample_label(
            claim_frame={
                "measure": "wins",
                "comparator": "none_of_these",
                "value": "50",
                "unit": "wins",
                "horizon_kind": "annual",
                "window_date": "",
            }
        )
    )
    assert ok["claim_frame"] == {
        "measure": "wins",
        "comparator": "none_of_these",
        "value": "50",
        "unit": "wins",
        "horizon_kind": "annual",
        "window_date": None,
    }

    with pytest.raises(ValueError, match="claim_frame.measure"):
        validate_label_submission(
            _sample_label(claim_frame={"measure": "freeform_unknown_measure"})
        )


def test_agreement_and_scorecard_answer_key_matching_contract():
    rows = []
    # 5 paired markets:
    # - geography disagrees on 2/5 (60% < 80%)
    # - stakes differs by 1 on all 5 (100% within-1 -> scorable as [3, 4])
    # - breadth differs by 3 on 2/5 (60% < 80% -> withheld from scorecard answers)
    for idx in range(5):
        mid = 500 + idx
        rows.append(
            _sample_label(
                market_id=mid,
                rater="labeler-a",
                role="primary",
                geography="us",
                subjects_answer={"selection_kind": "candidate", "selected": ["Boston Celtics"]},
                claim_frame={
                    "measure": "wins",
                    "comparator": "none_of_these",
                    "value": "50",
                    "unit": "wins",
                    "horizon_kind": "annual",
                    "window_date": None,
                },
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
                subjects_answer={"selection_kind": "candidate", "selected": ["Boston Celtics"]},
                claim_frame={
                    "measure": "wins",
                    "comparator": "none_of_these",
                    "value": "50",
                    "unit": "wins",
                    "horizon_kind": "annual",
                    "window_date": None,
                },
                stakes=4,
                breadth=1 if idx < 2 else 3,
            )
        )
    rows.append(
        _sample_label(
            market_id=500,
            rater="reviewer-c",
            role="tiebreak",
            geography="local",
            claim_frame={
                "measure": "wins",
                "comparator": "none_of_these",
                "value": "50",
                "unit": "wins",
                "horizon_kind": "annual",
                "window_date": None,
            },
            stakes=None,
            breadth=None,
            evidence_note="Confirmed district seat in title.",
        )
    )
    # Single not_sure market omits entities from scorecard answers.
    rows.append(
        _sample_label(
            market_id=599,
            rater="labeler-a",
            role="primary",
            subjects_answer={"selection_kind": "not_sure", "selected": []},
            stakes=2,
            breadth=2,
        )
    )

    markets_by_id = {
        500 + idx: {
            "market_id": 500 + idx,
            "source": "kalshi",
            "category": "politics" if idx == 0 else "sports",
            "outcome_names": ["Yes", "No"],
            "draw_bucket": "reader_weighted",
        }
        for idx in range(5)
    }
    markets_by_id[599] = {"market_id": 599, "source": "polymarket", "category": "other", "outcome_names": ["Yes", "No"]}

    bundle = build_answer_key_bundle(markets_by_id, rows, split="sealed")
    report = bundle["agreement"]
    assert report["paired_markets"] == 5
    assert report["resolved_tiebreaks"] == 1
    assert report["needs_tiebreak"] == 1
    assert bundle["withheld_taste_fields"] == ["breadth"]

    by_mid = {row["market_id"]: row for row in bundle["rows"]}
    m500 = by_mid[500]
    assert m500["resolution_source"] == "tiebreak"
    assert m500["answers"]["geography"] == "local"
    assert m500["answers"]["entities"] == ["Boston Celtics"]  # plain strings, never {"type": "unknown"}
    assert m500["answers"]["frame"] == {
        "measure": "wins",
        "comparator": None,
        "value": "50",
        "unit": "wins",
        "horizon_kind": "annual",
        "window_date": None,
    }
    assert m500["answers"]["stakes"] == [3, 4]  # both raters kept even when tiebreak resolved facts
    assert "breadth" not in m500["answers"]  # < 80% agreement goes to Alex, never scored

    # Unresolved fact disagreement on market 501 omits only the disputed fact field.
    m501 = by_mid[501]
    assert "geography" not in m501["answers"]
    assert m501["answers"]["stakes"] == [3, 4]
    assert "breadth" not in m501["answers"]

    # not_sure omits entities instead of scoring [].
    assert "entities" not in by_mid[599]["answers"]
    assert by_mid[599]["answers"]["stakes"] == 2


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


def test_migration_router_and_sealed_protection(monkeypatch):
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
    assert "/api/admin/cu-labeling/score-sealed" in routes

    async def _fake_db():
        yield AsyncMock()

    monkeypatch.setattr(admin_cu_labeling, "_check_admin_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr(admin_cu_labeling, "frozen_split_exists", lambda split: False)
    monkeypatch.setattr(admin_cu_labeling, "load_frozen_split", lambda split: [])
    monkeypatch.setattr(admin_cu_labeling, "_db_rows_for_split", AsyncMock(return_value=[]))
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)

        # Queue announces missing frozen dataset file + ships full claim vocabulary.
        q_resp = client.get("/api/admin/cu-labeling/queue", params={"rater": "tester"})
        assert q_resp.status_code == 200
        q_body = q_resp.json()
        assert q_body["dataset_file_present"] is False
        assert "not loaded" in q_body["dataset_file_missing_message"]
        assert "wins" in q_body["claim_vocabulary"]["measures"]

        # Sealed export is forbidden so sealed answers cannot leave the server.
        sealed_export = client.get("/api/admin/cu-labeling/export-answer-key", params={"split": "sealed"})
        assert sealed_export.status_code == 403

        # Dev export remains permitted.
        dev_export = client.get("/api/admin/cu-labeling/export-answer-key", params={"split": "dev"})
        assert dev_export.status_code == 200
        assert dev_export.json()["dataset"] == "dev"

        # Server-side sealed scorecard refuses partial runs unless allow_missing_predictions=True,
        # and returns aggregate scorecard only (never sealed answers).
        monkeypatch.setattr(
            admin_cu_labeling,
            "_run_sealed_scorecard",
            lambda *args, **kwargs: {
                "status": "measured",
                "missing_predictions": 1,
                "fields": [],
            },
        )
        partial = client.post(
            "/api/admin/cu-labeling/score-sealed",
            json={"predictions": [], "as_of": "2026-06-15"},
        )
        assert partial.status_code == 422

        allowed = client.post(
            "/api/admin/cu-labeling/score-sealed",
            json={"predictions": [], "as_of": "2026-06-15", "allow_missing_predictions": True},
        )
        assert allowed.status_code == 200
        body = allowed.json()
        assert set(body.keys()) == {"scorecard", "agreement", "withheld_taste_fields"}
    finally:
        app.dependency_overrides.pop(get_db, None)
