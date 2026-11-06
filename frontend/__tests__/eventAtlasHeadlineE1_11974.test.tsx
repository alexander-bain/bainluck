/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";

import SettledOutcomeHero from "@/components/event/SettledOutcomeHero";
import {
  EVENT_HEADLINE_PHASE_LABELS,
  resolveEventHeadlineBaseline,
  resolveEventHeadlinePhase,
} from "@/lib/event/eventHeadlinePhase";
import type { Event } from "@/lib/types";
import FIXTURE from "./fixtures/finalForecast11296.json";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const F = FIXTURE as unknown as Record<string, unknown>;

let eventPayload: unknown;
let historyPayload: unknown;
let searchParamsValue = new URLSearchParams();

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    const data =
      k === "event" ? eventPayload : k === "history" ? historyPayload : undefined;
    return { data, error: undefined, isLoading: false, mutate: () => undefined };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  heldFrameAfter: () => null,
  useLiveEventStream: () => ({
    frame: null,
    connected: false,
    status: "idle",
    confirmedAt: null,
    activityAt: null,
    updates: [],
  }),
}));

jest.mock("next/dynamic", () => ({
  __esModule: true,
  default: () => () => null,
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/14966179",
  useSearchParams: () => searchParamsValue,
  useParams: () => ({ id: "14966179" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function buildDetailEvent(patch: Partial<Event> = {}): Event {
  return ({ ...(F.detail_14966179 as Event), ...patch }) as Event;
}

function mountElement(element: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  return {
    container,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

function mountEventPage(ev: Event, query = "atlas=1") {
  searchParamsValue = new URLSearchParams(query);
  eventPayload = ev;
  historyPayload = {
    aggregate_line: [],
    pm_spread_data: { projected_final: null },
  };
  return mountElement(
    <AnalyticsProvider>
      <EventDetailPage params={{ id: String(ev.id) }} />
    </AnalyticsProvider>,
  );
}

describe("#11974 Step E1 — resolveEventHeadlinePhase", () => {
  const nowMs = Date.parse("2026-11-05T20:00:00Z");

  it("returns 'current' for a live game with a fresh quote (<= 30m)", () => {
    const phase = resolveEventHeadlinePhase({
      status: "live",
      commenceTime: "2026-11-05T19:00:00Z",
      observedAt: "2026-11-05T19:58:00Z",
      nowMs,
    });
    expect(phase).toBe("current");
    expect(EVENT_HEADLINE_PHASE_LABELS[phase!]).toBe("Current win chance");
  });

  it("returns 'current' before scheduled start when quote is fresh", () => {
    const phase = resolveEventHeadlinePhase({
      status: "scheduled",
      commenceTime: "2026-11-05T22:00:00Z",
      observedAt: "2026-11-05T19:55:00Z",
      nowMs,
    });
    expect(phase).toBe("current");
  });

  it("returns 'last_recorded' when the quote is older than 30 minutes", () => {
    const phase = resolveEventHeadlinePhase({
      status: "live",
      commenceTime: "2026-11-05T19:00:00Z",
      observedAt: "2026-11-05T19:29:59Z",
      nowMs,
    });
    expect(phase).toBe("last_recorded");
    expect(EVENT_HEADLINE_PHASE_LABELS[phase!]).toBe("Last recorded win chance");
  });

  it("returns 'last_recorded' when delivery is interrupted or timestamp is missing", () => {
    expect(
      resolveEventHeadlinePhase({
        status: "live",
        commenceTime: "2026-11-05T19:00:00Z",
        observedAt: "2026-11-05T19:59:00Z",
        deliveryInterrupted: true,
        nowMs,
      }),
    ).toBe("last_recorded");

    expect(
      resolveEventHeadlinePhase({
        status: "live",
        commenceTime: "2026-11-05T19:00:00Z",
        observedAt: null,
        nowMs,
      }),
    ).toBe("last_recorded");
  });

  it("returns 'last_recorded' when past scheduled start and status is not 'live'", () => {
    expect(
      resolveEventHeadlinePhase({
        status: "scheduled",
        commenceTime: "2026-11-05T19:00:00Z",
        observedAt: "2026-11-05T19:59:00Z",
        nowMs,
      }),
    ).toBe("last_recorded");
  });

  it("returns null on finished games, opening-line fallbacks, or missing readings", () => {
    expect(
      resolveEventHeadlinePhase({
        status: "completed",
        commenceTime: "2026-11-05T17:00:00Z",
        observedAt: "2026-11-05T19:59:00Z",
        nowMs,
      }),
    ).toBeNull();
    expect(
      resolveEventHeadlinePhase({
        status: "live",
        isOpeningLine: true,
        observedAt: "2026-11-05T19:59:00Z",
        nowMs,
      }),
    ).toBeNull();
    expect(
      resolveEventHeadlinePhase({
        status: "live",
        hasReading: false,
        observedAt: "2026-11-05T19:59:00Z",
        nowMs,
      }),
    ).toBeNull();
  });
});

describe("#11974 Step E1 — resolveEventHeadlineBaseline", () => {
  it("prefers prematch_odds ladder and formats home–away pregame baseline", () => {
    const baseline = resolveEventHeadlineBaseline({
      prematchOdds: {
        home_probability: 0.58,
        away_probability: 0.42,
        home_rendered_percent: 58,
        away_rendered_percent: 42,
        source: "kalshi",
      },
      openingHomeProb: 0.52,
      openingAwayProb: 0.48,
      openingHomePct: 52,
      openingAwayPct: 48,
      sport: "americanfootball_nfl",
      homeShort: "Buccaneers",
    });
    expect(baseline).toEqual({
      text: "Pregame 58% – 42%",
      homeProbability: 0.58,
      awayProbability: 0.42,
      homePercent: 58,
      awayPercent: 42,
      source: "kalshi",
      label: null,
    });
  });

  it("falls back to opening probabilities with the 'sportsbooks' label when prematch_odds is absent", () => {
    const baseline = resolveEventHeadlineBaseline({
      prematchOdds: null,
      openingHomeProb: 0.44,
      openingAwayProb: 0.56,
      openingHomePct: 44,
      openingAwayPct: 56,
      sport: "americanfootball_nfl",
      homeShort: "Buccaneers",
    });
    expect(baseline?.text).toBe("Pregame 44% – 56%");
    expect(baseline?.label).toBe("sportsbooks");
  });

  it("withholds complement away leg on draw-priced sports while keeping real two-leg opening pairs", () => {
    const complement = resolveEventHeadlineBaseline({
      prematchOdds: {
        home_probability: 0.64,
        away_probability: 0.36,
        home_rendered_percent: 64,
        away_rendered_percent: 36,
        source: "kalshi",
      },
      sport: "soccer_epl",
      homeShort: "Arsenal",
    });
    expect(complement?.text).toBe("Pregame Arsenal 64%");
    expect(complement?.awayProbability).toBeNull();

    const realTwoLeg = resolveEventHeadlineBaseline({
      prematchOdds: null,
      openingHomeProb: 0.55,
      openingAwayProb: 0.21,
      openingHomePct: 55,
      openingAwayPct: 21,
      sport: "soccer_epl",
      homeShort: "Arsenal",
    });
    expect(realTwoLeg?.text).toBe("Pregame 55% – 21%");
    expect(realTwoLeg?.awayProbability).toBe(0.21);
  });
});

describe("#11974 Step E1 — SettledOutcomeHero atlasMode", () => {
  const outcome = {
    winnerSide: "away" as const,
    winnerName: "Pittsburgh Steelers",
    resultLine: null,
    resultKind: null,
    resultExplanation: null,
    authority: "score" as const,
  };

  it("renders '✓ Won' and the hollow pregame mark when atlasMode is true", () => {
    const { container, unmount } = mountElement(
      <SettledOutcomeHero
        outcome={outcome}
        hasNumericScore={true}
        winnerPregameProb={0.56}
        winnerPregamePercent={56}
        loserPregameProb={0.44}
        loserPregamePercent={44}
        atlasMode={true}
      />,
    );
    expect(
      container.querySelector('[data-testid="event-hero-settled-verdict"]')
        ?.textContent,
    ).toBe("✓ Won");
    expect(
      container.querySelector('[data-testid="event-hero-pregame-mark"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-testid="event-hero-pregame"]')
        ?.textContent,
    ).toBe("56% pregame");
    unmount();
  });

  it("keeps 'Won' without the hollow mark when atlasMode is false", () => {
    const { container, unmount } = mountElement(
      <SettledOutcomeHero
        outcome={outcome}
        hasNumericScore={true}
        winnerPregameProb={0.56}
        winnerPregamePercent={56}
        loserPregameProb={0.44}
        loserPregamePercent={44}
      />,
    );
    expect(
      container.querySelector('[data-testid="event-hero-settled-verdict"]')
        ?.textContent,
    ).toBe("Won");
    expect(
      container.querySelector('[data-testid="event-hero-pregame-mark"]'),
    ).toBeNull();
    unmount();
  });
});

describe("#11974 Step E1 — EventPage headline wiring behind ?atlas=1", () => {
  it("during play: renders 'Current win chance' with pregame chance beside it and opens AtlasDetailsSheet from routine info", () => {
    const freshStamp = new Date(Date.now() - 45_000).toISOString();
    const base = F.detail_14966179 as Event;
    const liveEvent = buildDetailEvent({
      status: "live",
      completed_at: null,
      commence_time: new Date(Date.now() - 3600_000).toISOString(),
      home_score: 17,
      away_score: 14,
      hero_probability: 0.63,
      hero_probability_away: 0.37,
      hero_probability_source: "blend",
      hero_probability_observed_at: freshStamp,
      espn: {
        ...base.espn,
        period: "Q3",
        game_clock: "08:15",
      },
      win_probability_sources: {
        kalshi: {
          value: 0.63,
          display_name: "Kalshi",
          type: "market",
          color: "#22c55e",
          updated_at: freshStamp,
        },
      },
      current_odds: {
        ...base.current_odds,
        home_win_probability: 0.63,
        away_win_probability: 0.37,
        home_rendered_percent: 63,
        away_rendered_percent: 37,
        captured_at: freshStamp,
      },
      prematch_odds: {
        home_probability: 0.44,
        away_probability: 0.56,
        home_rendered_percent: 44,
        away_rendered_percent: 56,
        source: "kalshi",
      },
    } as Partial<Event>);

    const { container, unmount } = mountEventPage(liveEvent, "atlas=1");

    const phaseLabel = container.querySelector(
      '[data-testid="event-atlas-phase-label"]',
    );
    expect(phaseLabel?.textContent).toBe("Current win chance");
    expect(phaseLabel?.getAttribute("data-phase")).toBe("current");

    const pregameBaseline = container.querySelector(
      '[data-testid="event-atlas-pregame-baseline"]',
    );
    expect(pregameBaseline?.textContent).toBe("Pregame 44% – 56%");
    expect(
      container.querySelector('[data-testid="event-atlas-pregame-mark"]'),
    ).not.toBeNull();

    const infoBtn = container.querySelector(
      '[data-testid="event-atlas-headline-info-button"]',
    ) as HTMLButtonElement | null;
    expect(infoBtn).not.toBeNull();
    act(() => {
      infoBtn!.click();
    });

    expect(
      container.querySelector('[data-testid="atlas-details-sheet"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-testid="atlas-details-opening"]')
        ?.textContent,
    ).toContain("44%");
    expect(
      container.querySelector('[data-testid="atlas-details-last-observation"]')
        ?.textContent,
    ).toContain("63%");
    expect(
      container.querySelector(
        '[data-testid="atlas-details-scheduled-resolution"]',
      ),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-testid="atlas-details-attribution"]'),
    ).not.toBeNull();
    unmount();
  });

  it("after final: renders winner with '✓ Won' and pregame chance, and opens AtlasDetailsSheet with settled verdict", () => {
    const finishedEvent = buildDetailEvent({
      status: "completed",
      home_score: 19,
      away_score: 26,
      prematch_odds: {
        home_probability: 0.44,
        away_probability: 0.56,
        home_rendered_percent: 44,
        away_rendered_percent: 56,
        source: "kalshi",
      },
    } as Partial<Event>);

    const { container, unmount } = mountEventPage(finishedEvent, "atlas=1");

    expect(
      container.querySelector('[data-testid="event-hero-settled-verdict"]')
        ?.textContent,
    ).toBe("✓ Won");
    expect(
      container.querySelector('[data-testid="event-hero-pregame-mark"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-testid="event-hero-pregame"]')
        ?.textContent,
    ).toBe("56% pregame");

    const infoBtn = container.querySelector(
      '[data-testid="event-atlas-headline-info-button"]',
    ) as HTMLButtonElement | null;
    act(() => {
      infoBtn!.click();
    });

    expect(
      container.querySelector('[data-testid="atlas-details-sheet"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-testid="atlas-details-result-badge"]')
        ?.textContent,
    ).toBe("✓ Won");
    expect(
      container.querySelector('[data-testid="atlas-details-opening"]')
        ?.textContent,
    ).toContain("56%");
    unmount();
  });

  it("leaves the default page untouched when ?atlas=1 is absent", () => {
    const finishedEvent = buildDetailEvent();
    const { container, unmount } = mountEventPage(finishedEvent, "");

    expect(
      container.querySelector('[data-testid="event-hero-settled-verdict"]')
        ?.textContent,
    ).toBe("Won");
    expect(
      container.querySelector(
        '[data-testid="event-atlas-headline-info-button"]',
      ),
    ).toBeNull();
    expect(
      container.querySelector('[data-testid="event-atlas-phase-label"]'),
    ).toBeNull();
    unmount();
  });
});
