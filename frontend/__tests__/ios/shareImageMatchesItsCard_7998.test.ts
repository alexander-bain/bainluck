/**
 * #7998 — the iOS share IMAGE prints the pair its CARD printed, asserted by
 * reading the Swift and by re-running the arithmetic.
 *
 * The Discover card's share button has three outputs. The strip in the card body
 * and the share SENTENCE both asked `duelPercents` with the served pair; the
 * image, behind the same `ShareLink`'s `contextMenu`, rounded each side alone.
 *
 * Measured 2026-09-22 over the 408 production event payloads in
 * `artifacts/native-293/event-details.json`: of 295 two-way events serving a
 * printable pair, 119 (40%) produced an image disagreeing with the card the
 * reader had just long-pressed — 105 printing 101, and 14 printing a DIFFERENT
 * pair that already summed to 100 (NY Islanders @ NY Rangers: card `42% / 58%`,
 * image `43% / 57%`).
 *
 * 🔴 WHY THIS FILE EXISTS AND `ShareImageMatchesItsCard_7998Tests` DOES NOT
 * SUFFICE. The Swift tests prove `printedPercents`. They cannot prove the VIEW
 * calls it, nor that `DiscoverEventCard` still hands over the served pair — and
 * both of those are where the defect lived. Reverting either call site leaves
 * every Swift test green. These assertions kill that mutant, and they run in CI,
 * which compiles no Swift.
 *
 * 🔴 AND THE HANDOVER IS HALF THE FIX. `printedPercents` can only prefer the
 * served pair if someone passes it. `renderedShareImage()` previously handed over
 * two `Double`s and dropped the decided percents on the floor while its own
 * comment claimed it drew "the same pair rule the card's own strip draws". A scan
 * of `ShareCardRenderer` alone would not see that, so the caller is pinned too.
 *
 * Comments are stripped before scanning: this fix documents the defect by quoting
 * it, and a scanner that reads prose as code reports the cure as the disease.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

import { swiftCode } from "../helpers/swiftSource";

const REPO_ROOT = join(__dirname, "../../..");
const APP_ROOT = join(REPO_ROOT, "ios/Bain Luck/Bain Luck");

const SHARE_CARD = join(APP_ROOT, "Utilities/ShareCardRenderer.swift");
const DISCOVER_CARD = join(APP_ROOT, "Components/DiscoverEventCard.swift");

const read = (path: string) => readFileSync(path, "utf8");

/**
 * The banned shapes, as constants, because the capability tests below exercise
 * THE SAME predicates the production scan does. A capability test written
 * against its own private copy proves the copy works and says nothing about the
 * guard.
 *
 * Each is one 32pt figure formatted with no `renderedPercent:` — an opinion about
 * this side's percentage formed without reference to its other half.
 */
/** `formatProbability(awayProbability)` — the away figure, decided alone. */
const LONE_AWAY_FIGURE = /formatProbability\(\s*awayProbability\s*\)/;
/** `formatProbability(homeProbability)` — the home figure, decided alone. */
const LONE_HOME_FIGURE = /formatProbability\(\s*homeProbability\s*\)/;

/** THE PRODUCTION SCAN. Takes RAW Swift so no call site can choose a read. */
function loneFigureShapes(swiftSrc: string): string[] {
  const code = swiftCode(swiftSrc);
  return [LONE_AWAY_FIGURE, LONE_HOME_FIGURE]
    .map((re) => code.match(re)?.[0])
    .filter((m): m is string => Boolean(m));
}

