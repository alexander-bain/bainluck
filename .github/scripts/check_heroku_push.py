#!/usr/bin/env python3
"""Verify that a Heroku git push actually succeeded through the release phase.

Heroku runs the buildpack and ``release`` phase over the git push stream, then
often still exits ``0`` from ``git push`` even when the release command crashes
(e.g. ``remote: Waiting for release... failed.``). This script inspects the
captured git push output (and optionally the Heroku Platform API) so CI fails
closed instead of reporting a false green deploy or misclassifying a failed
release as a retryable git rejection.

Exit codes:
    0: Push and release succeeded (or remote was already up-to-date and live
       API check passed when enabled).
    1: Hard failure — Heroku refused the build or release, release completion
       was not confirmed, or Heroku Platform API verification failed.
    2: Pure git non-fast-forward / fetch-first rejection before Heroku accepted
       the push (eligible for caller supersede/retry logic on initial push).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HEROKU_API_BASE = "https://api.heroku.com"

_RELEASE_DONE_RE = re.compile(r"Waiting for release\.+\s*done\b", re.IGNORECASE)
_RELEASE_FAILED_RE = re.compile(r"Waiting for release\.+\s*failed\b", re.IGNORECASE)
_RELEASE_DECLARED_RE = re.compile(
    r"^\s*remote:\s*!?\s*(?:Release command declared|Running release command)\b",
    re.MULTILINE | re.IGNORECASE,
)
_REMOTE_REJECTED_RE = re.compile(r"!\s*\[remote rejected\]", re.IGNORECASE)
_HEROKU_PUSH_REFUSAL_RES = (
    re.compile(r"^\s*remote:\s*!?\s*Push rejected\b", re.MULTILINE | re.IGNORECASE),
    re.compile(
        r"^\s*remote:\s*!?\s*(?:Pre-receive hook declined|failed to compile|"
        r"App not compatible|No default language|Release failed)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
)
_GIT_NON_FF_RE = re.compile(
    r"!\s*\[rejected\].*\((?:non-fast-forward|fetch first)\)",
    re.IGNORECASE,
)
_UP_TO_DATE_RE = re.compile(r"^Everything up-to-date\s*$", re.MULTILINE)


def classify_heroku_push(
    log_text: str,
    push_exit: int,
    *,
    require_release_done: bool = True,
) -> tuple[int, str]:
    """Classify a Heroku ``git push`` invocation from its combined stdout/stderr.

    Returns ``(code, reason)`` where ``code`` matches the CLI exit contract:
    ``0`` success, ``1`` hard Heroku/deploy failure, ``2`` pure git non-FF rejection.
    """
    text = log_text or ""

    if _RELEASE_FAILED_RE.search(text):
        return 1, "Heroku release phase reported 'Waiting for release... failed.'."

    if _REMOTE_REJECTED_RE.search(text):
        return 1, "Heroku rejected the push at pre-receive/build stage ([remote rejected])."

    for pattern in _HEROKU_PUSH_REFUSAL_RES:
        if pattern.search(text):
            return 1, "Heroku refused the push in remote build/release output."

    if push_exit != 0:
        if _GIT_NON_FF_RE.search(text) or not text.strip():
            return 2, "Git push rejected (non-fast-forward / fetch first)."
        # Real git may reject without the parenthetical on some refs if `[rejected]` appears alone.
        if re.search(r"!\s*\[rejected\]", text, re.IGNORECASE) and not _REMOTE_REJECTED_RE.search(
            text
        ):
            return 2, "Git push rejected before Heroku pre-receive."
        return 1, f"git push failed with exit status {push_exit}."

    if _RELEASE_DONE_RE.search(text):
        return 0, "Heroku push and release phase reported done."

    if require_release_done:
        if _UP_TO_DATE_RE.search(text):
            return 0, "Git remote reported Everything up-to-date."
        if _RELEASE_DECLARED_RE.search(text):
            return (
                1,
                "Heroku declared/ran a release command but never reported "
                "'Waiting for release.... done.'.",
            )
        return (
            1,
            "Heroku push exited 0 without 'Waiting for release.... done.' confirmation.",
        )

    return 0, "Heroku push exited 0 with no failure signatures."


def is_missing_release_done_only(log_text: str, push_exit: int) -> bool:
    """Return True iff the only failure is omitted ``Waiting for release.... done.`` on exit 0."""
    unstrict_code, _ = classify_heroku_push(
        log_text,
        push_exit,
        require_release_done=False,
    )
    strict_code, _ = classify_heroku_push(
        log_text,
        push_exit,
        require_release_done=True,
    )
    return unstrict_code == 0 and strict_code == 1


def _heroku_get(
    path: str,
    token: str,
    *,
    headers: dict[str, str] | None = None,
    api_base: str = HEROKU_API_BASE,
    timeout: float = 15.0,
) -> Any:
    """Perform a single Heroku Platform API GET request."""
    url = f"{api_base.rstrip('/')}/{path.lstrip('/')}"
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.heroku+json; version=3",
        "User-Agent": "bainluck-ci-deploy-check",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sha_matches(actual: str | None, expected: str | None) -> bool:
    if not actual or not expected:
        return False
    a = actual.strip().lower()
    e = expected.strip().lower()
    if len(a) < 7 or len(e) < 7:
        return False
    return a == e or a.startswith(e) or e.startswith(a)


def verify_heroku_release_api(
    app: str,
    token: str,
    expected_sha: str,
    *,
    api_base: str = HEROKU_API_BASE,
    wait_seconds: float = 15.0,
    poll_interval: float = 2.0,
    request_fn: Any = None,
) -> tuple[bool, str]:
    """Confirm via Heroku Platform API that ``expected_sha`` is currently live & succeeded."""
    fetcher = request_fn or (
        lambda path, extra_headers=None: _heroku_get(
            path, token, headers=extra_headers, api_base=api_base
        )
    )

    deadline = time.monotonic() + max(0.0, wait_seconds)
    last_reason = f"Unable to verify live release for {app}."

    while True:
        try:
            releases = fetcher(
                f"apps/{app}/releases",
                {"Range": "version ..; order=desc, max=5"},
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            return False, f"Heroku releases API lookup failed for {app}: {exc}"

        if not isinstance(releases, list) or not releases:
            return False, f"Heroku releases API returned no releases for {app}."

        latest = releases[0] or {}
        latest_status = str(latest.get("status") or "").lower()
        latest_version = latest.get("version")
        latest_current = latest.get("current")

        if latest_status == "failed":
            return (
                False,
                f"Heroku latest release v{latest_version} on {app} failed "
                f"(status=failed, current={latest_current}).",
            )

        if latest_status == "succeeded" and latest_current is True:
            slug_id = (latest.get("slug") or {}).get("id")
            if not slug_id:
                return (
                    False,
                    f"Heroku release v{latest_version} on {app} has no slug id.",
                )
            try:
                slug = fetcher(f"apps/{app}/slugs/{slug_id}", None) or {}
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
                return (
                    False,
                    f"Heroku slug API lookup failed for {app} slug {slug_id}: {exc}",
                )
            slug_commit = slug.get("commit")
            if _sha_matches(slug_commit, expected_sha):
                return (
                    True,
                    f"Heroku release v{latest_version} on {app} is current/succeeded "
                    f"at {slug_commit}.",
                )
            last_reason = (
                f"Heroku current release v{latest_version} on {app} has commit "
                f"{slug_commit!r}, expected {expected_sha!r}."
            )
        else:
            last_reason = (
                f"Heroku latest release v{latest_version} on {app} not yet current/succeeded "
                f"(status={latest_status!r}, current={latest_current!r})."
            )

        if time.monotonic() >= deadline:
            return False, last_reason
        time.sleep(min(poll_interval, max(0.1, deadline - time.monotonic())))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Heroku git push output and optional Platform API release state."
    )
    parser.add_argument("--log", type=Path, required=True, help="Captured git push output file.")
    parser.add_argument("--push-exit", type=int, required=True, help="Exit status of git push.")
    parser.add_argument(
        "--require-release-done",
        action="store_true",
        help="Require 'Waiting for release.... done.' (or 'Everything up-to-date') on exit 0.",
    )
    parser.add_argument(
        "--verify-api",
        action="store_true",
        help="Confirm via Heroku Platform API that --expected-sha is current and succeeded.",
    )
    parser.add_argument("--app", default="", help="Heroku app name (e.g. bainluck).")
    parser.add_argument("--expected-sha", default="", help="Expected deployed commit SHA.")
    parser.add_argument(
        "--api-wait-seconds",
        type=float,
        default=15.0,
        help="Seconds to poll Heroku Platform API if latest release is still pending.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_text = args.log.read_text(encoding="utf-8", errors="replace") if args.log.exists() else ""

    code, reason = classify_heroku_push(
        log_text,
        args.push_exit,
        require_release_done=args.require_release_done,
    )
    if code != 0:
        if (
            args.require_release_done
            and args.verify_api
            and os.environ.get("HEROKU_SKIP_API_VERIFY") != "1"
            and is_missing_release_done_only(log_text, args.push_exit)
        ):
            print(
                f"HEROKU_PUSH_CHECK: {reason} Falling back to Heroku Releases API verification.",
                file=sys.stderr,
            )
        else:
            print(f"HEROKU_PUSH_CHECK[{code}]: {reason}", file=sys.stderr)
            return code

    if args.verify_api and os.environ.get("HEROKU_SKIP_API_VERIFY") != "1":
        token = (
            os.environ.get("HEROKU_API_KEY")
            or os.environ.get("HEROKU_OAUTH_TOKEN")
            or ""
        ).strip()
        if not token:
            print(
                "HEROKU_PUSH_CHECK[1]: --verify-api set but HEROKU_API_KEY/HEROKU_OAUTH_TOKEN is missing.",
                file=sys.stderr,
            )
            return 1
        if not args.app or not args.expected_sha:
            print(
                "HEROKU_PUSH_CHECK[1]: --verify-api requires --app and --expected-sha.",
                file=sys.stderr,
            )
            return 1
        ok, api_reason = verify_heroku_release_api(
            args.app,
            token,
            args.expected_sha,
            wait_seconds=args.api_wait_seconds,
        )
        if not ok:
            print(f"HEROKU_PUSH_CHECK[1]: {api_reason}", file=sys.stderr)
            return 1
        print(f"HEROKU_PUSH_CHECK[0]: {api_reason}")
        return 0

    print(f"HEROKU_PUSH_CHECK[0]: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
