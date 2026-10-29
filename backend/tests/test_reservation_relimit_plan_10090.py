"""#10090: a limits-only reservation change is an exact, operator-valid reincarnation plan.

Offline controls for `scripts/reservation_relimit_plan.py`. The real PG + Redis
lifecycle (old Other bucket refuses, relimited namespace admits, rollback) is
`integration/test_dnpl_reservation_relimit_10090_pg.py`.
"""

from dataclasses import asdict, replace
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.services import dnpl_activation_operator as operator
from app.services.dnpl_authority import Authority
from app.utils.dnpl_redis_authority import namespace_keys
from app.utils.preview_reservations import DEFAULT_LIMITS, ReservationPolicy

BACKEND = Path(__file__).resolve().parents[1]
PRIMARY = ("a" * 40, "b" * 40)
OTHER_FIRST = (128, 48, 96, 48, 160, 32)
CONFIGURED = "128,48,96,48,160,32"


def tool():
    # Imported per test: on a tree without the script each case FAILS (exit 1)
    # instead of the whole file erroring at collection.
    from scripts import reservation_relimit_plan

    return reservation_relimit_plan


def ready(incarnation=1, policy=None, primary=PRIMARY, state="ready"):
    return Authority(3, incarnation, uuid4(), uuid4(), state, *primary,
                     policy or ReservationPolicy().fingerprint)


def apps():
    return {app: {"release": 5955, "slug": str(uuid4()), "commit": "e" * 40}
            for app in operator.APPS}


def test_plans_are_exactly_the_operator_lifecycle_with_only_the_sizes_changed():
    t = tool()
    expected = ready(4)
    result = t.build(expected, PRIMARY, apps(), OTHER_FIRST, CONFIGURED)
    activate = operator.parse_plan(json.dumps(result["activate"]).encode())
    retire = operator.parse_plan(json.dumps(result["retire"]).encode())
    assert [s.step for s in activate.steps] == ["prepare", "arm", "initialize", "ready"]
    assert [s.step for s in retire.steps] == ["retire"]
    assert activate.run_id != retire.run_id
    candidate = activate.steps[0].candidate
    assert activate.steps[0].expected == expected
    assert candidate == replace(
        expected, incarnation=5, state="preparing", namespace=candidate.namespace,
        operation_id=candidate.operation_id,
        policy_fingerprint="v1-six-hour-ba82e47ee634aba7:128,48,96,48,160,32")
    assert candidate.namespace != expected.namespace
    assert candidate.operation_id != expected.operation_id
    assert candidate.policy_fingerprint == ReservationPolicy(OTHER_FIRST).fingerprint
    assert all(s.expected == candidate for s in activate.steps[1:])
    assert retire.steps[0].expected == replace(candidate, state="ready")
    assert result["next_expected_authority"] == json.loads(
        json.dumps(asdict(replace(candidate, state="ready")), default=str))
    summary = result["summary"]
    assert summary["from_fingerprint"].rsplit(":", 1)[0] == summary["to_fingerprint"].rsplit(":", 1)[0]
    assert summary["from_ledger_key"] == namespace_keys(expected)[0]
    assert summary["to_ledger_key"] == namespace_keys(candidate)[0] != summary["from_ledger_key"]
    assert summary["mutation_permitted"] is False


def test_rollback_to_default_from_a_relimited_authority():
    t = tool()
    relimited = ready(5, ReservationPolicy(OTHER_FIRST).fingerprint)
    result = t.build(relimited, PRIMARY, apps(), t.parse_limits("default"), "")
    assert result["summary"]["to_fingerprint"] == ReservationPolicy().fingerprint
    assert result["summary"]["to_incarnation"] == 6
    # The defaults may also be configured explicitly.
    t.build(relimited, PRIMARY, apps(), DEFAULT_LIMITS, "192,64,128,64,48,16")


@pytest.mark.parametrize(
    "expected, limits, configured, reason",
    [
        (ready(state="preparing"), OTHER_FIRST, CONFIGURED, "ready allocated"),
        (ready(state="disabled"), OTHER_FIRST, CONFIGURED, "ready allocated"),
        (ready(primary=("c" * 40, "b" * 40)), OTHER_FIRST, CONFIGURED, "not the normal route"),
        (ready(), DEFAULT_LIMITS, "", "equal the authority"),
        # A league-map or semantics change is a different policy, not a resize.
        (ready(policy="v1-six-hour-0000000000000000:192,64,128,64,48,16"),
         OTHER_FIRST, CONFIGURED, "not limits-only"),
        (ready(policy="v2-six-hour-ba82e47ee634aba7:192,64,128,64,48,16"),
         OTHER_FIRST, CONFIGURED, "not a v1"),
        (ready(policy="v1-six-hour-ba82e47ee634aba7:192,64,128,64,48"),
         OTHER_FIRST, CONFIGURED, "not a v1"),
        (ready(policy="v1-six-hour-ba82e47ee634aba7:0192,64,128,64,48,16"),
         OTHER_FIRST, CONFIGURED, "not canonical"),
        # The app's configured value must produce exactly the planned sizes.
        (ready(), OTHER_FIRST, "", "does not produce"),
        (ready(), OTHER_FIRST, "96,48,128,64,144,32", "does not produce"),
    ],
)
def test_refuses_anything_but_a_valid_limits_only_change(expected, limits, configured, reason):
    t = tool()
    with pytest.raises(t.RelimitRefused, match=reason):
        t.build(expected, PRIMARY, apps(), limits, configured)


