// #4470 — THE DISCOVER GAME CARD'S TWO NUMBERS ARE BOTH VISIBLE, asserted on the
// colour the card actually paints.
//
// Production page one, 2026-09-09 12:45 PT, 390px: the live UCL card "Leeds
// United @ Chelsea" printed ONE win probability — `35%` on the right — and a bar
// whose left two thirds were blank. The payload carried both numbers
// (`away 0.6774 / home 0.3226`). Nothing was missing and nothing was mislaid out:
// `components/discover/EventCard.tsx` spent `teams.primary_color` directly on
// `style={{ color }}` and on `backgroundColor`, and Leeds United's stored colour
// is `#ffffff`. The card surface is `#FFFFFF`.
//
// Measured on the screenshot rather than inferred — a pixel scan of the two bar
// rows, control card first:
//
//   Galatasaray @ Sporting Lisbon   x91-281 #aa0031 · x282-688 #008127
//   Leeds United @ Chelsea          x90-479 (255,255,255) · x480-688 #374151
//
// The left segment was drawn at the right width (390/600 = 65%) in pure white.
// Ink census over the two label boxes: 924 non-white px on the control, 31 on the
// specimen. Sized against production: over the 326 distinct `teams.primary_color`
// values carried by teams on events in the trailing 7 days (479 coloured teams),
// 33 teams across 85 events composite below 1.5:1 against the card — Real Madrid,
// Tottenham, Borussia Dortmund, RB Leipzig, Fulham, Marseille, Lyon, Sevilla,
// Villarreal and Fenerbahce among them.
//
// ## The arm a lazier fix dies on
//
// `lib/probabilityBarPair.ts` already owns this rule and already names `#ffffff`
// in its docstring; this card simply never adopted it. But adopting it verbatim
// is the wrong fix, and measurably so: the module decides visibility on the pixel
// composited at `SEGMENT_OPACITY = 0.7`, because that is what `FeedCard` paints.
// THIS bar is opaque. Nine real team colours over 25 events in the same 7 days —
// Lakers gold `#fdb927` at 1.73:1 among them — are visible at full opacity and
// rejected at 0.7, so the verbatim adoption would replace a real brand colour
// with a generic grey for no reader gain. Counter-case (B) below is that arm, and
// it fails if the opacity argument is dropped.
//
// Both directions per gotcha #43: an invisible colour is forced to move AND a
// visible one is asserted UNCHANGED. `FeedCard`'s own pair is a control here too,
// because this ship edits the shared module it depends on.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EventCard } from "@/components/discover/EventCard";
import {
  CARD_SURFACE,
  MIN_SURFACE_CONTRAST,
  SEGMENT_OPACITY,
  contrastRatio,
  probabilityBarPair,
} from "@/lib/probabilityBarPair";
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

/** The pixel a reader sees for an OPAQUE segment: the colour itself. */
function visibleOnCard(hex: string): boolean {
  return contrastRatio(rgb(hex), rgb(CARD_SURFACE)) >= MIN_SURFACE_CONTRAST;
}

function teamData(primary: string | null) {
  if (primary === null) return null;
  return {
    team_id: 1,
    slug: "t",
    primary_color: primary,
    secondary_color: "#000000",
    logo_small: "https://example.invalid/l.png",
    logo_large: "https://example.invalid/l.png",
    record: "0-0-0",
    abbreviation: "TTT",
  };
}

function makeData(awayPrimary: string | null, homePrimary: string | null): FeedEventData {
  return {
    id: 15301293,
    external_id: "evt-15301293",
    sport: "soccer_epl",
    sport_name: "Premier League",
    sport_label: "CUP",
    home_team: "Chelsea",
    away_team: "Leeds United",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "live",
    home_score: 0,
    away_score: 1,
    current_odds: {
      home_probability: 0.3226,
      away_probability: 0.6774,
      home_rendered_percent: 32,
      away_rendered_percent: 68,
    },
    home_team_data: teamData(homePrimary),
    away_team_data: teamData(awayPrimary),
  } as unknown as FeedEventData;
}

