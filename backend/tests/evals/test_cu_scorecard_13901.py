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
