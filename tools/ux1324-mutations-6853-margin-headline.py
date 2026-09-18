# ux1324-mutations-6853-margin-headline.py — the #6853 guard's own battery.
# Run from the repo root; restores the file in a `finally`.
import subprocess, re

F = "frontend/components/MarketMapSection.tsx"
ORIG = open(F).read()

BIND = """    const headline = isDone || favoredProb == null
      ? ""
      : `${favoredAbbr} ${formatProbability(favoredProb)}`;"""

MUTANTS = {
    # The code as it shipped before this fix.
    "raw-round": BIND.replace("${formatProbability(favoredProb)}",
                              "${Math.round(favoredProb * 100)}%"),
    # "Never print 100" satisfied by a cap — prints a number the value is not on.
    "cap-at-99": BIND.replace("${formatProbability(favoredProb)}",
                              "${Math.min(99, Math.round(favoredProb * 100))}%"),
    # Satisfied by deleting the headline: honest about 100, silent about 73.
    "headline-dropped": BIND.replace(': `${favoredAbbr} ${formatProbability(favoredProb)}`;',
                                     ': "";'),
    # The percent survives, the team name does not.
    "abbr-dropped": BIND.replace("${favoredAbbr} ${formatProbability(favoredProb)}",
                                 "${formatProbability(favoredProb)}"),
    # The wrong side named.
    "favourite-flipped": BIND.replace("const headline", "const headline")
    and BIND.replace("${favoredAbbr}", "${favoredAbbr === 'BUF' ? 'DET' : 'BUF'}"),
    # #5206's arm removed: a settled card grows a third voice.
    "isDone-dropped": BIND.replace("isDone || favoredProb == null", "favoredProb == null"),
}


def run():
    r = subprocess.run(
        ["npx", "jest", "--testPathPatterns=marginMapNeverClaimsCertainty6853"],
        cwd="frontend", capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    m = re.search(r"Tests:\s+(?:(\d+) failed, )?(\d+) passed", out)
    # WHICH ARM FIRED, not just how many. A pass/fail COUNT is a coarse
    # signature: `raw-round`, `cap-at-99` and `isDone-dropped` all read
    # "1 failed, 3 passed" while dying on two different clauses, and a battery
    # that counted only the numbers would report them as one signature and
    # overstate how much of the guard is load-bearing.
    arms = sorted({a.strip() for a in re.findall(r"●[^\n›]*›\s*(.+)", out)})
    return r.returncode, (m.group(0) if m else "?"), arms


try:
    assert BIND in ORIG, "anchor not found — the binding moved"
    caught, sigs = 0, {}
    for name, repl in MUTANTS.items():
        assert repl != BIND, f"{name}: no-op mutant"
        open(F, "w").write(ORIG.replace(BIND, repl))
        code, summary, arms = run()
        caught += code != 0
        sigs[tuple(arms)] = sigs.get(tuple(arms), 0) + 1
        print(f"{name:20} {'CAUGHT' if code else 'SURVIVED':9} exit={code}  {summary}")
        for a in arms:
            print(f"{'':20}   killed by: {a}")
    open(F, "w").write(ORIG)
    code, summary, arms = run()
    print(f"{'CONTROL (unmutated)':20} {'GREEN' if code == 0 else 'RED':9} exit={code}  {summary}")
    print(f"\n{caught}/{len(MUTANTS)} caught, {len(sigs)} distinct ARM-SETS, "
          f"control {'survived' if code == 0 else 'FAILED'}")
finally:
    open(F, "w").write(ORIG)
