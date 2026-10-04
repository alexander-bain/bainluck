#!/usr/bin/env python3
"""Deliver real warm URLs only to this hosted gate's disposable Watch simulator."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

MARKER = re.compile(r"^WATCH_UI_WARM_READY=([12]):([A-Fa-f0-9-]{36})$")


def readiness(line):
    match = MARKER.fullmatch(line.strip())
    if not match:
        return None
    try:
        nonce = str(uuid.UUID(match[2]))
    except ValueError:
        return None
    return int(match[1]), nonce


def verify(receipt, sha, udid):
    deliveries = receipt.get("deliveries", [])
    return (receipt.get("sha") == sha and receipt.get("udid") == udid
            and receipt.get("verdict") == "PASS" and len(deliveries) == 2
            and [item.get("step") for item in deliveries] == [1, 2]
            and all(item.get("exit_code") == 0 for item in deliveries)
            and bool(deliveries[0].get("nonce"))
            and deliveries[0]["nonce"] == deliveries[1].get("nonce"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--udid", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        if not verify(json.loads(args.receipt.read_text()), args.sha, args.udid):
            raise SystemExit("Warm delivery remains unpaid")
        return
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("Warm URL delivery requires a disposable hosted runner")
    uuid.UUID(args.udid)  # Never accept 'booted' or a global simulator selector.
    receipt = {"sha": args.sha, "udid": args.udid, "verdict": "UNPAID", "deliveries": []}
    def save():
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    save()
    offset = 0
    pending = ""
    expected_step = 1
    nonce = None
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        if args.log.exists():
            with args.log.open() as stream:
                stream.seek(offset)
                pending += stream.read(1024 * 1024)
                offset = stream.tell()
            lines = pending.split("\n")
            pending = lines.pop()
            for line in lines:
                marker = readiness(line)
                if marker is None:
                    continue
                step, token = marker
                if step < expected_step and token == nonce:
                    continue  # Duplicate console transport must not cause another open.
                if step != expected_step or (nonce is not None and token != nonce):
                    receipt["reason"] = "Out-of-order or mismatched readiness handshake"
                    save()
                    raise SystemExit(1)
                nonce = token
                try:
                    result = subprocess.run(["xcrun", "simctl", "openurl", args.udid,
                                             "bainluck-watch://selected-game"],
                                            capture_output=True, text=True, timeout=15)
                    code = result.returncode
                    diagnostic = result.stderr[-2000:]
                except subprocess.TimeoutExpired:
                    code, diagnostic = 124, "simctl openurl timed out"
                receipt["deliveries"].append({"step": step, "nonce": nonce,
                                               "exit_code": code, "diagnostic": diagnostic})
                if code:
                    save()
                    raise SystemExit(code)
                expected_step += 1
                if expected_step == 3:
                    receipt["verdict"] = "PASS"
                    save()
                    return
                save()
        time.sleep(0.5)
    receipt["reason"] = "Readiness timed out; XCTest console may be buffered"
    save()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
