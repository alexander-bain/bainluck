/**
 * UX-P273 / #2674 — THE RECESSION CARD PRINTS THE QUESTION IT IS ANSWERING.
 *
 * ═══ WHAT THIS IS ═══
 *
 * The card's headline question was a **string literal** in the page —
 * "Recession by end of 2026" — sitting above `t.recession.main_prob`, a number
 * the backend assigned from whichever binary recession market its theme loop
 * saw last, on a query with no ORDER BY. Nothing bound the two. Measured on
 * production 2026-09-02 the card read **13%**, which is market 109350 "Will
 * the IMF declare a global recession before 2027?" at 12.5% — while the market
 * the label actually asks about read 12.0% and was not on the card.
 *
 * The backend half of the repair (guard:
 * `backend/tests/test_economics_recession_headline_2674.py`) chooses the
 * headline deliberately and publishes that market's own question as `main_q`.
 * THIS file guards the half a user can see: that the page renders `main_q`
 * rather than a literal, and renders nothing at all when there is no question.
 *
 * ═══ WHY EVERY CLAIM HERE IS AN EQUALITY OR A NEGATIVE ═══
 *
 * The obvious assertion is vacuous. `"US recession by end of 2026?"` CONTAINS
 * `"Recession by end of 2026"` case-insensitively, so
 * `expect(text).toContain("recession by end of 2026")` passes on the fix AND
 * on the bug — the exact `toContain`-is-a-prefix trap ux/1011 hit on a
 * singular/plural fix. Worse, the old literal is a plausible market name, so a
 * page that ignored `main_q` entirely could still look right.
 *
 * So the headline is read out of a `data-testid` span and compared with `===`,
 * and the "no literal survives" claim is asserted as a `not.toContain` against
 * a payload whose question is deliberately NOTHING like the old label.
 *
 * ⚠️ Anchor note: the assertions select on `data-testid="recession-headline-q"`,
 * not on the Tailwind classes. Two other cards on this page carry the exact
 * same `text-[11px] font-bold tracking-[0.12em] ... uppercase` label classes
 * ("Quarterly GDP growth expectations", "Housing markets"), so a class-based
 * selector would pick up siblings and a restyle would break the guard.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EconomicsPage = require("@/app/economics/page").default;

/** No default on `payload` — an arm whose whole job is to pass a degenerate
 *  value cannot have the parameter defaulted out from under it (ux/1012). */
