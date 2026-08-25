/**
 * THE HONESTY GUARD — /tournaments/us-open championship boards (UX-P131).
 *
 * #2199 has the four US Open outright fields price-dark for 8 to 32 days while
 * this page ships on the marquee weekend. The directive's requirement is
 * precise: a board whose underlying prices are stale must SAY so, visibly, and
 * must never render staleness as a live number.
 *
 * So these tests assert the RENDERED MARKUP, not the props. A payload field
 * called `probability_is_live` that no pixel reflects is worth nothing, and
 * that gap is invisible to a test that only checks the data layer.
 *
 * Both directions are asserted throughout. A guard that only proves the stale
 * case can be satisfied by a component that marks everything stale forever,
 * which would be useless in the other direction — and once #2199 is fixed in
 * its own lane, the live case is the one that has to keep working.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import TrendSparkline from "@/components/tournament/TrendSparkline";
import {
  boardNotice,
  formatBoardProbability,
  rowIsPresentedAsLive,
  sparklinePoints,
  stalenessLabel,
  trendDirection,
  type TournamentBoardData,
  type TournamentRow,
} from "@/lib/tournament";

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "player-a",
    display_name: "Player A",
    seed: null,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.52,
    probability_is_live: true,
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    price_state: "live",
    source_count: 2,
    sources: [
      { source: "kalshi", probability: 0.5, observed_at: "2026-08-25T11:00:00+00:00" },
      { source: "polymarket", probability: 0.54, observed_at: "2026-08-25T11:00:00+00:00" },
    ],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [
      { date: "2026-08-23", probability: 0.48 },
      { date: "2026-08-24", probability: 0.5 },
      { date: "2026-08-25", probability: 0.52 },
    ],
    trend_delta: 0.04,
    ...overrides,
  };
}

function board(overrides: Partial<TournamentBoardData> = {}): TournamentBoardData {
  return {
    draw: "mens-singles",
    label: "Men's Singles",
    rows: [row()],
    contenders: 1,
    unpriced: 0,
    price_state: "live",
    newest_observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    ...overrides,
  };
}

const DARK_BOARD = board({
  price_state: "dark",
  age_hours: 8 * 24,
  newest_observed_at: "2026-08-17T09:00:00+00:00",
  rows: [
    row({
      probability_is_live: false,
      price_state: "dark",
      age_hours: 8 * 24,
      observed_at: "2026-08-17T09:00:00+00:00",
    }),
  ],
});

// ---------------------------------------------------------------------------
// The rendered admission
// ---------------------------------------------------------------------------

describe("a stale board says so, visibly", () => {
  it("renders a notice naming the age of the reading", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain('data-testid="price-state-notice"');
    expect(html).toContain("Prices paused");
    expect(html).toContain("8 days ago");
  });

  it("says the numbers are not live, in words", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain("not live prices");
  });

  it("marks every row non-live in the markup itself", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
  });

  it("still shows the number — we say we do not know, we do not go blank", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain("52.0%");
  });

  it("puts the reading's age on the row, not only in the banner", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain('data-testid="row-age"');
  });

  it("mutes the number so it cannot read as the live treatment", () => {
    const stale = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    const live = renderToStaticMarkup(<TournamentBoard board={board()} />);
    // The live board prints its blend in the primary text colour; the stale
    // board must not. This is the visual half of the contract — the data
    // attribute above is the machine-readable half.
    expect(live).toContain("text-text-primary");
    const staleProbabilityBlock = stale.slice(stale.indexOf('data-testid="row-probability"') - 200);
    expect(staleProbabilityBlock).toContain("text-text-secondary");
  });
});

describe("a live board does NOT cry wolf", () => {
  it("renders no notice at all", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board()} />);
    expect(html).not.toContain('data-testid="price-state-notice"');
    expect(html).not.toContain("Prices paused");
  });

  it("marks its rows live", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board()} />);
    expect(html).toContain('data-live="true"');
    expect(html).not.toContain('data-live="false"');
  });

  it("does not print a row age", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board()} />);
    expect(html).not.toContain('data-testid="row-age"');
  });
});

describe("a stale row inside an otherwise live board", () => {
  const mixed = board({
    rows: [
      row({ entity_key: "fresh", rank: 1 }),
      row({
        entity_key: "old",
        rank: 2,
        probability: 0.31,
        probability_is_live: false,
        price_state: "dark",
        age_hours: 30 * 24,
      }),
    ],
    contenders: 2,
  });

  it("does not launder the stale row", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={mixed} />);
    expect(html).toContain('data-live="true"');
    expect(html).toContain('data-live="false"');
    // The board is live overall, so there is no banner — which is exactly why
    // the per-row marking has to carry the weight here.
    expect(html).not.toContain('data-testid="price-state-notice"');
    expect(html).toContain('data-testid="row-age"');
  });
});

// ---------------------------------------------------------------------------
// The predicate the whole contract rests on
// ---------------------------------------------------------------------------

describe("rowIsPresentedAsLive", () => {
  it("trusts the server's verdict and nothing else", () => {
    expect(rowIsPresentedAsLive(row({ probability_is_live: true }))).toBe(true);
    expect(rowIsPresentedAsLive(row({ probability_is_live: false }))).toBe(false);
  });

  it("cannot be talked into a yes by a fresh-looking price_state", () => {
    // A payload that disagrees with itself must resolve to the SAFE reading.
    expect(
      rowIsPresentedAsLive(
        row({ probability_is_live: false, price_state: "live", age_hours: 0 })
      )
    ).toBe(false);
  });
});

describe("boardNotice", () => {
  it("is null only when the board is genuinely live", () => {
    expect(boardNotice(board())).toBeNull();
    expect(boardNotice(board({ price_state: "stale", age_hours: 9 }))).not.toBeNull();
    expect(boardNotice(board({ price_state: "dark", age_hours: 200 }))).not.toBeNull();
  });

  it("distinguishes never-priced from gone-quiet", () => {
    const never = boardNotice(
      board({ price_state: "dark", age_hours: null, newest_observed_at: null })
    );
    expect(never?.headline).toBe("No prices yet");
    const quiet = boardNotice(board({ price_state: "dark", age_hours: 200 }));
    expect(quiet?.headline).toBe("Prices paused");
  });
});

describe("stalenessLabel rounds DOWN", () => {
  it("never flatters the age", () => {
    // 8.9 days must not read as 9 — but more importantly 8.9 must not read as
    // "8 hours". The unit boundary is where this kind of label usually lies.
    expect(stalenessLabel(8 * 24 + 20)).toBe("8 days ago");
    expect(stalenessLabel(47.9)).toBe("47 hours ago");
    expect(stalenessLabel(48)).toBe("2 days ago");
    expect(stalenessLabel(1)).toBe("1 hour ago");
    expect(stalenessLabel(0.5)).toBe("30 min ago");
  });

  it("says never when there is no reading", () => {
    expect(stalenessLabel(null)).toBe("never");
  });
});

// ---------------------------------------------------------------------------
// Unsmoothed trend lines on a fixed axis
// ---------------------------------------------------------------------------

describe("sparklinePoints", () => {
  it("plots on a FIXED 0-100 axis, not an auto-scaled one", () => {
    // Two values two points apart. On a fixed axis they are nearly the same
    // height. On an auto-scaled axis one would sit at the top and the other at
    // the bottom, turning a 2pp wiggle into a visual collapse.
    const points = sparklinePoints(
      [
        { date: "a", probability: 0.5 },
        { date: "b", probability: 0.52 },
      ],
      52,
      26
    ).split(" ");
    const y0 = Number(points[0].split(",")[1]);
    const y1 = Number(points[1].split(",")[1]);
    expect(Math.abs(y0 - y1)).toBeLessThan(1);
    expect(y0).toBeCloseTo(13, 1);
  });

  it("puts 0% at the bottom and 100% at the top", () => {
    const points = sparklinePoints(
      [
        { date: "a", probability: 0 },
        { date: "b", probability: 1 },
      ],
      52,
      26
    ).split(" ");
    expect(Number(points[0].split(",")[1])).toBeCloseTo(26, 5);
    expect(Number(points[1].split(",")[1])).toBeCloseTo(0, 5);
  });

  it("emits exactly one vertex per observation — no interpolation", () => {
    const trend = [
      { date: "2026-08-20", probability: 0.4 },
      { date: "2026-08-21", probability: 0.44 },
      // A four-day gap. A smoother would invent points across it.
      { date: "2026-08-25", probability: 0.5 },
    ];
    expect(sparklinePoints(trend, 52, 26).split(" ")).toHaveLength(3);
  });

  it("draws nothing for a single observation", () => {
    expect(sparklinePoints([{ date: "a", probability: 0.5 }], 52, 26)).toBe("");
    expect(sparklinePoints([], 52, 26)).toBe("");
  });

  it("clamps rather than drawing outside the axis", () => {
    const points = sparklinePoints(
      [
        { date: "a", probability: -0.2 },
        { date: "b", probability: 1.4 },
      ],
      52,
      26
    ).split(" ");
    expect(Number(points[0].split(",")[1])).toBeCloseTo(26, 5);
    expect(Number(points[1].split(",")[1])).toBeCloseTo(0, 5);
  });
});

describe("TrendSparkline", () => {
  it("renders a polyline with one vertex per real observation", () => {
    const html = renderToStaticMarkup(
      <TrendSparkline trend={row().trend} delta={0.04} />
    );
    expect(html).toContain('data-points="3"');
    expect(html).toContain('data-direction="up"');
    expect(html).toContain("<polyline");
  });

  it("renders an empty slot rather than a fake line for one point", () => {
    const html = renderToStaticMarkup(
      <TrendSparkline trend={[{ date: "a", probability: 0.5 }]} delta={null} />
    );
    expect(html).toContain('data-testid="trend-sparkline-empty"');
    expect(html).not.toContain("<polyline");
  });

  it("draws a stale line in the neutral tone", () => {
    const html = renderToStaticMarkup(
      <TrendSparkline trend={row().trend} delta={0.04} muted />
    );
    expect(html).toContain("var(--text-muted)");
    expect(html).not.toContain("var(--accent-live)");
  });
});

describe("trendDirection has a dead band", () => {
  it("does not call noise a move", () => {
    expect(trendDirection(0.001)).toBe("flat");
    expect(trendDirection(-0.001)).toBe("flat");
    expect(trendDirection(0.04)).toBe("up");
    expect(trendDirection(-0.04)).toBe("down");
    expect(trendDirection(null)).toBe("flat");
  });
});

// ---------------------------------------------------------------------------
// Board shape
// ---------------------------------------------------------------------------

describe("board rendering", () => {
  it("renders rows in the order given, with their ranks", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard
        board={board({
          rows: [row({ entity_key: "a", rank: 1 }), row({ entity_key: "b", rank: 2, probability: 0.2 })],
          contenders: 2,
        })}
      />
    );
    expect(html.indexOf('data-entity="a"')).toBeLessThan(html.indexOf('data-entity="b"'));
    expect(html).toContain('data-rank="1"');
    expect(html).toContain('data-rank="2"');
  });

  it("renders a settled row as a result and never as a probability", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard
        board={board({
          rows: [
            row({
              state: "lost",
              probability: null,
              probability_is_live: false,
              trend: [],
              trend_delta: null,
            }),
          ],
        })}
      />
    );
    expect(html).toContain('data-testid="row-settled"');
    expect(html).toContain("lost");
    expect(html).toContain("—");
    expect(html).not.toContain("52.0%");
  });

  it("declares unpriced registered players instead of hiding them", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard board={board({ unpriced: 12 })} />
    );
    expect(html).toContain('data-testid="board-unpriced"');
    expect(html).toContain("12 more registered players have no price");
  });

  it("renders an honest empty board", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard
        board={board({ rows: [], contenders: 0, price_state: "dark", newest_observed_at: null, age_hours: null })}
      />
    );
    expect(html).toContain('data-testid="board-empty"');
    expect(html).toContain("No prices yet");
  });

  it("whispers the source count without becoming a comparison surface", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board()} />);
    expect(html).toContain("2 sources");
    // The individual source prices must NOT be on screen — standing ruling:
    // the blend is the product, sources are very faint, no comparison surface.
    expect(html).not.toContain("50.0%");
    expect(html).not.toContain("54.0%");
  });
});

describe("formatBoardProbability", () => {
  it("prints one decimal, and an em dash for absent", () => {
    expect(formatBoardProbability(0.523)).toBe("52.3%");
    expect(formatBoardProbability(0.0051)).toBe("0.5%");
    expect(formatBoardProbability(null)).toBe("—");
  });
});
