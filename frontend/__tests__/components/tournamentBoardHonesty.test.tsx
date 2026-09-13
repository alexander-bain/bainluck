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

import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TrendSparkline from "@/components/tournament/TrendSparkline";
import {
  boardNotice,
  boardRenderedPercents,
  formatBoardProbability,
  rowFreshnessLabel,
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
    freshest_observed_at: "2026-08-25T11:00:00+00:00",
    freshest_age_hours: 1,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [
      {
        source: "kalshi",
        probability: 0.5,
        observed_at: "2026-08-25T11:00:00+00:00",
        age_hours: 1,
        price_state: "live",
      },
      {
        source: "polymarket",
        probability: 0.54,
        observed_at: "2026-08-25T11:00:00+00:00",
        age_hours: 1,
        price_state: "live",
      },
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
    rows_not_live: 0,
    mixed_freshness_rows: 0,
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
    expect(html).toContain("Updates paused");
    expect(html).toContain("8 days ago");
  });

  it("says the numbers are not live, in words", () => {
    // UX-P146: the sentence used to end "not live prices". Alex's product-wide
    // ruling took the noun; the ADMISSION is what this test is for and it is
    // unchanged, so the assertion moved with the wording rather than being
    // dropped.
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain("not live ones");
  });

  it("marks every row non-live in the markup itself", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
  });

  it("still shows the number — we say we do not know, we do not go blank", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={DARK_BOARD} />);
    // `52.0%` until #5893; the claim this test makes is that the number is on
    // screen at all, and it is unchanged by how many digits it carries.
    expect(html).toContain(">52%<");
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
    expect(html).not.toContain("Updates paused");
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
// THE MIXED-CONTRIBUTOR ROW — `C-USOPEN-DAY3-TIER2`, at the pixel
//
// The server-side fix is the verdict; this is the half a reader can see. The
// specimen row blends a one-hour Kalshi price with a twenty-day Polymarket
// price, so it must render exactly as a wholly stale row does — muted, aged,
// never in the confident type — and it must say WHICH leg is old, because
// "20 days ago" on its own describes a row nobody has looked at, which is not
// what happened.
// ---------------------------------------------------------------------------

const MIXED_ROW = row({
  entity_key: "mixed",
  probability: 0.42,
  probability_is_live: false,
  price_state: "dark",
  observed_at: "2026-08-05T11:00:00+00:00",
  age_hours: 20 * 24,
  freshest_observed_at: "2026-08-25T11:00:00+00:00",
  freshest_age_hours: 1,
  stale_sources: ["polymarket"],
  mixed_freshness: true,
  sources: [
    {
      source: "kalshi",
      probability: 0.4,
      observed_at: "2026-08-25T11:00:00+00:00",
      age_hours: 1,
      price_state: "live",
    },
    {
      source: "polymarket",
      probability: 0.44,
      observed_at: "2026-08-05T11:00:00+00:00",
      age_hours: 20 * 24,
      price_state: "dark",
    },
  ],
});

describe("a row blended from a fresh source and a stale one", () => {
  const html = renderToStaticMarkup(
    <TournamentBoard
      board={board({ rows: [MIXED_ROW], mixed_freshness_rows: 1, rows_not_live: 1 })}
    />
  );

  it("is not rendered in the live treatment", () => {
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
    expect(html).toContain('data-mixed-freshness="true"');
  });

  it("still prints the number — the fresh half is real information", () => {
    expect(html).toContain(formatBoardProbability(0.42));
  });

  it("ages the row from its OLDEST leg, never its freshest", () => {
    expect(html).toContain('data-testid="row-age"');
    expect(html).toContain(stalenessLabel(20 * 24));
    // The one-hour reading must not appear as the row's age. This is the
    // rendered form of the whole defect.
    expect(html).not.toContain("1 hour ago");
  });

  it("says only PART of it is old, rather than implying the whole row is abandoned", () => {
    // UX-P150, ruling 141: this used to assert the venue NAME ("Polymarket").
    // Alex banned venue names in reader copy on 2026-08-28 — a reader gets our
    // probability, not our sourcing. The honesty property the assertion exists
    // for is untouched and is what is pinned here: the line has to distinguish
    // "one of the readings behind this is old" from "nobody has looked at this
    // in three weeks", and a count does that as well as a name did.
    expect(html).toContain("one reading");
    expect(html).not.toContain("Polymarket");
  });
});

