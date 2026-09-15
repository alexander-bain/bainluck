// #6249 — A CARD MAY ONLY SAY "ODDS AVAILABLE CLOSER TO THE EVENT" WHEN THAT IS TRUE.
//
// ── WHAT A READER SAW (production, 390px, 2026-09-14 ~23:1xZ) ────────────────
//
//   /sport/football            CHAMPIONSHIPS
//     Super Bowl                        College Football Playoff
//     Date TBD                          Date TBD
//     Odds available closer to          Odds available closer to
//     the event                         the event
//
// At that minute `/futures/86832` served 32 priced NFL teams, repriced that
// hour, and `/futures/31834253` served 36 Champions League clubs with a
// three-series trend chart. The page was denying content we hold, on the
// top-level page for the biggest US sport, in launch week.
//
// ── WHY IT COULD NEVER HAVE BEEN ANYTHING ELSE ───────────────────────────────
//
// The card had three branches: a golf tournament with a field, a tournament
// hub, else the sentence. `tournamentHubHref` opens with
// `if (sportSlug !== "tennis") return null`, so for ten of eleven sports the
// sentence was reached BY CONSTRUCTION — no market, however live, could change
// what the card said, because nothing on the path asked.
//
// ── WHAT THIS FILE PINS ──────────────────────────────────────────────────────
//
// The branch ORDER and the three renders. The other half of the fix — which
// market IS the Champions League — is not decided here and must not be: this
// component reads a server-resolved id. `backend/tests/test_showcase_futures_
// 6249.py` is where the men's/women's and league-phase refusals live.
//
// 🔴 THE NEGATIVE TEST IS THE LOAD-BEARING ONE. A fix that simply deleted the
// sentence would pass every positive assertion here and lose the card that is
// CORRECT for Wimbledon in September.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ShowcaseEventCard from "@/components/ShowcaseEventCard";
import type { SportShowcaseEvent } from "@/lib/types";

/** The claim that must not appear over a market we hold. */
const DENIAL = "Odds available closer to the event";

function render(sportSlug: string, event: SportShowcaseEvent): string {
  return renderToStaticMarkup(
    <ShowcaseEventCard sportSlug={sportSlug} event={event} />
  );
}

/** The Super Bowl as `/api/sports/hierarchy/football` serves it today. */
const SUPER_BOWL: SportShowcaseEvent = {
  name: "Super Bowl",
  type: "championship",
  futures_market_id: 86832,
  futures_priced_outcomes: 32,
};

/** Wimbledon in September: nothing to point at, and the card says so. */
const WIMBLEDON: SportShowcaseEvent = {
  name: "Wimbledon",
  type: "grand_slam",
  futures_market_id: null,
  futures_priced_outcomes: null,
};

describe("a showcase card over a market we hold", () => {
  it("links to that market and stops denying it", () => {
    const html = render("football", SUPER_BOWL);
    expect(html).toContain('href="/futures/86832"');
    expect(html).not.toContain(DENIAL);
    expect(html).not.toContain("Date TBD");
  });

  it("names the size of the field it is pointing at", () => {
    expect(render("football", SUPER_BOWL)).toContain(
      "Live probabilities · 32 contenders"
    );
  });

  it("says nothing about a count it was not given", () => {
    const html = render("soccer", {
      name: "Champions League",
      type: "championship",
      futures_market_id: 31834253,
      futures_priced_outcomes: null,
    });
    expect(html).toContain('href="/futures/31834253"');
    expect(html).toContain("Live probabilities");
    expect(html).not.toContain("contenders");
  });

  it("prints no date, because a market's close is not a competition's date", () => {
    // `resolution_date` on the Champions League market is 2027-06-05: the day
    // trading stops, not the day the final is played.
    expect(render("soccer", { ...SUPER_BOWL, name: "Champions League" })).not.toMatch(
      /20\d\d/
    );
  });
});

describe("a showcase card over nothing", () => {
  it("keeps the sentence that is true", () => {
    const html = render("tennis", WIMBLEDON);
    expect(html).toContain(DENIAL);
    expect(html).not.toContain("/futures/");
  });

  it("keeps it when the payload omits the keys entirely", () => {
    // An older server, or the list endpoint, sends `{name, type}` alone.
    const html = render("baseball", {
      name: "College World Series",
      type: "championship",
    });
    expect(html).toContain(DENIAL);
    expect(html).not.toContain("/futures/");
  });

  it("does not treat market id 0 as a market", () => {
    const html = render("baseball", {
      name: "College World Series",
      type: "championship",
      futures_market_id: 0,
      futures_priced_outcomes: 30,
    });
    expect(html).toContain(DENIAL);
    expect(html).not.toContain("/futures/0");
  });
});

describe("branch order", () => {
  it("prefers a hub to a market — the hub has the draw and the results", () => {
    const html = render("tennis", {
      name: "US Open",
      type: "grand_slam",
      futures_market_id: 999999,
      futures_priced_outcomes: 128,
    });
    expect(html).toContain('href="/tournaments/us-open"');
    expect(html).not.toContain("/futures/999999");
  });

  it("scopes the hub by sport, so the golf U.S. Open is not the tennis draw", () => {
    const html = render("golf", {
      name: "U.S. Open",
      type: "major",
      futures_market_id: 7,
      futures_priced_outcomes: 205,
    });
    expect(html).not.toContain("/tournaments/");
    expect(html).toContain('href="/futures/7"');
  });
});

describe("the card's vocabulary", () => {
  it("never says price, odds or bookmaker over a market we hold", () => {
    // Ruling 138 (probability, never price) and notice 33 (never "books" or
    // "bookmakers"). The denial card keeps the word "Odds" it has always had;
    // these assertions are about the card this ship adds.
    const html = render("football", SUPER_BOWL);
    expect(html.toLowerCase()).not.toMatch(/\bprice|bookmaker|\bbooks\b/);
  });
});