function render(payload: unknown, error: unknown = undefined): string {
  swrPayload = payload;
  swrError = error;
  return renderToStaticMarkup(React.createElement(EconomicsPage));
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** The rendered headline question, or null when the card prints none. */
function headlineQuestion(markup: string): string | null {
  const m = markup.match(
    /data-testid="recession-headline-q"[^>]*>([^<]*)</,
  );
  return m ? m[1].trim() : null;
}

/**
 * Whether a headline NUMBER is on the card.
 *
 * ⚠️ This deliberately does NOT test for the `data-testid`. The first version
 * did, and it was vacuous in the direction that matters: master has no testid
 * at all, so "the block is absent" read TRUE on the broken page for the wrong
 * reason — the marker was missing, not the block. `ProbNum` at size 64 is the
 * headline and nothing else on this card uses that size, so the font-size is
 * the honest discriminator and it exists in both arms.
 */
function headlineNumberIsPresent(markup: string): boolean {
  return /font-size:\s*64px|fontSize:64/.test(markup);
}

const OLD_HARDCODED_LABEL = "Recession by end of 2026";

/* ── Payloads ─────────────────────────────────────────────────────────────── */

function econ(recession: Record<string, unknown>) {
  return {
    total_markets: 100,
    updated_at: "2026-09-02T12:00:00Z",
    cross_source: [],
    by_source: {},
    themes: { recession: { count: 8, gdp_quarters: [], ...recession } },
  };
}

/** What the fixed backend publishes for today's production pool. */
const SERVED_FIXED = econ({
  main_prob: 12.0,
  main_q: "US recession by end of 2026?",
  main_market_id: 113012,
  side_markets: [
    { q: "Recession this year?", prob: 7.0, src: "kalshi", delta: null, market_id: 108622 },
    { q: "Recession in 2027?", prob: 27.5, src: "kalshi", delta: null, market_id: 12924898 },
  ],
});

/** A question sharing NO words with the old literal, so a page still printing
 *  the literal cannot be mistaken for one rendering the payload. */
const SERVED_UNRELATED = econ({
  main_prob: 31.0,
  main_q: "Will unemployment top 6% before the midterms?",
  main_market_id: 999,
  side_markets: [],
});

/** No binary recession market in the pool — the backend publishes nulls. */
const SERVED_EMPTY = econ({
  main_prob: null,
  main_q: null,
  main_market_id: null,
  side_markets: [
    { q: "Recession in 2027?", prob: 27.5, src: "kalshi", delta: null, market_id: 12924898 },
  ],
});

/* ── The seed is real ─────────────────────────────────────────────────────── */

describe("UX-P273 · the fixtures actually reach the recession card", () => {
  test("the recession section renders at all", () => {
    const text = visibleText(render(SERVED_FIXED));
    expect(text).toContain("GDP & Recession");
    expect(text).toContain("The big macro question");
  });

  test("the headline span is present and extractable", () => {
    // If this regex ever stops matching, every equality below reads `null`
    // and would silently agree with a `null` expectation.
    expect(headlineQuestion(render(SERVED_FIXED))).not.toBeNull();
  });
});

/* ── The ship ─────────────────────────────────────────────────────────────── */

describe("UX-P273 · the headline question comes from the payload", () => {
  test("the card prints the served question verbatim", () => {
    expect(headlineQuestion(render(SERVED_FIXED))).toBe(
      "US recession by end of 2026?",
    );
  });

  test("a completely different question is printed just as faithfully", () => {
    // The load-bearing arm. A page still printing the literal fails here even
    // though it would pass a `toContain` against SERVED_FIXED.
    expect(headlineQuestion(render(SERVED_UNRELATED))).toBe(
      "Will unemployment top 6% before the midterms?",
    );
  });

  test("the old hardcoded label does not survive anywhere on the page", () => {
    const text = visibleText(render(SERVED_UNRELATED));
    expect(text).not.toContain(OLD_HARDCODED_LABEL);
  });

  test("the question and the number are rendered as one unit", () => {
    // #2674's screen was 13% under a label describing another market. Both
    // come from `main_*` now, so the page cannot show one without the other.
    const markup = render(SERVED_UNRELATED);
    expect(headlineQuestion(markup)).toBe(
      "Will unemployment top 6% before the midterms?",
    );
    // `ProbNum` emits the value and the "%" as separate elements, so the
    // stripped text reads "31 %". Matched with \s* rather than asserting a
    // glued "31%" that the component never produces.
    expect(visibleText(markup)).toMatch(/\b31\s*%/);
  });

  test("the question is printed in full, not clipped", () => {
    // Truncating a question can change what it asks, which is the one thing
    // this card must not do. Deliberately not `slice(0, N)`d.
    const long =
      "Will the National Bureau of Economic Research declare a US recession beginning before the end of 2026?";
    const markup = render(
      econ({ main_prob: 4.0, main_q: long, main_market_id: 7, side_markets: [] }),
    );
    expect(headlineQuestion(markup)).toBe(long);
  });
});

/* ── Fail closed ──────────────────────────────────────────────────────────── */

describe("UX-P273 · no question means no headline", () => {
  test("a null question prints no headline block at all", () => {
    const markup = render(SERVED_EMPTY);
    expect(headlineNumberIsPresent(markup)).toBe(false);
  });

  test("a null question does not fall back to a confident 0%", () => {
    // The old code rendered `main_prob || 0`, so an absent number printed a
    // confident "0%" under a hardcoded question — a number the site does not
    // hold, answering a question nothing selected. Asserted against the
    // rendered "0 %" rather than only against the label, so this arm fails on
    // the NUMBER as well as on the literal.
    const markup = render(SERVED_EMPTY);
    const text = visibleText(markup);
    expect(text).not.toMatch(/\b0\s*%/);
    expect(text).not.toContain(OLD_HARDCODED_LABEL);
    expect(headlineQuestion(markup)).toBeNull();
  });

  test("the rest of the card still renders when the headline is absent", () => {
    // Fail closed on the headline, NOT on the section (#2215's class).
    const text = visibleText(render(SERVED_EMPTY));
    expect(text).toContain("Recession in 2027?");
  });
});

/* ── CONTROLS — green on master too ───────────────────────────────────────── */

describe("UX-P273 · controls", () => {
  test("CONTROL (green on master too): side rows print their own question", () => {
    // This is the convention the headline was the sole exception to: all nine
    // MarketRow call sites already render `q` from the payload.
    const text = visibleText(render(SERVED_FIXED));
    expect(text).toContain("Recession this year?");
    expect(text).toContain("Recession in 2027?");
  });

  test("CONTROL (green on master too): the section header is unchanged", () => {
    const text = visibleText(render(SERVED_FIXED));
    expect(text).toContain("The big macro question");
  });

  test("CONTROL (green on master too): an absent recession theme renders no section", () => {
    const text = visibleText(
      render({
        total_markets: 0,
        updated_at: "2026-09-02T12:00:00Z",
        cross_source: [],
        by_source: {},
        themes: {},
      }),
    );
    expect(text).not.toContain("The big macro question");
  });
});
