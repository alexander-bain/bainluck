# ux1324-mutations-6844-two-sided-duel.py — the #6844 guard's own battery.
# Run from the repo root; edits `TwoSidedTimeline.tsx` in place and restores it
# in a `finally`, so a Ctrl-C cannot leave a mutant on disk.
import subprocess, re

F = "frontend/components/event/TwoSidedTimeline.tsx"
ORIG = open(F).read()

BIND = "  const [aRendered, bRendered] = renderedDuelPercents(a.probability, b.probability);"
A_SITE = "{formatProbability(a.probability, { rendered: aRendered })}"
B_SITE = "{formatProbability(b.probability, { rendered: bRendered })}"

MUTANTS = {
    # The #6778 shape: only one side reads the pair. Prints the specimen's own
    # 68/33 again and satisfies every clause that does not check the SUM.
    "half-wired-b": [(B_SITE, "{formatProbability(b.probability)}")],
    # Normalize unconditionally, BYPASSING the complement band. The first draft of
    # this mutant swapped in `renderedCardPercents` and survived — because that
    # helper carries the same `isComplementPair` guard, so it was not the mutant
    # its name claimed. A band bypass is: it turns the independent 0.60/0.30 pair
    # into 67/33 and invents ten points of probability.
    "band-bypassed": [
        (BIND,
         "  const _t = (a.probability ?? 0) + (b.probability ?? 0);\n"
         "  const _lead = a.probability != null && _t > 0 ? Math.round(((a.probability / _t) * 1000) / 10) : null;\n"
         "  const [aRendered, bRendered] = _lead != null ? [_lead, 100 - _lead] : [null, null];"),
    ],
    # Print the integer instead of passing it as the option: loses "-" and both
    # boundary rules, which is the whole reason the fix is an option.
    "printed-directly": [
        (A_SITE, "{`${aRendered}%`}"),
        (B_SITE, "{`${bRendered}%`}"),
    ],
    # The two integers swapped.
    "sides-swapped": [
        (A_SITE, "{formatProbability(a.probability, { rendered: bRendered })}"),
        (B_SITE, "{formatProbability(b.probability, { rendered: aRendered })}"),
    ],
    # EXPECTED SURVIVOR, recorded rather than hidden: `fieldOrder` sorts the pair
    # descending, so `a` is always the favourite and the card-level helper is
    # arithmetically identical here. The duel helper is still the right call —
    # it is the named rule for two sides of ONE question and it does not depend
    # on the sort staying the way it is — but no test can tell them apart, and a
    # battery that pretended otherwise would be the lie.
    "card-helper-instead-of-duel": [
        (BIND, "  const [aRendered, bRendered] = renderedCardPercents([a.probability, b.probability]);"),
        ('import { renderedDuelPercents } from "@/lib/renderedPercent";',
         'import { renderedCardPercents } from "@/lib/renderedPercent";'),
    ],
}


def run():
    r = subprocess.run(
        ["npx", "jest", "--testPathPatterns=twoSidedBoutSumsToOneHundred6844"],
        cwd="frontend", capture_output=True, text=True,
    )
    m = re.search(r"Tests:\s+(?:(\d+) failed, )?(\d+) passed", r.stdout + r.stderr)
    return r.returncode, (m.group(0) if m else "?")


try:
    caught, sigs = 0, {}
    for name, edits in MUTANTS.items():
        src = ORIG
        for old, new in edits:
            assert old in src, f"{name}: anchor not found"
            src = src.replace(old, new)
        assert src != ORIG, f"{name}: no-op mutant"
        open(F, "w").write(src)
        code, summary = run()
        caught += code != 0
        sigs[summary] = sigs.get(summary, 0) + 1
        print(f"{name:30} {'CAUGHT' if code else 'SURVIVED':9} exit={code}  {summary}")
    open(F, "w").write(ORIG)
    code, summary = run()
    print(f"{'CONTROL (unmutated)':30} {'GREEN' if code == 0 else 'RED':9} exit={code}  {summary}")
    print(f"\n{caught}/{len(MUTANTS)} caught, {len(sigs)} distinct signatures, "
          f"control {'survived' if code == 0 else 'FAILED'}")
finally:
    open(F, "w").write(ORIG)
