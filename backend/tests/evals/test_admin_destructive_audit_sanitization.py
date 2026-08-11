"""Q332 Item 4 — the audit line stays sanitized after the Item 1 wiring.

C271 verified that a correct two-token call emits EXACTLY ONE ``admin_audit`` record
and that no token material reaches it. Item 1 added nine new call sites, and nine new
call sites are nine new chances to log a token, so the property is re-asserted here
rather than assumed to have survived.

Two complementary checks, because either alone is weak:
  * BEHAVIOURAL — one call, exactly one line, no secrets in it.
  * STATIC, over the whole censused set — no destructive handler logs its own token.
    The behavioural test only walks the gate; a handler that logged ``secret`` itself
    would sail past it.
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

import pytest
from starlette.requests import Request

from app.routes.admin_utils import (
    DESTRUCTIVE_TOKEN_HEADER,
    _check_admin_destructive,
)
from scripts.evals.admin_destructive_boundary_contract import handlers

BASE = "q332-audit-base-token"
SECOND = "q332-audit-destructive-token"
ROUTES = Path(__file__).resolve().parents[2] / "app/routes"

_LOG_CALL = re.compile(r"(?:logger|_logger|logging|log)\.\w+\((?:[^()]|\([^()]*\))*\)")


def _request(*, second: str | None = SECOND, query: bytes = b"secret-value=must-not-log"):
    headers = [(b"authorization", f"Bearer {BASE}".encode())]
    if second is not None:
        headers.append((DESTRUCTIVE_TOKEN_HEADER.lower().encode(), second.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/admin/test",
            "query_string": query,
            "headers": headers,
        }
    )


def test_correct_two_token_call_emits_exactly_one_sanitized_audit_line(monkeypatch, caplog):
    monkeypatch.setenv("ADMIN_TOKEN", BASE)
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", SECOND)

    with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
        assert _check_admin_destructive(None, request=_request()) is True

    lines = [r.getMessage() for r in caplog.records if "admin_audit" in r.getMessage()]
    assert len(lines) == 1, f"expected exactly one audit line, got {len(lines)}: {lines}"
    line = lines[0]
    for forbidden in (BASE, SECOND, "must-not-log"):
        assert forbidden not in line, f"audit line leaked {forbidden!r}: {line}"


def test_a_refused_call_does_not_emit_an_audit_line(monkeypatch, caplog):
    """A denial must not write the success record. Otherwise the audit log — the thing
    you read at 3am after a token leak — cannot distinguish an attempt from an act."""
    from fastapi import HTTPException

    monkeypatch.setenv("ADMIN_TOKEN", BASE)
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", SECOND)

    with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
        with pytest.raises(HTTPException):
            _check_admin_destructive(None, request=_request(second="wrong"))

    assert [r.getMessage() for r in caplog.records if "admin_audit" in r.getMessage()] == []


@pytest.mark.parametrize(
    "case",
    sorted(handlers().values(), key=lambda info: (info["module"], info["function"])),
    ids=lambda info: f"{info['module']}:{info['function']}",
)
def test_no_destructive_handler_logs_token_material(case):
    """Static sweep over the CENSUSED set, so a tenth destructive route inherits it."""
    source = (ROUTES / case["module"]).read_text()
    tree = ast.parse(source)
    body = ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == case["function"]:
            body = ast.get_source_segment(source, node) or ""
            break
    assert body, f"could not locate {case['function']} in {case['module']}"

    offenders = [
        call for call in _LOG_CALL.findall(body)
        if "secret" in call.lower() or "token" in call.lower()
    ]
    assert not offenders, (
        f"{case['module']}:{case['function']} logs token material: {offenders}"
    )
