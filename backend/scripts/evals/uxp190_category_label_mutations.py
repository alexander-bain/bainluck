#!/usr/bin/env python3
"""UX-P190 — a market's category chip reads as English, not as a payload key.

WHAT SHIPPED, and what these mutants restore

`FuturesMarket.llm_sport_category` is a snake_case key. Six frontend call sites
printed it VERBATIM, so `/search?q=Kikawada` rendered "TABLE_TENNIS" (the search
card uppercases its eyebrow), the market page and its OpenGraph share image
rendered "table_tennis", and `/discover/stats` rendered "Table_tennis" — a CSS
`capitalize` that structurally cannot reach an underscore. 14,588 OPEN markets
carry an underscored key; 14,584 are `table_tennis`, the 5th largest category at
103,674 markets.

The fix routes all six through `getMarketCategoryLabel` / `getNameForCategory`
in `lib/sportCategories.ts` — the curated labeller `FeedCard` and
`CombinedFeedCard` already used — and removes the two compensating CSS
transforms, which after the fix could only corrupt a label they do not own
("Track and Field" -> "Track And Field").

WHY THE TWO CSS MUTANTS ARE HERE AND NOT TREATED AS COSMETIC

UX-P189's lesson, paid for on `/calibration`: CSS hid half of that defect, which
is why it survived. A guard that grades only the helper passes while a call site
re-adds a transform that re-mangles the output. M10 and M13 are those two call
sites, and they are graded like any other.

TARGETS ARE TYPESCRIPT/TSX, not Python — the second harness in this directory
with non-Python targets, after `event_hero_duel_percent_mutations` (LAT-P119).
Pass A of `scan_mutation_residue.py` reads each declared target directly and is
already file-type agnostic.

    cd backend && python3 scripts/evals/uxp190_category_label_mutations.py

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
FRONTEND = REPO / "frontend"

LIB = FRONTEND / "lib/sportCategories.ts"
SEARCH_CARD = FRONTEND / "components/FuturesCard.tsx"
CMP_CARD = FRONTEND / "components/discover/ComparisonCard.tsx"
DISCOVER_CARD = FRONTEND / "components/discover/FuturesCard.tsx"
DAILY = FRONTEND / "app/daily/page.tsx"
STATS = FRONTEND / "app/discover/stats/page.tsx"
MARKET_PAGE = FRONTEND / "app/futures/[id]/page.tsx"
OG = FRONTEND / "app/futures/[id]/opengraph-image.tsx"

#: Backups are keyed EXPLICITLY per target, not by dropping every file into one
#: directory. The flat form derives the backup name from the BASENAME, and this
#: harness has three `page.tsx` and two `FuturesCard.tsx` among its eight
#: targets — they collided, the last writer won, and the guard's exit restore
#: wrote `app/futures/[id]/page.tsx` over `app/daily/page.tsx` and
#: `app/discover/stats/page.tsx`. The sha check caught it and refused to call
#: the tree clean, which is the whole reason that check exists; a harness whose
#: targets share a basename must pass the dict form.


def _backup_paths() -> dict[Path, Path]:
    """One backup file per target, named from the target's REPO-RELATIVE path."""
    root = Path("/tmp/uxp190_backups")
    return {
        t: root / str(t.relative_to(REPO)).replace("/", "__")
        for t in sorted({m[1] for m in MUTANTS})
    }

#: The jest modules that ARE the oracle. Named, not globbed: a pattern that
#: matched nothing would run zero tests and score every mutant killed.
ORACLE_PATTERNS = ("marketCategoryLabel", "marketCategoryChipRender")

