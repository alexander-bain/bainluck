/**
 * #8019 — A LADDER CARD NAMES ITS OWN SUBJECT, SO THIRTY-TWO STACKS STOP READING
 * AS ONE ANONYMOUS WALL.
 *
 * ═══ WHAT THE READER SAW ═══
 *
 * `/futures/58728338` — "Pro Football: Team Wins in First 8 Weeks", resolving
 * Nov 10 2026, in season and being read now — draws ONE ladder per NFL team and
 * every rung in every one of them reads `≥ N`:
 *
 *      ≥ 1   100%          ≥ 1   100%
 *      ≥ 2   100%          ≥ 2    95%
 *      ≥ 3    96%          ≥ 3    86%
 *      …                   …
 *
 * Thirty-two of those, consecutively, with no heading, crest or caption between
 * them — and the first two rungs of the first two cards are identical, so a
 * reader cannot even tell the blocks apart by their numbers. The page's hero
 * says "Baltimore" and its trend caption says "Buffalo", above a wall that names
 * neither. (authority/968's phone-width production LOOK, 2026-09-22 12:5xZ.)
 *
 * ═══ IT IS A RENDER DEFECT: THE PAYLOAD CARRIES THE WHOLE LABEL ═══
 *
 * Every one of the 242 outcome names is prefixed with its team, and the backend
 * groups on exactly that prefix — `GET /api/futures/groups/kalshi:KXNFLWINSWEEK-26W8`
 * serves 32 entries keyed `buffalo: #+ wins in first # weeks`, whose rungs are
 * named `Buffalo: 1+ wins in first 8 weeks` and so on. The stem is a SCOPE KEY,
 * which #7398 rightly refuses to print, and `group_title` is the page's own `<h1>`,
 * which #7398 also rightly refuses — so both refusals fired correctly and the
 * result was a blank heading. The team survived only in the rung names, and
 * `buildThresholdRungs` throws them away in favour of `≥ N`.
 *
 * `GROUP` below is that served payload for three of the 32 teams, ids, prices and
 * all.
 *
 * ═══ THE CONTROL THAT SEPARATES THIS FROM "PRINT A HEADING ALWAYS" ═══
 *
 * 🔴 `TREASURY` is #7398's own live specimen shape: a scope-key stem, a
 * `group_title` that echoes the H1, and rung names that carry no `"<subject>: "`
 * prefix. It must STILL print no heading. A change that made the title row
 * unconditional, or that fell back to the stem, satisfies every "Buffalo is on
 * the page" assertion in this file and reddens only this one.
 *
 * Measured on production 2026-09-22 before building: over a random 40 grouped
 * open markets, 11 ladder groups derive no subject and are untouched; over the 9
 * open boards whose outcomes all read `"<x>: <rung>"`, 217 of 217 derive one.
 * The fallback only ever fills a heading that is blank today, so no ladder that
 * reads correctly now can change.
 *
 * Assertions read the page's own SSR markup, not a helper call, because the
 * helper alone cannot see the defect: `thresholdLadderTitle` gained an optional
 * fourth argument, and a call site that does not pass it compiles, type-checks
 * and leaves every card exactly as blank as before. Dropping `outcomes.map(o =>
 * o.name)` from `app/futures/[id]/page.tsx` reddens the first three tests.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;
let ACTIVE_GROUP: unknown = null;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const idle = { data: undefined, error: null, isLoading: false, mutate: () => {} };
    if (key == null) return idle;
    const tag = Array.isArray(key) ? key[0] : key;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (tag === "futures-market") return { ...idle, data: ACTIVE_MARKET as any };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (tag === "futures-group") return { ...idle, data: ACTIVE_GROUP as any };
    return idle;
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FuturesDetailPage from "../app/futures/[id]/page";
import { ladderSubjectHeading, thresholdLadderTitle } from "@/lib/futuresLadder";

/* ────────────────────────────── the harness ────────────────────────────── */

const SEEN = "2026-09-22T12:55:00.000Z";

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["nextTick"] }).setSystemTime(new Date(SEEN));
});
afterAll(() => {
  jest.useRealTimers();
});

