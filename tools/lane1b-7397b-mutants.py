#!/usr/bin/env python3
"""#7397 second half — kill the mutants one at a time. (lane1b)

Each mutant is a single plausible wrong version of the fix. A SURVIVOR means the
guards do not actually pin that behaviour and the test is decoration.

The fix is COMMITTED before this runs, so `git checkout --` restores the FIX and
not the defect — the trap that made an earlier mutation run measure nothing.
"""
from __future__ import annotations

import subprocess
import sys

REPO = "/Users/bain/bainluck-dev/lane1b"
MLN = f"{REPO}/backend/app/utils/market_label_normalization.py"
LF = f"{REPO}/backend/app/routes/league_futures.py"
TESTS = [
    "tests/test_search_league_vocabulary_7397.py",
    "tests/test_league_page_league_vocabulary_7397.py",
]

MUTANTS = [
    (
        "1. qualified rules deleted entirely — the original WNBA defect, restored",
        MLN,
        '''_QUALIFIED_VENUE_LEAGUE_REWRITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\\bWomen(?:['’]s|s)?\\s+Pro Basketball\\b", re.I), "WNBA"),
]''',
        "_QUALIFIED_VENUE_LEAGUE_REWRITES: list[tuple[re.Pattern, str]] = []",
    ),
    (
        "2. ORDER SWAPPED — bare rules run first, so the qualified rule starves",
        MLN,
        """    label = raw_name
    for pat, repl in _QUALIFIED_VENUE_LEAGUE_REWRITES:
        label = pat.sub(repl, label)
""",
        """    label = raw_name
""",
    ),
    (
        "3. qualifier guard neutered — always rewrites, 'Girls NBA' comes back",
        MLN,
        "            if _LEAGUE_CHANGING_QUALIFIER.search(match.string[: match.start()]):",
        "            if False:",
    ),
    (
        "4. guard inverted — declines everything, un-fixes the whole ship",
        MLN,
        "            if _LEAGUE_CHANGING_QUALIFIER.search(match.string[: match.start()]):",
        "            if not _LEAGUE_CHANGING_QUALIFIER.search(match.string[: match.start()]):",
    ),
    (
        "5. guard reads the WHOLE string, not the text before the match",
        MLN,
        "            if _LEAGUE_CHANGING_QUALIFIER.search(match.string[: match.start()]):",
        "            if _LEAGUE_CHANGING_QUALIFIER.search(match.string):",
    ),
    (
        "6. WNBA rule answers NBA — the rule is present and looks right",
        MLN,
        '''(re.compile(r"\\bWomen(?:['’]s|s)?\\s+Pro Basketball\\b", re.I), "WNBA"),''',
        '''(re.compile(r"\\bWomen(?:['’]s|s)?\\s+Pro Basketball\\b", re.I), "NBA"),''',
    ),
    (
        "7. rail reverts to its own bare list — the two drift apart again",
        MLN,
        "    label = _apply_venue_league_rewrites(label, _PRO_SPORT_REWRITES)",
        """    for pat, repl in _PRO_SPORT_REWRITES:
        label = pat.sub(repl, label)""",
    ),
    (
        "8. league page: build_league serializes the raw name again",
        LF,
        '''            "name": rewrite_venue_league_vocabulary(market.name),
            "source": market.source,
            "external_id": market.external_id,
            "market_tier": market.market_tier,
            "category": market.category,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,''',
        '''            "name": market.name,
            "source": market.source,
            "external_id": market.external_id,
            "market_tier": market.market_tier,
            "category": market.category,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,''',
    ),
    (
        "9. league page: the OUTCOME column goes back to raw",
        LF,
        """            "name": rewrite_venue_league_vocabulary(
                (labels or {}).get(o.name, o.name)
            ),""",
        '''            "name": (labels or {}).get(o.name, o.name),''',
    ),
    (
        "10. outcome rewrite applied to the INPUT — the sided label lookup misses",
        LF,
        """            "name": rewrite_venue_league_vocabulary(
                (labels or {}).get(o.name, o.name)
            ),""",
        """            "name": (labels or {}).get(
                rewrite_venue_league_vocabulary(o.name),
                rewrite_venue_league_vocabulary(o.name),
            ),""",
    ),
    (
        "11. the possessive is made mandatory — 'Womens' relapses to NBA",
        MLN,
        '''re.compile(r"\\bWomen(?:['’]s|s)?\\s+Pro Basketball\\b", re.I)''',
        '''re.compile(r"\\bWomen's\\s+Pro Basketball\\b", re.I)''',
    ),
    (
        "12. qualified rule anchored to the start — mid-sentence rows relapse",
        MLN,
        '''re.compile(r"\\bWomen(?:['’]s|s)?\\s+Pro Basketball\\b", re.I)''',
        '''re.compile(r"^Women(?:['’]s|s)?\\s+Pro Basketball\\b", re.I)''',
    ),
]


def run_tests() -> tuple[bool, str]:
    p = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "--no-header", "-x"],
        cwd=f"{REPO}/backend", capture_output=True, text=True,
    )
    return p.returncode == 0, (p.stdout or "").strip().splitlines()[-1:]


ok, line = run_tests()
if not ok:
    raise SystemExit(f"BASELINE IS RED — fix that first: {line}")
print(f"baseline GREEN: {line}\n")

killed = survived = 0
for name, path, old, new in MUTANTS:
    with open(path) as fh:
        src = fh.read()
    if old not in src:
        print(f"  ?? {name}\n     ANCHOR NOT FOUND — mutant never applied, this is not a pass")
        survived += 1
        continue
    assert src.count(old) == 1, f"anchor is ambiguous for: {name}"
    with open(path, "w") as fh:
        fh.write(src.replace(old, new, 1))
    good, line = run_tests()
    subprocess.run(["git", "-C", REPO, "checkout", "--", path], check=True)
    if good:
        print(f"  SURVIVED  {name}")
        survived += 1
    else:
        print(f"  killed    {name}")
        killed += 1

print(f"\nkilled={killed}  survived={survived}  of {len(MUTANTS)}")
ok, line = run_tests()
print(f"restored to HEAD, suite {'GREEN' if ok else 'RED'}: {line}")
sys.exit(1 if survived else 0)
