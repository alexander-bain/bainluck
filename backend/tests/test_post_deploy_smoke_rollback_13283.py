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
    assert "commit read=standin5, expected=standin5" in report.summary
    assert all(ep.outcome == "failed" for ep in report.endpoints)
    assert all(len(ep.attempts) == 3 for ep in report.endpoints)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--self-test-500"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "would roll back" in proc.stdout
    assert "commit read=standin5, expected=standin5" in proc.stdout


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
    assert "commit read=abc12345, expected=abc12345" in report.summary
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


def test_ci_workflow_wires_live_post_deploy_smoke_without_heroku_cli():
    wf = yaml.safe_load(CI_YML_PATH.read_text(encoding="utf-8"))
    fast_gate_runs = "\n".join(str(step.get("run", "")) for step in wf["jobs"]["fast-gate"]["steps"])
    assert "post_deploy_smoke_rollback.py --self-test-500" in fast_gate_runs

    for rel_job_name in ("deploy", "deploy-after-full"):
        rel_job = wf["jobs"][rel_job_name]
        assert rel_job["outputs"]["deployed"] == "${{ steps.heroku_deploy.outputs.deployed }}"
        assert rel_job["steps"][-1].get("id") == "heroku_deploy"

    smoke_job = wf["jobs"]["post-deploy-smoke"]
    assert smoke_job["needs"] == ["deploy", "deploy-after-full"]
    assert smoke_job["timeout-minutes"] >= 15
    assert smoke_job["permissions"] == {"contents": "read", "issues": "write"}
    assert "needs.deploy.outputs.deployed == 'true'" in smoke_job["if"]
    assert "needs.deploy-after-full.outputs.deployed == 'true'" in smoke_job["if"]
    smoke_step = smoke_job["steps"][-1]
    assert smoke_step["env"]["AUTO_ROLLBACK_ENABLED"] == "${{ vars.AUTO_ROLLBACK_ENABLED }}"
    assert smoke_step["env"]["HEROKU_API_KEY"] == "${{ secrets.HEROKU_API_KEY }}"
    assert smoke_step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert smoke_step["env"]["NOW_LINES_ISSUE"] == "13580"
    assert "--execute" in smoke_step["run"]
    assert "--dry-run" not in smoke_step["run"]
    assert "https://api.bainluck.com" in smoke_step["run"]

    script_source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "releases:rollback" not in script_source.lower()
    # Ensure no subprocess invocation in code ever invokes a heroku CLI binary (Platform API HTTP only).
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


def test_execute_mode_rolls_back_reprobes_and_posts_alert(monkeypatch, tmp_path: Path):
    mod = _load_module()
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True, capture_output=True)
    app_file = tmp_path / "backend" / "app" / "x.py"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "old"], check=True, capture_output=True)
    prev_sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    app_file.write_text("x = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "new"], check=True, capture_output=True)
    head_sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()

    state = {"phase": "broken", "rollback_calls": [], "alerts": []}

    def fake_get(url: str, timeout: float):
        if url.endswith("/api/health"):
            sha = prev_sha[:8] if state["phase"] == "rolled_back" else head_sha[:8]
            return 200, json.dumps({"status": "ok", "commit": sha})
        if state["phase"] == "broken":
            return 500, '{"detail":"boom"}'
        if "/api/feed" in url:
            return 200, '{"items":[{"id":1}]}'
        return 200, '{"events":[{"id":2}]}'

    def fake_list(app: str, key: str):
        assert app == "bainluck" and key == "secret-key"
        return [
            {"id": "rel-new", "version": 6620, "status": "succeeded", "description": f"Deploy {head_sha[:8]}"},
            {"id": "rel-old", "version": 6619, "status": "succeeded", "description": f"Deploy {prev_sha[:8]}"},
        ]

    def fake_rollback(app: str, key: str, release_id: str):
        state["rollback_calls"].append((app, release_id))
        state["phase"] = "rolled_back"
        return {"id": "rel-rb", "version": 6621, "status": "succeeded", "description": "Rollback to v6619"}

    def fake_post(repo: str, issue: int, title: str, body: str, now_line: str) -> bool:
        state["alerts"].append((repo, issue, title, body, now_line))
        return True

    report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha=head_sha,
        prev_sha=prev_sha,
        initial_delay_seconds=0.0,
        retry_delay_seconds=0.0,
        health_wait_seconds=1.0,
        health_poll_seconds=0.05,
        reprobe_settle_seconds=0.0,
        dry_run=False,
        repo_root=tmp_path,
        heroku_app="bainluck",
        heroku_api_key="secret-key",
        repo="alexander-bain/bainluck",
        now_issue=13580,
        run_url="https://github.com/o/r/actions/runs/555",
        http_get=fake_get,
        sleep_fn=lambda _: None,
        heroku_list_fn=fake_list,
        heroku_rollback_fn=fake_rollback,
        gh_post_fn=fake_post,
    )
    assert report.verdict == "rolled_back"
    assert report.rollback_version == 6619
    assert report.reprobe_passed is True
    assert report.alert_posted is True
    assert state["rollback_calls"] == [("bainluck", "rel-old")]
    assert len(state["alerts"]) == 1
    repo, issue, title, body, now_line = state["alerts"][0]
    assert repo == "alexander-bain/bainluck" and issue == 13580
    assert title == f"URGENT: release `{head_sha[:8]}` rolled back"
    assert "v6619" in now_line and "re-probe PASS" in now_line and "HOLD" in now_line

    # CLI exits non-zero when --execute triggers a rollback so master alarms fire.
    monkeypatch.setattr(mod, "run_smoke_check", lambda **kwargs: report)
    assert mod.main(["--execute", "--expected-sha", head_sha]) == 1


