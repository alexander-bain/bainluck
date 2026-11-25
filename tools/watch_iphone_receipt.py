"""Fail-closed receipt for the full hosted BainLuckTests compatibility gate."""
import argparse
import json
from pathlib import Path
import re
from typing import Any


_CASE_RESULT_RE = re.compile(
    r"^Test Case '([^']+)' (passed|failed|skipped)\b", re.MULTILINE
)
_CASE_TIMEOUT_RE = re.compile(
    r"^Test Case '([^']+)' exceeded (?:maximum )?execution time allowance\b",
    re.MULTILINE,
)
_FAILING_HEADER_RE = re.compile(r"^Failing tests:\s*$", re.MULTILINE)
_FAILING_ENTRY_RE = re.compile(r"^[ \t]+([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\(\)\s*$")


def _normalize_test_name(raw: str) -> str:
    name = raw.strip()
    if name.startswith("-[") and name.endswith("]"):
        name = name[2:-1].strip()
    if name.endswith("()"):
        name = name[:-2]
    parts = name.split(None, 1)
    if len(parts) == 2:
        name = f"{parts[0]}.{parts[1]}"
    if name.startswith("BainLuckTests."):
        name = name[len("BainLuckTests.") :]
    return name


def parse_log_outcomes(log: str, suite_name: str = "All tests") -> dict[str, Any]:
    """Extract executed counts and failing/timed-out test names from xcodebuild output."""
    passed_cases: set[str] = set()
    failed_cases: set[str] = set()
    skipped_cases: set[str] = set()
    timed_out_cases: set[str] = set()

    for raw_name, status in _CASE_RESULT_RE.findall(log):
        name = _normalize_test_name(raw_name)
        if not name:
            continue
        if status == "passed":
            passed_cases.add(name)
        elif status == "failed":
            failed_cases.add(name)
        elif status == "skipped":
            skipped_cases.add(name)

    for raw_name in _CASE_TIMEOUT_RE.findall(log):
        name = _normalize_test_name(raw_name)
        if name:
            timed_out_cases.add(name)

    # Trailing "Failing tests:" summary catches crashes/timeouts that lack a failed Test Case line.
    for match in _FAILING_HEADER_RE.finditer(log):
        for line in log[match.end() :].splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if not line[0].isspace() or stripped.startswith("**"):
                break
            entry = _FAILING_ENTRY_RE.match(line)
            if entry:
                name = _normalize_test_name(entry.group(1))
                if name and name not in timed_out_cases:
                    failed_cases.add(name)

    # Ensure each test lands in exactly one bucket (timeout > failure > passed > skipped).
    failed_cases -= timed_out_cases
    passed_cases -= failed_cases | timed_out_cases
    skipped_cases -= passed_cases | failed_cases | timed_out_cases

    has_case_lines = bool(
        passed_cases or failed_cases or timed_out_cases or skipped_cases
    )
    if has_case_lines:
        executed = (
            len(passed_cases)
            + len(failed_cases)
            + len(timed_out_cases)
            + len(skipped_cases)
        )
        passed = len(passed_cases)
        failed = len(failed_cases)
        timed_out = len(timed_out_cases)
        skipped = len(skipped_cases)
    else:
        escaped = re.escape(suite_name)
        totals = re.findall(
            rf"^Test Suite '{escaped}' (?:passed|failed)[^\n]*\n[ \t]*Executed (\d+) tests?, with (\d+) failures?",
            log,
            re.MULTILINE,
        )
        executed = sum(int(count) for count, _ in totals)
        failed = sum(int(failures) for _, failures in totals)
        timed_out = 0
        passed = max(0, executed - failed)
        skipped = 0

    return {
        "tests": executed,
        "passed": passed,
        "failed": failed,
        "timed_out": timed_out,
        "skipped": skipped,
        "failed_tests": sorted(failed_cases),
        "timed_out_tests": sorted(timed_out_cases),
    }


def verified_summary(
    log: str,
    exit_code: int,
    suite_name: str = "All tests",
    min_tests: int = 1,
) -> tuple[int, str]:
    success = re.search(r"^\*\* TEST (?:EXECUTE )?SUCCEEDED \*\*[ \t]*$", log, re.MULTILINE)
    failure = re.search(r"^\*\* TEST (?:EXECUTE )?FAILED \*\*[ \t]*$", log, re.MULTILINE)
    if exit_code != 0 or not success or failure:
        raise ValueError("Test process did not finish successfully")
    escaped = re.escape(suite_name)
    totals = re.findall(
        rf"^Test Suite '{escaped}' passed[^\n]*\n[ \t]*(Executed (\d+) tests?, with (\d+) failures?[^\n]*)",
        log,
        re.MULTILINE,
    )
    if len(totals) != 1:
        raise ValueError(f"Expected exactly one completed {suite_name} summary")
    line, count, failures = totals[0]
    if int(count) < min_tests or int(failures) != 0:
        raise ValueError(f"Suite must execute at least {min_tests} tests with zero failures")
    return int(count), line


def build_receipt(
    log: str,
    exit_code: int,
    sha: str,
    *,
    suite_name: str = "All tests",
    min_tests: int = 1,
) -> tuple[dict[str, Any], str | None]:
    """Build receipt.json payload and optional failure message, always failing closed."""
    receipt: dict[str, Any] = {"sha": sha, "exit_code": exit_code, "verdict": "UNPAID"}
    try:
        count, line = verified_summary(
            log,
            exit_code,
            suite_name=suite_name,
            min_tests=min_tests,
        )
    except ValueError as error:
        outcomes = parse_log_outcomes(log, suite_name=suite_name)
        reasons = [str(error)]
        below_min_tests = outcomes["tests"] < min_tests
        if below_min_tests:
            floor_reason = (
                f"Executed {outcomes['tests']} tests, below minimum floor of {min_tests}"
            )
            if floor_reason != str(error):
                reasons.append(floor_reason)
            receipt["min_tests_reason"] = floor_reason
        receipt.update(
            reason=str(error),
            reasons=reasons,
            tests=outcomes["tests"],
            passed=outcomes["passed"],
            failed=outcomes["failed"],
            timed_out=outcomes["timed_out"],
            skipped=outcomes["skipped"],
            min_tests=min_tests,
            below_min_tests=below_min_tests,
            failed_tests=outcomes["failed_tests"],
            timed_out_tests=outcomes["timed_out_tests"],
        )
        return receipt, f"BainLuckTests gate unpaid: {'; '.join(reasons)}"

    receipt.update(verdict="PASS", tests=count, summary=line)
    return receipt, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--suite-name", default="All tests")
    parser.add_argument("--min-tests", default=1, type=int)
    args = parser.parse_args()
    receipt, failure_message = build_receipt(
        args.log.read_text(errors="replace"),
        args.exit_code,
        args.sha,
        suite_name=args.suite_name,
        min_tests=args.min_tests,
    )
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    if failure_message is not None:
        raise SystemExit(failure_message)
    print(f"Source: {args.sha}\n{receipt['summary']}")


if __name__ == "__main__":
    main()
