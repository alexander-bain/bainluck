"""Unit and CLI tests for the CU evaluation scorecard (#13901)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.utils.cu_eval_scorecard import (
    CU_SCORECARD_FIELDS,
    build_unlabeled_scorecard,
    format_scorecard_table,
    score_cu_eval_run,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _sample_answers() -> list[dict]:
    return [
        {
            "market_id": 101,
            "source": "kalshi",
            "category": "politics",
            "outcome_names": ["Yes", "No"],
            "readers_see": True,
            "answers": {
                "topic": "politics",
                "geography": "local",
                "temporal_class": "event_tied",
                "event_date": "2028-11-07",
                "stakes": 1,
                "breadth": 1,
                "junk_flags": [],
                "liveness": "active",
                "subject_ref": "entity:12",
            },
        },
        {
            "market_id": 102,
            "source": "polymarket",
            "category": "economics",
            "outcome_names": ["Above 100", "Above 200", "Above 300"],
            "readers_see": False,
            "answers": {
                "topic": "economics",
                "geography": "global",
                "temporal_class": "deadline",
                "event_date": None,
                "stakes": 3,
                "breadth": 4,
                "junk_flags": ["ladder"],
                "liveness": "unknown",
                "subject_ref": "team:9",
            },
        },
    ]


def _sample_predictions() -> list[dict]:
    return [
        {
            "market_id": 101,
            "field_deciders": {
                "geography": "code",
                "event_date": "code",
                "stakes": "code",
                "breadth": "code",
            },
            "profile": {
                "topic": "politics",
                "geography": "local",
                "temporal_class": "deadline",  # wrong
                "event_date": "2028-11-07",
                "stakes": 1,
                "breadth": None,  # blank
                "junk_flags": [],
                "liveness": "active",
                "subject_ref": "entity:12",
            },
        },
        {
            "market_id": 102,
            "field_deciders": {
                "junk_flags": "code",
            },
            "profile": {
                "topic": "unknown",  # said_not_known
                "geography": "global",
                "temporal_class": "deadline",
                "event_date": None,  # matching null is right
                "stakes": 3,
                "breadth": 4,
                "junk_flags": ["ladder"],
                "liveness": "unknown",  # matching expected unknown is right
                "subject_ref": "unresolved:fed reserve",  # said_not_known
            },
        },
    ]


def test_scorecard_counts_right_wrong_blank_idk_and_code_vs_model_columns():
    result = score_cu_eval_run(
        _sample_answers(),
        _sample_predictions(),
        as_of="2026-06-15",
        writer_rev=10,
        model="gpt-4o-mini",
        dataset="sealed",
        cost={"total_usd": 0.14},
    )
    assert result["status"] == "measured"
    assert result["market_count"] == 2
    assert result["cost"]["total_usd"] == 0.14
    assert result["cost"]["per_market_usd"] == 0.07

    by_field = {row["field"]: row for row in result["fields"]}
    assert by_field["topic"]["model"] == {
        "right": 1, "wrong": 0, "blank": 0, "said_not_known": 1, "total": 2,
    }
    assert by_field["temporal_class"]["model"] == {
        "right": 1, "wrong": 1, "blank": 0, "said_not_known": 0, "total": 2,
    }
    assert by_field["breadth"]["decided_by"] == "code_and_model"
    assert by_field["breadth"]["code"] == {
        "right": 0, "wrong": 0, "blank": 1, "said_not_known": 0, "total": 1,
    }
    assert by_field["breadth"]["model"] == {
        "right": 1, "wrong": 0, "blank": 0, "said_not_known": 0, "total": 1,
    }
    assert by_field["event_date"]["code"]["right"] == 1
    assert by_field["event_date"]["model"]["right"] == 1
    assert by_field["liveness"]["decided_by"] == "code"
    assert by_field["liveness"]["code"]["right"] == 2
    assert by_field["subject_ref"]["decided_by"] == "code"
    assert by_field["subject_ref"]["code"] == {
        "right": 1, "wrong": 0, "blank": 0, "said_not_known": 1, "total": 2,
    }

    table = format_scorecard_table(result)
    assert "Code R/W/B/IDK" in table
    assert "Model R/W/B/IDK" in table
    assert "$0.1400 total" in table


def test_scorecard_produces_all_four_required_slices():
    result = score_cu_eval_run(
        _sample_answers(),
        _sample_predictions(),
        as_of="2026-06-15",
        writer_rev=10,
        model="gpt-4o-mini",
    )
    assert set(result["slices"].keys()) == {
        "by_venue", "by_category", "by_market_shape", "by_exposure",
    }
    assert set(result["slices"]["by_venue"].keys()) == {"kalshi", "polymarket"}
    assert set(result["slices"]["by_category"].keys()) == {"economics", "politics"}
    assert set(result["slices"]["by_market_shape"].keys()) == {"binary", "ladder"}
    assert set(result["slices"]["by_exposure"].keys()) == {"readers_see", "rest"}
    assert result["slices"]["by_exposure"]["readers_see"]["market_count"] == 1
    assert result["slices"]["by_exposure"]["rest"]["market_count"] == 1


def test_unlabeled_builder_and_cli_round_trip(tmp_path):
    unlabeled = build_unlabeled_scorecard(as_of="2026-06-01")
    assert unlabeled["status"] == "not_measured_yet"
    assert unlabeled["as_of"] == "2026-06-01"
    assert len(unlabeled["fields"]) == len(CU_SCORECARD_FIELDS)

    ans_file = tmp_path / "answers.json"
    pred_file = tmp_path / "predictions.json"
    out_file = tmp_path / "scorecard.json"
    unmeasured_out = tmp_path / "unmeasured.json"
    ans_file.write_text(json.dumps({"rows": _sample_answers()}), encoding="utf-8")
    pred_file.write_text(
        json.dumps({"writer_rev": 10, "model": "gpt-4o-mini", "actual_usd": 0.14, "rows": _sample_predictions()}),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/score_cu_eval.py",
            "--answers",
            str(ans_file),
            "--predictions",
            str(pred_file),
            "--date",
            "2026-06-15",
            "--out",
            str(out_file),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["status"] == "measured"
    assert written["writer_rev"] == 10
    assert written["cost"]["total_usd"] == 0.14

    unmeasured_proc = subprocess.run(
        [
            sys.executable,
            "scripts/score_cu_eval.py",
            "--not-measured-yet",
            "--date",
            "2026-06-01",
            "--out",
            str(unmeasured_out),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert unmeasured_proc.returncode == 0, unmeasured_proc.stderr
    unmeasured = json.loads(unmeasured_out.read_text(encoding="utf-8"))
    assert unmeasured["status"] == "not_measured_yet"
    assert unmeasured["as_of"] == "2026-06-01"
    assert [f["field"] for f in unmeasured["fields"]] == [s.key for s in CU_SCORECARD_FIELDS]
    by_unmeasured = {f["field"]: f["decided_by"] for f in unmeasured["fields"]}
    for shared_field in ("geography", "event_date", "stakes", "breadth", "junk_flags"):
        assert by_unmeasured[shared_field] == "code_and_model"


def test_cli_refuses_missing_predictions_by_default_and_prints_count(tmp_path):
    answers = _sample_answers()
    preds = [_sample_predictions()[0]]  # Market 102 missing

    ans_file = tmp_path / "answers.json"
    pred_file = tmp_path / "predictions.json"
    out_file = tmp_path / "scorecard.json"
    ans_file.write_text(json.dumps({"rows": answers}), encoding="utf-8")
    pred_file.write_text(json.dumps({"rows": preds}), encoding="utf-8")

    refused = subprocess.run(
        [
            sys.executable,
            "scripts/score_cu_eval.py",
            "--answers",
            str(ans_file),
            "--predictions",
            str(pred_file),
            "--date",
            "2026-06-15",
            "--out",
            str(out_file),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert refused.returncode == 2
    assert "missing_predictions=1" in refused.stdout
    assert "Refusing to write scorecard: 1 answer-key market(s) have no prediction" in refused.stderr
    assert not out_file.exists()

    allowed = subprocess.run(
        [
            sys.executable,
            "scripts/score_cu_eval.py",
            "--answers",
            str(ans_file),
            "--predictions",
            str(pred_file),
            "--date",
            "2026-06-15",
            "--allow-missing-predictions",
            "--out",
            str(out_file),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert allowed.returncode == 0, allowed.stderr
    assert "missing_predictions=1" in allowed.stdout
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["missing_predictions"] == 1


def test_input_only_slices_and_recomputed_cu_event_facts_decider():
    # Neither field_deciders nor precomputed event_facts is present on this state house race,
    # and the prediction falsely claims junk_flags=["ladder"] on a binary ["Yes", "No"] market.
    answers = [
        {
            "market_id": 70136122,
            "source": "kalshi",
            "category": "politics",
            "title": "Vermont House Orleans-3 winner? (2028)",
            "outcome_names": ["Yes", "No"],
            "readers_see": True,
            "answers": {
                "geography": "local",
                "event_date": "2028-11-07",
                "stakes": 1,
                "breadth": 1,
                "junk_flags": [],
            },
        }
    ]
    preds = [
        {
            "market_id": 70136122,
            "profile": {
                "geography": "local",
                "event_date": "2028-11-07",
                "stakes": 1,
                "breadth": 1,
                "junk_flags": ["ladder"],
            },
        }
    ]
    result = score_cu_eval_run(answers, preds, as_of="2026-06-15", dataset="sealed")
    by_field = {row["field"]: row for row in result["fields"]}
    for code_fact_field in ("geography", "event_date", "stakes", "breadth"):
        assert by_field[code_fact_field]["decided_by"] == "code"
        assert by_field[code_fact_field]["code"]["right"] == 1
        assert by_field[code_fact_field]["model"]["total"] == 0

    # Market shape slice ignores prediction junk_flags=["ladder"] and classifies binary by inputs.
    assert set(result["slices"]["by_market_shape"].keys()) == {"binary"}


def test_matching_rules_for_entities_junk_flags_frame_and_taste_tolerance():
    answers = [
        {
            "market_id": 2001,
            "market_meta": {
                "source": "kalshi",
                "category": "sports",
                "outcome_names": ["Above 7,000", "Above 8,000"],
                "draw_bucket": "reader_weighted",
            },
            "answers": {
                "entities": ["Bill Belichick"],
                "junk_flags": ["ladder"],
                "frame": {
                    "measure": "wins",
                    "comparator": "gte",
                    "value": "7000",
                    "unit": "wins",
                    "horizon_kind": "annual",
                    "window_date": "2026-06-15",
                },
                "stakes": 2,
                "breadth": [2, 4],
            },
        },
        {
            "market_id": 2002,
            "market_meta": {
                "source": "polymarket",
                "category": "economics",
                "outcome_names": ["Yes", "No"],
                "draw_bucket": "roster_spread",
            },
            "answers": {
                "entities": [],
                "junk_flags": [],
                "stakes": 3,
                "breadth": [1, 2],
            },
        },
        {
            "market_id": 2003,
            "market_meta": {
                "source": "polymarket",
                "category": "tech",
                "outcome_names": ["Yes", "No"],
                "draw_bucket": "roster_spread",
            },
            "answers": {
                "entities": ["AI"],
                "junk_flags": ["ladder"],
            },
        },
    ]
    preds = [
        {
            "market_id": 2001,
            "profile": {
                # Ignores type ("person"), whole-word containment matches "Bill Belichick",
                # and counts "UNC" as an extra writer-only name without marking wrong.
                "entities": [
                    {"name": "belichick", "type": "person"},
                    {"name": "UNC", "type": "org"},
                ],
                # Extra unasked flag duplicate_phrasing does not fail a ladder/dated_bucket/neither label.
                "junk_flags": ["ladder", "duplicate_phrasing"],
                # Comma in thousands value matches canonical 7000.
                "frame": {
                    "measure": "wins",
                    "comparator": "gte",
                    "value": "7,000",
                    "unit": "wins",
                    "horizon_kind": "annual",
                    "window_date": "2026-06-15",
                },
                "stakes": 3,  # within +-1 of 2 -> right
                "breadth": 5,  # within +-1 of [2, 4] -> right
            },
        },
        {
            "market_id": 2002,
            "profile": {
                "entities": [],  # right on none_of_these
                "junk_flags": ["duplicate_phrasing"],  # ignored unasked flag on neither -> right
                "stakes": 5,  # outside +-1 of 3 -> wrong
                "breadth": 4,  # outside +-1 of [1, 2] -> wrong
            },
        },
        {
            "market_id": 2003,
            "profile": {
                # Whole-word check prevents "AI" matching inside "Bain".
                "entities": [{"name": "Bain", "type": "org"}],
                # Missing ladder flag (writer said neither []) -> wrong.
                "junk_flags": [],
            },
        },
    ]

    result = score_cu_eval_run(
        answers,
        preds,
        as_of="2026-06-15",
        dataset="sealed",
        withheld_fields=["oddity"],
    )
    assert result["withheld_fields"] == ["oddity"]
    by_field = {row["field"]: row for row in result["fields"]}
    assert by_field["entities"]["total"]["right"] == 2
    assert by_field["entities"]["total"]["wrong"] == 1
    assert by_field["entities"]["extra_names"] == 2  # "UNC" on 2001 + unmatched "Bain" on 2003
    assert by_field["junk_flags"]["total"]["right"] == 2
    assert by_field["junk_flags"]["total"]["wrong"] == 1
    assert by_field["frame"]["total"]["right"] == 1
    assert by_field["stakes"]["total"]["right"] == 1
    assert by_field["stakes"]["total"]["wrong"] == 1
    assert by_field["breadth"]["total"]["right"] == 1
    assert by_field["breadth"]["total"]["wrong"] == 1

    # Slices pull source, category, and draw_bucket=reader_weighted from market_meta.
    assert set(result["slices"]["by_venue"].keys()) == {"kalshi", "polymarket"}
    assert set(result["slices"]["by_category"].keys()) == {"economics", "sports", "tech"}
    assert result["slices"]["by_exposure"]["readers_see"]["market_count"] == 1
    assert result["slices"]["by_exposure"]["rest"]["market_count"] == 2

    table = format_scorecard_table(result)
    assert "Extra writer-only entity names (not counted wrong): 2" in table
    assert "Withheld taste fields (<80% agreement): oddity" in table
