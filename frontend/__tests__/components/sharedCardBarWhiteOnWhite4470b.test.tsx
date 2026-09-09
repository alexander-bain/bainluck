// #4470b — THE SHARED GAME CARD'S PROBABILITY BAR IS VISIBLE ON BOTH SIDES,
// asserted on the colour the card actually paints, at the opacity it paints it.
//
// ═══ THE DEFECT, MEASURED ═══
//
// `components/EventCard.tsx` is the shared card — /sports, league, search and
// my-stuff. It is a different file from the Discover card discover/023 fixed
// under #4470, and it reached the same defect by a different route: it rendered
// `<ProbabilityBar useCSSVars />`, and `ProbabilityBar` painted both halves
// `rgb(var(--team-*-primary))`, i.e. the raw `teams.primary_color` with no rule
// applied at all. 22 teams carry `#ffffff`; the card surface is `#FFFFFF`.
//
// Measured on production at 390px on 2026-09-09, reading the COMPOSITED pixel of
// every `[role="meter"]` segment on six league pages:
//
//   league                     segments   below 1.5:1
//   soccer_spain_la_liga             48            13
//   soccer_germany_bundesliga        36             6
//   soccer_france_ligue_one          36             6
//   soccer_epl                       40             4
//   soccer_italy_serie_a             48             5
//   soccer_uefa_champs_league        12             2
//   TOTAL                           220            36  (16.4%)
//
// 26 of the 36 sat at exactly 1.00 — pure white on white: Sevilla, Valencia,
// Leeds United, Fulham, Real Madrid, Augsburg, Eintracht Frankfurt, Borussia
// Mönchengladbach, Werder Bremen, Real Racing Santander, Alavés, Rayo Vallecano.
// The others were Fenerbahçe `#ffff00` (1.05), Bodø/Glimt `#fcee33` (1.09) and
// Celta/Málaga `#b9e8f0` (1.12). The bar did not print a faint segment; on those
// rows it printed nothing, on the side the card is about.
//
// ═══ THE ARM A SINGLE-OPACITY FIX DIES ON ═══
//
// This bar is not uniform, and that is deliberate design, not a defect: the
// favourite paints at opacity 1 and the underdog at 0.4, so the bar says who is
// ahead before it is read. `probabilityBarPair` took ONE opacity for both halves
// (`SEGMENT_OPACITY` for FeedCard, `1` for the Discover card under #4470), and
// neither scalar is right here. Replayed over the 324 distinct team colours on
// events in the 7 days to 2026-09-09:
//
//   opacity 1.0 : 8 colours below the floor — 33 teams,  85 events (4.0%)
//   opacity 0.7 : 17 colours                — 42 teams, 110 events (5.2%)
//   opacity 0.4 : 36 colours                — 64 teams, 176 events (8.2%)
//
// Lakers gold `#fdb927` is the discriminating specimen and it is a real colour,
// the one discover/023 named when warning against over-rescue: **1.73:1 at
// opacity 1, 1.25:1 at 0.4.** Decide it at 1 and the dimmed half stays invisible;
// decide it at 0.4 and a perfectly visible brand colour is replaced by a generic
// ladder colour for no reader gain. The two arms below pin BOTH directions on
// that one hex, and no scalar opacity can pass them both.
//
// ═══ THE GAP THIS SHIP HAD TO CLOSE IN THE MODULE ITSELF ═══
//
// `probabilityBarPair`'s final branch — neither side has a usable colour — used
// to return `AWAY_DEFAULT`/`HOME_DEFAULT` without checking them. At 0.7 they are
// 1.85:1 and 1.94:1 and nobody noticed. At 0.4 they are **1.40:1 and 1.46:1**,
// below the module's own floor. Since a card with no team colours is the common
// case, shipping the per-opacity decision without closing that would have put a
// bar that fails its own contract on most of the page. The defaults now walk the
// ladder like any other colour, and the FeedCard control arm proves that costs
// FeedCard nothing.
//
// ═══ BOTH DIRECTIONS (gotcha #43) ═══
//
// Every rescue arm is paired with a KEEP arm. A fix that painted everything
// indigo would pass "the white segment moved" and fail this file.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("next/link", () => {
  const Mock = ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
    React.createElement("a", { href, ...props }, children);
  return { __esModule: true, default: Mock };
});
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import { FAVORITE_OPACITY, UNDERDOG_OPACITY } from "@/components/ProbabilityBar";
import {
  AWAY_DEFAULT,
  CARD_SURFACE,
  HOME_DEFAULT,
  MIN_SURFACE_CONTRAST,
  SEGMENT_OPACITY,
  contrastRatio,
  probabilityBarPair,
} from "@/lib/probabilityBarPair";
import type { Event } from "@/lib/types";

type Rgb = [number, number, number];

function rgb(hex: string): Rgb {
  const clean = hex.trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) {
    throw new Error(`not a paintable hex colour: ${JSON.stringify(hex)}`);
  }
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

