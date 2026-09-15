// #2621, ux half — ONE CHIP, ONE COMPETITION, AND IT STAYS OUT FROM UNDER "LIVE".
//
// ── WHAT A READER SAW (production, 390px, the default landing page) ──────────
//
// Two defects on one element, both measured on 2026-09-15 over the 2,148 events
// with `commence_time` in NOW-2d..+7d:
//
//  (1) THE CHIP NAMED NINE SPORTS AT ONCE. `feed.py::_get_sport_label` derives
//      the served `sport_label` by keeping every segment of the sport key but the
//      leading sport FAMILY. Two competitions that differ only in their family
//      therefore collapse onto one word. 852 of 2,148 events (40%) wore a chip
//      another sport also wore:
//         OTHER              806 events  soccer_other 404, tennis_other 288,
//                                        baseball, basketball, cricket, esports,
//                                        americanfootball, icehockey, motorsport
//         GERMANY BUNDESLIGA  25 events  handball + soccer
//         SWEDEN ALLSVENSKAN  21 events  soccer + ice hockey
//      The same games on `/sports` and in `FeedCard` read "Other Soccer" and
//      "Handball-Bundesliga", because those two call `getSportLabel` — so this
//      surface was also the one disagreeing with its own card family (notice 35).
//
//  (2) THE "LIVE" BADGE SAT ON TOP OF THE CHIP'S TAIL. The chip (`absolute
//      top-3 left-3`) and the badge (`absolute top-3 left-1/2 -translate-x-1/2`)
//      were independent absolutes with nothing between them. At 390px the card
//      measures 334px and the badge starts at 136px, which a chip reaches at
//      about fifteen characters. 505 of the 2,148 events (24%) carry a label that
//      long. Photographed: `UEFA EUROPA LEAGUE` rendering as `UEFA EUROPA LEA`
//      with the badge over the rest
//      (`artifacts/ux-1270/before-chip-under-live-UEFA.png`).
//
// ── 🔴 WHY (2) IS ASSERTED STRUCTURALLY AND WHAT THAT DOES NOT PROVE ────────
//
// `renderToStaticMarkup` has no layout engine, so no test in this file can
// measure a pixel. What it CAN pin is the thing that made the overlap possible:
// the two pills being siblings positioned independently. The assertions below
// require them to share one flex row and require the badge NOT to carry its own
// centring, which makes the overlap unrepresentable rather than merely absent
// today. The pixel claim is paid by `tools/discover-chip-fit-2621.mjs` against
// production's own fonts and card width, not here.
//
// ── BOTH DIRECTIONS (gotcha #43) ────────────────────────────────────────────
//
// The short curated keys are the control. `MLB`, `NFL`, `EPL` and `US OPEN` were
// always correct and always fitted; a change that moved them is changing the
// wrong thing, so they are asserted byte-for-byte on the chip's text.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EventCard } from "@/components/discover/EventCard";
import { getSportLabel } from "@/lib/sportCategories";
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

type Opts = { servedLabel?: string | null; live?: boolean; trending?: boolean };

function render(sportKey: string | null, sportName: string | null, opts: Opts = {}): string {
  const data = {
    id: 15305024,
    external_id: `evt-${sportKey}`,
    sport: sportKey,
    sport_name: sportName,
    // The served label is deliberately the COLLIDING one in most cases below:
    // if the card still reads it, the collision comes straight back.
    sport_label: opts.servedLabel === undefined ? "COLLIDING" : opts.servedLabel,
    home_team: "Home",
    away_team: "Away",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: opts.live ? "live" : "upcoming",
    home_score: opts.live ? 1 : null,
    away_score: opts.live ? 0 : null,
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
      trending={!!opts.trending}
    />
  );
}