def test_execute_mode_refuses_double_rollback_failed_prior_and_superseded_release():
    mod = _load_module()
    bad_histories = [
        [
            {"id": "r2", "version": 102, "status": "succeeded", "description": "Rollback to v100"},
            {"id": "r1", "version": 100, "status": "succeeded", "description": "Deploy old11111"},
        ],
        [
            {"id": "r2", "version": 102, "status": "succeeded", "description": "Deploy new22222"},
            {"id": "r1", "version": 101, "status": "failed", "description": "Deploy old11111"},
        ],
        [
            {"id": "r2", "version": 102, "status": "succeeded", "description": "Deploy fff99999"},
            {"id": "r1", "version": 101, "status": "succeeded", "description": "Deploy old11111"},
        ],
        [
            {"id": "r2", "version": 102, "status": "succeeded", "description": "Set FOO config vars"},
            {"id": "r1", "version": 101, "status": "succeeded", "description": "Deploy new22222"},
        ],
    ]
    for releases in bad_histories:
        rollback_called = False
        alerts = []

        def no_rollback(app: str, key: str, rid: str):
            nonlocal rollback_called
            rollback_called = True
            return {}

        report = mod.run_smoke_check(
            base_url="http://standin.local",
            expected_sha="new22222abcdef12",
            initial_delay_seconds=0.0,
            retry_delay_seconds=0.0,
            skip_health_wait=True,
            dry_run=False,
            heroku_app="bainluck",
            heroku_api_key="secret-key",
            repo="alexander-bain/bainluck",
            now_issue=13580,
            http_get=lambda u, t: (500, '{"detail":"boom"}'),
            sleep_fn=lambda _: None,
            heroku_list_fn=lambda a, k: releases,
            heroku_rollback_fn=no_rollback,
            gh_post_fn=lambda r, i, title, body, line: alerts.append(line) or True,
        )
        assert report.verdict == "alert_only"
        assert rollback_called is False
        assert len(alerts) == 1 and "rollback refused" in alerts[0]


def test_execute_mode_migration_refusal_posts_alert_without_rollback(tmp_path: Path):
    mod = _load_module()
    rollback_called = False
    alerts = []
    report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha="new22222abcdef12",
        initial_delay_seconds=0.0,
        retry_delay_seconds=0.0,
        skip_health_wait=True,
        migrations_changed=True,
        dry_run=False,
        heroku_app="bainluck",
        heroku_api_key="secret-key",
        repo="alexander-bain/bainluck",
        now_issue=13580,
        http_get=lambda u, t: (500, '{"detail":"boom"}'),
        sleep_fn=lambda _: None,
        heroku_list_fn=lambda a, k: [],
        heroku_rollback_fn=lambda a, k, rid: (_ for _ in ()).throw(AssertionError("must not roll back")),
        gh_post_fn=lambda r, i, title, body, line: alerts.append(line) or True,
    )
    assert report.verdict == "alert_only"
    assert rollback_called is False
    assert len(alerts) == 1 and "migration changed" in alerts[0]


