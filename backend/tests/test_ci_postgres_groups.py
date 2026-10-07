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
import re
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
        ("bl_blend_deadlock_837", ["test_live_blend_stamp_deadlock_pg_837.py",
          "test_kalshi_price_lock_budget_pg_10661.py"]),
        ("bl_movement_accept_4079", ["test_numeric_movement_fields_4079_amended_real_postgres.py"]),
        ("bl_timeline_route_7284", ["test_the_timeline_route_loads_on_a_real_session_7284.py"]),
        ("bl_generic_history_7351", ["test_generic_market_history_7351_real_pg_redis.py",
          "test_supported_history_survives_display_selection_8000_real_pg_redis.py",
          "test_phone_history_detail_7547_real_pg_redis.py"]),
        ("bl_nascar_print_7548", ["test_polymarket_trade_print_7548_real_pg.py"]),
        ("bl_canonical_own_7594", ["test_7594_canonical_ownership_pg.py"]),
        ("bl_delay_contract_7617", ["test_a_delay_is_not_silence_pg_7617.py",
          "test_a_withdrawn_listing_is_not_a_start_pg_8755.py",
          "test_a_venue_stamp_later_session_pg_9588.py",
          "test_espn_pass_survives_one_failed_statement_pg_8796.py",
          "test_espn_pass_releases_rows_pg_9049.py",
          "test_settled_box_pass_survives_one_refused_box_pg_9713.py",
          "test_certain_postseason_playoff_pg_9602.py",
          "test_live_box_pass_survives_one_failed_write_pg_8913.py",
          "test_live_box_pass_reaches_every_fetchable_game_pg_9067.py"]),
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


def _env_group_splits(steps):
    """Steps reading a `$GITHUB_ENV` variable that no earlier step in their group wrote.

    The curated chain list above is exactly what missed #8755 and five more: they
    reuse the #7617 database through its variable (two of them through a fixture
    imported from #8796), never naming the database, so the split ran them on a
    runner without it and every one skipped. Derived here instead: the variables
    each provisioner writes, and every consumer whose step, test file, or the
    `tests.integration` modules that file imports mention one.
    """
    provisioners = {}
    for i, step in enumerate(steps):
        run = step.get("run", "")
        if "$GITHUB_ENV" in run:
            for var in set(re.findall(r'"([A-Z][A-Z0-9_]*)=', run)) | set(
                    re.findall(r'echo\s+"?([A-Z][A-Z0-9_]*)=', run)):
                provisioners.setdefault(var, []).append((i, step.get("if")))
    assert "DELAY_CONTRACT_DATABASE_URL" in provisioners  # the scan still sees the #7617 write
    splits = []
    for i, step in enumerate(steps):
        text = step.get("run", "")
        for rel in re.findall(r"tests/integration/[\w./-]+\.py", step.get("run", "")):
            source = (ROOT / "backend" / rel).read_text()
            text += source
            for module in re.findall(r"from tests\.integration\.(\w+) import", source):
                text += (ROOT / "backend/tests/integration" / f"{module}.py").read_text()
        for var, writers in provisioners.items():
            if var in text and not any(w <= i and group == step.get("if") for w, group in writers):
                splits.append((step.get("name"), var))
    return splits


def test_every_env_consumer_runs_after_its_provisioner_in_the_same_group():
    jobs, _ = _inputs()
    assert _env_group_splits(jobs["database-integration"]["steps"]) == []


def test_env_split_guard_catches_the_8755_split():
    """Mutant: #8755 back in `shared`, as first offered — the guard must name it."""
    jobs, _ = _inputs()
    steps = jobs["database-integration"]["steps"]
    step = next(s for s in steps if s.get("name", "").startswith("#8755 "))
    step["if"] = "matrix.group == 'shared'"
    assert _env_group_splits(steps) == [(step["name"], "DELAY_CONTRACT_DATABASE_URL")]


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
