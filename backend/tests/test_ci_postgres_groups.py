"""#9670: distribute real-DB work without losing a gate or its provisioning.

These are offline workflow checks, not claims that hosted integration passed.
The manifest is an explicit assignment of execution units, not a test allowlist:
every unit in the workflow must appear once, and every entry must execute once.
"""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
MANIFEST = ROOT / ".github/ci-postgres-groups.json"


def _inputs():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"], json.loads(MANIFEST.read_text())


def _validate_assignments(worker, manifest):
    groups = worker["strategy"]["matrix"]["group"]
    assert set(groups) == set(manifest)
    assert len(groups) == len(set(groups))
    steps = worker["steps"][4:]
    names = [s["name"] for s in steps]
    expected = [name for group in groups for name in manifest[group]]
    assert len(expected) == len(set(expected)), "duplicate assignment"
    assert Counter(names) == Counter(expected), "missing or extra execution unit"
    assert len(names) == len(set(names)), "duplicate execution unit"
    for group in groups:
        selected = [s["name"] for s in steps if s.get("if") == f"matrix.group == '{group}'"]
        assert selected == manifest[group], "assignment/order changed or unit would not run"


def test_each_execution_unit_runs_once_in_manifest_order():
    jobs, manifest = _inputs()
    _validate_assignments(jobs["database-integration"], manifest)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unassigned", "unknown_group"])
def test_incomplete_or_duplicate_dispatch_is_rejected(mutation):
    jobs, manifest = _inputs()
    worker = jobs["database-integration"]
    if mutation == "missing":
        worker["steps"].pop()
    elif mutation == "duplicate":
        manifest["shared"].append(manifest["isolated"][0])
    elif mutation == "unassigned":
        worker["steps"][4].pop("if")
    else:
        worker["steps"][4]["if"] = "matrix.group == 'typo'"
    with pytest.raises(AssertionError):
        _validate_assignments(worker, manifest)


def test_common_setup_services_and_intentional_scope_skip():
    jobs, _ = _inputs()
    worker = jobs["database-integration"]
    assert worker["needs"] == "change-scope"
    assert worker["if"] == "needs.change-scope.outputs.scope != 'frontend'"
    assert worker["strategy"]["fail-fast"] is False
    assert worker["strategy"]["matrix"]["group"] == ["shared", "isolated"]
    assert worker["services"]["postgres"]["image"] == "postgres:15"
    assert worker["services"]["postgres"]["env"]["POSTGRES_DB"] == "bl_searchtest"
    assert worker["services"]["redis"]["ports"] == ["56379:6379"]
    assert "REDIS_URL" not in worker["env"]  # Only named history steps use Redis.
    assert worker["env"]["DATABASE_URL"] == worker["env"]["SEARCH_TEST_DATABASE_URL"]
    assert worker["defaults"]["run"]["working-directory"] == "backend"
    assert [s.get("uses", s.get("name")) for s in worker["steps"][:4]] == [
        "actions/checkout@v6", "actions/setup-python@v7", "Install dependencies",
        "Verify the gate is actually armed",
    ]
    assert all("if" not in s for s in worker["steps"][:4])


def test_disposable_consumers_keep_their_provisioner_on_the_same_runner():
    jobs, _ = _inputs()
    steps = jobs["database-integration"]["steps"]
    # Generic history is deliberately one chain: all three consumers use its
    # nonce, scratch Postgres, and Redis. WS suspended uses WS slate's DB.
    chains = [
        ("bl_blend_deadlock_837", ["test_live_blend_stamp_deadlock_pg_837.py"]),
        ("bl_movement_accept_4079", ["test_numeric_movement_fields_4079_amended_real_postgres.py"]),
        ("bl_timeline_route_7284", ["test_the_timeline_route_loads_on_a_real_session_7284.py"]),
        ("bl_generic_history_7351", ["test_generic_market_history_7351_real_pg_redis.py",
          "test_supported_history_survives_display_selection_8000_real_pg_redis.py",
          "test_phone_history_detail_7547_real_pg_redis.py"]),
        ("bl_nascar_print_7548", ["test_polymarket_trade_print_7548_real_pg.py"]),
        ("bl_canonical_own_7594", ["test_7594_canonical_ownership_pg.py"]),
        ("bl_delay_contract_7617", ["test_a_delay_is_not_silence_pg_7617.py"]),
        ("bl_evidence_collapse_7878", ["test_winprob_evidence_collapse_pg_7878.py"]),
        ("bl_ws_slate_837", ["test_ws_slate_age_floor_pg_837.py",
          "test_ws_slate_suspended_open_market_pg_9484.py"]),
    ]
    for database, consumers in chains:
        provisions = [(i, s) for i, s in enumerate(steps)
                      if f'DB = "{database}"' in s.get("run", "")]
        assert len(provisions) == 1
        provision_index, provision = provisions[0]
        assert '"$GITHUB_ENV"' in provision["run"]
        for consumer in consumers:
            matches = [(i, s) for i, s in enumerate(steps)
                       if f"tests/integration/{consumer}" in s.get("run", "")]
            assert len(matches) == 1
            index, step = matches[0]
            assert provision_index < index
            assert provision["if"] == step["if"] == "matrix.group == 'isolated'"


def test_required_aggregate_runs_after_failure_and_deploy_still_depends_on_it():
    jobs, _ = _inputs()
    aggregate = jobs["search-recall"]
    assert "strategy" not in aggregate and "name" not in aggregate
    assert aggregate["needs"] == ["change-scope", "database-integration"]
    assert aggregate["if"] == "always() && needs.change-scope.outputs.scope != 'frontend'"
    assert "search-recall" in jobs["deploy"]["needs"]
    assert "continue-on-error" not in aggregate
    assert "continue-on-error" not in jobs["database-integration"]
    step = aggregate["steps"][0]
    assert step["env"] == {
        "SCOPE_RESULT": "${{ needs.change-scope.result }}",
        "INTEGRATION_RESULT": "${{ needs.database-integration.result }}",
    }
    assert "if" not in step and "continue-on-error" not in step


@pytest.mark.parametrize("scope_result", ["success", "failure", "cancelled", "skipped", ""])
@pytest.mark.parametrize("integration_result", ["success", "failure", "cancelled", "skipped", ""])
def test_actual_aggregate_command_only_accepts_completed_success(scope_result, integration_result):
    jobs, _ = _inputs()
    command = jobs["search-recall"]["steps"][0]["run"]
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", command],
        env={**os.environ, "SCOPE_RESULT": scope_result, "INTEGRATION_RESULT": integration_result},
        capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) == (scope_result == integration_result == "success")
