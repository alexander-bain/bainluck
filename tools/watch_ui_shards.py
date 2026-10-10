"""Exact-coverage receipts for five independently prepared hosted Watch pairs."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def manifest(root=ROOT):
    groups = json.loads((root / "tools/watch_ui_cases.json").read_text())
    if set(groups) != {"corner", "readings", "navigation", "controls", "widgets"}:
        raise ValueError(
            "Expected exactly corner, readings, navigation, controls and widgets shards"
        )
    declared = [case for cases in groups.values() for case in cases]
    source = [
        f"{path.stem}/{case}"
        for path in (root / "ios/Bain Luck/BainLuckWatchUITests").glob("*.swift")
        if not path.read_text().startswith("#if !DEBUG\n")
        for case in re.findall(r"func (test\w+)\(", path.read_text())
    ]
    if Counter(declared) != Counter(source) or any(
        count != 1 for count in Counter(declared).values()
    ):
        raise ValueError("Manifest must cover every source test exactly once")
    if any(not cases for cases in groups.values()):
        raise ValueError("Empty shards are not full coverage")
    if groups["corner"] != ["WidgetTapJourneyTests/testActualCornerSavedReadingAndTap"]:
        raise ValueError("Actual corner host requires its own fresh pair")
    return groups


def completed_cases(log, exit_code, expected):
    if (
        re.search(r"^\*\* TEST (?:EXECUTE )?FAILED \*\*\s*$", log, re.M)
        or exit_code != 0
        or not re.search(r"^\*\* TEST (?:EXECUTE )?SUCCEEDED \*\*\s*$", log, re.M)
    ):
        raise ValueError("Shard test process did not complete successfully")
    results = re.findall(
        r"^Test Case '-\[BainLuckWatchUITests\.(\w+) (test\w+)\]' (passed|failed|skipped) \([0-9.]+ seconds\)\.$",
        log,
        re.M,
    )
    observed = [f"{suite}/{case}" for suite, case, _ in results]
    if Counter(observed) != Counter(expected) or any(
        outcome != "passed" for _, _, outcome in results
    ):
        raise ValueError(
            "Shard has missing, duplicate, unexpected, failed or skipped cases"
        )
    totals = re.findall(
        r"^Test Suite '(?:All|Selected) tests' passed[^\n]*\n\s*Executed (\d+) tests?, with (\d+) failures?",
        log,
        re.M,
    )
    if len(totals) != 1 or tuple(map(int, totals[0])) != (len(expected), 0):
        raise ValueError("Shard terminal summary does not match exact case coverage")
    return observed


def shard_receipt(directory, shard, sha, exit_code, groups):
    signature = json.loads((directory / "simulator-widget-signing.json").read_text())
    if signature.get("verdict") != "PASS" or signature.get("sha") != sha:
        raise ValueError(
            "Shard installed simulator signing receipt is unpaid or wrong source"
        )
    if (directory / "source.txt").read_text().strip() != sha:
        raise ValueError("Shard source differs from expected source")
    products = json.loads((directory / "products-verification.json").read_text())
    if (
        products.get("sha") != sha
        or products.get("verdict") != "PASS"
        or not re.fullmatch(r"[0-9a-f]{64}", products.get("manifest_sha256", ""))
    ):
        raise ValueError("Immutable product verification is unpaid or wrong source")
    cases = completed_cases(
        (directory / "tests.log").read_text(), exit_code, groups[shard]
    )
    return {
        "sha": sha,
        "product_manifest_sha256": products["manifest_sha256"],
        "shard": shard,
        "verdict": "PASS",
        "tests": len(cases),
        "cases": cases,
        "watch_udid": (directory / "destination.txt").read_text().strip(),
        "phone_udid": (directory / "phone-destination.txt").read_text().strip(),
    }


def aggregate(directory, sha, groups, verify_markers=True):
    receipts = []
    logs = []
    for shard, expected in groups.items():
        part = directory / shard
        saved = json.loads((part / "receipt.json").read_text())
        if (
            saved.get("shard") != shard
            or saved.get("sha") != sha
            or saved.get("verdict") != "PASS"
        ):
            raise ValueError("Missing, failed or wrong-source shard receipt")
        checked = shard_receipt(
            part, shard, sha, int((part / "test-exit.txt").read_text()), groups
        )
        if checked != saved or Counter(saved["cases"]) != Counter(expected):
            raise ValueError("Shard receipt does not match its retained evidence")
        receipts.append(checked)
        logs.append((part / "tests.log").read_text())
    if len({r["product_manifest_sha256"] for r in receipts}) != 1:
        raise ValueError("Shards used different immutable product packages")
    if len(
        {udid for r in receipts for udid in (r["watch_udid"], r["phone_udid"])}
    ) != 2 * len(groups) or any(
        not r["watch_udid"] or not r["phone_udid"] for r in receipts
    ):
        raise ValueError("All journeys must use distinct fresh pairs")
    if verify_markers:
        combined = directory / "combined-tests.log"
        combined.write_text("\n".join(logs))
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        for gate in ("PYVERIFY", "PYALIAS", "PYCORNER"):
            code = harness.split(f"<<'{gate}'\n", 1)[1].split(f"\n{gate}", 1)[0]
            subprocess.run([sys.executable, "-c", code, str(combined)], check=True)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/watch_diagnostics_receipt.py"),
                "--log",
                str(combined),
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/watch_discovery_polish_receipt.py"),
                str(combined),
            ],
            check=True,
        )
    return {
        "sha": sha,
        "verdict": "PASS",
        "tests": sum(r["tests"] for r in receipts),
        "shards": receipts,
        "scope": "All manifest Debug Watch UI cases on five independently prepared hosted pairs",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["select", "receipt", "aggregate"])
    parser.add_argument(
        "--shard", choices=["corner", "readings", "navigation", "controls", "widgets"]
    )
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--sha")
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args()
    groups = manifest()
    if args.mode == "select":
        print(
            "\n".join(
                f"-only-testing:BainLuckWatchUITests/{case}"
                for case in groups[args.shard]
            )
        )
        return
    output = args.directory / (
        "receipt.json" if args.mode == "receipt" else "aggregate-receipt.json"
    )
    result = {"sha": args.sha, "verdict": "UNPAID"}
    try:
        result = (
            shard_receipt(args.directory, args.shard, args.sha, args.exit_code, groups)
            if args.mode == "receipt"
            else aggregate(args.directory, args.sha, groups)
        )
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        result["reason"] = str(error)
        output.write_text(json.dumps(result, indent=2) + "\n")
        raise SystemExit(str(error))
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
