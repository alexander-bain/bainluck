/**
 * #7320 — the search ANSWERS card claimed certainty about an open question.
 *
 * ═══ WHAT WAS ON THE SCREEN ═══
 *
 * Production 2026-09-20 00:12Z, `/search?q=astros`, the ANSWERS card: a row
 * reading **`NRFI 100%`** over a served probability of `0.9995`, on a market
 * that does not close until Sep 26. `100%` to a reader is not "very likely",
 * it is **decided** — and we printed it over a question the market itself was
 * still pricing. The same expression printed `0%` on the other end, which says
 * "impossible" about an outcome someone is actively buying.
 *
 * `lib/probabilityDisplay.ts` exists to make exactly this render impossible and
 * states the rule in its own docblock: *rounding may never move a probability
 * across a boundary it is not on*. `SearchFamilyCard` did not import it.
 *
 * ═══ WHY THIS SUITE RENDERS THE COMPONENT ═══
 *
 * The defect was not in the rule — the rule was always right — it was in a
 * surface not CALLING the rule. A unit test of `formatProbabilityPercent` would
 * have passed on every day this bug was live. So the assertion has to be about
 * what the CARD emits, which is why these tests go through
 * `renderToStaticMarkup` (this repo has no `@testing-library/react`; static
 * markup is the established idiom here and is sufficient — nothing below
 * depends on an event or an effect).
 *
 * ═══ SCOPE, STATED SO IT IS NOT OVERREAD ═══
 *
 * The whole-frontend version of this class is #3892 (171 sites, 116 web) and is
 * deliberately NOT pinned anywhere — a baseline that spans the frontend is one
 * nobody can move, which is the reasoning `eventPageInlinePercentInventory`
 * records for its own bounded scope. This suite pins the SEARCH surface only,
 * the same way that one pins the event page.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import { leaderLabel } from "@/components/searchFamilyDisplay";
import type { FuturesFamily } from "@/lib/types";

/**
 * The production specimen's shape. `probability` is the only field that varies
 * across these tests; everything else is held still so a failure names the
 * number and not the fixture.
 */
const cardWithLeaderAt = (probability: number | null): FuturesFamily =>
  ({
    family_key: "entity:astros",
    label: "Astros",
    headline: {
      id: 61545178,
      name: "Houston Astros - No Runs First Inning",
      outcome_count: 2,
      resolution_date: null,
      top_outcomes: [
        { id: 231932734, name: "NRFI", probability, movement: null, american_odds: null },
      ],
    },
    members: [],
    more_count: 0,
    member_count: 1,
  }) as unknown as FuturesFamily;

/**
 * What the reader sees, with markup removed and entities decoded.
 *
 * THE DECODE IS LOAD-BEARING, not tidying. The marker this whole suite is about
 * is `>` / `<`, and React escapes both in text content — the card emits
 * `&gt;99%`. Comparing against the raw markup would have failed the two
 * assertions that matter while the fix was working perfectly, which is the
 * failure that would tempt the next reader to weaken the assertion instead of
 * the helper. Tags are stripped FIRST, so the decode cannot manufacture one.
 */
const cardText = (probability: number | null): string =>
  renderToStaticMarkup(<SearchFamilyCard family={cardWithLeaderAt(probability)} />)
    .replace(/<[^>]*>/g, " ")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();

