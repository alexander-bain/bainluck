"""Temporal cutoff + claim envelope for the interestingness fitter (Queue 308).

Convention, matching the C216 oracle: ``labeled_at < cutoff`` is train,
``>= cutoff`` is holdout — the exact cutoff belongs to the holdout.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.discover_label_eval_runs import build_holdout_readiness
from scripts.evals.calibrate_interestingness import (
    build_envelope,
    label_observation_time,
    partition_rows,
)
from scripts.export_discover_labeled_dataset import build_labeled_dataset_statement

CUTOFF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _row(day: int, label: str = "love", **extra):
    return {
        "id": f"futures:{day}",
        "label": label,
        "labeled_at": f"2026-06-{day:02d}T12:00:00+00:00",
        **extra,
    }


# ---------------------------------------------------------------- partitioning


def test_cutoff_boundary_is_inclusive_to_holdout():
    rows = [
        {"id": "before", "labeled_at": "2026-05-31T23:59:59+00:00"},
        {"id": "exact", "labeled_at": "2026-06-01T00:00:00+00:00"},
        {"id": "after", "labeled_at": "2026-06-02T00:00:00+00:00"},
    ]
    train, holdout, dropped, _ = partition_rows(rows, CUTOFF)

    assert [r["id"] for r in train] == ["before"]
    assert [r["id"] for r in holdout] == ["exact", "after"], "the exact cutoff belongs to holdout"
    assert dropped == 0


def test_missing_timestamp_is_dropped_never_defaulted_into_train():
    rows = [
        {"id": "ok", "labeled_at": "2026-05-01T00:00:00+00:00"},
        {"id": "missing"},
        {"id": "garbage", "labeled_at": "not-a-date"},
    ]
    train, holdout, dropped, _ = partition_rows(rows, CUTOFF)

    assert [r["id"] for r in train] == ["ok"]
    assert holdout == []
    assert dropped == 2, "unparseable label times must be counted, not silently trained on"


def test_label_time_authority_prefers_labeled_at_then_created_at_then_timestamp():
    assert label_observation_time({"labeled_at": "2026-06-01T00:00:00+00:00"})[1] == "labeled_at"
    assert label_observation_time({"created_at": "2026-06-01T00:00:00+00:00"})[1] == "created_at"
    assert label_observation_time({"timestamp": "2026-06-01T00:00:00+00:00"})[1] == "timestamp"
    assert label_observation_time({})[0] is None


# ------------------------------------------------------------------- envelope


def _mixed_corpus(n_train: int = 30, n_holdout: int = 30):
    """Both partitions two-class and comfortably over the top-k floor."""
    rows = []
    for i in range(n_train):
        rows.append(
            {
                "id": f"train:{i}",
                "label": "love" if i % 2 else "kill",
                "labeled_at": f"2026-05-{(i % 28) + 1:02d}T12:00:00+00:00",
            }
        )
    for i in range(n_holdout):
        rows.append(
            {
                "id": f"hold:{i}",
                "label": "love" if i % 2 else "kill",
                "labeled_at": f"2026-06-{(i % 28) + 1:02d}T12:00:00+00:00",
            }
        )
    return rows


def test_envelope_carries_every_provenance_field():
    env = build_envelope(_mixed_corpus(), cutoff=CUTOFF, label_column="label", top_n=20)

    for key in (
        "cutoff",
        "train",
        "holdout",
        "dropped_no_timestamp",
        "label_policy",
        "baseline_p_at_k",
        "candidate_p_at_k",
        "delta_points",
        "verdict",
    ):
        assert key in env, f"envelope missing {key}"

    assert env["train"]["size"] == 30
    assert env["holdout"]["size"] == 30
    assert env["train"]["hash"] and env["holdout"]["hash"]
    assert env["train"]["hash"] != env["holdout"]["hash"]


def test_train_and_holdout_populations_are_disjoint():
    env = build_envelope(_mixed_corpus(), cutoff=CUTOFF, label_column="label", top_n=20)
    assert env["verdict"] != "REFUSE"
    assert "ITEM_LEAKAGE" not in env["refusal_reasons"]


def test_sub_floor_delta_is_no_meaningful_change():
    """Baseline == candidate (nothing learned) must not read as an improvement."""
    env = build_envelope(_mixed_corpus(), cutoff=CUTOFF, label_column="label", top_n=20)
    if env["delta_points"] is not None and abs(env["delta_points"]) < 2.0:
        assert env["verdict"] in {"NO_MEANINGFUL_CHANGE", "INSUFFICIENT_EVIDENCE"}


def test_one_class_holdout_refuses():
    rows = [
        {"id": f"t{i}", "label": "love" if i % 2 else "kill", "labeled_at": f"2026-05-{i+1:02d}T00:00:00+00:00"}
        for i in range(25)
    ] + [
        {"id": f"h{i}", "label": "kill", "labeled_at": f"2026-06-{i+1:02d}T00:00:00+00:00"}
        for i in range(25)
    ]
    env = build_envelope(rows, cutoff=CUTOFF, label_column="label", top_n=20)

    assert env["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "HOLDOUT_ONE_CLASS" in env["refusal_reasons"]


def test_tiny_holdout_refuses():
    rows = [
        {"id": f"t{i}", "label": "love" if i % 2 else "kill", "labeled_at": f"2026-05-{i+1:02d}T00:00:00+00:00"}
        for i in range(25)
    ] + [
        {"id": "h0", "label": "love", "labeled_at": "2026-06-02T00:00:00+00:00"},
        {"id": "h1", "label": "kill", "labeled_at": "2026-06-03T00:00:00+00:00"},
    ]
    env = build_envelope(rows, cutoff=CUTOFF, label_column="label", top_n=20)

    assert env["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "HOLDOUT_TOO_SMALL" in env["refusal_reasons"]


# --------------------------------------------------------------- export bound


def test_export_statement_carries_the_before_bound():
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sql = str(build_labeled_dataset_statement(since=since, before=CUTOFF))
    assert "created_at <" in sql, "the --before upper bound is missing from the statement"

    unbounded = str(build_labeled_dataset_statement(since=since))
    assert unbounded.count("created_at <") < sql.count("created_at <")


# ----------------------------------------------------------- holdout readiness


def test_holdout_readiness_flags_a_single_labelling_session():
    """The production corpus's actual shape: many rows, one sitting, one positive."""
    rows = [
        {"id": f"m{i}", "label": "kill", "created_at": "2026-05-24T16:04:58+00:00"}
        for i in range(23)
    ] + [{"id": "m23", "label": "love", "created_at": "2026-05-24T18:18:28+00:00"}]

    readiness = build_holdout_readiness(rows, top_k=20)

    assert readiness["constructible"] is False
    assert "SINGLE_LABELLING_SESSION" in readiness["blockers"]
    assert "TOO_FEW_POSITIVES_TO_SPLIT" in readiness["blockers"]
    assert readiness["positives"] == 1
    assert readiness["distinct_label_days"] == 1


def test_holdout_readiness_passes_a_healthy_corpus():
    rows = [
        {
            "id": f"m{i}",
            "label": "love" if i % 2 else "kill",
            "created_at": f"2026-06-{(i % 28) + 1:02d}T12:00:00+00:00",
        }
        for i in range(60)
    ]
    readiness = build_holdout_readiness(rows, top_k=20)

    assert readiness["constructible"] is True
    assert readiness["blockers"] == []
