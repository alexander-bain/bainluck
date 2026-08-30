/**
 * UX-P187 — THE CROSS-SOURCE SPOTLIGHT STOPS INVENTING DISAGREEMENTS.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/politics` ends on a section headed "⇄ Cross-source spotlight · Markets
 * where sources disagree". Each card names a question, prints Kalshi's number
 * beside Polymarket's, and reports the gap:
 *
 *     ⚠ 56.5pt spread
 *     How many House seats will Democrats win in Louisiana?
 *     KALSHI 92.5%          POLYMARKET 36.0%
 *     Merged: 64.3%             Disagree by 56.5pp
 *
 * The two sources were not 56.5 points apart. The 92.5% is Kalshi's price for
 * Democrats winning EXACTLY 1 SEAT; the 36.0% is Polymarket's price for NINE.
 * Both numbers are each market's LEADING outcome, and the leaders were
 * different outcomes, so the spread — and the "Merged: 64.3%", an average of
 * two different futures — were arithmetic on unrelated quantities.
 *
 * ═══ THE READER COUNT ═══
 *
 * Measured on production 2026-08-30 over every cross-source pair the route
 * finds, not just the eight it serves (`pair_census` in the fixture):
 *
 *     122  pairs found
 *      98  price DIFFERENT leading outcomes  ← the spread is an artifact
 *      95  share no outcome name at all      ← not comparable in any direction
 *      27  comparable
 *
 * Of the 8 rows served, 7 compared different outcomes. The section renders the
 * top FOUR, and three of those four were wrong. That is not bad luck: the list
 * is sorted by descending delta, and a mis-aligned pair produces a LARGER
 * number than a real disagreement, so the ranking systematically promoted the
 * artifacts and buried the real ones below the cut.
 *
 * It cut the other way too. "Rio de Janeiro Governor winner?" served a 0.7pt
 * spread that read as near-perfect agreement, while the two sources priced
 * Eduardo Paes at 94.0% and 63.8% — a real 30.2pt gap the page was hiding.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * The BEFORE is the verbatim production body, banked in
 * `backend/tests/fixtures/uxp187_politics_cross_source.json` before a line of
 * the fix was written, with each row's two real leading outcomes recorded
 * alongside it. Every assertion renders the SHIPPED `CrossSourceCard` and
 * reads the text a PERSON sees. There is no source-level arm — a guard that
 * greps the file stays green when someone deletes the call site.
 *
 *   npx jest --testPathPatterns=politicsCrossSourceOutcomeCapture
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import type { CrossSourceMatch } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-var-requires */
const { CrossSourceCard, CrossSourceSpotlight } =
  require("@/components/politics/CrossSourceSpotlight");
const LegacyCrossSourceCard =
  require("../fixtures/uxp187CrossSourceCardLegacy").default;
/* eslint-enable @typescript-eslint/no-var-requires */

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const banked = JSON.parse(
  fs.readFileSync(
    path.join(
      REPO,
      "backend",
      "tests",
      "fixtures",
      "uxp187_politics_cross_source.json",
    ),
    "utf8",
  ),
);

type BankedRow = CrossSourceMatch & {
  _kalshi_leader: string | null;
  _poly_leader: string | null;
  _leaders_agree: boolean;
  _shared_outcome_names: string[];
};

const SERVED_BEFORE = banked.served_before as BankedRow[];
const CENSUS = banked.pair_census as Record<string, number>;
const AFTER_TOP8 = banked.after_top8 as {
  q: string;
  outcome: string;
  k: number;
  p: number;
  delta: number;
}[];

const LOUISIANA = SERVED_BEFORE.find((r) => r.q.includes("Louisiana"))!;
const ESTONIA = SERVED_BEFORE.find((r) => r.q.includes("Estonia"))!;

