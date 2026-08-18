"""Q332 Item 5 — ``GET /api/admin/query`` is retired; one read rail, not two.

Asserted at the ROUTE BOUNDARY, deliberately. A test that only proved "the handler
raises" would still pass if the handler were reachable, and the claim being made here
is that the door does not exist — not that it is locked.
"""
from __future__ import annotations

from pathlib import Path

from app.main import app

ROUTES_DIR = Path(__file__).resolve().parents[1] / "app/routes"


def _paths() -> set[str]:
    return {getattr(route, "path", None) for route in app.routes}


def test_the_second_read_rail_is_gone_from_the_route_table():
    assert "/api/admin/query" not in _paths(), (
        "GET /api/admin/query is back. It is a second door into the same database "
        "that does NOT run assert_read_only or assert_no_operational_functions — "
        "pg_terminate_backend passes its two string checks (#1641). Use "
        "POST /api/admin/db-query."
    )


def test_the_surviving_rail_is_the_hardened_one():
    """Guards against 'retiring' the wrong rail and leaving the weak one standing."""
    assert "/api/admin/db-query" in _paths()


def _executable_text(source: str) -> str:
    """Source with comments and string literals removed.

    The distinction is load-bearing, not pedantry: this file, ``admin_utils`` and
    ``db_query.py`` all NAME ``?secret=`` in prose precisely to record that it is
    forbidden. A raw substring scan reads those refusals as violations and would
    push a future author to stop documenting the ban in order to pass the test —
    deleting the institutional memory that is the point. What is banned is building
    or parsing such a URL, which is code.
    """
    import io
    import tokenize

    kept = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return " ".join(kept)


def test_no_admin_route_reintroduces_query_string_secret_auth():
    """The retired rail took its token in the URL. Nothing may re-adopt that.

    Queue #252 Item 3 removed the ``?secret=`` query-parameter auth path — the
    secret must NEVER appear in the URL (history, Referer, logs, shared links).
    Header ``Authorization: Bearer`` is the only accepted transport. In particular
    ``secret: str = Query(...)`` must be GONE from every admin handler: it is
    not merely ignored, the parameter does not exist.
    """
    # (a) No admin module may construct or parse a URL carrying the token.
    offenders = []
    for path in sorted(ROUTES_DIR.glob("admin*.py")):
        if "?secret=" in _executable_text(path.read_text()):
            offenders.append(path.name)
    assert not offenders, f"query-string secret auth reintroduced in: {offenders}"

    # (b) The retired ``secret: str = Query(...)`` param itself must be GONE
    # from the cohort module — not merely ignored by _check_admin_secret.
    # Other admin modules still declare it for call-site compat (ignored), but
    # the cohort lane re-proves GONE per Queue #252 Item 3 and C-ADHOC cert.
    cohort_path = ROUTES_DIR / "admin_cohort.py"
    cohort_src = cohort_path.read_text()
    cohort_code = _executable_text(cohort_src)
    assert "secret" not in cohort_code or "Query" not in cohort_code, (
        "retired ?secret= Query param still declared in admin_cohort.py "
        "(must be GONE — header-only Bearer, not ignored compat): "
        f"code tokens contain secret={('secret' in cohort_code)} Query={('Query' in cohort_code)}"
    )
    # Line-level executability: no ``secret ... Query`` line survives
    for line in cohort_src.splitlines():
        if "secret" in line and "Query" in line and not line.strip().startswith("#"):
            assert "secret" not in _executable_text(line), (
                f"retired Query param line still present in admin_cohort.py: {line.strip()[:120]}"
            )


def test_db_query_script_uses_the_post_rail_with_a_bearer_header():
    """The consumer census's only live code entry. It must not resurrect the old URL."""
    source = (Path(__file__).resolve().parents[1] / "scripts/db_query.py").read_text()
    code = _executable_text(source)

    assert "/api/admin/db-query" in source, "script no longer targets the POST rail"
    assert "Authorization" in source and "Bearer" in source
    # In CODE, not in the docstring that explains why the old form is gone.
    assert "?secret=" not in code
    assert "/api/admin/query" not in code
