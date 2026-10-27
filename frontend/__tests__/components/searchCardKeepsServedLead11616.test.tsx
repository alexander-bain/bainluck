/**
 * #11616 — the search card keeps search's served lead order, and its badges are
 * the detail page's own price ranks.
 *
 * Root's NATIVE-DELTA disposition item 4 (FuturesCard probability re-sort) and
 * P1/M1-U (ROOT-PRODUCER-FIXTURE-DISPOSITION). The M1-U specimen is the actual
 * `/api/events/search?q=SGA` card at 0e5d583a (producer-capture
 * runs/20261027T192150Z-full-0e5d583a/M1-U.json): an open, exclusive NBA MVP
 * board whose priceless Shai row is a supported `api_settlement` winner. The
 * suggestion, the iOS card and the detail hero lead with Shai Won; the web card
 * re-sorted by probability, drew Shai LAST with a positional "5" (detail badges
 * him 6) and highlighted Victor 28% as the leader.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";

function outcome(
  id: number,
  name: string,
  probability: number | null,
  over: Partial<FuturesOutcome> = {},
): FuturesOutcome {
  return {
    id, name, probability, american_odds: null, rank: null, rank_change_24h: null,
    probability_change_24h: null, movement: null, opening_probability: null,
    opening_american_odds: null, is_winner: false, resolution_source: null,
    last_updated: null, ...over,
  } as FuturesOutcome;
}

function market(top_outcomes: FuturesOutcome[], over: Partial<FuturesMarket> = {}): FuturesMarket {
  return {
    id: 73, name: "NBA MVP Winner 2027", description: null, source: "kalshi",
    category: null, sport: "basketball_nba", sport_name: null,
    llm_sport_category: "basketball", external_id: null, mutually_exclusive: true,
    commence_time: null, resolution_date: null, outcome_count: 6, created_at: null,
    updated_at: null, status: "open", top_outcomes, ...over,
  } as unknown as FuturesMarket;
}

/** [label, badge, isLeader] per rendered row, in screen order. */
function rows(html: string): [string, string, boolean][] {
  const found = [
    ...html.matchAll(
      /<span class="([^"]*w-5 h-5 flex items-center justify-center text-\[10px\][^"]*)">(\d*)<\/span>[\s\S]*?data-outcome-label[^>]*>([^<]*)</g,
    ),
  ].map(([, cls, badge, label]) => [label, badge, cls.includes("font-bold")] as [string, string, boolean]);
  if (found.length === 0) throw new Error("extractor blind: no badge/label rows");
  return found;
}

const SEARCH = (m: FuturesMarket) =>
  renderToStaticMarkup(<FuturesCard market={m} readsOpenFieldOuts keepsServedOrder />);
const OTHER = (m: FuturesMarket) => renderToStaticMarkup(<FuturesCard market={m} />);

// M1-U, served order and fields verbatim (rank null on the priceless result).
const M1U = [
  outcome(1, "Shai Gilgeous-Alexander", null, { is_winner: true, resolution_source: "api_settlement" }),
  outcome(2, "Victor Wembanyama", 0.2818, { rank: 1 }),
  outcome(3, "Nikola Jokic", 0.2364, { rank: 2 }),
  outcome(4, "Luka Doncic", 0.1818, { rank: 3 }),
  outcome(5, "Anthony Edwards", 0.1636, { rank: 4 }),
];

describe("#11616 search card: served lead order and detail's badges", () => {
  it("leads with the supported result, as suggestion, iOS card and detail hero do", () => {
    const r = rows(SEARCH(market(M1U)));
    expect(r.map(([l]) => l)).toEqual([
      "Shai Gilgeous-Alexander", "Victor Wembanyama", "Nikola Jokic", "Luka Doncic", "Anthony Edwards",
    ]);
    expect(r[0][2]).toBe(true); // the highlighted row is the result
    expect(r.filter(([, , lead]) => lead)).toHaveLength(1);
  });

  it("P1: priced rows print detail's own rank; the priceless result prints no number", () => {
    const r = rows(SEARCH(market(M1U)));
    expect(r.map(([l, b]) => [l, b])).toEqual([
      ["Shai Gilgeous-Alexander", ""],
      ["Victor Wembanyama", "1"],
      ["Nikola Jokic", "2"],
      ["Luka Doncic", "3"],
      ["Anthony Edwards", "4"],
    ]);
  });

  it("CONTROL: every other surface keeps the leader-first sort (#2789)", () => {
    const r = rows(OTHER(market(M1U)));
    expect(r[0]).toEqual(["Victor Wembanyama", "1", true]);
    expect(r[r.length - 1].slice(0, 2)).toEqual(["Shai Gilgeous-Alexander", "5"]);
  });

  it("an independent open board keeps its live lead above a supported winner", () => {
    // Served by L1/L2: live tier first, the result after it.
    const served = [
      outcome(11, "↑ 4.25%", 0.4, { rank: 2 }),
      outcome(12, "↓ 3.5%", 0.95, { rank: 1, is_winner: true, resolution_source: "api_settlement" }),
    ];
    const r = rows(SEARCH(market(served, { mutually_exclusive: false, name: "Fed rate 2026" })));
    expect(r.map(([l, b, lead]) => [l, b, lead])).toEqual([
      ["↑ 4.25%", "2", true],
      ["↓ 3.5%", "1", false],
    ]);
  });

  it("the query pin keeps the place its price gives it, with its board rank (#8863)", () => {
    const served = [
      outcome(21, "Shai Gilgeous-Alexander", 0.08, { rank: 6, query_match: true, matched_rank: 6 }),
      ...M1U.slice(1),
    ];
    const r = rows(SEARCH(market(served)));
    expect(r.map(([l, b]) => [l, b])).toEqual([
      ["Victor Wembanyama", "1"],
      ["Nikola Jokic", "2"],
      ["Luka Doncic", "3"],
      ["Anthony Edwards", "4"],
      ["Shai Gilgeous-Alexander", "6"],
    ]);
    expect(r[0][2]).toBe(true);
  });

  it("a pin priced above the field rises to its price place, never above a result", () => {
    const served = [
      outcome(31, "Victor Wembanyama", 0.2818, { rank: 1, query_match: true, matched_rank: 1 }),
      outcome(1, "Shai Gilgeous-Alexander", null, { is_winner: true, resolution_source: "api_settlement" }),
      outcome(3, "Nikola Jokic", 0.2364, { rank: 2 }),
    ];
    const r = rows(SEARCH(market(served)));
    expect(r.map(([l]) => l)).toEqual(["Shai Gilgeous-Alexander", "Victor Wembanyama", "Nikola Jokic"]);
  });

  it("CONTROL: a legacy cached card with ranks stripped keeps positional badges", () => {
    const legacy = M1U.map((o) => ({ ...o, rank: null }));
    const r = rows(SEARCH(market(legacy)));
    expect(r.map(([, b]) => b)).toEqual(["1", "2", "3", "4", "5"]);
  });
});
