// #8841 — AN UNANNOUNCED START PRINTS ITS DAY AND "TBD", NOT A MADE-UP CLOCK.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Production 2026-09-26 ~15:20Z, `/search?q=red%20sox` at 390px: the Red Sox @
// Yankees Wild Card card read "Sep 29 1:00 PM". MLB had not set the time; ESPN
// carried `timeValid=false`. StatPal lists postseason games before their times
// exist and stamps them on the hour (20:00Z), and we printed the stamp.
//
// ── THE PAIR ─────────────────────────────────────────────────────────────────
//
// authority's PR #8856 (CERT-3567) puts `start_is_tbd` on `_format_event` (the
// search results, sports rails and event page) and on the team page's
// `_format_event_brief`. This half reads it on the four places a reader meets
// the clock: the shared card (search + sports), the team page's upcoming card
// and the event hero.
//
// Assertions test the PRESENCE OR ABSENCE OF A CLOCK, never a particular hour,
// so they hold in every timezone (the #3829 guard's rule). Every flag-true arm
// has a flag-absent control that DOES print a clock on the same row — without
// it, a card that printed nothing at all would pass.

import { readFileSync } from "fs";
import { join } from "path";
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
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import { UpcomingGameCard } from "@/components/TeamGameCards";
import { formatTbdStartLabel } from "@/lib/gameTimeLabel";
import { formatEventStartLabel, startClockState } from "@/lib/eventKeyStats";
import type { Event } from "@/lib/types";
import type { TeamGameBrief } from "@/lib/api";

/** Any "H:MM" — the thing the reader must not see when we do not know it. */
const A_CLOCK = /\d{1,2}:\d{2}/;

/** The specimen's placeholder, and the moment the defect was seen. */
const WILD_CARD_G1 = "2026-09-29T20:00:00+00:00";
const SEEN_AT = Date.parse("2026-09-26T15:20:00Z");

// Offsets for the rendered cards, which read the ambient clock (gotcha #44):
// three days out is never Today/Tomorrow in any zone.
const DAY = 24 * 3600_000;
const IN_3_DAYS = new Date(Date.now() + 3 * DAY).toISOString();

describe("#8841 formatTbdStartLabel — the day survives, the clock does not", () => {
  it("prints the specimen as its day and TBD", () => {
    expect(formatTbdStartLabel(WILD_CARD_G1, SEEN_AT)).toBe("Sep 29 · TBD");
  });

  it("says Today / Tomorrow against the reader's day", () => {
    expect(formatTbdStartLabel(WILD_CARD_G1, Date.parse("2026-09-29T12:00:00Z"))).toBe(
      "Today · TBD",
    );
    expect(formatTbdStartLabel(WILD_CARD_G1, Date.parse("2026-09-28T12:00:00Z"))).toBe(
      "Tomorrow · TBD",
    );
  });

  it("reads the placeholder's day in UTC, never localised (#4344)", () => {
    // ESPN's midnight-in-the-venue placeholder: Flushing midnight Friday is
    // 04:00Z Friday. The day it names is Sep 11 in whatever zone runs this.
    // ⚠️ The suite is pinned to UTC (#2462), so here this arm cannot tell a
    // UTC read from a local one — it pins the output shape only. The frame
    // itself is the same `getUTC*` read as `placeholderDayKey`.
    expect(formatTbdStartLabel("2026-09-11T04:00:00Z", SEEN_AT)).toBe("Sep 11 · TBD");
  });

  it("renders nothing rather than 'Invalid Date'", () => {
    expect(formatTbdStartLabel(null, SEEN_AT)).toBe("");
    expect(formatTbdStartLabel("not a date", SEEN_AT)).toBe("");
  });
});

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15319235,
    external_id: "statpal-mlb-wc1",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "New York Yankees",
    away_team: "Boston Red Sox",
    commence_time: IN_3_DAYS,
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_team_data: { primary_color: "#0C2340", logo_small: "h.png" },
    away_team_data: { primary_color: "#BD3039", logo_small: "a.png" },
    current_odds: {
      captured_at: new Date().toISOString(),
      home_probability: 0.56,
      away_probability: 0.44,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  } as unknown as Event;
}

describe("#8841 the shared card (search results + sports rails)", () => {
  it("prints the day and TBD, and no clock, when the start is a placeholder", () => {
    const html = renderToStaticMarkup(<EventCard event={makeEvent({ start_is_tbd: true })} />);
    expect(html).toContain(formatTbdStartLabel(IN_3_DAYS));
    expect(html).toContain("· TBD");
    expect(html).not.toMatch(A_CLOCK);
  });

  it("CONTROL: the same row without the flag prints its clock", () => {
    for (const flag of [undefined, null, false]) {
      const html = renderToStaticMarkup(
        <EventCard event={makeEvent({ start_is_tbd: flag })} />,
      );
      expect(html).toMatch(A_CLOCK);
      expect(html).not.toContain("TBD");
    }
  });
});

function brief(over: Partial<TeamGameBrief> = {}): TeamGameBrief {
  return {
    id: 15319235,
    home_team: "New York Yankees",
    away_team: "Boston Red Sox",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: IN_3_DAYS,
    sport_key: "baseball_mlb",
    is_home: false,
    opponent: "New York Yankees",
    win_probability: 0.44,
    ...over,
  };
}

describe("#8841 the team page's upcoming card", () => {
  for (const [arm, wp] of [["with a probability", 0.44], ["without one", null]] as const) {
    it(`prints the day and TBD, no clock and no "Starts" — ${arm}`, () => {
      const html = renderToStaticMarkup(
        <UpcomingGameCard
          game={brief({ start_is_tbd: true, win_probability: wp })}
          teamName="Boston Red Sox"
          teamColor={null}
        />,
      );
      expect(html).toContain(formatTbdStartLabel(IN_3_DAYS));
      expect(html).not.toMatch(A_CLOCK);
      expect(html).not.toContain("Starts");
    });

    it(`CONTROL: without the flag it prints its clock — ${arm}`, () => {
      const html = renderToStaticMarkup(
        <UpcomingGameCard
          game={brief({ win_probability: wp })}
          teamName="Boston Red Sox"
          teamColor={null}
        />,
      );
      expect(html).toMatch(A_CLOCK);
      expect(html).not.toContain("TBD");
    });
  }
});

describe("#8841 the event hero", () => {
  it("an MLB page (no tournament request) goes TBD on the event's own flag", () => {
    // `isTournamentSport: false` — MLB never asks `by-event`, so before this
    // ship the hero had no input that could say TBD for it.
    const state = startClockState({
      startIsTbd: true,
      isTournamentSport: false,
      tournamentResolved: false,
    });
    expect(state).toBe("tbd");
    expect(formatEventStartLabel(WILD_CARD_G1, state)).toBe("Sep 29, 2026 · TBD");
    expect(formatEventStartLabel(WILD_CARD_G1, "clock")).toMatch(A_CLOCK);
  });

  it("the page feeds the event payload's flag into that state", () => {
    // Source scan: the page is a default export with no seam. Comments are
    // stripped first so the explanatory comment cannot satisfy the guard.
    const code = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    const call = code.slice(code.indexOf("startClockState({"));
    const args = call.slice(0, call.indexOf("});"));
    expect(args).toMatch(/startIsTbd:\s*event\?\.start_is_tbd === true \|\|/);
    expect(args).toContain("eventTournament?.start_is_tbd");
  });
});
