/**
 * UX-P233 — THE RENDERED PAGE, not the helpers' return values (board item 11).
 *
 * `__tests__/lib/futuresBaselineLabels.test.ts` proves the labels. This file proves
 * the PAGE wears them, by SSR-rendering the real `app/futures/[id]/page.tsx`
 * against the verbatim production payload Alex reviewed.
 *
 * Both halves are needed. `movementLabel` had existed on `FuturesHero` for the
 * whole life of the component and **no caller ever passed it** — a correct label
 * helper that nothing renders is exactly the shape of defect this page keeps
 * producing (CERT-598 was a correct `pickHeroOutcome` beside a sort that never
 * asked it anything).
 *
 * ═══ ALEX'S DONE-BAR ═══
 *
 *     A reader can say what window each number is baselined on, without hovering
 *     anything.
 *
 * So the assertions below are about what is PAINTED next to each number, and the
 * sharpest one is negative: the word "24h" may not appear anywhere on this page,
 * because the same payload dates every row to 2026-08-28.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import market109441 from "../fixtures/uxp230_futures_109441.json";
import { movementExplanation } from "@/lib/futuresDetailDisplay";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = market109441;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_MARKET as any, error: null, isLoading: false, mutate: () => {} };
    }
    return { data: undefined, error: null, isLoading: false, mutate: () => {} };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({
    isPinned: () => false,
    togglePin: () => {},
    isMaxReached: false,
  }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FuturesDetailPage from "../../app/futures/[id]/page";
import { FuturesHero } from "../../components/FuturesHero";

function render(market: unknown, id: string): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

/**
 * Drop markup tags, leaving text.
 *
 * 🔴 A CHARACTER SCAN, NOT `replace(/<[^>]*>/g, "")`. CodeQL flagged the regex form
 * as **high severity** `js/incomplete-multi-character-sanitization`, and it is right
 * about the shape: a single-pass tag strip is the classic incomplete sanitizer,
 * because one pass over `<<a>script>` leaves a tag behind. Nothing untrusted flows
 * through this helper — it reads our own SSR output inside a test — but a new high
 * alert is a real CI gate, and "it is only a test" is not a reason to ship the
 * pattern people copy. A scan cannot be defeated by nesting.
 */
function stripTags(html: string): string {
  let out = "";
  let inTag = false;
  for (const ch of html) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out;
}

/** Text content of the element carrying a given `data-testid`, tags stripped. */
function testIdText(html: string, id: string): string | null {
  const m = new RegExp(`data-testid="${id}"[^>]*>([\\s\\S]*?)</`).exec(html);
  return m ? stripTags(m[1]).trim() : null;
}

/**
 * The page renders `last_updated` relative to the real clock, so a fixture banked
 * on 2026-08-28 only reads as "stale" while the wall clock is past 2026-08-29.
 * These tests are ABOUT staleness, so pin the clock rather than letting the answer
 * drift — a guard whose verdict depends on the day it runs is not a guard.
 */
const PINNED_NOW = new Date("2026-08-31T17:20:00Z");

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["nextTick", "setImmediate"] });
  jest.setSystemTime(PINNED_NOW);
});

afterAll(() => {
  jest.useRealTimers();
});

describe("UX-P233: every number on the futures page states its baseline", () => {
  test("the harness renders the real live table (positive control)", () => {
    // Every assertion below is about text being present or absent. A loading
    // shell would satisfy the negative ones vacuously. Prove the page first.
    const html = render(market109441, "109441");
    expect(html).toContain("All Outcomes");
    expect(html).toContain("Amazon");
  });

  test("🔴 the word '24h' appears NOWHERE on the page", () => {
    // The sharpest assertion in the file. The payload dates every outcome to
    // 2026-08-28, and CAL-P159 proved the field is a per-write delta that
    // freezes — so any surviving "24h" is a claim this very payload disproves.
    // The old sort control read "24h Change".
    const html = render(market109441, "109441");
    expect(html).not.toMatch(/24\s*h/i);
  });

  test("the hero's movement pill carries a window, and it is the last move", () => {
    const html = render(market109441, "109441");
    // The pill itself still shows the figure Alex saw.
    expect(testIdText(html, "hero-movement")).toContain("71.5 pts");
    // …and now says what it is baselined on.
    expect(testIdText(html, "hero-movement-window")).toBe("last move · Aug 28");
  });

  test("the table says once, at the top, when these prices were last taken", () => {
    const html = render(market109441, "109441");
    expect(testIdText(html, "market-as-of")).toBe("as of Aug 28");
  });

  test("the row's three numbers are each labelled", () => {
    const html = render(market109441, "109441");
    // "Open" was always labelled; these two were bare.
    expect(html).toContain(">Open<");
    expect(html).toContain(">Last move<");
    expect(html).toContain(">Latest<");
    // And the values themselves are untouched — this ship changes no arithmetic.
    expect(testIdText(html, "outcome-open")).toBe("14%");
    expect(testIdText(html, "outcome-change")).toBe("-71.5%");
  });

  test("the sort control names the field honestly", () => {
    const html = render(market109441, "109441");
    expect(html).toContain("Last move");
    expect(html).toContain("Probability");
  });

  test("the caption's baseline and the hero's are DIFFERENT, and both are stated", () => {
    // The pair Alex read as a contradiction: "↓ 71.5" over "Amazon up 13.5 pts
    // from opening". Both survive — they are both true — but a reader can now
    // see that one is the last move and the other is since opening.
    //
    // ⚠️ The caption is NOT asserted off this render, and the reason matters:
    // it lives inside the trend card and is gated on price history, which this
    // harness deliberately serves empty. Asserting it here would have needed a
    // history mock whose only job was to satisfy the assertion. Its text is
    // pinned by `movementExplanation` in the futuresDetailDisplay unit tests;
    // what this file owns is that the HERO now states a DIFFERENT window.
    const html = render(market109441, "109441");
    expect(testIdText(html, "hero-movement-window")).toContain("last move");

    const leader = (market109441.outcomes as { probability: number | null }[])[0];
    expect(movementExplanation(leader)).toContain("from opening");
    // The two windows really are different claims about the same outcome.
    expect(movementExplanation(leader)).toContain("up 13.5 pts");
    expect(testIdText(html, "hero-movement")).toContain("↓ 71.5 pts");
  });
});

