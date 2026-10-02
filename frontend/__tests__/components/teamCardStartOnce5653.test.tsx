/**
 * #5653 — A TEAM PAGE'S UPCOMING CARD SAYS WHEN, ONCE, AND SAYS WHICH DAY.
 *
 * Two defects in the same start line of `UpcomingGameCard`, both seen at 390px on
 * production:
 *
 * 1. An UNPRICED card printed its start twice — header `Starts Tue, Sep 15, 5:05 PM`,
 *    body `Tue, Sep 15, 5:05 PM` (`/sport/baseball/mlb/team/boston-red-sox`, 9/12), and
 *    `Oct 7 · TBD` twice on the Yankees page (10/1). The body is the slot a priced card
 *    fills with its win prob; with no price it fell back to the header's own string.
 * 2. The local clock dropped the date for anything inside 24 HOURS rather than "today":
 *    at 10:48 PM PDT the Red Sox page read `Starts 10:40 AM` for tomorrow morning's game,
 *    a clock already past today. A start already behind us read `Starts Recently`.
 *
 * The header now prints the Discover card's wording (`formatScheduledGameLabel`) once,
 * and an unpriced card ends after the header.
 *
 * The suite runs in UTC (jest.config.js pins it), so the clock is frozen at a UTC
 * instant and the specimen's shape — a start the next calendar day, under 24 hours
 * out — is rebuilt in that zone: 22:48 → 17:40 the next day, 18h52m away.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { UpcomingGameCard } from "@/components/TeamGameCards";
import type { TeamGameBrief } from "@/lib/api";

const NOW = new Date("2026-09-20T22:48:00Z");

function brief(overrides: Partial<TeamGameBrief> = {}): TeamGameBrief {
  return {
    id: 15315853,
    home_team: "Tampa Bay Rays",
    away_team: "Boston Red Sox",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: "2026-09-21T17:40:00Z",
    sport_key: "baseball_mlb",
    is_home: false,
    opponent: "Tampa Bay Rays",
    win_probability: 0.43,
    ...overrides,
  };
}

function render(game: TeamGameBrief): string {
  return renderToStaticMarkup(
    <UpcomingGameCard game={game} teamName="Boston Red Sox" teamColor={null} />,
  );
}

const count = (html: string, needle: string) => html.split(needle).length - 1;

beforeEach(() => {
  jest.useFakeTimers({ doNotFake: ["nextTick"] }).setSystemTime(NOW);
});
afterEach(() => {
  jest.useRealTimers();
});

describe("#5653 — the nearest fixture says which day it is", () => {
  it("a start tomorrow, under 24 hours out, reads 'Tomorrow', not a bare clock", () => {
    const html = render(brief());
    expect(html).toContain("Starts Tomorrow 5:40 PM");
    expect(html).not.toMatch(/Starts 5:40/);
  });

  it("control: a start later today reads 'Today'", () => {
    const html = render(brief({ commence_time: "2026-09-20T23:40:00Z" }));
    expect(html).toContain("Starts Today 11:40 PM");
  });

  it("a scheduled start already behind us prints no start line at all — never 'Recently'", () => {
    const html = render(brief({ commence_time: "2026-09-20T22:00:00Z", win_probability: 0.5 }));
    expect(html).not.toContain("Recently");
    expect(html).not.toContain("Starts");
    // The card itself still renders its price.
    expect(html).toContain("50%");
  });
});

describe("#5653 — an unpriced card states its start once", () => {
  const IN_3_DAYS = "2026-09-23T23:05:00Z";

  it("announced start: one start line, no body copy of it", () => {
    const html = render(brief({ commence_time: IN_3_DAYS, win_probability: null }));
    expect(count(html, "Starts Wed 11:05 PM")).toBe(1);
    expect(count(html, "11:05 PM")).toBe(1);
  });

  it("placeholder start: 'Sep 23 · TBD' once", () => {
    const html = render(
      brief({ commence_time: IN_3_DAYS, win_probability: null, start_is_tbd: true }),
    );
    expect(count(html, "Sep 23 · TBD")).toBe(1);
  });

  it("no start at all: 'TBD' once", () => {
    const html = render(brief({ commence_time: null, win_probability: null }));
    expect(count(html, "TBD")).toBe(1);
  });

  it("control: a priced card keeps the start in the header and the price in the body", () => {
    const html = render(brief({ commence_time: IN_3_DAYS }));
    expect(count(html, "Starts Wed 11:05 PM")).toBe(1);
    expect(html).toContain("43%");
    expect(html).toContain("win prob");
  });
});
