#!/usr/bin/env python3
"""native/199-200 — mutation battery for #888 (the league page draws what it fetched).

Each mutant rewrites SHIPPED Swift and asks whether the #888 guards notice. The
defect class is SILENT LOSS — `leagueData.sections[key]` renders an absent key
and an empty section identically, and `LeagueGridViewModel.loadLeagueMarkets`
catches a decode throw into a `logger.debug` — so the guards' whole job is to
notice content that cannot arrive.

Three defects live on this one reader path and each has its own arm here:

  M1-M9    the section vocabulary (`LeagueMarketSections`), including the
           second copy that used to live in `SportCategoryView`;
  M10-M14  the decode (`CategoryOutcome` / `LeagueMarketsResponse`), which is
           why the phone drew ZERO sections rather than a reduced set;
  M15-M16  the percent/fraction scale, which is why the first repaired
           screenshot showed every market at 0%.

Same four rules as the #6671 battery: a needle that is absent OR matches more
than once fails the battery rather than counting as a kill; the dirty-tree guard
is scoped to the mutated files with --untracked-files=no; restores with
`git checkout HEAD --`, never `git checkout --` (that reads the INDEX); and any
xcodebuild exit outside {0, 65} is a harness story, not a grade.

Usage:  python3 -u tools/native-199-mutations-888.py
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CATALOG = "ios/Bain Luck/Bain Luck/Utilities/LeagueMarketSections.swift"
CATEGORY = "ios/Bain Luck/Bain Luck/Views/SportCategoryView.swift"
MODELS = "ios/Bain Luck/Bain Luck/Models/CategoryModels.swift"
MUTABLE = [CATALOG, CATEGORY, MODELS]

PROJECT = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME = "Bain Luck"
SWIFT_FLAGS = "$(inherited) -Xfrontend -disable-sandbox"
TEST_CLASSES = [
    "BainLuckTests/LeagueGridSectionKeysMatchTheAPI888Tests",
    "BainLuckTests/LeagueMarketsDecodeAgainstProduction888Tests",
]

ORDER = 'static let order = ["series", "awards", "props", "season_stats", "more_markets"]'

# The live SportCategoryView call site, which used to hold its own copy of the
# vocabulary. M9 puts that copy back: the source-scan arm is the only assertion
# in the suite that can see it.
CATEGORY_CALLSITE = "ForEach(LeagueMarketSections.order, id: \\.self) { key in"

TERSE_ARM = """        if let percent = try c.decodeIfPresent(Double.self, forKey: .prob) {
            prob = percent
        } else {"""

VERBOSE_LINE = "prob = try c.decode(Double.self, forKey: .probability) * 100"

MUTANTS = [
    # ── the section vocabulary ────────────────────────────────────────────────
    ("M1 restore `playoff_props` (THE ORIGINAL DEFECT)", CATALOG, ORDER,
     ORDER.replace('"props"', '"playoff_props"'),
     "every Props market vanishes again — 31 of them on NCAAF alone"),
    ("M2 restore `novelty` (THE BIGGEST BUCKET)", CATALOG, ORDER,
     ORDER.replace('"more_markets"', '"novelty"'),
     "the classifier's DEFAULT bucket disappears — the single biggest section on most leagues"),
    ("M3 restore both dead keys — the exact shipped state", CATALOG, ORDER,
     ORDER.replace('"props"', '"playoff_props"').replace('"more_markets"', '"novelty"'),
     "48 of NBA's 64 markets gone, with no empty state to say so"),
    ("M4 a plausible near-miss spelling", CATALOG, ORDER,
     ORDER.replace('"more_markets"', '"moreMarkets"'),
     "camelCase against a snake_case API — silent, and exactly how this class recurs"),
    ("M5 drop `more_markets` rather than misspell it", CATALOG, ORDER,
     'static let order = ["series", "awards", "props", "season_stats"]',
     "an API section neither rendered nor declared — the second arm must catch this"),
    ("M6 render a section the API never emits at all", CATALOG, ORDER,
     ORDER.replace('"season_stats"', '"season_stats", "player_props"'),
     "a key invented on the client; renders nothing, says nothing"),
    ("M7 silently widen the exemption instead of rendering", CATALOG, ORDER,
     'static let order = ["series", "awards", "props", "season_stats"]\n    // exempt: more_markets',
     "a comment is not a declaration; the set must move, not the prose"),
    ("M8 strand a label on the old key (rename drift)", CATALOG,
     '"props": "Props",', '"playoff_props": "Props",',
     "the header falls through to the key-derived fallback with nothing going red"),
    ("M9 a SECOND COPY of the vocabulary in SportCategoryView", CATEGORY,
     CATEGORY_CALLSITE,
     'ForEach(["series", "awards", "playoff_props", "season_stats", "novelty"], id: \\.self) { key in',
     "exactly the shipped defect, in the file the issue did not name — only the source scan sees it"),

    # ── the decode ────────────────────────────────────────────────────────────
    ("M10 read only the terse `prob` spelling (THE ZERO-SECTION DEFECT)", MODELS,
     VERBOSE_LINE,
     "prob = try c.decode(Double.self, forKey: .prob)",
     "the whole league payload throws again and the page draws NOTHING, silently"),
    ("M11 drop the terse spelling instead (break politics)", MODELS,
     TERSE_ARM,
     """        if let percent = try c.decodeIfPresent(Double.self, forKey: .probability) {
            prob = percent * 100
        } else {""",
     "leagues repaired by breaking politics and entertainment — the trade this file exists to refuse"),
    ("M12 answer a missing probability with a zero", MODELS,
     VERBOSE_LINE,
     "prob = ((try? c.decode(Double.self, forKey: .probability)) ?? 0) * 100",
     "an outcome with no served probability is drawn as 0%, a number nobody sent"),
    ("M13 make the market array strict again", MODELS,
     "let lossy = try c.decode([String: LossyArray<LeagueMarketItem>].self, forKey: .sections)\n"
     "        sections = lossy.mapValues(\\.elements)\n"
     "        droppedMarkets = lossy.values.reduce(0) { $0 + $1.dropped }",
     "sections = try c.decode([String: [LeagueMarketItem]].self, forKey: .sections)\n"
     "        droppedMarkets = 0",
     "one unreadable row takes the whole league with it — gotcha #42, client side"),
    ("M14 make the outcome array strict again", MODELS,
     "topOutcomes = try c.decodeIfPresent(LossyArray<CategoryOutcome>.self,\n"
     "                                            forKey: .topOutcomes)?.elements",
     "topOutcomes = try c.decodeIfPresent([CategoryOutcome].self, forKey: .topOutcomes)",
     "production really does serve `\"probability\": null`; strict here loses the market and then the page"),

    # ── the scale ─────────────────────────────────────────────────────────────
    ("M15 forget the percent conversion (EVERY MARKET READS 0%)", MODELS,
     VERBOSE_LINE,
     "prob = try c.decode(Double.self, forKey: .probability)",
     "Int(0.43) == 0 — sections present, populated, and every line printing zero"),
    ("M16 convert the terse spelling too", MODELS,
     "        if let percent = try c.decodeIfPresent(Double.self, forKey: .prob) {\n"
     "            prob = percent\n",
     "        if let percent = try c.decodeIfPresent(Double.self, forKey: .prob) {\n"
     "            prob = percent * 100\n",
     "politics' 98% becomes 9800% — the mirror of M15, on the endpoint that was working"),
]

EQUIVALENT = [
    ("E1 reword the rationale comment (must SURVIVE)", CATALOG,
     "/// Render order. Membership is the contract; the order is a product choice.",
     "/// Render order. Membership is the contract; the ordering is a product call."),
    ("E2 reorder two sections (must SURVIVE — this guard is about membership)", CATALOG,
     ORDER, 'static let order = ["awards", "series", "props", "season_stats", "more_markets"]'),
]


def udid() -> str:
    out = subprocess.run(["xcrun", "simctl", "list", "devices", "available"],
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if re.match(r"^\s+iPhone ", line):
            m = re.search(r"\(([0-9A-Fa-f-]{36})\)", line)
            if m:
                return m.group(1)
    raise SystemExit("NO iPhone SIMULATOR AVAILABLE — the battery cannot run.")


def run_guard(device: str) -> bool:
    only = ["-only-testing:" + cls for cls in TEST_CLASSES]
    r = subprocess.run(
        ["xcodebuild", "test", "-project", str(PROJECT), "-scheme", SCHEME,
         "-destination", f"id={device}", *only,
         f"OTHER_SWIFT_FLAGS={SWIFT_FLAGS}"],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode not in (0, 65):
        raise SystemExit(f"xcodebuild exited {r.returncode} — the gate never ran.\n{r.stdout[-3000:]}")
    return r.returncode == 0


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", *MUTABLE],
        cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print(f"REFUSING: a file this battery mutates has uncommitted changes — commit first.\n{dirty}")
        return 2

    device = udid()
    print(f"simulator: {device}\n")
    originals = {rel: (ROOT / rel).read_text() for rel in MUTABLE}

    print("BASE: ", end="", flush=True)
    if not run_guard(device):
        print("RED before any mutant. The battery cannot grade anything.")
        return 2
    print("GREEN\n", flush=True)

    killed, survived, unapplied = [], [], []

    def apply_and_grade(name, rel, needle, replacement):
        original = originals[rel]
        hits = original.count(needle)
        if hits != 1:
            unapplied.append(f"{name} (needle matches {hits}x in {rel})")
            print(f"  NEEDLE {'ABSENT' if hits == 0 else 'AMBIGUOUS'}   {name}", flush=True)
            return None
        (ROOT / rel).write_text(original.replace(needle, replacement, 1))
        green = run_guard(device)
        subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=ROOT, check=True)
        return green

    for name, rel, needle, replacement, harm in MUTANTS:
        green = apply_and_grade(name, rel, needle, replacement)
        if green is None:
            continue
        if green:
            survived.append((name, harm))
            print(f"  SURVIVED          {name}\n                    -> {harm}", flush=True)
        else:
            killed.append(name)
            print(f"  killed            {name}", flush=True)

    print(flush=True)
    for name, rel, needle, replacement in EQUIVALENT:
        green = apply_and_grade(name, rel, needle, replacement)
        if green is None:
            continue
        print(f"  {'survived (correct)' if green else 'KILLED (over-tight — BAD)'}  {name}", flush=True)
        if not green:
            survived.append((name, "the guard reads cosmetics/order as contract"))

    print(f"\n{len(killed)}/{len(MUTANTS)} defect mutants killed.")
    if unapplied:
        print(f"BATTERY FAILURE — {len(unapplied)} never applied: {unapplied}")
        return 2
    if survived:
        print("SURVIVORS — the guard has holes:")
        for n, h in survived:
            print(f"  {n}: {h}")
        return 1
    print("No survivors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
