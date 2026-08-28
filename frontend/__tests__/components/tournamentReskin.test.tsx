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
import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate } from "@/lib/matchList";
import {
  CHART_SERIES_COUNT,
  COLLAPSED_ROW_COUNT,
  MAX_SERIES_COUNT,
  SERIES_COLORS,
  chartGeometry,
  chartSeries,
  chartSeriesFor,
  defaultSelection,
  legendName,
  pointsInTimeframe,
  seriesColorByEntity,
  seriesEndpoint,
  seriesPoints,
  timeframeIsDrawable,
  toggleSelection,
} from "@/lib/contenderChart";
import { TITLE_COLUMN_LABEL } from "@/lib/bracket";
import { SECTION_HEADING } from "@/components/tournament/TournamentProps";
import {
  broadcastFor,
  matchBroadcast,
  type SlateData,
  type SlateMatch,
} from "@/lib/slate";
import {
  answerOutcome,
  printedOutcomes,
  propGoverningAgeHours,
  propIsQuiet,
  propIsPresentedAsLive,
  propStaleOutcomes,
  propsForDraw,
  rankedOutcomes,
  type PropMarket,
} from "@/lib/tournamentProps";
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
    freshest_observed_at: "2026-08-25T11:00:00+00:00",
    freshest_age_hours: 1,
    stale_sources: [],
    mixed_freshness: false,
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
    rows_not_live: 0,
    mixed_freshness_rows: 0,
    price_state: "live",
    newest_observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    ...overrides,
  };
}

const render = (node: React.ReactElement) => renderToStaticMarkup(node);
const count = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

/**
 * The chart's props at their DEFAULT selection (UX-P137, ruling 6).
 *
 * Selection moved out of the component and up to the page, because the board's
 * colour tie-in has to follow the same choice. Every pre-existing assertion in
 * this file is about the default, so they all render through here and stay
 * assertions about "the top three" rather than about "whatever is selected".
 */
