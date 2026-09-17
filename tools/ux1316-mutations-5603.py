#!/usr/bin/env python3
"""Mutation battery for #5603's web label half.

THREE files under mutation, deliberately: the RULE (`discover/utils.ts`) and BOTH
WIRINGS (`discover/ConceptCard.tsx`, `FeedCard.tsx`). ux/1315's mutant C is the
reason — a battery that only mutates the rule cannot see a presentation decision,
and this ship's whole risk is that the rule lands on one of two concept renderers
and the other keeps printing the routing token.

In-memory restore, a `restored:` line per mutant, failing names from jest's JSON
(this workspace's reporter prints no per-test lines, so a `✕` scrape reads
"0 assertions fired" on every kill — ux/1315's battery trap).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
UTILS = FRONTEND / "components/discover/utils.ts"
DISCOVER_CARD = FRONTEND / "components/discover/ConceptCard.tsx"
SPORTS_CARD = FRONTEND / "components/FeedCard.tsx"
JSON_OUT = Path("/tmp/ux1316-mutation-5603.json")

MUTANTS = [
    (
        "A · the Discover wiring is reverted — the original defect, on the surface "
        "the card was written for",
        DISCOVER_CARD,
        "  const domainLabel = conceptDomainLabel(data.sport_label, data.domain);",
        '  const domainLabel = (data.domain || "event").toUpperCase();',
    ),
    (
        "B · the Sports wiring is reverted — the SECOND renderer, which the rule "
        "arms alone cannot see",
        SPORTS_CARD,
        "              {conceptDomainLabel(data.sport_label, data.domain)}",
        '              {data.domain?.toUpperCase() || "EVENT"}',
    ),
    (
        "C · the fallback becomes the obvious `sport_label || domain` — green for "
        "the evidenced card, and the defect again for every payload without the "
        "field (i.e. all eight served today)",
        UTILS,
        '  if (UNEVIDENCED_COMBAT_DOMAINS.has(routing.toLowerCase())) return "COMBAT";',
        "",
    ),
    (
        "D · the withheld chip names the promotion anyway",
        UTILS,
        '  if (UNEVIDENCED_COMBAT_DOMAINS.has(routing.toLowerCase())) return "COMBAT";',
        '  if (UNEVIDENCED_COMBAT_DOMAINS.has(routing.toLowerCase())) return "UFC";',
    ),
    (
        "E · the server's evidence is ignored — a fix written as 'never print UFC' "
        "rather than 'print what the server can prove'",
        UTILS,
        "  if (declared) return declared.toUpperCase();",
        "",
    ),
    (
        "F · `.trim()` is dropped, so a blank label from a cached envelope renders "
        "an EMPTY chip — worse than either label",
        UTILS,
        '  const declared = (sportLabel ?? "").trim();',
        '  const declared = sportLabel ?? "";',
    ),
    (
        "G · the set is widened to boxing — spending a truthful label to fix an "
        "untruthful one",
        UTILS,
        'const UNEVIDENCED_COMBAT_DOMAINS = new Set(["ufc"]);',
        'const UNEVIDENCED_COMBAT_DOMAINS = new Set(["ufc", "boxing"]);',
    ),
    (
        "H · the routing token is matched case-sensitively, so a `UFC` domain "
        "walks straight through the gate",
        UTILS,
        "  if (UNEVIDENCED_COMBAT_DOMAINS.has(routing.toLowerCase())) return \"COMBAT\";",
        '  if (UNEVIDENCED_COMBAT_DOMAINS.has(routing)) return "COMBAT";',
    ),
]

BAND = "aSlapFightingCardStopsWearingAUfcChip5603"


def run_tests() -> tuple[int, set[str]]:
    import json
    import os

    if JSON_OUT.exists():
        JSON_OUT.unlink()
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={BAND}", "--json", f"--outputFile={JSON_OUT}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    failed: set[str] = set()
    if JSON_OUT.exists():
        report = json.loads(JSON_OUT.read_text())
        for suite in report.get("testResults", []):
            for case in suite.get("assertionResults", []):
                if case.get("status") == "failed":
                    failed.add(case.get("fullName", "?"))
    return proc.returncode, failed


code, failed = run_tests()
print(f"BASELINE (the fix as committed): exit {code}, {len(failed)} failing")
if code != 0:
    for f in sorted(failed):
        print(f"   ✕ {f}")
    print("🔴 the baseline is not green — nothing below means anything")
    sys.exit(2)

killed = 0
signatures = []
for name, path, old, new in MUTANTS:
    orig = path.read_text()
    if old not in orig:
        print(f"\n🔴 {name}\n   anchor NOT FOUND in {path.name} — mutant never applied")
        continue
    mutated = orig.replace(old, new, 1)
    if mutated == orig:
        print(f"\n🔴 {name}\n   replacement is a NO-OP in {path.name}")
        continue
    path.write_text(mutated)
    applied = path.read_text() != orig
    code, failed = run_tests()
    path.write_text(orig)
    restored = "YES" if path.read_text() == orig else "🔴 NO"
    verdict = "KILLED" if code != 0 else "🔴 SURVIVED"
    if code != 0:
        killed += 1
        signatures.append(frozenset(failed))
    print(f"\n{verdict}  {name}")
    print(f"   applied: {applied} · exit {code} · {len(failed)} assertion(s) fired · restored: {restored}")
    for f in sorted(failed):
        print(f"     ✕ {f}")

print(f"\n{killed}/{len(MUTANTS)} killed · {len(set(signatures))} distinct failure signatures")
sys.exit(0 if killed == len(MUTANTS) else 3)
