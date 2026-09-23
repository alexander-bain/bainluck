/**
 * #8158 — THE "COMBINED" LINE STOPS DRAWING A FLAT, CONFIDENT 100% ON A PROPS BOARD.
 *
 * ## What a reader met
 *
 * `FuturesChart` built the combined line as `Math.min(1, sum)` over the rows on
 * screen. Production market **56775596** — *"Las Vegas: Team Specials"* — is ten
 * INDEPENDENT Kalshi props, and the served field measured 2026-09-22 through
 * `/api/futures/56775596/history?hours=168` totals **3.72**:
 *
 *     0.940  Brock Bowers records 3+ touchdowns in a single game
 *     0.640  Fernando Mendoza records 300+ passing yards in a single game
 *     0.520  Mike Washington Jr. records 500+ rushing yards
 *     0.385  Ashton Jeanty 75+ rushing and 75+ receiving yards
 *     0.380  Ashton Jeanty records 200+ rushing yards in a single game
 *     0.280  Jalen Nailor records 100+ receiving yards in a single game
 *     0.220  Mike Washington Jr. records 100+ rushing yards in a single game
 *     0.135  Las Vegas records 8+ sacks in a single game
 *     0.115  Las Vegas records 400+ passing yards in a single game
 *     0.105  Fernando Mendoza records 4+ passing touchdowns in a single game
 *
 * The chart's default top-three selection alone sums to **2.10**. Native measured
 * the same board's phone payload at **584 of 584 points clamped to exactly 100**,
 * with **20 distinct values collapsed to 1** (#8158, native/303). So ticking
 * "Combined" drew a dead-flat dashed line pinned to the top of the plot.
 *
 * The clamp is the defect, not the ugly number it hid. Summing independent binaries
 * is meaningless (gotcha #23); an unclamped 210% line at least READS as broken,
 * while a flat 100% reads as *"these three together are a lock"* — a claim the
 * market never made.
 *
 * ## What this file proves
 *
 * THE SPECIMEN: the real served field is refused, and — the arm that keeps this
 * guard from being vacuous — the raw unclamped sums it refuses are proven to be
 * above 1 at every timestamp, so the old code could only ever have drawn the flat
 * line. Delete the refusal and this file reddens on a fabricated 100%.
 *
 * THE CONTROLS: three genuinely exclusive production fields measured the same hour
 * — 1.000, 1.077 and 1.275 — keep their line, keep their movement, and keep the
 * clamp's original job of absorbing overround. A ceiling that merely turned the
 * feature off everywhere would fail here.
 *
 * THE WEB'S OWN HALF OF THE BUG: the old line summed `displayedOutcomes`, so
 * narrowing the table changed what the "sum" claimed to be. Two arms hold the
 * decision at the card: a two-row selection that is itself under the ceiling is
 * still refused when its FIELD is not one question, and a narrowed selection on an
 * exclusive field still draws.
 *
 * DOES NOT PROVE the rendered SVG or the control chip — those are the render test,
 * `components/aPropsBoardOffersNoCombinedLine8158.test.tsx`.
 */

import {
  SINGLE_QUESTION_SUM_CEILING,
  combinedLinePoints,
  fieldIsOneQuestion,
  lastServedProbability,
} from "@/lib/combinedLinePolicy";
import type { FuturesOutcomeHistory } from "@/lib/types";

const HOUR = 3_600_000;
const BASE = Date.UTC(2026, 8, 22, 0, 0, 0);

/** A series that walks from `from` to `to` over `n` hourly points — real movement,
 *  so a collapsed line is visible as a collapsed line and not as a short series. */
function series(id: number, name: string, from: number, to: number, n = 12): FuturesOutcomeHistory {
  return {
    outcome_id: id,
    name,
    history: Array.from({ length: n }, (_, k) => ({
      timestamp: new Date(BASE + k * HOUR).toISOString(),
      probability: from + ((to - from) * k) / (n - 1),
    })),
  } as unknown as FuturesOutcomeHistory;
}

/** `/api/futures/56775596/history?hours=168`, the ten rows above. Each series ends
 *  on its measured value and starts a little away from it so the field moves. */
