/**
 * #6778 — the chamber control card stops printing a split that adds to 101.
 *
 * ═══ WHAT A READER SAW, production 2026-09-17 ═══
 *
 * `/politics`, Congressional section, 390px (`artifacts/ux-1315/politics-mid-390.png`):
 *
 *     SENATE CONTROL      42% R   vs   59% D
 *
 * The payload prices the pair as an EXACT complement —
 * `chamber_control.senate = { gop: 41.5, dem: 58.5, market_id: 114419 }`, still
 * live at 2026-09-17 23:52Z — and `ChamberControlCard` rounded each side with its
 * own `Math.round`. JS rounds `.5` half-up, so both sides rounded UP at once and
 * the card claimed 101 points of probability.
 *
 * This is verbatim the class `renderedDuelPercents` was written for (#2831 /
 * UX-P114: a complement pair is rounded ONCE, together) and the one #6766 had
 * just removed from the market cards a few hundred pixels down this same page.
 * The chamber card was never wired to the contract.
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IT IS BUILT THIS WAY ═══
 *
 * THE ARM MOUNTS THE REAL PAGE. `ChamberControlCard` is a module-local of a Next
 * route file and must stay that way (a page may export only the allowlisted route
 * names — #5953 pays for that in a typecheck error), so this renders the DEFAULT
 * export and finds the card by its `/futures/<market_id>` anchor, exactly as the
 * #6766 battery does. Nothing in `app/` was rearranged to make the test possible.
 *
 * THE ASSERTION IS THE EXACT PAIR, NOT THE SUM. A fix that reached for
 * `renderedCardPercents` directly would round index 0 and derive index 1 — on
 * `41.5 / 58.5` that is `42 / 58`, which sums to 100 and is still wrong, because
 * the number that survives rounding must be the FAVOURITE whatever position it
 * arrives in. A sum-only assertion passes that mutant. So both sides are named.
 *
 * BOTH DIRECTIONS AND THE BAR ARE ASSERTED, because the risk of wiring a
 * normaliser into a card is what it takes with it: a NON-complement house pair
 * must keep its two independent numbers (normalizing `30 / 55` would invent 15
 * points), and the bar must keep drawing on the RAW values — it draws the split,
 * it does not print it.
 *
 *   TZ=UTC npx jest --testPathPatterns=chamberControlRoundsItsPairOnce6778
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { ChamberControl, PoliticsData } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__,
    error: undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

import PoliticsPage from "@/app/politics/page";

/* ── Reading the rendered page the way a person reads the screen ─────────── */

/**
 * The visible text of the card linking to `/futures/<id>`.
 *
 * Cut from its own anchor to the next anchor, which is what bounds a card on
 * this page: every card is a `<Link>` wrapper. Returns ALL matches — an empty
 * list means the card is not on the page, which the caller asserts on rather
 * than on an empty string ("absent" and "printed nothing" are different facts).
 *
 * 🔴 ONE PASS over the tag strip; no entity table is needed here because the
 * chamber card prints only digits, `%`, `R`, `D` and `vs`, but the pass must
 * stay single so it can never feed its own output back in (`js/double-escaping`,
 * the HIGH alert CodeQL raised on #6766's first push).
 */
function cardTexts(markup: string, marketId: number): string[] {
  const out: string[] = [];
  const needle = `href="/futures/${marketId}"`;
  for (let at = markup.indexOf(needle); at >= 0; at = markup.indexOf(needle, at + 1)) {
    const next = markup.indexOf('href="/futures/', at + 1);
    out.push(
      markup
        .slice(at, next < 0 ? markup.length : next)
        .replace(/<[^>]*>/g, " ")
        .replace(/\s+/g, " ")
        .trim(),
    );
  }
  return out;
}

/** Every whole-or-one-decimal percent the card prints, in order. */
function printedPercents(text: string): number[] {
  return (text.match(/(?<!\d)(\d{1,3}(?:\.\d)?)%/g) || []).map(parseFloat);
}

/** The bar widths the card draws, in order — a `width:NN%` inline style. */
function barWidths(markup: string, marketId: number): number[] {
  const at = markup.indexOf(`href="/futures/${marketId}"`);
  if (at < 0) return [];
  const next = markup.indexOf('href="/futures/', at + 1);
  const slice = markup.slice(at, next < 0 ? markup.length : next);
  return (slice.match(/width:\s*([\d.]+)%/g) || []).map((m) =>
    parseFloat(m.replace(/[^\d.]/g, "")),
  );
}

