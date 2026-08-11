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

import hashlib
import re

# --- bounds -----------------------------------------------------------------

MAX_ROW_CAP = 1000
DEFAULT_STATEMENT_TIMEOUT_MS = 10_000
MIN_EXPLAIN_TIMEOUT_MS = 500
# Heroku's H12 request boundary is 30s; a plan request must fail inside it rather
# than ride to a 503 (the failure mode #1494 was filed on).
MAX_EXPLAIN_TIMEOUT_MS = 25_000
# Contract `query_plan_rail_authority_contract.json`: `response_cap_bytes`. A plan
# tree is caller-influenced in SIZE as well as content — `timeout_ms` bounds how long
# the database works, not how many bytes come back.
RESPONSE_CAP_BYTES = 262_144

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


# --- execution policy: which functions may RUN ------------------------------
#
# LAT-P027 (#1641). The premise this section corrects, stated plainly:
#
#     A SELECT prefix plus SET TRANSACTION READ ONLY does not make execution
#     side-effect free.
#
# `SELECT pg_cancel_backend(pid)` is a SELECT. It contains no mutating keyword. It
# passes every guard above. READ ONLY does not stop it, because READ ONLY forbids
# writes to TABLES and SEQUENCES — it says nothing about backend management or
# session advisory locks, whose effects are not transactional and therefore cannot
# be rolled back. The same is true of `pg_terminate_backend`, `pg_advisory_lock`
# (a session lock a stateless HTTP request can never release), and `pg_sleep`.
#
# Measured on this repo's own base before the fix, all three were accepted:
#     EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT pg_cancel_backend(12345)
#
# TWO CONTROLS, in the two directions a single control fails:
#
#   1. An ALLOWLIST of callable names (the structural control, `analyze` only). It
#      has no false-NEGATIVE path for functions nobody thought of — an operational
#      function invented tomorrow is refused because it is absent, not because it
#      was predicted. This is the contract's `executable_function_policy`.
#
#   2. A DENYLIST of known-operational names, matched against the RAW statement
#      text (the backstop, on EVERY executing path). It has no false-negative path
#      from parser desync, because it does not parse: an `E'\''` escape string can
#      desynchronise literal-stripping and hide a call from control 1, but the name
#      is still sitting in the raw bytes for control 2 to find.
#
# Neither alone is sufficient; the failure modes are disjoint, which is the point.

# Applied to every path that EXECUTES, including the plain row path. That path is
# older and more used than ANALYZE, and it has been running these functions since
# long before the plan rail existed — the static audit on #1641 framed this as an
# ANALYZE defect, but gating only ANALYZE would have left the identical hole one
# JSON field away. Deliberately NARROW, so it cannot break the lane's daily rail:
# it names operational functions, not everything impure.
_OPERATIONAL_FUNCTIONS = frozenset(
    {
        # Backend management — effects are immediate and not transactional.
        "pg_cancel_backend",
        "pg_terminate_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_switch_wal",
        "pg_create_restore_point",
        "pg_promote",
        # Advisory locks — a session lock taken by a stateless request is never
        # released by that request, and outlives it on the pooled connection.
        "pg_advisory_lock",
        "pg_advisory_lock_shared",
        "pg_advisory_unlock",
        "pg_advisory_unlock_all",
        "pg_advisory_unlock_shared",
        "pg_advisory_xact_lock",
        "pg_advisory_xact_lock_shared",
        "pg_try_advisory_lock",
        "pg_try_advisory_lock_shared",
        "pg_try_advisory_xact_lock",
        "pg_try_advisory_xact_lock_shared",
        # Sequence writes. READ ONLY does reject these, so this is depth, not the
        # only line — and depth is cheap here.
        "nextval",
        "setval",
        # Time burners: bounded by statement_timeout, but a rail whose whole job is
        # diagnosing latency should not offer a way to manufacture it.
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        # Filesystem, large objects, and outbound connections.
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "lo_unlink",
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "pg_logical_emit_message",
        # Statistics reset — destroys the very evidence this lane measures with.
        "pg_stat_reset",
        "pg_stat_statements_reset",
        "pg_stat_reset_shared",
    }
)

_OPERATIONAL_RE = re.compile(
    r"\b(" + "|".join(sorted(_OPERATIONAL_FUNCTIONS)) + r")\b", re.IGNORECASE
)

