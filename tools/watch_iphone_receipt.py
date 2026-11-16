"""Fail-closed receipt for the full hosted BainLuckTests compatibility gate."""
import argparse
import json
from pathlib import Path
import re


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--suite-name", default="All tests")
    parser.add_argument("--min-tests", default=1, type=int)
    args = parser.parse_args()
    receipt = {"sha": args.sha, "exit_code": args.exit_code, "verdict": "UNPAID"}
    try:
        count, line = verified_summary(
            args.log.read_text(errors="replace"),
            args.exit_code,
            suite_name=args.suite_name,
            min_tests=args.min_tests,
        )
    except ValueError as error:
        receipt["reason"] = str(error)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        raise SystemExit(f"BainLuckTests gate unpaid: {error}")
    receipt.update(verdict="PASS", tests=count, summary=line)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Source: {args.sha}\n{line}")


if __name__ == "__main__":
    main()
