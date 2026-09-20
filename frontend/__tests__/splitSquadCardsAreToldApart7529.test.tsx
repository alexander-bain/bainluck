// TWO REAL GAMES STOP READING AS ONE GAME SHOWN TWICE — #7529.
//
// Photographed by live/457 on production, `/search?q=maple leafs` at 390px,
// 2026-09-20 15:14Z. The GAMES section opened with:
//
//     NHL                                        Sep 23 4:00 PM
//     Toronto Maple Leafs                          No price yet
//     Ottawa Senators
//
//     NHL                                        Sep 23 4:00 PM
//     Ottawa Senators                              No price yet
//     Toronto Maple Leafs
//
// THE DATA IS CORRECT AND THIS TEST MUST NEVER BE SATISFIED BY REMOVING A ROW.
// ESPN lists both (`401879650` Canadian Tire Centre, `401886441` Scotiabank
// Arena): an NHL preseason split-squad home-and-home. Our `15313768` /
// `15313769` are one each. De-duplicating would delete a real game; the defect
// is that the page renders a true fact as a duplicate.
//
// ── WHAT THE ASSERTIONS ARE ABOUT ──
//
// The claim is a READER's: "I cannot tell these two cards apart." So the two
// halves of this file answer two different questions and neither substitutes
// for the other:
//
//   1. `hostCuesForEvents` — does the trigger fire on exactly the ambiguous
//      rows and refuse everything else. Four refusals are pinned, because a
//      cue on every card is the change notice 34 / D102 forbids, and a cue on
//      a genuine twin would paper over a matching symptom (#2693).
//
//   2. the CARD, driven on the verbatim production payload — does the fix reach
//      the reader. The BEFORE case is the control and is not decoration: it
//      renders the two rows through the real component with no cue and asserts
//      that the two strings differ ONLY by the swapped name order, which is the
//      photograph. Without it, an AFTER that passed for some unrelated reason
//      would look like a fix.
//
// This file adds no component code and changes no layout (notice 41).

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
import { hostCuesForEvents } from "@/lib/sameFixtureHostCue";
import type { Event } from "@/lib/types";

/**
 * Offset, never a literal (gotcha #44): the real fixture is `2026-09-23T23:00Z`
 * and a fixed stamp walks through the card's Today / Tomorrow / live / FINAL
 * branches as the clock moves. Floored to the minute so both rows key the same
 * way whatever microsecond the suite starts on — the SAME MINUTE is the whole
 * trigger, so it has to be built, not hoped for.
 */
const KICKOFF = new Date(
  Math.floor((Date.now() + 3 * 86_400_000) / 60_000) * 60_000,
).toISOString();
const AN_HOUR_LATER = new Date(new Date(KICKOFF).getTime() + 3_600_000).toISOString();

const TORONTO = {
  team_id: 12715,
  slug: "toronto-nhl",
  primary_color: "#003e7e",
  secondary_color: "#ffffff",
  logo_small: "https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/tor.png",
  abbreviation: "TOR",
};
const OTTAWA = {
  team_id: 13381,
  slug: "ottawa",
  primary_color: "#dd1a32",
  secondary_color: "#b79257",
  logo_small: "https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/ott.png",
  abbreviation: "OTT",
};

/**
 * `GET /api/events/search?q=maple leafs` → `results[0..1]`, copied verbatim
 * from production 2026-09-20 15:52Z apart from the clock-safe commence stamp.
 */
function row(
  id: number,
  homeName: string,
  awayName: string,
  homeData: typeof TORONTO | typeof OTTAWA,
  awayData: typeof TORONTO | typeof OTTAWA,
  commence_time: string = KICKOFF,
): Event {
  return {
    id,
    external_id: null,
    sport: "icehockey_nhl",
    sport_name: "NHL",
    home_team: homeName,
    away_team: awayName,
    commence_time,
    completed_at: null,
    status: "scheduled",
    started_without_result: false,
    home_score: null,
    away_score: null,
    home_team_data: homeData,
    away_team_data: awayData,
  } as unknown as Event;
}

/** id 15313769 — the leg played at Scotiabank Arena. */
const AT_TORONTO = row(15313769, "Toronto Maple Leafs", "Ottawa Senators", TORONTO, OTTAWA);
/** id 15313768 — the leg played at Canadian Tire Centre, same minute. */
const AT_OTTAWA = row(15313768, "Ottawa Senators", "Toronto Maple Leafs", OTTAWA, TORONTO);

/** Rendered text with entities decoded. `&amp;` LAST — unescaping it first
 *  turns `&amp;#x27;` into an apostrophe, one escape too many. */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** The list renders it the way every call site does: measure, then hand down. */
function renderList(events: Event[], withCues: boolean): string[] {
  const cues = withCues ? hostCuesForEvents(events) : new Map();
  return events.map((event) =>
    text(
      renderToStaticMarkup(
        <EventCard event={event} hostCue={cues.get(event.id) ?? null} />,
      ),
    ),
  );
}

