/**
 * A RISING CHANCE OF RELEGATION IS NEVER GOOD NEWS (#7745).
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/sport/soccer/epl`, Premier League 2026-27 grid, the **Relegated** column,
 * photographed 2026-09-21 ~08:18Z:
 *
 *     club                       Relegated   24h as rendered
 *     Arsenal                         0.7%   green ▲0.3
 *     Manchester City                 7.5%   green ▲2
 *     Liverpool                       5.1%   green ▲2
 *     Chelsea                         1.5%   red   ▼0.4
 *     Brighton & Hove Albion          4.1%   green ▲0.9
 *     Manchester United               3.8%   green ▲2
 *
 * Arsenal are top of the table and the page congratulated them, in green, on
 * becoming more likely to go down; Chelsea's relegation risk FELL — unambiguous
 * good news — and printed red. Every number was correct: the served payload had
 * `relegation.trend_24h` positive for exactly the clubs rendered green. The
 * colour was the defect.
 *
 * ═══ THE MECHANISM ═══
 *
 * Both renderers of a 24h move — the grid cell and the event page's outcomes
 * ladder — painted one polarity over every column: up green, down red. That is
 * right for `top_4`, `championship` and every other key in the vocabulary, and
 * inverted for `relegation`, the one column where the number rising is the bad
 * outcome. Polarity is now declared per column in `lib/gridColumnPolarity` and
 * read off the column's structured key, never parsed out of its label.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Relegation rises red" is passed perfectly by painting the whole column red,
 * or the whole grid red. So every case below is paired: the same six deltas are
 * asserted to produce the exact OPPOSITE colours on `top_4`, a falling
 * relegation cell is asserted green in the same render as a rising one is
 * asserted red, and the arrow glyph is asserted to keep following the sign of
 * the number — the triangle states which way it moved and is never flipped.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import AdvancementPath, {
  NON_ADVANCEMENT_STAGE_KEYS,
  type AdvancementStage,
} from "@/components/event/AdvancementPath";
import { ADVERSE_COLUMN_KEYS, risingIsGood } from "@/lib/gridColumnPolarity";
import { gridCellsToProgression } from "@/lib/gridCellState";
import type { ProgressionResponse } from "@/lib/types";

/** The photographed rows: club → 24h move on `Relegated`, as 0–1. */
const SPECIMEN: { club: string; prob: number; trend: number }[] = [
  { club: "Arsenal", prob: 0.007, trend: 0.0032 },
  { club: "Manchester City", prob: 0.075, trend: 0.015 },
  { club: "Liverpool", prob: 0.051, trend: 0.0195 },
  { club: "Chelsea", prob: 0.015, trend: -0.004 },
  { club: "Brighton & Hove Albion", prob: 0.041, trend: 0.0093 },
  { club: "Manchester United", prob: 0.038, trend: 0.017 },
];

/** One grid, one column, the six clubs — the cell under test and nothing else. */
function renderGrid(columnKey: string): string {
  const data: ProgressionResponse = {
    sport: "soccer_epl",
    tournament_name: "Premier League 2026-27",
    stages: [
      {
        key: columnKey,
        label: columnKey === "relegation" ? "Relegated" : columnKey,
        order: 1,
        market_id: null,
        market_name: null,
        resolved: false,
      },
    ],
    participants: SPECIMEN.map((s) => {
      const { probabilities, changes_24h, status, sources_data } = gridCellsToProgression({
        [columnKey]: {
          merged_probability: s.prob,
          trend_24h: s.trend,
          sources: [],
          state: "live",
        },
      });
      return {
        name: s.club,
        team_id: null,
        logo_url: null,
        primary_color: null,
        conference: null,
        region: null,
        seed: null,
        record: null,
        probabilities,
        changes_24h,
        status,
        sources_data,
      };
    }),
  };
  return renderToStaticMarkup(<TournamentProgressionTable data={data} />);
}

/**
 * Each club's 24h indicator, read off its own row.
 *
 * Keyed by CLUB rather than by position: the table sorts its rows by the
 * column it is showing, so a positional read would pin the sort order as
 * though it were the polarity rule and go red the day either moves. And keyed
 * on the indicator's own `title` ("… in 24h") rather than on a colour class, so
 * a test that expects red cannot be satisfied by an element that is not the
 * indicator at all.
 */
function indicatorsByClub(markup: string): Record<string, { colour: string; glyph: string }> {
  const rows = markup.split("<tr").slice(1);
  const out: Record<string, { colour: string; glyph: string }> = {};
  for (const { club } of SPECIMEN) {
    const row = rows.find((r) => r.includes(club.replace(/&/g, "&amp;")));
    if (!row) continue;
    const m = /<span class="text-\[10px\] leading-none ([^"]+)" title="[^"]* in 24h">([▲▼])/.exec(row);
    if (!m) continue;
    out[club] = { colour: m[1], glyph: m[2] };
  }
  return out;
}

/** `{club: colour}` for a one-column grid — every club present, or the test fails. */
function coloursByClub(columnKey: string): Record<string, string> {
  const found = indicatorsByClub(renderGrid(columnKey));
  expect(Object.keys(found)).toHaveLength(SPECIMEN.length);
  return Object.fromEntries(Object.entries(found).map(([club, i]) => [club, i.colour]));
}

