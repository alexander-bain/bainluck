"""Verifier negatives are local files/process doubles, never Platform requests."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import dnpl_writer_observations as observations
from app.services.dnpl_operation_hold import OperationHoldRefused


@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setattr(observations.time, "time_ns", lambda: 100_000_000_000)
    monkeypatch.setattr(observations.time, "monotonic_ns", lambda: 10_000_000_000)
    apps = {
        app: {"release": 4, "slug": str(uuid4()), "commit": "a" * 40}
        for app in observations.APPS
    }
    binding = {
        "run_id": str(uuid4()),
        "nonce": "b" * 32,
        "step": "arm",
        "expected_authority": {},
        "expected_primary": "exact",
        "apps": apps,
    }
    reads, payloads = [], {}
    for app in observations.APPS:
        src = apps[app]
        payloads[app + "-releases"] = [
            {
                "current": True,
                "status": "succeeded",
                "version": src["release"],
                "slug": {"id": src["slug"]},
            }
        ]
        payloads[app + "-slug"] = {"id": src["slug"], "commit": src["commit"]}
        payloads[app + "-formation"] = [
            {"type": "worker-ws", "quantity": 0},
            {"type": "web", "quantity": 1},
        ]
        payloads[app + "-dynos"] = [
            {"type": "web", "name": "web.1", "release": {"version": 4}}
        ]
    for index, name in enumerate(observations.READ_NAMES):
        data = json.dumps(payloads[name]).encode()
        (tmp_path / (name + ".json")).write_bytes(data)
        reads.append(
            {
                "name": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "start_ns": 99_000_000_000 + index,
                "end_ns": 99_000_000_000 + index,
            }
        )
    result = {"binding": binding, "reads": reads}
    observation = observations.Observation(
        tmp_path, json.dumps(binding), json.dumps(result), 99_000_000_000, 9_000_000_000
    )
    return observation, result, payloads


def test_exact_raw_bindings_and_whole_collection_pass(sample):
    observation, result, _ = sample
    assert observation.validate() == result["binding"]


@pytest.mark.parametrize(
    "start,end",
    [
        (-1, 1),
        (98_999_999_999, 99_000_000_000),
        (99_000_000_000, 100_000_000_001),
        (99_000_000_001, 99_000_000_000),
        (True, 99_000_000_000),
        (99.0, 99_000_000_000),
    ],
)
def test_bad_collection_time_refuses(sample, start, end):
    observation, result, _ = sample
    result["reads"][0].update(start_ns=start, end_ns=end)
    with pytest.raises(OperationHoldRefused, match="observation time"):
        replace(observation, result_json=json.dumps(result)).validate()


@pytest.mark.parametrize(
    "wall,mono",
    [
        (300_000_000_000, 210_000_000_000),
        (98_000_000_000, 10_000_000_000),
        (103_000_000_000, 10_000_000_000),
    ],
)
def test_stale_or_disagreeing_wrapper_clocks_refuse(sample, monkeypatch, wall, mono):
    observation, _, _ = sample
    monkeypatch.setattr(observations.time, "time_ns", lambda: wall)
    monkeypatch.setattr(observations.time, "monotonic_ns", lambda: mono)
    with pytest.raises(OperationHoldRefused, match="clock changed"):
        observation.validate()


def test_raw_file_change_and_binding_replay_refuse(sample):
    observation, result, _ = sample
    result["binding"]["nonce"] = "c" * 32
    with pytest.raises(OperationHoldRefused, match="binding mismatch"):
        replace(observation, result_json=json.dumps(result)).validate()
    (observation.directory / (observations.READ_NAMES[0] + ".json")).write_text("[]")
    with pytest.raises(OperationHoldRefused, match="raw observation changed"):
        observation.validate()


@pytest.mark.parametrize(
    "problem",
    ["worker", "unknown", "dyno", "release", "slug", "unconverged", "missing"],
)
def test_writer_and_source_drift_refuse(sample, problem):
    _, result, payloads = sample
    binding = deepcopy(result["binding"])
    if problem == "worker":
        payloads["bainluck-formation"][0]["quantity"] = 1
    elif problem == "unknown":
        payloads["bainluck-formation"].append({"type": "addon-oneoff", "quantity": 1})
    elif problem == "dyno":
        payloads["bainluck-dynos"][0].update(type="run", name="run.1")
    elif problem == "release":
        payloads["bainluck-dynos"][0]["release"]["version"] = 3
    elif problem == "slug":
        payloads["bainluck-slug"]["commit"] = "b" * 40
    elif problem == "unconverged":
        binding["apps"]["bainluck-heavy"]["commit"] = "b" * 40
    else:
        payloads["bainluck-formation"] = []
    with pytest.raises(OperationHoldRefused):
        observations.validate_payloads(binding, payloads)


def test_hash_mismatch_never_executes_child(tmp_path, monkeypatch):
    monkeypatch.setattr(observations, "VERIFIER_SHA256", "0" * 64)
    monkeypatch.setattr(
        observations.subprocess,
        "run",
        lambda *a, **k: pytest.fail("must not run child"),
    )
    with pytest.raises(OperationHoldRefused, match="source changed"):
        observations.execute_verifier(
            tmp_path,
            run_id=str(uuid4()),
            step="arm",
            expected_authority={},
            expected_primary="",
            apps={},
        )


def test_parent_executes_once_with_fresh_nonce_and_ignores_existing_receipt(
    sample, monkeypatch
):
    observation, result, payloads = sample
    calls = []

    def child(argv, **kwargs):
        calls.append(argv)
        assert argv[1:3] == ["-I", str(observations.VERIFIER)]
        binding = json.loads(argv[4])
        directory = observation.directory / ("verify-" + binding["nonce"])
        assert directory.is_dir() and list(directory.iterdir()) == []
        reads = []
        for name in observations.READ_NAMES:
            data = json.dumps(payloads[name]).encode()
            (directory / (name + ".json")).write_bytes(data)
            reads.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "start_ns": 100_000_000_000,
                    "end_ns": 100_000_000_000,
                }
            )
        kwargs["stdout"].write(
            json.dumps({"binding": binding, "reads": reads}).encode()
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(observations.subprocess, "run", child)
    (observation.directory / "WRITER-STOP.1").write_text("fake existing receipt")
    output = observations.execute_verifier(
        observation.directory,
        run_id=result["binding"]["run_id"],
        step="arm",
        expected_authority={},
        expected_primary="exact",
        apps=result["binding"]["apps"],
    )
    assert len(calls) == 1
    assert output.validate()["nonce"] != result["binding"]["nonce"]
