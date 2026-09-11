/**
 * #5113 — the iOS props stat label repeated the matchup, so the stat name truncated.
 *
 * Photographed on `bainluck://events/15308637`:
 *
 *     TAMPA BAY VS ATLANTA: HITS + RUNS + R…   chance of hitting   Final 2
 *
 * The reader is already on the Tampa Bay vs Atlanta page — the teams are in the nav
 * bar two inches above — so every stat label on every card spent its width on a fact
 * the reader had, and "Hits + Runs + RBIs" truncated on all nine cards in the shot.
 *
 * MEASURED on production before the rule was chosen, 19 events, 2026-09-11:
 *
 *     3,974 rendered props · 100% carried a matchup prefix · 100% source=kalshi
 *     2,136 sampled prefixes · the ONLY separator present was "vs"
 *     the known-team token test fired on 100% of them
 *
 * ═══ WHY THE RULE IS "NAMES BOTH TEAMS" AND NOT "CUT AT THE FIRST COLON" ═══
 *
 * Cutting at the first colon is the tempting version and it loses data two ways.
 * Polymarket puts the PLAYER in that slot ("Cole Young: Total Bases O/U 2.5"), and a
 * stat whose own name contains a colon ("Shots at Goal: First Half") would lose its
 * name. The prefix is dropped only when something else on screen already says it:
 * this event's two teams, or the card header's player. Both branches are explicit.
 *
 * The abbreviated shapes are real and are covered: production serves
 * "Dallas vs New York G" and "New York J vs Tennessee".
 *
 * ═══ WHY THIS FILE EXISTS AND NOT ONLY THE XCTESTS ═══
 *
 * CI COMPILES NO SWIFT. `PlayerPropsStatLabelTests` proves the pure function on a
 * laptop; it structurally cannot prove the VIEW calls it, and reverting the view to
 * its old private `cleanStatLabel` body leaves every Swift test in the repo green
 * while restoring the exact bug. Same trap as `propsPrintTheServedVerdict4959.test.ts`.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That grouping changed. It must NOT: `group.type` is still the served `marketName`
 * and is still the key stat groups are built on, so two stats differing only in their
 * prefix remain two groups and #4857's ordering is untouched. The assertion below
 * pins that, because a "simplification" that keyed groups on the cleaned label would
 * silently merge them.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CARD = join(IOS_ROOT, "Components/PlayerPropsCardView.swift");
const HELPER = join(IOS_ROOT, "Utilities/PlayerPropsStatLabel.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass — the failure mode a source scan
// is most prone to, and the reason these are constants and not an inline join.
const present = [CARD, HELPER].every(existsSync);
const d = present ? describe : describe.skip;

d("#5113 — the stat label drops a prefix the reader can already see", () => {
  const card = () => stripComments(readFileSync(CARD, "utf8"));
  const helper = () => stripComments(readFileSync(HELPER, "utf8"));

  describe("THE MUTANTS: the view must delegate, and pass what the rule needs", () => {
    it("the label goes through PlayerPropsStatLabel, not a local prefix strip", () => {
      // Reverting to the old body is the whole regression.
      expect(card()).toMatch(/PlayerPropsStatLabel\.display\(/);
    });

    it("the view hands over BOTH teams — the matchup branch is dead without them", () => {
      expect(card()).toMatch(/homeTeam:\s*homeTeam/);
      expect(card()).toMatch(/awayTeam:\s*awayTeam/);
    });

    it("the view hands over the card's player — the Polymarket branch needs it", () => {
      // Passing nil here compiles and silently disables one of the two branches.
      expect(card()).toMatch(/cleanStatLabel\(group\.type,\s*player:\s*card\.name\)/);
    });

    it("the old inline prefix loop is gone from the view", () => {
      const body = card();
      const fn = body.match(/private func cleanStatLabel[\s\S]*?\n    \}/);
      expect(fn).not.toBeNull();
      expect(fn![0]).not.toMatch(/for prefix in \[/);
      expect(fn![0]).not.toMatch(/dropFirst/);
    });
  });

  describe("grouping is untouched — the stat key is still the served name", () => {
    it("stat groups are keyed on the raw marketName", () => {
      expect(card()).toMatch(
        /let statType = prop\.marketName\.trimmingCharacters\(in: \.whitespaces\)/,
      );
    });

    it("the cleaned label is never used as a key", () => {
      expect(card()).not.toMatch(/statType\s*=\s*.*cleanStatLabel/);
      expect(card()).not.toMatch(/statType\s*=\s*.*PlayerPropsStatLabel/);
    });
  });

  describe("the rule itself keeps its two guards", () => {
    it("a prefix must name BOTH sides, never one", () => {
      // `||` here would strip "Atlanta: Team Total Runs" — a team total losing its
      // team, which is a wrong label rather than a long one.
      expect(helper()).toMatch(
        /shares\(prefixTokens, with: homeTeam\)\s*&&\s*shares\(prefixTokens, with: awayTeam\)/,
      );
    });

    it("an empty remainder never wins — a card must not render a nameless stat", () => {
      expect(helper()).toMatch(/!remainder\.isEmpty/);
    });

    it("the token floor is 3, so joiners cannot satisfy a side", () => {
      // At 2, "vs" becomes a token and a prefix could match a team that merely
      // contains it.
      expect(helper()).toMatch(/\$0\.count >= 3/);
    });

    it("the player branch is case- and diacritic-insensitive", () => {
      // Production serves "Ronald Acuña Jr."; a byte compare would miss it.
      expect(helper()).toMatch(/\.caseInsensitive,\s*\.diacriticInsensitive/);
    });
  });
});
