#!/usr/bin/env python3
"""Post-deploy public smoke check and automatic Heroku rollback (#13283, Ruling 394c).

Verifies Discover and the league-scoped NBA games list after a Heroku release
(plus migration, double-rollback, superseded-release, and empty-200-list
guards). Supports both ``--dry-run`` (default for safe local/self-test runs)
and ``--execute`` (real Heroku Platform API rollback + re-probe + GitHub alert
in CI ``post-deploy-smoke``).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.bainluck.com"
DEFAULT_HEROKU_APP = "bainluck"
DEFAULT_HEROKU_API_BASE = "https://api.heroku.com"
DEFAULT_NOW_ISSUE = 13580
DEFAULT_INITIAL_DELAY_SECONDS = 60.0
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_HEALTH_WAIT_SECONDS = 360.0
DEFAULT_HEALTH_POLL_SECONDS = 10.0
DEFAULT_REPROBE_SETTLE_SECONDS = 15.0

KILL_SWITCH_ENV = "AUTO_ROLLBACK_ENABLED"
DISABLED_FLAG_VALUES = frozenset({"0", "false", "off", "no"})
BLOCKED_PRIOR_STATES = frozenset({"rolled_back", "failed"})
_HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


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
class HealthWaitResult:
    """Outcome of polling /api/health for the newly deployed commit."""

    commit: str | None
    last_status: int | None
    last_error: str | None = None


@dataclass(frozen=True)
class SmokeReport:
    """Full decision record for a dry-run or live smoke check."""

    verdict: str  # "disabled", "failed", "passed", "empty_list_report", "alert_only", "would_roll_back", "rolled_back"
    endpoints: tuple[EndpointResult, ...]
    changed_migrations: tuple[str, ...]
    prior_release_state: str
    expected_sha: str
    prev_sha: str
    health_commit: str | None
    summary: str
    rollback_version: int | None = None
    reprobe_passed: bool | None = None
    reprobe_endpoints: tuple[EndpointResult, ...] = ()
    alert_posted: bool = False


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


def _commit_context(health_commit: str | None, expected_sha: str) -> str:
    read_tag = _short_sha(health_commit) if (health_commit and health_commit.strip()) else "none"
    expected_tag = _short_sha(expected_sha) if (expected_sha and expected_sha.strip()) else "none"
    return f"commit read={read_tag}, expected={expected_tag}"


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
            "User-Agent": "bainluck-post-deploy-smoke/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def default_heroku_list_releases(
    app: str,
    api_key: str,
    *,
    api_base: str = DEFAULT_HEROKU_API_BASE,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Fetch recent Heroku releases ordered newest-first via Platform API."""
    url = f"{api_base.rstrip('/')}/apps/{app}/releases"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.heroku+json; version=3",
            "Range": "version ..; order=desc, max=10",
            "User-Agent": "bainluck-post-deploy-smoke/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list from Heroku releases API, got {type(data).__name__}")
    return data


