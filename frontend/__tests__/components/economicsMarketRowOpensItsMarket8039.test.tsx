import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import { MarketRow } from "../../components/economics/atoms";

// #8039 — `/economics` was a dead end. 346 market rows, each a question, a
// source chip and a probability, and not one of them opened anything: tapping
// "Will unemployment in Brazil be below 5.8% in Q4 2026?" at 390px left the
// reader on the same page (docHeight 14,525 before and after, 2026-10-01
// 13:5xZ). The identical card on /politics and /entertainment opens
// `/futures/{market_id}`, and `/api/economics` already serves that id on the
// rows — only the link was missing.
//
// Rows below are real production rows from `GET /api/economics`, 2026-10-01.
//
//   npx jest --testPathPatterns=economicsMarketRowOpensItsMarket8039

const html = (props: Parameters<typeof MarketRow>[0]) =>
  renderToStaticMarkup(<MarketRow {...props} />);

const BRAZIL_UNEMPLOYMENT = {
  q: "Will unemployment in Brazil be below 5.8% in Q4 2026?",
  prob: 65,
  src: "kalshi",
  leader: null,
  marketId: 109627,
};

// Served WITHOUT a market id: a WTI bracket in the Crude oil card.
const WTI_BRACKET = {
  q: "WTI $92.00 to $92.99",
  prob: 11.4,
  src: "kalshi",
  leader: null,
};

describe("#8039 · an /economics market row opens its market", () => {
  test("a row with a market id is a link to /futures/{id}", () => {
    const out = html(BRAZIL_UNEMPLOYMENT);
    expect(out).toContain('href="/futures/109627"');
    expect(out).toContain('data-testid="econ-market-row-link"');
    // The whole row is the target, question included.
    const anchor = out.slice(out.indexOf("<a"), out.lastIndexOf("</a>"));
    expect(anchor).toContain(BRAZIL_UNEMPLOYMENT.q);
    expect(anchor).toContain("65%");
  });

  test("a row with no market id stays a plain row — never /futures/undefined", () => {
    const out = html(WTI_BRACKET);
    expect(out).not.toContain("<a");
    expect(out).not.toContain("/futures/");
    expect(out).toContain("11%");
  });

  test("a market id of 0 is still an id", () => {
    expect(html({ ...BRAZIL_UNEMPLOYMENT, marketId: 0 })).toContain('href="/futures/0"');
  });

  test("every MarketRow on the page is handed its row's market id", () => {
    const page = readFileSync(join(__dirname, "..", "..", "app", "economics", "page.tsx"), "utf8");
    const calls = page.match(/<MarketRow\b[^>]*\/>/g) ?? [];
    expect(calls.length).toBeGreaterThanOrEqual(10);
    for (const call of calls) {
      expect(call).toMatch(/marketId=\{[mo]\.market_id\}/);
    }
  });
});
