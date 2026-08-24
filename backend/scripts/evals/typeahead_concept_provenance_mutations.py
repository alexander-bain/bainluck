#!/usr/bin/env python3
"""Mutation gate for LAT-P051's #1846 fix — typeahead concept provenance.

The change is four lines: one blanket `_derived = True` becomes a per-row
predicate, and the predicate itself is split into a shape-free core plus two thin
wrappers. Small diffs are exactly where a mutation gate earns its keep, because a
four-line change invites a four-line review and a passing suite reads as proof.

Discipline, each from a named prior failure:

* **The control runs FIRST and must be GREEN** (gotcha #122). A harness whose
  oracle fails on unmutated source scores a KILL for every mutant.
* **Every mutation is proven APPLIED before it is scored** — a `NOT-APPLIED`
  verdict exists and is reported, never silently skipped.
* **Restore from a byte-backup and assert the SHA** (gotcha #51: never
  `git checkout --` in a shared tree).
* **Never pipe a gate** (gotcha #124) — the exit code comes from the subprocess.
* **Plan the mutations BEFORE trusting the tests** (gotcha #131). That is not
  decoration here: planning `M5` is what revealed that
  `TestGolfPrependProtectsTheTie` had been written against a hand-ordered list,
  so it asserted that a stable sort is stable and would have survived the append
  mutation untouched. The test was rewritten to go through
  `_upsert_query_derived_concept` before this file was finished.

Run: ``python3 scripts/evals/typeahead_concept_provenance_mutations.py``
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
TARGET = BACKEND / "app" / "routes" / "events.py"
BACKUP = Path("/tmp/lat_p051_events_backup.py")

#: The amended contract test is IN the oracle set deliberately — Alex ruling 3,
#: 2026-08-14, closing the loop gotcha #130 opened. A test that had to be amended
#: because an honest fix broke it is the test most worth keeping under mutation.
ORACLES = [
    "tests/test_search_scorer_wiring.py",
    "tests/test_typeahead_evidence_boundary.py",
    "tests/test_search_latency_contract.py",
    # Added AFTER the first run, because the first run is what proved the unit
    # tests could not see the route. M1 (blanket flag restored) and M2 (predicate
    # inverted) both SURVIVED a 148-test set: every assertion computed `_derived`
    # itself instead of asking the endpoint. This file is the instrument that was
    # missing, and it exists because the mutation plan ran first (gotcha #131).
    "tests/integration/test_route_typeahead_concept_provenance.py",
    # M7's oracle: the #1206 stopword gate. Dropping the stopword set lets
    # `winner`/`champion` carry a match, so every winner-field concept would name
    # every winner-field query — a silent return of the over-match family through
    # a door the provenance flag does not cover.
    "tests/test_search_concept_query_gate.py",
]

#: (id, description, old, new). `old` must appear EXACTLY once.
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "M1",
        "THE DEFECT ITSELF: the blanket flag comes back",
        '        _ta_concept["_derived"] = not _query_names_typeahead_concept(q, _ta_concept)\n',
        '        _ta_concept["_derived"] = True\n',
    ),
    (
        "M2",
        "the predicate is INVERTED — the Emmys over-match returns",
        '        _ta_concept["_derived"] = not _query_names_typeahead_concept(q, _ta_concept)\n',
        '        _ta_concept["_derived"] = _query_names_typeahead_concept(q, _ta_concept)\n',
    ),
    (
        "M3",
        "the shape adapter reads /search's field names off a typeahead row",
        '    return _query_names_concept_row(\n'
        '        q, key=row.get("event_key"), name=row.get("text")\n'
        '    )\n',
        '    return _query_names_concept_row(\n'
        '        q, key=row.get("key"), name=row.get("name")\n'
        '    )\n',
    ),
    (
        "M4",
        "the shared core answers True for any non-empty query",
        "    if not q:\n"
        "        return False\n"
        "    q_tokens = _concept_match_tokens(q)\n",
        "    if not q:\n"
        "        return False\n"
        "    return True\n"
        "    q_tokens = _concept_match_tokens(q)\n",
    ),
    (
        "M5",
        "the query-derived upsert APPENDS instead of prepending — the golf major "
        "loses the tie it now depends on the prepend to win",
        "    seen.add(key)\n    pool.insert(0, new_row)\n",
        "    seen.add(key)\n    pool.append(new_row)\n",
    ),
    (
        "M6",
        "typeahead evidence reports every candidate as rankable",
        "        derived=bool(item.get(\"_derived\")),\n",
        "        derived=False,\n",
    ),
    (
        "M7",
        "the stopword guard is dropped, so 'winner'/'champion' can carry a match "
        "and every winner-field concept names every winner-field query",
        "        if len(t) >= 3 and t not in _CONCEPT_MATCH_STOPWORDS\n",
        "        if len(t) >= 3\n",
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
    original_sha = _sha(TARGET)
    shutil.copy2(TARGET, BACKUP)

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
    for mid, desc, old, new in MUTATIONS:
        source = BACKUP.read_text()
        count = source.count(old)
        if count != 1:
            not_applied.append((mid, f"anchor matched {count}x, expected 1"))
            print(f"{mid:>4}  NOT-APPLIED  ({count}x anchor)  {desc}")
            continue

        TARGET.write_text(source.replace(old, new, 1))
        if _sha(TARGET) == original_sha:
            not_applied.append((mid, "file unchanged after write"))
            print(f"{mid:>4}  NOT-APPLIED  (no byte change)  {desc}")
            shutil.copy2(BACKUP, TARGET)
            continue

        ok, summary = _run_oracles()
        shutil.copy2(BACKUP, TARGET)
        assert _sha(TARGET) == original_sha, "restore did not reproduce the original"

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
    assert _sha(TARGET) == original_sha
    print(f"target restored, sha {original_sha[:16]} matches original")
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
    with guarded_targets((TARGET,), BACKUP, 'lat_p051_typeahead_concept_provenance'):
        return _main()

if __name__ == "__main__":
    raise SystemExit(main())
