"""Tests and CI contract guards for #13283 (post-deploy smoke check, dry-run only)."""

from __future__ import annotations

import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "post_deploy_smoke_rollback.py"
CI_YML_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("post_deploy_smoke_rollback", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _serve_once(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}", thread


def _stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)


def test_default_endpoints_match_fables_correction():
    mod = _load_module()
    assert [(ep.label, ep.path, ep.list_key) for ep in mod.DEFAULT_ENDPOINTS] == [
        ("Discover", "/api/feed?machinery=1&limit=20", "items"),
        ("Games list", "/api/events?sport=basketball_nba&limit=20", "events"),
    ]


def test_standin_500_reports_would_roll_back_without_heroku_calls():
    mod = _load_module()
    report = mod.run_self_test_500()
    assert report.verdict == "would_roll_back"
    assert "would roll back" in report.summary
    assert all(ep.outcome == "failed" for ep in report.endpoints)
    assert all(len(ep.attempts) == 3 for ep in report.endpoints)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--self-test-500"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "would roll back" in proc.stdout


def test_standin_200_non_empty_passes_with_single_attempt_per_endpoint():
    mod = _load_module()
    seen_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen_paths.append(self.path)
            if self.path.startswith("/api/feed"):
                payload = {"items": [{"id": 1}]}
            elif self.path.startswith("/api/events"):
                payload = {"events": [{"id": 2}]}
            else:
                payload = {"status": "ok", "commit": "abc12345"}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server, base_url, thread = _serve_once(Handler)
    try:
        report = mod.run_smoke_check(
            base_url=base_url,
            expected_sha="abc12345def67890",
            initial_delay_seconds=0.0,
            retry_delay_seconds=0.0,
            health_wait_seconds=1.0,
            health_poll_seconds=0.0,
        )
    finally:
        _stop_server(server, thread)

    assert report.verdict == "passed"
    assert report.health_commit == "abc12345"
    assert [len(ep.attempts) for ep in report.endpoints] == [1, 1]
    assert "/api/feed?machinery=1&limit=20" in seen_paths
    assert "/api/events?sport=basketball_nba&limit=20" in seen_paths


def test_empty_200_list_is_reported_not_rolled_back():
    mod = _load_module()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/feed"):
                payload = {"items": []}
            else:
                payload = {"events": [{"id": 2}]}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server, base_url, thread = _serve_once(Handler)
    try:
        report = mod.run_smoke_check(
            base_url=base_url,
            expected_sha="abc12345",
            initial_delay_seconds=0.0,
            retry_delay_seconds=0.0,
            skip_health_wait=True,
        )
    finally:
        _stop_server(server, thread)

    assert report.verdict == "empty_list_report"
    assert "would roll back" not in report.summary
    assert report.endpoints[0].outcome == "empty_list"
    assert report.endpoints[1].outcome == "ok"


def test_transient_500_then_200_on_third_try_passes():
    mod = _load_module()
    counts = {"feed": 0, "events": 0}

    def fake_get(url: str, timeout: float):
        if "/api/feed" in url:
            counts["feed"] += 1
            if counts["feed"] < 3:
                return 500, '{"detail":"warming"}'
            return 200, '{"items":[{"id":1}]}'
        counts["events"] += 1
        return 200, '{"events":[{"id":2}]}'

    sleeps: list[float] = []
    report = mod.run_smoke_check(
        base_url="http://standin.local",
        initial_delay_seconds=60.0,
        retries=3,
        retry_delay_seconds=30.0,
        skip_health_wait=True,
        http_get=fake_get,
        sleep_fn=sleeps.append,
    )
    assert report.verdict == "passed"
    assert counts == {"feed": 3, "events": 1}
    assert sleeps == [60.0, 30.0, 30.0]


def test_migration_change_guard_refuses_rollback_and_alerts_only(tmp_path: Path):
    mod = _load_module()
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    app_file = tmp_path / "backend" / "app" / "x.py"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "base"], check=True, capture_output=True)
    prev_sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()

    mig_file = tmp_path / "backend" / "alembic" / "versions" / "20261120_test.py"
    mig_file.parent.mkdir(parents=True)
    mig_file.write_text("revision = '20261120_test'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "mig"], check=True, capture_output=True)
    head_sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()

    report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha=head_sha,
        prev_sha=prev_sha,
        initial_delay_seconds=0.0,
        retry_delay_seconds=0.0,
        skip_health_wait=True,
        repo_root=tmp_path,
        http_get=lambda url, timeout: (500, '{"detail":"boom"}'),
        sleep_fn=lambda _: None,
    )
    assert report.verdict == "alert_only"
    assert report.changed_migrations == ("backend/alembic/versions/20261120_test.py",)
    assert "alert only" in report.summary
    assert "would roll back" not in report.summary


def test_prior_rollback_or_failed_release_blocks_double_rollback():
    mod = _load_module()
    for state in ("rolled_back", "failed"):
        report = mod.run_smoke_check(
            base_url="http://standin.local",
            expected_sha="deadbeef",
            initial_delay_seconds=0.0,
            retry_delay_seconds=0.0,
            skip_health_wait=True,
            prior_release_state=state,
            http_get=lambda url, timeout: (500, '{"detail":"boom"}'),
            sleep_fn=lambda _: None,
        )
        assert report.verdict == "alert_only"
        assert "would roll back" not in report.summary


def test_kill_switch_disables_check_cleanly():
    mod = _load_module()
    assert mod.is_auto_rollback_enabled(None) is True
    assert mod.is_auto_rollback_enabled("") is True
    assert mod.is_auto_rollback_enabled("false") is False
    assert mod.is_auto_rollback_enabled("0") is False

    called = False

    def should_not_call(url: str, timeout: float):
        nonlocal called
        called = True
        return 500, ""

    report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha="deadbeef",
        auto_rollback_env="false",
        http_get=should_not_call,
    )
    assert report.verdict == "disabled"
    assert called is False


def test_ci_workflow_wires_dry_run_and_script_has_zero_heroku_mutations():
    wf = yaml.safe_load(CI_YML_PATH.read_text(encoding="utf-8"))
    fast_gate_runs = "\n".join(str(step.get("run", "")) for step in wf["jobs"]["fast-gate"]["steps"])
    assert "post_deploy_smoke_rollback.py --self-test-500" in fast_gate_runs

    deploy_job = wf["jobs"]["deploy"]
    assert deploy_job["outputs"]["deployed"] == "${{ steps.heroku_deploy.outputs.deployed }}"
    assert deploy_job["steps"][-1].get("id") == "heroku_deploy"

    smoke_job = wf["jobs"]["post-deploy-smoke-dry-run"]
    assert smoke_job["needs"] == ["deploy"]
    assert "needs.deploy.outputs.deployed == 'true'" in smoke_job["if"]
    smoke_step = smoke_job["steps"][-1]
    assert smoke_step["env"]["AUTO_ROLLBACK_ENABLED"] == "${{ vars.AUTO_ROLLBACK_ENABLED }}"
    assert "--dry-run" in smoke_step["run"]
    assert "https://api.bainluck.com" in smoke_step["run"]

    script_source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "releases:rollback" not in script_source.lower()
    assert "api.heroku.com" not in script_source.lower()
    # Ensure no subprocess invocation in code ever invokes a heroku CLI binary.
    tree = ast.parse(script_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else (func.attr if isinstance(func, ast.Attribute) else "")
            )
            if name in {"run", "Popen", "check_output", "check_call"}:
                dumped = ast.dump(node).lower()
                assert "'heroku'" not in dumped and '"heroku"' not in dumped
