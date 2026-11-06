import { readFileSync } from "fs";
import { join } from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AtlasChartMarkKey,
  AtlasResultWordMark,
} from "@/components/atlas/AtlasChartMarks";
import { ATLAS_STATE_COPY } from "@/components/atlas/atlasStateCopy";
import EventHeroProbabilityPair, {
  heroPrintedPair,
} from "@/components/EventHeroProbabilityPair";
import EkgHeartbeat from "@/components/event/EkgHeartbeat";
import SettledOutcomeHero from "@/components/event/SettledOutcomeHero";
import {
  displayedPreview,
  displayedProbabilityObservedAt,
  overlayBlendPreview,
  overlayBlendPreviewLine,
  previewAfter,
  type BlendPreviewFrame,
} from "@/lib/blendPreview";
import { headlineDisplayIdentity } from "@/lib/displayIdentity";
import {
  EMPTY_EKG_TRACKER,
  ekgDraws,
  stepEkgTracker,
} from "@/lib/event/ekgHeartbeat";
import {
  EVENT_HEADLINE_PHASE_LABELS,
  resolveAtlasHeadlineObservedAt,
  resolveEventHeadlineBaseline,
  resolveEventHeadlinePhase,
} from "@/lib/event/eventHeadlinePhase";
import { priceAgeClock } from "@/lib/event/liveConnectionStatus";
import { tenthsPair, tenthsText } from "@/lib/tenthsOptIn";

