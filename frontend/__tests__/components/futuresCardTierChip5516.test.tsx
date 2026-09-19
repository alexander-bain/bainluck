// #5516, defect 2 — THE CARD MUST STOP PRINTING IT, not merely compute a null.
//
// `marketCategoryLabelTier5516` proves the rule. Only this file proves
// `FuturesCard` renders the result, which is the codebase's standing lesson
// (#2060, and #2710's own strip test): a pure test cannot tell a rendered field
// from a declared one, and `FuturesCard` is the single production call site of
// `marketCategoryLabel` — if the tier is not threaded through it, every
// assertion in the pure file is true and the reader still sees "Championship".
//
// THE FIXTURE IS THE SERVED PAYLOAD. Rows verbatim from
// `GET /api/events/search?q=chiefs`, production 2026-09-19, the same request
// behind the 390px LOOK in artifacts-lane1b-389/chiefs-390.png.
//
// THE ABSENCE CHECK KEYS ON A STRING MASTER RENDERS. "Championship" is what the
// card prints today for the specimen; it is not a marker this diff introduces,
// so the test cannot be vacuously green on the parent. The paired control below
// asserts the same string is still PRESENT for the real championship, which is
// what separates this fix from simply deleting the chip.

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
jest.mock("@/components/EntityImage", () => ({ __esModule: true, default: () => null }));

import FuturesCard from "@/components/FuturesCard";
import type { FuturesMarket } from "@/lib/types";

function market(
  id: number,
  name: string,
  category: string,
  market_tier: number | null | undefined,
): FuturesMarket {
  return {
    id,
    name,
    category,
    market_tier,
    llm_sport_category: "football",
    sport: "americanfootball_nfl",
    sport_name: "NFL",
    status: "open",
    source: "polymarket",
    outcome_count: 2,
    mutually_exclusive: false,
    top_outcomes: [
      { id: id * 10 + 1, name: "Safety", probability: 0.92 },
      { id: id * 10 + 2, name: "Trade / Traded", probability: 0.85 },
    ],
  } as unknown as FuturesMarket;
}

/** The LOOK specimen. */
const NOVELTY_PROP = market(
  61441990,
  "What will the announcers say during the Colts vs Chiefs game?",
  "championship",
  5,
);
/** CONTROL — the real title race, two cards above it on the same rail. */
const REAL_CHAMPIONSHIP = market(129037, "Pro Football: 2027 Champion", "championship", 1);
/** CONTROL — tier 5, but already categorised correctly. */
const GAME_PROP = market(61184052, "IND Colts vs KC Chiefs: 1st Half Spread", "game_prop", 5);
/** CONTROL — the Vercel-ahead-of-Heroku deploy window. */
const TIERLESS = market(61441990, "What will the announcers say during the Colts vs Chiefs game?", "championship", undefined);

const render = (m: FuturesMarket) => renderToStaticMarkup(<FuturesCard market={m} showSport />);

describe("#5516 — FuturesCard stops badging a novelty prop Championship", () => {
  it("the specimen renders no Championship chip", () => {
    expect(render(NOVELTY_PROP)).not.toContain("Championship");
  });

  it("CONTROL: the real championship on the same rail still prints it", () => {
    // Red here would mean the chip was deleted rather than corrected.
    expect(render(REAL_CHAMPIONSHIP)).toContain("Championship");
  });

  it("CONTROL: a correctly-categorised tier-5 sibling keeps its chip", () => {
    expect(render(GAME_PROP)).toContain("Game Props");
  });

  it("CONTROL: a payload with no tier is unchanged, so a deploy window blanks nothing", () => {
    expect(render(TIERLESS)).toContain("Championship");
  });

  it("CONTROL: the specimen's own name and price still render", () => {
    // Green on the parent too. If this goes red the fixture stopped reaching the
    // card and the absence check above became vacuous.
    const html = render(NOVELTY_PROP);
    expect(html).toContain("What will the announcers say during the Colts vs Chiefs game?");
    expect(html).toContain("92%");
  });

  it("the raw column value never reaches the markup either way (#2710 preserved)", () => {
    for (const m of [NOVELTY_PROP, REAL_CHAMPIONSHIP, GAME_PROP]) {
      expect(render(m)).not.toContain("game_prop");
    }
  });
});