# SQL keywords that legitimately sit immediately before `(` and are not calls:
# `x IN (...)`, `OVER (...)`, `FILTER (WHERE ...)`, `numeric(10,2)`, `CAST(x AS int)`.
# Omitting one costs a FALSE REFUSAL naming the token, which is safe and a one-line
# fix; admitting a real function name here would be the dangerous direction, so this
# set contains only reserved words and type names.
#
# CAL-P037 added `not`, which was a plain omission sitting next to `and` and `or`:
# `WHERE NOT (a AND b)` was refused as "`not()` is not on the allowlist", a message
# naming a function that does not exist and cannot exist — NOT is a RESERVED word in
# PostgreSQL and therefore cannot be a function or type name, so it meets this set's
# criterion exactly and admits nothing.
#
# `materialized` is deliberately NOT here despite being the other token this rail
# kept refusing. It is an UNRESERVED keyword, so `materialized(...)` is a legal
# function name and putting it in this set would admit a real call. Its only
# non-call position is the CTE modifier, and that SHAPE is handled in
# `called_function_names` instead — narrow enough to keep this set's invariant true.
_SYNTACTIC_TOKENS = frozenset(
    {
        "all", "and", "any", "as", "asc", "at", "between", "by", "case", "cast",
        "cross", "desc", "distinct", "else", "end", "escape", "except", "exists",
        "filter", "first", "for", "from", "full", "group", "grouping", "having",
        "ilike", "in", "inner", "intersect", "interval", "into", "is", "join",
        "last", "lateral", "left", "like", "limit", "not", "nulls", "offset", "on",
        "only", "or", "order", "outer", "over", "partition", "range", "right", "rows",
        "select", "similar", "some", "then", "union", "using", "values", "when",
        "where", "window", "with", "within",
        # Type names, which appear before `(` in casts and length specifiers.
        "bigint", "bit", "boolean", "bytea", "char", "character", "date", "decimal",
        "double", "float", "inet", "int", "int2", "int4", "int8", "integer", "json",
        "jsonb", "numeric", "precision", "real", "smallint", "text", "time",
        "timestamp", "timestamptz", "tsquery", "tsvector", "uuid", "varchar",
    }
)

# Pure/read-only functions an analysis query legitimately needs. Absence is a
# refusal that NAMES the function, so widening this set is a one-line, reviewable
# change — which is the property that makes an allowlist maintainable here.
_PURE_FUNCTIONS = frozenset(
    {
        # Aggregates
        "array_agg", "avg", "bit_and", "bit_or", "bool_and", "bool_or", "corr",
        "count", "every", "json_agg", "jsonb_agg", "jsonb_object_agg", "max",
        "min", "mode", "percentile_cont", "percentile_disc", "stddev",
        "stddev_pop", "stddev_samp", "string_agg", "sum", "var_pop", "var_samp",
        "variance",
        # Window
        "cume_dist", "dense_rank", "first_value", "lag", "last_value", "lead",
        "nth_value", "ntile", "percent_rank", "rank", "row_number",
        # Conditional / null handling
        "coalesce", "greatest", "least", "nullif",
        # Strings
        "ascii", "btrim", "char_length", "character_length", "chr", "concat",
        "concat_ws", "decode", "encode", "format", "initcap", "left", "length",
        "lower", "lpad", "ltrim", "md5", "octet_length", "overlay", "position",
        "regexp_matches", "regexp_replace", "regexp_split_to_array",
        "regexp_split_to_table", "repeat", "replace", "reverse", "right", "rpad",
        "rtrim", "split_part", "starts_with", "strpos", "substr", "substring",
        "translate", "trim", "upper",
        # Numbers
        "abs", "ceil", "ceiling", "div", "exp", "floor", "ln", "log", "mod",
        "power", "random", "round", "sign", "sqrt", "trunc", "width_bucket",
        # Dates and times
        "age", "clock_timestamp", "current_date", "current_timestamp", "date_bin",
        "date_part", "date_trunc", "extract", "isfinite", "justify_days",
        "justify_hours", "justify_interval", "localtimestamp", "make_date",
        "make_interval", "make_timestamp", "make_timestamptz", "now",
        "statement_timestamp", "timezone", "to_char", "to_date", "to_number",
        "to_timestamp", "transaction_timestamp",
        # Arrays and sets
        "array_length", "array_position", "array_remove", "array_to_string",
        "cardinality", "generate_series", "string_to_array", "unnest",
        # JSON / JSONB
        "json_array_length", "json_build_array", "json_build_object",
        "json_extract_path", "json_extract_path_text", "json_typeof",
        "jsonb_array_elements", "jsonb_array_elements_text", "jsonb_array_length",
        "jsonb_build_array", "jsonb_build_object", "jsonb_each", "jsonb_each_text",
        "jsonb_extract_path", "jsonb_extract_path_text", "jsonb_object_keys",
        "jsonb_path_query", "jsonb_pretty", "jsonb_strip_nulls", "jsonb_typeof",
        "to_json", "to_jsonb",
        # Full-text search and trigram — this product's search path
        "phraseto_tsquery", "plainto_tsquery", "setweight", "similarity",
        "to_tsquery", "to_tsvector", "ts_headline", "ts_rank", "ts_rank_cd",
        "websearch_to_tsquery", "word_similarity",
        # Read-only introspection: sizes are the reason a latency lane opens a plan.
        "pg_column_size", "pg_database_size", "pg_indexes_size", "pg_relation_size",
        "pg_size_pretty", "pg_table_size", "pg_total_relation_size", "pg_typeof",
    }
)

