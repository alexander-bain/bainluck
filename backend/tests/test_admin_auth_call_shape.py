"""The admin auth gate must be called with ``request=`` as a KEYWORD (INT-067).

``_check_admin_secret`` and ``_check_admin_destructive`` are declared as::

    def _check_admin_secret(secret: str | None = None, *, request: Request | None = None)

``request`` is keyword-ONLY. A call written ``_check_admin_secret(request)``
therefore binds the ``Request`` object to ``secret`` and leaves ``request=None``.
The gate then reads the ``Authorization`` header off ``None``, finds nothing, and
raises 403 — for every caller, including one holding a perfectly valid
``ADMIN_TOKEN``. The endpoint is not "locked down"; it is unreachable.

WHY THIS NEEDS A TEST AND NOT JUST A FIX
----------------------------------------
The failure is invisible to every gate we run. It type-checks (``Request`` is a
valid ``str | None`` at runtime — Python does not enforce annotations), it
imports, it passes ``test_startup``, and the full 14,787-item backend suite was
GREEN on it. Nothing in the repo exercises a live admin route with a real token,
so "the endpoint 403s forever" and "the endpoint is correctly protected" are the
same observation to CI — gotcha #53's shape, applied to an auth gate.

It shipped in q350 (`/api/admin/kalshi/scan-report`) as the ONE call site out of
47 in `admin_providers.py` that dropped the keyword, and it was caught only
because INT-067 tried to take the #1845 mechanism read off that exact endpoint
two hours after deploying it. Had the read not been owed, an endpoint built
specifically to make a production freeze measurable would have answered 403 to
every future reader, and the natural diagnosis — "my token is wrong" — points
away from the code.

This test is cheap, exhaustive, and structural, so the next one cannot ship.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).parents[1] / "app" / "routes"

#: The auth gates whose ``request`` parameter is keyword-only.
KEYWORD_ONLY_REQUEST_GATES = {"_check_admin_secret", "_check_admin_destructive"}


def _offending_calls() -> list[tuple[str, int, str]]:
    """Every gate call that passes something positionally where it must not.

    Returns ``(filename, lineno, rendered_call)`` for each violation. A call is a
    violation when it hands the gate a POSITIONAL argument that is (or contains)
    the name ``request`` — the exact confusion the keyword-only marker exists to
    prevent. A legitimate positional first argument is ``secret``, which is
    retained for signature compatibility and ignored for auth.
    """
    bad: list[tuple[str, int, str]] = []

    for path in sorted(ROUTES_DIR.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a parse failure is its own test's job
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name not in KEYWORD_ONLY_REQUEST_GATES:
                continue

            for arg in node.args:  # positional only; keywords are fine by construction
                if isinstance(arg, ast.Name) and arg.id == "request":
                    bad.append((path.name, node.lineno, f"{name}({arg.id})"))

    return bad


def test_request_is_never_passed_positionally_to_an_admin_auth_gate():
    """A positional ``request`` silently disables the gate's only transport."""
    offenders = _offending_calls()
    assert offenders == [], (
        "These admin auth calls pass `request` POSITIONALLY, which binds it to "
        "`secret` and leaves `request=None` — the endpoint will 403 on every "
        "valid token:\n  "
        + "\n  ".join(f"{f}:{ln}  {call}" for f, ln, call in offenders)
        + "\n\nUse `_check_admin_secret(secret, request=request)` "
        "(or `_check_admin_secret(request=request)` when the route declares no "
        "`secret` query parameter)."
    )


def test_the_guard_can_actually_fail(tmp_path, monkeypatch):
    """Non-vacuity: prove the detector fires on the exact defect it was written for.

    A guard over a directory that happens to be clean is indistinguishable from a
    guard that matches nothing — #121's constant-oracle family and gotcha #130.
    So point it at a directory containing the known-bad line and require a hit.
    """
    fake_routes = tmp_path / "routes"
    fake_routes.mkdir()
    (fake_routes / "admin_bad.py").write_text(
        "def r(request):\n    _check_admin_secret(request)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("tests.test_admin_auth_call_shape.ROUTES_DIR", fake_routes)

    offenders = _offending_calls()
    assert offenders == [("admin_bad.py", 2, "_check_admin_secret(request)")]


@pytest.mark.parametrize("gate", sorted(KEYWORD_ONLY_REQUEST_GATES))
def test_gate_really_declares_request_keyword_only(gate):
    """If someone relaxes the signature, this test — not production — says so."""
    import inspect

    from app.routes import admin_utils

    sig = inspect.signature(getattr(admin_utils, gate))
    param = sig.parameters["request"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{gate}'s `request` is no longer keyword-only ({param.kind}). "
        "Either restore the marker or delete this suite deliberately — but do "
        "not leave positional calls legal by accident."
    )