describe("rowFreshnessLabel", () => {
  it("says nothing about a live row", () => {
    expect(rowFreshnessLabel(row())).toBeNull();
  });

  it("counts the stale contributors on a mixed row, without naming them", () => {
    // Ruling 141. The count is the fact; the venue was never the fact.
    expect(rowFreshnessLabel(MIXED_ROW)).toBe("one reading 20 days ago");
  });

  it("pluralises when more than one leg is old but not all of them", () => {
    // Three-source rows exist and "two reading 20 days ago" would be the kind
    // of sentence a reader files under "nobody looked at this".
    expect(
      rowFreshnessLabel({
        ...MIXED_ROW,
        stale_sources: ["polymarket", "odds_api"],
      })
    ).toBe("two readings 20 days ago");
  });

  it("falls back to a bare age when EVERY contributor is stale", () => {
    // Nothing to single out — naming both sources would be noise, and the
    // plain reading ("20 days ago") is then true of the whole row.
    expect(
      rowFreshnessLabel(
        row({
          probability_is_live: false,
          price_state: "dark",
          age_hours: 20 * 24,
          mixed_freshness: false,
          stale_sources: ["kalshi", "polymarket"],
        })
      )
    ).toBe("20 days ago");
  });

  it("reports the GOVERNING age, never the freshest", () => {
    // The regression that would reintroduce the defect in the copy alone.
    expect(rowFreshnessLabel(MIXED_ROW)).not.toContain("1 hour");
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
    expect(never?.headline).toBe("No numbers yet");
    const quiet = boardNotice(board({ price_state: "dark", age_hours: 200 }));
    expect(quiet?.headline).toBe("Updates paused");
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

  it("declares players with no price instead of hiding them", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard board={board({ unpriced: 12 })} />
    );
    expect(html).toContain('data-testid="board-unpriced"');
    // UX-P145: was "12 more registered players have no price". *Registered* is
    // the name of our JSON file. The COUNT is the point of the line and it is
    // still here — the reader must not be shown a board that looks complete.
    expect(html).toContain("12 more players in this draw have no number yet");
  });

  it("renders an honest empty board", () => {
    const html = renderToStaticMarkup(
      <TournamentBoard
        board={board({ rows: [], contenders: 0, price_state: "dark", newest_observed_at: null, age_hours: null })}
      />
    );
    expect(html).toContain('data-testid="board-empty"');
    expect(html).toContain("No numbers yet");
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

/**
 * ═══ #5893 — THE BOARD AND THE MATCH CARD ARE ONE ANSWER ═══
 *
 * Alex's case: NEXT UP said Zverev 58% and the board below said 57.2%, on final
 * day, three rows apart. live/199 fixed the served halves (both 0.575); these
 * guard the RENDERING, which was two separate departures from the product's
 * standing rule and needed both fixed to close it.
 *
 * The specimens are the real payload read at 2026-09-13 11:50Z.
 */
describe("formatBoardProbability", () => {
  it("prints the product's whole percent, and an em dash for absent", () => {
    expect(formatBoardProbability(0.523)).toBe("52%");
    expect(formatBoardProbability(null)).toBe("—");
  });

  it("inherits the boundary rule the decimal never had: possible never prints 0%", () => {
    // The men's board serves eighteen rows at 0.001 and 0.0005. `toFixed(1)`
    // printed every one of them `0.1%` — a false precision on the second — and
    // `Math.round` would print `0%`, which reads as impossible (UX-P046).
    expect(formatBoardProbability(0.001)).toBe("<1%");
    expect(formatBoardProbability(0.0005)).toBe("<1%");
    // Exactly zero IS the boundary. An eliminated contender may say so.
    expect(formatBoardProbability(0)).toBe("0%");
  });

  it("takes the field's integer when it is given one, and rounds alone when it is not", () => {
    expect(formatBoardProbability(0.425, 42)).toBe("42%");
    expect(formatBoardProbability(0.425)).toBe("43%");
  });
});

describe("boardRenderedPercents", () => {
  const contender = (key: string, probability: number | null, rank: number) =>
    row({ entity_key: key, display_name: key, probability, rank });

  it("rounds a two-horse field once, so the board cannot print 101", () => {
    // The exact pair live/199's PR #5902 serves. Rounded per row this is 58/43;
    // the FINAL card above it prints 58/42 through `renderedDuelPercents`.
    const percents = boardRenderedPercents([
      contender("zverev", 0.575, 1),
      contender("shelton", 0.425, 2),
      contender("dimitrov", 0.001, 3),
    ]);
    expect(percents.zverev).toBe(58);
    expect(percents.shelton).toBe(42);
    expect((percents.zverev ?? 0) + (percents.shelton ?? 0)).toBe(100);
    // The tail is not part of the pair and is not renormalized into one.
    expect(percents.dimitrov).toBe(0);
  });

  it("is decided over the whole field, so the women's 99.5/0.5 pair also totals 100", () => {
    const percents = boardRenderedPercents([
      contender("leader", 0.99475, 1),
      contender("other", 0.00525, 2),
    ]);
    expect(percents.leader).toBe(99);
    expect(percents.other).toBe(1);
  });

  it("leaves a field that is NOT down to two alone", () => {
    // Four live contenders: no pair rule, every row rounds on its own. Asserted
    // in this direction because a guard that only proves the final-day case is
    // satisfied by a component that pair-rounds the top two of every draw.
    const percents = boardRenderedPercents([
      contender("a", 0.4, 1),
      contender("b", 0.3, 2),
      contender("c", 0.2, 3),
      contender("d", 0.1, 4),
    ]);
    expect(percents).toEqual({ a: 40, b: 30, c: 20, d: 10 });
  });

  it("does not fire on the TOP two when a third contender is still priced", () => {
    // The gate is "exactly two", and this is the fixture that proves it: the
    // leading pair sums to exactly 1.0, so a `>= 2` gate would pair-round them
    // and derive 42 for a row that is not in a two-horse field. Found by a
    // mutation run — the four-way test below could not kill `>= 2`, because
    // `renderedDuelPercents` declined 0.4/0.3 on its own.
    const percents = boardRenderedPercents([
      contender("zverev", 0.575, 1),
      contender("shelton", 0.425, 2),
      contender("darkhorse", 0.05, 3),
    ]);
    expect(percents).toEqual({ zverev: 58, shelton: 43, darkhorse: 5 });
  });

  it("leaves two survivors alone when they are not a complement pair", () => {
    // Summing to 0.80 means a third of the field is unpriced, not that the vig
    // needs removing — normalizing here would invent twenty points.
    const percents = boardRenderedPercents([
      contender("a", 0.45, 1),
      contender("b", 0.35, 2),
    ]);
    expect(percents).toEqual({ a: 45, b: 35 });
  });

  it("gives a settled row no integer, so it still renders an em dash", () => {
    const percents = boardRenderedPercents([contender("out", null, 1)]);
    expect(percents.out).toBeNull();
    expect(formatBoardProbability(null, percents.out)).toBe("—");
  });
});

describe("the rendered board on final day (#5893)", () => {
  const finalDay = board({
    rows: [
      row({ entity_key: "zverev", display_name: "A. Zverev", probability: 0.575, rank: 1 }),
      row({ entity_key: "shelton", display_name: "B. Shelton", probability: 0.425, rank: 2 }),
    ],
    contenders: 2,
  });

  it("prints the two numbers the FINAL card prints, and no decimal", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={finalDay} />);
    const printed = [...html.matchAll(/data-testid="row-probability"[^>]*>([^<]+)</g)].map(
      (match) => match[1]
    );
    expect(printed).toEqual(["58%", "42%"]);
  });

  it("prints the SAME string in the chart legend as in the board", () => {
    // The cross-surface guard, and the reason this is not a one-line change.
    // #5893 is "one question, two numbers"; a fix applied to the board alone
    // moves the disagreement up the page instead of closing it, and every
    // board-only assertion above would still pass.
    const legend = renderToStaticMarkup(
      <ContenderChart
        rows={finalDay.rows}
        draw="mens-singles"
        selection={["zverev", "shelton"]}
        onToggle={() => {}}
      />
    );
    const legendPercents = [
      ...legend.matchAll(/data-testid="chart-legend-probability"[^>]*>([^<]+)</g),
    ].map((match) => match[1]);
    const boardPercents = [
      ...renderToStaticMarkup(<TournamentBoard board={finalDay} />).matchAll(
        /data-testid="row-probability"[^>]*>([^<]+)</g
      ),
    ].map((match) => match[1]);
    expect(legendPercents).toEqual(["58%", "42%"]);
    expect(legendPercents).toEqual(boardPercents);
  });

  it("keeps the pair whole under a long tail, collapsed and expanded alike", () => {
    // The reader-facing invariant: the number must not move on "show more".
    //
    // HONEST ABOUT WHAT THIS CANNOT PROVE. The memo reads `board.rows` rather
    // than the visible slice, and on rank-sorted rows those two CANNOT
    // disagree — the slice is the top three, so it holds at most as many
    // contenders as the field and never fewer than the field's first three.
    // No fixture distinguishes the two implementations, so this does not
    // pretend to; it holds the invariant a reader can see, and the whole-field
    // read is the belt for a future rule that is not monotonic in rank.
    const padded = board({
      rows: [
        ...finalDay.rows,
        ...Array.from({ length: 8 }, (_, index) =>
          row({
            entity_key: `out-${index}`,
            display_name: `Out ${index}`,
            probability: 0.001,
            rank: index + 3,
          })
        ),
      ],
      contenders: 2,
    });
    const html = renderToStaticMarkup(<TournamentBoard board={padded} />);
    const printed = [...html.matchAll(/data-testid="row-probability"[^>]*>([^<]+)</g)].map(
      (match) => match[1]
    );
    expect(printed.slice(0, 2)).toEqual(["58%", "42%"]);
  });
});