/** The pixel a reader sees: `hex` at `opacity` over the card. */
function paintedPixel(hex: string, opacity: number): Rgb {
  const c = rgb(hex);
  const s = rgb(CARD_SURFACE);
  return [0, 1, 2].map((i) => opacity * c[i] + (1 - opacity) * s[i]) as Rgb;
}

function visibleAt(hex: string, opacity: number): boolean {
  return (
    contrastRatio(paintedPixel(hex, opacity), rgb(CARD_SURFACE)) >= MIN_SURFACE_CONTRAST
  );
}

interface Segment {
  color: string;
  opacity: number;
}

/**
 * The two segments the card PAINTS, read out of its own rendered output.
 *
 * Deliberately not a call to `probabilityBarPair`. A helper-level assertion
 * passes happily while the component still hands `rgb(var(--team-home-primary))`
 * to `backgroundColor`, which was exactly the bug — the module has owned this
 * rule since #2962 and this card simply never called it. Only the rendered style
 * attribute proves the card spent the decided colour.
 *
 * The opacity is read from the SAME attribute for the same reason: the whole
 * point of the ship is that the colour and the opacity agree, so a probe that
 * took the colour from the DOM and the opacity from a constant could not see
 * them disagree.
 */
function segments(event: Event): { home: Segment; away: Segment } {
  const html = renderToStaticMarkup(<EventCard event={event} />);
  const meter = html.indexOf('role="meter"');
  if (meter < 0) {
    throw new Error(`the card rendered no probability bar.\n${html.slice(0, 1200)}`);
  }
  const found = [
    ...html
      .slice(meter)
      .matchAll(/style="background-color:([^";]+);opacity:([^";]+)[^"]*"/g),
  ].map((m) => ({ color: m[1].trim(), opacity: Number(m[2]) }));

  if (found.length !== 2) {
    throw new Error(
      `expected exactly two bar segments, found ${found.length}.\n` +
        html.slice(meter, meter + 900)
    );
  }
  // The bar renders home first, then away.
  return { home: found[0], away: found[1] };
}

/**
 * A league card. `homeProb` decides which side is the favourite and therefore
 * which side is dimmed, which is the axis this whole file turns on.
 */
function makeEvent(
  awayPrimary: string | null,
  homePrimary: string | null,
  homeProb: number
): Event {
  const teamData = (primary: string | null) =>
    primary === null ? null : { primary_color: primary, logo_small: "l.png" };
  return {
    id: 15301293,
    external_id: "evt-15301293",
    sport: "soccer_epl",
    sport_name: "Premier League",
    home_team: "Chelsea",
    away_team: "Leeds United",
    commence_time: "2030-01-01T12:00:00Z",
    status: "scheduled",
    home_team_data: teamData(homePrimary),
    away_team_data: teamData(awayPrimary),
    current_odds: {
      home_probability: homeProb,
      away_probability: 1 - homeProb,
    },
  } as unknown as Event;
}

// Real production specimens, all read off bainluck.com on 2026-09-09.
const WHITE = "#ffffff"; // Sevilla, Valencia, Leeds, Fulham, Real Madrid, Augsburg…
const LAKERS_GOLD = "#fdb927"; // 1.73:1 at opacity 1, 1.25:1 at 0.4
const SLATE = "#374151"; // a colour that is comfortably visible at both
const HOME_FAVOURITE = 0.62;
const AWAY_FAVOURITE = 0.38;