const chartProps = (rows: TournamentRow[], extra: Record<string, unknown> = {}) => ({
  rows,
  draw: "womens-singles",
  selection: defaultSelection(rows),
  onToggle: () => {},
  ...extra,
});

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
    const html = render(<ContenderChart {...chartProps(rows)} />);
    expect(count(html, 'data-testid="chart-legend-item"')).toBe(3);
  });

  it("draws exactly three lines however long the field is", () => {
    const html = render(<ContenderChart {...chartProps(rows)} />);
    expect(count(html, 'data-testid="chart-series"')).toBe(3);
    expect(count(html, "<polyline")).toBe(3);
  });

  it("gives each line an endpoint dot, as the reference does", () => {
    const html = render(<ContenderChart {...chartProps(rows)} />);
    expect(count(html, 'data-testid="chart-endpoint"')).toBe(3);
  });

  it("legend colours match the line colours", () => {
    const series = chartSeries(rows);
    expect(series.map((s) => s.color)).toEqual(
      SERIES_COLORS.slice(0, CHART_SERIES_COUNT)
    );
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
    const html = render(<ContenderChart {...chartProps(rows)} />);
    expect(html).toContain('data-option="1D"');
    expect(html).toContain("disabled");
  });

  it("mutes the whole chart when the prices are not live", () => {
    const dark = rows.map((r) => ({ ...r, probability_is_live: false }));
    const html = render(<ContenderChart {...chartProps(dark)} />);
    expect(html).toContain('data-live="false"');
    expect(html).toContain('opacity="0.45"');
  });

  it("renders nothing at all rather than an empty frame with no contenders", () => {
    expect(render(<ContenderChart {...chartProps([])} />)).toBe("");
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

  // UX-P137, ruling 8: the answer moved to the row.
  it("resolves per match, and SAYS when it is only the region-wide answer", () => {
    // The honest half of this ruling. Today the register holds rights per
    // region only, so every row gets the same string — and it is tagged
    // `tournament` so nobody can mistake a fallback for a per-match fact.
    const resolved = matchBroadcast({ broadcast: null }, broadcasts, "US");
    expect(resolved?.scope).toBe("tournament");
    expect(resolved?.channels).toEqual(["ESPN", "ESPN2"]);
  });

  it("prefers a match's OWN broadcast when the register names one", () => {
    // The seam. Nothing fills it today; a session feed will, as a data change.
    const resolved = matchBroadcast(
      { broadcast: { region: "US", channels: ["ESPN+"], note: null } },
      broadcasts,
      "US"
    );
    expect(resolved?.scope).toBe("match");
    expect(resolved?.channels).toEqual(["ESPN+"]);
  });

  it("never invents a channel", () => {
    expect(matchBroadcast({ broadcast: null }, undefined)).toBeNull();
    expect(matchBroadcast({ broadcast: { region: "US", channels: [], note: null } }, [])).toBeNull();
  });

  // The rendered half. Testing only `matchBroadcast` left the component free
  // to stop printing it entirely — a planted removal of the row markup stayed
  // GREEN against the pure tests above, which is the whole reason this block
  // exists rather than only the ones above it.
  const slateMatch = (n: number, overrides: Partial<SlateMatch> = {}): SlateMatch => ({
    matchup_key: `m-${n}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R128",
    scheduled_date: "2026-08-31T17:00:00Z",
    sides: [
      { entity_key: `a-${n}`, display_name: `A${n}`, seed: null, country: null, role: "contender", probability: 0.6, opening_probability: 0.58, move: 0.02, raw_probability: 0.6, raw_opening_probability: 0.58, age_hours: 0.2, price_state: "live" },
      { entity_key: `b-${n}`, display_name: `B${n}`, seed: null, country: null, role: "contender", probability: 0.4, opening_probability: 0.42, move: -0.02, raw_probability: 0.4, raw_opening_probability: 0.42, age_hours: 0.2, price_state: "live" },
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-08-26T20:00:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: `a-${n}`,
    has_moved: true,
    source_count: 1,
    ...overrides,
  });

  const slateOf = (matches: SlateMatch[]): SlateData => ({
    matches,
    count: matches.length,
    incoherent: 0,
    dropped: {},
    price_state: "live",
    newest_observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 0.2,
    dark_after_hours: 48,
  });

  // ⚠️ UX-P138's RULING 7 OVERRULED UX-P137's RULING 8 ON PLACEMENT, and these
  // assertions were inverted rather than deleted. Alex's clarification: "on
  // the event card's DETAIL view (tap), not on every row". The MATCH-LEVEL
  // resolution he ruled for at UX-P137 is unchanged and still tested — what
  // moved is where the answer is printed, and the strongest guard is now that
  // it is NOT on the closed row.
  const matchesOf = (matches: SlateMatch[], extra: Record<string, unknown> = {}) =>
    render(
      <TournamentMatches
        entries={matchListFromSlate(matches, { broadcasts })}
        {...extra}
      />
    );

  it("prints NO channel on the closed rows — ruling 7 moved it behind the tap", () => {
    const html = matchesOf([slateMatch(1), slateMatch(2), slateMatch(3)]);
    expect(html).not.toContain('data-testid="match-detail-broadcast"');
    expect(html).not.toContain("Sky Sports");
    // And the UX-P137 per-row line is gone with it, as is the single line
    // above the list that UX-P137 replaced.
    expect(html).not.toContain('data-testid="slate-row-broadcast"');
    expect(html).not.toContain('data-testid="slate-broadcast"');
  });

  /* ═══ UX-P154 MOVED THE ANSWER AGAIN, AND THESE TWO INVERTED ═══
   *
   * Ruling 7's "detail view" was an accordion inside the row. Alex's item 2
   * (2026-08-28) deleted the accordion — the whole card is the link — so the
   * detail view is the EVENT PAGE, and the channel renders in
   * `TournamentExtensions` (guarded in `tournamentExtensions.test.tsx`).
   *
   * The `matchBroadcast` resolution above is UNCHANGED and still tested: the
   * per-match preference, the region fallback and the `scope` tag are all the
   * same facts, still resolved on this list's entries, and still carried into
   * the payload. What moved is only where they are printed. So these two
   * assert the negative that a moved feature usually loses — the row does not
   * quietly keep a copy.
   */
  it("prints no channel on the row IN ANY STATE — there are no states left", () => {
    const entries = matchListFromSlate([slateMatch(1)], { broadcasts });
    const html = render(<TournamentMatches entries={entries} />);
    expect(html).not.toContain('data-testid="match-detail-broadcast"');
    expect(html).not.toContain("ESPN");
    // The resolution itself still ran — this is not green because the entry
    // has no broadcast to print.
    expect(entries[0].broadcast?.scope).toBe("tournament");
    expect(entries[0].broadcast?.channels).toEqual(["ESPN", "ESPN2"]);
  });

  it("a match with its own channel is still resolved, and still not on the row", () => {
    const entries = matchListFromSlate(
      [slateMatch(1, { broadcast: { region: "US", channels: ["ESPN+"], note: null } })],
      { broadcasts }
    );
    expect(entries[0].broadcast?.scope).toBe("match");
    expect(entries[0].broadcast?.channels).toEqual(["ESPN+"]);
    const html = render(<TournamentMatches entries={entries} />);
    expect(html).not.toContain("ESPN+");
  });

  it("a long round collapses to five matches with an expander (ruling 5)", () => {
    const many = Array.from({ length: 12 }, (_, i) => slateMatch(i + 1));
    const html = matchesOf(many);
    expect(count(html, 'data-testid="match-row"')).toBe(5);
    expect(html).toContain("Show all 12");
  });
});

// ---------------------------------------------------------------------------
// UX-P137 — every number says what it means, every list says how long it is
// ---------------------------------------------------------------------------

describe("ruling 2 — no unlabelled percentage column", () => {
  it("the board names what its number means", () => {
    const html = render(<TournamentBoard board={board(10)} />);
    expect(html).toContain('data-testid="board-column-label"');
    expect(html).toContain(TITLE_COLUMN_LABEL);
  });

  it("the chart names what its number means", () => {
    const rows = Array.from({ length: 8 }, (_, i) => row(i + 1));
    const html = render(<ContenderChart {...chartProps(rows)} />);
    expect(html).toContain('data-testid="chart-column-label"');
    expect(html).toContain(TITLE_COLUMN_LABEL);
  });

  it("the label is the TITLE question, because that is what the number is", () => {
    // Traced in `lib/bracket.ts`: the figure comes from the register player's
    // `kind: "outright"` sources — the champion market — on all three surfaces.
    // A label saying anything about a match would be a confident lie.
    expect(TITLE_COLUMN_LABEL.toLowerCase()).toContain("title");
    expect(TITLE_COLUMN_LABEL.toLowerCase()).not.toContain("match");
  });
});

describe("ruling 6 — the chart's player picker", () => {
  const rows = Array.from({ length: 20 }, (_, i) => row(i + 1));

  it("defaults to the top three, and the default is the board's order", () => {
    expect(defaultSelection(rows)).toEqual(["player-1", "player-2", "player-3"]);
    expect(defaultSelection(rows)).toHaveLength(CHART_SERIES_COUNT);
  });

  it("adds a fourth line with its OWN colour", () => {
    const added = toggleSelection(defaultSelection(rows), "player-9");
    expect(added).toHaveLength(4);
    const colours = chartSeriesFor(rows, added).map((s) => s.color);
    expect(new Set(colours).size).toBe(4);
    expect(colours[3]).toBe(SERIES_COLORS[3]);
  });

  it("removes exactly the line tapped, and no other", () => {
    const after = chartSeriesFor(rows, toggleSelection(defaultSelection(rows), "player-1"));
    expect(after.map((s) => s.entityKey)).toEqual(["player-2", "player-3"]);
    // Colours stay distinct after a removal. They are NOT pinned per entity —
    // the survivors shift up — and `chartSeriesFor` says why that is the
    // accepted trade. What must never happen is two lines sharing a colour.
    expect(new Set(after.map((s) => s.color)).size).toBe(2);
  });

  it("the legend dot and the line can never disagree about a colour", () => {
    // Both read the same `entry.color`, and this is the assertion that keeps
    // it that way if either half is ever rewritten.
    const html = render(<ContenderChart {...chartProps(rows)} />);
    for (const colour of SERIES_COLORS.slice(0, CHART_SERIES_COUNT)) {
      expect(html).toContain(`background-color:${colour}`);
      expect(html).toContain(`stroke="${colour}"`);
    }
  });

  it("refuses to empty the chart", () => {
    expect(toggleSelection(["player-1"], "player-1")).toEqual(["player-1"]);
  });

  it("refuses to draw more lines than it can render", () => {
    const full = rows.slice(0, MAX_SERIES_COUNT).map((r) => r.entity_key);
    expect(toggleSelection(full, "player-20")).toEqual(full);
    expect(chartSeriesFor(rows, rows.map((r) => r.entity_key))).toHaveLength(
      MAX_SERIES_COUNT
    );
  });

  it("offers the rest of the field, collapsed to five", () => {
    const html = render(<ContenderChart {...chartProps(rows, { initialPickerOpen: true })} />);
    expect(count(html, 'data-testid="chart-picker-option"')).toBe(5);
    expect(html).toContain('data-testid="show-more"');
    // ...and does not offer someone already drawn.
    expect(html).not.toContain('data-testid="chart-picker-option" data-entity="player-1"');
  });

  it("the picker is closed by default — the chart is not a form", () => {
    const html = render(<ContenderChart {...chartProps(rows)} />);
    expect(html).toContain('data-open="false"');
    expect(html).not.toContain('data-testid="chart-picker-list"');
  });

  it("the board's underline follows the chart's selection, not the board's rank", () => {
    const selection = toggleSelection(defaultSelection(rows), "player-9");
    const colours = seriesColorByEntity(chartSeriesFor(rows, selection));
    expect(Object.keys(colours)).toContain("player-9");
    const html = render(<TournamentBoard board={board(20)} seriesColors={colours} />);
    expect(html).toContain('data-testid="board-row-series-tie"');
  });
});

describe("rulings 5 and 9 — every long list collapses", () => {
  it("the props section shows five then expands", () => {
    const many = Array.from({ length: 11 }, (_, i) => ({
      key: `p-${i}`,
      title: `Question ${i}?`,
      hook: null,
      draw: null,
      source: "polymarket",
      outcomes: [
        {
          entity_key: `p-${i}:yes`,
          display_name: "Yes",
          probability: 0.4,
          probability_is_live: true,
          observed_at: "2026-08-25T11:00:00+00:00",
          age_hours: 1,
          price_state: "live" as const,
          is_answer: true,
        },
      ],
      answer_entity_key: `p-${i}:yes`,
      price_state: "live" as const,
      observed_at: "2026-08-25T11:00:00+00:00",
      age_hours: 1,
      freshest_observed_at: "2026-08-25T11:00:00+00:00",
      freshest_age_hours: 1,
      stale_outcomes: [],
      mixed_freshness: false,
    }));
    const html = render(<TournamentProps markets={many} draw="mens-singles" />);
    expect(count(html, 'data-testid="prop-market"')).toBe(5);
    expect(html).toContain("Show all 11");
  });

  it("a SHORT list gets no expander — the control is not decoration", () => {
    // The other direction. A rule that always rendered the button would pass
    // every "shows five" assertion and put "Show all 1" under a single card.
    const html = render(<TournamentProps markets={[]} draw="mens-singles" />);
    expect(html).not.toContain('data-testid="show-more"');
  });

  it("the expander names the FULL length, which is the whole point", () => {
    const html = render(<TournamentBoard board={board(44)} />);
    expect(html).toContain("Show all 44");
  });
});

describe("ruling 7 — the section is not named in gambling vocabulary", () => {
  it("says neither props nor futures where a reader can see it", () => {
    // Visible TEXT only — `data-testid="tournament-props"` is a selector other
    // suites and the capture rigs depend on, and renaming it would be churn
    // dressed as a fix. What Alex read is the heading.
    const visible = render(<TournamentProps markets={[]} draw="mens-singles" />)
      .replace(/<[^>]*>/g, " ")
      .toLowerCase();
    expect(visible).not.toContain("props");
    expect(visible).not.toContain("futures");
    expect(visible).toContain(SECTION_HEADING.toLowerCase());
  });
});

describe("curated props", () => {
  const market = (overrides: Partial<PropMarket> = {}): PropMarket => ({
    key: "calendar-slam",
    title: "Can Sinner win a second major this year?",
    hook: "He already has one in 2026.",
    draw: null,
    source: "kalshi",
    outcomes: [
      { entity_key: "yes", display_name: "Jannik Sinner", probability: 0.22, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: true },
    ],
    answer_entity_key: "yes",
    price_state: "live",
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    freshest_observed_at: "2026-08-25T11:00:00+00:00",
    freshest_age_hours: 1,
    stale_outcomes: [],
    mixed_freshness: false,
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

  it("answers with the CURATED outcome, never the biggest number", () => {
    // The specimen: a Kalshi threshold ladder where the max is the wrong
    // answer. "1+" at 99% under "can he win a SECOND major" is a 99% for
    // something whose real answer is 55.5%.
    const ladder = market({
      title: "Can Sinner win a second major this year?",
      answer_entity_key: "two-plus",
      outcomes: [
        { entity_key: "one-plus", display_name: "1+ Grand Slam wins", probability: 0.99, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: false },
        { entity_key: "two-plus", display_name: "2+ Grand Slam wins", probability: 0.555, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: true },
        { entity_key: "three-plus", display_name: "3+ Grand Slam wins", probability: 0.01, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: false },
      ],
    });
    expect(answerOutcome(ladder)?.display_name).toBe("2+ Grand Slam wins");

    const html = render(<TournamentProps markets={[ladder]} draw="mens-singles" />);
    expect(html).toContain("56%");
    // The headline must NOT be the ladder's max.
    expect(html).not.toContain(">99%<");
  });

  it("has no answer when the register named none", () => {
    const field = market({ answer_entity_key: null });
    expect(answerOutcome(field)).toBeNull();
  });

  it("a field market ranks instead of inventing a headline", () => {
    const field = market({
      title: "Who will win a Grand Slam in 2026?",
      answer_entity_key: null,
      outcomes: [
        { entity_key: "a", display_name: "A", probability: 0.2, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: false },
        { entity_key: "b", display_name: "B", probability: 0.5, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: false },
      ],
    });
    expect(rankedOutcomes(field).map((o) => o.display_name)).toEqual(["B", "A"]);

    const html = render(<TournamentProps markets={[field]} draw="mens-singles" />);
    expect(html).toContain('data-shape="field"');
    expect(html).toContain('data-testid="prop-field"');
    // No headline probability at all — that slot is exactly the guess refused.
    expect(html).not.toContain('data-testid="prop-probability"');
  });

  it("drops unpriced outcomes from a field ranking rather than ordering them", () => {
    const field = market({
      answer_entity_key: null,
      outcomes: [
        { entity_key: "a", display_name: "A", probability: null, probability_is_live: false, observed_at: null, age_hours: null, price_state: "dark", is_answer: false },
        { entity_key: "b", display_name: "B", probability: 0.5, probability_is_live: true, observed_at: "2026-08-25T11:00:00+00:00", age_hours: 1, price_state: "live", is_answer: false },
      ],
    });
    expect(rankedOutcomes(field).map((o) => o.display_name)).toEqual(["B"]);
  });

  it("renders an honest empty section rather than vanishing", () => {
    const html = render(<TournamentProps markets={[]} draw="mens-singles" />);
    expect(html).toContain('data-testid="tournament-props"');
    // UX-P145: "Nothing curated yet" → "Nothing to ask yet".
    expect(html).toContain("Nothing to ask yet");
    expect(html).not.toMatch(/\d+%/);
  });

  it("renders a curated prop with its hook", () => {
    const html = render(<TournamentProps markets={[market()]} draw="mens-singles" />);
    expect(html).toContain("Can Sinner win a second major this year?");
    expect(html).toContain("He already has one in 2026.");
    expect(html).toContain("22%");
  });

  // -------------------------------------------------------------------------
  // CERT-411 round 2 — a card is as fresh as its OLDEST PRINTED outcome
  // -------------------------------------------------------------------------
  //
  // THE SPECIMEN, and the reason it is a specimen and not a hypothetical: the
  // old rule was `ranked[0].probability_is_live` — the leader's flag, standing
  // in for the whole card. Every existing test above used all-live or all-dark
  // outcomes, so the mixed state, which is the one a real market spends most
  // of its life in, was never rendered once.
  //
  // Same defect the boards had before UX-P135 (a row is as fresh as its oldest
  // leg) and the slate had before it (a pair is live only when both sides
  // are). It survived here because this component read an outcome flag
  // directly instead of going through the pure layer.

  const outcome = (
    key: string,
    probability: number,
    live: boolean,
    ageHours: number
  ) => ({
    entity_key: key,
    display_name: key.toUpperCase(),
    probability,
    probability_is_live: live,
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: ageHours,
    price_state: (live ? "live" : "stale") as PropMarket["price_state"],
    is_answer: false,
  });

  /**
   * Fresh leader, stale runner-up — the card the old rule called live.
   *
   * ⚠️ THE RUNNER-UP'S AGE IS A PARAMETER SINCE UX-P138, and the default moved
   * from 480 hours to 30. The reason was ruling 8's rotation: a card past the
   * 48-hour boundary did not RENDER at all, so a 480-hour specimen made these
   * render assertions pass against an empty section — a fixed defect quietly
   * coming back.
   *
   * UX-P154 removed that hazard at the source. Alex's item 4 (2026-08-28)
   * overruled the rotation — a curated question is never hidden for age — so a
   * 480-hour card renders now, muted and saying its age. The 30-hour default
   * STAYS: it is the shape most of these assertions are about (a card that is
   * old but not remarkable), and the 480-hour case has its own test at the end
   * of this block, which is where the two rules meet.
   */
  const freshLeaderStaleRunner = (runnerAgeHours = 30) =>
    market({
      title: "Who will win a Grand Slam in 2026?",
      answer_entity_key: null,
      price_state: "stale",
      outcomes: [
        outcome("leader", 0.5, true, 1),
        outcome("runner", 0.3, false, runnerAgeHours),
        outcome("third", 0.2, true, 1),
      ],
    });

  it("SPECIMEN: a fresh leader does NOT make a stale runner-up live", () => {
    const card = freshLeaderStaleRunner();
    // The leader alone still looks live — that is exactly what the old rule read.
    expect(rankedOutcomes(card)[0].probability_is_live).toBe(true);
    // The card must not.
    expect(propIsPresentedAsLive(card)).toBe(false);

    const html = render(<TournamentProps markets={[card]} draw="mens-singles" />);
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
  });

  it("SPECIMEN: the muted card says WHICH outcome is old, and how old", () => {
    const html = render(
      <TournamentProps markets={[freshLeaderStaleRunner()]} draw="mens-singles" />
    );
    // A muted number with no stated reason reads as a bug, or is not noticed.
    expect(html).toContain('data-testid="prop-age"');
    expect(html).toContain("30 hours ago");
    expect(html).toContain("RUNNER");
  });

  it("the card is as old as its OLDEST printed outcome, not its newest", () => {
    expect(propGoverningAgeHours(freshLeaderStaleRunner(480))).toBe(480);
    expect(propGoverningAgeHours(freshLeaderStaleRunner())).toBe(30);
  });

  it("ITEM 4 MEETS CERT-411: the twenty-day card RENDERS, still not live", () => {
    /* The two rules compose, and UX-P154 changed which one owns the outcome.
     *
     * Until now ruling 8's rotation removed this card from the section
     * entirely, and this test asserted the empty state. Alex's item 4
     * (2026-08-28) reverses that half: illiquid props render with honest
     * freshness indication, never hidden — *"that's part of the value of the
     * product."*
     *
     * CERT-411's rule is UNTOUCHED and is now the one doing all the work:
     * `propIsPresentedAsLive` is still false for the 480-hour specimen, so the
     * card renders muted, with its age, and naming the outcome that is old.
     * That was always the fallback this test's old comment said would catch the
     * card "if rotation were ever loosened" — it has been, and it does.
     */
    const ancient = freshLeaderStaleRunner(480);
    expect(propIsPresentedAsLive(ancient)).toBe(false);
    expect(propIsQuiet(ancient)).toBe(true);
    const html = render(<TournamentProps markets={[ancient]} draw="mens-singles" />);
    expect(html).not.toContain('data-testid="props-empty"');
    expect(html).toContain('data-testid="prop-market"');
    expect(html).toContain('data-live="false"');
    expect(html).toContain('data-freshness="quiet"');
    // With its age, and with the old outcome named — the number is never shown
    // as current, which is the property CERT-411 bought.
    expect(html).toContain("Last number 20 days ago");
    expect(html).toContain("RUNNER");
  });

  it("an outcome the card does not PRINT cannot demote it", () => {
    // Only the top three are printed, so a stale fourth is not a contributor.
    // Getting this wrong in the other direction would mute a card whose every
    // visible number is current.
    const card = market({
      answer_entity_key: null,
      outcomes: [
        outcome("a", 0.4, true, 1),
        outcome("b", 0.3, true, 1),
        outcome("c", 0.2, true, 1),
        outcome("d", 0.1, false, 480),
      ],
    });
    expect(printedOutcomes(card).map((o) => o.entity_key)).toEqual(["a", "b", "c"]);
    expect(propIsPresentedAsLive(card)).toBe(true);
    expect(propStaleOutcomes(card)).toEqual([]);
  });

  it("an ANSWER card follows its answer, not the ladder's freshest rung", () => {
    // The mirror of the headline bug: a fresh 99% "1+" rung must not certify a
    // twenty-day-old "2+" answer as live.
    const ladder = market({
      answer_entity_key: "two-plus",
      price_state: "stale",
      outcomes: [
        { ...outcome("one-plus", 0.99, true, 1), display_name: "1+ Grand Slam wins" },
        {
          // 30h, not 480h — see the note on `freshLeaderStaleRunner`: past
          // ruling 8's rotation bound the card never reaches the renderer and
          // this assertion would pass against an empty section.
          ...outcome("two-plus", 0.555, false, 30),
          display_name: "2+ Grand Slam wins",
          is_answer: true,
        },
      ],
    });
    expect(propIsPresentedAsLive(ladder)).toBe(false);
    const html = render(<TournamentProps markets={[ladder]} draw="mens-singles" />);
    expect(html).toContain('data-live="false"');
  });

  it("a live card stays live, and says nothing about its age", () => {
    // The other direction. A rule that muted everything would pass every
    // assertion above and destroy the page.
    const card = market();
    expect(propIsPresentedAsLive(card)).toBe(true);
    const html = render(<TournamentProps markets={[card]} draw="mens-singles" />);
    expect(html).toContain('data-live="true"');
    expect(html).not.toContain('data-testid="prop-age"');
  });

  it("an unpriced card is not live — there is no reading to be fresh", () => {
    const unpriced = market({
      answer_entity_key: null,
      price_state: "dark",
      outcomes: [
        {
          ...outcome("a", 0, false, 0),
          probability: null,
          age_hours: null,
          price_state: "dark",
        },
      ],
    });
    expect(printedOutcomes(unpriced)).toEqual([]);
    expect(propIsPresentedAsLive(unpriced)).toBe(false);
  });
});
