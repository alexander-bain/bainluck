/**
 * #4306 — a single probability drawn beside a two-name title describes the side
 * named FIRST, asserted by reading the Swift and by re-running its arithmetic.
 *
 * `SearchView.searchEventRow` built its title away-first and drew
 * `homeProbability` beside it, unlabelled, so every scheduled row published the
 * market backwards: 6 of 6 live US Open rows on 2026-09-09, worst case an 86%
 * drawn beside a name priced at 13.8%. `DiscoverEventCard.shareMessage` did the
 * same in prose, and that sentence leaves the app.
 *
 * 🔴 THIS FILE IS IN JEST BECAUSE CI COMPILES NO SWIFT (#4302). The behavioural
 * proof is `BainLuckTests/LoneProbabilityNamesItsSideTests.swift`, which runs the
 * real functions — and which no pipeline runs. A Swift-only guard for a
 * Swift-only defect passes standing notices 13, 18, 28 and 32 alike while red.
 * So the rule is pinned twice: executed there, scanned here.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { swiftCode, swiftCodeKeepingStrings, swiftFunctionBody } from "../helpers/swiftSource";
import { renderedDuelPercents } from "@/lib/renderedPercent";

const REPO_ROOT = join(__dirname, "../../..");
const APP_ROOT = join(REPO_ROOT, "ios/Bain Luck/Bain Luck");

const SEARCH_VIEW = join(APP_ROOT, "Views/SearchView.swift");
const DISCOVER_CARD = join(APP_ROOT, "Components/DiscoverEventCard.swift");
const RENDERED_PERCENT = join(APP_ROOT, "Utilities/RenderedPercent.swift");
const SHARE_URLS = join(APP_ROOT, "Utilities/ShareURLs.swift");

const code = (path: string) => swiftCode(readFileSync(path, "utf8"));

function slice(path: string, declaration: string, source: string): string {
  const found = swiftFunctionBody(source, declaration);
  if (found === null) {
    throw new Error(
      `\`${declaration}\` is gone from ${path}. This guard watches that function; ` +
        `if it was renamed, repoint the guard — do not delete it.`,
    );
  }
  return found;
}

/** The function body with comments AND string bodies gone — for identifier bans. */
function body(path: string, declaration: string): string {
  return slice(path, declaration, code(path));
}

/** The function body with the string bodies kept — for assertions about the text drawn. */
function drawnText(path: string, declaration: string): string {
  return slice(path, declaration, swiftCodeKeepingStrings(readFileSync(path, "utf8")));
}

describe("the rule lives in one place", () => {
  it("firstNamedSideNumber returns the AWAY side of the duel pair", () => {
    const src = code(RENDERED_PERCENT);
    expect(src).toContain("func firstNamedSideNumber(");

    const fn = body(RENDERED_PERCENT, "func firstNamedSideNumber(");
    // The whole rule is which index of `duelPercents` is read. `[0]` is away —
    // pinned as the ARGUMENT of the rule and not as a nearby token, because a
    // guard satisfied by the mere presence of `duelPercents(` would pass on the
    // inverted `[1]`.
    expect(fn).toContain("duelPercents(");
    expect(fn).toContain(")[0]");
    expect(fn).not.toContain(")[1]");
  });
});

