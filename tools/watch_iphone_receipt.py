"""Fail-closed receipt for the full hosted BainLuckTests compatibility gate."""
import argparse
import json
from pathlib import Path
import re


def verified_summary(log: str, exit_code: int) -> tuple[int, str]:
    if exit_code != 0 or not re.search(r"^\*\* TEST SUCCEEDED \*\*\s*$", log, re.MULTILINE):
        raise ValueError("Test process did not finish successfully")
    totals = re.findall(
        r"^Test Suite 'All tests' passed[^\n]*\n[ \t]*(Executed (\d+) tests?, with (\d+) failures?[^\n]*)",
        log,
        re.MULTILINE,
    )
    if len(totals) != 1:
        raise ValueError("Expected exactly one completed All tests summary")
    line, count, failures = totals[0]
    if int(count) <= 0 or int(failures) != 0:
        raise ValueError("Full suite must execute nonzero tests with zero failures")
    return int(count), line


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = {"sha": args.sha, "exit_code": args.exit_code, "verdict": "UNPAID"}
    try:
        count, line = verified_summary(args.log.read_text(errors="replace"), args.exit_code)
    except ValueError as error:
        receipt["reason"] = str(error)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        raise SystemExit(f"BainLuckTests gate unpaid: {error}")
    receipt.update(verdict="PASS", tests=count, summary=line)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Source: {args.sha}\n{line}")


if __name__ == "__main__":
    main()