_ANALYZE_CALLABLE = _PURE_FUNCTIONS | _SYNTACTIC_TOKENS

_DOLLAR_QUOTED_RE = re.compile(r"\$(\w*)\$.*?\$\1\$", re.DOTALL)
_SINGLE_QUOTED_RE = re.compile(r"'(?:[^']|'')*'")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")

_QUOTED_IDENT_CALL_RE = re.compile(r'"[^"]*"\s*\(')
_QUALIFIED_CALL_RE = re.compile(r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(")
_CALL_RE = re.compile(r"([A-Za-z_]\w*)\s*\(")

# The CTE materialization modifier: `WITH x AS MATERIALIZED (SELECT ...)` and its
# `AS NOT MATERIALIZED` twin. This is the ONLY position in which `MATERIALIZED`
# precedes `(` without being a call, so the keyword is neutralised here — anchored
# to a preceding `AS` — rather than allowlisted as a callable name. `MATERIALIZED`
# is unreserved in PostgreSQL, so a bare `materialized(...)` really can be a
# user-defined function and must stay refused; matching the shape keeps that true
# while clearing the false refusal. `AS` is left in place so nothing else shifts.
_CTE_MATERIALIZED_RE = re.compile(
    r"\bas\s+(?:not\s+)?materialized\s*(?=\()", re.IGNORECASE
)


def strip_sql_noise(sql: str) -> str:
    """Blank out string literals and comments so a `name(` scan sees only code.

    Order matters: dollar-quoted bodies can contain single quotes, and both kinds of
    literal can contain `--`. Literals are replaced with an empty quoted pair rather
    than deleted, so token adjacency is preserved.

    This is a lexer approximation, NOT a parser, and it is documented as one. An
    `E'\\''` escape string can desynchronise it. That is survivable only because it
    is never the sole control: `assert_no_operational_functions` scans the RAW text,
    where a desync cannot hide a name. Trust this function to reduce false refusals,
    never to be the thing that makes execution safe.
    """
    text = _DOLLAR_QUOTED_RE.sub("''", sql or "")
    text = _SINGLE_QUOTED_RE.sub("''", text)
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    return _LINE_COMMENT_RE.sub(" ", text)


def called_function_names(sql: str) -> set[str]:
    """Every lowercased identifier used as a call in `sql`, literals/comments removed.

    The CTE materialization modifier is dropped first: `AS MATERIALIZED (` is a
    planner hint, not a call, and it is the one place the keyword precedes `(`
    legitimately. Everything else keeps the deliberately dumb `name(` scan —
    over-reporting a name costs a refusal that says which token, under-reporting
    one is how a call gets executed unseen.
    """
    text = _CTE_MATERIALIZED_RE.sub("as ", strip_sql_noise(sql))
    return {name.lower() for name in _CALL_RE.findall(text)}


def assert_no_operational_functions(sql: str) -> None:
    """Backstop for EVERY executing path. Raw-text match, deliberately unparsed.

    Refuses on a bare mention, so `WHERE name = 'pg_sleep'` is refused too. That is
    the correct direction for a backstop: a false refusal names the token and costs
    one rewrite, while a false acceptance cancels a production backend.
    """
    match = _OPERATIONAL_RE.search(normalize_statement(sql))
    if match:
        raise SqlGuardError(
            f"`{match.group(1)}` is an operational function and cannot be executed "
            f"by this rail. A read-only transaction does not make it safe: its "
            f"effect is not transactional and cannot be rolled back. Use "
            f"`explain: true` without `analyze` to inspect a plan without executing."
        )


def assert_analyze_function_policy(sql: str) -> None:
    """Allowlist gate for ANALYZE: every call in the statement must be known-pure.

    Schema-qualified and quoted-identifier calls are refused outright rather than
    resolved. `pg_catalog.pg_cancel_backend(...)` and `"pg_cancel_backend"(...)` are
    the two ways to spell a call whose bare name a scan would miss, and no analysis
    query needs either spelling — so refusing the SHAPE removes the bypass class
    without needing to reason about search_path.
    """
    stripped = strip_sql_noise(normalize_statement(sql))

    if _QUOTED_IDENT_CALL_RE.search(stripped):
        raise SqlGuardError(
            "EXPLAIN ANALYZE executes the statement, so a quoted-identifier function "
            "call is refused (it can spell a name this policy scans for)"
        )

    qualified = _QUALIFIED_CALL_RE.search(stripped)
    if qualified:
        raise SqlGuardError(
            f"EXPLAIN ANALYZE executes the statement, so the schema-qualified call "
            f"`{qualified.group(1)}.{qualified.group(2)}(` is refused; call the "
            f"function unqualified if it is a permitted one"
        )

    for name in sorted(called_function_names(stripped)):
        if name not in _ANALYZE_CALLABLE:
            raise SqlGuardError(
                f"`{name}()` is not on the allowlist of functions that may be "
                f"EXECUTED by EXPLAIN ANALYZE. Use `explain: true` without "
                f"`analyze` to plan this statement without running it."
            )


def assert_executable_for_analyze(sql: str) -> str:
    """Stricter gate for EXPLAIN ANALYZE, which DOES execute the statement.

    Three layers beyond `assert_read_only`:

    1. The statement must begin with SELECT — a leading `WITH` is refused even
       though it is fine to *plan*. The reason is data-modifying CTEs:
       `WITH x AS (...) INSERT INTO ...` is a real Postgres construct whose mutation
       lives in the middle of the string, so the only thing standing between it and
       execution would be a keyword regex. `_MUTATING_RE` does catch that particular
       example, but a keyword regex is a denylist, and the difference between
       planning and executing is exactly where a denylist should not be last.
    2. No operational function anywhere in the raw text.
    3. Every call is on the pure-function allowlist.

    `SET TRANSACTION READ ONLY` still wraps the execution, but it is no longer
    described here as the thing that "structurally prevents" the danger — it
    prevents table and sequence writes, and #1641 was filed because the functions
    that matter are not writes.
    """
    stmt = assert_read_only(sql)

    if not stmt.lstrip().upper().startswith("SELECT"):
        raise SqlGuardError(
            "EXPLAIN ANALYZE executes the statement, so it is restricted to a "
            "statement beginning with SELECT (a leading WITH is refused)"
        )

    assert_no_operational_functions(stmt)
    assert_analyze_function_policy(stmt)

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


# --- disclosure and bounds on the way OUT ------------------------------------


def fingerprint_statement(sql: str) -> str:
    """A stable, non-reversing handle for a statement.

    Replaces echoing the statement back. The echo carried no information the caller
    did not already have — they wrote it — while putting the full text, literals
    included, into browser state, screenshots and client telemetry. A fingerprint
    keeps the one property the echo was actually used for: confirming that the plan
    you are reading belongs to the statement you sent, and matching two responses to
    each other across a before/after pair.
    """
    return hashlib.sha256(normalize_statement(sql).encode("utf-8")).hexdigest()[:16]


def explain_mode_label(*, analyze: bool) -> str:
    """The server-composed option list. Contains no caller-supplied text."""
    return "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"


def summarize_plan(plan):
    """Root-node scalars only, for when the full tree is over the byte cap.

    Deliberately a fixed set of numeric/enum fields: no `Filter`, no `Index Cond`,
    no `Output` — those are the plan fields that quote the caller's literals, and a
    summary is the one place we can drop them without losing the plan's purpose.
    """
    node = plan
    if isinstance(node, list) and node:
        node = node[0]
    if isinstance(node, dict):
        node = node.get("Plan", node)
    if not isinstance(node, dict):
        return None
    keep = (
        "Node Type", "Relation Name", "Startup Cost", "Total Cost", "Plan Rows",
        "Plan Width", "Actual Startup Time", "Actual Total Time", "Actual Rows",
        "Actual Loops", "Shared Hit Blocks", "Shared Read Blocks",
    )
    return {k: node[k] for k in keep if k in node}


def cap_plan_payload(plan, *, cap_bytes: int = RESPONSE_CAP_BYTES) -> dict:
    """Bound the serialized plan, and say so explicitly when it is bounded.

    `timeout_ms` bounds DATABASE time and nothing else; a plan over a wide
    partitioned scan can be megabytes of JSON well inside its time budget. Returns
    the fields to merge into the response, always including `truncated` so the
    caller never has to infer completeness from size (gotcha #53: an empty-ish
    response and a complete one must not read the same).
    """
    import json as _json

    try:
        encoded = _json.dumps(plan, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return {
            "plan": None,
            "truncated": True,
            "truncation_reason": "plan_not_serializable",
            "plan_bytes": None,
            "response_cap_bytes": cap_bytes,
        }

    if len(encoded) <= cap_bytes:
        return {
            "plan": plan,
            "truncated": False,
            "plan_bytes": len(encoded),
            "response_cap_bytes": cap_bytes,
        }

    return {
        "plan": None,
        "plan_summary": summarize_plan(plan),
        "truncated": True,
        "truncation_reason": "response_cap_bytes",
        "plan_bytes": len(encoded),
        "response_cap_bytes": cap_bytes,
    }


# SQLSTATE -> stable reason code. The codes describe an error CLASS and quote no
# caller data, which is what makes them safe to return where `str(e)` was not.
_SQLSTATE_REASONS = {
    "57014": "statement_timeout",
    "25006": "read_only_transaction",
    "42601": "syntax_error",
    "42P01": "undefined_table",
    "42703": "undefined_column",
    "42883": "undefined_function",
    "42501": "insufficient_privilege",
    "42P02": "undefined_parameter",
    "22P02": "invalid_text_representation",
    "22012": "division_by_zero",
    "53100": "disk_full",
    "53200": "out_of_memory",
    "53300": "too_many_connections",
    "54001": "statement_too_complex",
    "55P03": "lock_not_available",
    "40P01": "deadlock_detected",
}

_SQLSTATE_CLASS_REASONS = {
    "22": "data_error",
    "23": "integrity_constraint_violation",
    "25": "invalid_transaction_state",
    "42": "invalid_statement",
    "53": "insufficient_resources",
    "54": "program_limit_exceeded",
    "57": "operator_intervention",
}


def _sqlstate_of(exc: BaseException) -> str | None:
    """Dig the SQLSTATE out of a SQLAlchemy wrapper or a raw DBAPI error."""
    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is None:
            continue
        for attr in ("sqlstate", "pgcode"):
            value = getattr(candidate, attr, None)
            if value:
                return str(value)
    return None


def classify_db_error(exc: BaseException) -> str:
    """Map a database exception to a stable reason code that discloses nothing.

    Replaces `detail=str(e)[:500]`. **Truncation is not redaction** — the first 500
    characters of a Postgres error are the most disclosing 500, because that is
    where the offending statement fragment, the literal values and the schema names
    live. A prefix of a secret is a secret.
    """
    state = _sqlstate_of(exc)
    if state:
        if state in _SQLSTATE_REASONS:
            return _SQLSTATE_REASONS[state]
        if state[:2] in _SQLSTATE_CLASS_REASONS:
            return _SQLSTATE_CLASS_REASONS[state[:2]]
    # Python 3.11+ aliases asyncio.TimeoutError to the builtin, so one check covers both.
    if isinstance(exc, TimeoutError):
        return "statement_timeout"
    return "query_failed"