@pytest.mark.parametrize("value", ["128,48,96,48,160", "200,100,100,64,48,16",
                                   "128, 48,96,48,160,32", "-1,48,96,48,160,32"])
def test_invalid_sizes_refuse_exactly_as_the_app_would(value):
    t = tool()
    with pytest.raises(ValueError):
        t.parse_limits(value)
    with pytest.raises(ValueError):
        t.build(ready(), PRIMARY, apps(), OTHER_FIRST, value)


def test_unset_ledger_fingerprint_with_invalid_current_sizes_refuses():
    t = tool()
    with pytest.raises(ValueError):
        t.build(ready(policy="v1-six-hour-ba82e47ee634aba7:300,64,128,64,48,16"),
                PRIMARY, apps(), OTHER_FIRST, CONFIGURED)


def test_configured_value_probe_leaves_the_process_environment_unchanged(monkeypatch):
    t = tool()
    monkeypatch.setenv("LIVE_BLEND_PREVIEW_RESERVATIONS", "1,1,1,1,1,1")
    t.build(ready(), PRIMARY, apps(), OTHER_FIRST, CONFIGURED)
    t.build(ready(policy=ReservationPolicy(OTHER_FIRST).fingerprint), PRIMARY, apps(),
            DEFAULT_LIMITS, "")
    assert os.environ["LIVE_BLEND_PREVIEW_RESERVATIONS"] == "1,1,1,1,1,1"


def _inputs(tmp_path, expected):
    (tmp_path / "authority.json").write_text(json.dumps(asdict(expected), default=str))
    (tmp_path / "apps.json").write_text(json.dumps(apps()))
    return ["--expected-authority", str(tmp_path / "authority.json"),
            "--primary", ":".join(PRIMARY), "--apps", str(tmp_path / "apps.json")]


def test_cli_writes_private_operator_plans_once(tmp_path, capsys):
    t = tool()
    out = tmp_path / "relimit"
    args = _inputs(tmp_path, ready(2)) + ["--to", CONFIGURED, "--configured", CONFIGURED,
                                          "--out-dir", str(out)]
    assert t.main(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "PLANS_WRITTEN" and printed["to_incarnation"] == 3
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    names = {"activate-plan.json", "retire-plan.json", "next-expected-authority.json",
             "RELIMIT-SUMMARY.json"}
    assert {p.name for p in out.iterdir()} == names
    for p in out.iterdir():
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    # The operator's own private-file reader accepts both plans as written.
    assert [s.step for s in operator.read_plan(out / "activate-plan.json").steps][0] == "prepare"
    assert operator.read_plan(out / "retire-plan.json").steps[0].step == "retire"
    # The written next authority is the exact input of the rollback build.
    rollback = tmp_path / "rollback"
    assert t.main(["--expected-authority", str(out / "next-expected-authority.json"),
                   "--primary", ":".join(PRIMARY), "--apps", str(tmp_path / "apps.json"),
                   "--to", "default", "--configured", "", "--out-dir", str(rollback)]) == 0
    assert json.loads(capsys.readouterr().out)["to_fingerprint"] == ReservationPolicy().fingerprint
    # No reuse of an existing directory.
    assert t.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"


def test_cli_refusal_reports_no_exception_text(tmp_path, capsys):
    t = tool()
    args = _inputs(tmp_path, ready()) + ["--to", CONFIGURED, "--configured", "",
                                         "--out-dir", str(tmp_path / "x")]
    assert t.main(args) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "REFUSED",
        "reason": "LIVE_BLEND_PREVIEW_RESERVATIONS read back from the app does not produce the target sizes",
    }
    assert not (tmp_path / "x").exists()
    (tmp_path / "authority.json").write_text("{not json")
    assert t.main(args) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "reason": "JSONDecodeError"}


def test_script_runs_as_a_file_from_the_backend_root():
    done = subprocess.run([sys.executable, "scripts/reservation_relimit_plan.py", "--help"],
                          cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "--configured" in done.stdout