const VEGAS_PROPS: FuturesOutcomeHistory[] = [
  series(1, "Brock Bowers 3+ TDs", 0.88, 0.94),
  series(2, "Mendoza 300+ passing yards", 0.6, 0.64),
  series(3, "Washington 500+ rushing yards", 0.57, 0.52),
  series(4, "Jeanty 75+ rush and 75+ rec", 0.36, 0.385),
  series(5, "Jeanty 200+ rushing yards", 0.41, 0.38),
  series(6, "Nailor 100+ receiving yards", 0.25, 0.28),
  series(7, "Washington 100+ rushing yards", 0.2, 0.22),
  series(8, "Las Vegas 8+ sacks", 0.15, 0.135),
  series(9, "Las Vegas 400+ passing yards", 0.1, 0.115),
  series(10, "Mendoza 4+ passing TDs", 0.12, 0.105),
];

/** `/api/futures/61998713/history` — "Democratic nomination odds leader on October
 *  31?", five alternatives to one question, served total 1.000. */
const NOMINATION_LEADER: FuturesOutcomeHistory[] = [
  series(21, "Newsom", 0.48, 0.52),
  series(22, "Harris", 0.24, 0.21),
  series(23, "Shapiro", 0.13, 0.12),
  series(24, "Whitmer", 0.09, 0.09),
  series(25, "Someone else", 0.06, 0.06),
];

/** `/api/futures/61980422/history` — "Lowest Mississippi level at St. Louis by
 *  November 30?", served total 1.077. A cumulative threshold ladder that sits UNDER
 *  the ceiling: this module does not claim to catch that shape, only the class where
 *  the sum is provably not a probability, and this arm pins that scope. */
const MISSISSIPPI: FuturesOutcomeHistory[] = [
  series(31, "Below -2 ft", 0.402, 0.43),
  series(32, "-2 to 0 ft", 0.3, 0.28),
  series(33, "0 to 2 ft", 0.2, 0.19),
  series(34, "2 to 4 ft", 0.105, 0.1),
  series(35, "Above 4 ft", 0.08, 0.077),
];

/** `/api/futures/61980283/history` — "B.C. Conservative Party Leadership Election
 *  Winner", served total **1.275**: a real exclusive field carrying real overround,
 *  0.025 under the ceiling. The arm that proves 1.3 is not a number that quietly
 *  strips working markets. */
const BC_LEADERSHIP: FuturesOutcomeHistory[] = [
  series(41, "Candidate A", 0.4, 0.44),
  series(42, "Candidate B", 0.3, 0.29),
  series(43, "Candidate C", 0.18, 0.17),
  series(44, "Candidate D", 0.12, 0.13),
  series(45, "Candidate E", 0.08, 0.085),
  series(46, "Candidate F", 0.07, 0.07),
  series(47, "Candidate G", 0.05, 0.05),
  series(48, "Candidate H", 0.04, 0.04),
];

function servedTotal(field: FuturesOutcomeHistory[]): number {
  return field.reduce((a, o) => a + (lastServedProbability(o) ?? 0), 0);
}

/** The sum the OLD code would have fed to `Math.min(1, …)` at each timestamp. */
function rawSums(displayed: FuturesOutcomeHistory[]): number[] {
  const n = displayed[0].history.length;
  return Array.from({ length: n }, (_, k) =>
    displayed.reduce((a, o) => a + (o.history[k].probability ?? 0), 0),
  );
}

