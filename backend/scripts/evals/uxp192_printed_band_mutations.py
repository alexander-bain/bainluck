#!/usr/bin/env python3
"""UX-P192 — a live price on `/weather` stops printing as impossible.

WHAT SHIPPED, and what these mutants restore

`rendered_percent` is lossy at exactly the place it matters. A temperature
bucket quoted at 0.0015 renders to `0`, and `/weather` printed that `0` raw.
`0%` does not read as "unlikely"; it reads as **impossible**, over a price a
market is actively making. The site has had the answer since UX-P046 — a value
strictly inside (0, 1) prints `<1%` or `>99%` — and `/weather` was the one
surface that never adopted it, because **the wire carried only the integer and
an integer cannot be un-rounded.**

Measured on production 2026-08-30, banked in
`backend/tests/fixtures/uxp192_printed_band.json`: 130 of the 571 served
numbers printed `0%`, out of a population containing **zero** exact zeros and
**zero** unpriced outcomes. Every one of them was false.

So three things shipped together, and each is a distinct way to get this wrong:

  1. the wire ships the PAIR (`_printed`), so the client can band at all;
  2. web prints through `weatherPercent` -> `formatProbabilityPercent`;
  3. native prints through `formatProbability` — whose band had to be CORRECTED
     first, because it used two hand-picked thresholds where web derives the
     band from the rounding result. The two disagreed at four values, including
     an exact `0` (printed `<1%`) and an exact `1` (printed `>99%`).

WHY THE THREE-RUNTIME SPAN IS THE POINT

UX-P191's battery was the first here to straddle two runtimes. This one is the
first to straddle three: Python (`weather.py`), TypeScript (`data.ts`,
`ProbabilityNumber.tsx`) and Swift (`FormattingUtilities.swift`). The Swift
oracle is the JEST contract-drift suite, not xcodebuild — the native gate does
not run in CI, so the CI-visible obligation is that the Swift table equals
`contracts/rendered_percent.json` and that the implementation's SHAPE is
derived-from-rounding rather than threshold-based. A mutation to the Swift band
that the drift suite cannot see is a real gap, and M13/M14 exist to prove it can.

All suites run for EVERY mutant rather than routing each to "its" runtime: a
mutation in one runtime that breaks another is exactly the cross-surface
coupling this ship is about, and routing would hide it.

    cd backend && python3 scripts/evals/uxp192_printed_band_mutations.py

Exit codes (gotcha #54): `0` all mutants killed, `1` a survivor — a real result,
`2` the battery could not run (missing target, absent node_modules, red oracle).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

WEATHER = BACKEND / "app/routes/weather.py"
DATA = FRONTEND / "components/weather/data.ts"
NUMBER = FRONTEND / "components/weather/ProbabilityNumber.tsx"
PANEL = FRONTEND / "components/weather/DistributionPanel.tsx"
SWIFT = REPO / "ios/Bain Luck/Bain Luck/Utilities/FormattingUtilities.swift"

#: Named, not globbed: a pattern matching nothing runs zero tests and scores
#: every mutant killed (gotcha #53 — a narrowed denominator must never print as
#: a full one). The battery asserts a floor on both counts below.
PYTEST_TARGETS = (
    "tests/integration/test_weather_printed_band_uxp192.py",
    "tests/integration/test_weather_printed_percent_uxp191.py",
    "tests/integration/test_weather_featured_leader_uxp186.py",
    "tests/integration/test_route_category_pages.py",
)
JEST_PATTERNS = (
    "weatherPrintedBandCapture",
    "renderedPercentContract",
    "probabilityDisplay",
    "weatherRainHonestyCapture",
)

#: The counts the oracle must actually execute. Without these a mutation that
#: breaks COLLECTION (an import error, a syntax error in a target) reads as a
#: kill for the wrong reason, and a `--testPathPatterns` typo reads as a clean
#: sweep over nothing.
MIN_PYTEST = 60
MIN_JEST = 120


def _backup_paths() -> dict[Path, Path]:
    """One backup per target, named from the target's REPO-RELATIVE path.

    The flat `BACKUP_DIR` form names backups by BASENAME and silently collides;
    UX-P190 lost three files to it. Not optional here even though these five
    basenames differ — it is the shape that cannot break.
    """
    root = Path("/tmp/uxp192_backups")
    return {
        t: root / str(t.relative_to(REPO)).replace("/", "__").replace(" ", "_")
        for t in sorted({m[1] for m in MUTANTS})
    }


#: `(id, target, needle, replacement, why)` — the indexed-tuple shape
#: `scan_mutation_residue.py` harvests as `("MUTANTS", 2, 3, 1)`.
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    # ── 1 · the wire stops carrying the value ──────────────────────────────
    (
        "M1-wire-drops-the-probability",
        WEATHER,
        '    return {"prob": 0 if printed is None else printed, "probability": probability}',
        '    return {"prob": 0 if printed is None else printed}',
        "THE DEFECT ITSELF, in one line. Without the fraction there is nothing "
        "for either client to band on, and every surface silently falls back to "
        "printing the integer — which is exactly the state this ship found.",
    ),
    (
        "M2-wire-ships-the-percent-not-the-fraction",
        WEATHER,
        '    return {"prob": 0 if printed is None else printed, "probability": probability}',
        '    return {"prob": 0 if printed is None else printed, "probability": probability * 100}',
        "The scale error. `probability: 0.15` becomes `15`, so the clients read "
        "every price as certain and print `>99%` across the whole page. Catches "
        "a guard that checks the KEY is present without checking its value.",
    ),
    (
        "M3-wire-rounds-the-fraction-too",
        WEATHER,
        "    printed = rendered_percent(probability)\n    return {",
        "    printed = rendered_percent(probability)\n    probability = float(printed or 0) / 100\n    return {",
        "The subtlest of the three, and the most plausible as a 'tidy-up': the "
        "pair is made CONSISTENT by throwing the value away. Every number still "
        "renders correctly; only the sub-1% ones lose the evidence for `<1%`.",
    ),
    # ⚠️ THE FIRST DRAFT OF THIS MUTANT WAS EQUIVALENT AND SURVIVED FOR THAT
    # REASON, not because a guard was missing. It flipped `p > best` to
    # `p >= best`, reasoning about `_leader_outcome_name`'s first-of-a-tie rule
    # — but this function returns the VALUE, and the two members of a tie have
    # the same value by definition, so the mutation could not change a byte.
    # A survivor is only evidence about the guards if the mutant is capable of
    # being wrong; the correct response was to write one that is.
    (
        "M4-leader-is-the-first-outcome-not-the-highest",
        WEATHER,
        "        if p > best:\n            best = p\n    return best",
        "        if p > best:\n            best = p\n    return float(next(iter(market.outcomes)).current_probability or 0)",
        "The hero prices whatever outcome the query happened to return first "
        "instead of the market's leader, while `_leader_outcome_name` still "
        "NAMES the leader — so the card reads `<1% · Minneapolis` over a "
        "44% favourite. The pair's whole promise is that they agree.",
    ),
    # ── 2 · web stops using the site's single home ─────────────────────────
    (
        "M5-web-adapter-ignores-the-probability",
        DATA,
        "  return formatProbabilityPercent(item.probability ?? item.prob / 100, {\n    rendered: item.prob,\n  });",
        "  return `${item.prob}%`;",
        "THE DEFECT ITSELF on web. The adapter reduced to the raw interpolation "
        "every one of these components used before.",
    ),
    (
        "M6-web-adapter-drops-the-rendered-override",
        DATA,
        "  return formatProbabilityPercent(item.probability ?? item.prob / 100, {\n    rendered: item.prob,\n  });",
        "  return formatProbabilityPercent(item.probability ?? item.prob / 100);",
        "Looks harmless — the two nearly always agree. But the server's integer "
        "is the one the card-sum rule decided (#2060), and re-deriving it here "
        "is how two sides of one question come to sum to 101.",
    ),
    (
        "M7-web-fallback-invents-a-band",
        DATA,
        "  return formatProbabilityPercent(item.probability ?? item.prob / 100, {\n    rendered: item.prob,\n  });",
        "  return formatProbabilityPercent(item.probability ?? 0.001, {\n    rendered: item.prob,\n  });",
        "THE WRONG DIRECTION, and the tempting one. A payload from the hourly "
        "cache with no `probability` would print `<1%` over a number the server "
        "never called small. A missing field must degrade to the OLD answer.",
    ),
    (
        "M8-hasPrice-asks-the-integer-again",
        DATA,
        "  return (item.probability ?? item.prob / 100) > 0;",
        "  return item.prob > 0;",
        "The histogram's hover gate. Restoring it hides the tooltip on exactly "
        "the buckets whose number the reader most needs — the ones this queue "
        "made printable.",
    ),
    (
        "M9-hero-splits-the-string-by-re-rounding",
        NUMBER,
        "  const printed = weatherPercent(item);\n  const body = printed.endsWith(\"%\") ? printed.slice(0, -1) : printed;",
        "  const printed = weatherPercent(item);\n  const body = String(Math.round(item.prob));",
        "The 64px hero. Formats once for the decision and again for the digits, "
        "so the big number reads `0` under a card that has already decided "
        "`<1%`. Two decisions for one number is the bug the formatter prevents.",
    ),
    (
        "M10-panel-peak-prints-the-integer",
        PANEL,
        "          {weatherPercent(peak)}\n        </span>",
        "          {peak.prob}%\n        </span>",
        "The temperature panel's headline. One surface reverting is the "
        "half-landing this ship exists to avoid, and it is the number a reader "
        "sees before any hover.",
    ),
    # ── 3 · native's band drifts back off the contract ─────────────────────
    (
        "M11-native-back-to-thresholds",
        SWIFT,
        "    if rounded <= 0 && value > 0 { return \"<1%\" }\n    if rounded >= 100 && value < 1 { return \">99%\" }",
        "    let pct = value * 100\n    if pct < 1 { return \"<1%\" }\n    if pct > 99 { return \">99%\" }",
        "THE NATIVE DEFECT ITSELF — the shape that printed `<1%` for an exact "
        "ZERO and `>99%` for an exact ONE, and disagreed with web at 0.005 and "
        "0.994. The jest drift suite asserts the derived shape, not the values, "
        "which is the only check CI can run on a runtime it never builds.",
    ),
    (
        "M12-native-returns-the-override-before-banding",
        SWIFT,
        "    let rounded = renderedPercent ?? Int((value * 100).rounded())\n\n    // Strictly inside the interval, but rounding would claim a boundary.",
        "    if let renderedPercent { return \"\\(renderedPercent)%\" }\n    let rounded = Int((value * 100).rounded())\n\n    // Strictly inside the interval, but rounding would claim a boundary.",
        "The composition the two halves of the contract meet at: a served 100 "
        "over a probability of 0.996 must still print `>99%`. This is what "
        "native's old code did, and it passes every non-override row — which is "
        "why `printed_override_cases` exists as its own table.\n\n"
        "⚠️ IT SURVIVED THE FIRST RUN, and that was the battery's best single "
        "finding. The Swift RUNTIME row that catches it "
        "(`testEveryPrintedOverrideRow`) lives in a suite CI never executes, and "
        "the jest shape checks only asserted what the code CONTAINS — which this "
        "mutation leaves entirely intact, since it merely adds a return above "
        "them. A containment check cannot see an early exit. The fix was a "
        "negative shape assertion in the drift suite; the general form is that "
        "**a guard on an unbuilt runtime must assert ORDER, not just presence.**",
    ),
    (
        "M13-swift-table-drifts-from-the-contract",
        SWIFT.parent.parent.parent / "BainLuckTests/RenderedPercentContractTests.swift",
        '    (0.0, "0%", true),',
        '    (0.0, "<1%", true),',
        "The DRIFT check itself. The native runtime check lives in a suite CI "
        "never runs, so the only CI-visible obligation is that its inlined table "
        "still equals the contract. If this survives, the Swift arm is "
        "unguarded in CI and nobody would know until they ran xcodebuild.",
    ),
    (
        "M14-contract-loses-its-boundary-rows",
        REPO / "contracts/rendered_percent.json",
        '    { "probability": 1.0,    "printed": "100%",  "diverged": true,',
        '    { "probability": 1.0,    "printed": ">99%",  "diverged": false,',
        "Defanging the table at the row that matters most — an exact one is "
        "certain, and 'settled means settled' is a product ruling. A contract "
        "that can be edited without a suite noticing is documentation.",
    ),
]


def _tail(proc: subprocess.CompletedProcess) -> list[str]:
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip().splitlines()[-8:]


def _run_pytest() -> tuple[bool, int, list[str]]:
    proc = subprocess.run(
        ["python3", "-m", "pytest", *PYTEST_TARGETS, "-q", "-p", "no:warnings"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # `N passed` / `N failed` — summed, because a red run reports both.
    ran = sum(
        int(n) for n, _kind in re.findall(r"(\d+) (passed|failed|error|errors)", out)
    )
    return proc.returncode == 0, ran, _tail(proc)


def _run_jest() -> tuple[bool, int, list[str]]:
    args = ["npx", "jest"]
    for pattern in JEST_PATTERNS:
        args += ["--testPathPatterns", pattern]
    proc = subprocess.run(
        args,
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"Tests:.*?(\d+) total", out, re.S)
    return proc.returncode == 0, int(m.group(1)) if m else 0, _tail(proc)


def _run_oracle() -> tuple[bool, tuple[int, int], list[str]]:
    """All three runtimes' CI-visible arms. Killed if EITHER suite goes red."""
    py_ok, py_n, py_tail = _run_pytest()
    js_ok, js_n, js_tail = _run_jest()
    return py_ok and js_ok, (py_n, js_n), py_tail + js_tail