/* ── Specimens, in the shape the route actually serves ───────────────────── */

/** The defect's own specimen, read from production 2026-09-17 23:52Z. */
const SENATE: ChamberControl = { gop: 41.5, dem: 58.5, market_id: 114419 };

/**
 * The SAME pair with the sides swapped, so the favourite is now on the left.
 * A fix that simply always rounds the R side DOWN passes the arm above and
 * fails this one.
 */
const SENATE_GOP_LEADS: ChamberControl = { gop: 58.5, dem: 41.5, market_id: 114420 };

/**
 * A pair that is NOT a complement — 85 points between two sides that do not
 * answer one question. Normalizing it would invent 15 points of probability,
 * so both numbers must survive untouched.
 */
const HOUSE_INDEPENDENT: ChamberControl = { gop: 30, dem: 55, market_id: 114421 };

function politicsPayload(
  senate: ChamberControl | null,
  house: ChamberControl | null,
): PoliticsData {
  return {
    total_markets: 1,
    updated_at: "2026-09-17T23:52:00+00:00",
    themes: {
      presidential: {
        count: 0,
        headline_q: null,
        candidates: [],
        has_dual_source: false,
        kalshi_market_id: null,
        poly_market_id: null,
        side_markets: [],
      },
      // `count > 0` is what gates the Congressional section; the chamber row is
      // inside it, so a zero here would render an empty page and pass everything.
      congressional: {
        count: 1,
        markets: [],
        chamber_control: { senate, house },
        senate_map: null,
      },
      gubernatorial: { count: 0, markets: [] },
      policy: { count: 0, markets: [] },
      scotus: { count: 0, markets: [] },
      international: { count: 0, markets: [] },
      other: { count: 0, markets: [] },
    },
    cross_source: [],
    by_source: { kalshi: 1, polymarket: 1 },
  };
}

function renderWith(payload: PoliticsData): string {
  (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__ = payload;
  return renderToStaticMarkup(React.createElement(PoliticsPage));
}

/* ═══ The chamber card, rendered ══════════════════════════════════════════ */

describe("/politics chamber control rounds its complement pair once, together", () => {
  const markup = renderWith(politicsPayload(SENATE, HOUSE_INDEPENDENT));

  it("renders both chamber cards (so the arms below cannot pass on an empty page)", () => {
    expect(cardTexts(markup, SENATE.market_id)).toHaveLength(1);
    expect(cardTexts(markup, HOUSE_INDEPENDENT.market_id)).toHaveLength(1);
  });

  it("prints 41% R vs 59% D on the pair that printed 101", () => {
    const [text] = cardTexts(markup, SENATE.market_id);
    // Both sides named, not just the sum: `42 / 58` also sums to 100 and is the
    // answer a fix reaching for `renderedCardPercents` directly would give.
    expect(printedPercents(text)).toEqual([41, 59]);
    // The number the card used to print, named so this cannot pass by accident.
    expect(text).not.toContain("42%");
  });

  it("keeps the favourite whole when the R side is the one that leads", () => {
    const swapped = renderWith(politicsPayload(SENATE_GOP_LEADS, null));
    const [text] = cardTexts(swapped, SENATE_GOP_LEADS.market_id);
    expect(printedPercents(text)).toEqual([59, 41]);
  });

  it("CONTROL — a non-complement pair keeps both served numbers", () => {
    const [text] = cardTexts(markup, HOUSE_INDEPENDENT.market_id);
    // 30 + 55 = 85. The card says so, because the two sides are not one question
    // and there is no total to normalize to.
    expect(printedPercents(text)).toEqual([30, 55]);
  });

  it("CONTROL — the bar still draws on the RAW values, not the printed ones", () => {
    // The bar is the split, not the label: `41.5 / 58.5` is the honest geometry
    // even where the printed pair is `41 / 59`.
    expect(barWidths(markup, SENATE.market_id)).toEqual([41.5, 58.5]);
    expect(barWidths(markup, HOUSE_INDEPENDENT.market_id)).toEqual([30, 55]);
  });
});
