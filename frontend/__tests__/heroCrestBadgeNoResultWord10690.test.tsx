// #10690 — A PHOTO-LESS PLAYER'S HERO TILE READ `WON` MID-MATCH.
//
// Production, 390px, live (`/events/15326071`, ATP Shanghai, Halys v Wong,
// Halys 83% at 6-4, 4-3): Chak Lam Coleman Wong has no headshot, so the hero
// drew the lettered fallback, and the badge rule took three letters of his
// surname. The tile read `WON`, at the weight of a result chip, beside a
// player trailing at 17%. A first-time reader takes it as "Wong won".
//
// The assertion is on the page's own markup (the #7270 pattern): the defect is
// what the hero paints, and a helper-only test would pass if the page stopped
// asking the helper.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { discoverCrestBadge, shippableCrestBadge, teamCrestBadge } from "@/lib/teamShortName";

const EVENT = {
  id: 15326071,
  sport: "tennis_atp_shanghai_masters",
  sport_title: "ATP Shanghai Masters",
  sport_name: "ATP Shanghai Masters",
  home_team: "Quentin Halys",
  away_team: "Chak Lam Coleman Wong",
  home_score: 1,
  away_score: 0,
  status: "live",
  commence_time: "2026-10-07T08:30:00+00:00",
  win_probability_sources: {},
};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? EVENT_HOLDER.value : undefined,
      error: undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15326071",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15326071" }),
}));

const EVENT_HOLDER: { value: unknown } = { value: EVENT };

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15326071" } }),
    ),
  );
}

/**
 * The crest tiles' letters, read off the page rather than recomputed.
 *
 * The lettered fallback is the only `font-extrabold` span in the hero, and it
 * is the element the inline expression used to fill. Reading the markup is what
 * makes this a guard about the PAGE: recomputing the badge here would assert
 * that the helper agrees with itself.
 */
function crestLetters(html: string): string[] {
  return Array.from(html.matchAll(/<span[^>]*font-extrabold[^>]*>([^<]*)<\/span>/g))
    .map(m => m[1].trim())
    .filter(Boolean);
}

const RESULT_WORDS = ["WON", "WIN", "TIE", "OUT"];

describe("#10690 the event hero never letters a player with a result word", () => {
  it("draws CW for the filed specimen, not WON", () => {
    EVENT_HOLDER.value = EVENT;
    const letters = crestLetters(draw());
    // Positive first: an empty hero would pass every "not" below.
    expect(letters.length).toBeGreaterThanOrEqual(2);
    expect(letters).toContain("CW");
    expect(letters).toContain("HAL");
    expect(letters).not.toContain("WON");
  });

  it("paints no result word for the other measured names, on either tile", () => {
    // Real production names from the same 60-day sweep: Tien -> TIE on the
    // home tile, Outlaw -> OUT on the away tile.
    EVENT_HOLDER.value = { ...EVENT, home_team: "Learner Tien", away_team: "Sidney Outlaw" };
    const letters = crestLetters(draw());
    expect(letters.length).toBeGreaterThanOrEqual(2);
    expect(letters).toContain("LT");
    expect(letters).toContain("SO");
    for (const badge of letters) expect(RESULT_WORDS).not.toContain(badge);
  });
});

describe("#10690 the badge rules, read on the names that spelled a result", () => {
  // [name, sport, what the bare rule paints, what a reader now sees]
  const SPECIMENS: Array<[string, string, string, string]> = [
    ["Chak Lam Coleman Wong", "tennis_atp", "WON", "CW"],
    ["Coleman Wong", "tennis_atp", "WON", "CW"],
    ["Wong", "tennis_atp", "WON", "W"],
    ["Learner Tien", "tennis_atp", "TIE", "LT"],
    ["Anthony Wint", "tennis_atp", "WIN", "AW"],
    ["Dallas Wings", "basketball_wnba", "WIN", "DW"],
    ["Denver Outlaws", "lacrosse_pll", "OUT", "DO"],
    ["Winslow United FC", "soccer_eng_national_league", "WIN", "WUF"],
    ["Wingate & Finchley FC", "soccer_eng_isthmian", "WIN", "WFF"],
  ];

  it.each(SPECIMENS)("%s (%s): %s -> %s", (name, sport, bare, shown) => {
    // The premise is asserted, so the table cannot quietly stop being about
    // anything: this IS what the shared rule (and the iPhone's mirror) paints.
    expect(teamCrestBadge(name, sport)).toBe(bare);
    expect(shippableCrestBadge(name, sport)).toBe(shown);
    // Discover's tiles take the same answer.
    expect(discoverCrestBadge(name, sport)).toBe(shown);
  });

  it("leaves teamCrestBadge and every clean badge exactly as shipped", () => {
    // Kept apart from UNSHIPPABLE_BADGES so the shared rule, which the iPhone
    // mirrors, does not move. Words not on the list stay as they were.
    expect(shippableCrestBadge("Leo Deflandre", "tennis_atp")).toBe("DEF");
    expect(shippableCrestBadge("Quentin Halys", "tennis_atp")).toBe("HAL");
    expect(shippableCrestBadge("Arizona State Sun Devils", null)).toBe("ASD");
    expect(discoverCrestBadge("Winnipeg Jets", "icehockey_nhl")).toBe("JET");
  });
});
