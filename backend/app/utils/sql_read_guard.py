"""Read-only SQL policy for the admin ad-hoc query rails, as a pure module.

No ORM session, no request context, no I/O. Every guard here is a pure function over
a SQL string, so the whole policy is testable without a database — which matters
concretely: this repo's sandbox has no local Postgres, so the existing
`tests/integration/test_route_admin_db_query.py` guards are `skipif(no DATABASE_URL)`
and run in CI only. A policy that can only be tested where it cannot be run locally
is a policy that drifts. (Ruling 005, extract-on-touch: the extracted unit must be
pure, or "moved the code" does not discharge it.)

THE CENTRAL DESIGN DECISION, because it is what keeps the rail safe:

    The caller never supplies the word EXPLAIN. The caller always supplies a plain
    SELECT/WITH, and the server composes `EXPLAIN (...) <statement>` around it.

So the prefix allowlist below is *unchanged* by the addition of plan support, and
cannot be bypassed by typing `EXPLAIN ...` — that string does not start with SELECT
or WITH and is rejected exactly as it was before. Widening the allowlist to admit an
`EXPLAIN` prefix would have been the obvious implementation and is the one that opens
the hole: `EXPLAIN ANALYZE` *executes* its statement, so an allowlist that admits the
prefix must then re-derive what the rest of the string does.
"""

from __future__ import annotations

import re

# --- bounds -----------------------------------------------------------------

MAX_ROW_CAP = 1000
DEFAULT_STATEMENT_TIMEOUT_MS = 10_000
MIN_EXPLAIN_TIMEOUT_MS = 500
# Heroku's H12 request boundary is 30s; a plan request must fail inside it rather
# than ride to a 503 (the failure mode #1494 was filed on).
MAX_EXPLAIN_TIMEOUT_MS = 25_000

MUTATING_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)

# Statements that may be planned WITHOUT executing. `WITH` is allowed here because
# EXPLAIN alone never runs the statement.
_READ_PREFIXES = ("SELECT", "WITH")


class SqlGuardError(ValueError):
    """A statement failed the read-only policy.

    `detail` is safe to hand straight back to an admin caller as an HTTP 400 body.
    """

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def normalize_statement(sql: str) -> str:
    """Strip surrounding whitespace and a single trailing semicolon."""
    return (sql or "").strip().rstrip(";")


def assert_read_only(sql: str) -> str:
    """Return the normalized statement, or raise SqlGuardError.

    This is the pre-existing db-query policy, moved verbatim in behaviour:
    no embedded semicolons, no mutating keyword, must start with SELECT or WITH.
    """
    stmt = normalize_statement(sql)

    if ";" in stmt:
        raise SqlGuardError("Multi-statement queries not allowed")

    if MUTATING_RE.search(stmt):
        raise SqlGuardError("Only SELECT queries are allowed")

    if not stmt.lstrip().upper().startswith(_READ_PREFIXES):
        raise SqlGuardError("Query must start with SELECT or WITH")

    return stmt


def assert_executable_for_analyze(sql: str) -> str:
    """Stricter gate for EXPLAIN ANALYZE, which DOES execute the statement.

    Beyond `assert_read_only`, the statement must begin with SELECT — a leading
    `WITH` is refused here even though it is fine to *plan*. The reason is
    data-modifying CTEs: `WITH x AS (...) INSERT INTO ...` is a real Postgres
    construct whose mutation lives in the middle of the string, so the only thing
    standing between it and execution would be a keyword regex. `_MUTATING_RE` does
    catch that particular example, but a keyword regex is a denylist, and the
    difference between planning and executing is exactly where a denylist should not
    be the last line of defence.

    Note this is defence in depth, not the sole protection: the caller runs plans
    inside `SET TRANSACTION READ ONLY`, which is what structurally prevents a write.
    """
    stmt = assert_read_only(sql)

    if not stmt.lstrip().upper().startswith("SELECT"):
        raise SqlGuardError(
            "EXPLAIN ANALYZE executes the statement, so it is restricted to a "
            "statement beginning with SELECT (a leading WITH is refused)"
        )

    return stmt


def build_explain_sql(sql: str, *, analyze: bool = False) -> str:
    """Compose the EXPLAIN wrapper. `sql` must already have passed the guards.

    BUFFERS is only added alongside ANALYZE: without execution there are no shared
    block counts worth reporting, and pairing them keeps the emitted option list
    honest about whether the numbers are measured or estimated.
    """
    options = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    return f"EXPLAIN ({options}) {normalize_statement(sql)}"


def resolve_explain_timeout_ms(requested: int | None) -> int:
    """Clamp a caller-supplied plan timeout into [MIN, MAX].

    Always returns a number: there is no path on which a plan request runs unbounded.
    """
    if requested is None:
        return DEFAULT_STATEMENT_TIMEOUT_MS
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return DEFAULT_STATEMENT_TIMEOUT_MS
    return max(MIN_EXPLAIN_TIMEOUT_MS, min(value, MAX_EXPLAIN_TIMEOUT_MS))


def resolve_row_cap(limit: int | None) -> int:
    """Server-side row cap: never above MAX_ROW_CAP, never below 1."""
    try:
        value = int(limit) if limit is not None else MAX_ROW_CAP
    except (TypeError, ValueError):
        value = MAX_ROW_CAP
    return max(1, min(value, MAX_ROW_CAP))


def needs_limit_wrap(sql: str) -> bool:
    """Whether the row-cap LIMIT still has to be appended (existing heuristic)."""
    lowered = normalize_statement(sql).lower()
    return not ("limit" in lowered.split("order")[-1] or "fetch" in lowered)