describe("#7320 — the search card's percentage obeys the boundary rule", () => {
  test("the census is not vacuous: the card renders its leader's percentage at all", () => {
    // Without this, every assertion below could be satisfied by a card that
    // renders no percentage whatsoever — the failure mode that makes a
    // "does not contain 100%" test worthless.
    const text = cardText(0.27);
    expect(text).toContain("NRFI");
    expect(text).toContain("27%");
  });

  test("🔴 THE FILED DEFECT: a live 0.9995 prints >99%, never a bare 100%", () => {
    const text = cardText(0.9995);
    expect(text).toContain(">99%");
    // The claim that was on the screen. Stated as its own assertion because
    // ">99%" containing "99%" makes a naive `toContain` check pass either way.
    expect(text).not.toMatch(/(^|[^>\d])100%/);
  });

  test("the other arm of the same expression: a live 0.0004 prints <1%, never 0%", () => {
    const text = cardText(0.0004);
    expect(text).toContain("<1%");
    expect(text).not.toMatch(/(^|[^<\d])0%/);
  });

  test("the boundaries themselves are still printed plainly — settled means settled", () => {
    // The rule is about values STRICTLY inside (0, 1). A graded outcome is
    // genuinely certain and must not be softened into ">99%", or the fix would
    // trade a false certainty for a false doubt.
    expect(cardText(1)).toContain("100%");
    expect(cardText(1)).not.toContain(">99%");
    expect(cardText(0)).toContain("0%");
    expect(cardText(0)).not.toContain("<1%");
  });

  test("ordinary values are untouched", () => {
    // The blast radius: a fix to the two ends must not move the middle.
    for (const [prob, printed] of [
      [0.27, "27%"],
      [0.5, "50%"],
      [0.994, "99%"],
      [0.006, "1%"],
    ] as const) {
      expect(cardText(prob)).toContain(printed);
    }
  });

  test("a row with no probability still renders, and claims nothing", () => {
    const text = cardText(null);
    expect(text).toContain("outcome");
    expect(text).not.toContain("%");
  });
});

describe("#7320 — the exported twin cannot reintroduce the defect", () => {
  // `leaderLabel` is NOT what the card renders — measured, its only importer is
  // this module's test — but it is exported and composes the same sentence, so
  // the next caller would have inherited the bare round. Pinned so that stays
  // fixed rather than being quietly re-spelt.
  test("leaderLabel routes through the contract at both ends", () => {
    const market = (probability: number) =>
      ({ top_outcomes: [{ id: 1, name: "NRFI", probability }] }) as never;
    expect(leaderLabel(market(0.9995))).toBe("NRFI >99%");
    expect(leaderLabel(market(0.0004))).toBe("NRFI <1%");
    // and the ordinary case the original test already pinned
    expect(leaderLabel(market(0.27))).toBe("NRFI 27%");
  });
});

/**
 * The bounded inventory for this surface — the same construction, and the same
 * reasoning, as `__tests__/lib/eventPageInlinePercentInventory.test.ts`.
 *
 * `Math.round(x * 100)` is not banned: it is right for a bar width and for a
 * points delta, and wrong for a printed probability. So the survivors are
 * pinned BY FILE with a reason, and the count fails in BOTH directions — too
 * many means a new site, too few means one was routed and the baseline was left
 * behind, which is how a guard stops describing the code.
 */
const INLINE = /Math\.round\([^;\n]*?\*\s*100\b/;

const SEARCH_SURFACE: Record<string, { count: number; because: string }> = {
  "components/SearchFamilyCard.tsx": {
    count: 0,
    because:
      "nothing left to permit — the one site was #7320 itself and it now calls " +
      "formatProbabilityPercent",
  },
  "components/searchFamilyDisplay.ts": {
    count: 1,
    because:
      "`movementArrow`'s magnitude, which is a 24h delta in POINTS and not a " +
      "probability — the boundary rule makes no claim about it. It is a " +
      "UX-P048 question (movement crosses into points exactly once, in " +
      "`movementPoints`) and deliberately NOT changed here: routing it would " +
      "alter the printed integer at exact .5 on a negative move, which is a " +
      "different ship from the one #7320 names",
  },
  "app/search/page.tsx": {
    count: 0,
    because: "the page composes cards; it prints no percentage of its own",
  },
};

describe("#7320 — the search surface's inline percent sites are pinned", () => {
  test("the scan is not vacuous", () => {
    // A regex that stopped matching would turn every count below into a pass.
    expect(INLINE.test("const w = Math.round(p * 100);")).toBe(true);
    expect(INLINE.test("formatProbabilityPercent(p)")).toBe(false);
  });

  test.each(Object.entries(SEARCH_SURFACE))(
    "%s keeps exactly the sites it is permitted",
    (file, { count }) => {
      const hits = readFileSync(file, "utf8")
        .split("\n")
        .filter((line) => INLINE.test(line)).length;
      expect(hits).toBe(count);
    },
  );

  test("the card reaches the contract, and by importing it rather than copying it", () => {
    const src = readFileSync("components/SearchFamilyCard.tsx", "utf8");
    expect(src).toContain('from "@/lib/probabilityDisplay"');
  });
});