def test_default_health_wait_handles_preboot_cutover():
    mod = _load_module()
    assert mod.DEFAULT_HEALTH_WAIT_SECONDS >= 360.0

    clock = 0.0
    sleeps: list[float] = []
    endpoint_paths: list[str] = []

    def fake_sleep(seconds: float) -> None:
        nonlocal clock
        sleeps.append(seconds)
        clock += seconds

    def fake_get(url: str, timeout: float):
        if url.endswith("/api/health"):
            commit = "new22222" if clock >= 200.0 else "old11111"
            return 200, json.dumps({"status": "ok", "commit": commit})
        endpoint_paths.append(url)
        if "/api/feed" in url:
            return 200, '{"items":[{"id":1}]}'
        return 200, '{"events":[{"id":2}]}'

    report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha="new22222abcdef12",
        initial_delay_seconds=60.0,
        retry_delay_seconds=30.0,
        http_get=fake_get,
        sleep_fn=fake_sleep,
        monotonic_fn=lambda: clock,
    )
    assert report.verdict == "passed"
    assert report.health_commit == "new22222"
    assert "PASS:" in report.summary
    assert "commit read=new22222, expected=new22222" in report.summary
    assert len(endpoint_paths) == 2


def test_health_commit_mismatch_after_full_wait_returns_failed_never_pass_or_inconclusive():
    mod = _load_module()
    for failing_endpoints in (False, True):
        clock = 0.0
        sleeps: list[float] = []
        probed_endpoints: list[str] = []

        def fake_sleep(seconds: float) -> None:
            nonlocal clock
            sleeps.append(seconds)
            clock += seconds

        def fake_get(url: str, timeout: float):
            if url.endswith("/api/health"):
                return 200, '{"status":"ok","commit":"old11111"}'
            probed_endpoints.append(url)
            return (500, '{"detail":"boom"}') if failing_endpoints else (200, '{"items":[{"id":1}]}')

        report = mod.run_smoke_check(
            base_url="http://standin.local",
            expected_sha="new22222abcdef12",
            initial_delay_seconds=60.0,
            http_get=fake_get,
            sleep_fn=fake_sleep,
            monotonic_fn=lambda: clock,
        )
        assert report.verdict == "failed"
        assert report.health_commit == "old11111"
        assert report.endpoints == ()
        assert probed_endpoints == []
        assert sum(sleeps) >= 360.0
        assert report.summary.startswith("FAIL:")
        assert "INCONCLUSIVE" not in report.summary
        assert "commit read=old11111, expected=new22222" in report.summary
        assert "PASS" not in report.summary.upper()
        assert "would roll back" not in report.summary.lower()


