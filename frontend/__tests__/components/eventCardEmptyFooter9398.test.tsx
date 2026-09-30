/**
 * #9398 — an upcoming game card with nothing for its footer draws no footer.
 *
 * Production 2026-09-28, /sports/icehockey_nhl at 390px: Montreal Canadiens @
 * Toronto Maple Leafs (15317562, tomorrow 4:00 PM PT) has no sportsbook
 * projection and no broadcast. `EventCard`'s footer (`!isFinished &&
 * !isSuspended`) still drew its `border-t` rule and padding, so the card ended
 * in a divider over an empty ~40px strip.
 *
 * Fixtures are verbatim `upcoming_games` rows from `GET /api/leagues/icehockey_nhl`
 * (`fixtures/eventCardEmptyFooter9398.json`). The clock is pinned to the
 * capture minute: both games are "tomorrow", and a past kickoff flips the card
 * to its no-result branch, which hides the footer for a different reason.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard from "../../components/EventCard";
import type { Event } from "../../lib/types";
import fixture from "../fixtures/eventCardEmptyFooter9398.json";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("../../hooks", () => ({
  useAnalytics: () => ({
    trackEventCardClick: jest.fn(),
  }),
}));

const FOOTER = "mt-2.5 pt-2 border-t";

function card(key: "leafs_canadiens" | "panthers_hurricanes", patch: Partial<Event> = {}): string {
  const event = { ...(JSON.parse(JSON.stringify(fixture[key])) as Event), ...patch };
  return renderToStaticMarkup(<EventCard event={event} />);
}

beforeAll(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-09-28T16:40:00Z"));
});
afterAll(() => {
  jest.useRealTimers();
});

describe("#9398 — the footer is drawn only when it holds something", () => {
  it("the specimen carries the defect's inputs: no projection, no broadcast", () => {
    const e = fixture.leafs_canadiens as unknown as Event;
    expect(e.status).toBe("scheduled");
    expect(e.current_odds?.projected_home_score ?? null).toBeNull();
    expect(e.espn?.broadcast ?? null).toBeNull();
  });

  it("Leafs–Canadiens renders no footer rule", () => {
    const html = card("leafs_canadiens");
    expect(html).toContain("Toronto");
    expect(html).not.toContain(FOOTER);
  });

  it("CONTROL: Panthers–Hurricanes keeps its footer with the broadcast", () => {
    const html = card("panthers_hurricanes");
    expect(html).toContain(FOOTER);
    expect(html).toMatch(/>ESPN</);
  });

  it("a projection alone keeps the footer and its Proj line", () => {
    const base = fixture.leafs_canadiens as unknown as Event;
    const html = card("leafs_canadiens", {
      current_odds: { ...base.current_odds!, projected_home_score: 3.6, projected_away_score: 2.7 },
    });
    expect(html).toContain(FOOTER);
    expect(html).toMatch(/Proj/);
  });

  it("a finished game still draws no footer", () => {
    const html = card("panthers_hurricanes", { status: "completed", home_score: 3, away_score: 2 });
    expect(html).not.toContain(FOOTER);
  });
});
