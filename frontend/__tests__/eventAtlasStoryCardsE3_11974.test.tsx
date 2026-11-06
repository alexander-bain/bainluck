/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import {
  FinishCardView,
  LadderCardView,
  MilestoneCardView,
  NFLEventCardDeck,
  type CardTeams,
} from "@/components/event/NFLEventCards";
import EventCardReader from "@/components/event/EventCardReader";
import type {
  FinishCard,
  MilestoneCard,
  NflEventCard,
  NflPropRow,
} from "@/lib/nflEventCardDeck";
import type { LadderCard } from "@/lib/nbaEventCards";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

function mount(element: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  return {
    container,
    rerender(next: React.ReactElement) {
      act(() => {
        root.render(next);
      });
    },
    unmount() {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

const TEAMS: CardTeams = {
  awayName: "Bills",
  homeName: "Chiefs",
  awayColor: "#00338D",
  homeColor: "#E31837",
};

const FINISH_CARD_DURING: FinishCard = {
  kind: "finish",
  id: "finish",
  phase: "during",
  pregame: { away: 23.5, home: 26.5, at: 1700000000000 },
  projectedNow: { away: 21, home: 28, at: 1700003600000 },
  final: null,
};

const FINISH_CARD_AFTER: FinishCard = {
  kind: "finish",
  id: "finish",
  phase: "after",
  pregame: { away: 23.5, home: 26.5, at: 1700000000000 },
  projectedNow: null,
  final: { away: 24, home: 27, at: 1700010800000 },
};

const MILESTONE_CARD: MilestoneCard = {
  kind: "milestone",
  id: "milestone:mahomes:passing",
  player: "Patrick Mahomes",
  stat: "Passing yards",
  side: "home",
  basis: "pregameMark",
  actual: 288,
  rungs: [
    { rowId: "r-225", threshold: 225, chance: 0.78, hit: true, observedAt: "2026-11-05T19:00:00Z" },
    { rowId: "r-250", threshold: 250, chance: 0.56, hit: true, observedAt: "2026-11-05T19:00:00Z" },
    { rowId: "r-300", threshold: 300, chance: 0.24, hit: false, observedAt: "2026-11-05T19:00:00Z" },
  ],
};

const MILESTONE_UNPRICED_CARD: MilestoneCard = {
  ...MILESTONE_CARD,
  id: "milestone:allen:passing",
  player: "Josh Allen",
  actual: null,
  rungs: [
    { rowId: "r-unpriced", threshold: 250, chance: null, hit: null, observedAt: null },
  ],
};

const LADDER_CARD_DURING: LadderCard = {
  kind: "ladder",
  id: "total",
  family: "total",
  phase: "during",
  actual: 38,
  forecast: 49.5,
  awayShort: "Bills",
  homeShort: "Chiefs",
  points: [
    {
      optionKey: "tot-45",
      x: 45,
      label: "Over 44.5",
      side: "game",
      chance: 0.72,
      now: 0.84,
      result: null,
      observedAt: "2026-11-05T20:15:00Z",
      detail: {
        detail: "option",
        label: "Over 44.5 total points",
        marketName: "Alternate Totals",
        baseline: 0.72,
        baselineObservedAt: "2026-11-05T19:00:00Z",
        quoted: 0.84,
        observedAt: "2026-11-05T20:15:00Z",
        source: "draftkings",
        result: null,
      },
    },
    {
      optionKey: "tot-50",
      x: 50,
      label: "Over 49.5",
      side: "game",
      chance: 0.51,
      now: 0.62,
      result: null,
      observedAt: "2026-11-05T20:15:00Z",
      detail: {
        detail: "option",
        label: "Over 49.5 total points",
        marketName: "Alternate Totals",
        baseline: 0.51,
        baselineObservedAt: "2026-11-05T19:00:00Z",
        quoted: 0.62,
        observedAt: "2026-11-05T20:15:00Z",
        source: "draftkings",
        result: null,
      },
    },
    {
      optionKey: "tot-55",
      x: 55,
      label: "Over 54.5",
      side: "game",
      chance: 0.28,
      now: 0.35,
      result: null,
      observedAt: "2026-11-05T20:15:00Z",
      detail: {
        detail: "option",
        label: "Over 54.5 total points",
        marketName: "Alternate Totals",
        baseline: 0.28,
        baselineObservedAt: "2026-11-05T19:00:00Z",
        quoted: 0.35,
        observedAt: "2026-11-05T20:15:00Z",
        source: "draftkings",
        result: null,
      },
    },
  ],
};

const PROP_ROWS: Record<string, NflPropRow> = {
  "r-250": {
    outcome_name: "Patrick Mahomes Over 249.5 Passing Yards",
    market_name: "Player Passing Yards",
    threshold: 250,
    pregame_mark: 0.56,
    over_probability: 0.56,
    observed_at: "2026-11-05T19:00:00Z",
    source: "fanduel",
    actual: 288,
    hit: true,
  },
};

describe("#11974 Step E3 — NFL/NBA story cards in the Atlas mark grammar", () => {
  it("keeps default (atlasMode=false) story cards unchanged without Atlas marks or sheet buttons", () => {
    const view = mount(
      <MilestoneCardView
        card={MILESTONE_CARD}
        color={TEAMS.homeColor}
        selected={1}
        onMove={() => {}}
      />,
    );

    expect(view.container.querySelector('[data-testid="atlas-story-card-mark-key"]')).toBeNull();
    expect(view.container.querySelector('[data-testid="atlas-story-card-details-button"]')).toBeNull();
    expect(view.container.textContent).toContain("250+ · 56%");
    expect(view.container.textContent).toContain("HIT");
    expect(view.container.textContent).not.toContain("✓ HIT");
    view.unmount();
  });

  it("draws the Atlas mark grammar on FinishCardView, MilestoneCardView, and LadderCardView when atlasMode is true", () => {
    const view = mount(
      <FinishCardView card={FINISH_CARD_AFTER} teams={TEAMS} atlasMode onDetails={() => {}} />,
    );

    const finishKey = view.container.querySelector('[data-testid="atlas-story-card-mark-key"]');
    expect(finishKey?.textContent).toContain("Pregame");
    expect(finishKey?.textContent).toContain("Final");
    expect(view.container.querySelector('[data-testid="finish-card-winner-badge"]')?.textContent).toBe("✓ Won");
    expect(view.container.querySelectorAll('[data-mark="finish-connector"]').length).toBe(2);

    view.rerender(
      <MilestoneCardView
        card={MILESTONE_CARD}
        color={TEAMS.homeColor}
        selected={1}
        onMove={() => {}}
        onDetails={() => {}}
        atlasMode
      />,
    );
    expect(view.container.querySelector('[data-testid="atlas-story-card-mark-key"]')?.textContent).toContain("✓ HIT");
    expect(view.container.textContent).toContain("✓ HIT · details");

    view.rerender(
      <LadderCardView
        card={LADDER_CARD_DURING}
        teams={TEAMS}
        selected={1}
        onMove={() => {}}
        onDetails={() => {}}
        atlasMode
      />,
    );
    expect(view.container.querySelector('[data-testid="atlas-story-card-mark-key"]')?.textContent).toContain("Recorded");
    expect(view.container.querySelector('[data-testid="atlas-story-card-mark-key"]')?.textContent).toContain("Change");
    expect(view.container.querySelectorAll('[data-mark="ladder-recorded"]').length).toBe(3);
    expect(view.container.querySelectorAll('[data-mark="ladder-connector"]').length).toBe(3);
    expect(view.container.querySelector('[data-mark="forecast-square"]')).not.toBeNull();
    view.unmount();
  });

  it("prints ATLAS_STATE_COPY.noRecentPrice ('No recent probability') when a rung has no price in atlasMode", () => {
    const view = mount(
      <MilestoneCardView
        card={MILESTONE_UNPRICED_CARD}
        color={TEAMS.awayColor}
        selected={0}
        onMove={() => {}}
        atlasMode
      />,
    );

    expect(view.container.textContent).toContain("No recent probability");
    view.unmount();
  });

  it("opens the shared AtlasDetailsSheet from any card in NFLEventCardDeck while preserving card order", () => {
    const cards: NflEventCard[] = [FINISH_CARD_DURING, LADDER_CARD_DURING, MILESTONE_CARD];
    const view = mount(
      <NFLEventCardDeck
        cards={cards}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        onOpen={() => {}}
        openerRef={() => {}}
        atlasMode
        rows={PROP_ROWS}
      />,
    );

    const cardEls = Array.from(view.container.querySelectorAll("[data-card-id]"));
    expect(cardEls.map((el) => el.getAttribute("data-card-id"))).toEqual([
      "finish",
      "total",
      "milestone:mahomes:passing",
    ]);

    const milestoneCardEl = view.container.querySelector('[data-card-id="milestone:mahomes:passing"]') as HTMLElement;
    const detailsBtn = milestoneCardEl.querySelector('[data-testid="atlas-story-card-details-button"]') as HTMLButtonElement;
    act(() => {
      detailsBtn.click();
    });

    const sheet = view.container.querySelector('[data-testid="atlas-details-sheet"]');
    expect(sheet).not.toBeNull();
    expect(sheet?.textContent).toContain("Patrick Mahomes Over 249.5 Passing Yards");
    expect(sheet?.textContent).toContain("Player Passing Yards");
    expect(sheet?.textContent).toContain("56%");
    expect(sheet?.textContent).toContain("✓ Won");
    view.unmount();
  });

  it("opens AtlasDetailsSheet inside EventCardReader when atlasMode is true and keeps held cards steady", () => {
    const cards: NflEventCard[] = [MILESTONE_CARD, LADDER_CARD_DURING];
    const view = mount(
      <EventCardReader
        openCardId="milestone:mahomes:passing"
        liveCards={cards}
        liveHeader={{ match: "Bills 24 · Chiefs 27 · Final", chances: "" }}
        liveRows={PROP_ROWS}
        teams={TEAMS}
        selection={{}}
        onSelect={() => {}}
        onClose={() => {}}
        atlasMode
      />,
    );

    const detailsButtons = view.container.querySelectorAll('[data-testid="atlas-story-card-details-button"]');
    act(() => {
      (detailsButtons[0] as HTMLButtonElement).click();
    });

    const sheet = view.container.querySelector('[data-testid="atlas-details-sheet"]');
    expect(sheet).not.toBeNull();
    expect(sheet?.textContent).toContain("Patrick Mahomes Over 249.5 Passing Yards");
    expect(view.container.querySelector('[data-testid="line-details"]')).toBeNull();
    view.unmount();
  });
});
