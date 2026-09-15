// #6247 — AN NFL CARD WEARS A FOOTBALL. Asserted on the card's own render.
//
// ── WHAT A READER SAW (production, 390px, the default landing page) ──────────
//
// The NFL card's chip read **📊 NFL** — the grey fallback glyph on a grey pill —
// two cards below an ⚾ MLB card and a ⚽ La Liga card. Same for every NHL card.
//
// ── THE MISMATCH ─────────────────────────────────────────────────────────────
//
// Every chip map in `components/discover/constants.ts` is keyed on a SHELF name
// (`football`, `hockey`, `motorsports`). The card passed
// `data.sport.split("_")[0]`, which is a SPORT-KEY segment (`americanfootball`,
// `icehockey`, `rugbyleague`). No match ⇒ `DEFAULT_EMOJI` and no gradient.
//
// Reach measured by discover/084 over the 95 sport keys carrying events in a
// 10-day window: americanfootball 659, icehockey 198, rugbyleague 30,
// motorsport 5 = **892 of 8,806 events** — every NFL and NHL card.
//
// #4326 repaired four fallers (esports, cycling, lacrosse, legal) by adding
// entries under shelf names, which could not reach these: `americanfootball` is
// not a shelf name and never will be.
//
// ── 🔴 WHY THE ASSERTION IS ON THE RENDER AND NOT ON `chipCategory` ──────────
//
// The prefixes `getCategoryForLeague` matches on carry the underscore
// (`americanfootball_`). So a fix that resolves the shelf but keeps handing it
// the truncated segment is COMPLETELY INERT — `chipCategory("americanfootball")`
// falls straight through and returns its argument, and a unit test of the
// helper alone passes while the card still prints 📊. Only the card's own
// output proves the whole key reached it.
//
// ── BOTH DIRECTIONS (gotcha #43) ─────────────────────────────────────────────
//
// The soccer card is the control: it was always correct, because `soccer_epl`
// truncates to a real shelf name. It must be byte-identical after the change.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EventCard } from "@/components/discover/EventCard";
import { CATEGORY_GRADIENTS, chipCategory, getCat } from "@/components/discover/constants";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

/** The glyph a card falls to when nothing matched. */
const FALLBACK = "📊";

function team(name: string) {
  return {
    id: 1,
    name,
    display_name: name,
    primary_color: "#123456",
    secondary_color: "#654321",
    logo: "https://example.invalid/s.png",
    logo_large: "https://example.invalid/l.png",
    record: "0-0",
    abbreviation: "TTT",
  };
}

function card(sportKey: string, sportName: string): string {
  const data = {
    id: 15305024,
    external_id: `evt-${sportKey}`,
    sport: sportKey,
    sport_name: sportName,
    sport_label: sportName,
    home_team: "Home",
    away_team: "Away",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "upcoming",
    home_score: null,
    away_score: null,
    current_odds: {
      home_probability: 0.55,
      away_probability: 0.45,
      home_rendered_percent: 55,
      away_rendered_percent: 45,
    },
    home_team_data: team("Home"),
    away_team_data: team("Away"),
  } as unknown as FeedEventData;

  return renderToStaticMarkup(
    <EventCard
      item={{ type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );
}

describe("the sports whose key segment is not a shelf name", () => {
  it("an NFL card draws the football, not the fallback", () => {
    const html = card("americanfootball_nfl", "NFL");
    expect(html).toContain("🏈");
    expect(html).not.toContain(FALLBACK);
  });

  it("an NFL card gets the football gradient it always had an entry for", () => {
    expect(card("americanfootball_nfl", "NFL")).toContain(
      CATEGORY_GRADIENTS.football
    );
  });

  it("an NHL card draws the hockey glyph", () => {
    const html = card("icehockey_nhl", "NHL");
    expect(html).toContain("🏒");
    expect(html).not.toContain(FALLBACK);
  });

  it("college football rides the same prefix", () => {
    expect(card("americanfootball_ncaaf", "NCAAF")).toContain("🏈");
  });

  it("a rugby league card stops falling through", () => {
    expect(card("rugbyleague_nrl", "NRL")).not.toContain(FALLBACK);
  });
});

describe("the cards that were already right (control)", () => {
  it("a soccer card is byte-identical to its pre-change render", () => {
    // `soccer_epl` truncates to `soccer`, a real shelf name, so this card never
    // had the bug — and a fix that changed it would be changing the wrong thing.
    const html = card("soccer_epl", "Premier League");
    expect(html).toContain("⚽");
    expect(html).toContain(CATEGORY_GRADIENTS.soccer);
    expect(html).not.toContain(FALLBACK);
  });

  it("a baseball card keeps its shelf", () => {
    expect(card("baseball_mlb", "MLB")).toContain("⚾");
  });
});

describe("chipCategory", () => {
  it("resolves a whole sport key to its shelf", () => {
    expect(chipCategory("americanfootball_nfl")).toBe("football");
    expect(chipCategory("icehockey_nhl")).toBe("hockey");
    expect(chipCategory("motorsport_f1")).toBe("motorsports");
  });

  it("returns a shelf name untouched, so llm_sport_category callers are unmoved", () => {
    for (const shelf of ["politics", "weather", "health", "soccer", "tennis"]) {
      expect(chipCategory(shelf)).toBe(shelf);
    }
  });

  it("is inert on the TRUNCATED segment — which is why the card passes the whole key", () => {
    // The prefixes carry the underscore. If this ever starts returning
    // "football", the card's call site has a second, silent way to be right and
    // the render assertions above stop proving anything.
    expect(chipCategory("americanfootball")).toBe("americanfootball");
    expect(getCat("americanfootball").emoji).toBe(FALLBACK);
  });

  it("hands an unknown key back unchanged, to fall through as before", () => {
    expect(chipCategory("quidditch_league")).toBe("quidditch_league");
    expect(getCat("quidditch_league").emoji).toBe(FALLBACK);
  });

  it("has nothing to say about nothing", () => {
    expect(chipCategory(null)).toBeUndefined();
    expect(chipCategory("")).toBeUndefined();
    expect(getCat(null).emoji).toBe(FALLBACK);
  });
});
