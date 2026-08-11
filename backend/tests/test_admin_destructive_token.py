"""Queue 315 Items 2 + 3 — the second token on destructive admin routes, and the
audit line that records sensitive admin calls.

Every behavioral test here asserts BOTH directions (gotcha #43). A gate exercised
only in the failing direction can be inverted — swap the comparison, and it denies
nothing while every test still passes. A gate exercised only in the passing
direction is indistinguishable from no gate at all.

The structural test at the bottom is the one that survives refactors: it re-derives
the destructive route set from source and fails if any of those routes stops
calling the gate. A list of routes in a queue document rots; an assertion does not.
"""

import ast
import logging
import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routes.admin_utils import (
    DESTRUCTIVE_TOKEN_HEADER,
    _check_admin_destructive,
    audit_admin_call,
)

BASE_TOKEN = "base-admin-token"
DESTRUCTIVE_TOKEN = "second-destructive-token"


def _request(
    *,
    bearer: str | None = BASE_TOKEN,
    destructive: str | None = None,
    path: str = "/api/admin/cleanup/crypto",
    query: str = "batch_size=5000",
    method: str = "POST",
) -> Request:
    headers = []
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    if destructive is not None:
        headers.append(
            (DESTRUCTIVE_TOKEN_HEADER.lower().encode(), destructive.encode())
        )
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query.encode(),
            "headers": headers,
        }
    )


@pytest.fixture
def both_tokens(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", BASE_TOKEN)
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", DESTRUCTIVE_TOKEN)


class TestDestructiveGateBothDirections:
    def test_both_tokens_succeed(self, both_tokens):
        """The PASSING direction. Without this, a gate that denies everything
        would look correct."""
        assert (
            _check_admin_destructive(
                None, request=_request(destructive=DESTRUCTIVE_TOKEN)
            )
            is True
        )

    def test_base_token_alone_is_refused(self, both_tokens):
        """The whole point: ADMIN_TOKEN is what agent lanes hold."""
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(None, request=_request())
        assert exc.value.status_code == 403

    def test_refusal_names_the_header_and_env_var(self, both_tokens):
        """Alex meets this 403 mid-operation. A generic denial would tell him
        nothing about what to do next."""
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(None, request=_request())
        detail = exc.value.detail
        assert DESTRUCTIVE_TOKEN_HEADER in detail
        assert "ADMIN_TOKEN_DESTRUCTIVE" in detail

    def test_wrong_destructive_token_is_refused(self, both_tokens):
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(None, request=_request(destructive="wrong"))
        assert exc.value.status_code == 403
        assert "does not match" in exc.value.detail

    def test_unconfigured_server_fails_closed_and_says_so(self, monkeypatch):
        """If ADMIN_TOKEN_DESTRUCTIVE is unset the route must DENY, not fall back
        to base-token-only. Fail-open here would make the whole item decoration."""
        monkeypatch.setenv("ADMIN_TOKEN", BASE_TOKEN)
        monkeypatch.delenv("ADMIN_TOKEN_DESTRUCTIVE", raising=False)
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(
                None, request=_request(destructive=DESTRUCTIVE_TOKEN)
            )
        assert exc.value.status_code == 403
        assert "ADMIN_TOKEN_DESTRUCTIVE" in exc.value.detail
        assert "heroku config:set" in exc.value.detail

    def test_destructive_token_alone_does_not_authenticate(self, both_tokens):
        """It is a SECOND factor, not an alternative one."""
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(
                None, request=_request(bearer=None, destructive=DESTRUCTIVE_TOKEN)
            )
        assert exc.value.status_code == 403

    def test_bad_base_token_is_refused_before_the_second_is_considered(
        self, both_tokens
    ):
        """A caller without the base token learns nothing about the second one."""
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(
                None, request=_request(bearer="nope", destructive=DESTRUCTIVE_TOKEN)
            )
        assert exc.value.status_code == 403
        assert "Invalid admin secret" in exc.value.detail
        assert "ADMIN_TOKEN_DESTRUCTIVE" not in exc.value.detail

    def test_query_param_cannot_supply_the_destructive_token(self, both_tokens):
        """Queue #252 Item 3 removed `?secret=` because a secret in a URL leaks
        through history, Referer, access logs and shared links. The second secret
        must not re-open that door."""
        req = _request(query=f"secret={DESTRUCTIVE_TOKEN}")
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(DESTRUCTIVE_TOKEN, request=req)
        assert exc.value.status_code == 403


class TestAuditLine:
    def test_destructive_call_emits_exactly_one_audit_line(self, both_tokens, caplog):
        with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
            _check_admin_destructive(
                None, request=_request(destructive=DESTRUCTIVE_TOKEN)
            )
        lines = [r for r in caplog.records if "admin_audit" in r.getMessage()]
        assert len(lines) == 1
        msg = lines[0].getMessage()
        assert "route=/api/admin/cleanup/crypto" in msg
        assert "kind=destructive" in msg

    def test_refused_call_emits_no_audit_line(self, both_tokens, caplog):
        """The audit line records what HAPPENED. A refusal is the rate limiter's
        and Sentry's business."""
        with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
            with pytest.raises(HTTPException):
                _check_admin_destructive(None, request=_request())
        assert not [r for r in caplog.records if "admin_audit" in r.getMessage()]

    def test_db_query_audit_logs_hashes_and_never_the_sql(self, caplog):
        """An audit log carrying SQL text or parameter values would become the
        exfiltration path the rate limit and the token were added to close."""
        secret_sql = "SELECT email, firebase_uid FROM users WHERE id = 364"
        req = _request(
            path="/api/admin/db-query", query="limit=500&token=sensitive-value"
        )
        with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
            audit_admin_call(req, kind="db_query", sql=secret_sql)

        msg = [r for r in caplog.records if "admin_audit" in r.getMessage()][
            0
        ].getMessage()
        assert "sql_hash=" in msg and "params_hash=" in msg
        # No fragment of the statement, and no query-string VALUE, survives.
        assert "SELECT" not in msg
        assert "users" not in msg
        assert "firebase_uid" not in msg
        assert "sensitive-value" not in msg

    def test_hash_is_stable_and_distinguishes_different_sql(self, caplog):
        """Hashes still answer what an audit log exists to answer: was this the
        same call repeated, or a new one each time."""
        req = _request(path="/api/admin/db-query", query="")
        with caplog.at_level(logging.INFO, logger="app.routes.admin_utils"):
            audit_admin_call(req, kind="db_query", sql="SELECT 1")
            audit_admin_call(req, kind="db_query", sql="SELECT 1")
            audit_admin_call(req, kind="db_query", sql="SELECT 2")

        hashes = [
            m.split("sql_hash=")[1].split()[0]
            for m in (r.getMessage() for r in caplog.records)
            if "admin_audit" in m
        ]
        assert hashes[0] == hashes[1]
        assert hashes[0] != hashes[2]


# ---------------------------------------------------------------------------
# Structural guard — the destructive route set actually calls the gate
# ---------------------------------------------------------------------------

# (module filename, route path as written in the decorator)
DESTRUCTIVE_ROUTES = [
    ("admin_data_quality.py", "/cleanup/crypto"),
    ("admin_data_quality.py", "/cleanup/turbo-collapse"),
    ("admin_data_quality.py", "/cleanup/reclassify-events"),
    ("admin_data_quality.py", "/cleanup/merge-duplicate-events"),
    ("admin_data_quality.py", "/cleanup/purge-orphan-pm-events"),
    ("admin_data_quality.py", "/db/delete-orphan-futures-snapshots"),
    ("admin_data_quality.py", "/db/vacuum"),
    ("admin_data_quality.py", "/db/drop-duplicate-index"),
    ("admin_data_quality.py", "/backfill-settled/reset-cursors"),
    ("admin_matching.py", "/prediction-markets/force-link"),
    ("admin_matching.py", "/prediction-markets/unlink"),
    ("admin_matching.py", "/entity-registry/seed"),
    ("admin_matching.py", "/entity-registry/canonicalize"),
    ("admin_celery.py", "/celery-purge-background"),
    ("admin_events.py", "/events/delete-duplicates"),
    ("admin_providers.py", "/espn/cleanup-bad-matches"),
]

_ROUTES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "routes")


