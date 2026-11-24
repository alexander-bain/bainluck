"""Tests for .github/scripts/check_heroku_push.py (#13495)."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "check_heroku_push.py"

# Verbatim failure lines from recorded deploy run 45173313789 (job 137729996553)
RECORDED_RUN_45173313789_LOG = """\
remote:  !     Release command declared: this new release will not be available until the command succeeds.
remote:        Released v6585
remote: Running release command...
remote: TypeError: Unknown option 'send_default_pii'
remote: Waiting for release... failed.
To https://git.heroku.com/bainluck.git
   2b470b8ad..3304537ab  3304537ab7a275197847dee64a54cce9b2a5514c -> master
"""

CLEAN_V6586_LOG = """\
remote:  !     Release command declared: this new release will not be available until the command succeeds.
remote:        Released v6586
remote: Running release command...
remote: Waiting for release.... done.
To https://git.heroku.com/bainluck.git
   2b470b8ad..41de6f5c4  41de6f5c486a0000000000000000000000000000 -> master
"""


def _load_module():
    spec = importlib.util.spec_from_file_location("check_heroku_push", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_recorded_run_45173313789_release_failure_exits_1_despite_git_exit_0(tmp_path):
    mod = _load_module()
    code, reason = mod.classify_heroku_push(RECORDED_RUN_45173313789_LOG, 0)
    assert code == 1
    assert "Waiting for release... failed." in reason

    log_file = tmp_path / "push.log"
    log_file.write_text(RECORDED_RUN_45173313789_LOG, encoding="utf-8")
    rc = mod.main(
        [
            "--log",
            str(log_file),
            "--push-exit",
            "0",
            "--require-release-done",
        ]
    )
    assert rc == 1


def test_clean_v6586_push_log_succeeds(tmp_path):
    mod = _load_module()
    code, _ = mod.classify_heroku_push(CLEAN_V6586_LOG, 0)
    assert code == 0

    log_file = tmp_path / "push.log"
    log_file.write_text(CLEAN_V6586_LOG, encoding="utf-8")
    rc = mod.main(["--log", str(log_file), "--push-exit", "0", "--require-release-done"])
    assert rc == 0


def test_buildpack_remote_rejected_is_hard_failure_not_non_ff():
    mod = _load_module()
    build_fail = """\
remote:  !     Push rejected, failed to compile Python app.
remote:  !     Push rejected to bainluck.
To https://git.heroku.com/bainluck.git
 ! [remote rejected] master -> master (pre-receive hook declined)
error: failed to push some refs to 'https://git.heroku.com/bainluck.git'
"""
    code, _ = mod.classify_heroku_push(build_fail, 1)
    assert code == 1


def test_missing_waiting_for_release_done_fails_closed():
    mod = _load_module()
    truncated = """\
remote:  !     Release command declared: this new release will not be available until the command succeeds.
remote:        Released v6590
remote: Running release command...
To https://git.heroku.com/bainluck.git
"""
    code, _ = mod.classify_heroku_push(truncated, 0, require_release_done=True)
    assert code == 1


def test_pure_git_non_fast_forward_returns_2():
    mod = _load_module()
    non_ff = """\
To https://git.heroku.com/bainluck.git
 ! [rejected] abcdef1234567 -> master (non-fast-forward)
error: failed to push some refs to 'https://git.heroku.com/bainluck.git'
"""
    code, _ = mod.classify_heroku_push(non_ff, 1)
    assert code == 2


def test_everything_up_to_date_plus_api_check_rejects_failed_release(tmp_path):
    mod = _load_module()
    log_file = tmp_path / "push.log"
    log_file.write_text("Everything up-to-date\n", encoding="utf-8")

    expected = "3304537ab7a275197847dee64a54cce9b2a5514c"

    def fake_failed_api(path, headers=None):
        if path.endswith("/releases"):
            return [{"version": 6585, "status": "failed", "current": False, "slug": {"id": "s1"}}]
        raise AssertionError(path)

    ok, reason = mod.verify_heroku_release_api(
        "bainluck", "tok", expected, wait_seconds=0.0, request_fn=fake_failed_api
    )
    assert ok is False
    assert "v6585" in reason and "failed" in reason

    def fake_stale_current_api(path, headers=None):
        if path.endswith("/releases"):
            return [{"version": 6584, "status": "succeeded", "current": True, "slug": {"id": "s0"}}]
        if path.endswith("/slugs/s0"):
            return {"commit": "2b470b8ad0000000000000000000000000000000"}
        raise AssertionError(path)

    ok2, reason2 = mod.verify_heroku_release_api(
        "bainluck", "tok", expected, wait_seconds=0.0, request_fn=fake_stale_current_api
    )
    assert ok2 is False
    assert "2b470b8ad" in reason2

    def fake_good_api(path, headers=None):
        if path.endswith("/releases"):
            return [{"version": 6586, "status": "succeeded", "current": True, "slug": {"id": "s2"}}]
        if path.endswith("/slugs/s2"):
            return {"commit": expected}
        raise AssertionError(path)

    ok3, _ = mod.verify_heroku_release_api(
        "bainluck", "tok", expected, wait_seconds=0.0, request_fn=fake_good_api
    )
    assert ok3 is True


def test_cli_verify_api_missing_token_fails_closed(tmp_path):
    mod = _load_module()
    log_file = tmp_path / "push.log"
    log_file.write_text(CLEAN_V6586_LOG, encoding="utf-8")

    stderr = io.StringIO()
    with patch.dict(
        os.environ,
        {"HEROKU_API_KEY": "", "HEROKU_OAUTH_TOKEN": "", "HEROKU_SKIP_API_VERIFY": ""},
    ):
        with patch("sys.stderr", stderr):
            rc = mod.main(
                [
                    "--log",
                    str(log_file),
                    "--push-exit",
                    "0",
                    "--require-release-done",
                    "--verify-api",
                    "--app",
                    "bainluck",
                    "--expected-sha",
                    "41de6f5c486a0000000000000000000000000000",
                ]
            )
    assert rc == 1
    assert "missing" in stderr.getvalue()
