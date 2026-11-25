import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import BlendVsSourcesCalibration, {
  pickDefaultCommonSetIndex,
} from "@/components/BlendVsSourcesCalibration";
import type {
  BlendVsSourceMetrics,
  BlendVsSourcesCalibrationData,
} from "@/lib/api";
import { SOURCE_COLORS } from "@/lib/sourceColors";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as unknown as { __bvsPayload: unknown }).__bvsPayload,
  }),
}));

const BANNED_NOTICE_33 = /\b(books?|bookmakers?|per-bookmaker)\b/i;
const BANNED_JARGON_BLEND = /\bblend(ed|s)?\b/i;
const BANNED_DECADE_PLURAL = /\b\d+0s\b/i;

function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function makeMetrics(
  nGames: number,
  ece: number,
  brier: number,
  eightBands = false,
): BlendVsSourceMetrics {
  const buckets = eightBands
    ? [1, 2, 3, 4, 5, 6, 7, 8].map((idx, pos) => ({
        bucket_idx: idx,
        bucket: `${idx * 10}-${(idx + 1) * 10}%`,
        midpoint: idx * 10 + 5,
        n: 30 + pos * 11,
        winners: Math.round((30 + pos * 11) * ((idx * 10 + 5) / 100)),
        avg_prob: (idx * 10 + 5) / 100,
        actual: (idx * 10 + 5) / 100 + (idx % 2 === 0 ? 0.011 : -0.013),
        error: idx % 2 === 0 ? 1.1 : -1.3,
        ci_lower: null,
        ci_upper: null,
      }))
    : [
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
      ];

  return {
    n_games: nGames,
    ece,
    gap: -0.4,
    brier,
    log_loss: 0.451,
    buckets,
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
          blend: makeMetrics(340, 1.4, 0.1712, true),
          source_metrics: makeMetrics(340, 1.8, 0.1745, true),
          delta_ece_pp: -0.4,
          delta_brier: -0.0033,
          delta_log_loss: -0.006,
        },
        {
          source: "espn",
          n_games: 310,
          distinct_events: 310,
          blend: makeMetrics(310, 1.4, 0.1715),
          source_metrics: makeMetrics(310, 2.9, 0.189),
          delta_ece_pp: -1.5,
          delta_brier: -0.0175,
          delta_log_loss: -0.021,
        },
        {
          source: "kalshi",
          n_games: 120,
          distinct_events: 120,
          blend: makeMetrics(120, 1.5, 0.172),
          source_metrics: makeMetrics(120, 2.1, 0.179),
          delta_ece_pp: -0.6,
          delta_brier: -0.007,
          delta_log_loss: -0.01,
        },
        {
          source: "polymarket",
          n_games: 95,
          distinct_events: 95,
          blend: makeMetrics(95, 1.6, 0.173),
          source_metrics: makeMetrics(95, 2.3, 0.181),
          delta_ece_pp: -0.7,
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
          sources: ["betting", "espn", "kalshi", "polymarket"],
          n_games: 95,
          distinct_events: 95,
          blend: makeMetrics(95, 1.6, 0.173),
          by_source: {
            betting: makeMetrics(95, 2.0, 0.176),
            espn: makeMetrics(95, 3.4, 0.194),
            kalshi: makeMetrics(95, 2.1, 0.179),
            polymarket: makeMetrics(95, 2.3, 0.181),
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

  test("renders 4 small miss panels with direct right-end labels, % bands, plain copy, and Notice 33/34 compliance", () => {
    (global as unknown as { __bvsPayload: unknown }).__bvsPayload = SAMPLE_PAYLOAD;
    const html = renderToStaticMarkup(<BlendVsSourcesCalibration />);
    const text = visibleText(html);

    expect(html).toContain('data-testid="calibration-blend-vs-sources-section"');
    expect(html).toContain('data-smoothing="none"');
    expect(html).toContain('data-testid="blend-vs-sources-panels"');

    // Four small panels — one per source, distinct non-green Bain Luck token (preserves SOURCE_COLORS.blend.hex).
    for (const src of ["betting", "espn", "kalshi", "polymarket"]) {
      expect(html).toContain(`data-testid="blend-vs-sources-panel-${src}"`);
      expect(html).toContain(`data-testid="panel-end-label-bainluck-${src}"`);
      expect(html).toContain(`data-testid="panel-end-label-${src}"`);
    }
    expect(html).toContain("var(--calibration-bainluck)");
    expect(SOURCE_COLORS.blend.hex).toBe("#059669");

    // Pass 2/3 & 11:41 AM rules: direct right-end labels, NO legend row, % bands, plain units.
    expect(html).toContain("Bain Luck 1.4 points");
    expect(html).toContain("Sportsbooks 1.8 points");
    expect(html).toContain("ESPN 2.9 points");
    expect(html).toContain("Kalshi 2.1 points");
    expect(html).toContain("Polymarket 2.3 points");
    expect(html).toContain("the same 340 games");
    expect(html).toContain("the same 95 games");
    expect(html).toContain("10%");
    expect(html).toContain("80%");
    expect(html).toContain("20%–30%");
    expect(html).toContain("bands of 10 points");

    // Plain 4-column table & mobile sizing.
    expect(html).toContain("Same games");
    expect(html).toContain("Bain Luck typical miss");
    expect(html).toContain("Source typical miss");
    expect(html).toContain("text-[13px] sm:text-sm");
    expect(html).toContain("normal-case sm:uppercase");

    // Disclosure starts closed and has simplified label; sample count phrase appears once.
    expect(html).toContain('data-testid="calibration-card-note"');
    expect(html).toContain("How this comparison works");
    expect(html).not.toContain("proper scoring rules &");
    expect(html).not.toMatch(/<details[^>]*\sopen(?:\s|>|=)/);

    // Zero banned jargon, no "pp", no "n=", no "10s..80s".
    expect(text).not.toMatch(/\bpp\b/);
    expect(text).not.toContain("n=");
    expect(text).not.toMatch(BANNED_DECADE_PLURAL);
    expect(text).not.toMatch(BANNED_NOTICE_33);
    expect(text).not.toMatch(BANNED_JARGON_BLEND);
  });
});
