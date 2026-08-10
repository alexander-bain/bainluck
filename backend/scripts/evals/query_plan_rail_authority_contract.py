"""LAT-P019 query-plan safety contract.

Extends the canonical ``admin_surface_truth_contract``.  This oracle describes
the authority boundary for a diagnostic rail which accepts SQL: authentication,
non-executing plans by default, explicit structural protection for execution,
and bounded/redacted output.  Keyword allowlists are evidence, but never a
substitute for those structural controls.
"""

from __future__ import annotations


def evaluate(case: dict) -> dict:
    reasons: list[str] = []

    if not case.get("authenticated", False):
        reasons.append("unauthenticated")
    if case.get("caller_supplied_explain", False):
        reasons.append("caller_controls_explain")
    if case.get("multiple_statements", False):
        reasons.append("multiple_statements")
    if not case.get("read_prefix", False):
        reasons.append("non_read_prefix")

    if case.get("analyze", False):
        if not case.get("read_only_transaction", False):
            reasons.append("analyze_not_read_only")
        # SELECT can call pg_cancel_backend, pg_advisory_lock, nextval, and
        # extension functions. A prefix/keyword check does not make execution
        # side-effect free.
        if not case.get("executable_function_policy", False):
            reasons.append("executable_select_functions_uncontrolled")

    timeout_ms = case.get("timeout_ms")
    if timeout_ms is None or timeout_ms < 1 or timeout_ms > 25_000:
        reasons.append("timeout_unbounded")

    if not case.get("error_redacted", False):
        reasons.append("error_disclosure")
    if not case.get("query_redacted", False):
        reasons.append("query_disclosure")
    response_cap = case.get("response_cap_bytes")
    if response_cap is None or response_cap <= 0:
        reasons.append("response_unbounded")
    if not case.get("postgres_semantics_tested", False):
        reasons.append("database_semantics_unproven")

    return {"verdict": "REFUSE" if reasons else "ACCEPT", "reasons": reasons}

