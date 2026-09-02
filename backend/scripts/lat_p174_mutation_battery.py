#!/usr/bin/env python3
"""Mutation battery for LAT-P174 — prove each guard is load-bearing.

Each mutation is applied to a REAL source file, proved to have applied by
re-reading the file and asserting the replacement is present (a battery that
silently no-ops reports SURVIVED for a guard that was never attacked), the
pinned tests are run, and the file is restored byte-identically.

Run from `backend/`:  python3 scripts/lat_p174_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TESTS = (
    "tests/test_futures_market_snapshot_lat_p174.py",
    "tests/test_feed_market_load_shared_lat_p174.py",
)

# (label, file, old, new, the test that MUST go red)
MUTATIONS = [
    (
        "column-dropped-from-snapshot",
        "app/utils/futures_market_snapshot.py",
        '    "volume_24h",\n',
        "",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        "to_plain-uses-getattr",
        "app/utils/futures_market_snapshot.py",
        "    state = instance.__dict__\n    return [state.get(name) for name in columns]",
        "    return [getattr(instance, name, None) for name in columns]",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        "schema-version-not-checked",
        "app/utils/futures_market_snapshot.py",
        '    if not isinstance(payload, dict) or payload.get("v") != SNAPSHOT_SCHEMA_VERSION:\n        return None',
        "    if not isinstance(payload, dict):\n        return None",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        "market_load-not-on-the-header-allowlist",
        "app/utils/principal_independent_cache.py",
        '{"concepts", "canonical_counts", "market_load"}',
        '{"concepts", "canonical_counts"}',
        "tests/test_feed_market_load_shared_lat_p174.py",
    ),
    (
        "namespace-cap-ignored",
        "app/utils/principal_independent_cache.py",
        'MAX_ENTRIES_BY_NAMESPACE: dict[str, int] = {"market_load": 6}',
        "MAX_ENTRIES_BY_NAMESPACE: dict[str, int] = {}",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        "hydration-not-shared",
        "app/routes/feed.py",
        '_snapshot_payload = await _pic.get_or_build(\n            "market_load", _snapshot_key, _build_market_rows\n        )',
        "_snapshot_payload = await _build_market_rows()",
        "tests/test_feed_market_load_shared_lat_p174.py",
    ),
    # ----------------------------------------------------------------------
    # CERT-615 repairs. Each of these five was GREEN under the battery above —
    # that is the whole finding, so each now has its own attacker.
    # ----------------------------------------------------------------------
    (
        # [P1] The certifier's own mutation, verbatim. Against the blocked tree
        # this left all 17 tests green while `/api/feed` served `items: []`.
        # Pointed at the SHIP file so it proves the runtime half specifically;
        # the drift gate kills it independently.
        "cert615-p1-alias-read-of-an-absent-column",
        "app/routes/feed.py",
        "    for market in markets:\n        try:\n            is_recycled = False",
        "    for market in markets:\n        try:\n            market_alias = market\n"
        "            _ = market_alias.event_id\n            is_recycled = False",
        "tests/test_feed_market_load_shared_lat_p174.py",
    ),
    (
        # [P1] `llm_gender` is read only through `getattr`, so the regex scan
        # could not see it. This is the certifier's second independent probe.
        "cert615-p1-getattr-only-column-dropped",
        "app/utils/futures_market_snapshot.py",
        '    "llm_gender",\n',
        "",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        # [P1] Neuter the analyser's alias tracking — the construct the regex
        # was blind to. The guard must not be able to lose this and stay green.
        "cert615-p1-drift-gate-stops-following-aliases",
        "tests/test_futures_market_snapshot_lat_p174.py",
        "    aliases = {seed}\n    for _ in range(_MAX_ESCAPE_DEPTH):",
        "    aliases = {seed}\n    for _ in range(0):",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        # [P1] Neuter the literal-`getattr` arm the same way.
        "cert615-p1-drift-gate-stops-reading-literal-getattr",
        "tests/test_futures_market_snapshot_lat_p174.py",
        "            return {node.args[1].value}",
        "            return set()",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
    (
        # [P2] Accept the envelope without validating row arity — the exact
        # state the blocked tree shipped, where a same-version malformed
        # payload was declared readable and then decoded to nothing.
        "cert615-p2-row-arity-not-validated",
        "app/utils/futures_market_snapshot.py",
        "    return isinstance(values, (list, tuple)) and len(values) == width",
        "    return isinstance(values, (list, tuple))",
        "tests/test_futures_market_snapshot_lat_p174.py",
    ),
]


def _run(test: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).returncode


def _purge_pycache() -> None:
    """Stale bytecode makes a battery report phantom results either way."""
    for cache in REPO.rglob("__pycache__"):
        for item in cache.iterdir():
            item.unlink()
        cache.rmdir()


def main() -> int:
    print("baseline:", end=" ", flush=True)
    _purge_pycache()
    for test in TESTS:
        code = _run(test)
        if code != 0:
            print(f"\nBASELINE RED on {test} (exit {code}) — battery aborted")
            return 2
    print("both suites green")

    killed, survived = [], []
    for label, rel, old, new, test in MUTATIONS:
        path = REPO / rel
        original = path.read_text()
        before = hashlib.sha256(original.encode()).hexdigest()
        if original.count(old) != 1:
            print(f"  {label}: ANCHOR NOT UNIQUE ({original.count(old)} matches) — abort")
            return 3
        path.write_text(original.replace(old, new, 1))
        applied = path.read_text()
        assert new in applied or new == "", f"{label}: replacement text absent"
        assert old not in applied, f"{label}: mutation did not apply"
        _purge_pycache()
        code = _run(test)
        path.write_text(original)
        assert (
            hashlib.sha256(path.read_text().encode()).hexdigest() == before
        ), f"{label}: restore was not byte-identical"
        _purge_pycache()
        (killed if code != 0 else survived).append(label)
        print(f"  {label}: {'KILLED' if code != 0 else 'SURVIVED'} (exit {code}) via {test}")

    print(f"\n{len(killed)}/{len(MUTATIONS)} killed, {len(survived)} survived")
    if survived:
        print("SURVIVED:", ", ".join(survived))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