const GOOD = "text-emerald-400";
const BAD = "text-red-400";

describe("the grid's Relegated column (#7745)", () => {
  it("paints a rising relegation risk red and a falling one green", () => {
    expect(coloursByClub("relegation")).toEqual({
      "Arsenal": BAD, // ▲0.3 — more likely to go down
      "Manchester City": BAD, // ▲1.5
      "Liverpool": BAD, // ▲2
      "Chelsea": GOOD, // ▼0.4 — less likely to go down
      "Brighton & Hove Albion": BAD, // ▲0.9
      "Manchester United": BAD, // ▲1.7
    });
  });

  it("keeps the triangle pointing the way the number moved", () => {
    // The colour answers "is this good news"; the glyph answers "which way did
    // it move". Flipping the glyph would make the indicator lie about the
    // number, which is a worse defect than the one being fixed.
    const found = indicatorsByClub(renderGrid("relegation"));
    expect(found["Arsenal"].glyph).toBe("▲");
    expect(found["Chelsea"].glyph).toBe("▼");
  });

  it("paints the SAME six moves the opposite way on a Top 4 column", () => {
    // The control that stops "everything red" passing the case above.
    expect(coloursByClub("top_4")).toEqual({
      "Arsenal": GOOD,
      "Manchester City": GOOD,
      "Liverpool": GOOD,
      "Chelsea": BAD,
      "Brighton & Hove Albion": GOOD,
      "Manchester United": GOOD,
    });
    const found = indicatorsByClub(renderGrid("top_4"));
    expect(found["Arsenal"].glyph).toBe("▲");
    expect(found["Chelsea"].glyph).toBe("▼");
  });

  it("treats an unrecognised column as up-is-good", () => {
    // Golf's `make_cut`, and by the same route any column a future config adds:
    // there is no third colour, and the whole measured vocabulary bar one key
    // rises toward something good.
    expect(coloursByClub("make_cut")).toEqual(coloursByClub("top_4"));
    expect(coloursByClub("make_cut")["Arsenal"]).toBe(GOOD);
  });
});

describe("the event page's outcomes ladder (#7745)", () => {
  /** Coventry City's season-outcomes rungs, the shape `RelatedFutures` builds. */
  const ladder = (columnKey: string | undefined, change: number): AdvancementStage[] => [
    { label: columnKey === "relegation" ? "Relegated" : "Top 4", prob: 0.785, change, resolved: false, columnKey },
  ];

  const render = (stages: AdvancementStage[]) => renderToStaticMarkup(<AdvancementPath stages={stages} />);

  it("paints a rising relegation rung as bad news, falling as good", () => {
    expect(render(ladder("relegation", 0.013))).toContain("text-accent-danger");
    expect(render(ladder("relegation", 0.013))).not.toContain("text-accent-brand");
    expect(render(ladder("relegation", -0.013))).toContain("text-accent-brand");
    expect(render(ladder("relegation", -0.013))).not.toContain("text-accent-danger");
  });

  it("keeps the arrow pointing the way the number moved", () => {
    expect(render(ladder("relegation", 0.013))).toContain("↑");
    expect(render(ladder("relegation", -0.013))).toContain("↓");
  });

  it("leaves a Top 4 rung, and a rung with no column key, alone", () => {
    expect(render(ladder("top_4", 0.013))).toContain("text-accent-brand");
    expect(render(ladder("top_4", -0.013))).toContain("text-accent-danger");
    // The raw-futures fallback and the tennis register carry no structured key.
    expect(render(ladder(undefined, 0.013))).toContain("text-accent-brand");
    expect(render(ladder(undefined, -0.013))).toContain("text-accent-danger");
  });
});

describe("the polarity vocabulary itself", () => {
  it("names at least one adverse column, and relegation is one", () => {
    // Emptying the set passes every "is good news green" case above by
    // reverting the fix, so the set is asserted non-empty on its own account.
    expect(ADVERSE_COLUMN_KEYS.size).toBeGreaterThan(0);
    expect(ADVERSE_COLUMN_KEYS.has("relegation")).toBe(true);
    for (const key of ADVERSE_COLUMN_KEYS) {
      expect(risingIsGood(key)).toBe(false);
    }
  });

  it("answers up-is-good for the rest of the measured vocabulary", () => {
    // Every other key/label pair in `league_configs.py`, re-counted 2026-09-21.
    for (const key of [
      "championship",
      "conference",
      "division",
      "elite_eight",
      "final",
      "final_four",
      "make_cut",
      "make_playoffs",
      "pennant",
      "quarterfinal",
      "round_of_32",
      "semifinal",
      "sweet_16",
      "title_game",
      "top_10",
      "top_20",
      "top_4",
      "top_5",
      "win",
    ]) {
      expect(risingIsGood(key)).toBe(true);
    }
  });

  it("answers up-is-good for an absent key", () => {
    expect(risingIsGood(undefined)).toBe(true);
    expect(risingIsGood(null)).toBe(true);
    expect(risingIsGood("")).toBe(true);
  });

  it("is the one set both surfaces read", () => {
    // #7206's heading rule and #7745's colour rule ask the same question of the
    // same vocabulary; two sets of one string each is how they stop agreeing.
    expect(NON_ADVANCEMENT_STAGE_KEYS).toBe(ADVERSE_COLUMN_KEYS);
  });
});
