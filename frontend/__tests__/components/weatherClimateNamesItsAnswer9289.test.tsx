/**
 * #9289: the /weather climate card names the outcome its percentage prices.
 *
 * Production, 2026-09-28 04:28Z (390px LOOK): "EV market share in 2030? — 84%"
 * with nothing saying 84% of what. The market's leader is "Above 10%". Every
 * other /weather card already carried `leader`; climate neither served nor
 * rendered it. Rows below are the served payload's own rows with the leader
 * the route now emits.
 *
 *   npx jest --testPathPatterns=weatherClimateNamesItsAnswer9289
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined }),
}));

/* eslint-disable @typescript-eslint/no-var-requires */
const ClimateDashboard = require("@/components/weather/ClimateDashboard").default;
/* eslint-enable @typescript-eslint/no-var-requires */

const ROWS = [
  { q: "EV market share in 2030?", prob: 84, probability: 0.845, src: "kalshi", scale: "2030", leader: "Above 10%" },
  { q: "How low will Lake Powell drop?", prob: 70, probability: 0.7, src: "polymarket", scale: "2026", leader: "Above 3,510 ft" },
  { q: "Will 2026 be the hottest year ever?", prob: 65, probability: 0.65, src: "kalshi", scale: "2026", leader: null },
  // A payload cached before the field existed has no key at all.
  { q: "US meets its climate goals?", prob: 18, probability: 0.18, src: "kalshi", scale: "2030" },
];

function leaders(markup: string): string[] {
  return Array.from(markup.matchAll(/data-testid="climate-leader"[^>]*>([^<]*)</g)).map((m) => m[1]);
}

describe("#9289 climate card names its answer", () => {
  it("prints each served leader, and only those", () => {
    swrPayload = ROWS;
    const markup = renderToStaticMarkup(React.createElement(ClimateDashboard));
    expect(leaders(markup)).toEqual(["Above 3,510 ft", "Above 10%"]);
  });

  it("the name sits in the same row block as its question", () => {
    swrPayload = ROWS;
    const markup = renderToStaticMarkup(React.createElement(ClimateDashboard));
    const q = markup.indexOf("EV market share in 2030?");
    const name = markup.indexOf("Above 10%");
    const next = markup.indexOf("US meets its climate goals?");
    expect(q).toBeGreaterThan(-1);
    expect(name).toBeGreaterThan(q);
    expect(next).toBeGreaterThan(name);
  });
});
