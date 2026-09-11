/**
 * #4970 / D132 — "WIN PROBABILITY SOURCES" SAYS WHEN EACH SOURCE WAS LAST READ.
 *
 * ═══ WHAT A READER GOT ═══
 *
 * `/events/15310077/models` (Cubs–Pirates, live), 390px, read off production
 * 2026-09-11 20:14Z. Six source cards, each a name and a percentage:
 *
 *     kalshi       99.0%      0.1 min old
 *     betting      99.2%      0.3 min old
 *     stat_model      —       0.8 min old
 *     mlb             —       1.9 min old
 *     polymarket      —      39.1 min old
 *     espn         59.9%     97.2 min old
 *
 * ESPN's 59.9% sits two cards under Kalshi's 99.0% in the same weight and the
 * same ink, on a page subtitled "How each source calculates who will win", and
 * nothing on it says that one of those two numbers stopped moving an hour and
 * thirty-seven minutes ago. The per-SPORTSBOOK rows nested inside the Betting
 * card have carried a "2m ago" Status column for as long as they have existed;
 * the per-SOURCE numbers, which is what D132 calls the source rows, had none.
 *
 * ═══ WHY THIS MOUNTS THE PAGE INSTEAD OF READING THE FILE ═══
 *
 * The defect is in what a card PRINTS. `SourceComparisonRow`'s header states the
 * rule this follows: a render defect is not provable by grepping the file it was
 * printed from. So the page is mounted with its data mocked and the assertions
 * read the text a reader would read.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * A page that renders no source cards would satisfy "no card claims a false
 * age" trivially, so the card census is asserted first and every source is
 * required BY NAME. The three states are pinned separately, because the one
 * that is easy to lose is the third:
 *
 *   1. a FRESH source prints its age and is not muted;
 *   2. a STALE source prints its age and IS muted;
 *   3. a source with NO stamp prints NO age — it must not read as "just now".
 *
 * (3) is the whole reason `formatSourceAge` returns `null` rather than a word.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** 2026-09-11T20:14:00Z — the instant the specimen above was read. */
const NOW = Date.parse("2026-09-11T20:14:00.000Z");
const ago = (minutes: number) =>
  new Date(NOW - minutes * 60 * 1000).toISOString();

const EVENT = {
  id: 15310077,
  home_team: "Chicago Cubs",
  away_team: "Pittsburgh Pirates",
  status: "live",
  current_odds: { home_probability: 0.992 },
  win_probability_sources: {
    betting: {
      value: 0.992,
      display_name: "Sportsbooks",
      type: "market",
      color: "#111827",
      updated_at: ago(0.3),
    },
    kalshi: {
      value: 0.99,
      display_name: "Kalshi",
      type: "market",
      color: "#22c55e",
      updated_at: ago(0.1),
    },
    polymarket: {
      value: 0.97,
      display_name: "Polymarket",
      type: "market",
      color: "#3b82f6",
      updated_at: ago(39.1),
    },
    espn: {
      value: 0.599,
      display_name: "ESPN",
      type: "model",
      color: "#f97316",
      updated_at: ago(97.2),
    },
    // The third state: a source the payload carries with no stamp on it.
    stat_model: {
      value: 0.94,
      display_name: "Bain Luck Model",
      type: "model",
      color: "#a855f7",
    },
  },
};

const HISTORY = {
  points: 40,
  win_prob_sources: {
    kalshi: { display_name: "Kalshi", type: "market", color: "#22c55e", snapshot_count: 40 },
    polymarket: { display_name: "Polymarket", type: "market", color: "#3b82f6", snapshot_count: 40 },
    espn: { display_name: "ESPN", type: "model", color: "#f97316", snapshot_count: 40 },
    stat_model: { display_name: "Bain Luck Model", type: "model", color: "#a855f7", snapshot_count: 40 },
  },
};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: string | null) => {
    if (key === null) return { data: undefined, error: undefined };
    return {
      data: String(key).endsWith("/history") ? HISTORY : EVENT,
      error: undefined,
    };
  },
}));

