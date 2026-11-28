#!/usr/bin/env python3
"""Run `fast-gate` housekeeping guard tests concurrently (~1 min wall time, 412: D)."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MANIFEST_PATH = REPO_ROOT / ".github" / "ci-fast-gate-housekeeping-tests.txt"
DURATIONS_PATH = BACKEND_DIR / "scripts" / "ci_shard_durations.json"
DEFAULT_WEIGHT = 2.0


def load_housekeeping_manifest(manifest_path: Path = MANIFEST_PATH) -> list[str]:
    """Load and validate non-empty test paths relative to ``backend/``."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Housekeeping manifest missing: {manifest_path}")
    paths: list[str] = []
    seen: set[str] = set()
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        entry = raw.split("#", 1)[0].strip()
        if not entry:
            continue
        if entry in seen:
            raise ValueError(f"Duplicate entry in housekeeping manifest: {entry}")
        target = BACKEND_DIR / entry
        if not target.is_file():
            raise FileNotFoundError(f"Housekeeping test file does not exist: {target}")
        seen.add(entry)
        paths.append(entry)
    if not paths:
        raise ValueError("Housekeeping manifest is empty")
    return paths


def _load_durations(durations_path: Path = DURATIONS_PATH) -> dict[str, float]:
    if not durations_path.exists():
        return {}
    try:
        raw = json.loads(durations_path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in (raw.get("files") or {}).items()}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def lpt_buckets(files: list[str], workers: int, weights: dict[str, float]) -> list[list[str]]:
    """Pack housekeeping files across ``workers`` parallel pytest invocations."""
    count = max(1, min(workers, len(files)))
    ordered = sorted(files, key=lambda f: (-weights.get(f, DEFAULT_WEIGHT), f))
    bins: list[list[str]] = [[] for _ in range(count)]
    loads = [0.0] * count
    for f in ordered:
        idx = loads.index(min(loads))
        bins[idx].append(f)
        loads[idx] += weights.get(f, DEFAULT_WEIGHT)
    return [sorted(b) for b in bins if b]


def _run_bucket(idx: int, bucket: list[str]) -> tuple[int, int, float, str]:
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *bucket, "-q"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - t0
    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return idx, proc.returncode, elapsed, combined.strip()


def main(argv: list[str] | None = None) -> int:
    default_workers = min(4, max(2, os.cpu_count() or 2))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=default_workers, help="parallel pytest processes")
    ap.add_argument("--list", action="store_true", help="print manifest entries and exit")
    args = ap.parse_args(argv)

    files = load_housekeeping_manifest()
    if args.list:
        for entry in files:
            print(entry)
        return 0

    weights = _load_durations()
    buckets = lpt_buckets(files, args.workers, weights)
    t0 = time.monotonic()
    print(f"fast-gate housekeeping: running {len(files)} guard files across {len(buckets)} workers")
    with ThreadPoolExecutor(max_workers=len(buckets)) as pool:
        results = list(pool.map(lambda pair: _run_bucket(*pair), enumerate(buckets, 1)))
    wall = time.monotonic() - t0

    failed = 0
    for idx, rc, elapsed, out in results:
        status = "PASS" if rc == 0 else f"FAIL({rc})"
        print(f"\n--- housekeeping worker {idx}/{len(buckets)} [{status}, {elapsed:.2f}s]: {', '.join(buckets[idx - 1])} ---")
        if rc != 0:
            failed += 1
            print(out)
        else:
            tail = out.splitlines()[-2:] if out else []
            for line in tail:
                print(line)

    print(f"\nfast-gate housekeeping summary: {len(files)} files, {len(buckets)} workers, wall={wall:.2f}s, failed_workers={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
