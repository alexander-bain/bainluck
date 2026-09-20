#!/usr/bin/env python3
"""native/260 — mutation run for #7350 (a sparse window keeps its range controls).

Alex's TestFlight 1.0 (16), futures 59165099: nine observations reaching back to
August 18, exactly one inside seven days, and the card showed "Limited price
history available" with NO CHIPS UNDER IT. The eight older observations were in
the response the view was holding and there was no way to ask for them.

The ship has two halves and they fail in different ways, so both are mutated:

  * RULE mutants — `cardBody`, `sparseCopy`, `windowWord`, and the counting that
    feeds them. These are pure static functions and a unit suite is exactly the
    right instrument.

  * REACHABILITY mutants — 🔴 THE ONES THAT MATTER. The defect was never in a
    rule. It was WHERE `controlBar` sat in a `@ViewBuilder`, and a body returning
    an opaque type cannot be called. A mutant that puts the chips back inside the
    plot branch, or drops the hint's `Text` while still computing the string,
    leaves a perfect rule suite entirely green and is fully user-visible. Same
    shape as #7077's seam and #4624's.

So a mutant declares which instrument should kill it, and the runner escalates:
every mutant meets the UNIT suite first, and one flagged `journey` that survived
it is then run against the tap-driven journey on the simulator. A mutant killed
only by the journey is not a weaker kill — it is the evidence that the journey is
load-bearing rather than decorative.

A mutant that SURVIVES BOTH is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-260-mutations-7350.py [--list] [--no-journey]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
CHART = ROOT / "Bain Luck/Components/EvolutionChartView.swift"
PROJECT = ROOT / "Bain Luck.xcodeproj"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"
SPM = pathlib.Path.home() / (
    "Library/Developer/Xcode/DerivedData/"
    "Bain_Luck-cwkxplfeuucvrvbplvqqlcgmpcgx/SourcePackages")

SWIFT_FLAGS = "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"


def _xcb(scheme, only):
    cmd = ["xcodebuild", "test", "-project", str(PROJECT), "-scheme", scheme,
           "-destination", f"id={SIM}"]
    if SPM.is_dir():
        cmd += ["-clonedSourcePackagesDirPath", str(SPM)]
    return cmd + [f"-only-testing:{only}", SWIFT_FLAGS]


UNIT = _xcb("Bain Luck", "BainLuckTests/ASparseWindowKeepsItsRangeControls7350Tests")
JOURNEY = _xcb(
    "BainLuckUITests",
    "BainLuckUITests/AReaderCanReachOlderPricesFromASparseChart7350Tests")

# ─── the pre-fix body, verbatim: the chips lived inside the "there is a chart"
#     branch and the empty state was one sentence for two different facts.
SPARSE_KEEPS_CHIPS = """                case .sparse(let copy):
                    VStack(spacing: 0) {
                        controlBar
                        emptyState(copy.note, hint: copy.hint)
                    }"""
CHIPS_HIDDEN_AGAIN = """                case .sparse(let copy):
                    VStack(spacing: 0) {
                        emptyState(copy.note, hint: copy.hint)
                    }"""
ONE_SENTENCE_FOR_TWO_FACTS = """                case .sparse(let copy):
                    VStack(spacing: 0) {
                        controlBar
                        emptyState("Limited price history available")
                    }"""

HINT_IS_DRAWN = """            if let hint {
                Text(hint)"""
# Computes the correct string and draws nothing. Every pure test stays green.
HINT_COMPUTED_NOT_DRAWN = """            if let hint, false {
                Text(hint)"""

# The cadence recited from the poll schedule, as it stood on build 16.
CADENCE_PROMISE = """            if let hint {
                Text("Prices update every 1-2 hours for this market")"""

WINDOW_COUNT_RESPECTS_CUTOFF = """            if let cutoff, date < cutoff { return }
            total += 1"""
WINDOW_COUNT_IGNORES_CUTOFF = """            _ = cutoff
            total += 1"""

#   name, find, replace, why-a-survivor-matters, instrument
MUTANTS = [
    # ═══ reachability — the defect's own shape ═══
    ("chips-hidden-in-the-sparse-state", SPARSE_KEEPS_CHIPS, CHIPS_HIDDEN_AGAIN,
     "THIS IS #7350 ITSELF. The card counts eight older prices and gives the "
     "reader no way to reach them — exactly Alex's photograph.", "unit"),
    ("empty-state-back-to-one-sentence", SPARSE_KEEPS_CHIPS, ONE_SENTENCE_FOR_TWO_FACTS,
     "'Limited price history available' printed over both an empty window and an "
     "empty history — gotcha #53, two facts wearing one sentence.", "unit"),
    ("hint-computed-but-never-drawn", HINT_IS_DRAWN, HINT_COMPUTED_NOT_DRAWN,
     "the string is right and it is not on the phone. No pure test can see this; "
     "if the journey does not kill it, nothing does.", "journey"),
    ("cadence-promise-restored", HINT_IS_DRAWN, CADENCE_PROMISE,
     "a poll schedule recited to the reader as a promise, over nine observations "
     "spread across a month.", "unit"),

    # ═══ the counting that feeds the sentence ═══
    ("window-count-ignores-the-cutoff",
     WINDOW_COUNT_RESPECTS_CUTOFF, WINDOW_COUNT_IGNORES_CUTOFF,
     "every observation counts as in-window, so 'earlier prices' reads 0 and the "
     "specimen loses its way out. The unit suite passes values in, so only a "
     "journey against the real response can see this.", "journey"),

    # ═══ the boundary between a sentence and a plot ═══
    ("sparse-boundary-one-point-plots",
     "guard windowPoints < 2 else { return .plot }",
     "guard windowPoints < 1 else { return .plot }",
     "a single price drawn as a line — the invented interval #7077 was about.", "unit"),
    ("sparse-boundary-swallows-real-charts",
     "guard windowPoints < 2 else { return .plot }",
     "guard windowPoints < 3 else { return .plot }",
     "a genuine two-point chart replaced by a sentence.", "unit"),

    # ═══ the sentence's arithmetic ═══
    ("earlier-guard-off-by-one",
     "guard earlier > 0 else {", "guard earlier >= 0 else {",
     "a market whose every price is inside the window is told to look elsewhere.", "unit"),
    ("zero-history-sent-on-an-errand",
     'guard seen > 0 else { return SparseCopy(note: "No price history yet", hint: nil) }',
     'guard seen > 0 else { return SparseCopy(note: "No price history yet", hint: "Try a longer range") }',
     "a market with no prices at all tells the reader to keep looking.", "unit"),
    ("window-count-not-clamped-to-total",
     "let inWindow = max(0, min(windowInstants, seen))",
     "let inWindow = max(0, windowInstants)",
     "a negative 'earlier' count manufactures prices that do not exist.", "unit"),
    # The first run of this suite carried `max(0, totalInstants)` -> `totalInstants`
    # here and it SURVIVED. It was not a hole: `guard seen > 0` already sends every
    # non-positive total to the honest sentence, so the two forms agree on all
    # 10,201 input pairs in -50...50 — a provably EQUIVALENT mutant, i.e. a second
    # copy of a rule the function already had. The clamp was deleted rather than
    # excused, and the mutant replaced by one that moves an observable value.
    ("negative-total-read-as-positive",
     "let seen = totalInstants", "let seen = abs(totalInstants)",
     "a nonsense count is printed as real history rather than degraded to the "
     "honest sentence.", "unit"),
    ("singular-and-plural-collapsed",
     'let earlierPhrase = earlier == 1 ? "one earlier price" : "\\(earlier) earlier prices"',
     'let earlierPhrase = "\\(earlier) earlier prices"',
     "'1 earlier prices' — the sentence reads as a template.", "unit"),
    ("in-window-branch-collapsed",
     'case 0: windowPhrase = "No prices \\(windowWord)"\n        case 1: windowPhrase = "One price \\(windowWord)"',
     'case 0: windowPhrase = "No prices \\(windowWord)"\n        case 1: windowPhrase = "No prices \\(windowWord)"',
     "the specimen's one visible price is denied.", "unit"),

    # ═══ the window count is a COUNT, not a ternary ═══
    # `cardBody` gates on POINTS and this sentence counts INSTANTS; a timeline
    # entry holding only `Field` or only outcomes past `topFilter` is an instant
    # with no point, so a sparse card CAN hold two or more. The first cut read
    # both of these branches as "one or none" and lied on every such window.
    ("several-prices-called-one",
     'default: windowPhrase = "\\(inWindow) prices \\(windowWord)"',
     'default: windowPhrase = "One price \\(windowWord)"',
     "three observations reported to the reader as one.", "unit"),
    ("full-window-read-as-no-history",
     'note: inWindow == 1\n                    ? "Only one price seen so far"\n                    : "\\(inWindow) prices seen so far"',
     'note: "No price history yet"',
     "'No price history yet' printed over a response holding nine prices — the "
     "exact gotcha #53 sentence this ship exists to stop.", "unit"),

    # ═══ the window's own name ═══
    ("window-word-borrows-the-chip",
     'case .week: return "in the last 7 days"', 'case .week: return "7d"',
     "'No prices 7d' — the borrowed-chip vocabulary #7077 fixed.", "unit"),
    ("widest-window-names-itself",
     'case .season: return "in this range"', 'case .season: return "6M"',
     "'6M' reads as a chip, not as a phrase inside a sentence.", "unit"),
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


_IN_FLIGHT = {}


def _restore_all(*_):
    for path, original in list(_IN_FLIGHT.items()):
        try:
            path.write_text(original)
            print(f"  restored {path.name} on exit")
        except Exception as e:      # noqa: BLE001 — best effort on the way down
            print(f"  !! COULD NOT RESTORE {path}: {e}\n"
                  f"     git checkout it BY HAND before committing")
        _IN_FLIGHT.pop(path, None)


atexit.register(_restore_all)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda s, f: (_restore_all(), sys.exit(128 + s)))


def main():
    if "--list" in sys.argv:
        for n, _, _, _, inst in MUTANTS:
            print(f"  [{inst:7}] {n}")
        return 0
    allow_journey = "--no-journey" not in sys.argv

    # `--only <name>` re-grades one mutant. A full pass costs ~10 minutes PER
    # mutant (each one edits the app module, so every run is a full recompile),
    # and re-running fifteen to re-read one is how a suite stops being run at
    # all. The scoped verdict says how many of the whole suite it covered.
    scope = MUTANTS
    if "--only" in sys.argv:
        wanted = sys.argv[sys.argv.index("--only") + 1]
        scope = [m for m in MUTANTS if m[0] == wanted]
        if not scope:
            print(f"no mutant named {wanted!r} — run --list")
            return 2

    print("baseline (unmutated tree)")
    code, _, _ = run(UNIT)
    if code != 0:
        print(f"  UNIT BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  unit baseline GREEN")
    if allow_journey:
        code, _, _ = run(JOURNEY)
        if code != 0:
            print(f"  JOURNEY BASELINE IS RED (exit {code}) — a journey-flagged mutant "
                  f"cannot be graded against a red baseline")
            return 2
        print("  journey baseline GREEN")
    print()

    killed, survived = [], []
    for name, find, repl, why, instrument in scope:
        original = CHART.read_text()
        # A refused patch prints a green indistinguishable from an unkillable
        # mutant, so refusal is reported as a NON-result, never a pass.
        if find not in original:
            print(f"  REFUSED  {name} — anchor not found; the mutant patched NOTHING")
            survived.append((name, "REFUSED"))
            continue
        if original.count(find) != 1:
            print(f"  REFUSED  {name} — anchor occurs {original.count(find)}x, not unique")
            survived.append((name, "REFUSED-AMBIGUOUS"))
            continue
        try:
            _IN_FLIGHT[CHART] = original
            CHART.write_text(original.replace(find, repl, 1))

            code, compiled, _ = run(UNIT)
            if code != 0:
                how = "unit" if compiled else "COMPILE ONLY"
                print(f"  killed   {name}  [{how}]")
                if not compiled:
                    print("           ^ a compile kill does not prove the suite would "
                          "catch it")
                killed.append(name)
                continue

            # Survived the unit suite. If the defect is a seam the unit suite
            # cannot reach BY CONSTRUCTION, that is expected — escalate.
            if instrument == "journey" and allow_journey:
                code, compiled, _ = run(JOURNEY)
                if code != 0:
                    print(f"  killed   {name}  [journey — invisible to the unit suite]")
                    killed.append(name)
                    continue
                print(f"  SURVIVED {name}  [unit AND journey]\n           {why}")
                survived.append((name, "SURVIVED-BOTH"))
            elif instrument == "journey":
                print(f"  SKIPPED  {name} — journey-only mutant, --no-journey given")
                survived.append((name, "NOT-GRADED"))
            else:
                print(f"  SURVIVED {name}\n           {why}")
                survived.append((name, "SURVIVED"))
        finally:
            CHART.write_text(original)
            _IN_FLIGHT.pop(CHART, None)

    covered = "" if len(scope) == len(MUTANTS) else f"  (scoped run — {len(scope)} of {len(MUTANTS)})"
    print(f"\n{len(killed)}/{len(scope)} killed{covered}")
    for n, s in survived:
        print(f"  {s}: {n}")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
