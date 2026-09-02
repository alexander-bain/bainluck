#!/usr/bin/env python3
"""Mutation gate for LAT-P052's OUTCOME-EVIDENCE probe class (ruling 056, #1861).

WHAT IS UNDER TEST HERE IS AN INSTRUMENT, NOT A FEATURE
-------------------------------------------------------
`-44` shipped a real ranking change and moved zero probes. Ruling 056 says a null
read indicts the instrument until the probe set is shown to discriminate. This
queue's answer is a new probe class plus a demonstration that it discriminates —
so the thing that must not silently rot is **the measuring apparatus**, and the
apparatus has three separable seams:

* the **registry artifact** (`search_gold_probes.json`) — where a one-word edit
  can move a probe into the ledger cohort and invalidate every published number;
* the **scorer** (`search_match_class.py`) — where MC4 itself lives;
* the **route** (`_search_owned_outcome_names`) — where #1843's unbounded walk
  lives, and where the re-cap regression would actually happen.

Three targets, because a mutation confined to one seam proves nothing about the
other two.

WHAT PLANNING THE MUTATIONS FOUND, BEFORE ANY OF THEM RAN (gotcha #131)
------------------------------------------------------------------------
Writing `M7` — "re-cap the owned-outcome walk at 3, i.e. restore the #1843
defect" — exposed that
`tests/test_search_outcome_evidence_discrimination.py` **could not kill it**. That
file builds `Evidence` directly, so it never traverses
`_search_owned_outcome_names` at all, and its own docstring claimed otherwise.
The claim was corrected and `tests/test_typeahead_evidence_boundary.py` — which
owns that call site — was added to the oracle set. Neither file covers the other,
and before this gate nothing said so.

`M2` found the second gap: nothing asserted `metadata.migrated`, so folding the
five new probes into the gold-draft count (46 -> 51) would have overstated
coverage of Alex's query set with every test green. An assertion was added.

Discipline, each from a named prior failure:

* **The control runs FIRST and must be GREEN** (gotcha #122). A harness whose
  oracle fails on unmutated source scores a KILL for every mutant.
* **Every mutation is proven APPLIED before it is scored** — `NOT-APPLIED` is a
  reported verdict, never a silent skip.
* **Restore from a byte-backup and assert the SHA** (gotcha #51: never
  `git checkout --` in a shared tree).
* **Never pipe a gate** (gotcha #124) — the exit code comes from the subprocess.

Run: ``python3 scripts/evals/outcome_evidence_class_mutations.py``
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]

REGISTRY = BACKEND / "scripts" / "evals" / "search_gold_probes.json"
SCORER = BACKEND / "app" / "utils" / "search_match_class.py"
ROUTE = BACKEND / "app" / "routes" / "events.py"

#: Targets whose anchors legitimately match MORE THAN ONCE.
#:
#: The registry is a GENERATED artifact: `"split": "canary"` and
#: `"difficulty": "discrimination"` appear once per probe by construction, and
#: the realistic edit this harness reproduces — a hand patch, a bad merge —
#: changes ONE of them. So a repeated anchor here is the mutant working, not a
#: mutant that cannot run, and `_apply` below mutates exactly one occurrence.
#:
#: #2391: `scan_mutation_residue.py` graded M1/M3/M4 as ambiguous debt because
#: it assumed every harness in this directory refuses a non-unique anchor. This
#: one documents the opposite and always has. Published as a constant so the
#: scan reads the same exemption `_apply` enforces, instead of asserting a
#: contract this harness does not have.
ANCHOR_MAY_REPEAT_IN: frozenset[Path] = frozenset({REGISTRY})

BACKUPS = {
    REGISTRY: Path("/tmp/lat_p052_registry_backup.json"),
    SCORER: Path("/tmp/lat_p052_scorer_backup.py"),
    ROUTE: Path("/tmp/lat_p052_events_backup.py"),
}

ORACLES = [
    "tests/test_search_outcome_evidence_discrimination.py",
    # M7's oracle, and the reason this line exists is in the module docstring:
    # the discrimination file cannot see the route seam.
    "tests/test_typeahead_evidence_boundary.py",
    # The class must not perturb the scorer's ratified properties.
    "tests/test_search_match_class_properties.py",
]

#: (id, target, description, old, new). `old` must appear EXACTLY once.
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1",
        REGISTRY,
        "THE LEDGER BREAKER: an outcome-evidence probe moves into the `test` "
        "split, silently growing the cohort every §5 number is written against",
        '"split": "canary"',
        '"split": "test"',
    ),
    (
        "M2",
        REGISTRY,
        "the gold-draft count absorbs the new class (46 -> 51), overstating "
        "coverage of Alex's query set",
        '"migrated": 46',
        '"migrated": 51',
    ),
    (
        "M3",
        REGISTRY,
        "the discrimination probes are relabelled as ordinary coverage, so the "
        "two halves stop being distinguishable (P10)",
        '"gold_family": "outcome_evidence"',
        '"gold_family": "events"',
    ),
    (
        "M4",
        REGISTRY,
        "the class stops declaring itself a discrimination set",
        '"difficulty": "discrimination"',
        '"difficulty": "baseline"',
    ),
    (
        "M5",
        SCORER,
        "MC4's conjunction becomes a disjunction — ANY query token in the "
        "outcome set is enough, so a market ranks on half a query",
        "        if outcome_tokens and all(t in outcome_tokens for t in q_tokens):\n",
        "        if outcome_tokens and any(t in outcome_tokens for t in q_tokens):\n",
    ),
    (
        "M6",
        SCORER,
        "MC4 is deleted outright — owned-outcome evidence stops being a tier and "
        "every owner falls to the MC5 floor",
        "        if outcome_tokens and all(t in outcome_tokens for t in q_tokens):\n"
        "            return MC4_OUTCOME_ONLY\n",
        "        if False:\n"
        "            return MC4_OUTCOME_ONLY\n",
    ),
    (
        "M7",
        ROUTE,
        "THE #1843 DEFECT RESTORED: the owned-outcome walk is re-capped at the "
        "display cut, so the scorer again sees only what the dropdown shows",
        "    return tuple(\n"
        "        o.name for o in market.outcomes\n"
        "        if o.name and not _is_placeholder_outcome_name(o.name)\n"
        "    )\n",
        "    return tuple(\n"
        "        o.name for o in market.outcomes\n"
        "        if o.name and not _is_placeholder_outcome_name(o.name)\n"
        "    )[:3]\n",
    ),
    (
        "M8",
        SCORER,
        "MC4 consults only the first three owned outcomes — the same defect as "
        "M7 but at the SCORER seam, which a route-level test cannot see",
        "        for o in ev.outcomes:\n            outcome_tokens.update(tokens(o))\n",
        "        for o in ev.outcomes[:3]:\n            outcome_tokens.update(tokens(o))\n",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_oracles() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *ORACLES, "-q", "--no-header"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(
            f"oracle exited {proc.returncode} — a usage error, not a result "
            f"(gotcha #121). Refusing to score.\n{proc.stdout[-3000:]}"
        )
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return proc.returncode == 0, (tail[-1] if tail else "<no output>")


def _main() -> int:
    original = {path: _sha(path) for path in BACKUPS}
    for path, backup in BACKUPS.items():
        shutil.copy2(path, backup)

    print("=" * 78)
    print("CONTROL — oracles against UNMUTATED source")
    ok, summary = _run_oracles()
    print(f"  {summary}")
    if not ok:
        print("\nCONTROL IS RED. Every mutant below would score a KILL it did not")
        print("earn (gotcha #122). Aborting without running any mutation.")
        for path, backup in BACKUPS.items():
            shutil.copy2(backup, path)
        return 2
    print("  control: oracles PASS on unmutated source")
    print("=" * 78)

    killed, survived, not_applied = [], [], []
    for mid, target, desc, old, new in MUTATIONS:
        backup = BACKUPS[target]
        source = backup.read_text()
        count = source.count(old)
        if count < 1:
            not_applied.append((mid, f"anchor matched {count}x, expected >=1"))
            print(f"{mid:>4}  NOT-APPLIED  ({count}x anchor)  {desc}")
            continue

        # The registry is a generated artifact: an anchor legitimately repeats
        # once per probe, and mutating ONE of them is the realistic edit (a hand
        # patch, a bad merge). Source anchors must be unique. The exemption is
        # read from `ANCHOR_MAY_REPEAT_IN` rather than re-spelled here so this
        # check and the scan's cannot drift apart (#2391).
        may_repeat = target in ANCHOR_MAY_REPEAT_IN
        replacements = 1 if may_repeat else count
        if not may_repeat and count != 1:
            not_applied.append((mid, f"source anchor matched {count}x, expected 1"))
            print(f"{mid:>4}  NOT-APPLIED  ({count}x anchor)  {desc}")
            continue

        target.write_text(source.replace(old, new, replacements))
        if _sha(target) == original[target]:
            not_applied.append((mid, "file unchanged after write"))
            print(f"{mid:>4}  NOT-APPLIED  (no byte change)  {desc}")
            shutil.copy2(backup, target)
            continue

        ok, summary = _run_oracles()
        shutil.copy2(backup, target)
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
    for path, sha in original.items():
        assert _sha(path) == sha, f"{path.name} not restored"
        print(f"  restored {path.name} sha {sha[:16]}")
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
    with guarded_targets(tuple(BACKUPS), BACKUPS, 'lat_p052_outcome_evidence_class'):
        return _main()

if __name__ == "__main__":
    raise SystemExit(main())
