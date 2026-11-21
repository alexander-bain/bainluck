#!/usr/bin/env python3
"""Post-deploy public smoke check and rollback dry-run planner (#13283, Ruling 311: A).

Dry-run only: verifies Discover and the league-scoped NBA games list after a
Heroku release (plus migration and double-rollback guards) and reports what it
would do — including the exact phrase ``would roll back`` — without ever
executing a Heroku rollback or mutating configuration.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.bainluck.com"
DEFAULT_INITIAL_DELAY_SECONDS = 60.0
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_HEALTH_WAIT_SECONDS = 120.0
DEFAULT_HEALTH_POLL_SECONDS = 10.0

KILL_SWITCH_ENV = "AUTO_ROLLBACK_ENABLED"
DISABLED_FLAG_VALUES = frozenset({"0", "false", "off", "no"})
BLOCKED_PRIOR_STATES = frozenset({"rolled_back", "failed"})


@dataclass(frozen=True)
class EndpointSpec:
    """Public read endpoint validated after a release."""

    label: str
    path: str
    list_key: str


DEFAULT_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(label="Discover", path="/api/feed?machinery=1&limit=20", list_key="items"),
    EndpointSpec(
        label="Games list",
        path="/api/events?sport=basketball_nba&limit=20",
        list_key="events",
    ),
)


@dataclass(frozen=True)
class ProbeAttempt:
    """Single HTTP attempt against a post-deploy read endpoint."""

    attempt: int
    status: int | None
    kind: str  # "ok", "empty_list", "http_error", "timeout", "network_error", "invalid_json"
    detail: str


@dataclass(frozen=True)
class EndpointResult:
    """Aggregated outcome across retries for one endpoint."""

    spec: EndpointSpec
    outcome: str  # "ok", "empty_list", "failed"
    attempts: tuple[ProbeAttempt, ...]


@dataclass(frozen=True)
class SmokeReport:
    """Full decision record for a dry-run smoke check."""

    verdict: str  # "disabled", "passed", "empty_list_report", "alert_only", "would_roll_back"
    endpoints: tuple[EndpointResult, ...]
    changed_migrations: tuple[str, ...]
    prior_release_state: str
    expected_sha: str
    prev_sha: str
    health_commit: str | None
    summary: str


def is_auto_rollback_enabled(env_value: str | None) -> bool:
    """Return False when AUTO_ROLLBACK_ENABLED is explicitly disabled."""
    if env_value is None:
        return True
    normalized = env_value.strip().lower()
    if not normalized:
        return True
    return normalized not in DISABLED_FLAG_VALUES


def _short_sha(sha: str) -> str:
    clean = sha.strip()
    return clean[:8] if clean else "unknown"


def _sha_matches(health_commit: str | None, expected_sha: str) -> bool:
    if not health_commit or not expected_sha:
        return False
    live = health_commit.strip().lower()
    expected = expected_sha.strip().lower()
    if len(live) < 7 or len(expected) < 7:
        return live == expected
    return expected.startswith(live) or live.startswith(expected)


def default_http_get(url: str, timeout: float) -> tuple[int, str]:
    """Perform a read-only GET request and return (status_code, body_text)."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "bainluck-post-deploy-smoke-dry-run/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def wait_for_health_commit(
    *,
    base_url: str,
    expected_sha: str,
    timeout_seconds: float,
    health_wait_seconds: float,
    poll_interval_seconds: float,
    http_get: Callable[[str, float], tuple[int, str]] = default_http_get,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> str | None:
    """Poll /api/health until expected_sha appears or health_wait_seconds expires."""
    url = f"{base_url.rstrip('/')}/api/health"
    deadline = monotonic_fn() + max(0.0, health_wait_seconds)
    last_commit: str | None = None
    while True:
        try:
            status, body = http_get(url, min(timeout_seconds, 15.0))
            if status == 200:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    commit = payload.get("commit")
                    if isinstance(commit, str) and commit.strip():
                        last_commit = commit.strip()
                        if not expected_sha or _sha_matches(last_commit, expected_sha):
                            return last_commit
        except (OSError, ValueError, TimeoutError):
            pass
        if monotonic_fn() >= deadline or poll_interval_seconds <= 0:
            return last_commit
        sleep_fn(min(poll_interval_seconds, max(0.0, deadline - monotonic_fn())))


def probe_endpoint_once(
    base_url: str,
    spec: EndpointSpec,
    *,
    attempt: int,
    timeout_seconds: float,
    http_get: Callable[[str, float], tuple[int, str]],
) -> ProbeAttempt:
    """Probe one public URL once and classify the response without swallowing errors."""
    url = f"{base_url.rstrip('/')}{spec.path}"
    try:
        status, body = http_get(url, timeout_seconds)
    except TimeoutError as exc:
        return ProbeAttempt(attempt=attempt, status=None, kind="timeout", detail=f"timeout: {exc}")
    except (OSError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", exc)
        kind = "timeout" if isinstance(reason, TimeoutError) else "network_error"
        return ProbeAttempt(attempt=attempt, status=None, kind=kind, detail=f"{kind}: {reason}")

    if status != 200:
        return ProbeAttempt(
            attempt=attempt,
            status=status,
            kind="http_error",
            detail=f"HTTP {status}",
        )

    try:
        payload: Any = json.loads(body)
    except ValueError as exc:
        return ProbeAttempt(
            attempt=attempt,
            status=status,
            kind="invalid_json",
            detail=f"HTTP 200 invalid JSON: {exc}",
        )

    if not isinstance(payload, dict) or not isinstance(payload.get(spec.list_key), list):
        return ProbeAttempt(
            attempt=attempt,
            status=status,
            kind="invalid_json",
            detail=f"HTTP 200 missing list field '{spec.list_key}'",
        )

    rows = payload[spec.list_key]
    if len(rows) == 0:
        return ProbeAttempt(
            attempt=attempt,
            status=status,
            kind="empty_list",
            detail=f"HTTP 200 with empty '{spec.list_key}' list (0 items)",
        )
    return ProbeAttempt(
        attempt=attempt,
        status=status,
        kind="ok",
        detail=f"HTTP 200 ({len(rows)} items)",
    )


def probe_endpoint_with_retries(
    base_url: str,
    spec: EndpointSpec,
    *,
    retries: int,
    retry_delay_seconds: float,
    timeout_seconds: float,
    http_get: Callable[[str, float], tuple[int, str]],
    sleep_fn: Callable[[float], None],
) -> EndpointResult:
    """Try one endpoint up to ``retries`` times and distinguish errors from empty 200 lists."""
    attempts: list[ProbeAttempt] = []
    total_tries = max(1, retries)
    for idx in range(1, total_tries + 1):
        result = probe_endpoint_once(
            base_url,
            spec,
            attempt=idx,
            timeout_seconds=timeout_seconds,
            http_get=http_get,
        )
        attempts.append(result)
        if result.kind == "ok":
            return EndpointResult(spec=spec, outcome="ok", attempts=tuple(attempts))
        if idx < total_tries and retry_delay_seconds > 0:
            sleep_fn(retry_delay_seconds)

    if any(item.kind == "empty_list" for item in attempts):
        return EndpointResult(spec=spec, outcome="empty_list", attempts=tuple(attempts))
    return EndpointResult(spec=spec, outcome="failed", attempts=tuple(attempts))


def detect_changed_migrations(
    *,
    repo_root: Path,
    prev_sha: str,
    expected_sha: str,
    explicit_flag: bool = False,
) -> tuple[str, ...]:
    """Return changed Alembic migration files between prev_sha and expected_sha."""
    if explicit_flag:
        return ("--migrations-changed",)
    prev_clean = prev_sha.strip()
    head_clean = expected_sha.strip()
    if not prev_clean or not head_clean or prev_clean == head_clean:
        return ()
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            f"{prev_clean}..{head_clean}",
            "--",
            "backend/alembic/versions/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # Fail closed on migration detection ambiguity: alert instead of blind rollback.
        return ("git-diff-unavailable",)
    files = tuple(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return files


def read_prior_release_state(explicit_state: str, state_file: Path | None) -> str:
    """Resolve prior release state from CLI option or optional JSON state file."""
    clean = explicit_state.strip().lower()
    if clean:
        return clean
    if state_file is not None and state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "unknown"
        if isinstance(data, dict):
            raw = str(data.get("prior_release_state") or data.get("status") or "ok").strip().lower()
            return raw or "ok"
    return "ok"


def _failing_summary_lines(endpoints: tuple[EndpointResult, ...]) -> list[str]:
    lines: list[str] = []
    for ep in endpoints:
        last = ep.attempts[-1] if ep.attempts else None
        status_text = last.detail if last is not None else "no attempts"
        lines.append(f"- {ep.spec.label} ({ep.spec.path}): {ep.outcome} [{status_text}]")
    return lines


def run_smoke_check(
    *,
    base_url: str = DEFAULT_BASE_URL,
    expected_sha: str = "",
    prev_sha: str = "",
    initial_delay_seconds: float = DEFAULT_INITIAL_DELAY_SECONDS,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    health_wait_seconds: float = DEFAULT_HEALTH_WAIT_SECONDS,
    health_poll_seconds: float = DEFAULT_HEALTH_POLL_SECONDS,
    skip_health_wait: bool = False,
    migrations_changed: bool = False,
    prior_release_state: str = "",
    prior_state_file: Path | None = None,
    auto_rollback_env: str | None = None,
    repo_root: Path | None = None,
    endpoints: tuple[EndpointSpec, ...] = DEFAULT_ENDPOINTS,
    http_get: Callable[[str, float], tuple[int, str]] = default_http_get,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> SmokeReport:
    """Run the post-deploy smoke verification and produce a dry-run verdict."""
    if auto_rollback_env is None:
        auto_rollback_env = os.environ.get(KILL_SWITCH_ENV)
    resolved_prior_state = read_prior_release_state(prior_release_state, prior_state_file)
    resolved_root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]
    changed_migrations = detect_changed_migrations(
        repo_root=resolved_root,
        prev_sha=prev_sha,
        expected_sha=expected_sha,
        explicit_flag=migrations_changed,
    )

    if not is_auto_rollback_enabled(auto_rollback_env):
        return SmokeReport(
            verdict="disabled",
            endpoints=(),
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=None,
            summary=f"{KILL_SWITCH_ENV} is disabled ({auto_rollback_env!r}); skipping post-deploy check (dry-run).",
        )

    health_commit: str | None = None
    if expected_sha and not skip_health_wait:
        health_commit = wait_for_health_commit(
            base_url=base_url,
            expected_sha=expected_sha,
            timeout_seconds=timeout_seconds,
            health_wait_seconds=health_wait_seconds,
            poll_interval_seconds=health_poll_seconds,
            http_get=http_get,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )

    if initial_delay_seconds > 0:
        sleep_fn(initial_delay_seconds)

    results = tuple(
        probe_endpoint_with_retries(
            base_url,
            spec,
            retries=retries,
            retry_delay_seconds=retry_delay_seconds,
            timeout_seconds=timeout_seconds,
            http_get=http_get,
            sleep_fn=sleep_fn,
        )
        for spec in endpoints
    )

    failed = tuple(r for r in results if r.outcome == "failed")
    empties = tuple(r for r in results if r.outcome == "empty_list")
    detail_block = "\n".join(_failing_summary_lines(results))

    if not failed and not empties:
        return SmokeReport(
            verdict="passed",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=(
                "PASS: post-deploy public read checks succeeded (dry-run; no rollback needed).\n"
                f"{detail_block}"
            ),
        )

    if not failed and empties:
        return SmokeReport(
            verdict="empty_list_report",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=(
                "REPORT ONLY: endpoint answered HTTP 200 with an empty list; "
                "errors and empty lists are different things — no rollback (dry-run).\n"
                f"{detail_block}"
            ),
        )

    short_sha = _short_sha(expected_sha or (health_commit or ""))
    planned_issue_title = f"URGENT: release `{short_sha}` rolled back"

    if changed_migrations:
        mig_list = ", ".join(changed_migrations)
        return SmokeReport(
            verdict="alert_only",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=(
                f"alert only: database migration changed ({mig_list}); "
                "automatic rollback refused (dry-run, no Heroku call).\n"
                f"{detail_block}"
            ),
        )

    if resolved_prior_state in BLOCKED_PRIOR_STATES or resolved_prior_state == "unknown":
        return SmokeReport(
            verdict="alert_only",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=(
                f"alert only: prior release state is '{resolved_prior_state}'; "
                "never roll back twice / over failed prior release — automatic rollback refused "
                "(dry-run, no Heroku call).\n"
                f"{detail_block}"
            ),
        )

    return SmokeReport(
        verdict="would_roll_back",
        endpoints=results,
        changed_migrations=changed_migrations,
        prior_release_state=resolved_prior_state,
        expected_sha=expected_sha,
        prev_sha=prev_sha,
        health_commit=health_commit,
        summary=(
            f"would roll back release {short_sha} (dry-run only; NO Heroku call made)\n"
            f"planned_issue_title: {planned_issue_title}\n"
            f"{detail_block}"
        ),
    )


def run_self_test_500() -> SmokeReport:
    """Spin up a local stand-in server returning HTTP 500 and verify dry-run reports 'would roll back'."""

    class _StandIn500Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/health"):
                body = json.dumps({"status": "ok", "commit": "standin500"}).encode("utf-8")
                self.send_response(200)
            else:
                body = json.dumps({"detail": "simulated stand-in 500"}).encode("utf-8")
                self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _StandIn500Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = run_smoke_check(
            base_url=f"http://127.0.0.1:{port}",
            expected_sha="standin500abcdef",
            prev_sha="",
            initial_delay_seconds=0.0,
            retries=3,
            retry_delay_seconds=0.0,
            timeout_seconds=5.0,
            skip_health_wait=True,
            auto_rollback_env="true",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    if report.verdict != "would_roll_back" or "would roll back" not in report.summary:
        raise AssertionError(f"Expected 'would roll back' from stand-in 500 self-test, got: {report}")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry-run mode only (never calls Heroku).",
    )
    parser.add_argument(
        "--self-test-500",
        action="store_true",
        help="Run a local HTTP 500 stand-in server and verify dry-run reports 'would roll back'.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--prev-sha", default="")
    parser.add_argument("--initial-delay-seconds", type=float, default=DEFAULT_INITIAL_DELAY_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--retry-delay-seconds", type=float, default=DEFAULT_RETRY_DELAY_SECONDS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--health-wait-seconds", type=float, default=DEFAULT_HEALTH_WAIT_SECONDS)
    parser.add_argument("--health-poll-seconds", type=float, default=DEFAULT_HEALTH_POLL_SECONDS)
    parser.add_argument("--skip-health-wait", action="store_true")
    parser.add_argument("--migrations-changed", action="store_true")
    parser.add_argument("--prior-release-state", default="")
    parser.add_argument("--prior-state-file", type=Path, default=None)
    parser.add_argument(
        "--fail-on-would-rollback",
        action="store_true",
        help="Exit non-zero if verdict is 'would_roll_back' or 'alert_only'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.self_test_500:
        report = run_self_test_500()
        print("self-test-500 OK:", report.summary)
        return 0

    report = run_smoke_check(
        base_url=args.base_url,
        expected_sha=args.expected_sha,
        prev_sha=args.prev_sha,
        initial_delay_seconds=args.initial_delay_seconds,
        retries=args.retries,
        retry_delay_seconds=args.retry_delay_seconds,
        timeout_seconds=args.timeout_seconds,
        health_wait_seconds=args.health_wait_seconds,
        health_poll_seconds=args.health_poll_seconds,
        skip_health_wait=args.skip_health_wait,
        migrations_changed=args.migrations_changed,
        prior_release_state=args.prior_release_state,
        prior_state_file=args.prior_state_file,
    )
    print(report.summary)
    if args.fail_on_would_rollback and report.verdict in {"would_roll_back", "alert_only"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