describe("the search row draws the side it named first", () => {
  const fn = () => body(SEARCH_VIEW, "private func searchEventRow(");

  it("goes through the shared rule", () => {
    expect(fn()).toContain("firstNamedSideNumber(");
  });

  it("draws the number the rule returned, and nothing it derived itself", () => {
    const slice = fn();
    expect(slice).toContain(
      "formatProbability(firstNamed.probability, renderedPercent: firstNamed.percent)",
    );
    // The defect, exactly: a home-side probability handed to the formatter.
    expect(slice).not.toMatch(/formatProbability\(\s*(odds\.)?home/);
    // And no second rounding beside a rule that already decided the integer.
    // Read from the string-KEEPING text: see the note on the share-message
    // assertion below — Swift rounds inside string interpolations, and the
    // identifier-ban text cannot see in there.
    expect(drawnText(SEARCH_VIEW, "private func searchEventRow(")).not.toContain(".rounded()");
  });

  it("still keys its title and its score off the same side", () => {
    const drawn = drawnText(SEARCH_VIEW, "private func searchEventRow(");
    expect(drawn).toContain("\\(event.awayTeam) vs \\(event.homeTeam)");
    expect(drawn).toContain("\\(away) - \\(home)");
  });
});

describe("the sentence that leaves the app", () => {
  const fn = () => body(DISCOVER_CARD, "private var shareMessage:");

  it("is built by the shared helper from the card's own duel pair", () => {
    const slice = fn();
    expect(slice).toContain("eventShareMessage(");
    expect(slice).toContain("duelPercents(");
    // #5363 — the away half is still the card's own `duel[0]` and is still
    // never re-rounded here; it is now WITHHELD on a draw-priced sport, so it
    // reaches the call through a local the rule gates. Both halves pinned: the
    // gate itself, and that what survives it is `duel[0]` and nothing else.
    expect(slice).toMatch(
      /let awayPercent = DrawPricedWinner\.sportPricesADraw\(event\.sport\) \? nil : duel\[0\]/
    );
    expect(slice).toContain("awayPercent: awayPercent");
    expect(slice).toContain("homePercent: duel[1]");
  });

  /**
   * 🔴 READ FROM THE STRING-KEEPING TEXT, AND THIS IS NOT A DETAIL. The sentence
   * this replaced did its rounding INSIDE a string interpolation:
   *
   *     "\(away) vs \(home) — \(Int((prob * 100).rounded()))% on Bain Luck"
   *
   * `swiftCode` deletes string bodies, so an assertion written against it cannot
   * see `Int(` or `.rounded()` there at all. The first draft of this guard was
   * written that way and the mutant that restores the old sentence killed only
   * one of its three assertions — this one passed on the defect it names.
   */
  it("quotes no number it rounded itself", () => {
    const drawn = drawnText(DISCOVER_CARD, "private var shareMessage:");
    expect(drawn).not.toContain(".rounded()");
    expect(drawn).not.toMatch(/Int\(/);
  });

  it("names a side in front of every percent it prints", () => {
    // Both percents or neither: half a duel is the unattributed form again.
    expect(body(SHARE_URLS, "func eventShareMessage(")).toContain(
      "guard let awayPercent, let homePercent else",
    );
    // Every `%` in the emitted sentence is preceded by an interpolated name.
    expect(drawnText(SHARE_URLS, "func eventShareMessage(")).toContain(
      "\\(away) \\(awayPercent)% vs \\(home) \\(homePercent)%",
    );
  });
});

describe("the arithmetic the Swift table asserts", () => {
  // The six production rows the Swift suite pins, re-run through web's arm of
  // the same contract. If the two runtimes ever disagree about which integer the
  // first-named side gets, this fails in CI even though the Swift never runs.
  const SPECIMENS: Array<{ away: string; awayProbability: number; homeProbability: number; expected: number }> = [
    { away: "Elena Rybakina", awayProbability: 0.72, homeProbability: 0.28, expected: 72 },
    { away: "Coco Gauff", awayProbability: 0.645, homeProbability: 0.355, expected: 65 },
    { away: "Alexander Blockx", awayProbability: 0.395, homeProbability: 0.605, expected: 39 },
    { away: "Botic van de Zandschulp", awayProbability: 0.138, homeProbability: 0.862, expected: 14 },
    { away: "Jessica Pegula", awayProbability: 0.38, homeProbability: 0.62, expected: 38 },
    { away: "Ben Shelton", awayProbability: 0.72, homeProbability: 0.28, expected: 72 },
  ];

  it.each(SPECIMENS)(
    "$away is drawn at $expected%",
    ({ awayProbability, homeProbability, expected }) => {
      expect(renderedDuelPercents(awayProbability, homeProbability)[0]).toBe(expected);
    },
  );

  it("would have disagreed with the old home-side reading on every row", () => {
    for (const row of SPECIMENS) {
      const old = Math.round(row.homeProbability * 100);
      expect(renderedDuelPercents(row.awayProbability, row.homeProbability)[0]).not.toBe(old);
    }
  });

  it("keeps rows that can tell the two sides apart", () => {
    // The control from the Swift suite, repeated: a specimen set where both sides
    // round alike, or where the first-named side is always the favourite, passes
    // an inverted implementation.
    const favourite = SPECIMENS.filter((r) => r.awayProbability > r.homeProbability);
    expect(favourite.length).toBeGreaterThan(0);
    expect(favourite.length).toBeLessThan(SPECIMENS.length);
    for (const row of SPECIMENS) {
      expect(Math.round(row.awayProbability * 100)).not.toBe(Math.round(row.homeProbability * 100));
      expect(row.awayProbability + row.homeProbability).toBeCloseTo(1, 3);
    }
  });
});
