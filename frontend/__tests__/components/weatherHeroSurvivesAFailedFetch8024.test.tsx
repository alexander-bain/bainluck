/**
 * #8024 — `/weather` stops replacing the WHOLE PAGE with "Something went wrong"
 * when one of its six endpoints fails.
 *
 * ═══ WHAT A READER SAW, production 2026-09-22 ═══
 *
 *   Something went wrong
 *   Reload page
 *
 * That was the entire page: docHeight 1201 at 390px, header and footer only, no
 * hero and no sections — while the footer still links Weather under CATEGORIES.
 * Reproduced here from the live stack, captured with a console probe (look.sh
 * photographs the page and cannot see a console, which is why it went
 * undiagnosed):
 *
 *   TypeError: Cannot read properties of null (reading 'map')
 *       at W (.../_next/static/chunks/app/weather/page-d6af43d727a9696e.js)
 *
 * ═══ THE MECHANISM, AND WHY THE GUARD LOOKED FINE ═══
 *
 *   const items   = liveItems?.length ? liveItems : null;
 *   const loading = !items && !error;
 *   ...
 *   {!loading && <div>{items.map(...)}</div>}          // ← threw
 *
 * `loading` is false in TWO states, not one: items exist, and **the fetch
 * failed**. `!loading` was standing in for "items exist" and is true in exactly
 * the state where `items` is null. The card to the RIGHT of these dots already
 * handled `error && !items` correctly — so the component knew about the error
 * state, and only this one branch inferred it from `loading` instead of asking
 * for it.
 *
 * `app/weather/page.tsx:19` wraps all six sections in ONE ErrorBoundary, so a
 * single throw in the first child takes the other five down with it. That is the
 * amplifier and it is why a one-line guard is a p1: the blast radius of any
 * unguarded null on this page is the whole page.
 *
 * ═══ WHAT THESE ASSERTIONS ARE BUILT TO KILL ═══
 *
 * The suite renders the REAL component through `renderToStaticMarkup`, so a
 * throw fails the test the way it failed the page — no mock of the component's
 * own logic. The four states are asserted together because the bug lives in the
 * relationship between them: any guard that is correct for three and wrong for
 * the fourth is the bug.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherHeroSurvivesAFailedFetch8024
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/* ── SWR is the only thing between WeatherHero and its payload ──────────── */
let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const WeatherHero = require("@/components/weather/WeatherHero").default;

/** A featured market in the shape `GET /api/weather/featured` serves. */
const MARKET = {
  q: "Where will it rain on Sep 22, 2026?",
  prob: 70,
  tag: "DAILY RAIN",
  src: "kalshi",
  leader: "New York City",
  history: [],
};

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function render(payload: unknown, error: unknown): string {
  swrPayload = payload;
  swrError = error;
  return renderToStaticMarkup(React.createElement(WeatherHero));
}

/** How many rotation dots the hero drew. */
function dotCount(markup: string): number {
  return (markup.match(/aria-label="Featured market \d+"/g) || []).length;
}

beforeEach(() => {
  swrPayload = undefined;
  swrError = undefined;
});

describe("#8024 — the state that took the page down", () => {
  it("DOES NOT THROW when the fetch fails (this is the whole bug)", () => {
    // Pre-fix this call raises
    // `TypeError: Cannot read properties of null (reading 'map')`.
    expect(() => render(undefined, new Error("Weather API error: 429"))).not.toThrow();
  });

  it("says what happened instead of drawing dots for markets it does not have", () => {
    const markup = render(undefined, new Error("Weather API error: 429"));
    expect(visibleText(markup)).toContain("Failed to load featured markets");
    expect(dotCount(markup)).toBe(0);
  });

  it("still renders the headline, so the reader gets a page and not a boundary", () => {
    const markup = render(undefined, new Error("Weather API error: 500"));
    expect(visibleText(markup)).toContain("What are the odds it rains tomorrow?");
  });
});

describe("#8024 — the other three states are unchanged", () => {
  it("loading: no data, no error — a skeleton and no dots", () => {
    const markup = render(undefined, undefined);
    expect(dotCount(markup)).toBe(0);
    expect(visibleText(markup)).not.toContain("Failed to load featured markets");
  });

  it("loaded: one dot per market, and the market is on screen", () => {
    const markup = render([MARKET, { ...MARKET, q: "Second question" }], undefined);
    expect(dotCount(markup)).toBe(2);
    expect(visibleText(markup)).toContain("Where will it rain on Sep 22, 2026?");
  });

  it("loaded-but-EMPTY (200 with []) is treated as nothing to show, not as an error", () => {
    // `[]` is falsy-by-length here, so `items` is null with no error set. This
    // is the third state that reaches the guard with a null, and the reason the
    // guard must ask about `items` rather than about `error`.
    const markup = render([], undefined);
    expect(dotCount(markup)).toBe(0);
    expect(visibleText(markup)).not.toContain("Failed to load featured markets");
  });
});

/**
 * 🔴 THE CONTROL. Every assertion above is satisfied by a component that never
 * draws dots at all — "render nothing" passes the whole suite. The loaded arm
 * carries the positive count, and this arm pins that the dots track the payload
 * rather than a constant, so a fix cannot be "delete the dots".
 */
describe("#8024 — control: the dots still follow the payload", () => {
  it("draws exactly as many dots as there are markets, at two different sizes", () => {
    expect(dotCount(render([MARKET], undefined))).toBe(1);
    expect(dotCount(render([MARKET, MARKET, MARKET], undefined))).toBe(3);
  });
});