jest.mock("@/lib/api", () => ({
  fetchEvent: jest.fn(),
  fetchEventHistory: jest.fn(),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import ModelsPage from "@/app/events/[id]/models/page";

function markup(): string {
  jest.useFakeTimers().setSystemTime(NOW);
  try {
    return renderToStaticMarkup(
      React.createElement(ModelsPage, { params: { id: "15310077" } }),
    );
  } finally {
    jest.useRealTimers();
  }
}

/** Every `data-source` on a source card, in render order. */
function cardSources(html: string): string[] {
  return [...html.matchAll(/data-testid="model-source-card" data-source="([^"]+)"/g)].map(
    (m) => m[1],
  );
}

/** The visible age text keyed by source, for cards that print one. */
function agesBySource(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of html.matchAll(
    /data-testid="model-source-age" data-source="([^"]+)"[^>]*>([^<]*)</g,
  )) {
    out[m[1]] = m[2];
  }
  return out;
}

describe("#4970 — the census first, so no assertion below can pass vacuously", () => {
  it("renders one card per source, every one of them by name", () => {
    const sources = cardSources(markup());
    expect(sources).toEqual(
      expect.arrayContaining([
        "betting",
        "kalshi",
        "polymarket",
        "espn",
        "stat_model",
      ]),
    );
    expect(sources.length).toBe(5);
  });

  it("still prints the numbers it printed before", () => {
    const html = markup();
    expect(html).toContain("99.2%"); // betting
    expect(html).toContain("99.0%"); // kalshi
    expect(html).toContain("59.9%"); // espn — the stale one
    expect(html).toContain("Chicago Cubs");
  });
});

describe("#4970 — each source says when it was last read", () => {
  it("SHIP: the fresh source and the 97-minute-old one no longer read alike", () => {
    const ages = agesBySource(markup());
    expect(ages.kalshi).toBe("just now");
    expect(ages.espn).toBe("1h ago");
    expect(ages.kalshi).not.toBe(ages.espn);
  });

  it("SHIP: every stamped source prints its own age", () => {
    const ages = agesBySource(markup());
    expect(ages.betting).toBe("just now");
    expect(ages.polymarket).toBe("39m ago");
    expect(ages.espn).toBe("1h ago");
  });

  it("SHIP: an UNSTAMPED source prints no age at all — not 'just now'", () => {
    const html = markup();
    const ages = agesBySource(html);
    // The card exists and shows its number...
    expect(cardSources(html)).toContain("stat_model");
    expect(html).toContain("94.0%");
    // ...and says nothing about when we read it.
    expect(ages.stat_model).toBeUndefined();
  });
});

describe("#4970 — a stale source is marked as one, in both directions", () => {
  it("flags past 30 minutes and does not flag inside it", () => {
    const html = markup();
    const flag = (source: string) =>
      new RegExp(
        `data-testid="model-source-card" data-source="${source}" data-source-stale="([^"]+)"`,
      ).exec(html)?.[1];

    expect(flag("espn")).toBe("true"); // 97.2 min
    expect(flag("polymarket")).toBe("true"); // 39.1 min
    expect(flag("kalshi")).toBe("false"); // 0.1 min
    expect(flag("betting")).toBe("false"); // 0.3 min
    // An undatable source is not a stale one — we cannot support that claim.
    expect(flag("stat_model")).toBe("false");
  });

  it("mutes the stale number and leaves the fresh one in primary ink", () => {
    const html = markup();
    // The muted class must appear on a percentage, not merely somewhere on the
    // page — `text-text-muted` is also the team-name line under every number.
    expect(html).toMatch(
      /class="text-lg font-bold text-text-muted"[^>]*>\s*59\.9%/,
    );
    expect(html).toMatch(
      /class="text-lg font-bold text-text-primary"[^>]*>\s*99\.0%/,
    );
  });
});
