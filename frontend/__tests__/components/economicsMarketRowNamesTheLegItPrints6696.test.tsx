import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MarketRow } from "../../components/economics/atoms";

// #6696 — an `/economics` Market row must name the outcome its percentage
// belongs to. The backend half chooses and names the leg (`EconMarketRow.leader`,
// `economics._leader_name`); this is the render half, and without it the field
// is served and thrown away.
//
// Production, `GET /api/economics` 2026-09-17 04:45Z, TRADE & TARIFFS:
//
//     What will the tariff rate on Canadian imports be on Jan 1, 2027?   85%
//
// 85% of WHAT. The question asks for a rate and the card answered with a bare
// confidence, in bold green behind a near-full bar. The number is the price of
// "10% or above"; naming it is the whole repair on this side.
//
// The rows below are real production rows, copied verbatim.

const html = (props: Parameters<typeof MarketRow>[0]) =>
  renderToStaticMarkup(<MarketRow {...props} />);

// `renderToStaticMarkup` escapes, so "S&P 500" arrives as "S&amp;P 500" — and
// three of the real leaders on this page carry an ampersand. Decoding keeps the
// specimens below readable as the reader's own words rather than as markup.
const text = (props: Parameters<typeof MarketRow>[0]) =>
  html(props).replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"');

const CANADIAN_TARIFF_RATE = {
  q: "What will the tariff rate on Canadian imports be on Jan 1, 2027?",
  prob: 85.0,
  src: "kalshi",
  leader: "10% or above",
};

describe("#6696 — an /economics row names the leg it prints", () => {
  it("prints the leader beside the source chip", () => {
    expect(text(CANADIAN_TARIFF_RATE)).toContain("10% or above");
  });

  it("still prints the number it always printed", () => {
    // The name is added; the percentage is not replaced by it.
    expect(html(CANADIAN_TARIFF_RATE)).toContain("85%");
  });

  it.each([
    ["Which sectors will Trump tariff in 2026?", 97.0, "Pharmaceuticals"],
    ["Bitcoin vs. Gold vs. S&P 500 in 2026", 54.5, "S&P 500"],
    ["Texas crude oil production in 2026", 95.5, "Above 5.6 million barrels/day"],
  ])("names %s", (q, prob, leader) => {
    expect(text({ q, prob, src: "kalshi", leader })).toContain(leader);
  });

  describe("when there is nothing worth naming", () => {
    // The backend sends an explicit null for a question that already answers
    // itself. The row must render exactly as it did before this ship — no
    // empty element, no stray separator.
    it("renders nothing extra for an explicit null", () => {
      const withNull = html({ q: "Will the S&P finish positive this year?", prob: 85.5, src: "kalshi", leader: null });
      const without = html({ q: "Will the S&P finish positive this year?", prob: 85.5, src: "kalshi" });
      expect(withNull).toEqual(without);
    });

    it("survives a payload served before the field existed", () => {
      // The hourly cache can serve a row with no `leader` key at all.
      expect(() => html({ q: "Will the S&P finish positive this year?", prob: 85.5, src: "kalshi" })).not.toThrow();
    });

    it("does not emit the leader element", () => {
      expect(html({ q: "Will it happen?", prob: 40, src: "kalshi", leader: null }))
        .not.toContain("econ-market-leader");
    });
  });

  describe("the leader is not allowed to be truncated away", () => {
    // Weather measured 8/8 leaders cut at 390px when the same content was laid
    // out as a nowrap row (ux/1083, #3147), and the longest names here are
    // longer still. The line wraps instead; a `truncate` on this line would
    // silently delete the repair on a phone.
    const longest = html({
      q: "Texas crude oil production in 2026",
      prob: 95.5,
      src: "kalshi",
      leader: "Above 5.6 million barrels/day",
    });

    it("lays the line out as wrapping", () => {
      expect(longest).toContain("flex-wrap");
    });

    it("does not truncate it", () => {
      const line = longest.slice(longest.indexOf("flex-wrap"));
      expect(line).not.toContain("truncate");
    });

    it("keeps the whole name", () => {
      expect(longest).toContain("Above 5.6 million barrels/day");
    });
  });
});
