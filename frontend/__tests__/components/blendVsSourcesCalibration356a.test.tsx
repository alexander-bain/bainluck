import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import BlendVsSourcesCalibration, {
  pickDefaultCommonSetIndex,
} from "@/components/BlendVsSourcesCalibration";
import type {
  BlendVsSourceMetrics,
  BlendVsSourcesCalibrationData,
} from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as unknown as { __bvsPayload: unknown }).__bvsPayload,
  }),
}));

const BANNED_NOTICE_33 = /\b(books?|bookmakers?|per-bookmaker)\b/i;

function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function makeMetrics(nGames: number, ece: number, brier: number): BlendVsSourceMetrics {
  return {
    n_games: nGames,
    ece,
    gap: -0.4,
    brier,
    log_loss: 0.451,
    buckets: [
      {
        bucket_idx: 2,
        bucket: "20-30%",
        midpoint: 25,
        n: 18,
        winners: 4,
        avg_prob: 0.24,
        actual: 0.2222,
        error: -1.78,
        ci_lower: 9.0,
        ci_upper: 45.2,
      },
      {
        bucket_idx: 6,
        bucket: "60-70%",
        midpoint: 65,
        n: nGames - 18,
        winners: Math.round((nGames - 18) * 0.65),
        avg_prob: 0.651,
        actual: 0.6471,
        error: -0.39,
        ci_lower: 55.0,
        ci_upper: 73.5,
      },
    ],
  };
}

const SAMPLE_PAYLOAD: BlendVsSourcesCalibrationData = {
  schema: "blend-vs-sources/1",
  status: "ready",
  smoothing: "none",
  generated_at: "2026-11-23T12:00:00+00:00",
  recording_start: "2026-11-06T05:52:44+00:00",
  events_scanned: 340,
  horizons: {
    start: {
      n_events: 340,
      per_source_matched: [
        {
          source: "betting",
          n_games: 340,
          distinct_events: 340,
          blend: makeMetrics(340, 1.4, 0.1712),
          source_metrics: makeMetrics(340, 1.8, 0.1745),
          delta_ece_pp: -0.4,
          delta_brier: -0.0033,
          delta_log_loss: -0.006,
        },
        {
          source: "kalshi",
          n_games: 120,
          distinct_events: 120,
          blend: makeMetrics(120, 1.9, 0.173),
          source_metrics: makeMetrics(120, 2.7, 0.181),
          delta_ece_pp: -0.8,
          delta_brier: -0.008,
          delta_log_loss: -0.012,
        },
      ],
      common_source_sets: [
        {
          sources: ["betting", "espn"],
          n_games: 280,
          distinct_events: 280,
          blend: makeMetrics(280, 1.5, 0.1715),
          by_source: {
            betting: makeMetrics(280, 1.9, 0.175),
            espn: makeMetrics(280, 3.1, 0.191),
          },
        },
        {
          sources: ["betting", "espn", "kalshi"],
          n_games: 120,
          distinct_events: 120,
          blend: makeMetrics(120, 1.9, 0.173),
          by_source: {
            betting: makeMetrics(120, 2.1, 0.176),
            espn: makeMetrics(120, 3.4, 0.194),
            kalshi: makeMetrics(120, 2.7, 0.181),
          },
        },
      ],
    },
    t_minus_1h: {
      n_events: 310,
      per_source_matched: [],
      common_source_sets: [],
    },
  },
};

describe("#356a BlendVsSourcesCalibration", () => {
  afterEach(() => {
    (global as unknown as { __bvsPayload: unknown }).__bvsPayload = undefined;
  });

  test("returns null when SWR holds legacy CalibrationData or computing state", () => {
    (global as unknown as { __bvsPayload: unknown }).__bvsPayload = {
      total_outcomes: 50000,
      buckets: [],
    };
    expect(renderToStaticMarkup(<BlendVsSourcesCalibration />)).toBe("");

    (global as unknown as { __bvsPayload: unknown }).__bvsPayload = {
      schema: "blend-vs-sources/1",
      status: "computing",
      smoothing: "none",
      horizons: {},
    };
    expect(renderToStaticMarkup(<BlendVsSourcesCalibration />)).toBe("");
  });

  test("picks highest-cardinality material common set as default", () => {
    const sets = SAMPLE_PAYLOAD.horizons.start.common_source_sets;
    expect(pickDefaultCommonSetIndex(sets)).toBe(1);
  });

  test("renders unsmoothed blend + source curves with counts, 375px table sizing, and Notice 33/34 compliance", () => {
    (global as unknown as { __bvsPayload: unknown }).__bvsPayload = SAMPLE_PAYLOAD;
    const html = renderToStaticMarkup(<BlendVsSourcesCalibration />);

    expect(html).toContain('data-testid="calibration-blend-vs-sources-section"');
    expect(html).toContain('data-smoothing="none"');
    // Plotted legend carries exact game count on the common set (120 games).
    expect(html).toContain("Bain Luck (120)");
    expect(html).toContain("Sportsbooks (120)");
    expect(html).toContain("ESPN (120)");
    expect(html).toContain("Kalshi (120)");
    // Raw un-smoothed bucket counts appear in the SVG labels/titles.
    expect(html).toContain("n=18");
    expect(html).toContain("n=102");
    expect(html).toContain("no smoothing");

    // Notice 34 disclosure starts closed.
    expect(html).toContain('data-testid="calibration-card-note"');
    expect(html).not.toMatch(/<details[^>]*\sopen(?:\s|>|=)/);

    // #8581 phone-safe table sizing classes.
    expect(html).toContain("text-[13px] sm:text-sm");
    expect(html).toContain("normal-case sm:uppercase");

    // Pairwise matched counts & metrics appear cleanly.
    expect(html).toContain("340");
    expect(html).toContain("1.4pp");
    expect(html).toContain("0.1712");

    // Zero Notice-33 banned words reach visible copy.
    expect(visibleText(html)).not.toMatch(BANNED_NOTICE_33);
  });
});