#: `(id, target, needle, replacement, why)` — the indexed-tuple shape
#: `scan_mutation_residue.py` harvests as `("MUTANTS", 2, 3, 1)`. One table with
#: a per-entry Path, rather than eight tables with eight module constants,
#: because eight targets is where the split-table shape stops reading.
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1-helper-prints-the-raw-key",
        LIB,
        "  if (categoryKey) return getNameForCategory(categoryKey);",
        "  if (categoryKey) return categoryKey;",
        "THE DEFECT ITSELF, in one place: the helper hands back the payload key. "
        "Every call site regresses at once.",
    ),
    (
        "M2-helper-prefers-the-llm-key-over-the-curated-sport",
        LIB,
        "  if (sportName) return sportName;\n"
        "  if (categoryKey) return getNameForCategory(categoryKey);",
        "  if (categoryKey) return getNameForCategory(categoryKey);\n"
        "  if (sportName) return sportName;",
        "Inverts the preference order, so an MLB market labels as its LLM "
        "category. Not an underscore bug — the other half of the contract.",
    ),
    (
        "M3-helper-returns-empty-string-not-undefined",
        LIB,
        "  if (categoryKey) return getNameForCategory(categoryKey);\n  return undefined;\n}",
        '  if (categoryKey) return getNameForCategory(categoryKey);\n  return "";\n}',
        "An empty string is truthy-adjacent enough to swallow each caller's own "
        "fallback word, so a bare market renders a blank chip instead of "
        '"Markets". The vacuity failure the undefined contract exists to stop.',
    ),
    (
        "M4-helper-stops-honouring-SPORT_CATEGORIES",
        LIB,
        "  const cat = _CATEGORY_BY_KEY.get(categoryKey.toLowerCase());\n  if (cat) return cat.name;",
        "  const cat = undefined;\n  if (cat) return cat;",
        "Drops the curated table and leaves only the title-case fallback. "
        'The CONTROL half: "MMA" becomes "Mma", "Tech & Science" becomes "Tech". '
        "Underscores would still be gone, so a shape-only guard passes here.",
    ),
    (
        "M5-search-card-reverts-to-the-payload-key",
        SEARCH_CARD,
        "                  {market.llm_sport_category\n"
        "                    ? getNameForCategory(market.llm_sport_category)\n"
        "                    : formatSportName(market.sport, market.sport_name)}",
        "                  {market.llm_sport_category || formatSportName(market.sport, market.sport_name)}",
        "The PROVEN surface: /search, /my-stuff, /preferences. Restores "
        '"TABLE_TENNIS" on the 9 fixture rows captured from the live route.',
    ),
    (
        "M6-comparison-card-reverts",
        CMP_CARD,
        '  const category = getMarketCategoryLabel(data.sport_name, data.llm_sport_category) || "Markets";',
        '  const category = data.sport_name || data.llm_sport_category || "Markets";',
        "One of the three character-for-character copies of the open-coded "
        "expression. Graded through a real render.",
    ),
    (
        "M7-discover-futures-card-reverts",
        DISCOVER_CARD,
        '  const category = getMarketCategoryLabel(data.sport_name, data.llm_sport_category) || "Markets";',
        '  const category = data.sport_name || data.llm_sport_category || "Markets";',
        "The second copy. Graded by the source scan, since this card is not "
        "rendered in the suite.",
    ),
    (
        "M8-daily-reverts",
        DAILY,
        '      category: getMarketCategoryLabel(data.sport_name, data.llm_sport_category) || "Markets",',
        '      category: data.sport_name || data.llm_sport_category || "Markets",',
        "The third copy. This is the one a seventh copy would look like.",
    ),
    (
        "M9-stats-page-reverts-to-the-payload-key",
        STATS,
        "{getNameForCategory(cat)}</span>",
        "{cat}</span>",
        "/discover/stats By Category. Its rows come from a useEffect fetch, so "
        "the guard is a source anchor, not a render — stated, not implied.",
    ),
    (
        "M10-stats-page-re-adds-the-compensating-capitalize",
        STATS,
        'className="text-sm font-semibold w-24 shrink-0"',
        'className="text-sm font-semibold capitalize w-24 shrink-0"',
        "UX-P189's lesson: the CSS that masked half the old defect becomes a "
        'corruption once the labeller owns casing ("Track and Field" -> '
        '"Track And Field"). Absence asserted, not assumed.',
    ),
    (
        "M11-market-page-reverts",
        MARKET_PAGE,
        "        categoryLabel={getMarketCategoryLabel(market.sport_name, market.llm_sport_category)}",
        "        categoryLabel={market.sport_name || market.llm_sport_category || undefined}",
        "The /futures/[id] header chip — the same 14,584 open markets, on the "
        "page a reader lands on from search.",
    ),
    (
        "M12-opengraph-share-image-reverts",
        OG,
        "  const categoryLabel =\n"
        '    getMarketCategoryLabel(market?.sport_name, market?.llm_sport_category) || "Discover";',
        '  const categoryLabel = market?.sport_name || market?.llm_sport_category || "Discover";',
        "The share card. This one leaves the product: a pasted link renders the "
        "raw key to everyone who sees it, not just to the reader who clicked.",
    ),
    (
        "M14-market-page-heading-skips-the-curated-table",
        MARKET_PAGE,
        "`More ${getNameForCategory(market.llm_sport_category)}`",
        "`More ${toTitleCaseAcronymSafe(market.llm_sport_category)}`",
        "The SEVENTH site, and the subtlest: this one already de-underscored, so "
        "no underscore guard would ever have caught it. It skipped the curated "
        "table, and the page called one category two names — the header chip "
        'said "Tech & Science" while the heading below said "More Tech".',
    ),
    (
        "M13-opengraph-re-adds-the-compensating-text-transform",
        OG,
        "                color: accent,",
        '                color: accent,\n                textTransform: "capitalize",',
        "The share card's half of M10. Caught a real slip during this build: the "
        "first replacement COMMENT quoted the banned string and the guard fired.",
    ),
]


def _run_oracle() -> tuple[bool, list[str]]:
    """Run the two jest modules. Returns (passed, tail)."""
    args = ["npx", "jest"]
    for pattern in ORACLE_PATTERNS:
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
    # The dict form takes one explicit path per target. Assert the mapping is
    # injective before trusting it — a silent collision here is the failure this
    # harness already hit once.
    assert len(set(backups.values())) == len(backups), "backup paths collide"

    with guarded_targets(targets, backups, "uxp190-category-label"):
        for mutant_id, path, needle, replacement, _why in MUTANTS:
            original = path.read_text()
            count = original.count(needle)
            if count != 1:
                # A needle that does not apply scores nothing. It must never be
                # reported as a kill (gotcha #53 — the silent case gets loud).
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
