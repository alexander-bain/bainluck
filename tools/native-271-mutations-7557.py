#!/usr/bin/env python3
"""native/271 — mutation run for #7557 (a graded grid cell drawing the no-market glyph).

Eleven mutants. Restoring the shipped defect is one of them; the rest are the
ways this guard suite could stop meaning anything:

  * 1 is the defect as it shipped, reached through the only door that still
    compiles: `declaredRenderState` always nil, so every cell infers from the
    number and every graded rung goes back to `.open` + "—".
  * 2 and 3 are the two terminal states losing their chrome one at a time. A
    suite that asserts "not .open" on a mixed row passes when only one of them
    breaks.
  * 4 is the same bug pointed the other way, and the more dangerous one: a cell
    we have no market for rendered as ✕. It publishes a verdict we do not have.
  * 5 and 6 are the fail-closed clauses: an unrecognised state read as live, and
    the `clinched` alias dropped so a clinched cell degrades to unavailable.
    Both are byte-identical on TODAY's payload — the register sends neither
    today — which is exactly why they need assertions rather than a render.
  * 7 and 8 are "settled means settled" at the model: a terminal cell handing a
    renderer its stale price, and a settled column keeping its 24-hour delta.
    The card already ignores a clinched rung's probability, so 7 is invisible to
    a raster and visible only to an assertion.
  * 9 removes the [0,1] bound. Also byte-identical on today's payload.
  * 10 widens `isTerminal` to swallow `missing`, which is how a fail-closed
    vocabulary quietly becomes a guessing one.
  * 11 is the VIEW ignoring a correct model: the adapter reading the raw
    `mergedProbability` again. It compiles, it passes anything asserting on
    `renderState`, and the reader sees the defect.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-271-mutations-7557.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
STATE = ROOT / "Bain Luck/Utilities/GridCellRenderState.swift"
CARD = ROOT / "Bain Luck/Components/LadderCardView.swift"
GUARD = WORKTREE / "tools/reserved-sim-guard.sh"


def disposable_sim():
    """A device this run may install to, from the rig's shared picker.

    🪤 NOT A HARD-CODED UDID. Two simulators hold Alex's signed-in account and
    both are named `iPhone 17`, so a destination written by NAME resolves to one
    of them. `tools/reserved-sim-guard.sh` is the authority on which devices are
    protected, and asking it is the only spelling that stays correct when the
    list changes.
    """
    pick = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_default_shoot_sim'],
                          capture_output=True, text=True)
    udid = (pick.stdout or "").strip().splitlines()
    udid = udid[-1].strip() if udid else ""
    if not udid:
        sys.exit("FATAL: no disposable iPhone simulator on this machine")
    check = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_is_reserved_sim "{udid}"'])
    if check.returncode == 0:
        sys.exit(f"FATAL: the picker returned RESERVED device {udid} — refusing to install")
    return udid


SIM = disposable_sim()

# ── the normaliser ──────────────────────────────────────────────────────────

DECLARED_WIRED = '''    var declaredRenderState: GridCellRenderState? {
        guard let state else { return nil }'''
DECLARED_BLIND = '''    var declaredRenderState: GridCellRenderState? {
        if true { return nil }
        guard let state else { return nil }'''

ALIAS_WIRED = '''        if state == "clinched" { return .won }'''
ALIAS_DROPPED = '''        if state == "clinched" { return .unavailable }'''

UNKNOWN_WIRED = '''        if state == "clinched" { return .won }
        return .unavailable
    }'''
UNKNOWN_IS_LIVE = '''        if state == "clinched" { return .won }
        return .live
    }'''

PROB_WIRED = '''        renderState == .live ? usableProbability : nil'''
PROB_ALWAYS = '''        usableProbability'''

TREND_WIRED = '''        guard renderState == .live, let trend = trend24H, trend.isFinite else { return nil }'''
TREND_UNGATED = '''        guard let trend = trend24H, trend.isFinite else { return nil }'''

BOUND_WIRED = '''        guard let value = mergedProbability, value.isFinite, value >= 0, value <= 1 else {'''
BOUND_REMOVED = '''        guard let value = mergedProbability, value.isFinite else {'''

TERMINAL_WIRED = '''    var isTerminal: Bool { self == .won || self == .eliminated }'''
TERMINAL_WIDE = '''    var isTerminal: Bool { self == .won || self == .eliminated || self == .missing }'''

# ── the adapter ─────────────────────────────────────────────────────────────

WON_WIRED = '''        case .won:                          self = .clinched'''
WON_OPEN = '''        case .won:                          self = .open'''

ELIM_WIRED = '''        case .eliminated:                   self = .eliminated'''
ELIM_OPEN = '''        case .eliminated:                   self = .open'''

EMPTY_WIRED = '''        case .live, .missing, .unavailable: self = .open'''
EMPTY_IS_A_VERDICT = '''        case .live:                         self = .open
        case .missing, .unavailable:        self = .eliminated'''

ADAPTER_WIRED = '''                probability: cell?.publishedProbability,'''
ADAPTER_RAW = '''                probability: cell?.mergedProbability,'''

# name, file, find, replace, runner, why-a-survivor-matters
MUTANTS = [
    ("1-the-declared-state-is-never-read", STATE, DECLARED_WIRED, DECLARED_BLIND, "swift",
     "THE SHIPPED DEFECT. Every graded cell falls back to the number, the number "
     "is null by contract, and 53 decided MLB rungs print the no-market glyph"),

    ("2-a-clinched-cell-loses-its-tick", CARD, WON_WIRED, WON_OPEN, "swift",
     "half the defect. A suite that only checks a mixed row's 'not all open' "
     "passes while Milwaukee's clinched division is blank again"),

    ("3-an-eliminated-cell-loses-its-cross", CARD, ELIM_WIRED, ELIM_OPEN, "swift",
     "the other half, and the half no single-specimen test sees"),

    ("4-a-cell-with-no-market-is-drawn-as-eliminated", CARD, EMPTY_WIRED, EMPTY_IS_A_VERDICT, "swift",
     "the bug pointed the other way and the worse one: 'we have no market' "
     "rendered as 'this cannot happen'. A verdict we do not have"),

    ("5-an-unrecognised-state-is-read-as-live", STATE, UNKNOWN_WIRED, UNKNOWN_IS_LIVE, "swift",
     "the fail-closed clause. Byte-identical on today's payload — the register "
     "sends no unknown state — and a published price for a cell we cannot read "
     "the day it sends one"),

    ("6-the-clinched-alias-is-dropped", STATE, ALIAS_WIRED, ALIAS_DROPPED, "both",
     "a producer using the DISPLAY word silently degrades to unavailable, which "
     "renders empty: this issue again, arriving by a different door"),

    ("7-a-settled-cell-publishes-its-price", STATE, PROB_WIRED, PROB_ALWAYS, "swift",
     "settled means settled, at the model. The card ignores a clinched rung's "
     "probability, so no raster can see this — only an assertion can"),

    ("8-a-settled-column-keeps-its-24h-delta", STATE, TREND_WIRED, TREND_UNGATED, "swift",
     "a move printed beside a market that has stopped trading. WSH, COL and CIN "
     "in the LOOK are the rows that would carry it"),

    ("9-the-probability-bound-is-removed", STATE, BOUND_WIRED, BOUND_REMOVED, "swift",
     "byte-identical on today's payload and a 140% bar off the end of the card "
     "on a bad one — the mutant that proves the suite tests the rule"),

    ("10-missing-is-treated-as-terminal", STATE, TERMINAL_WIRED, TERMINAL_WIDE, "swift",
     "how a fail-closed vocabulary becomes a guessing one: the absence of a "
     "market reclassified as a graded outcome"),

    ("11-the-adapter-reads-the-raw-probability-again", CARD, ADAPTER_WIRED, ADAPTER_RAW, "swift",
     "a correct model and an adapter that bypasses it. Every assertion on "
     "`renderState` passes; the rung carries the number anyway"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600`. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/GridCellStateReachesTheRung7557Tests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]

JEST = ["npx", "jest", "--testPathPatterns", "gridCellStateParity7557"]


def run_swift():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out)


def run_jest():
    r = subprocess.run(JEST, capture_output=True, text=True,
                       cwd=str(WORKTREE / "frontend"))
    out = r.stdout + r.stderr
    # A suite that never ran is not a pass and not a kill — it is a broken rig.
    return r.returncode, ("Tests:" in out)


def run(runner):
    """Returns (red, reached) — `reached` is False when the check never ran at all."""
    if runner == "swift":
        return run_swift()
    if runner == "jest":
        return run_jest()
    swift_code, swift_ran = run_swift()
    jest_code, jest_ran = run_jest()
    return (swift_code or jest_code), (swift_ran and jest_ran)


_IN_FLIGHT = {}


def _restore_all(*_):
    for path, original in list(_IN_FLIGHT.items()):
        try:
            path.write_text(original)
            print(f"  restored {path.name} on exit")
        except Exception as e:      # noqa: BLE001 — best effort on the way down
            print(f"  !! COULD NOT RESTORE {path}: {e}\n     git checkout it BY HAND before committing")
        _IN_FLIGHT.pop(path, None)


atexit.register(_restore_all)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda s, f: (_restore_all(), sys.exit(128 + s)))


def main():
    if "--list" in sys.argv:
        for n, f, _, _, runner, _ in MUTANTS:
            print(f"  {n}  ({f.name}, {runner})")
        return 0

    print("baseline (unmutated tree)")
    code, reached = run("both")
    if code != 0 or not reached:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, runner, why in MUTANTS:
        original = path.read_text()
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
            _IN_FLIGHT[path] = original
            path.write_text(original.replace(find, repl, 1))
            code, reached = run(runner)
            if code != 0:
                how = "assertions" if reached else "COMPILE/RIG ONLY"
                print(f"  killed   {name}  [{runner}: {how}]")
                if not reached:
                    print("           ^ a compile kill does not prove the suite would catch it")
                killed.append(name)
            else:
                print(f"  SURVIVED {name}\n           {why}")
                survived.append((name, "SURVIVED"))
        finally:
            path.write_text(original)
            _IN_FLIGHT.pop(path, None)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    for n, s in survived:
        print(f"  {s}: {n}")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect CLEAN — this ship is committed):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