def test_health_unanswered_or_5xx_after_full_wait_triggers_rollback_under_311a_guards(tmp_path: Path):
    """Ruling 394 Change 2: health answering 5xx or unreachable past wait rolls back under 311: A."""
    mod = _load_module()
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True, capture_output=True)
    app_file = tmp_path / "backend" / "app" / "x.py"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "old"], check=True, capture_output=True)
    prev_sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    app_file.write_text("x = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "new"], check=True, capture_output=True)
    head_sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()

    # Case 1 (dry-run): poll 1 sees 200 old commit, then timeouts -> clears stale old commit and triggers rollback.
    clock = 0.0
    sleeps: list[float] = []
    polls = {"n": 0}

    def fake_sleep(seconds: float) -> None:
        nonlocal clock
        sleeps.append(seconds)
        clock += seconds

    def fake_get_stale_then_timeout(url: str, timeout: float):
        if url.endswith("/api/health"):
            polls["n"] += 1
            if polls["n"] == 1:
                return 200, json.dumps({"status": "ok", "commit": prev_sha[:8]})
            raise TimeoutError("booting")
        raise AssertionError(f"endpoint should not be probed when health never answered: {url}")

    dry_report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha=head_sha,
        prev_sha=prev_sha,
        prior_release_state="ok",
        repo_root=tmp_path,
        initial_delay_seconds=60.0,
        http_get=fake_get_stale_then_timeout,
        sleep_fn=fake_sleep,
        monotonic_fn=lambda: clock,
    )
    assert dry_report.verdict == "would_roll_back"
    assert dry_report.health_commit is None
    assert sum(sleeps) >= 360.0
    assert "would roll back" in dry_report.summary.lower()

    mig_report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha=head_sha,
        prev_sha=prev_sha,
        prior_release_state="ok",
        migrations_changed=True,
        initial_delay_seconds=0.0,
        health_wait_seconds=1.0,
        health_poll_seconds=0.0,
        http_get=lambda u, t: (503, '{"detail":"down"}'),
        sleep_fn=lambda _: None,
    )
    assert mig_report.verdict == "alert_only"

    # Case 2 (execute): health 503 past wait executes rollback and re-probes; migration refusal stays alert_only.
    state = {"phase": "broken", "rollbacks": [], "alerts": []}

    def fake_get_503(url: str, timeout: float):
        if state["phase"] == "broken":
            return 503, '{"detail":"down"}'
        if url.endswith("/api/health"):
            return 200, json.dumps({"status": "ok", "commit": prev_sha[:8]})
        if "/api/feed" in url:
            return 200, '{"items":[{"id":1}]}'
        return 200, '{"events":[{"id":2}]}'

    releases = [
        {"id": "rel-new", "version": 6620, "status": "succeeded", "description": f"Deploy {head_sha[:8]}"},
        {"id": "rel-old", "version": 6619, "status": "succeeded", "description": f"Deploy {prev_sha[:8]}"},
    ]

    def fake_rollback_503(app: str, key: str, rid: str):
        state["rollbacks"].append(rid)
        state["phase"] = "rolled_back"
        return {"id": "rel-rb", "version": 6621}

    exec_report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha=head_sha,
        prev_sha=prev_sha,
        initial_delay_seconds=0.0,
        retry_delay_seconds=0.0,
        health_wait_seconds=1.0,
        health_poll_seconds=0.0,
        reprobe_settle_seconds=0.0,
        dry_run=False,
        repo_root=tmp_path,
        heroku_app="bainluck",
        heroku_api_key="secret-key",
        repo="alexander-bain/bainluck",
        now_issue=13580,
        http_get=fake_get_503,
        sleep_fn=lambda _: None,
        heroku_list_fn=lambda a, k: releases,
        heroku_rollback_fn=fake_rollback_503,
        gh_post_fn=lambda r, i, title, body, line: state["alerts"].append(line) or True,
    )
    assert exec_report.verdict == "rolled_back"
    assert state["rollbacks"] == ["rel-old"]
    assert len(state["alerts"]) == 1

    # Case 3 (execute + old commit 200): release did not take -> alert, no rollback.
    old_rollbacks: list[str] = []
    old_alerts: list[str] = []
    old_report = mod.run_smoke_check(
        base_url="http://standin.local",
        expected_sha=head_sha,
        prev_sha=prev_sha,
        initial_delay_seconds=0.0,
        retry_delay_seconds=0.0,
        health_wait_seconds=1.0,
        health_poll_seconds=0.0,
        dry_run=False,
        heroku_app="bainluck",
        heroku_api_key="secret-key",
        repo="alexander-bain/bainluck",
        now_issue=13580,
        http_get=lambda u, t: (200, json.dumps({"status": "ok", "commit": prev_sha[:8]})),
        sleep_fn=lambda _: None,
        heroku_list_fn=lambda a, k: releases,
        heroku_rollback_fn=lambda a, k, rid: old_rollbacks.append(rid) or {},
        gh_post_fn=lambda r, i, title, body, line: old_alerts.append(line) or True,
    )
    assert old_report.verdict == "failed"
    assert old_report.alert_posted is True
    assert old_rollbacks == []
    assert len(old_alerts) == 1 and "not auto-rolled back" in old_alerts[0]


def test_cli_exits_nonzero_when_commit_never_matches_even_under_dry_run(monkeypatch):
    mod = _load_module()
    failed_report = mod.SmokeReport(
        verdict="failed",
        endpoints=(),
        changed_migrations=(),
        prior_release_state="ok",
        expected_sha="new22222abcdef12",
        prev_sha="old11111",
        health_commit="old11111",
        summary="FAIL: /api/health did not serve expected commit within 360s (commit read=old11111, expected=new22222; dry-run; no rollback).",
    )
    monkeypatch.setattr(mod, "run_smoke_check", lambda **kwargs: failed_report)
    exit_code = mod.main(
        [
            "--dry-run",
            "--base-url",
            "http://standin.local",
            "--expected-sha",
            "new22222abcdef12",
        ]
    )
    assert exit_code == 1