describe("Event-page Atlas Step E5 — live path (EKG, previews, tenths) & 390 px fidelity (#11974)", () => {
  it("renders tenths on the atlas live headline and keeps complement pairs summing to 100.0", () => {
    const pair = tenthsPair(0.9334, 0.0666);
    expect(pair.home).not.toBeNull();
    expect(pair.away).not.toBeNull();
    expect(tenthsText(pair.home!)).toBe("93.3%");
    expect(tenthsText(pair.away!)).toBe("6.7%");

    const html = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.9334}
        awayProb={0.0666}
        homePct={93}
        awayPct={7}
        tenths
        atlasMode
      />,
    );
    expect(html).toContain('data-hero-digits=""');
    expect(html).toContain('data-hero-decimal=""');
    expect(html).toContain(">93<");
    expect(html).toContain(">.3<");
    expect(html).toContain(">6<");
    expect(html).toContain(">.7<");
  });

  it("overlays one-stream blend previews onto the atlas headline and chart line while preserving Current win chance via resolveAtlasHeadlineObservedAt", () => {
    const nowMs = Date.parse("2026-11-06T05:00:00Z");
    const committedAt = "2026-11-06T04:15:00Z"; // 45m old committed write (> 30m stale threshold)
    const confirmedAt = "2026-11-06T04:59:55Z"; // 5s old live stream confirmation
    const previewAt = "2026-11-06T04:59:58Z"; // 2s old one-stream preview

    const event = {
      id: 15342685,
      status: "live",
      sport: "basketball_nba",
      hero_probability_source: "blend",
      hero_probability: 0.912,
      hero_probability_away: 0.088,
      hero_probability_observed_at: committedAt,
      blend_fold_revision: { "15342685": 12 },
    };

    // Without stream confirmation, a 45m-old DB write would age into "last_recorded".
    expect(
      resolveEventHeadlinePhase({
        status: "live",
        commenceTime: "2026-11-06T03:00:00Z",
        isOpeningLine: false,
        hasReading: true,
        observedAt: committedAt,
        deliveryInterrupted: false,
        nowMs,
      }),
    ).toBe("last_recorded");

    // With resolveAtlasHeadlineObservedAt, a steady price confirmed by the live
    // stream 5s ago advances the clock ahead of 45m-old acceptedPriceClock,
    // freshestSourceStamp, and currentOddsCapturedAt so the phase stays "current".
    const atlasObservedAt = resolveAtlasHeadlineObservedAt({
      acceptedPriceClock: committedAt,
      confirmedAtShown: confirmedAt,
      freshestSourceStamp: committedAt,
      currentOddsCapturedAt: committedAt,
    });
    expect(atlasObservedAt).toBe(confirmedAt);
    expect(
      resolveEventHeadlinePhase({
        status: "live",
        commenceTime: "2026-11-06T03:00:00Z",
        isOpeningLine: false,
        hasReading: true,
        observedAt: atlasObservedAt,
        deliveryInterrupted: false,
        nowMs,
      }),
    ).toBe("current");

    // When no price clock is adopted, resolveAtlasHeadlineObservedAt falls back
    // to freshestSourceStamp and then currentOddsCapturedAt.
    expect(
      resolveAtlasHeadlineObservedAt({
        acceptedPriceClock: null,
        confirmedAtShown: confirmedAt,
        freshestSourceStamp: "2026-11-06T04:50:00Z",
        currentOddsCapturedAt: committedAt,
      }),
    ).toBe("2026-11-06T04:50:00Z");

    // Now a one-stream preview frame arrives:
    const frame: BlendPreviewFrame = {
      event_id: 15342685,
      p: 0.934,
      status: "live",
      display_observed_at: previewAt,
      preview: {
        kind: "blend",
        epoch: 4,
        seq: 9,
        base_rev: 12,
        ttl_ms: 15_000,
      },
    };
    const previewState = previewAfter(null, frame, 15342685, nowMs);
    const admitted = displayedPreview(previewState, event, nowMs);
    expect(admitted).toBeCloseTo(0.934, 6);

    const overlaid = overlayBlendPreview(event, previewState, nowMs);
    expect(overlaid.hero_probability).toBeCloseTo(0.934, 6);
    expect(overlaid.hero_probability_away).toBeCloseTo(0.066, 6);

    const acceptedClock = displayedProbabilityObservedAt(
      event,
      previewState,
      nowMs,
      committedAt,
    );
    expect(acceptedClock).toBe(previewAt);

    const identity = headlineDisplayIdentity({
      heroBlend: true,
      previewShown: admitted !== null,
      preview: previewState,
      committedRevision: event.blend_fold_revision,
      observedAt: acceptedClock,
    });
    expect(identity.basis).toBe("preview");

    const printed = heroPrintedPair({
      homeProb: overlaid.hero_probability,
      awayProb: overlaid.hero_probability_away,
      homePct: Math.round(overlaid.hero_probability * 100),
      awayPct: Math.round(overlaid.hero_probability_away * 100),
      tenths: true,
    });
    expect(printed).toEqual({ home: "93.4%", away: "6.6%" });

    const baseLine = [
      { timestamp: "2026-11-06T04:30:00Z", home_probability: 0.88 },
      { timestamp: committedAt, home_probability: 0.912 },
    ];
    const previewLine = overlayBlendPreviewLine(
      event,
      previewState,
      nowMs,
      baseLine,
      null,
    );
    expect(previewLine).toHaveLength(3);
    expect(previewLine?.[2]).toEqual({
      timestamp: previewAt,
      home_probability: 0.934,
    });
  });

  it("beats the EKG on a held live atlas page when confirmations, previews, or venue activity arrive, and hides on final", () => {
    const now0 = Date.parse("2026-11-06T05:00:00Z");
    const t0 = stepEkgTracker(
      EMPTY_EKG_TRACKER,
      {
        eventId: 15342685,
        status: "open",
        confirmedAt: "2026-11-06T04:59:55Z",
        priceObservedAt: "2026-11-06T04:59:50Z",
        activityAt: "2026-11-06T04:59:55Z",
      },
      now0,
    );
    expect(t0.beats).toBe(0);

    // Stream confirms price 6s later -> beats advances to 1
    const now1 = now0 + 6_000;
    const t1 = stepEkgTracker(
      t0,
      {
        eventId: 15342685,
        status: "open",
        confirmedAt: "2026-11-06T05:00:05Z",
        priceObservedAt: "2026-11-06T04:59:50Z",
        activityAt: "2026-11-06T05:00:05Z",
      },
      now1,
    );
    expect(t1.beats).toBe(1);

    // One-stream preview advances priceObservedAt 3s later -> beats advances to 2
    const now2 = now1 + 3_000;
    const t2 = stepEkgTracker(
      t1,
      {
        eventId: 15342685,
        status: "open",
        confirmedAt: "2026-11-06T05:00:05Z",
        priceObservedAt: "2026-11-06T05:00:08Z",
        activityAt: "2026-11-06T05:00:05Z",
      },
      now2,
    );
    expect(t2.beats).toBe(2);

    expect(
      ekgDraws({
        optIn: true,
        quoteEligible: true,
        isLive: true,
        terminalLabel: null,
      }),
    ).toBe(true);

    const ekgHtml = renderToStaticMarkup(
      <EkgHeartbeat tracker={t2} status="open" now={now2} />,
    );
    expect(ekgHtml).toContain('data-testid="ekg-heartbeat"');
    expect(ekgHtml).toContain('data-ekg-mode="beating"');
    expect(ekgHtml).toContain('data-ekg-beats="2"');

    // Once the game finishes, ekgDraws returns false:
    expect(
      ekgDraws({
        optIn: true,
        quoteEligible: true,
        isLive: false,
        terminalLabel: "Finished",
      }),
    ).toBe(false);
  });

  it("maintains full mark-grammar fidelity across a live game and a settled game", () => {
    const baseline = resolveEventHeadlineBaseline({
      prematchOdds: {
        home_probability: 0.6,
        away_probability: 0.4,
        source: "sportsbooks",
      },
      openingHomeProb: 0.6,
      openingAwayProb: 0.4,
      openingHomePct: 60,
      openingAwayPct: 40,
      sport: "basketball_nba",
      homeShort: "Warriors",
    });
    expect(baseline?.text).toBe("Pregame 60% – 40%");
    expect(EVENT_HEADLINE_PHASE_LABELS.current).toBe("Current win chance");

    const liveKeyHtml = renderToStaticMarkup(
      <AtlasChartMarkKey settled={false} showOpening />,
    );
    expect(liveKeyHtml).toContain("Opening");
    expect(liveKeyHtml).toContain("Recorded reading");
    expect(liveKeyHtml).toContain("Change");
    expect(liveKeyHtml).not.toContain(ATLAS_STATE_COPY.wonWithCheck);

    const settledHeroHtml = renderToStaticMarkup(
      <SettledOutcomeHero
        outcome={{
          winnerSide: "home",
          winnerName: "Ravens",
          resultLine: "27 – 20",
          resultExplanation: null,
          resultKind: "score",
          authority: "score",
        }}
        hasNumericScore
        winnerPregameProb={0.78}
        winnerPregamePercent={78}
        winnerPregameSource="kalshi"
        winnerPregameLabel="Kalshi"
        loserPregameProb={0.22}
        loserPregamePercent={22}
        atlasMode
      />,
    );
    expect(settledHeroHtml).toContain(ATLAS_STATE_COPY.wonWithCheck);
    expect(settledHeroHtml).toContain('data-testid="event-hero-pregame-mark"');
    expect(settledHeroHtml).toContain("78% pregame");

    const settledKeyHtml = renderToStaticMarkup(
      <svg>
        <AtlasResultWordMark
          outcomeId={1}
          x={240}
          y={24}
          plotLeft={40}
          plotRight={320}
          result="won"
        />
      </svg>,
    );
    expect(settledKeyHtml).toContain(ATLAS_STATE_COPY.wonWithCheck);
  });

  it("wires resolveAtlasHeadlineObservedAt and data-atlas-mode in app/events/[id]/page.tsx", () => {
    const pageSrc = readFileSync(
      join(__dirname, "..", "app", "events", "[id]", "page.tsx"),
      "utf8",
    );
    expect(pageSrc).toContain(
      "const atlasObservedAt = resolveAtlasHeadlineObservedAt({",
    );
    expect(pageSrc).toContain('data-atlas-mode={atlasOptIn ? "true" : undefined}');
  });
});
