/**
 * #4970's native half — the iOS Additional Markets card DATES its prices, and
 * the decision is wired into the view rather than merely existing beside it.
 *
 * WHY THIS FILE AND NOT ONLY THE SWIFT SUITE.
 * `AQuietLegOnALiveCardSaysSoTests` proves `ageDecision` — what draws, when, and
 * with which stamp. It cannot prove `propMiniCard` and `outcomeRow` USE the
 * answer: both are methods on a SwiftUI view whose `body` no XCTest can reach.
 * Delete the two `PriceAgeMarkView(...)` call sites and every Swift assertion
 * still passes while the phone goes back to drawing a 43-minute-old 53% beside
 * a two-minute-old 100% with nothing to tell them apart. These assertions kill
 * that mutant, and they run in CI, which compiles no Swift.
 *
 * MEASURED (production, 2026-09-16 16:5xZ, three live soccer events in one
 * pass): 15310931 "Second Half Result" summed to 153% at leg ages 2 / 43 / 25
 * minutes; 15313067 "Halftime Result" 182% at 2 / 115 / 115; 15307696 "First
 * Team to Score" 135% at 49 / 284 / 284. In each one the arithmetic excess is
 * the leg nothing refreshed.
 *
 * TWO COPIES OF ONE RULE, pinned as such: web's `PropMiniCard`
 * (`frontend/components/SpecialEventMarkets.tsx`) and Swift's
 * `SpecialEventMarketsView.ageDecision`. Both answer "all rows quiet ⇒ one card
 * mark; mixed ⇒ the stale rows carry their own", and the last block below
 * asserts the Swift text still carries both arms.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const REPO = join(__dirname, "../../..");
const VIEW = join(REPO, "ios/Bain Luck/Bain Luck/Components/SpecialEventMarketsView.swift");
const MODEL = join(REPO, "ios/Bain Luck/Bain Luck/Models/FuturesModels.swift");
const WEB = join(REPO, "frontend/components/SpecialEventMarkets.tsx");

function stripSwiftComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass.
const present = existsSync(VIEW) && existsSync(MODEL) && existsSync(WEB);
const d = present ? describe : describe.skip;

d("a quiet leg on a live iOS Additional Markets card says so", () => {
  const view = () => stripSwiftComments(readFileSync(VIEW, "utf8"));
  const model = () => stripSwiftComments(readFileSync(MODEL, "utf8"));

  describe("the stamp reaches the card at all", () => {
    it("GameMarketOther decodes observedAt", () => {
      // The whole defect: `observed_at` has been on every one of these rows
      // since #4970 and this model threw it away.
      expect(model()).toMatch(/struct GameMarketOther[\s\S]*?\blet observedAt: String\?/);
    });

    it("the built OutcomeEntry carries it", () => {
      const src = view();
      expect(src).toMatch(/struct OutcomeEntry[\s\S]*?\bvar observedAt: String\?/);
      // Both construction sites — the append and the first-row case. A stamp
      // that reaches only one of them dates half a card.
      const built = src.match(/OutcomeEntry\([\s\S]{0,220}?observedAt: m\.observedAt/g) ?? [];
      expect(built).toHaveLength(2);
    });
  });

  describe("the decision is wired into what renders", () => {
    it("propMiniCard computes it and draws the card mark", () => {
      const src = view();
      expect(src).toMatch(/Self\.ageDecision\(\s*sorted,\s*live: isLiveEvent\s*\)/);
      expect(src).toMatch(/PriceAgeMarkView\(observedAt: age\.cardStamp, cadence: \.live\)/);
    });

    it("the row mark is drawn, and only when the card is not speaking", () => {
      const src = view();
      expect(src).toMatch(/outcomeRow\([\s\S]{0,80}?showAge: age\.showRowAges\)/);
      expect(src).toMatch(/if showAge, !isGameFinished \{\s*PriceAgeMarkView\(observedAt: o\.observedAt, cadence: \.live\)/);
    });

    it("the live triple gates it, so a pregame card is never dated", () => {
      // `!isGameFinished` alone would mark every row of every upcoming game,
      // whose markets are polled far slower than the live cadence.
      expect(view()).toMatch(
        /var isLiveEvent: Bool \{\s*!isGameFinished && !SettledQuote\.isPregame\(eventStatus\)/
      );
    });
  });

  describe("both arms of the rule survive", () => {
    it("the card speaks only when EVERY row agrees, with the OLDEST stamp", () => {
      const src = view();
      // `stale.count == outcomes.count` is the arm that stops one quiet row
      // putting a false age over a card full of fresh ones.
      expect(src).toMatch(/stale\.count == outcomes\.count/);
      expect(src).toMatch(/SourceAge\.oldestStamp\(stale\.map\(\\\.observedAt\)\)/);
    });

    it("the mixed arm hands the age back to the rows", () => {
      expect(view()).toMatch(/AgeDecision\(cardStamp: nil, showRowAges: !stale\.isEmpty\)/);
    });

    it("it does not renormalise the card, which is upstream's job", () => {
      // Guarding the absence: a later reader "fixing" the 153% here would
      // shrink a fresh 99.55% to flatter a 43-minute-old 52.5%.
      expect(view()).not.toMatch(/normaliz|normalis/i);
    });
  });

  describe("web and native answer it the same way", () => {
    it("web still has the card-speaks-for-all arm this mirrors", () => {
      const web = readFileSync(WEB, "utf8");
      expect(web).toMatch(/cardSpeaksForAll/);
      expect(web).toMatch(/oldestSourceStamp/);
    });
  });
});
