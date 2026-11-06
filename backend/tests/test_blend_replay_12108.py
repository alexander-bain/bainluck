"""The replay must retain refusals, reproduce publications, and expose bad rows."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.probability_publication import build_publication
from scripts.evals.blend_replay_export import (
    build_export,
    confirmed_readings,
    instant,
    rebuild_betting,
    read_packets,
)
from scripts.evals.blend_scorer import (
    candidate_prediction,
    committed_protocol,
    metrics,
    paired_interval,
    paired_metrics,
    replay,
    score_candidate,
    score_export,
)

STAMP = "2026-10-05T19:00:00+00:00"
START = "2026-10-06T20:00:00+00:00"
SWITCH = datetime(2026, 11, 6, 5, tzinfo=timezone.utc)


def packet(event_id=1, cluster="series-1"):
    bag = {"betting": {"value": 0.61, "updated_at": STAMP}, "betting_book_count": 3}
    pub = build_publication(
        event_id=event_id,
        sources=bag,
        rev=3,
        status="scheduled",
        espn_win_prob_home=None,
        opening_home_probability=None,
        observations=[
            {
                "source": "betting",
                "value": 0.61,
                "returned_sources": bag,
                "removed": False,
                "rev": 3,
                "stamped_at": STAMP,
                "prior_txn_row_write": False,
            }
        ],
        queued_frame=None,
    )
    pub["recorded_at"] = STAMP
    return {
        "event": {
            "id": event_id,
            "league": "baseball_mlb",
            "cluster_id": cluster,
            "start": START,
            "outcome": 1,
        },
        "odds_snapshots": [
            {
                "id": i,
                "bookmaker": f"book-{i}",
                "captured_at": STAMP,
                "valid_until": START,
                "home_win_probability": p,
            }
            for i, p in enumerate([0.60, 0.61, 0.70], 1)
        ],
        "win_prob_snapshots": [],
        "publications": [pub],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        [0.60, 0.61, 0.95],
        [0.6, 0.7],
        [0.2, 0.21, 0.8, 0.81],
        [0.60, 0.61, 0.62, 0.63],
        [0.0, 0.6, 0.7, 0.8],
    ],
)
async def test_betting_matches_the_actual_producer(monkeypatch, values):
    from app.tasks import odds_polling

    async def snapshot(_session, _event_id, bookmaker, _data, **_kwargs):
        p = bookmaker["p"]
        return (
            SimpleNamespace(
                home_win_probability=p,
                away_win_probability=1 - p,
                home_spread=None,
                over_under=None,
            ),
            False,
        )

    write = AsyncMock()
    monkeypatch.setattr(odds_polling, "_create_or_update_snapshot", snapshot)
    monkeypatch.setattr(odds_polling, "_maybe_set_opening_odds", AsyncMock())
    monkeypatch.setattr(
        "app.utils.nonvenue_live_push.write_nonvenue_probability", write
    )
    await odds_polling._ingest_event_odds(
        AsyncMock(),
        SimpleNamespace(id=1),
        {"bookmakers": [{"key": str(i), "p": p} for i, p in enumerate(values)]},
        instant(START),
        {},
    )
    rebuilt = rebuild_betting([{"home_win_probability": p} for p in values])
    assert write.await_count == 1
    assert write.await_args.args[3] == rebuilt["value"]
    assert (
        write.await_args.kwargs["metadata"]["betting_book_count"]
        == rebuilt["book_count"]
    )
    assert write.await_args.kwargs["evidence"]["median"] == rebuilt["median"]
    assert write.await_args.kwargs["evidence"]["split_pair"] == rebuilt["split"]


def test_latest_confirmation_never_uses_a_future_or_unconfirmed_quote():
    rows = packet()["odds_snapshots"]
    rows.extend(
        [
            {
                **rows[0],
                "id": 20,
                "captured_at": "2026-10-07T00:00:00Z",
                "valid_until": "2026-10-08T00:00:00Z",
                "home_win_probability": 0.99,
            },
            {
                **rows[0],
                "id": 21,
                "bookmaker": "pulled",
                "valid_until": "2026-10-05T19:01:00Z",
                "home_win_probability": 0.99,
            },
        ]
    )
    result = confirmed_readings(rows, instant(START), "bookmaker")
    assert [r["id"] for r in result] == [1, 2, 3]


def test_recorded_values_reproduce_exact_probability_and_tier():
    data = packet()
    exported = build_export([data], SWITCH)
    served = [r for r in exported["rows"] if r["kind"] == "served"]
    assert len(served) == 4
    for row in served:
        assert row["sources"] == data["publications"][0]["sources"]
        assert replay(row) == (row["blend_probability"], row["blend_tier"])
    report = score_export(exported, replicates=100)
    assert report["recorded_reproduction"] == {"n": 4, "mismatches": 0}
    assert report["activation"] == "NONE"


def test_reconstruction_stays_labelled_and_cannot_borrow_mutable_fallbacks():
    exported = build_export([packet()], SWITCH)
    reconstructed = [r for r in exported["rows"] if r["kind"] == "reconstruction"]
    assert len(reconstructed) == 4
    for row in reconstructed:
        assert (
            row["reconstruction_evidence"]["clock_basis"]
            == "capture_not_original_writer_stamp"
        )
        assert row["blend_inputs"] == {
            "espn_win_prob_home": None,
            "opening_home_probability": None,
        }


def test_same_series_cannot_cross_training_and_tuning():
    a, b = packet(), packet(2)
    b["event"]["start"] = "2026-10-16T00:00:00Z"
    exported = build_export([a, b], SWITCH)
    assert exported["result"] == "FAIL"
    assert len(exported["failures"]) == 1
    assert "crosses time splits" in exported["failures"][0]["reason"]


def test_ece_uses_scorecards_ten_bands_and_percentage_points():
    result = metrics(
        [
            {"probability": 0.09, "outcome": 1},
            {"probability": 0.11, "outcome": 0},
            {"probability": 1.0, "outcome": 1},
        ]
    )
    assert result["n"] == 3
    assert result["ece"] == 34.0
    assert result["gap"] == -26.67


@pytest.mark.parametrize(
    "damage", ["unreadable", "duplicate", "wrong_method", "wrong_value"]
)
def test_bad_rows_and_recorded_mismatches_never_become_a_pass(damage):
    exported = build_export([packet()], SWITCH)
    served = next(r for r in exported["rows"] if r["kind"] == "served")
    if damage == "unreadable":
        exported["rows"].append({"broken": True})
    elif damage == "duplicate":
        exported["rows"].append(deepcopy(served))
    elif damage == "wrong_method":
        served["blend_method"] = "unknown/v2"
    else:
        served["blend_probability"] = 0.99
    report = score_export(exported, replicates=100)
    assert report["result"] == "FAIL"


def test_unknown_outcome_is_a_failed_packet_not_a_smaller_denominator():
    raw = packet()
    raw["event"]["outcome"] = None
    exported = build_export([raw], SWITCH)
    assert exported["result"] == "FAIL"
    assert len(exported["failures"]) == 1
    assert score_export(exported, replicates=100)["result"] == "FAIL"


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [1800, -1, float("nan"), float("inf")])
async def test_bad_or_exhausted_nightly_budget_refuses_before_connecting(
    monkeypatch, seconds
):
    connect = AsyncMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", connect)
    with pytest.raises(ValueError, match="budget"):
        await read_packets([{"event_id": 1, "cluster_id": "one"}], seconds_used=seconds)
    connect.assert_not_called()


@pytest.mark.asyncio
async def test_database_export_obeys_busy_hours_before_connecting(monkeypatch):
    monkeypatch.setattr("app.utils.busy_db_defer.in_busy_window", lambda: True)
    with pytest.raises(ValueError, match="off-peak"):
        await read_packets([{"event_id": 1, "cluster_id": "one"}], seconds_used=0)


@pytest.mark.asyncio
async def test_reader_is_readonly_bounded_and_carries_forward_spent_budget(monkeypatch):
    raw = packet()
    queries = []
    engine_options = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def begin(self):
            return self

        async def rollback(self):
            pass

        async def execute(self, sql, params=None):
            query = str(sql)
            queries.append((query, params))
            if "FROM events" in query:
                rows = [
                    {
                        "id": 1,
                        "start": START,
                        "status": "completed",
                        "league": "baseball_mlb",
                        "home_score": 4,
                        "away_score": 2,
                    }
                ]
            elif "FROM odds_snapshots" in query:
                rows = raw["odds_snapshots"]
            elif "FROM win_prob_snapshots" in query:
                rows = raw["win_prob_snapshots"]
            elif "FROM probability_publications" in query:
                rows = raw["publications"]
            else:
                rows = []
            return SimpleNamespace(mappings=lambda: rows)

    engine = SimpleNamespace(connect=lambda: Connection(), dispose=AsyncMock())

    def create(_url, **options):
        engine_options.append(options)
        return engine

    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", create)
    monkeypatch.setattr("app.utils.busy_db_defer.in_busy_window", lambda: False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/fixture")
    result, receipt = await read_packets(
        [{"event_id": 1, "cluster_id": "one"}], seconds_used=7
    )
    assert engine_options[0]["connect_args"]["server_settings"] == {
        "default_transaction_read_only": "on",
        "statement_timeout": "10000",
    }
    assert queries[0][0] == "SET TRANSACTION READ ONLY"
    reads = [
        (sql, params) for sql, params in queries if sql.strip().startswith("SELECT")
    ]
    assert len(reads) == 4
    assert all("event_id" in params for _, params in reads)
    assert all("LIMIT :limit" in sql for sql, _ in reads[1:])
    assert receipt["statements"] == 4
    assert receipt["statement_seconds_before"] == 7
    assert receipt["statement_seconds_after"] >= 7
    assert result[0]["event"]["outcome"] == 1
    engine.dispose.assert_awaited_once()


def test_existing_receipt_refuses_before_database_read(monkeypatch, tmp_path):
    from scripts.evals import blend_replay_export as exporter

    output = tmp_path / "frozen.json"
    output.write_text("preserve")
    read = AsyncMock(side_effect=AssertionError("must not read database"))
    monkeypatch.setattr(exporter, "read_packets", read)
    monkeypatch.setattr(
        "sys.argv",
        [
            "export",
            "--database",
            "--manifest",
            "unused.json",
            "--read-window-clear",
            "--statement-seconds-used",
            "0",
            "--recording-start",
            SWITCH.isoformat(),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(FileExistsError):
        exporter.main()
    read.assert_not_called()
    assert output.read_text() == "preserve"


def test_reconstruction_disagreement_cannot_hide_behind_exact_recorded_replay():
    raw = packet()
    for book in raw["odds_snapshots"]:
        book["home_win_probability"] = 0.9
    report = score_export(build_export([raw], SWITCH), replicates=100)
    assert report["recorded_reproduction"] == {"n": 4, "mismatches": 0}
    assert report["reconstruction_agreement"]["k"] == 0
    assert report["reconstruction_agreement"]["n"] == 4
    assert report["result"] == "FAIL"


def test_historical_bank_cannot_become_prospective_heldout_evidence():
    raw = packet()
    raw["event"]["start"] = (SWITCH + timedelta(days=2)).isoformat()
    exported = build_export([raw], SWITCH)
    assert all(not row["recorded"] for row in exported["coverage"])
    assert not any(row["kind"] == "served" for row in exported["rows"])
    report = score_export(exported, replicates=100)
    assert report["cohorts"] == []
    assert report["result"] == "UNKNOWN"


def test_heldout_reconstructions_are_compared_but_never_graded_as_served():
    raw = packet()
    raw["event"]["start"] = (SWITCH + timedelta(days=2)).isoformat()
    raw["publications"][0]["recorded_at"] = (SWITCH + timedelta(hours=1)).isoformat()
    report = score_export(build_export([raw], SWITCH), replicates=100)
    assert len(report["cohorts"]) == 4
    assert all(
        row["kind"] == "served" and row["split"] == "held_out"
        for row in report["cohorts"]
    )


def test_unreadable_coverage_counts_as_failure():
    exported = build_export([packet()], SWITCH)
    exported["coverage"].append({"broken": True})
    report = score_export(exported, replicates=100)
    assert report["failures"]["unreadable_coverage"] == 1
    assert report["result"] == "FAIL"


def test_candidate_runs_actual_cascade_and_restores_current_weights():
    from app.utils.aggregation import SOURCE_WEIGHTS

    exported = build_export([packet()], SWITCH)
    row = next(r for r in exported["rows"] if r["kind"] == "served")
    row["sources"]["kalshi"] = {"value": 0.8, "updated_at": STAMP}
    original = dict(SOURCE_WEIGHTS)
    weights = {**original, "betting": 0.01, "kalshi": 5.0}
    assert replay(row)[0] == 0.61
    assert candidate_prediction(row, weights)[0] == 0.8
    assert dict(SOURCE_WEIGHTS) == original


@pytest.mark.parametrize("damage", ["new_feature", "negative", "nonfinite", "all_zero"])
def test_unregistered_candidate_feature_or_invalid_weight_is_refused(damage):
    from app.utils.aggregation import SOURCE_WEIGHTS

    weights = dict(SOURCE_WEIGHTS)
    if damage == "new_feature":
        weights["invented"] = 1
    elif damage == "negative":
        weights["betting"] = -1
    elif damage == "nonfinite":
        weights["betting"] = float("nan")
    else:
        weights = {name: 0 for name in weights}
    row = next(
        r for r in build_export([packet()], SWITCH)["rows"] if r["kind"] == "served"
    )
    with pytest.raises(ValueError):
        candidate_prediction(row, weights)


def test_candidate_intervals_are_paired_and_keep_the_delta_direction():
    rows = [
        {"baseline": 0.6, "candidate": 0.8, "outcome": 1, "cluster_id": str(i)}
        for i in range(4)
    ]
    delta = paired_metrics(rows)
    assert delta["ece"] == -20
    assert delta["brier"] == pytest.approx(-0.12)
    interval = paired_interval(rows, replicates=100, seed=1)
    assert interval["bounds"]["log_loss"][1] < 0


def test_training_fit_never_earns_a_heldout_licence():
    from app.utils.aggregation import SOURCE_WEIGHTS

    exported = build_export([packet()], SWITCH)
    candidate = {"method_id": "fixture", "weights": dict(SOURCE_WEIGHTS)}
    result = score_candidate(exported, candidate, replicates=100, seed=1)
    assert result["shared_guardrail"] == "UNKNOWN_NO_HELDOUT"
    assert not any(row["statistical_bar_met"] for row in result["cohorts"])
    assert result["licence"] == "HELD" and result["activation"] == "NONE"


def test_protocol_requires_committed_bytes_even_if_new_checksum_is_supplied(tmp_path):
    from pathlib import Path

    source = Path(__file__).parents[1] / "scripts/evals/blend_replay_protocol.json"
    path = tmp_path / "protocol.json"
    path.write_bytes(source.read_bytes())
    for args in [
        ["init", "-q", "-b", "codex/protocol-fixture"],
        ["add", "--", "protocol.json"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "-q",
            "-m",
            "Freeze fixture protocol",
        ],
    ]:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        committed_protocol(path, original, repository=tmp_path)["activation"] == "NONE"
    )
    path.write_bytes(path.read_bytes() + b"\n")
    replacement = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="committed"):
        committed_protocol(path, replacement, repository=tmp_path)


def test_a_corrupted_time_split_is_a_failure_not_extra_training_data():
    exported = build_export([packet()], SWITCH)
    exported["rows"][0]["split"] = "held_out"
    report = score_export(exported, replicates=100)
    assert report["result"] == "FAIL"
    assert report["failures"]["unreadable_row"] >= 1


def test_committed_protocol_cannot_weaken_nonmetric_guards(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from scripts.evals import blend_scorer

    source = Path(__file__).parents[1] / "scripts/evals/blend_replay_protocol.json"
    protocol = json.loads(source.read_bytes())
    protocol["speed_gate_required"] = False
    raw = json.dumps(protocol).encode()
    path = tmp_path / "protocol.json"
    path.write_bytes(raw)
    monkeypatch.setattr(
        blend_scorer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=raw),
    )
    with pytest.raises(ValueError, match="adopted gates"):
        committed_protocol(path, hashlib.sha256(raw).hexdigest(), repository=tmp_path)