describe("hostCuesForEvents — the trigger", () => {
  it("fires on the split-squad pair and names a different host on each", () => {
    const cues = hostCuesForEvents([AT_TORONTO, AT_OTTAWA]);

    expect(cues.get(15313769)).toEqual({ label: "TOR", name: "Toronto Maple Leafs" });
    expect(cues.get(15313768)).toEqual({ label: "OTT", name: "Ottawa Senators" });
    // The point of the cue is that the two cards do not print the same thing.
    expect(cues.get(15313769)!.label).not.toEqual(cues.get(15313768)!.label);
  });

  it("REFUSES the same pair at different times — the clock already tells them apart", () => {
    // The everyday two-meetings-in-a-week case. #6361 gave those cards a date;
    // a host cue on top of a date they already differ by is the grey type
    // notice 34 / D102 refuses.
    const later = row(
      15313768,
      "Ottawa Senators",
      "Toronto Maple Leafs",
      OTTAWA,
      TORONTO,
      AN_HOUR_LATER,
    );
    expect(hostCuesForEvents([AT_TORONTO, later]).size).toBe(0);
  });

  it("REFUSES a slate of different fixtures at one minute", () => {
    // Eight games at 7pm is a normal Tuesday, not an ambiguity.
    const islanders = row(
      15312630,
      "Toronto Maple Leafs",
      "New York Islanders",
      TORONTO,
      OTTAWA,
    );
    expect(hostCuesForEvents([AT_TORONTO, islanders]).size).toBe(0);
  });

  it("REFUSES two rows that share a HOST — a cue there would say nothing, and hide a twin", () => {
    // Two rows, same clubs, same minute, SAME home side is the two-rows-for-one-
    // game symptom (#2693) that belongs to matching. Printing "at TOR" on both
    // would leave the reader exactly as stuck and make the defect look handled.
    const duplicate = row(99, "Toronto Maple Leafs", "Ottawa Senators", TORONTO, OTTAWA);
    expect(hostCuesForEvents([AT_TORONTO, duplicate]).size).toBe(0);
  });

  it("never keys a row with no usable start time", () => {
    // `leagueGameToEvent` passes "" for a game we hold no time for, and the card
    // prints no time for it (UX-P074). Keying on `NaN` would collide every one
    // of those with every other one.
    const noTime = [
      row(1, "Toronto Maple Leafs", "Ottawa Senators", TORONTO, OTTAWA, ""),
      row(2, "Ottawa Senators", "Toronto Maple Leafs", OTTAWA, TORONTO, ""),
      row(3, "Ottawa Senators", "Toronto Maple Leafs", OTTAWA, TORONTO, "not a date"),
    ];
    expect(hostCuesForEvents(noTime).size).toBe(0);
  });

  it("falls back to the host's full name when no abbreviation is served", () => {
    // `/api/leagues/{key}` serves no team data at all, so the cue still has to
    // resolve to something a reader can read.
    const bare = (id: number, home: string, away: string) =>
      ({
        id,
        home_team: home,
        away_team: away,
        commence_time: KICKOFF,
      }) as unknown as Event;

    const cues = hostCuesForEvents([
      bare(1, "Toronto Maple Leafs", "Ottawa Senators"),
      bare(2, "Ottawa Senators", "Toronto Maple Leafs"),
    ]);
    expect(cues.get(1)).toEqual({
      label: "Toronto Maple Leafs",
      name: "Toronto Maple Leafs",
    });
    expect(cues.get(2)!.label).toBe("Ottawa Senators");
  });
});

describe("the search card, driven on the verbatim production payload", () => {
  it("BEFORE — the two cards differ only by the order of the two names", () => {
    // THE CONTROL, and it is the photograph. Strip the two club names out of
    // each rendering and what is left is byte-identical: same league, same
    // stamp, same "No price yet". That equality IS the reader's complaint.
    const [toronto, ottawa] = renderList([AT_TORONTO, AT_OTTAWA], false);

    const withoutNames = (s: string) =>
      s.replace(/Toronto Maple Leafs|Ottawa Senators|Maple Leafs|Senators/g, "TEAM");

    expect(toronto).not.toEqual(ottawa);
    expect(withoutNames(toronto)).toEqual(withoutNames(ottawa));
  });

  it("AFTER — each card prints the host that separates it from its sibling", () => {
    const [toronto, ottawa] = renderList([AT_TORONTO, AT_OTTAWA], true);

    expect(toronto).toContain("at TOR");
    expect(ottawa).toContain("at OTT");
    // Neither card wears the other's host: the cue has to be a discriminator,
    // not a decoration that happens to appear on both.
    expect(toronto).not.toContain("at OTT");
    expect(ottawa).not.toContain("at TOR");

    // And the control's equality is now broken where a reader can see it.
    const withoutNames = (s: string) =>
      s.replace(/Toronto Maple Leafs|Ottawa Senators|Maple Leafs|Senators/g, "TEAM");
    expect(withoutNames(toronto)).not.toEqual(withoutNames(ottawa));
  });

  it("an ordinary card carries no cue at all", () => {
    // The blast-radius assertion. Every unambiguous card in the product — which
    // is all but a handful — renders exactly as it did before this ship.
    const islanders = row(
      15312630,
      "Toronto Maple Leafs",
      "New York Islanders",
      TORONTO,
      OTTAWA,
    );
    const [before] = renderList([islanders], false);
    const [after] = renderList([islanders], true);

    expect(after).toEqual(before);
    expect(after).not.toContain(" at ");
  });
});
