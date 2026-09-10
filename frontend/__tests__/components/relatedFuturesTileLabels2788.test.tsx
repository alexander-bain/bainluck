// THE TILE MUST SHOW IT — #2788 (render half).
//
// `labelDisambiguation2788.test.ts` proves the function is right. Only this file
// proves the prop tile PRINTS its answer, which is the codebase's own standing
// lesson (#2060): a contract test cannot tell a rendered field from a declared
// one, and wrapping a branch in `{false && (` leaves every string intact.
//
// The payload below is the real one — `GET /api/events/15301243/related-futures`
// on `842e6167` / v4020, 2026-09-03 — reduced to the three rows that reach the
// OTHER group. Everything that decides the group ("game_prop", a market name
// with no colon, a probability inside the 0.02–0.98 band) is carried verbatim,
// because a fixture that missed any of those would render a different section
// and prove nothing.
//
// BOTH DIRECTIONS PER GOTCHA #43: the render case has a sibling asserting a
// group of ordinary player names comes out with its names intact.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

let payload: Record<string, unknown> = {};
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: payload, error: undefined, isLoading: false }),
}));
jest.mock("@/lib/api", () => ({
  fetchRelatedFutures: jest.fn(),
  formatProbability: (p: number | null) =>
    p === null || p === undefined ? "--" : `${Math.round(p * 100)}%`,
}));

import RelatedFutures from "@/components/RelatedFutures";
import { DEFAULT_VISIBLE_CHARS } from "@/lib/labelDisambiguation";

const QUARTERS =
  "Will Carlos Alcaraz advance to the Quarterfinals in Men's Singles at the 2026 US Open?";
const SEMIS =
  "Will Carlos Alcaraz advance to the Semifinals in Men's Singles at the 2026 US Open?";

function prop(
  marketName: string,
  outcomeName: string,
  probability: number,
  outcomeId: number,
) {
  return {
    market_id: 900 + outcomeId,
    outcome_id: outcomeId,
    market_name: marketName,
    outcome_name: outcomeName,
    clean_label: marketName,
    probability,
    display_category: "game_prop",
    market_tier: 5,
    source: "kalshi",
    all_sources: ["kalshi"],
    relevance_score: 1,
    resolution_date: null,
    probability_change_24h: null,
    rank: null,
    matched_player: null,
  };
}

function setPayload(futures: Array<ReturnType<typeof prop>>) {
  payload = {
    event_id: 15301243,
    home_team: "Wu Yibing",
    away_team: "Carlos Alcaraz",
    home_team_futures: [],
    away_team_futures: futures,
    series_markets: [],
    total_count: futures.length,
    event_status: "scheduled",
    box_score: null,
  };
}

function render(): string {
  return renderToStaticMarkup(
    <RelatedFutures
      eventId={15301243}
      homeTeam="Wu Yibing"
      awayTeam="Carlos Alcaraz"
      sportKey="tennis_atp_us_open"
    />,
  );
}

/** The text of every prop-tile label, in document order. */
function tileLabels(html: string): string[] {
  return Array.from(
    html.matchAll(
      /class="text-\[11px\] font-semibold text-text-primary truncate leading-tight"[^>]*>([^<]*)</g,
    ),
  ).map((m) => m[1]);
}

/**
 * What the tile shows before the ellipsis at its NARROWEST — 110px, the floor.
 *
 * The tile may now grow past that when its row has space (see the sizing
 * describe below), but the disambiguation gate is deliberately keyed to the
 * floor: stripping a shared prefix that WOULD have been distinguishable in a
 * wider tile costs the reader a little context, while failing to strip one that
 * is indistinguishable at 110px is #2788 itself.
 */
function asRendered(label: string): string {
  return label.slice(0, DEFAULT_VISIBLE_CHARS);
}