def main() -> int:
    targets = sorted({m[1] for m in MUTANTS})
    for target in targets:
        if not target.exists():
            print(f"🔴 battery cannot run — missing target {target}")
            return 2
    if not (FRONTEND / "node_modules").exists():
        print(
            "🔴 battery cannot run — frontend/node_modules is absent. "
            "Symlink master's (see .gitignore's note on worktree installs)."
        )
        return 2

    baseline_ok, (py_n, js_n), baseline_tail = _run_oracle()
    if not baseline_ok:
        print("🔴 battery cannot run — the oracle is RED before any mutation:")
        print("\n".join(baseline_tail))
        return 2
    if py_n < MIN_PYTEST or js_n < MIN_JEST:
        print(
            f"🔴 battery cannot run — the oracle executed {py_n} pytest and "
            f"{js_n} jest tests, below the {MIN_PYTEST}/{MIN_JEST} floor. A "
            "target list that has rotted scores every mutant killed."
        )
        return 2
    print(
        f"baseline: oracle GREEN — {py_n} pytest + {js_n} jest tests, "
        f"{len(MUTANTS)} mutants to run\n"
    )

    killed: list[str] = []
    survived: list[str] = []
    not_applied: list[str] = []

    backups = _backup_paths()
    backups[list(backups)[0]].parent.mkdir(parents=True, exist_ok=True)
    assert len(set(backups.values())) == len(backups), "backup paths collide"

    with guarded_targets(targets, backups, "uxp192-printed-band"):
        for mutant_id, path, needle, replacement, _why in MUTANTS:
            original = path.read_text()
            count = original.count(needle)
            if count != 1:
                not_applied.append(f"{mutant_id} (needle matched {count}x)")
                print(f"  ⚠️  NOT APPLIED  {mutant_id} — needle matched {count}x")
                continue
            path.write_text(original.replace(needle, replacement))
            try:
                passed, _counts, _t = _run_oracle()
            finally:
                path.write_text(original)
            if passed:
                survived.append(mutant_id)
                print(f"  🔴 SURVIVED     {mutant_id}")
            else:
                killed.append(mutant_id)
                print(f"  ✅ killed       {mutant_id}")

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed · {len(survived)} survived · "
        f"{len(not_applied)} not applied"
    )
    for s in survived:
        print(f"  SURVIVOR — the guard covering {s} does not bite")
    for n in not_applied:
        print(f"  NOT APPLIED — {n}")
    return 0 if (not survived and not not_applied) else 1


if __name__ == "__main__":
    sys.exit(main())