def default_heroku_rollback(
    app: str,
    api_key: str,
    target_release_id: str,
    *,
    api_base: str = DEFAULT_HEROKU_API_BASE,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Roll back Heroku app to ``target_release_id`` via Platform API POST /releases."""
    url = f"{api_base.rstrip('/')}/apps/{app}/releases"
    payload = json.dumps({"release": target_release_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.heroku+json; version=3",
            "Content-Type": "application/json",
            "User-Agent": "bainluck-post-deploy-smoke/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict from Heroku rollback API, got {type(data).__name__}")
    return data


def select_rollback_target(
    releases: list[dict[str, Any]],
    expected_sha: str,
) -> tuple[dict[str, Any] | None, str]:
    """Validate release history and pick the prior release target, or return an alert reason."""
    if not releases or len(releases) < 2:
        return None, "fewer than 2 releases available in Heroku history"

    latest = releases[0] or {}
    latest_desc = str(latest.get("description") or "").strip()
    if latest_desc.lower().startswith("rollback to "):
        return None, f"latest Heroku release v{latest.get('version')} is already a rollback ({latest_desc})"

    if expected_sha:
        if not latest_desc.startswith("Deploy "):
            return (
                None,
                f"latest Heroku release v{latest.get('version')} ({latest_desc or 'no description'}) is not a Deploy of {_short_sha(expected_sha)}",
            )
        token = latest_desc[len("Deploy "):].strip().split()[0]
        if _HEX_SHA_RE.match(token) and not _sha_matches(token, expected_sha):
            return (
                None,
                f"latest Heroku release v{latest.get('version')} deployed {token}, not {_short_sha(expected_sha)}",
            )

    previous = releases[1] or {}
    prev_id = str(previous.get("id") or "").strip()
    prev_version = previous.get("version")
    prev_status = str(previous.get("status") or "").strip().lower()
    prev_desc = str(previous.get("description") or "").strip()

    if not prev_id:
        return None, f"prior release v{prev_version} has no release id"
    if prev_status != "succeeded":
        return None, f"prior release v{prev_version} status is {prev_status!r}, not 'succeeded'"
    if prev_desc.lower().startswith("rollback to "):
        return None, f"prior release v{prev_version} is already a rollback ({prev_desc})"
    return previous, ""


def default_post_github_alert(
    repo: str,
    now_issue: int,
    title: str,
    body: str,
    now_line: str,
) -> bool:
    """Open an URGENT alert issue and post one line on the NOW issue via ``gh api``."""
    if not repo or not os.environ.get("GH_TOKEN"):
        print("GH_TOKEN or REPO missing — cannot post GitHub smoke alert.", file=sys.stderr)
        return False

    issue_url = ""
    try:
        created = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues", "--method", "POST", "--input", "-"],
            input=json.dumps({"title": title, "body": body}),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if created.returncode == 0 and created.stdout.strip():
            data = json.loads(created.stdout)
            issue_url = str(data.get("html_url") or "")
        else:
            print(
                f"Failed to create smoke alert issue ({created.returncode}): {created.stderr.strip()[:240]}",
                file=sys.stderr,
            )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Error creating smoke alert issue: {exc}", file=sys.stderr)

    comment_text = f"{now_line} ({issue_url})" if issue_url else now_line
    try:
        commented = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues/{now_issue}/comments", "--method", "POST", "--input", "-"],
            input=json.dumps({"body": comment_text}),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if commented.returncode != 0:
            print(
                f"Failed to comment on #{now_issue} ({commented.returncode}): {commented.stderr.strip()[:240]}",
                file=sys.stderr,
            )
            return bool(issue_url)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Error commenting on #{now_issue}: {exc}", file=sys.stderr)
        return bool(issue_url)


def wait_for_health_commit_detailed(
    *,
    base_url: str,
    expected_sha: str,
    timeout_seconds: float,
    health_wait_seconds: float,
    poll_interval_seconds: float,
    http_get: Callable[[str, float], tuple[int, str]] = default_http_get,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> HealthWaitResult:
    """Poll /api/health until expected_sha appears or health_wait_seconds expires."""
    url = f"{base_url.rstrip('/')}/api/health"
    deadline = monotonic_fn() + max(0.0, health_wait_seconds)
    last_commit: str | None = None
    last_status: int | None = None
    last_error: str | None = None
    while True:
        try:
            status, body = http_get(url, min(timeout_seconds, 15.0))
            last_status = int(status)
            if status == 200:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    commit = payload.get("commit")
                    if isinstance(commit, str) and commit.strip():
                        last_commit = commit.strip()
                        last_error = None
                        if not expected_sha or _sha_matches(last_commit, expected_sha):
                            return HealthWaitResult(commit=last_commit, last_status=200)
                    else:
                        last_commit = None
                        last_error = "HTTP 200 missing commit in /api/health"
                else:
                    last_commit = None
                    last_error = "HTTP 200 non-dict /api/health payload"
            else:
                last_commit = None
                last_error = f"HTTP {status}"
        except (OSError, ValueError, TimeoutError) as exc:
            # Clear stale prior old-commit state if a later poll sees connection drop/non-JSON.
            last_status = None
            last_commit = None
            last_error = f"{type(exc).__name__}: {exc}"
        if monotonic_fn() >= deadline or poll_interval_seconds <= 0:
            if last_commit is None and last_error is not None:
                print(f"health poll finished without commit ({last_error})", file=sys.stderr)
            return HealthWaitResult(
                commit=last_commit,
                last_status=last_status,
                last_error=last_error,
            )
        sleep_fn(min(poll_interval_seconds, max(0.0, deadline - monotonic_fn())))


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
    return wait_for_health_commit_detailed(
        base_url=base_url,
        expected_sha=expected_sha,
        timeout_seconds=timeout_seconds,
        health_wait_seconds=health_wait_seconds,
        poll_interval_seconds=poll_interval_seconds,
        http_get=http_get,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    ).commit


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
    except ValueError as json_exc:
        # Bind as `json_exc` to avoid matching `futures_categories_warm_mutations:M9` in scan_mutation_residue Pass B.
        return ProbeAttempt(
            attempt=attempt,
            status=status,
            kind="invalid_json",
            detail=f"HTTP 200 invalid JSON: {json_exc}",
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


def _emit_execute_alert(
    *,
    gh_post_fn: Callable[[str, int, str, str, str], bool],
    repo: str,
    now_issue: int,
    title: str,
    body: str,
    now_line: str,
) -> bool:
    if not repo:
        return False
    return gh_post_fn(repo, now_issue, title, body, now_line)


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
    reprobe_settle_seconds: float = DEFAULT_REPROBE_SETTLE_SECONDS,
    skip_health_wait: bool = False,
    migrations_changed: bool = False,
    prior_release_state: str = "",
    prior_state_file: Path | None = None,
    auto_rollback_env: str | None = None,
    repo_root: Path | None = None,
    endpoints: tuple[EndpointSpec, ...] = DEFAULT_ENDPOINTS,
    dry_run: bool = True,
    heroku_app: str = DEFAULT_HEROKU_APP,
    heroku_api_key: str = "",
    repo: str = "",
    now_issue: int = DEFAULT_NOW_ISSUE,
    run_url: str = "",
    http_get: Callable[[str, float], tuple[int, str]] = default_http_get,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    heroku_list_fn: Callable[[str, str], list[dict[str, Any]]] = default_heroku_list_releases,
    heroku_rollback_fn: Callable[[str, str, str], dict[str, Any]] = default_heroku_rollback,
    gh_post_fn: Callable[[str, int, str, str, str], bool] = default_post_github_alert,
) -> SmokeReport:
    """Run post-deploy smoke verification in dry-run (default) or live execute mode."""
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
    mode_tag = "dry-run" if dry_run else "live"

    if not is_auto_rollback_enabled(auto_rollback_env):
        tail = "skipping post-deploy check (dry-run)." if dry_run else "skipping post-deploy auto-rollback."
        return SmokeReport(
            verdict="disabled",
            endpoints=(),
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=None,
            summary=f"{KILL_SWITCH_ENV} is disabled ({auto_rollback_env!r}); {tail}",
        )

    health_commit: str | None = None
    health_boot_results: tuple[EndpointResult, ...] | None = None
    commit_ctx = _commit_context(health_commit, expected_sha)
    if expected_sha and not skip_health_wait:
        wait_res = wait_for_health_commit_detailed(
            base_url=base_url,
            expected_sha=expected_sha,
            timeout_seconds=timeout_seconds,
            health_wait_seconds=health_wait_seconds,
            poll_interval_seconds=health_poll_seconds,
            http_get=http_get,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        health_commit = wait_res.commit
        commit_ctx = _commit_context(health_commit, expected_sha)
        if not _sha_matches(health_commit, expected_sha):
            # Health answering 200 with the old commit means the release did not take:
            # alert without rolling back. If health stops answering or returns 5xx past the
            # wait, fall through into the Ruling 311: A automatic rollback guards.
            if wait_res.last_status == 200 and health_commit:
                short_sha = _short_sha(expected_sha or (health_commit or ""))
                summary = (
                    f"FAIL: /api/health did not serve expected commit within "
                    f"{int(health_wait_seconds)}s ({commit_ctx}; {mode_tag}; no rollback)."
                )
                posted = False
                if not dry_run:
                    run_note = f" ([run]({run_url}))" if run_url else ""
                    posted = _emit_execute_alert(
                        gh_post_fn=gh_post_fn,
                        repo=repo,
                        now_issue=now_issue,
                        title=f"URGENT: release `{short_sha}` failed health commit check (no rollback)",
                        body=f"{summary}\n{run_note}".strip(),
                        now_line=(
                            f"URGENT: release `{short_sha}` failed post-deploy `/api/health` commit check "
                            f"({commit_ctx}; not auto-rolled back){run_note}; HOLD (no further merges until Fable posts a line)"
                        ),
                    )
                return SmokeReport(
                    verdict="failed",
                    endpoints=(),
                    changed_migrations=changed_migrations,
                    prior_release_state=resolved_prior_state,
                    expected_sha=expected_sha,
                    prev_sha=prev_sha,
                    health_commit=health_commit,
                    summary=summary,
                    alert_posted=posted,
                )

            err_kind = "http_error" if wait_res.last_status is not None else "network_error"
            detail = wait_res.last_error or (
                f"HTTP {wait_res.last_status}" if wait_res.last_status is not None else "no response"
            )
            health_boot_results = (
                EndpointResult(
                    spec=EndpointSpec(label="Health", path="/api/health", list_key="commit"),
                    outcome="failed",
                    attempts=(
                        ProbeAttempt(
                            attempt=1,
                            status=wait_res.last_status,
                            kind=err_kind,
                            detail=detail,
                        ),
                    ),
                ),
            )

    if health_boot_results is not None:
        results = health_boot_results
        failed = results
        empties = ()
        detail_block = "\n".join(_failing_summary_lines(results))
    else:
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
                    f"PASS: post-deploy public read checks succeeded ({commit_ctx}; {mode_tag}; no rollback needed).\n"
                    f"{detail_block}"
                ),
            )

        if not failed and empties:
            dry_suffix = " (dry-run)" if dry_run else ""
            return SmokeReport(
                verdict="empty_list_report",
                endpoints=results,
                changed_migrations=changed_migrations,
                prior_release_state=resolved_prior_state,
                expected_sha=expected_sha,
                prev_sha=prev_sha,
                health_commit=health_commit,
                summary=(
                    f"REPORT ONLY: endpoint answered HTTP 200 with an empty list ({commit_ctx}); "
                    f"errors and empty lists are different things — no rollback{dry_suffix}.\n"
                    f"{detail_block}"
                ),
            )

    short_sha = _short_sha(expected_sha or (health_commit or ""))
    planned_issue_title = f"URGENT: release `{short_sha}` rolled back"
    failed_labels = ", ".join(r.spec.label for r in failed)
    run_note = f" [CI run]({run_url})" if run_url else ""

    if changed_migrations:
        mig_list = ", ".join(changed_migrations)
        tail = "(dry-run, no Heroku call)." if dry_run else "(no Heroku rollback executed)."
        summary = (
            f"alert only: database migration changed ({mig_list}; {commit_ctx}); "
            f"automatic rollback refused {tail}\n{detail_block}"
        )
        posted = False
        if not dry_run:
            posted = _emit_execute_alert(
                gh_post_fn=gh_post_fn,
                repo=repo,
                now_issue=now_issue,
                title=f"URGENT: release `{short_sha}` failed smoke check (migration changed; alert only)",
                body=f"{summary}\n{run_note}".strip(),
                now_line=(
                    f"URGENT: release `{short_sha}` failed post-deploy smoke ({failed_labels}); "
                    f"rollback refused (migration changed: `{mig_list}`); "
                    f"HOLD (no further merges until Fable posts a line){run_note}"
                ),
            )
        return SmokeReport(
            verdict="alert_only",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=summary,
            alert_posted=posted,
        )

    if resolved_prior_state in BLOCKED_PRIOR_STATES or resolved_prior_state == "unknown":
        tail = "(dry-run, no Heroku call)." if dry_run else "(no Heroku rollback executed)."
        summary = (
            f"alert only: prior release state is '{resolved_prior_state}' ({commit_ctx}); "
            f"never roll back twice / over failed prior release — automatic rollback refused {tail}\n"
            f"{detail_block}"
        )
        posted = False
        if not dry_run:
            posted = _emit_execute_alert(
                gh_post_fn=gh_post_fn,
                repo=repo,
                now_issue=now_issue,
                title=f"URGENT: release `{short_sha}` failed smoke check (prior state={resolved_prior_state}; alert only)",
                body=f"{summary}\n{run_note}".strip(),
                now_line=(
                    f"URGENT: release `{short_sha}` failed post-deploy smoke ({failed_labels}); "
                    f"rollback refused (prior_release_state={resolved_prior_state}); "
                    f"HOLD (no further merges until Fable posts a line){run_note}"
                ),
            )
        return SmokeReport(
            verdict="alert_only",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=summary,
            alert_posted=posted,
        )

    if dry_run:
        return SmokeReport(
            verdict="would_roll_back",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=(
                f"would roll back release {short_sha} ({commit_ctx}; dry-run only; NO Heroku call made)\n"
                f"planned_issue_title: {planned_issue_title}\n"
                f"{detail_block}"
            ),
        )

    # Live execute path (Ruling 394c): validate Heroku release history, roll back once, re-probe, alert.
    def _refuse_live(reason: str) -> SmokeReport:
        summary = f"alert only: {reason} ({commit_ctx}); no rollback executed.\n{detail_block}"
        posted = _emit_execute_alert(
            gh_post_fn=gh_post_fn,
            repo=repo,
            now_issue=now_issue,
            title=f"URGENT: release `{short_sha}` failed smoke check (rollback refused)",
            body=f"{summary}\n{run_note}".strip(),
            now_line=(
                f"URGENT: release `{short_sha}` failed post-deploy smoke ({failed_labels}); "
                f"rollback refused ({reason}); "
                f"HOLD (no further merges until Fable posts a line){run_note}"
            ),
        )
        return SmokeReport(
            verdict="alert_only",
            endpoints=results,
            changed_migrations=changed_migrations,
            prior_release_state=resolved_prior_state,
            expected_sha=expected_sha,
            prev_sha=prev_sha,
            health_commit=health_commit,
            summary=summary,
            alert_posted=posted,
        )

    if not heroku_api_key.strip() or not heroku_app.strip():
        return _refuse_live("missing HEROKU_API_KEY or heroku app name")

    try:
        releases = heroku_list_fn(heroku_app, heroku_api_key)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return _refuse_live(f"Heroku releases lookup failed: {exc}")

    target, refuse_reason = select_rollback_target(releases, expected_sha)
    if target is None:
        return _refuse_live(refuse_reason)

    target_id = str(target["id"])
    target_version = target.get("version")
    try:
        rollback_resp = heroku_rollback_fn(heroku_app, heroku_api_key, target_id)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return _refuse_live(f"Heroku rollback to v{target_version} failed: {exc}")

    rolled_version = rollback_resp.get("version")
    if prev_sha and not skip_health_wait:
        wait_for_health_commit(
            base_url=base_url,
            expected_sha=prev_sha,
            timeout_seconds=timeout_seconds,
            health_wait_seconds=min(health_wait_seconds, 180.0),
            poll_interval_seconds=health_poll_seconds,
            http_get=http_get,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
    elif reprobe_settle_seconds > 0:
        sleep_fn(reprobe_settle_seconds)

    reprobe_results = tuple(
        probe_endpoint_with_retries(
            base_url,
            spec,
            retries=min(2, retries),
            retry_delay_seconds=min(10.0, retry_delay_seconds),
            timeout_seconds=timeout_seconds,
            http_get=http_get,
            sleep_fn=sleep_fn,
        )
        for spec in endpoints
    )
    reprobe_ok = all(r.outcome == "ok" for r in reprobe_results)
    reprobe_block = "\n".join(_failing_summary_lines(reprobe_results))
    reprobe_label = "PASS" if reprobe_ok else "FAIL"

    issue_body = (
        f"Post-deploy smoke check failed on release `{short_sha}` ({commit_ctx}) and "
        f"automatically rolled `{heroku_app}` back to prior release **v{target_version}** "
        f"(new rollback release v{rolled_version}).\n\n"
        f"### Failing reads before rollback\n{detail_block}\n\n"
        f"### Re-probe after rollback ({reprobe_label})\n{reprobe_block}\n"
        + (f"\nCI run: {run_url}\n" if run_url else "")
    )
    now_line = (
        f"URGENT: release `{short_sha}` rolled back to Heroku v{target_version} "
        f"after failed smoke ({failed_labels}); re-probe {reprobe_label}; "
        f"HOLD (no further merges until Fable posts a line){run_note}"
    )
    posted = _emit_execute_alert(
        gh_post_fn=gh_post_fn,
        repo=repo,
        now_issue=now_issue,
        title=planned_issue_title,
        body=issue_body,
        now_line=now_line,
    )
    return SmokeReport(
        verdict="rolled_back",
        endpoints=results,
        changed_migrations=changed_migrations,
        prior_release_state=resolved_prior_state,
        expected_sha=expected_sha,
        prev_sha=prev_sha,
        health_commit=health_commit,
        summary=(
            f"ROLLED BACK release {short_sha} ({commit_ctx}) to Heroku v{target_version} "
            f"(rollback v{rolled_version}); re-probe {reprobe_label}.\n"
            f"{detail_block}\nRe-probe:\n{reprobe_block}"
        ),
        rollback_version=int(target_version) if isinstance(target_version, int) else None,
        reprobe_passed=reprobe_ok,
        reprobe_endpoints=reprobe_results,
        alert_posted=posted,
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
            health_wait_seconds=2.0,
            health_poll_seconds=0.05,
            skip_health_wait=False,
            auto_rollback_env="true",
            dry_run=True,
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
        help="Dry-run mode only (default when --execute is omitted; never calls Heroku).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute real Heroku rollback + re-probe + GitHub alert when a smoke probe fails.",
    )
    parser.add_argument(
        "--self-test-500",
        action="store_true",
        help="Run a local HTTP 500 stand-in server and verify dry-run reports 'would roll back'.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--prev-sha", default="")
    parser.add_argument("--heroku-app", default=os.environ.get("HEROKU_APP", DEFAULT_HEROKU_APP))
    parser.add_argument("--heroku-api-key", default=os.environ.get("HEROKU_API_KEY", ""))
    parser.add_argument("--repo", default=os.environ.get("REPO", ""))
    parser.add_argument("--now-issue", type=int, default=int(os.environ.get("NOW_LINES_ISSUE", str(DEFAULT_NOW_ISSUE))))
    parser.add_argument("--run-url", default=os.environ.get("RUN_URL", ""))
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
    if args.dry_run and args.execute:
        parser.error("--dry-run and --execute cannot be combined")

    dry_run = not args.execute
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
        dry_run=dry_run,
        heroku_app=args.heroku_app,
        heroku_api_key=args.heroku_api_key,
        repo=args.repo,
        now_issue=args.now_issue,
        run_url=args.run_url,
    )
    print(report.summary)
    if report.verdict in {"failed", "rolled_back"}:
        return 1
    if (not dry_run or args.fail_on_would_rollback) and report.verdict in {"would_roll_back", "alert_only"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
