"""LAT-P036 — mutation harness for the stemmer synonym, the alias tier and the
wrong-league guard.

A green suite proves the code works on the paths the suite walks. It does not
prove the suite would NOTICE the code being undone, and that second property is
the only reason a regression guard exists. So each mutant below deliberately
breaks one property this queue shipped, and the harness demands the oracle FAIL.

TWO DIRECTIONS, on purpose
--------------------------
Half the mutants REMOVE the fix (drop the synonym, drop the alias, drop the tier
branch, drop the ticker check). The other half OVER-APPLY it — make the synonym
symmetric, promote alias hits to tier 0, replace the league guard's name test
with the ticker instead of adding to it. A guard that only catches deletion lets
the next cycle "improve" the rule into a recall regression, which is how both
LAT-P002 and LAT-P035 were reverted.

WHY IT MUTATES ON DISK, AND WHAT THAT OBLIGES
---------------------------------------------
The oracle is a pytest module that imports ``app.routes.events`` and reads it
with ``inspect.getsource``; an in-memory exec'd copy would not be the module it
sees. So the mutation is written to the real file and restored from a ``cp``
backup.

That makes one failure mode load-bearing: **a mutation that does not APPLY
reports green**, because the oracle passes against unmutated source and a naive
harness scores that as a kill. Every mutant therefore asserts its needle was
present, that the file actually changed, and — after restore — that the file is
byte-identical to the backup. A mutant that fails to apply is a HARNESS failure
and exits non-zero; it is never silently counted as a kill.

This file replaces ``search_word_test_mutations.py``, which went with the
``e22576db`` revert of LAT-P035. The discipline above is inherited from it
deliberately; the mutants are this queue's own.

Usage::

    python scripts/evals/search_stemmer_alias_mutations.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
EVENTS = BACKEND / "app/routes/events.py"

ORACLE = "tests/test_search_stemmer_alias_and_league_demotion.py"

# (id, file, needle, replacement, oracle, why)
MUTANTS: list[tuple[str, Path, str, str, str, str]] = [
    # ---- direction 1: undo the fix -------------------------------------
    (
        "president-synonym-removed",
        EVENTS,
        """    "president": "presidential",
}""",
        "}",
        ORACLE,
        "Undoes #1761: `president` stems to `presid`, the text to `presidenti`, so "
        "ts_rank_cd scores the 667M-volume Presidential Election market 0 and it "
        "sorts below every market merely named 'President'.",
    ),
    (
        "nba-finals-alias-removed",
        EVENTS,
        """    ("nba", "finals"): (("pro", "basketball", "champion"),),
}""",
        "}",
        ORACLE,
        "Market 350 is named '2026 Pro Basketball Champion'; without the alias no "
        "stemmer and no synonym can reach it, which is why it sat open six cycles.",
    ),
    (
        "alias-tier-removed",
        EVENTS,
        """    if _futures_alias_arms:
        _futures_tier_whens.append((or_(*_futures_alias_arms), 1))
""",
        "",
        ORACLE,
        "Recall without a tier: alias rows rank against the literal query, score 0, "
        "and market 350 lands at position 11 below five ticket-price markets.",
    ),
    (
        "alias-arms-not-shared",
        EVENTS,
        """    _futures_alias_arms = _alias_futures_arms(terms)
    _futures_where_or.extend(_futures_alias_arms)""",
        "    _futures_where_or.extend(_alias_futures_arms(terms))",
        ORACLE,
        "Recall and the tier stop reading one list, so they can disagree about what "
        "an alias hit is — the SQL/Python divergence class LAT-P033 fixed.",
    ),
    (
        "league-demotion-ticker-check-removed",
        EVENTS,
        """        if any(p.search(n) for p in pats):
            return True
        ticker = (getattr(m, "external_id", None) or "").lower()
        return ticker.startswith(ticker_prefixes)""",
        "        return any(p.search(n) for p in pats)",
        ORACLE,
        "Back to name-only, which the corpus outgrew: 46 of 75 open WNBA markets are "
        "named \"Women's Pro Basketball\" and carry no `wnba` token to match.",
    ),
    # ---- direction 2: over-apply it ------------------------------------
    (
        "president-synonym-made-symmetric",
        EVENTS,
        '    "president": "presidential",',
        '    "president": "presidential",\n    "presidential": "president",',
        ORACLE,
        "The tidy-up direction: adds the reverse mapping, widening `presidential` to "
        "86 President-only markets as an unmeasured recall change.",
    ),
    (
        "alias-tier-promoted-to-literal",
        EVENTS,
        "_futures_tier_whens.append((or_(*_futures_alias_arms), 1))",
        "_futures_tier_whens.append((or_(*_futures_alias_arms), 0))",
        ORACLE,
        "Over-applies it: a phrase WE substituted ties with a name the user actually "
        "typed, so an alias can outrank a literal match.",
    ),
    (
        "league-demotion-name-check-removed",
        EVENTS,
        """        if any(p.search(n) for p in pats):
            return True
        ticker = (getattr(m, "external_id", None) or "").lower()
        return ticker.startswith(ticker_prefixes)""",
        """        ticker = (getattr(m, "external_id", None) or "").lower()
        return ticker.startswith(ticker_prefixes)""",
        ORACLE,
        "The inverse over-correction: ticker-only silently drops every non-Kalshi "
        "source, whose external_id is not a `kx…` ticker at all.",
    ),
]


def _run_oracle(oracle: str) -> bool:
    """True when the oracle PASSES (i.e. the mutant survived)."""

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", oracle, "-x", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    return proc.returncode == 0


def main() -> int:
    killed: list[str] = []
    survived: list[str] = []
    unapplied: list[str] = []

    for name, path, needle, replacement, oracle, why in MUTANTS:
        original = path.read_text(encoding="utf-8")

        # A mutant that does not apply is a HARNESS failure, never a kill.
        if needle not in original:
            unapplied.append(f"{name}: needle absent from {path.name}")
            print(f"  UNAPPLIED {name}  <- needle not found")
            continue

        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / path.name
            shutil.copy2(path, backup)
            mutated = original.replace(needle, replacement, 1)
            if mutated == original:
                unapplied.append(f"{name}: replacement was a no-op")
                print(f"  UNAPPLIED {name}  <- replacement changed nothing")
                continue
            path.write_text(mutated, encoding="utf-8")
            try:
                if path.read_text(encoding="utf-8") == original:
                    unapplied.append(f"{name}: file unchanged on disk")
                    print(f"  UNAPPLIED {name}  <- file did not change on disk")
                    continue
                if _run_oracle(oracle):
                    survived.append(f"{name}: {why}")
                    print(f"  SURVIVED  {name}")
                else:
                    killed.append(name)
                    print(f"  killed    {name}")
            finally:
                shutil.copy2(backup, path)
                if path.read_text(encoding="utf-8") != original:
                    print(f"  !! RESTORE FAILED for {path} — check your tree", file=sys.stderr)
                    return 3

    print(
        f"\nMUTATION SUMMARY: {len(killed)} killed, {len(survived)} survived, "
        f"{len(unapplied)} unapplied, {len(MUTANTS)} total"
    )
    for line in survived:
        print(f"  SURVIVED: {line}", file=sys.stderr)
    for line in unapplied:
        print(f"  UNAPPLIED: {line}", file=sys.stderr)

    # Unapplied is a failure in its OWN right: it means the harness proved nothing.
    return 0 if not survived and not unapplied else 1


if __name__ == "__main__":
    raise SystemExit(main())
