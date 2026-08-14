#!/usr/bin/env python3
"""Mutation gate for LAT-P049's `/search` scorer wiring.

Discipline this harness is built to satisfy, each from a named prior failure:

* **The control runs FIRST and must be GREEN** (gotcha #122). A mutation harness
  whose oracle fails on unmutated source scores a KILL for every mutant and
  cannot tell that from coverage.
* **Every mutation must be proven APPLIED before it is scored.** An edit that
  silently fails to match reports a survivor as a kill of nothing — so a
  `NOT-APPLIED` verdict exists and is used, never skipped.
* **Restore from a byte-backup and assert the SHA**, never `git checkout --`
  (which in a shared tree can reach further than intended).
* **Never pipe a gate** (gotcha #124): pytest's own exit code is captured
  directly from the subprocess, not inferred from a downstream command.

Run: ``python3 scripts/evals/search_scorer_wiring_mutations.py``
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGET = BACKEND / "app" / "routes" / "events.py"
BACKUP = Path("/tmp/lat_p049_events_backup.py")

ORACLES = [
    "tests/test_search_scorer_wiring.py",
    "tests/integration/test_route_search_private_evidence.py",
]

#: (id, description, old, new). `old` must appear EXACTLY once.
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "M1",
        "the upgrade stops clearing _derived — the concept stays UNRANKABLE",
        '        existing["_derived"] = False\n',
        '        existing["_derived"] = True\n',
    ),
    (
        "M2",
        "the upgraded twin is no longer moved to the front",
        "        pool.insert(0, pool.pop(idx))\n",
        "        pass  # MUTANT: no move-to-front\n",
    ),
    (
        "M3",
        "THE ORIGINAL BUG, imported: /search flags provenance blanket-true",
        '        _c["_derived"] = not _query_names_concept(q, _c)\n',
        '        _c["_derived"] = True\n',
    ),
    (
        "M4",
        "the awards call site reverts to a first-writer-wins skip (AC#1)",
        "    if _awards_concept:\n"
        "        event_concepts = _upsert_search_query_derived_concept(\n"
        "            event_concepts, _seen_concept_keys, _awards_concept,\n"
        "        )\n",
        "    if _awards_concept and _awards_concept[\"key\"] not in _seen_concept_keys:\n"
        "        _seen_concept_keys.add(_awards_concept[\"key\"])\n"
        "        event_concepts.insert(0, _awards_concept)\n"
        "        event_concepts = event_concepts[:5]\n",
    ),
    (
        "M5",
        "the private _aliases key is no longer stripped from /search teams",
        '    for _t in matched_teams:\n        _t.pop("_aliases", None)\n',
        "    for _t in matched_teams:\n        pass  # MUTANT: no strip\n",
    ),
    (
        "M6",
        "alternate_names is dropped from the /search team SELECT",
        "               Team.alternate_names, team_rank)\n",
        "               team_rank)\n",
    ),
    (
        "M7",
        "the teams bucket is no longer ranked — raw FTS order ships",
        "    matched_teams = _search_rank_candidates(\n"
        "        q, [(_search_team_evidence(t), t) for t in matched_teams]\n"
        "    )[:5]\n",
        "    matched_teams = matched_teams[:5]\n",
    ),
    (
        "M8",
        "the concepts bucket is no longer ranked",
        "    event_concepts = _search_rank_candidates(\n"
        "        q, [(_search_concept_evidence(c), c) for c in event_concepts]\n"
        "    )[:5]\n",
        "    event_concepts = event_concepts[:5]\n",
    ),
    (
        "M9",
        "team evidence withholds the alias set from the scorer",
        '    aliases: tuple[str, ...] = tuple(row.get("_aliases") or ())\n'
        '    if row.get("abbreviation"):\n'
        '        aliases = (*aliases, row["abbreviation"])\n',
        "    aliases: tuple[str, ...] = ()\n",
    ),
    (
        "M10",
        "concept evidence reports every row as rankable",
        '        derived=bool(row.get("_derived")),\n',
        "        derived=False,\n",
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


def main() -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
