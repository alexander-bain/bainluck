#!/usr/bin/env python3
"""#7004 mutation battery — can the guard tell an honest box from every dishonest one?

The fix is an ABSENCE, which is the easiest thing to guard vacuously, so the
mutants are weighted towards the two ways an absence-guard fails: the label
comes back under a DIFFERENT name, and the box stops rendering at all (which
satisfies every `not.toContain` ever written).

Mutant 1 is also the RED-FIRST run — it restores the exact string that shipped.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "frontend/components/daily/DailyThresholdBox.tsx"

ANCHOR = """      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">"""
LABELLED = '''      <p className="text-sm text-text-secondary">{LABEL}</p>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">'''

MUTANTS = [
    # RED-FIRST: the exact label that was live on production.
    ("label-restored-verbatim", ANCHOR, LABELLED.replace("{LABEL}", "Market line")),
    ("label-reworded-market-price", ANCHOR, LABELLED.replace("{LABEL}", "Market price")),
    ("label-reworded-odds", ANCHOR, LABELLED.replace("{LABEL}", "The odds")),
    ("label-reworded-consensus", ANCHOR, LABELLED.replace("{LABEL}", "Sportsbook consensus")),
    ("label-reworded-the-line", ANCHOR, LABELLED.replace("{LABEL}", "The line")),
    ("label-as-a-sentence", ANCHOR, LABELLED.replace("{LABEL}", "What traders say right now")),
    # The mutant that satisfies every absence assertion in the file.
    ("box-renders-nothing", "  return (\n    <div", "  return null;\n  return (\n    <div"),
    # The number stops being the one it was handed.
    ("threshold-hardcoded", "{threshold}%", "34%"),
    ("subject-dropped", "<p className=\"text-lg font-semibold\">{subject}</p>", ""),
    ("question-dropped",
     "          <p className=\"text-sm text-text-muted\">\n            Is the probability higher or lower than this?\n          </p>",
     ""),
]


def jest() -> bool:
    r = subprocess.run(
        ["npx", "jest", "--testPathPatterns=dailyThresholdIsNotTheMarketLine7004"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    if r.returncode not in (0, 1):
        sys.exit(f"HARNESS FAILURE: jest exited {r.returncode}\n{r.stderr[-2000:]}")
    return r.returncode == 0


def main() -> int:
    original = BOX.read_text()

    print("control (unmutated) ...", end=" ", flush=True)
    if not jest():
        sys.exit("CONTROL IS RED — every result below would be meaningless.")
    print("GREEN")

    survivors = []
    try:
        for name, find, repl in MUTANTS:
            n = original.count(find)
            if n != 1:
                sys.exit(f"{name}: anchor appears {n} times, expected 1")
            BOX.write_text(original.replace(find, repl))
            green = jest()
            BOX.write_text(original)
            if green:
                survivors.append(name)
            print(f"  {'SURVIVED' if green else 'killed':9} {name}")
    finally:
        BOX.write_text(original)

    print(f"\n{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} killed")
    if survivors:
        print("SURVIVORS (holes in the guard):", ", ".join(survivors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
