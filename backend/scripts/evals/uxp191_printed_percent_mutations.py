#!/usr/bin/env python3
"""UX-P191 — two surfaces print a percentage the way the rest of the site does.

WHAT SHIPPED, and what these mutants restore

Two surfaces bypassed a single-home formatter that already existed, and each
bypass printed a number the product's own rules say is wrong.

`/weather` rounded every probability with Python's `round()`, which is BANKER'S
rounding: `round(78.5)` is 78, while `Math.round` on web, `.rounded()` on native
and the server's own `rendered_percent` (#1933, `contracts/rendered_percent.json`)
all give 79. Measured on production 2026-08-30: 81 of 442 open weather markets
and 373 of 2,650 priced outcomes printed a point LOW, and 71 of the 500 numbers
actually served by `GET /api/weather/*` change — including two of the five
featured heroes, and four temperature buckets priced 0.005 that printed a bare
`0%` over a live quote. Three call sites, one rule.

`/politics`'s cross-source card printed `.toFixed(1)` inline instead of going
through `formatProbabilityPercent` (UX-P046). That forced a decimal digit onto
numbers that do not have one — 6 of the 8 served rows, 3 of the 4 rendered —
and skipped the boundary rule on the one surface that selects for extremes by
construction.

WHY THE ARITHMETIC MUTANTS MATTER AS MUCH AS THE ROUNDING ONES

Rounding the card's two numbers without deriving the rest FROM them breaks it:
`4.5 / 86.0` prints `5% / 86%`, a gap of 81, while the served delta of 81.5
rounds to 82. Two of the eight live rows land in that gap. M9 and M10 are those
near-misses, graded like any other.

TARGETS ARE PYTHON **AND** TYPESCRIPT, so the oracle is pytest AND jest. Both
run for every mutant rather than routing each mutant to "its" suite: a mutation
in one runtime that breaks the other is exactly the cross-surface coupling this
ship is about, and routing would hide it.

    cd backend && python3 scripts/evals/uxp191_printed_percent_mutations.py

Exit codes (gotcha #54): `0` all mutants killed, `1` a survivor — a real result,
`2` the battery could not run (missing target, absent node_modules, red oracle).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

WEATHER = BACKEND / "app/routes/weather.py"
CARD = FRONTEND / "components/politics/CrossSourceSpotlight.tsx"

#: The pytest module and the jest modules that ARE the oracle. Named, not
#: globbed: a pattern matching nothing runs zero tests and scores every mutant
#: killed (gotcha #53 — a narrowed denominator must never print as a full one).
PYTEST_TARGETS = (
    "tests/integration/test_weather_printed_percent_uxp191.py",
    "tests/integration/test_weather_featured_leader_uxp186.py",
    # ⚠️ UX-P192's file was added to the oracle because M3 SURVIVED without it,
    # and the survival is instructive rather than embarrassing. Rounding the
    # yes-leg EARLY (`round(p * 100) / 100`) leaves the printed INTEGER correct
    # — 0.635 still prints 64 — so every UX-P191-era assertion, all of which are
    # about the integer, agrees with the mutant. What it destroys is the
    # FRACTION the client bands on, and only the file that asserts the fraction
    # can see that. A battery whose oracle predates the property being mutated
    # cannot grade it.
    "tests/integration/test_weather_printed_band_uxp192.py",
)
JEST_PATTERNS = (
    "politicsCrossSourcePrecisionCapture",
    "politicsCrossSourceOutcomeCapture",
)


def _backup_paths() -> dict[Path, Path]:
    """One backup file per target, named from the target's REPO-RELATIVE path.

    The flat `BACKUP_DIR` form names backups by BASENAME and silently collides;
    UX-P190 lost three files to it. The dict form is not optional here even
    though these two basenames differ — it is the shape that cannot break.
    """
    root = Path("/tmp/uxp191_backups")
    return {
        t: root / str(t.relative_to(REPO)).replace("/", "__")
        for t in sorted({m[1] for m in MUTANTS})
    }


#: `(id, target, needle, replacement, why)` — the indexed-tuple shape
#: `scan_mutation_residue.py` harvests as `("MUTANTS", 2, 3, 1)`.
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    # ── the weather rounding rule ──────────────────────────────────────────
    # ⚠️ UX-P192 COLLAPSED THE THREE CALL SITES INTO ONE (`_printed`), so M1-M6
    # were re-pointed at the surviving code. They were NOT deleted and NOT
    # weakened: each still restores the same wrong arithmetic, and the two that
    # used to hit `_highest_prob` and the city loop separately now hit the one
    # home — which is a STRONGER mutation, because it breaks all seven surfaces
    # at once and so must be caught by all seven guards.
    #
    # Re-pointing rather than deleting matters: a battery whose needles have
    # rotted reports NOT APPLIED, which is honest but proves nothing, and the
    # next reader has no way to tell a stale battery from a covered one.
    (
        "M1-printed-back-to-bankers",
        WEATHER,
        "    printed = rendered_percent(probability)",
        "    printed = round(probability * 100)",
        "THE DEFECT ITSELF. `_printed` feeds the featured hero, the temperature "
        "panel, both rain lists, the natural-events list, the climate board and "
        "the wildcards rail.",
    ),
    (
        "M2-leader-scan-drops-the-fraction",
        WEATHER,
        "        if p > best:\n            best = p\n    return best",
        "        if p > best:\n            best = p\n    return float(round(best * 100)) / 100",
        "Rounds at the SCAN instead of at the print, so the fraction the client "
        "bands on is already a whole percent. Every `<1%` collapses back to 0.",
    ),
    (
        "M3-rain-yes-leg-rounds-early",
        WEATHER,
        "            return float(o.current_probability or 0)\n    # Fallback: use highest probability",
        "            return float(round(float(o.current_probability or 0) * 100)) / 100\n    # Fallback: use highest probability",
        "The sharpest of the three, because its own FALLBACK branch stays "
        "correct: the rain card would band differently depending on whether the "
        'market happened to label its leg "Yes".',
    ),
    (
        "M4-printed-always-rounds-up",
        WEATHER,
        "    printed = rendered_percent(probability)",
        "    import math as _m\n    printed = _m.ceil(probability * 100)",
        "Wrong in the OTHER direction. A guard asserting only 'the number went "
        "up' passes; half-up is a rule, not a nudge.",
    ),
    (
        "M5-printed-double-scales",
        WEATHER,
        "    printed = rendered_percent(probability)",
        "    printed = rendered_percent(probability * 100)",
        "`rendered_percent` already multiplies by 100. Catches a guard that "
        "checks the helper is CALLED without checking what it returns.",
    ),
    (
        "M6-printed-truncates",
        WEATHER,
        "    printed = rendered_percent(probability)",
        "    printed = int(probability * 100)",
        "Whole numbers, still wrong. Truncation agrees with banker's on half "
        "the boundary and with nothing on the rest.",
    ),
    # ── the cross-source card ──────────────────────────────────────────────
    (
        "M7-kalshi-back-to-a-forced-decimal",
        CARD,
        "  const kalshiPct = formatProbabilityPercent(market.kalshi / 100);",
        "  const kalshiPct = `${market.kalshi.toFixed(1)}%`;",
        "THE DEFECT ITSELF on the politics side: `86.0%` for a value of 86.",
    ),
    (
        "M8-poly-back-to-a-forced-decimal",
        CARD,
        "  const polyPct = formatProbabilityPercent(market.poly / 100);",
        "  const polyPct = `${market.poly.toFixed(1)}%`;",
        "The other half of the pair. One side fixed and one not is worse than "
        "neither — the card's whole job is comparing the two.",
    ),
    (
        "M9-delta-rounded-from-the-served-float",
        CARD,
        "  const printedDelta = Math.abs(kalshiWhole - polyWhole);",
        "  const printedDelta = Math.round(delta);",
        "THE ARITHMETIC TRAP, and the most plausible wrong fix: `5% / 86%` "
        'captioned "Disagree by 82pp". Two of the eight live rows.',
    ),
    (
        "M10-merged-averaged-from-the-raw-pair",
        CARD,
        "  const printedMerged = Math.round((kalshiWhole + polyWhole) / 2);",
        "  const printedMerged = Math.round((market.kalshi + market.poly) / 2);",
        "The near-miss: 45 where the printed pair midpoints to 46. Inside any "
        "range check, so only an exact-midpoint assertion sees it.",
    ),
    (
        "M11-boundary-rule-dropped",
        CARD,
        "  const kalshiPct = formatProbabilityPercent(market.kalshi / 100);",
        "  const kalshiPct = `${renderedPercent(market.kalshi / 100) ?? 0}%`;",
        "Whole numbers, no `<1%` / `>99%`. A live 0.04% price prints `0%`, "
        "which a reader reads as impossible — on the surface that ranks by "
        "extremity and so selects for exactly these values.",
    ),
    (
        "M12-percent-handed-in-as-a-probability",
        CARD,
        "  const polyPct = formatProbabilityPercent(market.poly / 100);",
        "  const polyPct = formatProbabilityPercent(market.poly);",
        "The scale error the `/ 100` exists to prevent: every card prints "
        "`>99%` for Polymarket. Catches a guard that only greps for the call.",
    ),
    (
        "M13-badge-gate-moved-onto-the-printed-gap",
        CARD,
        "  const arbitrage = delta > 5;\n  const disagree = delta > 2;",
        "  const arbitrage = printedDelta > 5;\n  const disagree = printedDelta > 2;",
        "Silently re-curates which cards earn a badge — a display artifact "
        "deciding editorial emphasis. The gates are deliberately on the "
        "server's precision; this asserts that choice is load-bearing.",
    ),
]


def _run_pytest() -> tuple[bool, list[str]]:
    proc = subprocess.run(
        ["python3", "-m", "pytest", *PYTEST_TARGETS, "-q", "-p", "no:warnings"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip().splitlines()[-6:]


def _run_jest() -> tuple[bool, list[str]]:
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
    return proc.returncode == 0, out.strip().splitlines()[-6:]


def _run_oracle() -> tuple[bool, list[str]]:
    """Both runtimes. A mutant is killed if EITHER suite goes red."""
    py_ok, py_tail = _run_pytest()
    js_ok, js_tail = _run_jest()
    return py_ok and js_ok, py_tail + js_tail


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

    baseline_ok, baseline_tail = _run_oracle()
    if not baseline_ok:
        print("🔴 battery cannot run — the oracle is RED before any mutation:")
        print("\n".join(baseline_tail))
        return 2
    print(f"baseline: oracle GREEN ({len(MUTANTS)} mutants to run)\n")

    killed: list[str] = []
    survived: list[str] = []
    not_applied: list[str] = []

    backups = _backup_paths()
    backups[list(backups)[0]].parent.mkdir(parents=True, exist_ok=True)
    assert len(set(backups.values())) == len(backups), "backup paths collide"

    with guarded_targets(targets, backups, "uxp191-printed-percent"):
        for mutant_id, path, needle, replacement, _why in MUTANTS:
            original = path.read_text()
            count = original.count(needle)
            if count != 1:
                not_applied.append(f"{mutant_id} (needle matched {count}x)")
                print(f"  ⚠️  NOT APPLIED  {mutant_id} — needle matched {count}x")
                continue
            path.write_text(original.replace(needle, replacement))
            try:
                passed, _tail = _run_oracle()
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
