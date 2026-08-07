"""Pure contract for eval imports across local and CI invocation contexts."""

from __future__ import annotations


CANONICAL_PREFIX = "scripts.evals."
FORBIDDEN_PREFIXES = ("backend.scripts.evals.", ".")


def evaluate(case: dict) -> dict:
    import_path = str(case.get("import_path") or "")
    invocation = case.get("invocation")
    reasons: list[str] = []

    if import_path.startswith("backend.scripts.evals."):
        reasons.append("repo_root_only_import")
    elif import_path.startswith("."):
        reasons.append("relative_import_context_loss")
    elif not import_path.startswith(CANONICAL_PREFIX):
        reasons.append("noncanonical_eval_import")

    if case.get("same_file_loaded_twice"):
        reasons.append("duplicate_module_identity")
    if case.get("namespace_ambiguous"):
        reasons.append("namespace_ambiguity")
    if not case.get("module_discovered", True):
        reasons.append("future_eval_not_discovered")

    supported = {
        "repo_root_pytest",
        "backend_pytest",
        "direct_script",
        "module_execution",
    }
    if invocation not in supported:
        reasons.append("unsupported_invocation")
    if invocation == "direct_script" and case.get("requires_package_context"):
        reasons.append("direct_execution_package_dependency")

    return {
        "verdict": "REFUSE" if reasons else "ALLOW",
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def evaluate_suite(rows: list[dict]) -> dict:
    results = [evaluate(row) for row in rows]
    reasons = [reason for result in results for reason in result["reason_codes"]]
    contexts = {row.get("invocation") for row in rows if evaluate(row)["verdict"] == "ALLOW"}
    if not {"repo_root_pytest", "backend_pytest"} <= contexts:
        reasons.append("pytest_context_gap")
    return {
        "verdict": "REFUSE" if reasons else "ALLOW",
        "reason_codes": list(dict.fromkeys(reasons)),
    }