describe("#4470b — the shared card's bar never paints an invisible segment", () => {
  describe("the production specimens", () => {
    it("white on the DIMMED side is rescued — Leeds United at 38%", () => {
      const { away } = segments(makeEvent(WHITE, SLATE, HOME_FAVOURITE));

      expect(away.opacity).toBe(UNDERDOG_OPACITY);
      expect(away.color.toLowerCase()).not.toBe(WHITE);
      expect(visibleAt(away.color, away.opacity)).toBe(true);
    });

    it("white on the BRIGHT side is rescued too — Sevilla at 60%", () => {
      // 10 of the 36 failing segments were at opacity 1. A fix that only
      // considered the dimmed half would leave those exactly as they were.
      const { home } = segments(makeEvent(SLATE, WHITE, HOME_FAVOURITE));

      expect(home.opacity).toBe(FAVORITE_OPACITY);
      expect(home.color.toLowerCase()).not.toBe(WHITE);
      expect(visibleAt(home.color, home.opacity)).toBe(true);
    });

    it("a visible colour is left alone — no re-branding", () => {
      const { home, away } = segments(makeEvent(SLATE, SLATE, HOME_FAVOURITE));

      expect(home.color.toLowerCase()).toBe(SLATE);
      expect(away.color.toLowerCase()).toBe(SLATE);
    });
  });

  describe("the decision is made at the opacity the segment is painted at", () => {
    // Lakers gold: visible at 1, invisible at 0.4. No single scalar opacity can
    // satisfy both of these; together they are the ship.

    it("Lakers gold is KEPT when it is the favourite's colour (opacity 1)", () => {
      const { home } = segments(makeEvent(SLATE, LAKERS_GOLD, HOME_FAVOURITE));

      expect(home.opacity).toBe(FAVORITE_OPACITY);
      expect(home.color.toLowerCase()).toBe(LAKERS_GOLD);
      expect(visibleAt(LAKERS_GOLD, FAVORITE_OPACITY)).toBe(true);
    });

    it("Lakers gold is RESCUED when it is the underdog's colour (opacity 0.4)", () => {
      const { home } = segments(makeEvent(SLATE, LAKERS_GOLD, AWAY_FAVOURITE));

      expect(home.opacity).toBe(UNDERDOG_OPACITY);
      expect(home.color.toLowerCase()).not.toBe(LAKERS_GOLD);
      expect(visibleAt(home.color, home.opacity)).toBe(true);
      // The premise both arms rest on, asserted rather than assumed — if the
      // floor or the underdog opacity ever moves, this file says so out loud
      // instead of quietly testing nothing.
      expect(visibleAt(LAKERS_GOLD, UNDERDOG_OPACITY)).toBe(false);
    });
  });

  describe("a card with no team colours", () => {
    it("both segments are visible — including the dimmed one", () => {
      // The module's own defaults are 1.40:1 and 1.46:1 at 0.4, below its floor.
      // This is the common case on production, not an edge case.
      const { home, away } = segments(makeEvent(null, null, HOME_FAVOURITE));

      expect(visibleAt(home.color, home.opacity)).toBe(true);
      expect(visibleAt(away.color, away.opacity)).toBe(true);
    });

    it("the two segments are not the same colour — the #2902 flat block", () => {
      const { home, away } = segments(makeEvent(null, null, HOME_FAVOURITE));

      expect(home.color.toLowerCase()).not.toBe(away.color.toLowerCase());
    });
  });

  describe("controls — what this ship must NOT have moved", () => {
    it("FeedCard's scalar call is bit-identical, defaults included", () => {
      // The whole reason the defaults could go unchecked for so long: at 0.7
      // they pass. Closing the gap must therefore cost FeedCard nothing.
      expect(probabilityBarPair(null, null)).toEqual({
        away: AWAY_DEFAULT,
        home: HOME_DEFAULT,
      });
      expect(probabilityBarPair(null, null, SEGMENT_OPACITY)).toEqual({
        away: AWAY_DEFAULT,
        home: HOME_DEFAULT,
      });
      for (const pair of [
        [WHITE, SLATE],
        [SLATE, WHITE],
        [LAKERS_GOLD, SLATE],
        [null, SLATE],
      ] as const) {
        expect(probabilityBarPair(pair[0], pair[1])).toEqual(
          probabilityBarPair(pair[0], pair[1], SEGMENT_OPACITY)
        );
      }
    });

    it("a scalar opacity and the equivalent pair agree", () => {
      for (const op of [1, SEGMENT_OPACITY, UNDERDOG_OPACITY]) {
        expect(probabilityBarPair(WHITE, LAKERS_GOLD, op)).toEqual(
          probabilityBarPair(WHITE, LAKERS_GOLD, { away: op, home: op })
        );
      }
    });

    it("the dimming still marks the favourite", () => {
      // The bar's design is untouched: this ship changed which colour is
      // painted, never which half is bright.
      const homeFav = segments(makeEvent(SLATE, SLATE, HOME_FAVOURITE));
      expect(homeFav.home.opacity).toBe(FAVORITE_OPACITY);
      expect(homeFav.away.opacity).toBe(UNDERDOG_OPACITY);

      const awayFav = segments(makeEvent(SLATE, SLATE, AWAY_FAVOURITE));
      expect(awayFav.home.opacity).toBe(UNDERDOG_OPACITY);
      expect(awayFav.away.opacity).toBe(FAVORITE_OPACITY);
    });
  });

  it("no bar segment is painted from a CSS variable", () => {
    // The structural half of the fix. A variable cannot be reasoned about, so
    // while either half read one, no rule could be applied to it — which is why
    // this defect survived two sibling fixes to the same class.
    //
    // Comments are stripped first, deliberately. The prose above this component
    // and inside it NAMES `rgb(var(--team-home-primary))` in order to explain
    // what was removed, and a guard that cannot tell a comment from code would
    // be permanently red for the documentation that makes it understandable.
    const source = readFileSync(
      join(__dirname, "..", "..", "components", "ProbabilityBar.tsx"),
      "utf8"
    );
    const code = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");

    expect(code).not.toContain("var(--team-");
    expect(code).not.toContain("useCSSVars");
    // …and the module that owns the rule is genuinely reached.
    expect(code).toContain("probabilityBarPair");
  });
});