/** The chip's own text, read out of the rendered pill rather than the whole card. */
function chipText(html: string): string {
  const m = html.match(/rounded-full backdrop-blur-sm[^>]*>(.*?)<\/div>/);
  if (!m) throw new Error("no chip pill in the render");
  return m[1].replace(/<[^>]*>/g, "").replace(/&#x27;/g, "'").trim();
}

/** The chip's text with the sport glyph dropped — the words, on their own. */
function chipLabel(html: string): string {
  return chipText(html).split(" ").slice(1).join(" ");
}

// The sport keys that shared a chip, with the `sports.name` production actually
// serves beside each — re-read from production at 2026-09-15T08:40Z, by name,
// rather than carried over from the build. That re-read corrected two rows:
// `icehockey_sweden_allsvenskan` serves "HockeyAllsvenskan" (this list said
// "SHL - Sweden", which production has never served for that key), and
// `rugby_other` is a TENTH sport on the `OTHER` chip that the first pass missed.
// The served name is not decoration here: `getSportLabel` returns it verbatim
// whenever it is not raw, so a wrong name in this fixture tests a payload that
// does not exist.
//
// The handball/soccer Bundesliga pair has NO fixtures in the current window —
// handball is between seasons — so it is not one of today's live collisions. It
// stays because the collision is structural in the key, not seasonal: both keys
// derive the chip "GERMANY BUNDESLIGA" the moment handball plays again.
const COLLIDED: Array<[string, string]> = [
  ["soccer_other", "soccer_other"],
  ["tennis_other", "tennis_other"],
  ["baseball_other", "baseball_other"],
  ["basketball_other", "basketball_other"],
  ["cricket_other", "cricket_other"],
  ["esports_other", "esports_other"],
  ["americanfootball_other", "americanfootball_other"],
  ["icehockey_other", "icehockey_other"],
  ["motorsport_other", "motorsport_other"],
  ["rugby_other", "rugby_other"],
  ["handball_germany_bundesliga", "Handball-Bundesliga"],
  ["soccer_germany_bundesliga", "Bundesliga - Germany"],
  ["soccer_sweden_allsvenskan", "Allsvenskan - Sweden"],
  ["icehockey_sweden_allsvenskan", "HockeyAllsvenskan"],
];

describe("#2621(a) — the chip stops naming more than one competition", () => {
  it("no two of the fourteen keys that collided render the same chip", () => {
    // Asserted on the WORDS, not on `chipText`. Two of these pairs sit in
    // different categories and so carry different glyphs — a distinctness test
    // over the whole pill is satisfiable by the emoji alone while both chips
    // still say the same thing, which is the defect.
    const labels = COLLIDED.map(([k, n]) => chipLabel(render(k, n)));
    expect(new Set(labels).size).toBe(COLLIDED.length);
  });

  it("the ten sports that all read OTHER each name their own sport", () => {
    // 804 of the window's 2,133 events at the 08:40Z re-read — the largest single
    // defect on the surface. The word that replaced them has to be the reader's
    // word, not merely a different one, so these are asserted by value.
    expect(chipText(render("soccer_other", "soccer_other"))).toContain("Other Soccer");
    expect(chipText(render("tennis_other", "tennis_other"))).toContain("Other Tennis");
    expect(chipText(render("basketball_other", "basketball_other"))).toContain("Other Basketball");
    expect(chipText(render("icehockey_other", "icehockey_other"))).toContain("Other Hockey");
    expect(chipText(render("rugby_other", "rugby_other"))).toContain("Other Rugby");
  });

  it("the handball Bundesliga is not the football Bundesliga", () => {
    // 🔴 This assertion was VACUOUS on `chipText` and only the red-first pass
    // said so: handball and soccer draw different glyphs, so "🤾 COLLIDING" and
    // "⚽ COLLIDING" compare unequal while both chips read the same WORD. The
    // emoji is not the claim — the competition name is.
    expect(chipLabel(render("handball_germany_bundesliga", "Handball-Bundesliga")))
      .not.toBe(chipLabel(render("soccer_germany_bundesliga", "Bundesliga - Germany")));
  });

  it("🔴 the served label is NOT read — the collision cannot come back through it", () => {
    // The whole defect was this field winning. A payload whose `sport_label`
    // says one thing and whose key says another must render the key's answer;
    // if this flips, every assertion above is satisfiable by the old code.
    const html = render("soccer_other", "soccer_other", { servedLabel: "OTHER" });
    expect(chipText(html)).toContain("Other Soccer");
    expect(chipText(html)).not.toBe("⚽ OTHER");
  });

  it("agrees with the chip its two siblings print for the same game", () => {
    // `components/EventCard.tsx:470` and `components/FeedCard.tsx:471` both call
    // `getSportLabel(sport, sport_name)`. Notice 35: one card family, one word.
    for (const [k, n] of COLLIDED) {
      expect(chipText(render(k, n))).toContain(getSportLabel(k, n));
    }
  });
});

describe("#2621(a) control — the keys that were already right do not move", () => {
  it.each([
    ["baseball_mlb", "MLB", "MLB"],
    ["americanfootball_nfl", "NFL", "NFL"],
    ["soccer_epl", "EPL", "EPL"],
    ["tennis_atp_us_open", "ATP US Open", "US Open"],
  ])("%s still reads %s", (key, served, expected) => {
    expect(chipLabel(render(key, served))).toBe(expected);
  });

  it("a payload with no sport key keeps the old ladder rather than saying 'Sports'", () => {
    // `sport_label` is set only on the event-card path, so a card that carries
    // one and no key must still print it — the guard exists because the obvious
    // simplification (always call getSportLabel) makes this card read "Sports".
    expect(chipText(render(null, null, { servedLabel: "MLB" }))).toContain("MLB");
  });
});

describe("#2621(b) — the LIVE badge can no longer sit on the chip", () => {
  it("the badge is not independently centred any more", () => {
    // `left-1/2 -translate-x-1/2` on a sibling absolute IS the overlap: it puts
    // the badge at a fixed pixel the chip is free to grow past.
    const html = render("soccer_uefa_europa_league", "UEFA Europa League", { live: true });
    expect(html).toContain("LIVE");
    expect(html).not.toContain("left-1/2 -translate-x-1/2");
  });

  it("the chip and the badge are in one flex row", () => {
    const html = render("soccer_uefa_europa_league", "UEFA Europa League", { live: true });
    // The row: one absolute, left-anchored, that both pills sit inside.
    const row = html.match(/<div class="absolute top-3 left-3 [^"]*flex items-center gap-2"><div class="min-w-0 truncate[\s\S]*?<\/div><div class="shrink-0 flex items-center gap-1\.5 bg-red-500[\s\S]*?<\/div><\/div>/);
    expect(row).not.toBeNull();
  });

  it("the chip truncates rather than growing without bound", () => {
    const html = render("soccer_austria_bundesliga", "Austrian Football Bundesliga");
    expect(html).toMatch(/class="min-w-0 truncate/);
  });

  it("the row reserves the trending pill's corner when there is one", () => {
    // #4131 keeps that pill `absolute right-12`, so the row yields to it instead
    // of moving it. Without this the longest chips run under "🔥 Trending".
    expect(render("soccer_uefa_europa_league", "UEFA Europa League", { trending: true }))
      .toContain("absolute top-3 left-3 right-36 flex items-center gap-2");
    expect(render("soccer_uefa_europa_league", "UEFA Europa League"))
      .toContain("absolute top-3 left-3 right-12 flex items-center gap-2");
  });

  it("a card that is not live renders no badge at all (control)", () => {
    const html = render("baseball_mlb", "MLB");
    expect(html).not.toContain("bg-red-500/90");
  });
});