/** Whether the renderer's own pair decision exists and defers to the contract. */
function decidesThePairOnce(swiftSrc: string): boolean {
  const code = swiftCode(swiftSrc);
  return (
    /static func printedPercents\(/.test(code) &&
    /duelPercents\(/.test(code)
  );
}

/** How many of the two served fields the caller hands to the renderer. */
function servedFieldsHandedOver(swiftSrc: string): string[] {
  const code = swiftCode(swiftSrc);
  return [
    /awayRenderedPercent:\s*event\.currentOdds\?\.awayRenderedPercent/,
    /homeRenderedPercent:\s*event\.currentOdds\?\.homeRenderedPercent/,
  ]
    .map((re) => code.match(re)?.[0])
    .filter((m): m is string => Boolean(m));
}

// ---------------------------------------------------------------------------
// The suite is meaningless pointed at nothing. A path typo would otherwise read
// as a clean pass, so the paths are asserted as a TEST rather than used to skip.
// ---------------------------------------------------------------------------

describe("#7998 — the files this guard reads all exist", () => {
  it.each([SHARE_CARD, DISCOVER_CARD])("%s", (path) => {
    expect(existsSync(path)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 0. THE GUARD'S OWN CAPABILITY.
//
// The production scan is a negative assertion over a tree that is now clean, so
// it passes whether or not it can see anything. Its subject here is the SCAN,
// fed a specimen — deliberately not "the tree still contains a case", which is a
// liveness assertion that dies the moment the population is correct.
// ---------------------------------------------------------------------------

describe("#7998 — the scan can see the defect it bans", () => {
  /** `ShareableEventCardView`'s two figures exactly as they read before this ship. */
  const DEFECTIVE = [
    "                        if let awayProbability {",
    "                            Text(formatProbability(awayProbability))",
    "                                .font(.system(size: 32, weight: .black))",
    "                        }",
    "                        Text(formatProbability(homeProbability))",
    "                            .font(.system(size: 32, weight: .black))",
  ].join("\n");

  /** `renderedShareImage()` handing over probabilities and nothing else. */
  const DEFECTIVE_CALLER = [
    "        return ShareCardRenderer.renderEventCard(",
    "            homeProbability: printable.home,",
    "            awayProbability: printable.away,",
    "            sportName: event.sportName ?? event.sport ?? \"Sports\",",
    "        )",
  ].join("\n");

  it("the specimens really do contain the defect before any strip", () => {
    // Without this the rest of the describe could pass on a typo'd specimen — a
    // fixture that misrepresents the defect makes every assertion below vacuous.
    expect(DEFECTIVE).toMatch(LONE_AWAY_FIGURE);
    expect(DEFECTIVE).toMatch(LONE_HOME_FIGURE);
    expect(DEFECTIVE_CALLER).not.toMatch(/awayRenderedPercent:/);
  });

  it("THE PRODUCTION SCAN sees them", () => {
    // 🔴 The one that matters: the exact functions the bans below call, not a
    // copy of their regexes.
    expect(loneFigureShapes(DEFECTIVE)).toHaveLength(2);
    expect(decidesThePairOnce(DEFECTIVE)).toBe(false);
    expect(servedFieldsHandedOver(DEFECTIVE_CALLER)).toHaveLength(0);
  });

  it("the scan still strips comments, so the fix may document itself", () => {
    // The original reason for any strip at all. If this regressed, the file
    // would red on its own explanatory comment and someone would revert the lot.
    const documented = [
      "// Was: Text(formatProbability(awayProbability)) — see #7998.",
      "/* and formatProbability(homeProbability) beside it. */",
      "let printed = Self.printedPercents(away: a, home: h)",
    ].join("\n");
    expect(loneFigureShapes(documented)).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 1. THE BAN, on the view that renders the image.
// ---------------------------------------------------------------------------

describe("#7998 — ShareableEventCardView decides its pair once", () => {
  it("neither 32pt figure is formatted on its own", () => {
    expect(loneFigureShapes(read(SHARE_CARD))).toEqual([]);
  });

  it("the decision exists as a testable static and defers to the contract", () => {
    // Static rather than inline in the `some View`: the arithmetic being
    // unreachable from XCTest is how #4963's iOS clearance came to read the share
    // SENTENCE and never the image.
    expect(decidesThePairOnce(read(SHARE_CARD))).toBe(true);
  });

  it("the view draws the decided strings rather than re-deriving them", () => {
    const code = swiftCode(read(SHARE_CARD));
    expect(code).toContain("Text(printed.home)");
    expect(code).toContain("if let awayPercent = printed.away {");
  });

  it("it does not re-implement the rounding rule (#3892's class)", () => {
    // The pairing belongs to `duelPercents` / `renderedDuelPercents`. A second
    // copy of the scale here is exactly what put 57 on the image where the card
    // and the server both said 58.
    const code = swiftCode(read(SHARE_CARD));
    expect(code).not.toMatch(/printedPercents[\s\S]{0,600}\* 100/);
  });
});

// ---------------------------------------------------------------------------
// 2. THE HANDOVER, on the caller that holds the served pair.
// ---------------------------------------------------------------------------

describe("#7998 — renderedShareImage hands over the pair the card decided", () => {
  it("both served fields are passed, as a pair", () => {
    // A count rather than a boolean: #2279's rule is BOTH SERVED OR NEITHER, and
    // a caller that passed only one would re-open the 101 from the other side.
    expect(servedFieldsHandedOver(read(DISCOVER_CARD))).toHaveLength(2);
  });

  it("the card's own strip still asks the same question", () => {
    // If the strip stopped using `duelPercents`, the image would now match a card
    // that had itself become wrong — this guard's subject is AGREEMENT, so the
    // other side of the agreement is pinned too.
    expect(swiftCode(read(DISCOVER_CARD))).toMatch(
      /duelPercents\(\s*away:[\s\S]{0,200}servedHome:\s*event\.currentOdds\?\.homeRenderedPercent/
    );
  });
});

// ---------------------------------------------------------------------------
// 3. THE ARITHMETIC, re-run here so the guard is not purely textual.
//
// The web arm of the same contract is imported and swept over the grid the
// venues quote on. Native's `renderedDuelPercents` is the Swift arm of this
// identical rule (`contracts/rendered_percent.json`), so an answer that holds
// here is the answer the phone prints.
// ---------------------------------------------------------------------------

describe("#7998 — the two failure classes, on the grid the venues quote on", () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { renderedDuelPercents } = require("@/lib/renderedPercent");

  /** The pre-fix expression: `formatProbability` with no `renderedPercent:`. */
  const independently = (p: number) => Math.round(p * 100);

  it("the pair always sums to 100, and independent rounding did not", () => {
    let summedTo101 = 0;
    let statedADifferentPair = 0;
    let checked = 0;

    for (let step = 1; step < 200; step += 1) {
      const home = step * 0.005;
      const away = 1 - home;
      // Only pairs where both sides print a numeral; `<1%` / `>99%` are claims
      // about the value and are unaffected by the pair decision.
      if (home * 100 < 1 || home * 100 > 99) continue;
      if (away * 100 < 1 || away * 100 > 99) continue;
      checked += 1;

      const [a, h] = renderedDuelPercents(away, home);
      expect(a + h).toBe(100);

      const oldAway = independently(away);
      const oldHome = independently(home);
      if (oldAway + oldHome === 101) summedTo101 += 1;
      else if (oldAway !== a || oldHome !== h) statedADifferentPair += 1;
    }

    expect(checked).toBeGreaterThan(150);
    // If either arm never fired, this file is guarding half of nothing.
    expect(summedTo101).toBeGreaterThan(0);
    // 🔴 The arm a sum guard cannot see — the 14 production rows.
    expect(statedADifferentPair).toBeGreaterThan(0);
  });

  it("the two photographed specimens, end to end", () => {
    // Ruse @ Lys, 15314911 — the 101.
    expect(renderedDuelPercents(0.585, 0.415)).toEqual([59, 41]);
    // Islanders @ Rangers, 15313235 — the pair that already summed to 100.
    expect(renderedDuelPercents(0.425, 0.575)).toEqual([42, 58]);
    expect(independently(0.425) + independently(0.575)).toBe(100);
    expect(independently(0.575)).not.toBe(58);
  });
});
