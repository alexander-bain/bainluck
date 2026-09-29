/**
 * #9633: `/events/15320530` (Tomic v Sun, settled 2026-09-29) served one extra
 * market, Set 1 Winner, as two `other` rows. The event page mounted Additional
 * Markets only at `other.length >= 3`, so the card never drew. #5540 had already
 * dropped `buildMarketSection`'s own floor for a lone question; the page gate
 * never followed.
 *
 * The rows below are that event's `/game-markets` → `other`, verbatim from
 * production 2026-09-29, less `contributor_outcome_ids` (not on the wire type,
 * not read by the section).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import SpecialEventMarkets from "@/components/SpecialEventMarkets";
import { SPECIAL_MARKETS_MIN_WIRE_ROWS } from "@/lib/gamePropsDrawnAbove";
import type { GameMarketsResponse } from "@/lib/api";

const SET_1: GameMarketsResponse["other"] = [
  { market_name: "Set 1 Winner: Bernard Tomic vs Fajing Sun", outcome_name: "Bernard Tomic", observed_at: "2026-09-29T06:38:55.761340+00:00", probability: 1.0, source: "polymarket", is_winner: true, resolution_source: "api_settlement", _market_id: 63071709 },
  { market_name: "Set 1 Winner: Bernard Tomic vs Fajing Sun", outcome_name: "Fajing Sun", observed_at: "2026-09-29T06:38:55.761340+00:00", probability: null, source: "polymarket", is_winner: false, resolution_source: "api_settlement", _market_id: 63071709 },
];

const MONEYLINE_ONLY: GameMarketsResponse["other"] = [
  { market_name: "Bernard Tomic vs Fajing Sun", outcome_name: "Bernard Tomic", probability: 0.6, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 1 },
  { market_name: "Bernard Tomic vs Fajing Sun", outcome_name: "Fajing Sun", probability: 0.4, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 1 },
];

function render(other: GameMarketsResponse["other"], eventStatus = "completed"): string {
  const data = { other, home_team: "Tomic", away_team: "Sun" } as GameMarketsResponse;
  return renderToStaticMarkup(<SpecialEventMarkets data={data} eventStatus={eventStatus} />);
}

describe("#9633 one extra question gets its card", () => {
  it("the page's floor admits the specimen's two rows", () => {
    expect(SET_1.length).toBe(2);
    expect(SET_1.length).toBeGreaterThanOrEqual(SPECIAL_MARKETS_MIN_WIRE_ROWS);
  });

  it("the section draws Set 1 Winner and names Tomic", () => {
    const html = render(SET_1);
    expect(html).toMatch(/Set 1/);
    expect(html).toMatch(/Tomic/);
  });

  it("control: a lone moneyline (the hero's own market) still draws nothing", () => {
    expect(MONEYLINE_ONLY.length).toBeGreaterThanOrEqual(SPECIAL_MARKETS_MIN_WIRE_ROWS);
    expect(render(MONEYLINE_ONLY, "scheduled")).toBe("");
  });
});

describe("#9633 the event page mounts on that floor", () => {
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  const page = fs.readFileSync(path.join(__dirname, "..", "app", "events", "[id]", "page.tsx"), "utf8");

  it("gates Additional Markets on SPECIAL_MARKETS_MIN_WIRE_ROWS, not a literal", () => {
    expect(page).toMatch(/gameMarkets\.other\?\.length \?\? 0\) >= SPECIAL_MARKETS_MIN_WIRE_ROWS && \(\s*<SectionErrorBoundary label="Special markets"/);
    expect(page).not.toMatch(/other\?\.length \?\? 0\) >= [0-9]/);
  });
});