function render(market: unknown, group: unknown, id: string): string {
  ACTIVE_MARKET = market;
  ACTIVE_GROUP = group;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

/**
 * The page's markup with tags removed and runs of whitespace collapsed — what a
 * reader's eye walks, in order. Deliberately NOT a class or testid read: the
 * heading is a plain span with styling classes, and pinning those would make a
 * restyle look like a regression while a heading rendered somewhere useless
 * would still pass.
 */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/* ───────────────────────────── the specimens ───────────────────────────── */

let nextOutcomeId = 219814414;

function rungs(team: string, prices: number[]) {
  return prices.map((probability, i) => ({
    outcome_id: nextOutcomeId++,
    name: `${team}: ${i + 1}+ wins in first 8 weeks`,
    probability,
    threshold_value: i + 1,
    threshold_unit: "",
    threshold_direction: "above",
    source: "kalshi",
  }));
}

/** `GET /api/futures/groups/kalshi:KXNFLWINSWEEK-26W8`, three of its 32 entries. */
const GROUP = {
  group_id: "kalshi:KXNFLWINSWEEK-26W8",
  group_title: "Pro Football: Team Wins in First 8 Weeks",
  group_type: "kalshi_event",
  market_count: 1,
  markets: [],
  sources: ["kalshi"],
  threshold_groups: {
    "buffalo: #+ wins in first # weeks": rungs("Buffalo", [1, 1, 0.96, 0.895, 0.71, 0.39]),
    "pittsburgh: #+ wins in first # weeks": rungs("Pittsburgh", [1, 0.95, 0.86, 0.65, 0.38, 0.16]),
    "cleveland: #+ wins in first # weeks": rungs("Cleveland", [1, 0.83, 0.53, 0.24, 0.08, 0.02]),
  },
};

const FOOTBALL = {
  id: 58728338,
  name: "Pro Football: Team Wins in First 8 Weeks",
  status: "open",
  source: "kalshi",
  category: "championship",
  llm_sport_category: "football",
  market_type: "field",
  mutually_exclusive: false,
  group_id: "kalshi:KXNFLWINSWEEK-26W8",
  bookmakers: ["kalshi"],
  resolution_date: "2026-11-10T00:00:00+00:00",
  updated_at: SEEN,
  outcomes: [],
};

/**
 * #7398's shape, and the reason this fix is a fallback rather than a preference:
 * a scope-key stem, a `group_title` that IS the H1, and rungs whose names carry
 * no subject. Nothing here may print a heading.
 */
const TREASURY_TITLE = "How low will the 30Y US Treasury yield get by Sep 30, 2026?";
const TREASURY_GROUP = {
  group_id: "kalshi:KX30YRDIRLM-26SEP30L",
  group_title: TREASURY_TITLE,
  group_type: "kalshi_event",
  market_count: 1,
  markets: [],
  sources: ["kalshi"],
  threshold_groups: {
    "# or below": [4.2, 4.4, 4.6, 4.8].map((v, i) => ({
      outcome_id: 900000 + i,
      name: `${v}% or below`,
      probability: 0.9 - i * 0.2,
      threshold_value: v,
      threshold_unit: "%",
      threshold_direction: "below",
      source: "kalshi",
    })),
  },
};

const TREASURY = {
  ...FOOTBALL,
  id: 60653756,
  name: TREASURY_TITLE,
  llm_sport_category: null,
  group_id: "kalshi:KX30YRDIRLM-26SEP30L",
};

/* ──────────────────────────────── the page ──────────────────────────────── */

describe("the futures ladder card names the team it is about", () => {
  test("🔴 the live defect: the Buffalo ladder is headed 'Buffalo'", () => {
    const text = visibleText(render(FOOTBALL, GROUP, "58728338"));
    // The market name carries no team, and the rungs render as `≥ N`, so the
    // ONLY way this word can reach the page is as the card's heading.
    expect(text).toContain("Buffalo");
  });

  test("🔴 sibling ladders are told apart, each heading immediately above its own rungs", () => {
    const text = visibleText(render(FOOTBALL, GROUP, "58728338"));
    // Buffalo and Pittsburgh both open `≥ 1 100%`; before the fix the two blocks
    // were indistinguishable. Order is the assertion that a heading is doing a
    // heading's job rather than sitting in a footer.
    for (const team of ["Buffalo", "Pittsburgh", "Cleveland"]) {
      expect(text).toContain(team);
    }
    expect(text.indexOf("Buffalo")).toBeLessThan(text.indexOf("Pittsburgh"));
    expect(text.indexOf("Pittsburgh")).toBeLessThan(text.indexOf("Cleveland"));
  });

  test("the rungs keep their own labels — a heading was added, nothing was relabelled", () => {
    const text = visibleText(render(FOOTBALL, GROUP, "58728338"));
    expect(text).toContain("≥ 1");
    expect(text).toContain("≥ 6");
    // The full outcome name is the payload's, not the reader's: a card headed
    // "Buffalo" whose rungs each repeated "Buffalo: 4+ wins in first 8 weeks"
    // would be a different, worse fix.
    expect(text).not.toContain("wins in first 8 weeks");
  });

  test("🔴 CONTROL — #7398's Treasury ladder still prints no heading at all", () => {
    const text = visibleText(render(TREASURY, TREASURY_GROUP, "60653756"));
    expect(text).not.toContain("# or below");
    // The H1 is the question; it must appear exactly once, not again over the rungs.
    expect(text.split(TREASURY_TITLE).length - 1).toBe(1);
    expect(text).toContain("≤ 4.2%");
  });
});

/* ─────────────────────────────── the rule ──────────────────────────────── */

describe("ladderSubjectHeading", () => {
  test("every name sharing one prefix yields that prefix", () => {
    expect(
      ladderSubjectHeading(["Buffalo: 1+ wins", "Buffalo: 2+ wins", "Buffalo: 3+ wins"]),
    ).toBe("Buffalo");
  });

  test("🔴 disagreeing prefixes yield nothing — a mixed group has no one subject", () => {
    expect(ladderSubjectHeading(["Buffalo: 1+ wins", "Pittsburgh: 2+ wins"])).toBeUndefined();
  });

  test("🔴 one name without the separator disqualifies the whole group", () => {
    // Otherwise a single un-prefixed rung would be silently filed under a
    // subject that does not describe it.
    expect(ladderSubjectHeading(["Buffalo: 1+ wins", "2+ wins"])).toBeUndefined();
    expect(ladderSubjectHeading(["Buffalo: 1+ wins", null])).toBeUndefined();
  });

  test("🔴 a name that OPENS with the separator has an empty subject, not a blank heading", () => {
    expect(ladderSubjectHeading([": 1+ wins", ": 2+ wins"])).toBeUndefined();
  });

  test("only the FIRST separator splits, so a subject may not swallow a colon in the rung", () => {
    expect(ladderSubjectHeading(["Buffalo: at 7:30: yes", "Buffalo: at 8:30: yes"])).toBe(
      "Buffalo",
    );
  });

  test("no names at all is no subject", () => {
    expect(ladderSubjectHeading([])).toBeUndefined();
    expect(ladderSubjectHeading(undefined)).toBeUndefined();
  });
});

describe("thresholdLadderTitle falls back to the subject, and only into a blank", () => {
  const NAMES = ["Buffalo: 1+ wins", "Buffalo: 2+ wins"];

  test("🔴 the defect's own arguments: scope key + H1-echoing group_title → 'Buffalo'", () => {
    expect(
      thresholdLadderTitle(
        "buffalo: #+ wins in first # weeks",
        "Pro Football: Team Wins in First 8 Weeks",
        "Pro Football: Team Wins in First 8 Weeks",
        NAMES,
      ),
    ).toBe("Buffalo");
  });

  test("🔴 a heading that already prints is NOT replaced by the subject", () => {
    // The fallback's whole safety argument. Preferring the subject would silently
    // re-title every cross-market ladder that reads correctly today.
    expect(
      thresholdLadderTitle("above #", "US Open 2026 — total aces", "Will Alcaraz hit 30+ aces?", NAMES),
    ).toBe("US Open 2026 — total aces");
  });

  test("🔴 a subject that echoes the page H1 is refused like any other heading", () => {
    expect(
      thresholdLadderTitle("above #", null, " buffalo ", ["Buffalo: 1+", "Buffalo: 2+"]),
    ).toBeUndefined();
  });

  test("🔴 a subject that is itself a scope key is refused too", () => {
    expect(
      thresholdLadderTitle("above #", null, "Some question?", ["group:kx: 1+", "group:kx: 2+"]),
    ).toBeUndefined();
  });

  test("omitting the argument entirely leaves #7398's answers untouched", () => {
    expect(thresholdLadderTitle("# or below", null, "Some question?")).toBeUndefined();
  });
});
