import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard from "../../components/EventCard";
import type { Event } from "../../lib/types";

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

function makeEvent(overrides: Partial<Event> = {}): Event {
  return {
    id: 100,
    external_id: "evt-100",
    sport: "basketball_nba",
    home_team: "Boston Celtics",
    away_team: "New York Knicks",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: "2030-01-01T11:00:00.000Z",
      home_probability: 0.62,
      away_probability: 0.38,
      spread: null,
      over_under: null,
      projected_home_score: 111,
      projected_away_score: 104,
    },
    opening_odds: {
      home_probability: 0.55,
      away_probability: 0.45,
      spread: null,
      over_under: null,
      favorite: "home",
    },
    ...overrides,
  };
}

describe("EventCard", () => {
  it("shows projected score footer for scheduled events", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, { event: makeEvent() })
    );

    expect(html).toContain("Proj");
    expect(html).toContain("111-104");
    expect(html).not.toContain("Final");
  });

  it("shows live badge and opening split for live started events", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "live",
          commence_time: "2020-01-01T12:00:00.000Z",
          pulse: {
            score: 88,
            status: "racing",
            label: "Must-Watch",
            emoji: "🫀",
          },
        }),
      })
    );

    expect(html).toContain("LIVE");
    expect(html).toContain("Opened");
    expect(html).toContain("55/45");
    expect(html).toContain("🫀 88");
  });

  it("treats not-yet-started live events as pregame (no live badge)", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "live",
          commence_time: "2999-01-01T12:00:00.000Z",
        }),
      })
    );

    expect(html).not.toContain("LIVE");
    expect(html).toContain("Proj");
  });

  it("shows final state and uses opening odds as pre-game probabilities", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "completed",
          home_score: 102,
          away_score: 99,
          current_odds: {
            captured_at: "2030-01-01T11:00:00.000Z",
            home_probability: 0.2,
            away_probability: 0.8,
            spread: null,
            over_under: null,
            projected_home_score: 95,
            projected_away_score: 110,
          },
        }),
      })
    );

    // Completed games display the OPENING odds (0.55/0.45 from makeEvent) as
    // separate "55%"/"45%" probability values — not a "Pre-game:" label or a
    // combined "55%/45%" string (both removed in a prior EventCard redesign).
    expect(html).toContain("Final");
    expect(html).toContain("55%");
    expect(html).toContain("45%");
    expect(html).toContain("102");
    expect(html).toContain("99");
  });
});