describe("UX-P233: a FRESH market is not decorated with staleness it does not have", () => {
  const fresh = {
    ...market109441,
    outcomes: (market109441.outcomes as { last_updated: string }[]).map((o) => ({
      ...o,
      last_updated: "2026-08-31T16:00:00Z", // 80 minutes before the pinned clock
    })),
  };

  test("no as-of line — labelling a current price is noise, not honesty", () => {
    const html = render(fresh, "109441");
    expect(testIdText(html, "market-as-of")).toBeNull();
    expect(html).not.toContain("as of");
  });

  test("the movement pill still names its window, because the NOUN is not the clock", () => {
    // A per-write delta on a row written 80 minutes ago is still a per-write
    // delta. Freshness changes whether we can date it usefully, not what it is.
    const html = render(fresh, "109441");
    expect(testIdText(html, "hero-movement-window")).toBe("last move · Aug 31");
    expect(html).not.toMatch(/24\s*h/i);
  });
});

describe("UX-P233: BOTH hero renderings carry the window", () => {
  /**
   * 🔴 THE HERO HAS TWO RENDERINGS AND THE FIRST VERSION OF THIS GUARD MET ONLY ONE.
   *
   * `FuturesHero` paints an AMBIENT variant when it has >=3 sparkline points and a
   * PLAIN variant otherwise, and each writes its own movement markup. The page
   * harness above serves empty history, so it exercises the plain one only — a
   * mutation battery renaming the AMBIENT variant's hook survived every assertion
   * in this file. That is UX-P211's lesson exactly: *when a state changes how a
   * component renders, enumerate the renderings.*
   */
  const UP_CURVE = [0.1, 0.2, 0.3, 0.45, 0.6];

  test("the AMBIENT variant (with history) states the window", () => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="Which company ships first?"
        probability={0.27}
        outcomeName="Amazon"
        movement={-71.5}
        movementLabel="last move · Aug 28"
        sparklinePoints={UP_CURVE}
      />,
    );
    expect(testIdText(html, "hero-movement")).toContain("71.5 pts");
    expect(testIdText(html, "hero-movement-window")).toBe("last move · Aug 28");
  });

  test("the PLAIN variant (no history) states the window", () => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="Which company ships first?"
        probability={0.27}
        outcomeName="Amazon"
        movement={-71.5}
        movementLabel="last move · Aug 28"
      />,
    );
    expect(testIdText(html, "hero-movement")).toContain("71.5 pts");
    expect(testIdText(html, "hero-movement-window")).toBe("last move · Aug 28");
  });

  test("neither variant paints a naked window with no figure beside it", () => {
    // A label with no number is worse than no label: it describes nothing.
    for (const points of [UP_CURVE, undefined]) {
      const html = renderToStaticMarkup(
        <FuturesHero
          name="M"
          probability={0.27}
          movement={null}
          movementLabel="last move · Aug 28"
          sparklinePoints={points}
        />,
      );
      expect(testIdText(html, "hero-movement")).toBeNull();
      expect(testIdText(html, "hero-movement-window")).toBeNull();
    }
  });

  test("a SETTLED hero shows no movement pill and therefore no window", () => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="M"
        probability={0.21}
        outcomeName="Kai Havertz"
        movement={-71.5}
        movementLabel="last move · Aug 28"
        resolved
        resolvedWon
      />,
    );
    expect(testIdText(html, "hero-movement")).toBeNull();
    expect(testIdText(html, "hero-movement-window")).toBeNull();
  });
});

describe("UX-P233: a payload with no timestamps claims nothing in either direction", () => {
  const undated = {
    ...market109441,
    outcomes: (market109441.outcomes as object[]).map((o) => ({
      ...o,
      last_updated: null,
    })),
  };

  test("no as-of, no invented date, and the window is still named", () => {
    const html = render(undated, "109441");
    expect(testIdText(html, "market-as-of")).toBeNull();
    // Named but undated — we know WHAT the number is, not WHEN it was taken.
    expect(testIdText(html, "hero-movement-window")).toBe("last move");
    expect(html).not.toMatch(/24\s*h/i);
    // And nothing fabricated a day from the epoch or from "now".
    expect(html).not.toContain("Jan 1");
  });
});
