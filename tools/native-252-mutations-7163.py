#!/usr/bin/env python3
"""native/252 — mutation battery for #7163's guards, on BOTH clients.

#7163 gives `short` the particles a person's surname carries, gated on the
sport. The risk this battery is aimed at is not "does the fix work" — ux
measured that over the production name population before the browser half
shipped — but "would the guards notice if it stopped working, or if it started
reaching the names it must never touch". Every mutant below either restores the
defect, opens the gate onto clubs, or breaks an assumption the walk rests on,
and must turn at least one named test RED.

The battery runs on BOTH clients because the ship is one rule with two
implementations: a Swift mutant runs `ParticledSurname7163Tests`, a TypeScript
mutant runs the cross-client parity suite. A guard on one client is a guard on
one client (standing notice 33).

One mutant deliberately edits the SWIFT file and grades on JEST — that is the
out-of-source set comparison, and it is the only mutant that can prove the
parity guard actually reads the iPhone's copy rather than its own idea of it.

Two CONTROLS, one per runner, change nothing and must stay GREEN — a battery
that reds on everything, a broken harness included, reads as success.

    tools/native-252-mutations-7163.py            # the whole battery
    tools/native-252-mutations-7163.py --list     # print the mutants, run nothing
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
RULE = REPO / "ios/Bain Luck/Bain Luck/Utilities/TeamShortName.swift"
TITLE = REPO / "ios/Bain Luck/Bain Luck/Utilities/EventNavTitle.swift"
WEB = REPO / "frontend/lib/teamShortName.ts"

SWIFT_CLASS = "BainLuckTests/ParticledSurname7163Tests"
JEST_PATTERN = "teamDesignatorParityAcrossClients"
# iPhone 17 Pro, disposable. NOT DD0DC456 or 76D961F0 — those hold Alex's
# signed-in account and the fleet guard refuses them by name.
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

SWIFT, JEST = "swift", "jest"

# (name, runner, file, old, new, why)
MUTANTS = [
    (
        "delete the walk (#7163 itself)",
        SWIFT,
        RULE,
        "        if namesAPerson(sportKey: sportKey) {\n"
        "            let start = particledSurnameStart(parts)\n"
        "            if start < parts.count - 1 {\n"
        "                return parts[start...].joined(separator: \" \")\n"
        "            }\n"
        "        }\n",
        "",
        "the defect restored verbatim: de Minaur is Minaur again on every "
        "surface that threads its sport",
    ),
    (
        "open the gate for EVERY sport",
        SWIFT,
        RULE,
        "        if namesAPerson(sportKey: sportKey) {\n"
        "            let start = particledSurnameStart(parts)",
        "        if true {\n"
        "            let start = particledSurnameStart(parts)",
        "the club population reached: Tigres de la UANL reads 'de la UANL' and "
        "ux's 2,797 soccer names move. The half of this ship that is a GATE, "
        "not a rule, is only visible in this direction",
    ),
    (
        "take one step instead of walking",
        SWIFT,
        RULE,
        "        while start > 0, nameParticles.contains(bareToken(words[start - 1]).lowercased()) {",
        "        if start > 0, nameParticles.contains(bareToken(words[start - 1]).lowercased()) {",
        "stacked particles stop being crossed: 'Botic van de Zandschulp' hands "
        "back 'de Zandschulp', the same defect one token along",
    ),
    (
        "match the particle case-SENSITIVELY",
        SWIFT,
        RULE,
        "        while start > 0, nameParticles.contains(bareToken(words[start - 1]).lowercased()) {",
        "        while start > 0, nameParticles.contains(bareToken(words[start - 1])) {",
        "production stores both spellings, so half the population silently "
        "keeps the defect — 'Van de Zandschulp' truncates to 'de Zandschulp'",
    ),
    (
        "run the walk ABOVE the designator refusal",
        SWIFT,
        RULE,
        "        if isNonDistinctiveToken(last) { return parts.joined(separator: \" \") }",
        "        if namesAPerson(sportKey: sportKey) {\n"
        "            let s = particledSurnameStart(parts)\n"
        "            if s < parts.count - 1 { return parts[s...].joined(separator: \" \") }\n"
        "        }\n"
        "        if isNonDistinctiveToken(last) { return parts.joined(separator: \" \") }",
        "the two rules compose into a label neither would produce: 'Juan de la "
        "Cruz III' becomes 'de la Cruz III', a generational suffix hung off a "
        "particle. ORDER, not presence, is the claim",
    ),
    (
        "let the walk run off the front of the name",
        SWIFT,
        RULE,
        "        while start > 0, nameParticles.contains(",
        "        while start >= 0, nameParticles.contains(",
        "a name that is ALL particles indexes words[-1]; the bound is the only "
        "thing standing between the walk and a crash on a one-word input",
    ),
    (
        "drop one particle from the iPhone's set",
        SWIFT,
        RULE,
        '        "dos",   // 2   dos Santos',
        "",
        "an entry silently removed: 'Joao dos Santos' is 'Santos' again, and "
        "the two clients' sets are one apart",
    ),
    (
        "stop the PAIR carrying the matchup's sport",
        SWIFT,
        RULE,
        "        let a = served(awayServed) ?? short(away, sportKey: sportKey)",
        "        let a = served(awayServed) ?? short(away)",
        "one tennis match drawn with one side on the person rule and the other "
        "on the club rule — the #4624 failure, relocated to the label",
    ),
    (
        "stop GROWTH carrying the sport",
        SWIFT,
        RULE,
        "                    short(away, sportKey: sportKey).split(separator: \" \").filter { !$0.isEmpty }.count,\n"
        "                    short(home, sportKey: sportKey).split(separator: \" \").filter { !$0.isEmpty }.count)",
        "                    short(away).split(separator: \" \").filter { !$0.isEmpty }.count,\n"
        "                    short(home).split(separator: \" \").filter { !$0.isEmpty }.count)",
        "growth starts one word narrower than the label it is growing FROM, so "
        "a collided pair is handed back the bare surnames this fix just widened",
    ),
    (
        "stop the NAV TITLE passing its own sport",
        SWIFT,
        TITLE,
        "            away: away, home: home, awayServed: awayServed, homeServed: homeServed,\n"
        "            sportKey: sportKey\n"
        "        )\n"
        "        return \"\\(labels.away) vs \\(labels.home)\"",
        "            away: away, home: home, awayServed: awayServed, homeServed: homeServed\n"
        "        )\n"
        "        return \"\\(labels.away) vs \\(labels.home)\"",
        "the rule is right and the view never asks it — the shape of the "
        "original defect, and the reason the wiring is pinned on the one "
        "reader-facing entry point that is static",
    ),
    (
        "CONTROL (swift): change nothing",
        SWIFT,
        RULE,
        "",
        "",
        "the xcodebuild harness must be capable of GREEN",
    ),
    (
        "web: drop one particle from the browser's set",
        JEST,
        WEB,
        '  "dos", // 2   dos Santos\n',
        "",
        "the browser's half of the same removal, which the out-of-source set "
        "comparison must see from the other side",
    ),
    (
        "web: take one step instead of walking",
        JEST,
        WEB,
        "  while (\n    start > 0 &&",
        "  if (\n    start > 0 &&",
        "the browser stops crossing stacked particles while the iPhone keeps "
        "doing it — a divergence no single-client suite can see",
    ),
    (
        "web: run the walk above the designator refusal",
        JEST,
        WEB,
        "  if (isNonDistinctiveTrailingWord(words[words.length - 1])) return full;\n"
        "  // #7163 — a person's surname carries its particles with it. Gated on the\n"
        "  // sport, so a club can never reach this: see `NAME_PARTICLES` for the club\n"
        "  // names the ungated form would have broken.\n"
        "  if (namesAPerson(sportKey)) {\n"
        "    const start = particledSurnameStart(words);\n"
        "    if (start < words.length - 1) return words.slice(start).join(\" \");\n"
        "  }\n",
        "  if (namesAPerson(sportKey)) {\n"
        "    const start = particledSurnameStart(words);\n"
        "    if (start < words.length - 1) return words.slice(start).join(\" \");\n"
        "  }\n"
        "  if (isNonDistinctiveTrailingWord(words[words.length - 1])) return full;\n",
        "the browser's order broken on its own, and a MOVE rather than a delete "
        "— the first draft of this mutant deleted the refusal, which reds for a "
        "reason that is not the order claim and flattered both suites",
    ),
    (
        "swift set edited, graded on JEST",
        JEST,
        RULE,
        '        "abu",\n',
        "",
        "THE ONLY MUTANT THAT PROVES THE PARITY GUARD READS THE IPHONE'S FILE. "
        "Every other jest mutant edits the browser, which a guard comparing a "
        "transcribed copy against itself would also catch",
    ),
    (
        "CONTROL (jest): change nothing",
        JEST,
        WEB,
        "",
        "",
        "the jest harness must be capable of GREEN",
    ),
]


def run_swift() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(REPO / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", f"platform=iOS Simulator,id={SIM}",
            "-disableAutomaticPackageResolution",
            "-only-testing:" + SWIFT_CLASS,
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # A compile failure is a RED for a mutant and a broken harness for the
    # control; either way SAY WHICH, because "0 tests executed" and "19 tests,
    # 3 failures" are different stories and only one of them is a guard biting.
    line = ""
    for ln in proc.stdout.splitlines():
        if "Executed" in ln and "test" in ln:
            line = ln.strip()
    return proc.returncode == 0, line or "NO TEST RAN (compile failure or harness error)"


def run_jest() -> tuple[bool, str]:
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={JEST_PATTERN}"],
        cwd=REPO / "frontend",
        capture_output=True,
        text=True,
    )
    line = ""
    for ln in (proc.stderr + proc.stdout).splitlines():
        if ln.strip().startswith("Tests:"):
            line = ln.strip()
    return proc.returncode == 0, line or "NO TEST RAN (harness error)"


RUNNERS = {SWIFT: run_swift, JEST: run_jest}


def main() -> int:
    if "--list" in sys.argv:
        for name, runner, _, old, new, why in MUTANTS:
            print(f"- [{runner}] {name}\n    {'CONTROL' if old == new else 'mutates'}: {why}")
        return 0

    # `--only <substring>` re-runs one repaired mutant without paying for the
    # whole battery again (a Swift mutant costs a full app-module rebuild, ~10
    # minutes). The CONTROLS always run, because a filtered battery with no
    # control is a battery that cannot tell a kill from a broken harness.
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    results = []
    for name, runner, path, old, new, why in MUTANTS:
        # Case-INSENSITIVE: the two order mutants differ only by "ABOVE"/"above",
        # and a case-sensitive filter silently ran one of the pair and reported
        # "0 gaps" over a battery that had skipped the mutant being repaired.
        if only is not None and only.lower() not in name.lower() and old != new:
            continue
        original = path.read_text(encoding="utf-8")
        is_control = old == new

        if not is_control:
            if original.count(old) != 1:
                # A needle that does not apply reads exactly like a kill. Refuse
                # rather than grade it.
                print(
                    f"!! NEEDLE NOT FOUND for {name!r}: {original.count(old)} matches",
                    file=sys.stderr,
                )
                return 2
            path.write_text(original.replace(old, new), encoding="utf-8")

        try:
            green, summary = RUNNERS[runner]()
        finally:
            # Always restore, Ctrl-C included: a mutant left in the tree is a
            # defect shipped by the battery that was meant to catch it.
            path.write_text(original, encoding="utf-8")

        if is_control:
            verdict = "GREEN (correct)" if green else "RED (HARNESS BROKEN)"
            ok = green
        else:
            verdict = "SURVIVED (gap)" if green else "killed"
            ok = not green
        results.append((ok, name, runner, verdict, summary))
        print(f"[{'ok ' if ok else 'GAP'}] {runner:5} {name}\n      {verdict} — {summary}")

    killed = sum(1 for ok, _, _, v, _ in results if ok and "killed" in v)
    controls = sum(1 for ok, _, _, v, _ in results if ok and "GREEN" in v)
    gaps = [r for r in results if not r[0]]
    print(f"\n{killed} killed, {controls} controls green, {len(gaps)} gaps")
    for _, name, runner, verdict, summary in gaps:
        print(f"  GAP [{runner}] {name}: {verdict} — {summary}")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
