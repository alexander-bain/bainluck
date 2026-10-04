#!/usr/bin/env python3
"""Fail closed on Xcode's non-iOS dependency graph and Watch copy commands."""
import argparse
import json
import re
from pathlib import Path


def inspect(log: str, platform: str, exit_code: int) -> dict:
    if platform not in {"macOS", "visionOS"}:
        raise ValueError("Unsupported platform")
    if exit_code != 0:
        raise ValueError(f"xcodebuild did not succeed: {exit_code}")
    if "** BUILD FAILED **" in log:
        raise ValueError("Conflicting failed build marker")
    if not re.search(r"^\*\* BUILD SUCCEEDED \*\*\s*$", log, re.MULTILINE):
        raise ValueError("Missing final BUILD SUCCEEDED")
    graphs = list(re.finditer(r"Target dependency graph \((\d+) targets?\)", log))
    if len(graphs) != 1:
        raise ValueError("Expected exactly one target dependency graph")
    graph = graphs[0]
    tail = log[graph.end():]
    # Entries have no indentation assumptions: Xcode versions vary their formatting.
    entries = re.findall(r"^\s*Target '([^']+)' in project '([^']+)'", tail, re.MULTILINE)
    count = int(graph.group(1))
    if count <= 0 or len(entries) != count:
        raise ValueError("Dependency graph count does not match parsed target entries")
    if entries.count(("Bain Luck", "Bain Luck")) != 1:
        raise ValueError("Main Bain Luck target absent or duplicated")
    forbidden = [(name, project) for name, project in entries
                 if name in {"BainLuckWatch", "BainLuckWatch Watch App", "BainLuckComplication"}]
    if forbidden:
        raise ValueError(f"Watch targets scheduled: {forbidden}")
    # Scan commands as well as the graph: implicit product copies must not slip through.
    if re.search(r"(?:builtin-copy|\bCopy\b|\bCpResource\b|\bditto\b)[^\n]*(?:watchkitapp|BainLuckWatch|BainLuckComplication|/Watch(?:/|\s|$))", log, re.IGNORECASE):
        raise ValueError("Watch content copy scheduled")
    if re.search(r"^\s*(?:SwiftCompile|SwiftDriver|CompileSwift|Ld|CodeSign)[^\n]*(?:BainLuckWatch|BainLuckComplication)", log, re.MULTILINE):
        raise ValueError("Watch compilation or signing scheduled")
    return {"platform": platform, "target_count": count, "targets": [n for n, _ in entries],
            "verdict": "PASS", "scope": "non-iOS build plan excludes Watch targets and content; compilation and runtime unverified"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = {"sha": args.sha, "platform": args.platform, "verdict": "UNPAID"}
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
            raise ValueError("Expected full source SHA")
        receipt.update(inspect(args.log.read_text(), args.platform, args.exit_code))
    except (ValueError, OSError) as error:
        receipt["reason"] = str(error)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        raise SystemExit(str(error))
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
