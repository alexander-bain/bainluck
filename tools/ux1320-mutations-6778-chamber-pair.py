#!/usr/bin/env python3
"""#6778 mutation battery — does the guard suite actually hold the rule?

A green bar on a fixed tree proves nothing. Each mutant below breaks the rule in
one specific way and must be CAUGHT by a named clause. A SURVIVOR is a hole.

COMMIT BEFORE RUNNING. Restores by writing the original bytes back, never by
`git checkout --` (which would take the whole worktree with it).

    python3 tools/ux1320-mutations-6778-chamber-pair.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
PAGE = FE / "app" / "politics" / "page.tsx"
TEST = FE / "__tests__" / "chamberControlRoundsItsPairOnce6778.test.tsx"

CALL = (
    "  const [gopPct, demPct] = renderedDuelPercents(probs.gop / 100, probs.dem / 100);"
)

# (name, file, find, replace, why it must be caught)
MUTANTS = [
    (
        "rule-removed: the pre-#6778 card, each side rounded on its own",
        PAGE,
        CALL,
        "  const [gopPct, demPct] = [Math.round(probs.gop), Math.round(probs.dem)];",
        "the original defect — the specimen must print 42/59 = 101 again",
    ),
    (
        "card-not-duel: round index 0 and derive, so the LOSER survives whole",
        PAGE,
        CALL,
        "  const [gopPct, demPct] = [Math.round(probs.gop), 100 - Math.round(probs.gop)];",
        "prints 42/58 — sums to 100 and is still wrong. The clause asserting the "
        "EXACT pair is the only thing that sees this; a sum-only assertion passes it",
    ),
    (
        "args-swapped: the pair enters the helper in the wrong positions",
        PAGE,
        CALL,
        "  const [gopPct, demPct] = renderedDuelPercents(probs.dem / 100, probs.gop / 100);",
        "prints 59% R vs 41% D — the right arithmetic under the wrong labels",
    ),
    (
        "scale-dropped: percents handed to a helper that wants fractions",
        PAGE,
        CALL,
        "  const [gopPct, demPct] = renderedDuelPercents(probs.gop, probs.dem);",
        "41.5 + 58.5 = 100 is outside the [0.99, 1.01] complement band, so the "
        "helper falls through and the card prints 415%",
    ),
    (
        "half-wired-R: only the D side reads the pair",
        PAGE,
        "              {gopPct ?? Math.round(probs.gop)}%",
        "              {Math.round(probs.gop)}%",
        "prints 42/59 on the specimen — the ship clause sees it",
    ),
    (
        "half-wired-D: only the R side reads the pair",
        PAGE,
        "              {demPct ?? Math.round(probs.dem)}%",
        "              {Math.round(probs.dem)}%",
        "prints 41/59 on the specimen and PASSES the ship clause. Only the "
        "favourite-on-the-left clause sees it (59/42) — which is what makes that "
        "second direction load-bearing rather than decorative",
    ),
    (
        "normalise-everything: the non-complement house pair gets normalized too",
        PAGE,
        CALL,
        "  const total = probs.gop + probs.dem;\n"
        "  const [gopPct, demPct] = renderedDuelPercents(probs.gop / total, probs.dem / total);",
        "the specimen is unchanged (41/59) and the house 30/55 becomes 35/65 — "
        "15 invented points. Only the non-complement CONTROL sees this",
    ),
    (
        "bar-follows-the-label: the geometry redrawn on the printed percents",
        PAGE,
        '<div className={s.binaryR} style={{ width: `${probs.gop}%` }} />',
        '<div className={s.binaryR} style={{ width: `${gopPct}%` }} />',
        "the bar control — the split is drawn on the raw values, not the rounded ones",
    ),
    (
        "card-not-rendered: the Senate card disappears from the section",
        PAGE,
        '{senate && <ChamberControlCard chamber="Senate" probs={senate} />}',
        '{false && <ChamberControlCard chamber="Senate" probs={senate} />}',
        "the presence clause — every other arm reads an absent card as an empty "
        "list, so without this one a deleted card would pass the battery",
    ),
]

# Deliberate controls: these MUST survive. A control that dies means the suite is
# resting on a line that only reads like an assertion.
CONTROLS = [
    (
        "control: the `not.toContain(\"42%\")` string ban neutered",
        TEST,
        'expect(text).not.toContain("42%");',
        'expect(text).not.toContain("nonsense%");',
        "that line names the old number for a reader; `toEqual([41, 59])` above it "
        "is what holds the rule, and this proves the rule does not rest on a string ban",
    ),
]


def run_suite() -> tuple[bool, str]:
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=chamberControlRoundsItsPairOnce6778"],
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
