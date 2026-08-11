"""LAT-P035 — mutation harness for the futures word test and its stability gate.

A green suite proves the code works on the paths the suite walks. It does not prove
the suite would NOTICE the code being undone, and that second property is the only
reason a regression guard exists. So each mutant below deliberately breaks one
property this queue shipped, and the harness demands the oracle FAIL.

TWO DIRECTIONS, on purpose
--------------------------
Half the mutants REMOVE the fix (drop the word test, drop the lexeme-less guard,
un-allowlist ``numnode``). The other half OVER-APPLY it — AND the guard instead of
OR-ing it, put the word test on the outcome arm, count a bucket reorder as a flap.
A guard that only catches deletion lets the next cycle "improve" the rule into the
LAT-P002 revert, which is exactly how the futures bucket emptied the last time.

WHY IT MUTATES ON DISK, AND WHAT THAT OBLIGES
---------------------------------------------
The oracles are pytest modules that import ``app.routes.events`` and read it with
``inspect.getsource``; an in-memory exec'd copy would not be the module they see.
So the mutation is written to the real file and restored from a ``cp`` backup.

That makes one failure mode load-bearing: **a mutation that does not APPLY reports
green**, because the oracle passes against unmutated source and a naive harness
scores that as a kill. Every mutant therefore asserts its needle was present, that
the file actually changed, and — after restore — that the file is byte-identical to
the backup. A mutant that fails to apply is a HARNESS failure and exits non-zero; it
is never silently counted as a kill.

Usage::

    python scripts/evals/search_word_test_mutations.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
EVENTS = BACKEND / "app/routes/events.py"
GUARD = BACKEND / "app/utils/sql_read_guard.py"
PRODUCER = BACKEND / "scripts/evals/search_bucket_producer.py"
REGISTRY_GEN = BACKEND / "scripts/evals/build_search_gold_registry.py"

SHAPE_ORACLE = "tests/test_search_latency_contract.py"
STABILITY_ORACLE = "tests/evals/test_search_bucket_stability.py"
REGISTRY_ORACLE = "tests/evals/test_search_gold_registry.py"

# (id, file, needle, replacement, oracle, why)
MUTANTS: list[tuple[str, Path, str, str, str, str]] = [
    # ---- direction 1: undo the fix -------------------------------------
    (
        "futures-drop-word-test",
        EVENTS,
        """    return and_(
        _build_expanded_ilike(FuturesMarket.name, term, exp),
        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),
    )""",
        """    return _build_expanded_ilike(FuturesMarket.name, term, exp)""",
        SHAPE_ORACLE,
        "Reverts the futures name arm to substring-only: `nba champion` returns "
        "nine ITF tennis set markets again (#1758).",
    ),
    (
        "futures-or-instead-of-and",
        EVENTS,
        """    return and_(
        _build_expanded_ilike(FuturesMarket.name, term, exp),
        or_(
            _term_has_no_lexemes(term),""",
        """    return or_(
        _build_expanded_ilike(FuturesMarket.name, term, exp),
        or_(
            _term_has_no_lexemes(term),""",
        SHAPE_ORACLE,
        "OR-s the unindexable FTS arm at the top level — 1c's seq scan, the 20s median.",
    ),
    (
        "futures-drop-guard",
        EVENTS,
        """        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),""",
        """        _build_expanded_fts(FuturesMarket.name, term, exp),""",
        SHAPE_ORACLE,
        "Removes the lexeme-less guard from futures: a stopword term zeroes the "
        "conjunction and gold probe `taylor swift pregnant by...?` is lost.",
    ),
    (
        "events-drop-guard",
        EVENTS,
        """        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(Event.home_team_name, term, expansion),""",
        """        or_(
            _build_expanded_fts(Event.home_team_name, term, expansion),""",
        SHAPE_ORACLE,
        "Removes the guard from events: `dodgers and cubs` returns zero events "
        "(measured live on v3775 before the fix).",
    ),
    (
        "single-term-path-unguarded",
        EVENTS,
        "        futures_name_ilike = _futures_name_match_term(term, exp)",
        "        futures_name_ilike = _build_expanded_ilike(FuturesMarket.name, term, exp)",
        SHAPE_ORACLE,
        "Word-tests only the multi-term path. `nba champion` looks fixed while every "
        "single-term query keeps its substring collisions.",
    ),
    (
        "multi-term-path-unguarded",
        EVENTS,
        """            _futures_name_match_term(term, exp)
            for term, exp in expanded""",
        """            _build_expanded_ilike(FuturesMarket.name, term, exp)
            for term, exp in expanded""",
        SHAPE_ORACLE,
        "The inverse: single-term guarded, multi-term not — the motivating query "
        "itself stays broken.",
    ),
    (
        "unallowlist-numnode",
        GUARD,
        '"numnode", "phraseto_tsquery"',
        '"phraseto_tsquery"',
        SHAPE_ORACLE,
        "Blinds the plan rail to the search path's own SQL: EXPLAIN ANALYZE of the "
        "shipped predicate is refused by name.",
    ),
    (
        "registry-drop-adjudication",
        REGISTRY_GEN,
        '     ["team:boston-red-sox"], "pass",',
        '     [], "pass",',
        REGISTRY_ORACLE,
        "Removes the Red Sox alternative: the headline recall number goes back to "
        "being decided by which duplicate row sorts first.",
    ),
    (
        "flap-reported-as-stable",
        PRODUCER,
        '"STABLE" if len(unique) == 1',
        '"STABLE" if len(unique) >= 1',
        STABILITY_ORACLE,
        "Calls a flapping probe stable — the exact failure this mode exists to catch.",
    ),
    (
        "unverified-reported-as-stable",
        PRODUCER,
        '"UNVERIFIED" if len(good) < 2',
        '"UNVERIFIED" if len(good) < 0',
        STABILITY_ORACLE,
        "Absence of evidence read as evidence of stability (gotcha #53): one good "
        "run and one failure score the same as two agreeing runs.",
    ),
    # ---- direction 2: over-apply it ------------------------------------
    (
        "guard-anded-not-ored",
        EVENTS,
        """        or_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),""",
        """        and_(
            _term_has_no_lexemes(term),
            _build_expanded_fts(FuturesMarket.name, term, exp),
        ),""",
        SHAPE_ORACLE,
        "Inverts the guard into a REQUIREMENT that the term be a stopword — every "
        "real query matches nothing.",
    ),
    (
        "outcome-arm-word-tested",
        EVENTS,
        """        return FuturesMarket.id.in_(
            select(FuturesOutcome.market_id).where(
                _build_expanded_ilike(FuturesOutcome.name, term, exp)
            )
        )""",
        """        return FuturesMarket.id.in_(
            select(FuturesOutcome.market_id).where(
                and_(
                    _build_expanded_ilike(FuturesOutcome.name, term, exp),
                    _build_expanded_fts(FuturesOutcome.name, term, exp),
                )
            )
        )""",
        SHAPE_ORACLE,
        "Extends the rule to the outcome arm — a ~95% candidate cut (measured on "
        "`fed`: 1,027 markets -> 47) smuggled in on this queue's evidence.",
    ),
    (
        "reorder-counted-as-flap",
        PRODUCER,
        """    by_bucket: dict[str, set[str]] = {}
    for row in candidates:
        by_bucket.setdefault(str(row.get("bucket")), set()).add(str(row.get("entity_id")))
    return [[bucket, *sorted(ids)] for bucket, ids in sorted(by_bucket.items())]""",
        """    return [[str(row.get("bucket")), str(row.get("entity_id"))] for row in candidates]""",
        STABILITY_ORACLE,
        "Makes within-bucket reordering count as instability: the mode cries wolf "
        "every run and gets switched off.",
    ),
]


def _run_oracle(oracle: str) -> bool:
    """True when the oracle PASSES (i.e. the mutant survived)."""

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", oracle, "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    return proc.returncode == 0


def main() -> int:
    files = {EVENTS, GUARD, PRODUCER, REGISTRY_GEN}
    backups: dict[Path, Path] = {}
    tmp = Path(tempfile.mkdtemp(prefix="lat-p035-mutations-"))
    for path in files:
        backup = tmp / path.name
        shutil.copy2(path, backup)
        backups[path] = backup

    killed, survived, unapplied = [], [], []
    try:
        for mutant_id, path, needle, replacement, oracle, why in MUTANTS:
            original = path.read_text(encoding="utf-8")
            if needle not in original:
                # A drifted needle is a HARNESS failure. Reporting it as a kill is
                # the specific lie this harness is built to make impossible.
                unapplied.append((mutant_id, "needle not found — the source moved"))
                print(f"  UNAPPLIED {mutant_id}: needle not found")
                continue
            mutated = original.replace(needle, replacement, 1)
            if mutated == original:
                unapplied.append((mutant_id, "replacement was a no-op"))
                print(f"  UNAPPLIED {mutant_id}: replacement changed nothing")
                continue
            path.write_text(mutated, encoding="utf-8")
            if path.read_text(encoding="utf-8") != mutated:
                unapplied.append((mutant_id, "write did not land"))
                print(f"  UNAPPLIED {mutant_id}: write did not land")
                continue

            oracle_passed = _run_oracle(oracle)
            path.write_text(original, encoding="utf-8")

            if oracle_passed:
                survived.append((mutant_id, why))
                print(f"  SURVIVED  {mutant_id} — {why}")
            else:
                killed.append(mutant_id)
                print(f"  killed    {mutant_id}")
    finally:
        for path, backup in backups.items():
            shutil.copy2(backup, path)
            assert path.read_bytes() == backup.read_bytes(), f"restore failed for {path}"
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"MUTATION SUMMARY: {len(killed)} killed, {len(survived)} survived, "
          f"{len(unapplied)} unapplied, {len(MUTANTS)} total")
    for mutant_id, reason in unapplied:
        print(f"  UNAPPLIED {mutant_id}: {reason}")
    for mutant_id, why in survived:
        print(f"  SURVIVED  {mutant_id}: {why}")
    return 1 if (survived or unapplied) else 0


if __name__ == "__main__":
    raise SystemExit(main())
