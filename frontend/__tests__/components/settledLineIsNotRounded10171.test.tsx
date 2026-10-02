/**
 * #10171 — A NUMBER ON THE RAIL SAYS THE VALUE IT IS DRAWN AT.
 *
 * `/events/15322407` (Phillies @ Braves, final 6–2), 390px, 2026-10-02: the
 * Runs map headed "Total: expected vs final" printed `PRE-GAME 8` beside
 * `FINAL 8 runs` — a game that landed exactly on its line. It went OVER: the
 * stored opening total is 7.5 (`opening_odds.over_under`). The tile rounded
 * the half-point line, and the mid-axis tick rounded 7.5 (the midpoint of
 * 3…12) to `8`, so the FINAL-8 dot sat right of a tick labelled 8 too.
 *
 * The fixture is that page's own `game-markets` body (totals + the 1st-5
 * ladder) as served on 2026-10-02, trimmed to the fields the card reads.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { railNumber } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const PHI_ATL_TOTALS = [
  { threshold: 6.5, over_probability: 1.0, source: "polymarket", market_type: "game_total", market_name: "Philadelphia Phillies vs. Atlanta Braves: O/U 6.5", outcome_name: "Over", is_winner: true, resolution_source: "api_settlement", period: null, movement: 0.4 },
  { threshold: 7.5, over_probability: 1.0, source: "polymarket", market_type: "game_total", market_name: "Philadelphia Phillies vs. Atlanta Braves: O/U 7.5", outcome_name: "Over", is_winner: true, resolution_source: "api_settlement", period: null, movement: 0.525 },
  { threshold: 8.5, over_probability: 0.0, source: "polymarket", market_type: "game_total", market_name: "Philadelphia Phillies vs. Atlanta Braves: O/U 8.5", outcome_name: "Under", is_winner: false, resolution_source: "api_settlement", period: null, movement: 0.4 },
];

function body(overrides: object = {}) {
  return {
    event_id: 15322407,
    home_team: "Atlanta Braves",
    away_team: "Philadelphia Phillies",
    home_score: 6,
    away_score: 2,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [],
    totals: PHI_ATL_TOTALS,
    ...overrides,
  };
}

function render(opts: { eventStatus?: string; openingOverUnder?: number | null; markets?: object } = {}) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={(opts.markets ?? body()) as never}
      eventStatus={opts.eventStatus ?? "completed"}
      homeTeam="Atlanta Braves"
      awayTeam="Philadelphia Phillies"
      homeAbbr="ATL"
      awayAbbr="PHI"
      homeWinProb={0.51}
      awayWinProb={0.49}
      overUnder={8.4}
      openingOverUnder={opts.openingOverUnder === undefined ? 7.5 : opts.openingOverUnder}
      sportKey="baseball_mlb"
    />
  );
}

/** Every rail's `[left, mid, right]` axis labels, as rendered. */
function axisLabels(html: string): string[][] {
  const out: string[][] = [];
  const re = /data-axis-labels=""[^>]*>((?:\s*<span[^>]*>[^<]*<\/span>){3})/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    out.push([...m[1].matchAll(/<span[^>]*>([^<]*)<\/span>/g)].map((s) => s[1]));
  }
  return out;
}

describe("#10171 — railNumber", () => {
  it("keeps a half-point line's half and a whole value whole", () => {
    expect(railNumber(7.5)).toBe("7.5");
    expect(railNumber(8)).toBe("8");
    expect(railNumber(0)).toBe("0");
    expect(railNumber(2.5)).toBe("2.5");
  });
});

describe("#10171 — PHI@ATL 6–2: the settled runs card does not say the game landed on its line", () => {
  it("the Pre-game tile prints the 7.5 line, not 8", () => {
    const text = visibleText(render());
    expect(text).toMatch(/Pre-game 7\.5\b/);
    expect(text).not.toMatch(/Pre-game 8\b/);
    // The FINAL tile is untouched — 8 runs were scored.
    expect(text).toMatch(/Final 8 runs/);
  });

  it("every rail's mid tick is the value at its centre", () => {
    const rails = axisLabels(render());
    expect(rails.length).toBeGreaterThan(0);
    for (const [left, mid, right] of rails) {
      const lo = Number(left);
      const hi = Number(right.replace(/\+$/, ""));
      expect(mid).toBe(railNumber((lo + hi) / 2));
    }
  });

  it("the specimen's runs rail is 3…12, so its centre tick reads 7.5", () => {
    const rails = axisLabels(render());
    expect(rails).toContainEqual(["3", "7.5", "12+"]);
  });

  it("CONTROL: a whole-number opening total still prints whole", () => {
    const text = visibleText(render({ openingOverUnder: 8 }));
    expect(text).toMatch(/Pre-game 8\b/);
    expect(text).not.toMatch(/Pre-game 8\.0/);
  });
});

describe("#10171 — the live half card's headline quotes the line it is drawing", () => {
  const liveHalf = body({
    status: "in_progress",
    home_score: 1,
    away_score: 0,
    totals: [
      { threshold: 7.5, over_probability: 0.52, source: "kalshi", market_type: "game_total", market_name: "Philadelphia vs Atlanta Total Runs", outcome_name: "Over 7.5 runs", is_winner: null, resolution_source: null, period: null, movement: 0 },
      { threshold: 8.5, over_probability: 0.4, source: "kalshi", market_type: "game_total", market_name: "Philadelphia vs Atlanta Total Runs", outcome_name: "Over 8.5 runs", is_winner: null, resolution_source: null, period: null, movement: 0 },
    ],
    period_markets: [
      { threshold: 2.5, over_probability: 0.7, probability: 0.7, source: "kalshi", market_type: "half_total", market_name: "First 5 Innings Total Runs", outcome_name: "Over 2.5 runs", period: "1H" },
      { threshold: 3.5, over_probability: 0.5, probability: 0.5, source: "kalshi", market_type: "half_total", market_name: "First 5 Innings Total Runs", outcome_name: "Over 3.5 runs", period: "1H" },
      { threshold: 4.5, over_probability: 0.3, probability: 0.3, source: "kalshi", market_type: "half_total", market_name: "First 5 Innings Total Runs", outcome_name: "Over 4.5 runs", period: "1H" },
    ],
  });

  it("prints O/U 3.5, not O/U 4", () => {
    const text = visibleText(render({ eventStatus: "in_progress", markets: liveHalf }));
    expect(text).toMatch(/O\/U 3\.5\b/);
    expect(text).not.toMatch(/O\/U 4\b/);
  });
});