function render(data: FeedEventData): string {
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

interface Painted {
  awayText: string;
  homeText: string;
  awayBar: string;
  homeBar: string;
}

/**
 * The colours the card PAINTS, read out of its own output.
 *
 * Deliberately not a call to `probabilityBarPair` — #2060's lesson, one layer up.
 * A helper-level assertion passes happily while the component still hands the raw
 * `awayColor` to the span, which is exactly the bug. Only the rendered style
 * attribute proves the card spent the rescued colour.
 */
function painted(data: FeedEventData): Painted {
  const html = render(data);

  const text = (side: "away" | "home"): string => {
    const m = html.match(
      new RegExp(`<span[^>]*style="color:([^";]+)[^>]*data-testid="event-card-${side}-probability"`)
    ) ?? html.match(
      new RegExp(`data-testid="event-card-${side}-probability"[^>]*style="color:([^";]+)`)
    );
    if (!m) {
      throw new Error(
        `no ${side} probability span with an inline colour.\n${html.slice(0, 1500)}`
      );
    }
    return m[1].trim();
  };

  const bars = [
    ...html.matchAll(/<div class="transition-all duration-500" style="width:[^";]+;background-color:([^";]+)"/g),
  ].map((m) => m[1].trim());
  if (bars.length !== 2) {
    throw new Error(
      `expected exactly two bar segments, found ${bars.length}.\n${html.slice(0, 1500)}`
    );
  }

  return { awayText: text("away"), homeText: text("home"), awayBar: bars[0], homeBar: bars[1] };
}

// The production specimen. Chelsea has no `teams` row on the served payload, so
// the home side already falls through to the card's slate default; Leeds carries
// the real `#ffffff`.
const LEEDS = "#ffffff";
const CHELSEA_FALLBACK = "#374151";

describe("#4470 — a Discover game card never paints a probability white on white", () => {
  it("the production specimen: Leeds United's number and bar segment are both visible", () => {
    const p = painted(makeData(LEEDS, null));

    expect(visibleOnCard(p.awayText)).toBe(true);
    expect(visibleOnCard(p.awayBar)).toBe(true);
    // Not merely "not white" — the raw colour is gone, both places.
    expect(p.awayText.toLowerCase()).not.toBe(LEEDS);
    expect(p.awayBar.toLowerCase()).not.toBe(LEEDS);
  });

  it("the number and its own bar segment are always the same colour", () => {
    // They are one team's half of the card; a fix that rescued the bar and left
    // the number would print a green 68% above a grey segment.
    for (const away of [LEEDS, "#ffff00", "#aa0031", null]) {
      const p = painted(makeData(away, null));
      expect(p.awayText.toLowerCase()).toBe(p.awayBar.toLowerCase());
      expect(p.homeText.toLowerCase()).toBe(p.homeBar.toLowerCase());
    }
  });

  it("the two sides stay visible AND distinguishable when BOTH colours are unusable", () => {
    const p = painted(makeData("#ffffff", "#fffff0"));
    expect(visibleOnCard(p.awayBar)).toBe(true);
    expect(visibleOnCard(p.homeBar)).toBe(true);
    expect(p.awayBar.toLowerCase()).not.toBe(p.homeBar.toLowerCase());
  });

  // COUNTER-CASE (A): the control card from the same screenshot. Two real,
  // visible colours must survive untouched — the fix corrects white-on-white, it
  // does not re-brand the league.
  it("the control pair from the same page is unchanged", () => {
    const p = painted(makeData("#aa0031", "#008127"));
    expect(p.awayBar.toLowerCase()).toBe("#aa0031");
    expect(p.homeBar.toLowerCase()).toBe("#008127");
    expect(p.awayText.toLowerCase()).toBe("#aa0031");
    expect(p.homeText.toLowerCase()).toBe("#008127");
  });

  // COUNTER-CASE (B): the arm that fails if the opacity argument is dropped and
  // the module's 0.7 default is used to decide an opaque bar.
  it.each([
    ["#fdb927", "Lakers gold"],
    ["#7ccdef", "Kansas City Current sky"],
    ["#ffc72c", "a 1.56:1 gold"],
    ["#a7c6ed", "a 1.76:1 powder blue"],
  ])("keeps %s (%s), which a reader CAN see at full opacity", (hex) => {
    // Establish the premise rather than assume it: this colour is above the floor
    // opaque and below it at FeedCard's opacity, so the two decisions differ here.
    expect(visibleOnCard(hex)).toBe(true);
    const at07 = rgb(hex).map((v) => SEGMENT_OPACITY * v + (1 - SEGMENT_OPACITY) * 255) as Rgb;
    expect(contrastRatio(at07, rgb(CARD_SURFACE))).toBeLessThan(MIN_SURFACE_CONTRAST);

    const p = painted(makeData(hex, null));
    expect(p.awayBar.toLowerCase()).toBe(hex.toLowerCase());
    expect(p.awayText.toLowerCase()).toBe(hex.toLowerCase());
  });

  // The card's own default for a team with no row at all still has to be visible
  // and distinct — this is the side of the production specimen that was FINE, and
  // it must stay fine.
  it("keeps the card's slate default for a team with no row", () => {
    const p = painted(makeData(LEEDS, null));
    expect(p.homeBar.toLowerCase()).toBe(CHELSEA_FALLBACK);
    expect(visibleOnCard(p.homeBar)).toBe(true);
    expect(p.homeBar.toLowerCase()).not.toBe(p.awayBar.toLowerCase());
  });

  // The 33 real teams the census named. Every one of them, through the component.
  it.each([
    ["#ffffff", "Real Madrid, Tottenham, Leeds, Fulham, RB Leipzig, Marseille, Lyon, Sevilla, Valencia (22 teams / 61 events)"],
    ["#ffff00", "Villarreal, AEK Athens, Fenerbahce (4 teams / 8 events)"],
    ["#ffee00", "Borussia Dortmund (2 teams / 4 events)"],
    ["#FCED0B", "Lecce"],
    ["#ece83a", "Nashville SC"],
    ["#FCEE33", "Bodo/Glimt"],
    ["#b9e8f0", "Malaga"],
    ["#cee5eb", "Portland Fire"],
  ])("rescues %s — %s", (hex) => {
    expect(visibleOnCard(hex)).toBe(false); // the premise: it really is invisible
    const p = painted(makeData(hex, null));
    expect(visibleOnCard(p.awayBar)).toBe(true);
    expect(visibleOnCard(p.awayText)).toBe(true);
  });
});

// This ship edits the module `FeedCard` depends on. Its behaviour is the control.
describe("#4470 — the shared rule's default is untouched, so FeedCard is untouched", () => {
  it("the two-argument call still decides at SEGMENT_OPACITY", () => {
    // Lakers gold is the discriminating colour: kept at opacity 1, rescued at 0.7.
    expect(probabilityBarPair("#fdb927", "#008127").away).not.toBe("#fdb927");
    expect(probabilityBarPair("#fdb927", "#008127", 1).away).toBe("#fdb927");
  });

  it.each([
    ["#ffffff", null],
    [null, null],
    ["#aa0031", "#008127"],
    ["#fdb927", null],
  ])("pair(%s, %s) is identical with the default argument omitted or passed", (a, b) => {
    expect(probabilityBarPair(a, b)).toEqual(probabilityBarPair(a, b, SEGMENT_OPACITY));
  });
});