def _handler_source(module_file: str, route_path: str) -> str:
    """Return the source of the handler decorated with the given route path."""
    full = os.path.join(_ROUTES_DIR, module_file)
    src = open(full).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr in {"post", "delete", "put", "patch"}
            ):
                continue
            if dec.args and isinstance(dec.args[0], ast.Constant):
                if dec.args[0].value == route_path:
                    return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"route not found: {module_file} {route_path}")


@pytest.mark.parametrize("module_file,route_path", DESTRUCTIVE_ROUTES)
def test_destructive_route_calls_the_gate(module_file, route_path):
    body = _handler_source(module_file, route_path)
    assert "_check_admin_destructive(" in body, (
        f"{module_file} {route_path} does not call _check_admin_destructive — a "
        f"destructive route is reachable with ADMIN_TOKEN alone."
    )


@pytest.mark.parametrize("module_file,route_path", DESTRUCTIVE_ROUTES)
def test_destructive_route_does_not_also_keep_the_weaker_gate(module_file, route_path):
    """A leftover `_check_admin_secret(...)` alongside the new gate would be
    harmless here, but a leftover that REPLACED it on a later edit would not be
    visible. Assert the handler auths exactly once, through the strong gate."""
    body = _handler_source(module_file, route_path)
    assert "_check_admin_secret(" not in body, (
        f"{module_file} {route_path} still calls _check_admin_secret directly"
    )