describe("#8158 the specimen: ten independent props", () => {
  it("is the field that was measured — 3.72, and its top three 2.10", () => {
    expect(servedTotal(VEGAS_PROPS)).toBeCloseTo(3.72, 3);
    expect(servedTotal(VEGAS_PROPS.slice(0, 3))).toBeCloseTo(2.1, 3);
  });

  it("the old line could only have been the flat 100%: every raw sum exceeds 1", () => {
    const sums = rawSums(VEGAS_PROPS.slice(0, 3));
    expect(Math.min(...sums)).toBeGreaterThan(1);
    // …and the clamp would have collapsed that movement to a single value.
    expect(new Set(sums).size).toBeGreaterThan(1);
    expect(new Set(sums.map((s) => Math.min(1, s))).size).toBe(1);
  });

  it("is not one question, so the field is refused", () => {
    expect(fieldIsOneQuestion(VEGAS_PROPS)).toBe(false);
  });

  it("is still refused when the reader narrows to a selection under the ceiling", () => {
    // The web's own half of the bug: the old code summed the rows on screen, so
    // picking the two cheapest props (0.135 + 0.115) produced a tidy, plausible,
    // entirely fabricated line. The verdict belongs to the FIELD, not the picker —
    // `fieldIsOneQuestion` is never handed the selection, and this is the arm that
    // would redden if a later ship passed it one.
    const twoCheapest = [VEGAS_PROPS[7], VEGAS_PROPS[8]];
    expect(servedTotal(twoCheapest)).toBeLessThan(SINGLE_QUESTION_SUM_CEILING);
    expect(fieldIsOneQuestion(twoCheapest)).toBe(true); // the selection alone looks fine…
    expect(fieldIsOneQuestion(VEGAS_PROPS)).toBe(false); // …and the field is what decides.
  });

  it("the arithmetic helper does NOT judge — the caller does", () => {
    // Moved here after the union finding (see `fieldIsOneQuestion`'s "who may call
    // this"): on `/multi-history` the served rows double-count contenders, so a
    // helper that judged its own input would strip the line off every league
    // championship chart. `combinedLinePoints` sums; `fieldIsOneQuestion` judges.
    expect(combinedLinePoints(VEGAS_PROPS.slice(0, 3))).not.toBeNull();
  });
});

describe("#8158 the controls: exclusive fields keep their line", () => {
  const CASES: [string, FuturesOutcomeHistory[], number][] = [
    ["nomination leader", NOMINATION_LEADER, 1.0],
    ["Mississippi level", MISSISSIPPI, 1.077],
    ["B.C. leadership", BC_LEADERSHIP, 1.275],
  ];

  it.each(CASES)("%s (total %#2$s) is one question and draws", (_name, field, total) => {
    expect(servedTotal(field)).toBeCloseTo(total, 3);
    expect(fieldIsOneQuestion(field)).toBe(true);
    const pts = combinedLinePoints(field);
    expect(pts).not.toBeNull();
    expect(pts!.length).toBe(field[0].history.length);
  });

  it("keeps drawing, and keeps its movement, when the reader narrows an exclusive field", () => {
    // The question the control was added to answer: "Newsom or Harris — combined?"
    // 0.48+0.24 → 0.52+0.21, a real number that really moves, nowhere near the clamp.
    const narrowed = NOMINATION_LEADER.slice(0, 2);
    const pts = combinedLinePoints(narrowed)!;
    expect(pts).not.toBeNull();
    expect(Math.max(...pts.map((p) => p.sum))).toBeLessThan(1);
    expect(new Set(pts.map((p) => p.sum)).size).toBe(pts.length);
    expect(pts[0].sum).toBeCloseTo(0.72, 6);
    expect(pts[pts.length - 1].sum).toBeCloseTo(0.73, 6);
  });

  it("still lets the clamp absorb overround, which is the job it was written for", () => {
    // B.C. runs 1.240 → 1.275: real vig on a real exclusive field. The full field of
    // one question IS certainty, so pinning it at 100% is the truthful answer — and
    // the trim is a couple of percent of vig, not the factor of two that made the
    // props board lie. The arm below proves the trim is that small.
    const pts = combinedLinePoints(BC_LEADERSHIP)!;
    expect(pts.every((p) => p.sum === 1)).toBe(true);
    const raw = rawSums(BC_LEADERSHIP);
    expect(Math.max(...raw)).toBeCloseTo(1.275, 6);
    expect(Math.max(...raw) - 1).toBeLessThan(0.3);
    // …against the specimen, where the same clamp hid a factor of two.
    expect(Math.max(...rawSums(VEGAS_PROPS.slice(0, 3))) - 1).toBeGreaterThan(1);
  });

  it("keeps drawing on a truncated field, which can only lose mass", () => {
    // `/api/futures/61814765/history` — "DP World Tour: Open de France Winner",
    // nine rows of a 150-golfer field, served total 0.388. `top=N` removes
    // probability, so it can talk a field UNDER the ceiling but never over it.
    const golf = [
      series(51, "Golfer A", 0.1, 0.11),
      series(52, "Golfer B", 0.08, 0.078),
      series(53, "Golfer C", 0.07, 0.07),
      series(54, "Golfer D", 0.06, 0.06),
      series(55, "Golfer E", 0.07, 0.07),
    ];
    expect(servedTotal(golf)).toBeLessThan(SINGLE_QUESTION_SUM_CEILING);
    expect(combinedLinePoints(golf)).not.toBeNull();
  });
});