function markup(
  Component: React.ComponentType<{ market: CrossSourceMatch }>,
  market: CrossSourceMatch,
): string {
  return renderToStaticMarkup(React.createElement(Component, { market }));
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(m: string): string {
  return m
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

/** COUNT the caption element, don't just look for its text.
 *
 *  React renders `{undefined}` as nothing, so a card that emitted the caption
 *  UNGUARDED would put a real, empty, margin-bearing `<p>` on the page and a
 *  text-only probe would see a clean card. The element is what has to be
 *  absent, not merely its contents. (UX-P186 paid for this one.) */
function captionCount(m: string): number {
  return (m.match(/<p [^>]*style="[^"]*margin-top:-6px/g) || []).length;
}

/* ═══ 1 · the banked BEFORE really is the broken state ═════════════════ */

describe("UX-P187 · the fixture is genuinely the defect", () => {
  test("no served row said which outcome its two numbers priced", () => {
    for (const row of SERVED_BEFORE) expect(row).not.toHaveProperty("outcome");
  });

  test("7 of the 8 served rows compared two DIFFERENT outcomes", () => {
    expect(SERVED_BEFORE).toHaveLength(8);
    expect(SERVED_BEFORE.filter((r) => r._leaders_agree)).toHaveLength(1);
  });

  test("three of the FOUR the section renders were wrong", () => {
    // CrossSourceSpotlight slices to 4. The rendered set is the reader count.
    const rendered = SERVED_BEFORE.slice(0, 4);
    expect(rendered.filter((r) => !r._leaders_agree)).toHaveLength(3);
  });

  test("the Louisiana card is the one from the docstring", () => {
    expect(LOUISIANA.kalshi).toBe(92.5);
    expect(LOUISIANA.poly).toBe(36.0);
    expect(LOUISIANA.delta).toBe(56.5);
    expect(LOUISIANA._kalshi_leader).toContain("exactly 1 seats");
    expect(LOUISIANA._poly_leader).toBe("9");
    // and the two markets have no outcome in common at all, in either
    // direction — this pair is not repairable, only droppable.
    expect(LOUISIANA._shared_outcome_names).toEqual([]);
  });

  test("the population census is the one the docstring quotes", () => {
    expect(CENSUS).toMatchObject({
      pairs_total: 122,
      leaders_agree: 24,
      leaders_differ: 98,
      no_shared_outcome: 95,
      comparable: 27,
    });
    // The two partitions must account for every pair, or one of them is a
    // count of something else.
    expect(CENSUS.leaders_agree + CENSUS.leaders_differ).toBe(
      CENSUS.pairs_total,
    );
    expect(CENSUS.comparable + CENSUS.no_shared_outcome).toBe(
      CENSUS.pairs_total,
    );
    // Every leader-agreeing pair is comparable by construction; the surplus is
    // the pairs rescued by aligning on a lower-ranked shared outcome.
    expect(CENSUS.comparable).toBeGreaterThanOrEqual(CENSUS.leaders_agree);
  });
});

/* ═══ 2 · prove the instrument ═════════════════════════════════════════ */

describe("UX-P187 · the legacy card is wrong in exactly this way", () => {
  test("the shipped-before card printed both numbers and named neither", () => {
    const text = visibleText(
      markup(LegacyCrossSourceCard, {
        ...LOUISIANA,
        outcome: "Democrats win exactly 1 seat",
      }),
    );
    expect(text).toContain("92.5%");
    expect(text).toContain("36.0%");
    // Handed the outcome on a plate, the legacy card still cannot say it.
    expect(text).not.toContain("Democrats win exactly 1 seat");
    expect(captionCount(markup(LegacyCrossSourceCard, LOUISIANA))).toBe(0);
  });

  test("...and it averaged two different futures into one 'Merged'", () => {
    const text = visibleText(markup(LegacyCrossSourceCard, LOUISIANA));
    expect(text).toContain("Merged: 64.3%");
    expect(text).toContain("56.5pp");
  });
});

/* ═══ 3 · the ship, rendered ═══════════════════════════════════════════ */

describe("UX-P187 · every number on the card says what it prices", () => {
  const AFTER: CrossSourceMatch = {
    q: "Next President of Estonia?",
    outcome: "Ülle Madise",
    kalshi: 97.5,
    poly: 34.6,
    delta: 62.9,
    category: "presidential",
    kalshi_market_id: 59165073,
    poly_market_id: 57305363,
  };

  test("the card names the outcome both sources price", () => {
    const text = visibleText(markup(CrossSourceCard, AFTER));
    expect(text).toContain("Next President of Estonia?");
    expect(text).toContain("Ülle Madise");
    expect(text).toContain("97.5%");
    expect(text).toContain("34.6%");
  });

  test("the name tracks the payload — it is not hard-coded", () => {
    // Vacuity companion. Without this, a card that printed a constant string
    // would satisfy the assertion above.
    const other = visibleText(
      markup(CrossSourceCard, { ...AFTER, outcome: "Alar Karis" }),
    );
    expect(other).toContain("Alar Karis");
    expect(other).not.toContain("Ülle Madise");
  });

  test("a bare Yes is still named — on THIS surface it is the whole point", () => {
    // The Khamenei row compared a Kalshi timing bracket against Polymarket's
    // "No". Suppressing "Yes" as uninformative (which is the right call on the
    // weather hero) would leave a reader unable to tell a Yes-vs-Yes card from
    // the Yes-vs-No one that started all this.
    const text = visibleText(
      markup(CrossSourceCard, {
        ...AFTER,
        q: "Will another country leave OPEC in 2026?",
        outcome: "Yes",
        kalshi: 30.5,
        poly: 11.5,
        delta: 19.0,
      }),
    );
    expect(text).toContain("Yes");
    expect(text).toContain("30.5%");
  });

  test("a pre-deploy cached payload renders no caption AND no empty element", () => {
    // /api/politics is served from an hourly precompute, so for up to an hour
    // after the deploy the body has no `outcome` key at all. The card must
    // degrade to what it looked like before, not to a blank gap.
    const { outcome: _dropped, ...cached } = AFTER;
    const m = markup(CrossSourceCard, cached as CrossSourceMatch);
    expect(visibleText(m)).toContain("97.5%");
    expect(captionCount(m)).toBe(0);
  });

  test("the caption is one element, present exactly once, when named", () => {
    // The companion to the check above: if the matcher ever stops matching,
    // BOTH the presence and the absence assertions would read 0 and pass.
    expect(captionCount(markup(CrossSourceCard, AFTER))).toBe(1);
  });
});

/* ═══ 4 · the section, and what it is made of after the fix ════════════ */

describe("UX-P187 · the spotlight still has something to show", () => {
  test("dropping the incomparable pairs does not empty the section", () => {
    // 27 comparable pairs against a 4-card grid. Suppression is only the right
    // answer if the honest supply outlasts it, and it does by a wide margin.
    expect(banked.after_available).toBe(27);
    expect(AFTER_TOP8).toHaveLength(8);
  });

  test("every row the fix serves names an outcome and prices only that", () => {
    for (const row of AFTER_TOP8) {
      expect(typeof row.outcome).toBe("string");
      expect(row.outcome.trim()).not.toBe("");
      expect(row.delta).toBeCloseTo(Math.abs(row.k - row.p), 1);
    }
  });

  test("the ranking is by TRUE delta, so the real gaps come first", () => {
    const deltas = AFTER_TOP8.map((r) => r.delta);
    expect([...deltas].sort((a, b) => b - a)).toEqual(deltas);
    // Estonia's real 62.9 leads; Louisiana's fake 56.5 is gone entirely.
    expect(AFTER_TOP8[0].q).toBe("Next President of Estonia?");
    expect(AFTER_TOP8.some((r) => r.q.includes("Louisiana"))).toBe(false);
  });

  test("the fix surfaces a real gap the old ranking was HIDING", () => {
    // Rio served delta 0.7 — near-perfect agreement — while the two sources
    // were 30.2 points apart about Eduardo Paes.
    const rio = AFTER_TOP8.find((r) => r.q.includes("Rio de Janeiro"))!;
    expect(rio.outcome).toBe("Eduardo Paes");
    expect(rio.delta).toBeCloseTo(30.2, 1);
  });

  test("the grid renders four cards and each one is captioned", () => {
    const rows: CrossSourceMatch[] = AFTER_TOP8.map((r, i) => ({
      q: r.q,
      outcome: r.outcome,
      kalshi: r.k,
      poly: r.p,
      delta: r.delta,
      category: "presidential",
      kalshi_market_id: i,
      poly_market_id: 1000 + i,
    }));
    const m = renderToStaticMarkup(
      React.createElement(CrossSourceSpotlight, { matches: rows }),
    );
    expect(captionCount(m)).toBe(4);
    const text = visibleText(m);
    for (const row of AFTER_TOP8.slice(0, 4)) {
      expect(text).toContain(row.outcome);
    }
  });

  test("an empty match list still renders nothing at all", () => {
    expect(
      renderToStaticMarkup(
        React.createElement(CrossSourceSpotlight, { matches: [] }),
      ),
    ).toBe("");
  });
});

/* ═══ 5 · the call site ════════════════════════════════════════════════ */

describe("UX-P187 · /politics still renders the section", () => {
  // Everything above drives the extracted component directly, which is the
  // only way to render it at all — but a component guard stays green when
  // someone deletes the CALL. Two narrow positive assertions on the page,
  // not a blunt source-level scan: an over-broad `not.toContain` arm fails on
  // a correct file.
  const page = fs.readFileSync(
    path.join(FRONTEND, "app", "politics", "page.tsx"),
    "utf8",
  );

  test("the page imports the extracted component", () => {
    expect(page).toContain(
      'from "@/components/politics/CrossSourceSpotlight"',
    );
  });

  test("...and mounts it against the payload's cross_source", () => {
    expect(page).toMatch(
      /<CrossSourceSpotlight\s+matches=\{data\.cross_source\}\s*\/>/,
    );
  });

  test("the extracted card is no longer declared inside the route file", () => {
    // A Next.js route file may only export the reserved names, so a copy left
    // behind here would be invisible to every test in this file while being
    // the thing that actually renders.
    expect(page).not.toContain("function CrossSourceCard(");
  });
});
