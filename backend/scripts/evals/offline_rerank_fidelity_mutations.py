#!/usr/bin/env python3
"""Mutation gate for LAT-P050's instrument-fidelity work.

Same discipline as `search_scorer_wiring_mutations.py`, each rule from a named
prior failure:

* **The control runs FIRST and must be GREEN** (gotcha #122). A harness whose
  oracle is red on unmutated source scores a KILL for every mutant and cannot
  tell that from coverage.
* **Every mutation is proven APPLIED before it is scored** — a `NOT-APPLIED`
  verdict exists and is used, never skipped.
* **Restore from a byte-backup and assert the SHA**, never `git checkout --`,
  which in a shared tree can reach further than intended (gotcha #51).
* **Never pipe a gate** (gotcha #124): pytest's exit code is read from the
  subprocess directly.

New here: mutations span FOUR files (the route, the scorer's wire form, and both
eval scripts), because the thing under test is an AGREEMENT between an endpoint
and an offline harness. A single-file harness could not have expressed it — and
"the seam between two components" is exactly where this program's last three
defects lived.

Run: ``python3 scripts/evals/offline_rerank_fidelity_mutations.py``
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]

ROUTE = BACKEND / "app" / "routes" / "events.py"
SCORER = BACKEND / "app" / "utils" / "search_match_class.py"
RERANK = BACKEND / "scripts" / "evals" / "search_offline_rerank.py"
PRODUCER = BACKEND / "scripts" / "evals" / "search_results_producer.py"

TARGETS = (ROUTE, SCORER, RERANK, PRODUCER)
BACKUP_DIR = Path("/tmp/lat_p050_backups")

ORACLES = [
    "tests/test_offline_rerank_fidelity.py",
    "tests/integration/test_route_typeahead_evidence_echo.py",
    # The structural companion. Included because LAT-P050's cache-isolation
    # change turned this file red by STRENGTHENING the guard it asserts — the
    # test pinned a literal substring rather than the contract (gotcha #130).
    # It is amended and now belongs in the oracle set, not outside it.
    #
    # LAT-P054: it went red a SECOND time for the same reason — the read-guard
    # assertion was still pinned to a literal after LAT-P050 fixed only the
    # write-guard one. Both now read the nearest `if` and substring-match, so a
    # guard that gets STRONGER can no longer fail the test that keeps it strong.
    "tests/test_search_latency_contract.py",
    # LAT-P054/#1866: behavioural cover for the debug_timing guards (M13/M14).
    "tests/integration/test_route_typeahead_debug_timing.py",
]

#: (id, target, description, old, new). `old` must appear EXACTLY once.
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1", ROUTE,
        "THE WHOLE POINT: the echo is rebuilt from the suggestion, not taken "
        "from the Evidence that ranked — so the stripped aliases vanish",
        "        _by_payload = {id(_item): _ev for _ev, _item in _ta_candidates}\n"
        "        _evidence_echo = [\n"
        "            _ev_wire(_by_payload[id(_s)]) for _s in suggestions\n"
        "        ]\n",
        "        _evidence_echo = [\n"
        "            _ev_wire(_typeahead_evidence(_s)) for _s in suggestions\n"
        "        ]\n",
    ),
    (
        "M2", ROUTE,
        "a debug answer IS written to the cache — normal users get `_evidence`",
        "    if not _ta_degraded and not debug_evidence and not debug_timing:\n",
        "    if not _ta_degraded:\n",
    ),
    (
        "M3", ROUTE,
        "a debug request READS the cache, silently returning no echo",
        "    if not debug_evidence and not debug_timing:\n        try:\n"
        "            _rc = get_redis_client()\n",
        "    if True:\n        try:\n            _rc = get_redis_client()\n",
    ),
    # LAT-P054/#1866: `debug_timing` joined both guards, so both need their own
    # mutant. Dropping only the debug_timing conjunct leaves `debug_evidence`
    # intact, so M2/M3 above would still be killed by the echo oracles and the
    # new guard would be unprotected — a gap that looks like coverage.
    (
        "M13", ROUTE,
        "a debug-TIMING answer is written to the cache — normal users get "
        "per-stage server timings for the full TTL",
        "    if not _ta_degraded and not debug_evidence and not debug_timing:\n",
        "    if not _ta_degraded and not debug_evidence:\n",
    ),
    (
        "M14", ROUTE,
        "a debug-TIMING request READS the cache, so it is answered with a "
        "payload carrying no `debug_timing` key — silence read as a free request",
        "    if not debug_evidence and not debug_timing:\n        try:\n"
        "            _rc = get_redis_client()\n",
        "    if not debug_evidence:\n        try:\n            _rc = get_redis_client()\n",
    ),
    (
        "M4", ROUTE,
        "the echo leaks into the DEFAULT response (measured-surface change)",
        "    _evidence_echo: list[dict] | None = None\n    if debug_evidence:\n",
        "    _evidence_echo: list[dict] | None = None\n    if True:\n",
    ),
    (
        "M5", ROUTE,
        "the private-key strip is skipped when the echo is on",
        "    for _s in suggestions:\n        _s.pop(\"_derived\", None)\n",
        "    for _s in [] if debug_evidence else suggestions:\n        _s.pop(\"_derived\", None)\n",
    ),
    (
        "M6", SCORER,
        "the wire form drops aliases — the exact evidence teams rank MC0 on",
        '        "aliases": list(ev.aliases),\n',
        '        "aliases": [],\n',
    ),
    (
        "M7", SCORER,
        "the wire form drops the derived flag, so UNRANKABLE never crosses",
        '        derived=bool(payload.get("derived")),\n',
        "        derived=False,\n",
    ),
    (
        "M8", RERANK,
        "an unlabelled (v1) capture is optimistically called `exact`",
        '        fidelity = "legacy"\n',
        '        fidelity = "exact"\n',
    ),
    (
        "M9", RERANK,
        "the legacy path hand-rolls Evidence again instead of using the "
        "endpoint's `_typeahead_evidence`",
        "        from app.routes.events import _typeahead_evidence\n\n"
        "        return _typeahead_evidence(suggestion)\n",
        "        return Evidence(name=suggestion.get(\"text\") or \"\",\n"
        "                        kind=suggestion.get(\"type\") or \"market\")\n",
    ),
    (
        "M10", RERANK,
        "the echo is ignored and every candidate goes down the legacy path",
        "        ev = evidence_from_wire(echo) if isinstance(echo, dict) else _legacy_evidence(c)\n",
        "        ev = _legacy_evidence(c)\n",
    ),
    (
        "M11", RERANK,
        "`--require-fidelity` never refuses — the pipeline gate is defanged",
        '        if FIDELITIES.index(meta["rerank_fidelity"]) > wanted:\n',
        "        if False:\n",
    ),
    (
        "M12", PRODUCER,
        "a MISALIGNED echo is zipped in anyway and labelled faithful",
        "    if not isinstance(evidence, list) or len(evidence) != len(suggestions):\n",
        "    if not isinstance(evidence, list):\n",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_oracles() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *ORACLES, "-q", "--no-header", "-x"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(
            f"oracle exited {proc.returncode} — a usage error, not a result "
            f"(gotcha #121). Refusing to score.\n{proc.stdout[-2000:]}"
        )
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return proc.returncode == 0, (tail[-1] if tail else "<no output>")


def _main() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    original = {t: _sha(t) for t in TARGETS}
    backups = {}
    for t in TARGETS:
        b = BACKUP_DIR / t.name
        shutil.copy2(t, b)
        backups[t] = b

    print("=" * 78)
    print("CONTROL — oracles against UNMUTATED source")
    ok, summary = _run_oracles()
    print(f"  {summary}")
    if not ok:
        print("\nCONTROL IS RED. Every mutant below would score a KILL it did not")
        print("earn (gotcha #122). Aborting without running any mutation.")
        return 2
    print("  control: oracles PASS on unmutated source")
    print("=" * 78)

    killed, survived, not_applied = [], [], []
    for mid, target, desc, old, new in MUTATIONS:
        source = backups[target].read_text()
        count = source.count(old)
        if count != 1:
            not_applied.append((mid, f"anchor matched {count}x, expected 1"))
            print(f"{mid:>4}  NOT-APPLIED  ({count}x anchor)  {desc}")
            continue

        target.write_text(source.replace(old, new, 1))
        if _sha(target) == original[target]:
            not_applied.append((mid, "file unchanged after write"))
            print(f"{mid:>4}  NOT-APPLIED  (no byte change)  {desc}")
            shutil.copy2(backups[target], target)
            continue

        ok, summary = _run_oracles()
        shutil.copy2(backups[target], target)
        assert _sha(target) == original[target], "restore did not reproduce the original"

        if ok:
            survived.append((mid, desc))
            print(f"{mid:>4}  SURVIVED     {desc}\n        {summary}")
        else:
            killed.append((mid, desc))
            print(f"{mid:>4}  KILLED       {desc}")

    print("=" * 78)
    print(f"killed {len(killed)}/{len(MUTATIONS)} · survived {len(survived)} · "
          f"not-applied {len(not_applied)}")
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    for mid, why in not_applied:
        print(f"  NOT-APPLIED {mid}: {why}")
    for t in TARGETS:
        assert _sha(t) == original[t], f"{t.name} not restored"
    print("all four targets restored, SHAs match originals")
    return 0 if (not survived and not not_applied) else 1



def main() -> int:
    """Run the harness with an UNCONDITIONAL restore around it — #2107 sibling.

    `_main()` still restores after each mutant, exactly as before; this is the
    net under it. The incident it exists for is `bcdcd95f`, where a harness
    died at **exit 143** between writing a mutant and restoring it, and the
    mutant rode a commit. `try/finally` alone does not survive SIGTERM, so the
    guard installs the handler that gives `finally` something to run on — see
    `_mutation_guard.py` for the four failure cases and which one is not
    catchable.
    """
    with guarded_targets(TARGETS, BACKUP_DIR, 'lat_p050_offline_rerank_fidelity'):
        return _main()

if __name__ == "__main__":
    raise SystemExit(main())
