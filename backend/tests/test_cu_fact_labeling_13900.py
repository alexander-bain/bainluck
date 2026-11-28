"""Tests for #13900 Content Understanding dual-rater fact labeling & agreement."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.models import CuFactLabel
from app.routes import admin_cu_labeling
from app.services import get_db, get_db_rw
from app.utils.cu_fact_labeling import (
    CLAIM_SLOTS,
    DEFAULT_DATASET_PATHS,
    DEFAULT_REPEATABILITY_PATH,
    EVENT_DATE_CANNOT_TELL,
    PRACTICE_CARD_IDS,
    build_answer_key_bundle,
    build_answer_key_rows,
    build_venue_market_link,
    compute_practice_status,
    evaluate_practice_submission,
    extract_subject_candidates,
    fact_disagreements,
    get_claim_vocabulary,
    load_practice_markets,
    load_repeatability_priority_ids,
    order_queue_markets,
    score_event_date_against_key,
    select_shared_100_ids,
    sort_outcomes_for_display,
    validate_label_submission,
    visible_labels_for_rater,
)
from app.utils.cu_frame import sanitize_cu_frame


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
    assert {slot: ok["claim_frame"][slot] for slot in CLAIM_SLOTS} == {
        "measure": "wins",
        "comparator": "none_of_these",
        "value": "50",
        "unit": "wins",
        "horizon_kind": "annual",
        "window_date": None,
    }
    assert ok["claim_frame"]["raw"]["window_date"] is None

    with pytest.raises(ValueError, match="claim_frame.measure"):
        validate_label_submission(
            _sample_label(claim_frame={"measure": "freeform_unknown_measure"})
        )


def test_agreement_and_scorecard_answer_key_matching_contract():
    rows = []
    # 5 paired markets:
    # - geography disagrees on 1/5 (m500 -> 80% exact, tiebroken to local)
    # - event_date disagrees on 1/5 (m501 -> 80% exact, left unresolved so omitted on m501)
    # - stakes differs by 1 on all 5 (100% within-1 -> scorable as [3, 4])
    # - breadth differs by 3 on 2/5 (60% < 80% -> withheld from scorecard answers with examples)
    for idx in range(5):
        mid = 500 + idx
        rows.append(
            _sample_label(
                market_id=mid,
                rater="labeler-a",
                role="primary",
                geography="us",
                event_date="2026-06-15",
                structure="neither",
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
                geography="local" if idx == 0 else "us",
                event_date=EVENT_DATE_CANNOT_TELL if idx == 1 else "2026-06-15",
                structure="neither",
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
            structure="neither",
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
    assert bundle["withheld_fields"] == ["breadth"]
    assert bundle["withheld_taste_fields"] == ["breadth"]
    assert len(bundle["withheld_examples"]["breadth"]) == 2

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

    # Unresolved fact disagreement on market 501 omits only the disputed fact field (event_date).
    m501 = by_mid[501]
    assert "event_date" not in m501["answers"]
    assert m501["answers"]["geography"] == "us"
    assert m501["answers"]["stakes"] == [3, 4]
    assert "breadth" not in m501["answers"]

    # not_sure omits entities instead of scoring [].
    assert "entities" not in by_mid[599]["answers"]
    assert by_mid[599]["answers"]["stakes"] == 2


def test_fact_field_below_80_pct_is_withheld_with_examples():
    rows = []
    for idx in range(5):
        mid = 600 + idx
        rows.append(_sample_label(market_id=mid, rater="a", role="primary", geography="us"))
        rows.append(
            _sample_label(
                market_id=mid,
                rater="b",
                role="second",
                geography="local" if idx < 2 else "us",
            )
        )
    bundle = build_answer_key_bundle({}, rows, split="sealed")
    assert "geography" in bundle["withheld_fields"]
    assert len(bundle["withheld_examples"]["geography"]) == 2
    assert all("geography" not in r["answers"] for r in bundle["rows"])


def test_claim_frame_cleaning_preserves_raw_and_six_cases():
    cases = [
        # (title, label_frame, writer_raw_frame)
        (
            "Will Team X score at least 2 goals by December 31, 2027?",
            {
                "measure": "goals",
                "comparator": "gte",
                "value": "2",
                "unit": "goals",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
            {
                "measure": "goals",
                "comparator": "gte",
                "value": "2",
                "unit": "goals",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
        ),
        (
            "Will Team X score at least 2 goals by December 31, 2027?",
            {
                "measure": "goals",
                "comparator": "gte",
                "value": "2",
                "unit": "goals",
                "horizon_kind": "multi_year",
                "window_date": "2027-12-31",
            },
            {
                "measure": "goals",
                "comparator": "gte",
                "value": "2",
                "unit": "goals",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
        ),
        (
            "Fed rate decision in June 2027?",
            {
                "measure": "interest_rate",
                "comparator": "eq",
                "value": None,
                "unit": None,
                "horizon_kind": "monthly",
                "window_date": "June 2027",
            },
            {
                "measure": "interest_rate",
                "comparator": "eq",
                "value": None,
                "unit": None,
                "horizon_kind": "monthly",
                "window_date": "June 2027",
            },
        ),
        (
            "Will Bitcoin hit $100,000 by December 31, 2027?",
            {
                "measure": "price_high",
                "comparator": "gte",
                "value": "$100,000",
                "unit": "",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
            {
                "measure": "price_high",
                "comparator": "gte",
                "value": "100000",
                "unit": "$",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
        ),
        (
            "Will Bitcoin hit $100,000 by December 31, 2027?",
            {
                "measure": "price_high",
                "comparator": "gte",
                "value": "100,000",
                "unit": "",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
            {
                "measure": "price_high",
                "comparator": "gte",
                "value": "100000",
                "unit": "$",
                "horizon_kind": "multi_year",
                "window_date": "December 31, 2027",
            },
        ),
        (
            "Will uncategorized metric X stay open in 2027?",
            {
                "measure": "none_of_these",
                "comparator": None,
                "value": None,
                "unit": None,
                "horizon_kind": None,
                "window_date": None,
            },
            None,
        ),
    ]

    label_rows = []
    markets_by_id = {}
    predictions = []
    for idx, (title, raw_frame, writer_raw) in enumerate(cases, start=1):
        mid = 7000 + idx
        sub = validate_label_submission(
            _sample_label(market_id=mid, rater="rater-a", role="primary", claim_frame=raw_frame),
            market_title=title,
        )
        # Typed text preserved in claim_frame["raw"].
        assert sub["claim_frame"]["raw"]["window_date"] == (raw_frame.get("window_date") or None)
        if idx == 4:
            assert sub["claim_frame"]["raw"]["value"] == "$100,000"
            assert sub["claim_frame"]["value"] == "100,000"
            assert sub["claim_frame"]["unit"] == "$"
        elif idx == 5:
            assert sub["claim_frame"]["raw"]["unit"] is None
            assert sub["claim_frame"]["unit"] == "$"
        elif idx == 1:
            assert sub["claim_frame"]["window_date"] == "2027-12-31"
        elif idx == 3:
            assert sub["claim_frame"]["window_date"] == "2027-06"

        sanitized_writer, drop = sanitize_cu_frame(writer_raw, title=title)
        assert drop in {None, "absent"}
        if idx < 6:
            # Verify canonical cleaned window_date and unit match writer's own cleaner.
            assert sub["claim_frame"]["window_date"] == sanitized_writer["window_date"]
            assert sub["claim_frame"]["unit"] == sanitized_writer["unit"]

        label_rows.append(sub)
        markets_by_id[mid] = {
            "market_id": mid,
            "title": title,
            "source": "kalshi",
            "category": "economics",
            "outcome_names": ["Yes", "No"],
        }
        predictions.append(
            {
                "market_id": mid,
                "profile": {
                    "entities": [{"name": "Boston Celtics", "type": "team"}],
                    "geography": "us",
                    "event_date": "2026-06-15",
                    "junk_flags": [],
                    "frame": sanitized_writer,
                    "stakes": 3,
                    "breadth": 3,
                },
            }
        )

    bundle = build_answer_key_bundle(markets_by_id, label_rows, split="sealed")
    assert bundle["unlisted_measure_count"] == 1
    by_mid = {r["market_id"]: r for r in bundle["rows"]}
    assert "frame" not in by_mid[7006]["answers"]
    assert by_mid[7006]["unlisted_measure"] is True

    # Two labelers typing "December 31, 2027" vs "2027-12-31" (and "$100,000" vs "100000" + blank unit) agree.
    assert fact_disagreements(label_rows[0], label_rows[1], market_title=cases[0][0]) == []
    assert fact_disagreements(label_rows[3], label_rows[4], market_title=cases[3][0]) == []

    # Exercise both modules end-to-end against cu_eval_scorecard (#13901) on master.
    from app.utils.cu_eval_scorecard import score_cu_eval_run

    scorecard = score_cu_eval_run(
        bundle["rows"],
        predictions,
        as_of="2026-06-15",
        dataset="sealed",
    )
    frame_row = next(f for f in scorecard["fields"] if f["field"] == "frame")
    assert frame_row["total"] == {"right": 5, "wrong": 0, "blank": 0, "said_not_known": 0, "total": 5}


def test_geography_country_picker_and_subject_chip_vs_custom_agreement():
    row_a = validate_label_submission(
        _sample_label(
            rater="a",
            role="primary",
            geography="Canada",
            subjects_answer={"selection_kind": "candidate", "selected": ["Gemini"]},
        )
    )
    row_b = validate_label_submission(
        _sample_label(
            rater="b",
            role="second",
            geography="country:CA",
            subjects_answer={"selection_kind": "custom", "selected": ["Gemini"]},
        )
    )
    assert row_a["geography_answer"] == "country:CA"
    assert row_b["geography_answer"] == "country:CA"
    assert fact_disagreements(row_a, row_b) == []

    # Scorer whole-word containment matches "Donald Trump" and "Trump", while None vs Not sure differs.
    row_c = validate_label_submission(
        _sample_label(
            rater="b",
            role="second",
            geography="country:CA",
            subjects_answer={"selection_kind": "custom", "selected": ["Gemini Inc"]},
        )
    )
    assert fact_disagreements(row_a, row_c) == []

    none_row = validate_label_submission(
        _sample_label(rater="a", role="primary", subjects_answer={"selection_kind": "none_of_these", "selected": []})
    )
    unsure_row = validate_label_submission(
        _sample_label(rater="b", role="second", subjects_answer={"selection_kind": "not_sure", "selected": []})
    )
    assert fact_disagreements(none_row, unsure_row) == ["subjects"]

    with pytest.raises(ValueError, match="geography_answer"):
        validate_label_submission(_sample_label(geography="NotARealCountryPlace"))


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

    # Strip leading question words, competition beside teams, tickers, city weather places, and generic/party chips.
    assert extract_subject_candidates({"title": "Will the St. Louis Blues make the 2026-27 NHL Playoffs?"}) == [
        "St. Louis Blues",
    ]
    assert extract_subject_candidates({"title": "Will the San Jose Sharks make the 2026-27 NHL Playoffs?"}) == [
        "San Jose Sharks",
    ]
    assert extract_subject_candidates({"title": "Will Half-Life 3 be announced before 2027?"}) == ["Half-Life 3"]
    assert extract_subject_candidates({"title": "Will the U.S. invade Iran before 2027?"}) == ["U.S.", "Iran"]
    assert extract_subject_candidates({"title": "Will Trump praise Allah again by June 30, 2027?"}) == ["Trump", "Allah"]
    assert extract_subject_candidates({"title": "Rain in Chicago in June 2027?"}) == []
    assert extract_subject_candidates({"title": "Highest temperature in Denver on July 28?"}) == []
    assert extract_subject_candidates({"title": "Amazon (AMZN) closes above ___ on July 30?"}) == ["Amazon"]
    assert extract_subject_candidates({"title": "Will Marvell (MRVL) beat quarterly earnings?"}) == ["Marvell"]
    assert extract_subject_candidates(
        {"title": "Vermont House Orleans-3 winner? (2028)", "outcome_names": ["Democratic party", "Republican party"]}
    ) == []
    assert extract_subject_candidates(
        {"title": "Moody's or S&P downgrades France by July 30, 2027?"}
    ) == ["Moody's", "S&P", "France"]
    assert extract_subject_candidates(
        {"title": "Artist with the most monthly Spotify listeners at the end of June 2027?"}
    ) == ["Spotify"]
    assert extract_subject_candidates({"title": "Best AI this month"}) == []
    micron_chips = extract_subject_candidates({"title": "Will Micron Technology, Inc. (MU) hit (HIGH) $840 in June 2027?"})
    assert micron_chips == ["Micron Technology"]
    assert "Inc" not in micron_chips

    # Unconditionally check all 500 frozen market titles on master (no silent skip).
    question_starters = {
        "will", "who", "what", "when", "where", "which", "how",
        "is", "are", "was", "were", "does", "do", "did",
        "can", "could", "would", "should", "has", "have", "had",
    }
    corporate_suffixes = {"inc", "corp", "ltd", "llc", "plc"}
    expected_counts = {"sealed": 300, "dev": 200}
    checked_total = 0
    dev_by_id: dict[int, dict] = {}
    for split_name, expected_n in expected_counts.items():
        path = DEFAULT_DATASET_PATHS[split_name]
        assert path.exists(), f"Missing frozen {split_name} dataset at {path}"
        markets = json.loads(path.read_text(encoding="utf-8"))["markets"]
        assert len(markets) == expected_n
        checked_total += len(markets)
        for market in markets:
            if split_name == "dev":
                dev_by_id[int(market["market_id"])] = market
            for chip in extract_subject_candidates(market):
                assert chip.split()[0].lower() not in question_starters, (split_name, market["title"], chip)
                assert chip.rstrip(".").lower() not in corporate_suffixes, (split_name, market["title"], chip)
    assert checked_total == 500
    assert extract_subject_candidates(dev_by_id[72559511]) == []
    assert extract_subject_candidates(dev_by_id[63119270]) == ["San Jose Sharks"]
    assert extract_subject_candidates(dev_by_id[70136122]) == []
    assert extract_subject_candidates(dev_by_id[65059801]) == ["Moody's", "S&P", "France"]


def test_dev_shared_100_ids_checked_in_and_valid():
    assert DEFAULT_REPEATABILITY_PATH.exists()
    assert DEFAULT_DATASET_PATHS["sealed"].exists()
    assert DEFAULT_DATASET_PATHS["dev"].exists()
    ids = load_repeatability_priority_ids()
    assert len(ids) == 100
    assert len(set(ids)) == 100
    dev_path = DEFAULT_DATASET_PATHS["dev"]
    dev_ids = {int(m["market_id"]) for m in json.loads(dev_path.read_text(encoding="utf-8"))["markets"]}
    assert set(ids).issubset(dev_ids)


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
    # Keep field-wide dual-rater geography agreement >= 80% so geography is not withheld.
    for mid in (43, 44, 45, 46):
        rows.append(_sample_label(market_id=mid, rater="a", role="primary", geography="us"))
        rows.append(_sample_label(market_id=mid, rater="b", role="second", geography="us"))

    markets_by_id = {
        mid: {"market_id": mid, "source": "kalshi", "category": "politics", "outcome_names": ["Yes", "No"]}
        for mid in (42, 43, 44, 45, 46)
    }
    exported = build_answer_key_rows(
        markets_by_id,
        rows,
        split="sealed",
    )
    m42 = next(r for r in exported if r["market_id"] == 42)
    assert m42["resolution_source"] == "tiebreak"
    assert m42["answers"]["geography"] == "local"


def test_migration_router_and_sealed_protection(monkeypatch, caplog):
    assert CuFactLabel.__tablename__ == "cu_fact_labels"
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "cu_fact_labels_13900.py"
    )
    text = mig_path.read_text(encoding="utf-8")
    assert 'revision = "cu_fact_labels_13900"' in text
    assert 'down_revision = "poll_open_outcomes_13673"' in text
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

        # Queue announces missing frozen dataset file and sealed lock status.
        q_resp = client.get("/api/admin/cu-labeling/queue", params={"rater": "tester"})
        assert q_resp.status_code == 200
        q_body = q_resp.json()
        assert q_body["dataset_file_present"] is False
        assert "not loaded" in q_body["dataset_file_missing_message"]
        assert q_body["sealed_locked"] is True
        assert q_body["practice_status"]["required"] == 5
        assert "wins" in q_body["claim_vocabulary"]["measures"]

        # Sealed & practice exports are forbidden so only dev exports leave the server.
        sealed_export = client.get("/api/admin/cu-labeling/export-answer-key", params={"split": "sealed"})
        assert sealed_export.status_code == 403
        practice_export = client.get("/api/admin/cu-labeling/export-answer-key", params={"split": "practice"})
        assert practice_export.status_code == 403

        # Dev export remains permitted.
        dev_export = client.get("/api/admin/cu-labeling/export-answer-key", params={"split": "dev"})
        assert dev_export.status_code == 200
        assert dev_export.json()["dataset"] == "dev"

        # With zero resolved sealed labels, return a plain "no_labels_yet" status (not measured),
        # and strip newlines from logged request identifiers.
        with caplog.at_level(logging.INFO):
            empty_sealed = client.post(
                "/api/admin/cu-labeling/score-sealed",
                json={
                    "predictions": [],
                    "as_of": "2026-06-15",
                    "run_id": "run-empty\nFORGED",
                    "writer_rev": 10,
                },
            )
        assert empty_sealed.status_code == 200
        assert empty_sealed.json()["status"] == "no_labels_yet"
        assert empty_sealed.json()["scorecard"] is None
        assert "cu_sealed_scorecard_call run_id=run-emptyFORGED writer_rev=10 market_count=0" in caplog.text

        # When sealed labels exist, partial predictions unconditionally fail closed with 422,
        # and full predictions succeed with structured response + audit log line.
        monkeypatch.setattr(
            admin_cu_labeling,
            "_db_rows_for_split",
            AsyncMock(return_value=[_sample_label(market_id=888, rater="a", role="primary")]),
        )
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
            json={
                "predictions": [],
                "as_of": "2026-06-15",
                "allow_missing_predictions": True,
                "run_id": "run-partial",
                "writer_rev": 10,
            },
        )
        assert partial.status_code == 422

        monkeypatch.setattr(
            admin_cu_labeling,
            "_run_sealed_scorecard",
            lambda *args, **kwargs: {
                "status": "measured",
                "missing_predictions": 0,
                "fields": [],
            },
        )
        with caplog.at_level(logging.INFO):
            full_ok = client.post(
                "/api/admin/cu-labeling/score-sealed",
                json={
                    "predictions": [{"market_id": 888, "profile": {}}],
                    "as_of": "2026-06-15",
                    "run_id": "run-full",
                    "writer_rev": 10,
                },
            )
        assert full_ok.status_code == 200
        body = full_ok.json()
        assert body["status"] == "measured"
        assert set(body.keys()) == {
            "status",
            "scorecard",
            "agreement",
            "withheld_fields",
            "withheld_taste_fields",
            "withheld_examples",
            "unlisted_measure_count",
        }
        assert "cu_sealed_scorecard_call run_id=run-full writer_rev=10 market_count=1" in caplog.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_live_datasets_and_real_score_sealed_route(monkeypatch):
    async def _fake_db():
        yield AsyncMock()

    monkeypatch.setattr(admin_cu_labeling, "_check_admin_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr(admin_cu_labeling, "_db_rows_for_split", AsyncMock(return_value=[]))
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)

        # Dev queue loads real cu_dev_200_v1.json and surfaces shared-100 markets first.
        dev_shared = client.get("/api/admin/cu-labeling/queue", params={"split": "dev", "scope": "shared_100", "rater": "tester"})
        assert dev_shared.status_code == 200
        shared_body = dev_shared.json()
        assert shared_body["total_in_scope"] == 100
        shared_ids = set(load_repeatability_priority_ids())
        assert {item["market_id"] for item in shared_body["items"]} == shared_ids

        dev_q = client.get("/api/admin/cu-labeling/queue", params={"split": "dev", "scope": "all", "rater": "tester"})
        assert dev_q.status_code == 200
        dev_body = dev_q.json()
        assert dev_body["dataset_file_present"] is True
        assert dev_body["dataset_file_missing_message"] is None
        assert dev_body["total_in_scope"] == 200
        assert dev_body["items"][0]["market_id"] in shared_ids

        # Practice round loads 5 curated dev cards in order and locks sealed until completed.
        practice_q = client.get("/api/admin/cu-labeling/queue", params={"split": "practice", "rater": "tester"})
        assert practice_q.status_code == 200
        practice_body = practice_q.json()
        assert [item["market_id"] for item in practice_body["items"]] == list(PRACTICE_CARD_IDS)
        assert practice_body["practice_status"]["completed"] == 0
        assert practice_body["practice_status"]["unlocked_sealed"] is False
        assert all(item["venue_url"] and item["venue_link_label"] for item in practice_body["items"])

        # Sealed queue is locked until tester finishes all 5 practice cards.
        sealed_locked = client.get("/api/admin/cu-labeling/queue", params={"split": "sealed", "scope": "all", "rater": "tester"})
        assert sealed_locked.status_code == 200
        locked_body = sealed_locked.json()
        assert locked_body["sealed_locked"] is True
        assert locked_body["items"] == []

        # After saving all 5 practice cards for tester, sealed unlocks cleanly.
        completed_practice_rows = [
            _sample_label(dataset_split="practice", market_id=mid, rater="tester", role="primary")
            for mid in PRACTICE_CARD_IDS
        ]
        monkeypatch.setattr(
            admin_cu_labeling,
            "_db_rows_for_split",
            AsyncMock(side_effect=lambda _db, split: completed_practice_rows if split == "practice" else []),
        )
        sealed_q = client.get("/api/admin/cu-labeling/queue", params={"split": "sealed", "scope": "all", "rater": "tester"})
        assert sealed_q.status_code == 200
        sealed_body = sealed_q.json()
        assert sealed_body["dataset_file_present"] is True
        assert sealed_body["sealed_locked"] is False
        assert sealed_body["total_in_scope"] == 300
        first_sealed_id = int(sealed_body["items"][0]["market_id"])
        assert sealed_body["items"][0]["venue_url"].startswith("https://")
        assert sealed_body["items"][0]["venue_link_label"]

        # Another rater remains locked until they finish their own 5 practice cards.
        other_locked = client.get("/api/admin/cu-labeling/queue", params={"split": "sealed", "scope": "all", "rater": "other-person"})
        assert other_locked.status_code == 200
        assert other_locked.json()["sealed_locked"] is True
        assert other_locked.json()["items"] == []

        # Real cu_eval_scorecard + zero sealed labels returns HTTP 200 no_labels_yet (not 503).
        no_labels = client.post(
            "/api/admin/cu-labeling/score-sealed",
            json={"predictions": [], "as_of": "2026-06-15", "run_id": "run-empty", "writer_rev": 10},
        )
        assert no_labels.status_code == 200
        assert no_labels.json()["status"] == "no_labels_yet"
        assert no_labels.json()["scorecard"] is None

        # Real cu_eval_scorecard + one sealed label runs end-to-end without mocks on _run_sealed_scorecard.
        monkeypatch.setattr(
            admin_cu_labeling,
            "_db_rows_for_split",
            AsyncMock(return_value=[_sample_label(market_id=first_sealed_id, rater="a", role="primary")]),
        )
        pred = {
            "market_id": first_sealed_id,
            "profile": {
                "entities": ["Donald Trump"],
                "event_date": "2026-06-15",
                "geography": "us",
                "junk_flags": [],
                "frame": None,
                "stakes": 4,
                "breadth": 5,
            },
        }
        measured = client.post(
            "/api/admin/cu-labeling/score-sealed",
            json={
                "predictions": [pred],
                "as_of": "2026-06-15",
                "run_id": "run-real-1",
                "writer_rev": 10,
                "model": "gpt-4o-mini",
            },
        )
        assert measured.status_code == 200
        m_body = measured.json()
        assert m_body["status"] == "measured"
        assert m_body["scorecard"]["status"] == "measured"
        assert m_body["scorecard"]["dataset"] == "sealed"
        assert m_body["scorecard"]["market_count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_cannot_tell_event_date_validation_agreement_tiebreak_and_scorecard():
    # Reject mixing no_single_day=True and event_date_answer="cannot_tell", and reject empty date.
    with pytest.raises(ValueError, match="Cannot choose both"):
        validate_label_submission(
            _sample_label(event_date=EVENT_DATE_CANNOT_TELL, no_single_day=True)
        )
    with pytest.raises(ValueError, match="event_date_answer is required"):
        validate_label_submission(_sample_label(event_date=None, no_single_day=False))

    sub_a = validate_label_submission(
        _sample_label(market_id=901, rater="a", role="primary", event_date=EVENT_DATE_CANNOT_TELL, no_single_day=False)
    )
    sub_b = validate_label_submission(
        _sample_label(market_id=901, rater="b", role="second", event_date=EVENT_DATE_CANNOT_TELL, no_single_day=False)
    )
    sub_nsd = validate_label_submission(
        _sample_label(market_id=902, rater="b", role="second", event_date=None, no_single_day=True)
    )
    assert sub_a["event_date_answer"] == EVENT_DATE_CANNOT_TELL
    assert sub_a["no_single_day"] is False

    # Two raters both choosing cannot_tell agree; cannot_tell vs no_single_day disagrees.
    assert fact_disagreements(sub_a, sub_b) == []
    assert fact_disagreements(sub_a, sub_nsd) == ["event_date"]

    # Resolved cannot_tell stays in the key as "cannot_tell" so a writer stating a specific day is scored wrong.
    bundle = build_answer_key_bundle({}, [sub_a, sub_b], split="sealed")
    assert bundle["cannot_tell_event_date_count"] == 1
    assert len(bundle["rows"]) == 1
    assert bundle["rows"][0]["answers"]["event_date"] == EVENT_DATE_CANNOT_TELL
    assert score_event_date_against_key(EVENT_DATE_CANNOT_TELL, "2026-06-15") is False
    assert score_event_date_against_key(EVENT_DATE_CANNOT_TELL, None) is True
    assert score_event_date_against_key(EVENT_DATE_CANNOT_TELL, EVENT_DATE_CANNOT_TELL) is True
    assert score_event_date_against_key(None, None) is True
    assert score_event_date_against_key(None, "2026-06-15") is False
    assert score_event_date_against_key("2028-11-07", "2028-11-07") is True
    assert score_event_date_against_key("2028-11-07", "2029-05-07") is False


def test_sort_outcomes_for_display_numeric_buckets_thresholds_and_years():
    assert sort_outcomes_for_display(
        ["60°F or higher", "52-53°F", "48-49°F", "41°F or below", "42-43°F"]
    ) == ["41°F or below", "42-43°F", "48-49°F", "52-53°F", "60°F or higher"]
    assert sort_outcomes_for_display(
        ["1", "2", "3 to 9", "10 to 24", "Above 249", "25 to 99", "0", "100 to 249"]
    ) == ["0", "1", "2", "3 to 9", "10 to 24", "25 to 99", "100 to 249", "Above 249"]
    assert sort_outcomes_for_display(
        ["Above 13100", "Above 13000", "Above 13200"]
    ) == ["Above 13000", "Above 13100", "Above 13200"]
    assert sort_outcomes_for_display(
        ["Before 2030", "Before 2028", "Before 2027", "Before 2029"]
    ) == ["Before 2027", "Before 2028", "Before 2029", "Before 2030"]
    assert sort_outcomes_for_display(["Yes", "No"]) == ["Yes", "No"]


def test_optional_structure_and_claim_frame_omitted_from_card_submission():
    sub = validate_label_submission(
        {
            "dataset_split": "sealed",
            "market_id": 777,
            "rater": "Grader One",
            "role": "primary",
            "subjects_answer": {"selection_kind": "candidate", "selected": ["Boston Celtics"]},
            "event_date_answer": "2026-06-15",
            "no_single_day": False,
            "geography_answer": "us",
            "stakes": 2,
            "breadth": 3,
        }
    )
    assert sub["structure_answer"] is None
    assert sub["claim_frame"] is None

    bundle = build_answer_key_bundle({}, [sub], split="sealed")
    answers = bundle["rows"][0]["answers"]
    assert "junk_flags" not in answers
    assert "frame" not in answers
    assert answers["event_date"] == "2026-06-15"
    assert answers["geography"] == "us"


def test_venue_market_link_variants_and_practice_round_feedback():
    kalshi = build_venue_market_link(
        {"market_id": 56862751, "source": "kalshi", "external_id": "KXCHINABIRTHLIMITS-26JUL08", "title": "Will China abolish birth limits?"}
    )
    assert kalshi == {
        "venue_url": "https://kalshi.com/markets/kxchinabirthlimits",
        "venue_link_label": "Open on Kalshi",
    }

    pm_slug = build_venue_market_link(
        {"market_id": 71609185, "source": "polymarket", "external_id": "1434884", "title": "Will Marvell (MRVL) beat quarterly earnings?"},
        {"market_metadata": {"polymarket_event_slug": "will-marvell-beat-quarterly-earnings"}},
    )
    assert pm_slug == {
        "venue_url": "https://polymarket.com/event/will-marvell-beat-quarterly-earnings",
        "venue_link_label": "Open on Polymarket",
    }

    pm_search = build_venue_market_link(
        {"market_id": 71609185, "source": "polymarket", "external_id": "1434884", "title": "Will Marvell (MRVL) beat quarterly earnings?"}
    )
    assert pm_search["venue_url"].startswith("https://polymarket.com/markets?_q=")
    assert pm_search["venue_link_label"] == "Find on Polymarket"

    odds = build_venue_market_link({"market_id": 99999, "source": "odds_api", "title": "NASCAR cup"})
    assert odds == {"venue_url": "https://bainluck.com/futures/99999", "venue_link_label": "Open on Bain Luck"}

    practice_markets = load_practice_markets()
    assert [m["market_id"] for m in practice_markets] == list(PRACTICE_CARD_IDS)

    feedback_ok = evaluate_practice_submission(
        71609185,
        {
            "subjects_answer": {"selection_kind": "candidate", "selected": ["Marvell"]},
            "event_date_answer": EVENT_DATE_CANNOT_TELL,
            "no_single_day": False,
            "geography_answer": "us",
        },
    )
    assert feedback_ok is not None
    assert feedback_ok["all_facts_matched"] is True
    assert compute_practice_status(
        [
            {"dataset_split": "practice", "market_id": mid, "rater": "  Alice  "}
            for mid in PRACTICE_CARD_IDS[:3]
        ],
        "alice",
    )["completed"] == 3


def test_post_label_sealed_403_until_practice_complete_and_practice_returns_feedback(monkeypatch):
    class _ScalarRes:
        def __init__(self, val):
            self._val = val

        def scalar_one_or_none(self):
            return self._val

        def scalar_one(self):
            return self._val

        def scalars(self):
            return self

        def all(self):
            return []

    class _PracticeDb:
        async def execute(self, stmt, *args, **kwargs):
            text_sql = str(stmt)
            if "INSERT INTO cu_fact_labels" in text_sql.upper() or ("cu_fact_labels" in text_sql and "VALUES" in text_sql):
                row = CuFactLabel(
                    id=1,
                    dataset_split="practice",
                    market_id=70733228,
                    rater="Alice",
                    role="primary",
                    subjects_answer={"selection_kind": "candidate", "selected": ["Israel", "Iran"]},
                    event_date_answer=None,
                    no_single_day=True,
                    geography_answer="global",
                    structure_answer=None,
                    claim_frame=None,
                    stakes=4,
                    breadth=4,
                    evidence_note=None,
                )
                return _ScalarRes(row)
            return _ScalarRes("Practice Market Title")

        async def commit(self):
            return None

    async def _fake_rw():
        yield _PracticeDb()

    monkeypatch.setattr(admin_cu_labeling, "_check_admin_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr(admin_cu_labeling, "_db_rows_for_split", AsyncMock(return_value=[]))
    app.dependency_overrides[get_db_rw] = _fake_rw
    try:
        client = TestClient(app)

        blocked = client.post(
            "/api/admin/cu-labeling/label",
            json={
                "dataset_split": "sealed",
                "market_id": 68851041,
                "rater": "Alice",
                "role": "primary",
                "subjects_answer": {"selection_kind": "candidate", "selected": ["Trump"]},
                "event_date_answer": None,
                "no_single_day": True,
                "geography_answer": "us",
                "stakes": 3,
                "breadth": 4,
            },
        )
        assert blocked.status_code == 403
        assert "5 practice cards" in blocked.json()["detail"]

        monkeypatch.setattr(
            admin_cu_labeling,
            "_db_rows_for_split",
            AsyncMock(
                return_value=[
                    _sample_label(dataset_split="practice", market_id=70733228, rater="Alice", role="primary")
                ]
            ),
        )
        saved = client.post(
            "/api/admin/cu-labeling/label",
            json={
                "dataset_split": "practice",
                "market_id": 70733228,
                "rater": "Alice",
                "role": "primary",
                "subjects_answer": {"selection_kind": "candidate", "selected": ["Israel", "Iran"]},
                "event_date_answer": None,
                "no_single_day": True,
                "geography_answer": "global",
                "stakes": 4,
                "breadth": 4,
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["saved"] is True
        assert body["practice_feedback"]["all_facts_matched"] is True
        assert body["practice_status"]["completed"] == 1
        assert body["practice_status"]["unlocked_sealed"] is False
    finally:
        app.dependency_overrides.pop(get_db_rw, None)
