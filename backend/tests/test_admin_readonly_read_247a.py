"""Tests for Ruling 247: A — single read-only admin-read script and allowlist."""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ADMIN = REPO_ROOT / "tools" / "admin"


def _load_readonly_read():
    spec = importlib.util.spec_from_file_location(
        "bainluck_readonly_read_247a", TOOLS_ADMIN / "readonly_read.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rr = _load_readonly_read()

SECRET_TOKEN = "test-secret-admin-token-9f8e7d6c5b4a"


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_allowlist_starts_with_exactly_ranking_grades_and_slates():
    entries = rr.load_allowlist()
    names = [e["name"] for e in entries]
    paths = [e["path"] for e in entries]
    assert names == ["ranking_grades", "ranking_slates"]
    assert paths == ["/api/admin/ranking/grades", "/api/admin/ranking/slates"]
    assert entries[1]["templates"] == ["/api/admin/ranking/slates/{ref}"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_writes_and_non_get_methods_are_refused_before_token_or_network(method):
    token_called = False
    net_called = False

    def fail_token():
        nonlocal token_called
        token_called = True
        return SECRET_TOKEN

    def fail_open(*args, **kwargs):
        nonlocal net_called
        net_called = True
        raise AssertionError("network must not be called")

    with pytest.raises(rr.ReadOnlyRefusedError, match="GET only"):
        rr.readonly_get(
            "/api/admin/ranking/grades?days=6",
            lane="Builder E",
            issue="11937",
            method=method,
            token_provider=fail_token,
            urlopen=fail_open,
        )
    assert not token_called
    assert not net_called


@pytest.mark.parametrize(
    "address",
    [
        "/api/admin/db-query",
        "/api/admin/ranking/pair-picks",
        "/api/admin/ranking/slates/capture",
        "/api/admin/ranking/grouping-grades",
        "/api/admin/ranking/slates/../db-query",
        "/api/admin/ranking/slates/%2e%2e/db-query",
        "/api/admin/ranking/slates/latest/extra",
        "/api/admin/ranking/slates/a%2fb",
        "/api/admin/ranking/grades?secret=abc",
        "https://evil.example.com/api/admin/ranking/grades",
        "//evil.example.com/api/admin/ranking/grades",
        "",
    ],
)
def test_unlisted_or_unsafe_addresses_are_refused_before_token_or_network(address):
    token_called = False
    net_called = False

    def fail_token():
        nonlocal token_called
        token_called = True
        return SECRET_TOKEN

    def fail_open(*args, **kwargs):
        nonlocal net_called
        net_called = True
        raise AssertionError("network must not be called")

    with pytest.raises(rr.ReadOnlyRefusedError):
        rr.readonly_get(
            address,
            lane="Builder E",
            issue="11937",
            token_provider=fail_token,
            urlopen=fail_open,
        )
    assert not token_called
    assert not net_called


@pytest.mark.parametrize(
    "address",
    [
        "/api/admin/ranking/grades?days=6",
        "/api/admin/ranking/slates?surface=discover&limit=14",
        "/api/admin/ranking/slates/latest?surface=discover",
        "/api/admin/ranking/slates/8bd96ad5dfaa243c",
    ],
)
def test_allowed_addresses_succeed_with_get_and_audit_line(address):
    seen_req = {}

    def fake_open(req, timeout=60):
        seen_req["url"] = req.full_url
        seen_req["method"] = req.get_method()
        seen_req["auth"] = req.get_header("Authorization")
        return _FakeResponse(b'{"ok": true}')

    fixed_now = datetime(2026, 11, 19, 1, 46, tzinfo=timezone.utc)  # 5:46 PM PT
    payload, audit_line = rr.readonly_get(
        address,
        lane="Builder E",
        issue="11937",
        token_provider=lambda: SECRET_TOKEN,
        urlopen=fake_open,
        now=fixed_now,
    )
    assert payload == {"ok": True}
    assert seen_req["method"] == "GET"
    assert seen_req["url"] == f"https://api.bainluck.com{address}"
    assert seen_req["auth"] == f"Bearer {SECRET_TOKEN}"
    assert audit_line == (
        f"admin-read | 2026-11-18 5:46 PM PT | lane=Builder E | GET {address} | issue=#11937"
    )
    assert SECRET_TOKEN not in audit_line


def test_token_never_appears_in_error_output_on_http_error(capsys, monkeypatch):
    def fake_open(req, timeout=60):
        body = io.BytesIO(f"Unauthorized for token {SECRET_TOKEN}".encode("utf-8"))
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", hdrs={}, fp=body
        )

    monkeypatch.setenv("ADMIN_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(rr.urllib.request, "urlopen", fake_open)
    code = rr.main(["--lane", "Builder E", "--issue", "11937", "/api/admin/ranking/grades?days=2"])
    captured = capsys.readouterr()
    assert code == 2
    assert SECRET_TOKEN not in captured.out
    assert SECRET_TOKEN not in captured.err
    assert "[REDACTED]" in captured.err


def test_token_never_appears_in_error_output_on_url_error(capsys, monkeypatch):
    def fake_open(req, timeout=60):
        raise urllib.error.URLError(f"boom with {SECRET_TOKEN} inside")

    monkeypatch.setenv("ADMIN_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(rr.urllib.request, "urlopen", fake_open)
    code = rr.main(["--lane", "Builder E", "--issue", "11937", "/api/admin/ranking/slates/latest"])
    captured = capsys.readouterr()
    assert code == 2
    assert SECRET_TOKEN not in captured.out
    assert SECRET_TOKEN not in captured.err
    assert "[REDACTED]" in captured.err


def test_token_never_appears_in_response_or_cli_out(tmp_path, capsys, monkeypatch):
    def fake_open(req, timeout=60):
        return _FakeResponse(json.dumps({"echo": SECRET_TOKEN, "grades": []}).encode("utf-8"))

    out_file = tmp_path / "grades.json"
    monkeypatch.setenv("ADMIN_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr(rr.urllib.request, "urlopen", fake_open)
    code = rr.main([
        "--lane", "Builder E",
        "--issue", "11937",
        "--out", str(out_file),
        "/api/admin/ranking/grades?days=2",
    ])
    captured = capsys.readouterr()
    assert code == 0
    assert SECRET_TOKEN not in captured.out
    assert SECRET_TOKEN not in captured.err
    saved_text = out_file.read_text(encoding="utf-8")
    assert SECRET_TOKEN not in saved_text
    assert "admin-read |" in captured.out
    assert "lane=Builder E" in captured.out
    assert "GET /api/admin/ranking/grades?days=2" in captured.out
    assert "issue=#11937" in captured.out


def test_cli_refuses_write_method(capsys):
    code = rr.main([
        "--lane", "Builder E",
        "--issue", "11937",
        "--method", "POST",
        "/api/admin/ranking/grades",
    ])
    captured = capsys.readouterr()
    assert code == 2
    assert "GET only" in captured.err


def test_script_never_opens_dotenv():
    import re
    src = (TOOLS_ADMIN / "readonly_read.py").read_text(encoding="utf-8")
    assert re.search(r"(?<![A-Za-z0-9_])\.env\b", src) is None
    assert "dotenv" not in src.lower()


def test_read_admin_token_uses_heroku_netrc_and_never_leaks_heroku_key(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    heroku_key = "heroku-secret-key-xyz987"
    fake_netrc = MagicMock()
    fake_netrc.authenticators.return_value = ("user", None, heroku_key)

    def fail_open(req, timeout=30):
        raise urllib.error.URLError(f"failed with {heroku_key}")

    with pytest.raises(rr.ReadOnlyRequestError) as excinfo:
        rr.read_admin_token(urlopen=fail_open, netrc_loader=lambda: fake_netrc)
    assert heroku_key not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)
