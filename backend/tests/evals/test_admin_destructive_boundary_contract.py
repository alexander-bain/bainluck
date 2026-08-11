"""C271 post-merge attacks against Q315's real admin boundaries."""
from __future__ import annotations

import logging

import pytest
from starlette.requests import Request

from app.routes.admin_utils import (
    DESTRUCTIVE_TOKEN_HEADER,
    _check_admin_destructive,
    _check_admin_secret,
)
from scripts.evals.admin_destructive_boundary_contract import evaluate_pack, handlers, load_pack

BASE = "c271-base-admin-token"
SECOND = "c271-destructive-token"


def _request(*, scheme: str = "Bearer", second: str | None = None) -> Request:
    headers = [(b"authorization", f"{scheme} {BASE}".encode())]
    if second is not None:
        headers.append((DESTRUCTIVE_TOKEN_HEADER.lower().encode(), second.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/admin/test",
            "query_string": b"secret-value=must-not-log",
            "headers": headers,
        }
    )


def test_fixture_is_the_complete_direct_destruction_census():
    pack = load_pack()
    expected = {
        f"{case['module']}:{case['method']}:{case['route']}" for case in pack["cases"]
    }
    assert set(handlers()) == expected


@pytest.mark.parametrize("case", load_pack()["cases"], ids=lambda case: case["id"])
def test_every_directly_destructive_handler_uses_the_strong_gate_exactly_once(case):
    result = evaluate_pack({"cases": [case]})
    assert result["passed"] == 1, result["rows"]


def test_bearer_scheme_is_case_insensitive_at_auth_and_rate_boundaries(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", BASE)
    # RFC 9110 authentication schemes are case-insensitive; rate_limit.py already
    # lower-cases this same prefix before assigning the 300/min admin bucket.
    assert _check_admin_secret(None, request=_request(scheme="bearer")) is True


def test_two_tokens_emit_one_sanitized_audit_line(monkeypatch, caplog):
    monkeypatch.setenv("ADMIN_TOKEN", BASE)
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", SECOND)
    with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
        assert _check_admin_destructive(None, request=_request(second=SECOND)) is True
    lines = [record.getMessage() for record in caplog.records if "admin_audit" in record.getMessage()]
    assert len(lines) == 1
    assert BASE not in lines[0] and SECOND not in lines[0] and "must-not-log" not in lines[0]


@pytest.mark.parametrize("second", [None, "wrong-token"])
def test_missing_or_wrong_second_token_fails_closed(monkeypatch, second):
    from fastapi import HTTPException

    monkeypatch.setenv("ADMIN_TOKEN", BASE)
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", SECOND)
    with pytest.raises(HTTPException) as error:
        _check_admin_destructive(None, request=_request(second=second))
    assert error.value.status_code == 403
