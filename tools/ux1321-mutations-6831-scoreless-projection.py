#!/usr/bin/env python3
"""#6831 mutation battery — does the guard suite actually hold the rule?

A green bar on a fixed tree proves nothing. Each mutant below breaks the rule in
one specific way and must be CAUGHT by a named clause. A SURVIVOR is a hole.

The rule under test: on a live card, `pace.projected_total` is printed only when
it is a positive number. It is the score so far divided by the fraction elapsed,
so a scoreless game yields exactly 0 at every elapsed fraction, and 0 is not
null — which is how /events/14638444 came to headline "Projected 0" over its own
"PRE-GAME 55" tile 11 minutes into a 0 - 0 NFL game.

COMMIT BEFORE RUNNING. Restores by writing the original bytes back, never by
`git checkout --` (which would take the whole worktree with it).

    python3 tools/ux1321-mutations-6831-scoreless-projection.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
CARD = FE / "components" / "MarketMapSection.tsx"
TEST = FE / "__tests__" / "components" / "scorelessLiveProjectionHasNoStanding6831.test.tsx"

GUARD = (
    "    const projectedRaw = pace?.projected_total ?? null;\n"
    "    const projected = projectedRaw != null && projectedRaw > 0 ? projectedRaw : null;"
)

# The live headline's GATE, not its template. Mutating the template alone is
# INERT: the gate `projected != null` is already false on the scoreless
# specimen, so the branch never runs and the mutant cannot express the defect
# it is named for. Half-wiring has to move the GATE onto the raw value.
HEADLINE_GATE = (
    '      : status === "live" && projected != null\n'
    "      ? `Projected ${Math.round(projected)}`"
)

# (name, file, find, replace, why it must be caught)
MUTANTS = [
    (
        "rule-removed: the pre-#6831 card, presence-only",
        CARD,
        GUARD,
        "    const projected = pace?.projected_total ?? null;",
        "the original defect — the 0 - 0 specimen headlines `Projected 0` and "
        "tiles `0.0` again",
    ),
    (
        "boundary-ge: `>= 0` admits the exact value the defect is made of",
        CARD,
        GUARD,
        "    const projectedRaw = pace?.projected_total ?? null;\n"
        "    const projected = projectedRaw != null && projectedRaw >= 0 ? projectedRaw : null;",
        "0 is the whole population of this bug, so an off-by-one on the "
        "comparator is the defect untouched",
    ),
    (
        "boundary-ne: `!== 0` lets a negative through",
        CARD,
        GUARD,
        "    const projectedRaw = pace?.projected_total ?? null;\n"
        "    const projected = projectedRaw != null && projectedRaw !== 0 ? projectedRaw : null;",
        "passes the ship clause and the standing control — only the negative "
        "clause distinguishes `> 0` from `!== 0`",
    ),
    (
        "always-null: delete the projection outright",
        CARD,
        GUARD,
        "    const projected = null as number | null;",
        "satisfies the ship clause by losing a true number on every scoring "
        "game. Only the standing CONTROL sees this",
    ),
    (
        "half-wired-headline: marker guarded, headline still on the raw value",
        CARD,
        HEADLINE_GATE,
        '      : status === "live" && projectedRaw != null\n'
        "      ? `Projected ${Math.round(projectedRaw)}`",
        "the card headlines `Projected 0` while its own tile shows nothing — "
        "caught only because the ship clause asserts BOTH sites",
    ),
    (
        "suppress-the-card: withhold the forecast by withholding everything",
        CARD,
        "    if (gameTotals.length === 0) return null;",
        "    if (gameTotals.length === 0 || (pace?.total_scored ?? 0) === 0) return null;",
        "passes the ship clause and loses ACTUAL, PRE-GAME and the ladder with "
        "it. Only the keeps-every-number CONTROL sees this",
    ),
]

CONTROLS = [
    (
        "CONTROL rename-only: the binding renamed, the rule identical",
        CARD,
        GUARD,
        "    const paceForward = pace?.projected_total ?? null;\n"
        "    const projected = paceForward != null && paceForward > 0 ? paceForward : null;",
        "a pure rename changes no reader-visible value, so a suite that dies "
        "here is keyed on the source text rather than on what the card prints",
    ),
]


def run_suite() -> tuple[bool, str]:
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=scorelessLiveProjectionHasNoStanding6831"],
        cwd=FE, capture_output=True, text=True,
    )
    return p.returncode == 0, (p.stdout + p.stderr)


def caught_clauses(output: str) -> list[str]:
    """Jest names each failure on a `● <describe> › <clause>` line."""
    names = []
    for line in output.splitlines():
        s = line.strip()
        if s.startswith("●") and "›" in s:
            clause = s.split("›")[-1].strip()
            if clause and clause not in names:
                names.append(clause)
    return names


def main() -> int:
    ok, out = run_suite()
    if not ok:
        print("BASELINE IS RED — fix the tree before mutating.")
        print(out[-3000:])
        return 2
    print("baseline: GREEN\n")

    survivors = []
    signatures = set()
    bad_controls = []
    for name, path, find, repl, why in MUTANTS + CONTROLS:
        is_control = (name, path, find, repl, why) in CONTROLS
        original = path.read_text()
        if find not in original:
            print(f"🔴 ANCHOR NOT FOUND — {name}\n     looked for: {find!r}")
            survivors.append(name + " (anchor missing)")
            continue
        path.write_text(original.replace(find, repl, 1))
        print(f"applied   {name}")
        try:
            passed, output = run_suite()
        finally:
            path.write_text(original)
            print(f"restored  {name}")
        clauses = caught_clauses(output)
        if is_control:
            if passed:
                print(f"   ✅ survived as designed — {why}\n")
            else:
                print(f"   🔴 CONTROL DIED — caught by: {'; '.join(clauses)}\n")
                bad_controls.append(name)
            continue
        if passed:
            print(f"   🔴 SURVIVED — {why}\n")
            survivors.append(name)
        else:
            signatures.add(tuple(sorted(clauses)))
            shown = "; ".join(clauses) or "(suite red, clause unparsed)"
            print(f"   ✅ caught by: {shown}\n")

    print("=" * 72)
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} mutants caught, "
          f"{len(signatures)} distinct failure signatures; "
          f"{len(CONTROLS) - len(bad_controls)}/{len(CONTROLS)} controls survived as designed")
    if survivors or bad_controls:
        for s in survivors:
            print("  SURVIVOR (a hole in the guard):", s)
        for s in bad_controls:
            print("  CONTROL DIED (the suite rests on prose):", s)
        return 1
    ok, _ = run_suite()
    print("tree restored and GREEN" if ok else "🔴 TREE NOT RESTORED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
