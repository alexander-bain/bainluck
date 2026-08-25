/**
 * THE RE-SKIN GUARD — Alex's mock verdict, asserted (UX-P132).
 *
 * The verdict is a set of taste rulings, but three of them have a failure mode
 * a test can hold:
 *
 * 1. **Collapse.** Alex called the uncollapsed contender list "a P1 on the
 *    page, not polish" — the women's draw ran 44 rows and reading it meant
 *    scrolling past everything else. Three rows, then "show all N".
 * 2. **Three lines, never all contenders.** The reference draws exactly three.
 *    A chart that quietly widened to 44 lines would still render, and would be
 *    unreadable.
 * 3. **Adaptation, not imitation.** The reference's rows carry two-sided
 *    green/red price pills. That is a trading format and copying it would
 *    breach the standing no-price-format ruling. Our rows print ONE blended
 *    probability. This is the one item where following the reference too
 *    faithfully is the bug.
 *
 * Both directions are asserted throughout: a collapse guard that only proves
 * "shows three" is satisfied by a component that can never expand.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentProps from "@/components/tournament/TournamentProps";
import {
  CHART_SERIES_COUNT,
  COLLAPSED_ROW_COUNT,
  SERIES_COLORS,
  chartGeometry,
  chartSeries,
  legendName,
  pointsInTimeframe,
  seriesEndpoint,
  seriesPoints,
  timeframeIsDrawable,
} from "@/lib/contenderChart";
import { broadcastFor } from "@/lib/slate";
import { leadingOutcome, propsForDraw, type PropMarket } from "@/lib/tournamentProps";
import type { TournamentBoardData, TournamentRow } from "@/lib/tournament";

function trend(n: number, start = 0.2) {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-08-${String(i + 1).padStart(2, "0")}`,
    probability: start + i * 0.01,
  }));
}

function row(index: number, overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: `player-${index}`,
    display_name: `Player ${index} Surname`,
    seed: null,
    country: null,
    rank: index,
    state: "live",
    probability: 0.6 - index * 0.01,
    probability_is_live: true,
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    price_state: "live",
    source_count: 2,
    sources: [],
    blend_rule: "mean",
    divergent: false,
    trend: trend(10),
    trend_delta: 0.09,
    ...overrides,
  };
}

function board(count: number, overrides: Partial<TournamentBoardData> = {}): TournamentBoardData {
  const rows = Array.from({ length: count }, (_, i) => row(i + 1));
  return {
    draw: "womens-singles",
    label: "Women's Singles",
    rows,
    contenders: count,
    unpriced: 0,
    price_state: "live",
    newest_observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    ...overrides,
  };
}

const render = (node: React.ReactElement) => renderToStaticMarkup(node);
const count = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

// ---------------------------------------------------------------------------
// 1. Collapse — Alex's P1
// ---------------------------------------------------------------------------

describe("collapsed contender list", () => {
  it("shows only three rows out of a long draw", () => {
    const html = render(<TournamentBoard board={board(44)} />);
    expect(count(html, 'data-testid="board-row"')).toBe(COLLAPSED_ROW_COUNT);
  });

  it("offers an expander naming the true total", () => {
    const html = render(<TournamentBoard board={board(44)} />);
    expect(html).toContain("Show all 44");
    expect(html).toContain('data-testid="board-expander"');
    expect(html).toContain('data-expanded="false"');
  });

  it("does not offer an expander when everything already fits", () => {
    const html = render(<TournamentBoard board={board(3)} />);
    expect(count(html, 'data-testid="board-row"')).toBe(3);
    expect(html).not.toContain('data-testid="board-expander"');
  });

  it("the collapse count and the chart line count are the same number", () => {
    // A list of five under a chart of three invites the reader to hunt for two
    // missing lines.
    expect(COLLAPSED_ROW_COUNT).toBe(CHART_SERIES_COUNT);
  });
});

// ---------------------------------------------------------------------------
// 2. The chart — three lines, fixed axis, no smoothing
// ---------------------------------------------------------------------------

describe("contender chart", () => {
  const rows = Array.from({ length: 20 }, (_, i) => row(i + 1));

  it("names exactly three contenders in the legend", () => {
    const html = render(<ContenderChart rows={rows} draw="womens-singles" />);
    expect(count(html, 'data-testid="chart-legend-item"')).toBe(3);
  });

  it("draws exactly three lines however long the field is", () => {
    const html = render(<ContenderChart rows={rows} draw="womens-singles" />);
    expect(count(html, 'data-testid="chart-series"')).toBe(3);
    expect(count(html, "<polyline")).toBe(3);
  });

  it("gives each line an endpoint dot, as the reference does", () => {
    const html = render(<ContenderChart rows={rows} draw="womens-singles" />);
    expect(count(html, 'data-testid="chart-endpoint"')).toBe(3);
  });

  it("legend colours match the line colours", () => {
    const series = chartSeries(rows);
    expect(series.map((s) => s.color)).toEqual([...SERIES_COLORS]);
  });

  it("plots on a FIXED 0-100 axis, never auto-scaled to the data", () => {
    // Two series in a narrow band must NOT fill the height. If they did, a 2pp
    // wiggle would read as a collapse.
    const narrow = [
      row(1, { trend: [
        { date: "2026-08-01", probability: 0.50 },
        { date: "2026-08-02", probability: 0.52 },
      ] }),
    ];
    const series = chartSeries(narrow);
    const geometry = chartGeometry(series, "ALL", 100, 100);
    const points = seriesPoints(series[0], geometry, "ALL");
    const ys = points.split(" ").map((p) => Number(p.split(",")[1]));
    expect(ys).toEqual([50, 48]);
    expect(Math.min(...ys)).toBeGreaterThan(0);
  });

  it("draws straight segments between real observations — no interpolation", () => {
    const gapped = [
      row(1, { trend: [
        { date: "2026-08-01", probability: 0.2 },
        // 08-02 genuinely unobserved
        { date: "2026-08-03", probability: 0.4 },
      ] }),
    ];
    const series = chartSeries(gapped);
    const geometry = chartGeometry(series, "ALL", 100, 100);
    // Two observations, two plotted points. A filled gap would make three.
    expect(seriesPoints(series[0], geometry, "ALL").split(" ")).toHaveLength(2);
  });

  it("shares one x-domain so two lines are comparable in time", () => {
    const a = row(1, { trend: [
      { date: "2026-08-01", probability: 0.3 },
      { date: "2026-08-05", probability: 0.4 },
    ] });
    const b = row(2, { trend: [
      { date: "2026-08-03", probability: 0.2 },
      { date: "2026-08-05", probability: 0.25 },
    ] });
    const geometry = chartGeometry(chartSeries([a, b]), "ALL", 100, 100);
    expect(geometry.dates).toEqual(["2026-08-01", "2026-08-03", "2026-08-05"]);
    // The late starter begins part-way across, not at x=0.
    const late = seriesPoints(chartSeries([a, b])[1], geometry, "ALL");
    expect(late.startsWith("0.0,")).toBe(false);
  });

  it("a single observation is not a line", () => {
    const one = chartSeries([row(1, { trend: [{ date: "2026-08-01", probability: 0.3 }] })]);
    const geometry = chartGeometry(one, "ALL", 100, 100);
    expect(seriesPoints(one[0], geometry, "ALL")).toBe("");
    expect(seriesEndpoint(one[0], geometry, "ALL")).toBeNull();
  });

  it("measures a timeframe back from the LAST OBSERVATION, not from now", () => {
    // The fields are dark 8-32 days (#2199). A 1W window measured from today
    // would be empty for a market with a full month of history ending three
    // weeks ago — the chart would read "no data" when the truth is "no recent
    // data", which the banner already says properly.
    const old = trend(10);
    expect(pointsInTimeframe(old, "1W")).toHaveLength(7);
    expect(pointsInTimeframe(old, "ALL")).toHaveLength(10);
  });

  it("offers an undrawable timeframe as disabled rather than blank", () => {
    const series = chartSeries(rows);
    expect(timeframeIsDrawable(series, "ALL")).toBe(true);
    expect(timeframeIsDrawable(series, "1D")).toBe(false);
    const html = render(<ContenderChart rows={rows} draw="womens-singles" />);
    expect(html).toContain('data-option="1D"');
    expect(html).toContain("disabled");
  });

  it("mutes the whole chart when the prices are not live", () => {
    const dark = rows.map((r) => ({ ...r, probability_is_live: false }));
    const html = render(<ContenderChart rows={dark} draw="womens-singles" />);
    expect(html).toContain('data-live="false"');
    expect(html).toContain('opacity="0.45"');
  });

  it("renders nothing at all rather than an empty frame with no contenders", () => {
    expect(render(<ContenderChart rows={[]} draw="womens-singles" />)).toBe("");
  });

  it("shortens legend names without losing the surname", () => {
    expect(legendName("Aryna Sabalenka")).toBe("A. Sabalenka");
    expect(legendName("Felix Auger-Aliassime")).toBe("F. Auger-Aliassime");
    expect(legendName("Sinner")).toBe("Sinner");
  });
});

// ---------------------------------------------------------------------------
// 3. Adaptation, not imitation — the pills we do NOT copy
// ---------------------------------------------------------------------------

describe("no two-sided price pills", () => {
  it("each row prints exactly ONE probability", () => {
    const html = render(<TournamentBoard board={board(10)} />);
    const rows = html.split('data-testid="board-row"').slice(1);
    expect(rows).toHaveLength(3);
    for (const markup of rows) {
      expect(count(markup, 'data-testid="row-probability"')).toBe(1);
    }
  });

  it("renders no complement of any shown probability", () => {
    // The reference pairs 34.5% with 65.5%. If a complement ever appeared, this
    // is what would catch it.
    const one = board(1);
    one.rows[0].probability = 0.345;
    const html = render(<TournamentBoard board={one} />);
    expect(html).toContain("34.5%");
    expect(html).not.toContain("65.5%");
  });
});

// ---------------------------------------------------------------------------
// Where to watch, and the curated props section
// ---------------------------------------------------------------------------

describe("where to watch", () => {
  const broadcasts = [
    { region: "US", channels: ["ESPN", "ESPN2"], note: null },
    { region: "UK", channels: ["Sky Sports Tennis"], note: null },
  ];

  it("picks the reader's region", () => {
    expect(broadcastFor(broadcasts, "UK")?.channels).toEqual(["Sky Sports Tennis"]);
  });

  it("falls back to the rights holder rather than to nothing", () => {
    expect(broadcastFor(broadcasts, "JP")?.region).toBe("US");
  });

  it("is null when the register carries no mapping", () => {
    expect(broadcastFor(undefined)).toBeNull();
    expect(broadcastFor([])).toBeNull();
  });
});

describe("curated props", () => {
  const market = (overrides: Partial<PropMarket> = {}): PropMarket => ({
    key: "calendar-slam",
    title: "Can Sinner complete the calendar slam?",
    hook: "He has three of the four.",
    draw: null,
    source: "kalshi",
    outcomes: [
      { entity_key: "yes", display_name: "Jannik Sinner", probability: 0.22, probability_is_live: true },
    ],
    price_state: "live",
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    ...overrides,
  });

  it("shows tournament-wide props under both pills", () => {
    expect(propsForDraw([market()], "mens-singles")).toHaveLength(1);
    expect(propsForDraw([market()], "womens-singles")).toHaveLength(1);
  });

  it("hides a prop scoped to the other draw", () => {
    const mens = market({ draw: "mens-singles" });
    expect(propsForDraw([mens], "womens-singles")).toHaveLength(0);
  });

  it("summarises with the leading outcome", () => {
    const two = market({
      outcomes: [
        { entity_key: "a", display_name: "A", probability: 0.2, probability_is_live: true },
        { entity_key: "b", display_name: "B", probability: 0.5, probability_is_live: true },
      ],
    });
    expect(leadingOutcome(two)?.display_name).toBe("B");
  });

  it("has no leading outcome when nothing is priced", () => {
    const dark = market({
      outcomes: [{ entity_key: "a", display_name: "A", probability: null, probability_is_live: false }],
    });
    expect(leadingOutcome(dark)).toBeNull();
  });

  it("renders an honest empty section rather than vanishing", () => {
    const html = render(<TournamentProps markets={[]} draw="mens-singles" />);
    expect(html).toContain('data-testid="tournament-props"');
    expect(html).toContain("Nothing curated yet");
    expect(html).not.toMatch(/\d+%/);
  });

  it("renders a curated prop with its hook", () => {
    const html = render(<TournamentProps markets={[market()]} draw="mens-singles" />);
    expect(html).toContain("Can Sinner complete the calendar slam?");
    expect(html).toContain("He has three of the four.");
    expect(html).toContain("22%");
  });
});
