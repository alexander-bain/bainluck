import { readFileSync } from "fs";
import { join } from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ATLAS_STATE_COPY } from "@/components/atlas/atlasStateCopy";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import GameLineBrowser from "@/components/event/GameLineBrowser";
import QuestionCatalog from "@/components/event/QuestionCatalog";
import {
  EMPTY_CONNECTION_TRACKER,
  presentConnectionStatus,
} from "@/lib/event/liveConnectionStatus";
import type { GameMarketsResponse } from "@/lib/api";

const EMPTY_GAME_MARKETS = {
  event_id: 15342680,
  home_team: "Golden State Warriors",
  away_team: "Miami Heat",
  home_score: null,
  away_score: null,
  status: "scheduled",
  totals: [],
  spreads: [],
  team_totals: [],
  period_markets: [],
  player_props: [],
  matchups: [],
  other: [],
  pace: null,
} as GameMarketsResponse;

describe("Event-page Atlas Step E4 — shared state language (#11974)", () => {
  it("uses ATLAS_STATE_COPY.loading and ATLAS_STATE_COPY.updateInterrupted in presentConnectionStatus when atlasMode is true", () => {
    const connecting = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "connecting",
        terminalLabel: null,
        priceMayBeOld: false,
        scoreMayBeOld: false,
        atlasMode: true,
      },
      1_000,
    );
    expect(connecting.label).toBe(ATLAS_STATE_COPY.loading);
    expect(connecting.label).toBe("Loading");

    const rollover = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "rollover",
        terminalLabel: null,
        priceMayBeOld: false,
        scoreMayBeOld: false,
        atlasMode: true,
      },
      1_000,
    );
    expect(rollover.label).toBe(ATLAS_STATE_COPY.loading);

    const retrying = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "retrying",
        terminalLabel: null,
        priceMayBeOld: false,
        scoreMayBeOld: false,
        atlasMode: true,
      },
      1_000,
    );
    expect(retrying.label).toBe(ATLAS_STATE_COPY.updateInterrupted);
    expect(retrying.label).toBe("Update interrupted");

    const stalePrice = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "open",
        terminalLabel: null,
        priceMayBeOld: true,
        scoreMayBeOld: false,
        atlasMode: true,
      },
      1_000,
    );
    expect(stalePrice.label).toBe(ATLAS_STATE_COPY.updateInterrupted);

    const staleScore = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "open",
        terminalLabel: null,
        priceMayBeOld: false,
        scoreMayBeOld: true,
        atlasMode: true,
      },
      1_000,
    );
    expect(staleScore.label).toBe(ATLAS_STATE_COPY.updateInterrupted);
  });

  it("preserves legacy connection status labels when atlasMode is false", () => {
    const connecting = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "connecting",
        terminalLabel: null,
        priceMayBeOld: false,
        scoreMayBeOld: false,
        atlasMode: false,
      },
      1_000,
    );
    expect(connecting.label).toBe("Connecting");

    const retrying = presentConnectionStatus(
      EMPTY_CONNECTION_TRACKER,
      {
        status: "retrying",
        terminalLabel: null,
        priceMayBeOld: false,
        scoreMayBeOld: false,
        atlasMode: false,
      },
      1_000,
    );
    expect(retrying.label).toBe("Updates interrupted · reconnecting");
  });

  it("renders Postponed, Void, and No recent probability in EventHeroProbabilityPair under atlasMode", () => {
    const postponedHtml = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.54}
        awayProb={0.46}
        homePct={54}
        awayPct={46}
        stopped
        stoppageLabel="Postponed"
        atlasMode
      />,
    );
    expect(postponedHtml).toContain('data-testid="event-atlas-state-label"');
    expect(postponedHtml).toContain(ATLAS_STATE_COPY.postponed);
    expect(postponedHtml).not.toContain("54");

    const stoppedWithoutLabelHtml = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.54}
        awayProb={0.46}
        homePct={54}
        awayPct={46}
        stopped
        stoppageLabel={null}
        atlasMode
      />,
    );
    expect(stoppedWithoutLabelHtml).not.toContain('data-testid="event-atlas-state-label"');
    expect(stoppedWithoutLabelHtml).not.toContain(ATLAS_STATE_COPY.postponed);
    expect(stoppedWithoutLabelHtml).not.toContain("54");

    const voidHtml = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={null}
        awayProb={null}
        homePct={null}
        awayPct={null}
        voided
        atlasMode
      />,
    );
    expect(voidHtml).toContain('data-testid="event-atlas-state-label"');
    expect(voidHtml).toContain(ATLAS_STATE_COPY.voided);

    const noRecentPregameHtml = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={null}
        awayProb={null}
        homePct={null}
        awayPct={null}
        started={false}
        atlasMode
      />,
    );
    expect(noRecentPregameHtml).toContain("No probability yet");
    expect(noRecentPregameHtml).not.toContain('data-testid="atlas-no-recent-probability"');
    expect(noRecentPregameHtml).not.toContain(ATLAS_STATE_COPY.noRecentPrice);

    const noRecentLiveHtml = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={null}
        awayProb={null}
        homePct={null}
        awayPct={null}
        started
        atlasMode
      />,
    );
    expect(noRecentLiveHtml).toContain('data-testid="atlas-no-recent-probability"');
    expect(noRecentLiveHtml).toContain("No recent probability");
    expect(noRecentLiveHtml).not.toContain(">No price<");

    const settledEmptyHtml = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={null}
        awayProb={null}
        homePct={null}
        awayPct={null}
        started
        venueSettled
        atlasMode
      />,
    );
    expect(settledEmptyHtml).not.toContain(ATLAS_STATE_COPY.noRecentPrice);
  });

  it("renders No recent probability and ✓ Won / ✗ Lost in QuestionCatalog and GameLineBrowser under atlasMode", () => {
    const staleStamp = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const liveData: GameMarketsResponse = {
      ...EMPTY_GAME_MARKETS,
      team_totals: [
        {
          market_type: "team_total",
          market_name: "Team Total Points",
          outcome_name: "Over 112.5",
          threshold: 112.5,
          over_probability: 0.52,
          movement: null,
          source: "DraftKings",
          observed_at: staleStamp,
        },
      ],
    };

    const catalogHtml = renderToStaticMarkup(
      <QuestionCatalog data={liveData} status="live" atlasMode />,
    );
    expect(catalogHtml).toContain('data-testid="atlas-no-recent-probability"');
    expect(catalogHtml).toContain(ATLAS_STATE_COPY.noRecentPrice);

    const browserHtml = renderToStaticMarkup(
      <GameLineBrowser data={liveData} status="live" atlasMode />,
    );
    expect(browserHtml).toContain('data-testid="atlas-no-recent-probability"');
    expect(browserHtml).toContain(ATLAS_STATE_COPY.noRecentPrice);

    // Closed period markets and unpaired Under rows (no Over twin) are null by
    // design, not because of freshness — neither may claim "No recent probability".
    const nonStaleNullData: GameMarketsResponse = {
      ...EMPTY_GAME_MARKETS,
      closed_period_markets: [
        {
          market_type: "period_total",
          market_name: "1st Quarter Total Points",
          outcome_name: "Over 54.5",
          threshold: 54.5,
          probability: null,
          over_probability: 0.52,
          source: "DraftKings",
          period: "1Q",
          window_closed: true,
        },
      ],
      team_totals: [
        {
          market_type: "team_total",
          market_name: "Team Total Points",
          outcome_name: "Under 112.5",
          threshold: 112.5,
          over_probability: 0.52,
          movement: null,
          source: "DraftKings",
          observed_at: staleStamp,
        },
      ],
    };
    const nonStaleCatalogHtml = renderToStaticMarkup(
      <QuestionCatalog data={nonStaleNullData} status="live" atlasMode />,
    );
    expect(nonStaleCatalogHtml).not.toContain('data-testid="atlas-no-recent-probability"');
    expect(nonStaleCatalogHtml).not.toContain(ATLAS_STATE_COPY.noRecentPrice);

    const nonStaleBrowserHtml = renderToStaticMarkup(
      <GameLineBrowser data={nonStaleNullData} status="live" atlasMode />,
    );
    expect(nonStaleBrowserHtml).not.toContain('data-testid="atlas-no-recent-probability"');
    expect(nonStaleBrowserHtml).not.toContain(ATLAS_STATE_COPY.noRecentPrice);

    const settledData: GameMarketsResponse = {
      ...EMPTY_GAME_MARKETS,
      team_totals: [
        {
          market_type: "team_total",
          market_name: "Team Total Points",
          outcome_name: "Over 112.5",
          threshold: 112.5,
          over_probability: 1,
          movement: null,
          source: "DraftKings",
          is_winner: true,
        },
        {
          market_type: "team_total",
          market_name: "Team Total Points",
          outcome_name: "Over 120.5",
          threshold: 120.5,
          over_probability: 0,
          movement: null,
          source: "DraftKings",
          is_winner: false,
        },
      ],
    };
    const settledBrowserHtml = renderToStaticMarkup(
      <GameLineBrowser data={settledData} status="final" atlasMode />,
    );
    expect(settledBrowserHtml).toContain(ATLAS_STATE_COPY.wonWithCheck);
    expect(settledBrowserHtml).toContain("✓ Won");
    expect(settledBrowserHtml).toContain(ATLAS_STATE_COPY.lostWithCross);
    expect(settledBrowserHtml).toContain("✗ Lost");
  });

  it("wires ATLAS_STATE_COPY loading, voided, and atlasMode passthrough in app/events/[id]/page.tsx", () => {
    const pageSrc = readFileSync(
      join(__dirname, "..", "app", "events", "[id]", "page.tsx"),
      "utf8",
    );
    expect(pageSrc).toContain(
      "text={atlasOptIn && !pastSlowLoadMark ? ATLAS_STATE_COPY.loading : loadingView.text}",
    );
    expect(pageSrc).toContain(
      "atlasOptIn && venueVoided\n                  ? ATLAS_STATE_COPY.voided\n                  : venueSettledSentence ??",
    );
    expect(pageSrc).toContain("atlasMode: atlasOptIn,");
    expect(pageSrc).toContain("atlasMode={atlasOptIn}");
    expect(pageSrc).toContain("voided={venueVoided}");
    expect(pageSrc).toContain("stoppageLabel={stoppageLabel}");
    expect(pageSrc).toContain(
      "<GameLineBrowser data={gameMarkets} status={event.status} atlasMode={atlasOptIn} />",
    );
    expect(pageSrc).toContain(
      "<QuestionCatalog data={gameMarkets} status={event.status} atlasMode={atlasOptIn} />",
    );
  });
});
