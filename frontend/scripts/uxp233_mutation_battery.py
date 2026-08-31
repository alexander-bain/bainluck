#!/usr/bin/env python3
"""UX-P233 mutation battery — board item 11, the unlabelled baselines.

This ship is COPY, so most mutants are the plausible wrong words rather than wrong
arithmetic — above all the tempting `24h`, which the payload itself disproves
(CAL-P159; every row on 109441 is dated 2026-08-28). Mutants A-D are the four ways
to reintroduce that false claim.

For every mutant we PROVE the edit applied (the file on disk really changed and
contains the mutant text), run the guards, and require a non-zero exit. Sources are
restored inside `finally:` and the restore is verified byte-for-byte by sha256.

Run from `frontend/`:  python3 scripts/uxp233_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

LIB = Path("lib/futuresDetailDisplay.ts")
PAGE = Path("app/futures/[id]/page.tsx")
HERO = Path("components/FuturesHero.tsx")

TEST_PATTERN = "futuresBaseline|futuresHeroAmbient|futuresDetailDisplay"

# (id, file, find, replace, what it models[, TZ to detect it under])
MUTANTS: list[tuple] = [
    (
        "A",
        LIB,
        'if (priceAgeDays(lastUpdated, now) == null) return "last move";\n  return `last move · ${utcDayLabel(new Date(lastUpdated as string))}`;',
        'return "last 24h";',
        "🔴 THE FALSE CLAIM ITSELF — the label goes back to asserting a 24-hour "
        "window the payload dates to 2026-08-28",
    ),
    (
        "B",
        PAGE,
        'label="Last move"',
        'label="24h Change"',
        "the sort control reverts to naming a window the data does not have",
    ),
    (
        "C",
        PAGE,
        "Last move\n        </div>",
        "24h Change\n        </div>",
        "the row's change column re-acquires the 24h claim",
    ),
    (
        "D",
        LIB,
        'return `last move · ${utcDayLabel(new Date(lastUpdated as string))}`;',
        'return `today · ${utcDayLabel(new Date(lastUpdated as string))}`;',
        "'today' — a different unprovable freshness word for the same number",
    ),
    (
        "E",
        LIB,
        "  if (!lastUpdated) return null;",
        "  if (!lastUpdated) return 0;",
        "a MISSING stamp read as zero age, i.e. absence dressed as freshness "
        "(gotcha #53) — the page would then claim the price is current",
    ),
    (
        "F",
        LIB,
        "  if (age == null || age <= AS_OF_AFTER_DAYS) return null;",
        "  if (age == null) return null;",
        "the as-of fires on a FRESH price too — noise presented as honesty, and "
        "an 'as of' on a price taken minutes ago misleads in the other direction",
    ),
    (
        "G",
        LIB,
        "const AS_OF_AFTER_DAYS = 1;",
        "const AS_OF_AFTER_DAYS = 30;",
        "the staleness threshold widens so a 2.9-day-old price silently passes "
        "as current — the exact page Alex reviewed",
    ),
    # 🔴 RUN THIS ONE IN SYDNEY, AND THAT IS THE WHOLE POINT.
    # `FuturesHero` is a CLIENT component, so `toLocaleDateString` resolves in the
    # READER'S zone: 2026-08-28T20:50Z is Aug 28 in UTC and Aug 29 in Sydney. Drop
    # the `timeZone: "UTC"` pin and two readers see different dates for one instant.
    # CI runs `TZ=UTC`, where local and UTC agree — so under UTC this mutant is
    # INVISIBLE, and it survived the first battery for exactly that reason. A guard
    # that can only be run where the bug cannot appear is not a guard (CERT-534).
    (
        "H",
        LIB,
        '    timeZone: "UTC",\n',
        "",
        "the date label falls back to the reader's local zone, so a user in "
        "Sydney and a user in Los Angeles see different days for one instant",
        "Australia/Sydney",
    ),
    (
        "I",
        LIB,
        "  return Math.max(0, (now.getTime() - then.getTime()) / 86_400_000);",
        "  return (now.getTime() - then.getTime()) / 86_400_000;",
        "a future stamp yields a NEGATIVE age, which compares as fresh",
    ),
    (
        "J",
        PAGE,
        "        movementLabel={movementWindowLabel(leader?.last_updated)}",
        "",
        "the page stops passing the label — the helper is correct and nothing "
        "renders it, which is the state this prop was ALREADY in before this ship",
    ),
    (
        "K",
        PAGE,
        "  const marketAsOf = asOfLabel(leader?.last_updated);",
        "  const marketAsOf = null;",
        "the table's single as-of line disappears and every number under it "
        "loses its date again",
    ),
    (
        "L",
        HERO,
        '                        data-testid="hero-movement-window"',
        '                        data-testid="hero-movement-window-x"',
        "the render hook is renamed — the guard must not read a missing element "
        "as agreement",
    ),
    (
        "M",
        PAGE,
        "            Latest\n",
        "            Now\n",
        "the current column claims to be 'Now' on prices the same payload dates "
        "to three days ago",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards(tz: str = "UTC") -> int:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": tz},
    )
    return proc.returncode


def main() -> int:
    files = (LIB, PAGE, HERO)
    originals = {p: p.read_text() for p in files}
    original_shas = {p: sha(p) for p in files}

    # Both baselines, because mutant H is only detectable outside UTC and a green
    # verdict there is worthless if the unmutated code is red there too. The Sydney
    # run also PROVES the UTC pin works: same expectations, different reader zone.
    for tz in ("UTC", "Australia/Sydney"):
        baseline = run_guards(tz)
        if baseline != 0:
            print(f"BASELINE IS NOT GREEN under TZ={tz} (exit {baseline}) — battery is meaningless")
            return 2
        print(f"baseline TZ={tz}: GREEN")
    print()

    killed, survived = [], []
    try:
        for mutant in MUTANTS:
            mid, path, find, repl, why = mutant[:5]
            tz = mutant[5] if len(mutant) > 5 else "UTC"
            src = originals[path]
            if src.count(find) != 1:
                print(f"{mid}: ANCHOR NOT UNIQUE ({src.count(find)} hits) — battery invalid")
                return 2
            mutated = src.replace(find, repl)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"
            if repl:
                assert repl in path.read_text(), f"{mid}: mutant text absent after write"
            else:
                assert find not in path.read_text(), f"{mid}: deletion did not apply"

            code = run_guards(tz)
            path.write_text(src)
            assert sha(path) == original_shas[path], f"{mid}: restore not byte-identical"

            where = "" if tz == "UTC" else f" [TZ={tz}]"
            if code != 0:
                killed.append(mid)
                print(f"{mid}: KILLED (exit {code}){where} — {why}")
            else:
                survived.append(mid)
                print(f"{mid}: *** SURVIVED ***{where} — {why}")
    finally:
        for path, src in originals.items():
            path.write_text(src)
            assert sha(path) == original_shas[path], f"RESIDUE: {path} not restored"
        print("\nall sources restored, sha256 verified")

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print(f"SURVIVORS: {', '.join(survived)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
