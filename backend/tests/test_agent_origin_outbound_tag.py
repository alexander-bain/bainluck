"""Guards for outbound `x-bainluck-origin` tagging (notice 39 / #1916, #4459 ship 5).

The class of bug every test here exists to catch is the SILENT one. Nothing in
this channel raises when it breaks: a header spelled wrong, a header resolved at
import time, a header sent to Kalshi, a header sent twice — each produces a
perfectly normal 200 and a probe whose author believes it is tagged. So these
assert the wire, not the happy path.
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

import pytest

from app.utils.agent_origin import (
    DEFAULT_AGENT,
    ORIGIN_HEADER,
    ORIGIN_USER,
    is_our_host,
    origin_headers,
    resolve_agent,
    tagged,
)

BACKEND = pathlib.Path(__file__).resolve().parents[1]
GATE_SCRIPTS = sorted(BACKEND.glob("scripts/gate_*.py"))


# ---------------------------------------------------------------------------
# The name on the wire
# ---------------------------------------------------------------------------


def test_header_name_is_the_documented_wire_name():
    assert ORIGIN_HEADER == "x-bainluck-origin"
    assert ORIGIN_USER == "user"


def test_reader_and_sender_share_one_constant():
    """`routes/events.py` must not re-spell the header.

    A sender/reader drift of one character raises nothing: every probe looks
    tagged and every row is still written. This is the only cheap guard.
    """
    from app.routes import events

    assert events._ORIGIN_HEADER is ORIGIN_HEADER
    assert events._ORIGIN_USER is ORIGIN_USER

    src = (BACKEND / "app" / "routes" / "events.py").read_text()
    # The literal may appear in prose/docstrings, but never as an assignment.
    assert not re.search(
        r'^_ORIGIN_HEADER\s*=\s*[\'"]', src, re.M
    ), "events.py re-spells the header literal instead of importing it"


# ---------------------------------------------------------------------------
# Resolution happens at CALL time
# ---------------------------------------------------------------------------


def test_agent_is_resolved_at_call_time_not_import_time(monkeypatch):
    """The failure the shell helper shipped a comment about.

    A name captured at import produces an EMPTY header, the backend reads empty
    as a person, and the call votes in the search head exactly as it did
    untagged.
    """
    monkeypatch.setenv("BL_AGENT", "lane-one")
    assert resolve_agent() == "lane-one"
    monkeypatch.setenv("BL_AGENT", "lane-two")
    assert resolve_agent() == "lane-two", "agent was captured, not re-read"


@pytest.mark.parametrize("value", ["", "   "])
def test_absent_or_blank_agent_still_tags(monkeypatch, value):
    """Being unnamed is not evidence of humanity."""
    monkeypatch.setenv("BL_AGENT", value)
    assert resolve_agent() == DEFAULT_AGENT
    headers = origin_headers("https://api.bainluck.com/api/x")
    assert headers[ORIGIN_HEADER] == DEFAULT_AGENT
    assert headers[ORIGIN_HEADER] != "", "an empty header reads as a PERSON server-side"


def test_unset_agent_still_tags(monkeypatch):
    monkeypatch.delenv("BL_AGENT", raising=False)
    assert origin_headers("https://api.bainluck.com/x")[ORIGIN_HEADER] == DEFAULT_AGENT


# ---------------------------------------------------------------------------
# Never on a third party's wire
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://api.bainluck.com/api/admin/db-query",
        "https://bainluck.com/",
        "http://localhost:8000/api/feed",
        "http://127.0.0.1:8000/api/feed",
        "api.bainluck.com/api/feed",  # scheme-less, as a script may build it
    ],
)
def test_our_hosts_are_tagged(url):
    assert is_our_host(url)
    assert ORIGIN_HEADER in origin_headers(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.elections.kalshi.com/trade-api/v2/events",
        "https://gamma-api.polymarket.com/events",
        "https://site.api.espn.com/apis/site/v2/sports",
        "https://api.github.com/repos/x/y",
        "https://the-odds-api.com/v4/sports",
    ],
)
def test_third_party_hosts_are_never_tagged(url):
    assert not is_our_host(url)
    assert origin_headers(url) == {}


def test_lookalike_host_is_not_ours():
    """A substring test would tag this; the host is parsed instead."""
    assert not is_our_host("https://example.com/?ref=bainluck.com")
    assert not is_our_host("https://bainluck.com.evil.test/x")
    assert origin_headers("https://example.com/?ref=bainluck.com") == {}


def test_userinfo_cannot_smuggle_our_host():
    assert not is_our_host("https://api.bainluck.com@evil.test/x")


# ---------------------------------------------------------------------------
# Never twice — the caller's explicit intent wins
# ---------------------------------------------------------------------------


def test_existing_tag_is_not_overridden(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "lane")
    existing = {ORIGIN_HEADER: ORIGIN_USER}
    assert origin_headers("https://api.bainluck.com/x", existing) == {}
    assert tagged("https://api.bainluck.com/x", existing)[ORIGIN_HEADER] == ORIGIN_USER


def test_existing_tag_match_is_case_insensitive(monkeypatch):
    """HTTP header names are case-insensitive; a dict lookup is not."""
    monkeypatch.setenv("BL_AGENT", "lane")
    existing = {"X-BainLuck-Origin": ORIGIN_USER}
    assert origin_headers("https://api.bainluck.com/x", existing) == {}


def test_tagged_preserves_caller_headers_and_does_not_mutate(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "lane")
    original = {"Authorization": "Bearer t", "Content-Type": "application/json"}
    out = tagged("https://api.bainluck.com/x", original)
    assert out["Authorization"] == "Bearer t"
    assert out["Content-Type"] == "application/json"
    assert out[ORIGIN_HEADER] == "lane"
    assert ORIGIN_HEADER not in original, "caller's dict was mutated"


def test_caller_user_agent_is_not_clobbered(monkeypatch):
    monkeypatch.setenv("BL_AGENT", "lane")
    out = tagged("https://api.bainluck.com/x", {"User-Agent": "mine/1.0"})
    assert out["User-Agent"] == "mine/1.0"


# ---------------------------------------------------------------------------
# The gate scripts actually carry it
# ---------------------------------------------------------------------------


def test_there_are_gate_scripts_to_check():
    """Denominator guard: an empty glob would make every test below vacuous."""
    assert len(GATE_SCRIPTS) >= 4, [p.name for p in GATE_SCRIPTS]


def _http_gate_scripts():
    return [p for p in GATE_SCRIPTS if "urllib.request.Request" in p.read_text()]


def test_the_http_gate_scripts_are_the_expected_three():
    names = sorted(p.name for p in _http_gate_scripts())
    assert names == [
        "gate_futures_name_fts_index.py",
        "gate_futures_open_trgm_index.py",
        "gate_teams_fts_index.py",
    ], names


@pytest.mark.parametrize("path", _http_gate_scripts(), ids=lambda p: p.name)
def test_every_gate_request_is_tagged(path: pathlib.Path):
    """Every `urllib.request.Request` in a gate script passes headers through
    `tagged(...)`. Asserted on the AST so a commented-out call cannot pass."""
    tree = ast.parse(path.read_text())
    requests = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Request"
    ]
    assert requests, f"{path.name}: no urllib Request found — did the shape change?"
    for call in requests:
        kw = {k.arg: k.value for k in call.keywords}
        assert "headers" in kw, f"{path.name}: Request built with no headers"
        headers = kw["headers"]
        assert isinstance(headers, ast.Call) and getattr(
            headers.func, "id", None
        ) == "tagged", (
            f"{path.name}: Request headers are a bare dict — untagged probe traffic"
        )


@pytest.mark.parametrize("path", _http_gate_scripts(), ids=lambda p: p.name)
def test_gate_scripts_import_cleanly(path: pathlib.Path):
    """The import sits below a `sys.path` insert; a bad placement is an
    ImportError that only shows up when the gate is next run for real."""
    proc = subprocess.run(
        [sys.executable, "-c", f"import ast,sys; ast.parse(open({str(path)!r}).read())"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    src = path.read_text()
    insert_at = src.index("sys.path.insert")
    import_at = src.index("from app.utils.agent_origin import tagged")
    assert import_at > insert_at, (
        f"{path.name}: agent_origin imported before sys.path is set up"
    )


# ---------------------------------------------------------------------------
# The tag must never buy privilege
# ---------------------------------------------------------------------------


def test_rate_limiter_does_not_read_the_origin_header():
    """`x-bainluck-origin` is caller-supplied and forgeable. It is fit for
    saying WHO, never for granting WHAT. If an allowlist is ever keyed on it,
    this fails — deliberately."""
    src = (BACKEND / "app" / "utils" / "rate_limit.py").read_text()
    assert "bainluck-origin" not in src.lower(), (
        "rate_limit.py reads the forgeable origin header — an allowlist for the "
        "entire internet; see agent_origin.py's module docstring"
    )