describe("#8158 the ceiling", () => {
  function flatField(values: number[]): FuturesOutcomeHistory[] {
    return values.map((v, i) => series(60 + i, `row ${i}`, v, v));
  }

  it("admits a field sitting exactly on it and refuses the next step up", () => {
    const at = flatField([0.65, 0.65]);
    expect(servedTotal(at)).toBeLessThanOrEqual(SINGLE_QUESTION_SUM_CEILING);
    expect(fieldIsOneQuestion(at)).toBe(true);

    const over = flatField([0.66, 0.65]);
    expect(servedTotal(over)).toBeGreaterThan(SINGLE_QUESTION_SUM_CEILING);
    expect(fieldIsOneQuestion(over)).toBe(false);
  });

  it("sits well clear of both measured populations", () => {
    // Exclusive median 1.014, non-exclusive median 3.610 (native, 11,095 open markets).
    expect(SINGLE_QUESTION_SUM_CEILING).toBeGreaterThan(1.014);
    expect(SINGLE_QUESTION_SUM_CEILING).toBeLessThan(3.610);
  });
});

describe("#8158 what it refuses to judge", () => {
  it("answers yes on an unpriced field rather than dressing silence as a verdict", () => {
    const unpriced: FuturesOutcomeHistory[] = [
      { outcome_id: 71, name: "A", history: [] },
      { outcome_id: 72, name: "B", history: [] },
    ] as unknown as FuturesOutcomeHistory[];
    expect(fieldIsOneQuestion(unpriced)).toBe(true);
    expect(fieldIsOneQuestion([])).toBe(true);
  });

  it("will not judge a single priced row, which could only ever pass", () => {
    const one = [series(73, "only row", 0.4, 0.4)];
    expect(fieldIsOneQuestion(one)).toBe(true);
    // And a lone row is never a combined line regardless.
    expect(combinedLinePoints(one)).toBeNull();
  });
});

describe("#8158 a trailing null is a missing reading, not a zero", () => {
  /** 0.90 + 0.50 + 0.10 = 1.50, refused — but only if the middle row's last
   *  KNOWN price is read. `history[last]?.probability ?? 0`, the sort idiom next
   *  door in EvolutionView, scores it 1.00 and hands back the fabricated line. */
  const TRAILING_NULL: FuturesOutcomeHistory[] = [
    series(81, "priced high", 0.9, 0.9),
    {
      outcome_id: 82,
      name: "last reading missing",
      history: [
        { timestamp: new Date(BASE).toISOString(), probability: 0.5 },
        { timestamp: new Date(BASE + HOUR).toISOString(), probability: null },
      ],
    },
    series(83, "priced low", 0.1, 0.1),
  ] as unknown as FuturesOutcomeHistory[];

  it("reads the last price, not the last row", () => {
    expect(lastServedProbability(TRAILING_NULL[1])).toBe(0.5);
    expect(TRAILING_NULL[1].history[TRAILING_NULL[1].history.length - 1].probability).toBeNull();
  });

  it("refuses the field that only looks exclusive when the null is scored zero", () => {
    expect(servedTotal(TRAILING_NULL)).toBeCloseTo(1.5, 6);
    expect(fieldIsOneQuestion(TRAILING_NULL)).toBe(false);
  });

  it("returns null for a row that never carried a price", () => {
    const never = {
      outcome_id: 84,
      name: "never priced",
      history: [{ timestamp: new Date(BASE).toISOString(), probability: null }],
    } as unknown as FuturesOutcomeHistory;
    expect(lastServedProbability(never)).toBeNull();
  });
});
