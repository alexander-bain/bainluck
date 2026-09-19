#!/usr/bin/env python3
"""native/233 — mutation battery for #4624's guards, on BOTH clients.

#4624 threads the sport to the crest badge so the compound-CLUB fork closes for
a person. The risk this battery is aimed at is not "does the fix work" — the
census answers that on 10,533 production names — but "would the guards notice if
it stopped working, or if it started reaching names it must not". Every mutant
below either restores the defect, widens the gate past its population, or breaks
an assumption the fix rests on, and must turn at least one named test RED.

The battery runs on BOTH clients because the ship is one rule with two
implementations: a Swift mutant runs `CrestBadgeNamesAPerson4624Tests`, a
TypeScript mutant runs the cross-client parity suite. A guard on one client is a
guard on one client (standing notice 33).

Two CONTROLS, one per runner, change nothing and must stay GREEN — a battery
that reds on everything, a broken harness included, reads as success.

    tools/native-233-mutations-4624.py            # the whole battery
    tools/native-233-mutations-4624.py --list     # print the mutants, run nothing
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
RULE = REPO / "ios/Bain Luck/Bain Luck/Utilities/TeamShortName.swift"
CIRCLE = REPO / "ios/Bain Luck/Bain Luck/Components/TeamLogoView.swift"
HERO = REPO / "ios/Bain Luck/Bain Luck/Views/EventDetailView.swift"
WEB = REPO / "frontend/lib/teamShortName.ts"

SWIFT_CLASS = "BainLuckTests/CrestBadgeNamesAPerson4624Tests"
JEST_PATTERN = "teamDesignatorParityAcrossClients"
# iPhone 17 Pro. NOT 76D961F0 — that is Alex's reserved sign-in device and the
# fleet guard refuses it by name.
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

SWIFT, JEST = "swift", "jest"

# (name, runner, file, old, new, why)
MUTANTS = [
    (
        "delete the person gate (#4624 itself)",
        SWIFT,
        RULE,
        "        if namesAPerson(sportKey: sportKey), !unshippableBadges.contains(shipped.lowercased()) {\n"
        "            return shipped\n"
        "        }\n",
        "",
        "the defect restored verbatim: every three-part person is back on their "
        "initials, EMA and not ALC",
    ),
    (
        "open the gate for EVERY sport",
        SWIFT,
        RULE,
        "        if namesAPerson(sportKey: sportKey), !unshippableBadges.contains(shipped.lowercased()) {",
        "        if !unshippableBadges.contains(shipped.lowercased()) {",
        "the fix applied to clubs too: Notre Dame Fighting Irish goes NDF -> IRI "
        "and #4466's whole measurement is reverted. The half of this ship that "
        "is a DISCRIMINATOR, not a rule, is only visible in this direction",
    ),
    (
        "match the sport as a SUBSTRING instead of the first segment",
        SWIFT,
        RULE,
        '        let sport = key.split(separator: "_").first.map(String.init) ?? key\n'
        "        return individualSportPrefixes.contains(sport)",
        "        return individualSportPrefixes.contains(where: { key.contains($0) })",
        "soccer_england_boxing_day_cup now names a person, so every club in "
        "England's Boxing Day fixtures takes the person rule",
    ),
    (
        "drop the unshippable clause from the person branch",
        SWIFT,
        RULE,
        "        if namesAPerson(sportKey: sportKey), !unshippableBadges.contains(shipped.lowercased()) {",
        "        if namesAPerson(sportKey: sportKey) {",
        "a surname that spells one of the three letters nobody may ship reaches a "
        "crest — the only direction this change can make a badge WORSE",
    ),
    (
        "let a nil key mean a person",
        SWIFT,
        RULE,
        '        guard let key = sportKey?.lowercased(), !key.isEmpty else { return false }',
        '        guard let key = sportKey?.lowercased() else { return true }\n'
        '        if key.isEmpty { return true }',
        "every unthreaded call site silently changes behaviour, which is exactly "
        "what the 0-names-move-on-the-nil-key census promises cannot happen",
    ),
    (
        "widen the set by one sport",
        SWIFT,
        RULE,
        '        "tennis", "golf", "mma", "boxing",',
        '        "tennis", "golf", "mma", "boxing", "esports",',
        "an organisation badged as a person, and the cross-client set silently "
        "one entry apart — the divergence the parity guard exists for",
    ),
    (
        "stop the pair passing the matchup's sport to one side",
        SWIFT,
        RULE,
        "        let a = awayAbbr ?? abbreviation(away, sportKey: sportKey)",
        "        let a = awayAbbr ?? abbreviation(away)",
        "one tennis match drawn with one side on the club rule and one on the "
        "person rule",
    ),
    (
        "stop the circle passing its own sport",
        SWIFT,
        CIRCLE,
        "            Text(Self.badge(teamName: teamName, opponentName: opponentName, sportKey: sportKey))",
        "            Text(Self.badge(teamName: teamName, opponentName: opponentName))",
        "the rule is right and the view never asks it — the shape of the original "
        "defect, and the reason the entry point is static and asserted",
    ),
    (
        "take the sport back off the event hero",
        SWIFT,
        HERO,
        "                        sportKey: event.sport,\n"
        "                        // #4720 — the hero draws BOTH circles",
        "                        // #4720 — the hero draws BOTH circles",
        "the reader-visible surface this ship was photographed on stops asking; "
        "only the source-scan guard can see it, because a `some View` body cannot "
        "be called from a test",
    ),
    (
        "CONTROL (swift): change nothing",
        SWIFT,
        RULE,
        "",
        "",
        "the Swift harness must be capable of GREEN, or every RED above is the "
        "battery failing rather than a guard biting",
    ),
    (
        "web: delete the person branch",
        JEST,
        WEB,
        "      : person && !UNSHIPPABLE_BADGES.has(surname)\n"
        "        ? surname\n"
        "        : initials;",
        "      : initials;",
        "the browser reverts to initials while the iPhone does not — the two "
        "clients disagree about one name, which is #4539's whole lesson",
    ),
    (
        "web: read the sport as a substring",
        JEST,
        WEB,
        '  return INDIVIDUAL_SPORT_PREFIXES.has(key.split("_")[0]);',
        "  return [...INDIVIDUAL_SPORT_PREFIXES].some(p => key.includes(p));",
        "the browser's half of the first-segment rule, mutated on its own",
    ),
    (
        "web: drop the type test",
        JEST,
        WEB,
        '  if (typeof sportKey !== "string") return false;\n'
        "  const key = sportKey.trim().toLowerCase();",
        '  const key = (sportKey ?? "").trim().toLowerCase();',
        "`names.map(teamCrestBadge)` hands map's INDEX in as the sport and throws "
        "— a blank card, and the hazard a passing suite actually caught",
    ),
    (
        "web: widen the set by one sport",
        JEST,
        WEB,
        '  "tennis",\n  "golf",\n  "mma",\n  "boxing",\n',
        '  "tennis",\n  "golf",\n  "mma",\n  "boxing",\n  "esports",\n',
        "the set one entry apart from the iPhone's, which is the divergence the "
        "out-of-source comparison is for",
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
    # control; either way SAY WHICH, because "0 tests executed" and "15 tests,
    # 3 failures" are different stories and only one of them is a guard biting.
    line = ""
    for ln in proc.stdout.splitlines():
        if "Test Suite 'All tests'" in ln or ("Executed" in ln and "test" in ln):
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

    results = []
    for name, runner, path, old, new, why in MUTANTS:
        original = path.read_text(encoding="utf-8")
        is_control = old == new

        if not is_control:
            if original.count(old) != 1:
                # A needle that does not apply reads exactly like a kill. Refuse
                # rather than grade it.
                print(f"!! NEEDLE NOT FOUND for {name!r}: {original.count(old)} matches", file=sys.stderr)
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
            verdict = "RED (bites)" if not green else "GREEN (SURVIVED — guard is blind)"
            ok = not green

        results.append((name, verdict, why))
        print(f"{'ok ' if ok else 'XX '}[{runner:5s}] {name:52s} {verdict}  {summary}")

    print()
    bad = [r for r in results if "SURVIVED" in r[1] or "HARNESS BROKEN" in r[1]]
    print(f"{len(results) - len(bad)}/{len(results)} mutants behaved as required")
    for name, verdict, why in results:
        print(f"  - {name}: {verdict}\n      {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