/** The inline `style` of every prop tile, parsed into declarations. */
function tileStyles(html: string): Array<Record<string, string>> {
  return Array.from(html.matchAll(/<a href="\/futures\/[^"]*"[^>]*style="([^"]*)"/g)).map((m) =>
    Object.fromEntries(
      m[1]
        .split(";")
        .filter(Boolean)
        .map((d) => {
          const i = d.indexOf(":");
          return [d.slice(0, i).trim(), d.slice(i + 1).trim()];
        }),
    ),
  );
}

describe("the OTHER prop tiles do not print one string for two questions", () => {
  beforeEach(() => {
    setPayload([prop(QUARTERS, QUARTERS, 0.785, 1), prop(SEMIS, SEMIS, 0.55, 2)]);
  });

  it("renders both tiles (the control every case below depends on)", () => {
    // Without this, a section that stopped rendering entirely would satisfy
    // every "they differ" assertion by comparing nothing.
    expect(tileLabels(render())).toHaveLength(2);
  });

  it("renders labels that differ INSIDE the visible window", () => {
    // THE bug. Before the fix both of these read "Will Carlos Al".
    const [a, b] = tileLabels(render());
    expect(asRendered(a)).not.toBe(asRendered(b));
  });

  it("prints the clause that tells the two questions apart", () => {
    const labels = tileLabels(render());
    expect(labels.some((l) => l.startsWith("Quarterfinals"))).toBe(true);
    expect(labels.some((l) => l.startsWith("Semifinals"))).toBe(true);
  });

  it("still prints both probabilities beside them", () => {
    // The number was never the defect and must not become one.
    const html = render().replace(/<[^>]*>/g, " ");
    expect(html).toContain("79%");
    expect(html).toContain("55%");
  });

  it("keeps the full question recoverable on the LABEL itself", () => {
    // Necessary regardless, per the issue: a reader who cannot fit the question
    // on screen can still hover it, and a screen reader still reads it.
    //
    // Scoped to the label element, NOT to the page. A bare
    // `html.toContain('title="Will Carlos…"')` passes on the UNFIXED file — the
    // headshot fallback beside the label already carries the same string — so
    // it would have been a guard that proved nothing.
    const titles = Array.from(
      render().matchAll(
        /class="text-\[11px\] font-semibold text-text-primary truncate leading-tight" title="([^"]*)"/g,
      ),
    ).map((m) => m[1]);

    expect(titles).toHaveLength(2);
    expect(titles).toContain(QUARTERS.replace(/'/g, "&#x27;"));
    expect(titles).toContain(SEMIS.replace(/'/g, "&#x27;"));
  });
});

describe("the tile is sized by its row and its own content, never by a constant", () => {
  // THE LEFTOVER HALF OF #2788, filed again as the truncation note on #3417.
  //
  // Disambiguation above stops two tiles printing ONE string. It cannot help a
  // group holding a SINGLE tile: `width: 110` clipped "Alexander Zverev" to
  // "Alexander Zv…" by 7px on `/events/15309061`, in a row with 264px unused at
  // 390px — and the SAME 7px in a row with 874px unused at 1024px. Measured with
  // `tools/prop-tile-fit-2788.mjs` against production, 2026-09-10.
  //
  // jsdom cannot lay out flexbox, so these grade the STYLE CONTRACT that the
  // browser measurement confirmed, not the pixels. The pixel proof is the
  // before/after differential in the PR.
  beforeEach(() => {
    setPayload([prop(QUARTERS, QUARTERS, 0.785, 1), prop(SEMIS, SEMIS, 0.55, 2)]);
  });

  it("renders tiles at all (the control the assertions below depend on)", () => {
    expect(tileStyles(render()).length).toBeGreaterThan(0);
  });

  it("pins no fixed width on the tile", () => {
    // The defect's exact shape. Matched as a standalone declaration so that
    // `min-width`/`max-width` — which both contain the word — cannot satisfy it.
    for (const style of tileStyles(render())) {
      expect(Object.keys(style)).not.toContain("width");
    }
  });

  it("lets the tile grow into free space", () => {
    // Without a positive grow factor the cap and the floor are both inert and
    // the tile stays 110px forever: the fix would ship as dead style.
    for (const style of tileStyles(render())) {
      expect(Number(style["flex-grow"])).toBeGreaterThan(0);
    }
  });

  it("caps the tile at its own content, so a lone tile is not a banner", () => {
    for (const style of tileStyles(render())) {
      expect(style["max-width"]).toBe("max-content");
    }
  });

  it("keeps a 110px floor so the scrolling arm cannot regress", () => {
    // Three tiles at phone width overflow and scroll. That arm measured
    // identical before and after precisely because the floor did not move.
    for (const style of tileStyles(render())) {
      expect(style["min-width"]).toBe("110px");
      expect(style["flex-basis"]).toBe("110px");
    }
  });

  it("never caps without a floor — the pair, in both directions", () => {
    // NOT a restatement of the two cases above. `max-content` is NARROWER than
    // 110px for the score tiles, whose widest child is a 48px gauge, so a cap
    // shipped WITHOUT the floor would silently shrink them from 110px to ~68px
    // at every width. CSS resolves min-width over max-width when they conflict,
    // and that resolution is the only reason those tiles hold still.
    for (const style of tileStyles(render())) {
      const capped = style["max-width"] === "max-content";
      const floor = parseFloat(style["min-width"] ?? "");
      expect(capped).toBe(true);
      expect(floor).toBeGreaterThanOrEqual(parseFloat(style["flex-basis"]));
    }
  });
});

describe("ordinary player-prop tiles are untouched", () => {
  it("keeps whole player names", () => {
    // The regression direction. These carry a colon, so they parse as
    // player+line and the labels are short names that were never ambiguous.
    //
    // The market name must name one of THIS event's teams: `isRelevantGameProp`
    // drops a `Team A at Team B` prop whose matchup matches neither side, which
    // is a real cross-sport-leak filter and not something to route around.
    setPayload([
      prop("Wu Yibing at Carlos Alcaraz: Aces", "Derrick White: 12+", 0.61, 3),
      prop("Wu Yibing at Carlos Alcaraz: Aces", "Jaylen Brown: 20+", 0.44, 4),
    ]);
    const labels = tileLabels(render());
    expect(labels).toContain("Derrick White");
    expect(labels).toContain("Jaylen Brown");
  });
});
