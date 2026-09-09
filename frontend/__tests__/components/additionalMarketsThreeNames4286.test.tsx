/**
 * #4286 — `Additional Markets` → `Other Markets` → `additional markets`.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Found paying #4167's post-merge LOOK on production `af3d8a56`, 390px,
 * `https://bainluck.com/events/15307197` (Angels 6 – Red Sox 1, Final). Once
 * #4167 had cleaned the section subtitle to the single word `settled`, this was
 * the top of the block, in full:
 *
 *     Additional Markets          <- the section heading
 *     settled
 *     ┌──────────────────────────
 *     │ Other Markets            <- the only card's title
 *     │ additional markets       <- that card's subtitle
 *     │
 *     │   Los Angeles A vs Boston: First 5 Innings
 *
 * Three names for one idea in four lines, before a single market appears.
 *
 * `Other Markets` is `FALLBACK_CATEGORY` — "gap K11", the bucket a row lands in
 * when no `CATEGORY_PATTERNS` entry claims it. This module's own header records
 * that on MLB it takes **100% of rows on 6 of 6 games**, so it is very often
 * the section's only card, and when it is, its title restates the heading and
 * its subtitle restates it again.
 *
 * ═══ 🔴 THIS IS NOT A NOTICE-34 FIX, AND MUST NOT BECOME ONE ═══
 *
 * It sits one line below #4167's notice-34 sweep and the temptation to treat it
 * the same way is obvious and wrong. Nothing removed here is diagnostic prose:
 * there is no coverage count, no method note, no limitation. These are
 * HEADINGS, and the judgement is that two of them name nothing the third has
 * not already named. A category that says something its title does not keeps
 * its subtitle, and that is asserted below, not assumed.
 *
 * ═══ THE SHAPE OF THE GUARD ═══
 *
 * The suppression is conditional — lone fallback only — so every case here is
 * paired with the case that must NOT suppress. A test that only proved the
 * absence would pass just as well against a render that dropped every card
 * title on the page.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { FALLBACK_CATEGORY, categorizeMarketName } from "../../lib/otherMarketGroups";
import type { GameMarketsResponse } from "../../lib/api";

const PM = "polymarket";

function payload(other: Array<Record<string, unknown>>): GameMarketsResponse {
  return { other } as unknown as GameMarketsResponse;
}

/**
 * Rows copied in shape from the production page this was found on: three-way
 * markets whose names match no `CATEGORY_PATTERNS` entry, so everything lands
 * in the fallback and the section renders exactly one card.
 *
 * 🔴 THREE outcomes per market, not two, and that is not decoration. A market
 * with exactly two complementary rows is classified as the win-probability
 * market by `findWinProbMarkets` and filtered out of this section entirely;
 * with fewer than three rows surviving, `buildMarketSection` returns no
 * categories at all. My first fixture was two-way and rendered an EMPTY string
 * — at which point every `not.toContain` below passed for the wrong reason.
 * The `SURVIVAL FIRST` assertions are what caught it, and they are why they
 * come first in every case.
 */
const FALLBACK_ONLY = [
  { market_name: "Los Angeles A vs Boston: First 5 Innings", outcome_name: "Los Angeles A wins first 5 innings", probability: 0.99, source: PM },
  { market_name: "Los Angeles A vs Boston: First 5 Innings", outcome_name: "Boston wins first 5 innings", probability: 0.01, source: PM },
  { market_name: "Los Angeles A vs Boston: First 5 Innings", outcome_name: "Tie", probability: 0.01, source: PM },
  { market_name: "Los Angeles A vs Boston: First 7 Innings", outcome_name: "Los Angeles A wins first 7 innings", probability: 0.99, source: PM },
  { market_name: "Los Angeles A vs Boston: First 7 Innings", outcome_name: "Boston wins first 7 innings", probability: 0.2, source: PM },
  { market_name: "Los Angeles A vs Boston: First 7 Innings", outcome_name: "Tie", probability: 0.03, source: PM },
];

/**
 * The same rows PLUS a market a pattern claims (`coin toss` → `Novelty Props`),
 * so the section renders two cards and the fallback is no longer alone.
 */
const FALLBACK_PLUS_SIBLING = [
  ...FALLBACK_ONLY,
  { market_name: "Los Angeles A vs Boston: Coin Toss", outcome_name: "Heads", probability: 0.5, source: PM },
  { market_name: "Los Angeles A vs Boston: Coin Toss", outcome_name: "Tails", probability: 0.48, source: PM },
  { market_name: "Los Angeles A vs Boston: Coin Toss", outcome_name: "Lands on edge", probability: 0.02, source: PM },
];

describe("#4286 — the model", () => {
  test("the fallback carries no subtitle, and a real category still does", () => {
    // THE POSITIVE CONTROL FOR THE WHOLE FILE. If `categorizeMarketName` ever
    // returned an empty subtitle for everything, every "no subtitle" assertion
    // below would pass while the page lost information. It does not.
    expect(categorizeMarketName("Los Angeles A vs Boston: First 5 Innings")).toEqual({
      category: FALLBACK_CATEGORY,
      subtitle: "",
    });
    expect(categorizeMarketName("Los Angeles A vs Boston: Coin Toss")).toEqual({
      category: "Novelty Props",
      subtitle: "fun markets",
    });
    // And the constant is still the string the render compares against, so a
    // rename cannot silently disable the suppression.
    expect(FALLBACK_CATEGORY).toBe("Other Markets");
  });
});

describe("#4286 — the lone fallback card stops naming the section again", () => {
  const html = renderToStaticMarkup(<SpecialEventMarkets data={payload(FALLBACK_ONLY)} />);

  test("the section heading is the only place the idea is named", () => {
    // SURVIVAL FIRST — an empty render satisfies every absence below.
    expect(html).toContain("Additional Markets");
    expect(html).toContain("First 5 Innings");
    expect(html).toContain("99%");

    // The two restatements are gone.
    expect(html).not.toContain("additional markets");
    expect(html).not.toContain("Other Markets");
  });

  test("`Additional Markets` appears exactly once", () => {
    // Keyed on the count, not on presence: the defect was a REPETITION, and an
    // assertion that the string is present cannot see a repetition at all.
    expect((html.match(/Additional Markets/g) ?? []).length).toBe(1);
    // Case-insensitively too, which is how the subtitle differed from it.
    expect((html.match(/additional markets/gi) ?? []).length).toBe(1);
  });
});

describe("#4286 — a fallback WITH a sibling keeps its title", () => {
  const html = renderToStaticMarkup(
    <SpecialEventMarkets data={payload(FALLBACK_PLUS_SIBLING)} />
  );

  test("both cards are named, because now the name distinguishes them", () => {
    // THE OTHER DIRECTION (gotcha #43). With two cards the fallback's title is
    // load-bearing — it is the only thing telling a reader which card is which
    // — so suppressing it here would be a worse bug than the one being fixed.
    expect(html).toContain("Novelty Props");
    expect(html).toContain(FALLBACK_CATEGORY);
    // The sibling keeps the subtitle that says something its title does not.
    expect(html).toContain("fun markets");
    // But the fallback's dead subtitle is still gone, in both arrangements.
    expect(html).not.toContain("additional markets");
  });
});
