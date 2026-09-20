/**
 * #7587 — the matched-bucket "Difference" cell prints the gap, unsigned, which
 * is the quantity the sentence under the table already calls a difference.
 *
 * Shopped on production at 390px, 2026-09-20 ~20:05Z, DEFAULT (traded) cohort.
 * Under "Does a price that moves predict better?" the table's three numeric
 * columns all came out of one formatter, so all three wore a sign in the same
 * tabular type:
 *
 *   Predicted    Traded    Untraded   Difference
 *   40-50%       −3.5pp     +0.3pp       −3.8pp
 *   50-60%       +0.2pp     +1.7pp       −1.5pp
 *
 * and the fold beneath, "Reading this table", defines that sign:
 *
 *   "Error is actual minus predicted, in percentage points: negative = the
 *    outcome happened LESS often than the price implied."
 *
 * True of the first two columns, false of the third. Read by the rule the page
 * had just given, −3.8pp says "outcomes happened 3.8pp less often than the
 * price implied", and nothing in that band did: −3.5 and +0.3 subtracted is not
 * an error anything has.
 *
 * ═══ WHY EXPLAINING THE SIGN WAS NOT THE FIX ═══
 *
 * Because the sign does not track the thing the heading asks about. Measured on
 * the live payload (2026-09-20, `buckets[]` grouped by `bucket_idx` ×
 * `price_moved`):
 *
 *   40-50%   traded −3.49  untraded +0.31   gap −3.80   traded 11x FURTHER
 *   50-60%   traded +0.18  untraded +1.69   gap −1.51   traded  9x CLOSER
 *
 * Same sign, opposite verdicts, under a heading that asks which cohort predicts
 * better — and nine of ten rows were negative, so the column read as a uniform
 * answer to a question it cannot answer. That property is not a quirk of one
 * payload, so ARM 5 below rebuilds it in the fixture and asserts it: this file
 * fails if the specimen stops being one where sign and closeness disagree, which
 * is the only condition under which the fix's premise holds.
 *
 * ═══ WHAT IS *NOT* THE DEFECT, SO NO FIX GOES THERE ═══
 *
 * `gapPp` is correct and deliberately signed — `moved.errorPp -
 * unchanged.errorPp`, `lib/calibrationMath.ts` — and `widest` is already chosen
 * on `Math.abs`. The measurement is right; only its RENDER was wrong. So
 * `lib/calibrationMath.ts` is untouched, `data-gap-pp` keeps the sign for probes
 * and rails (ARM 2), and this file must not be satisfied by absolute-valuing
 * `gapPp` at source — that would delete direction from the data as well as the
 * cell, and break `compareMatchedBuckets`'s own suite.
 *
 * Nor is the fix "drop the two error columns' signs to match". Their sign is
 * content, it is defined one line below them, and ARM 1 asserts it SURVIVES —
 * without that arm, deleting every sign on the table passes this file.
 *
 * ═══ WHAT THIS FILE GUARDS ═══
 *
 *   1. UNSIGNED, BESIDE TWO SIGNED — the gap cell carries neither `+` nor `−`
 *      while both error cells in the same row still carry one. Both halves, or
 *      the assertion is satisfied by a table with no signs anywhere.
 *   2. THE DATA KEEPS THE SIGN — `data-gap-pp` is still negative on rows where
 *      the moved cohort sits lower, so nothing downstream of the render loses
 *      direction.
 *   3. THE CELL IS |gap| — equal to the absolute value at display precision, not
 *      zero, not the wrong term, not one of the two errors.
 *   4. ONE QUANTITY, ONE CONVENTION — the widest row's cell and the sentence
 *      forty pixels below it print the same string. That internal disagreement
 *      is the defect stated at its shortest, and it regresses the moment either
 *      side is reformatted alone.
 *   5. THE FIXTURE IS THE SPECIMEN — two comparable rows with negative gaps,
 *      one where the moved cohort is further from the line and one where it is
 *      closer. Asserted, not commented.
 *   6. THE FOLD NAMES THE THIRD COLUMN — a signless number beside two signed
 *      ones is its own small puzzle, and the fold that already decodes the
 *      columns is where that is answered (notice 34: it is a method note, so it
 *      folds rather than sitting in the body).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { compareMatchedBuckets } from "@/lib/calibrationMath";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as unknown as { __calPayload: CalibrationData }).__calPayload,
  }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/components/CalibrationChart", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: () => ReactLib.createElement("div", { "data-testid": "chart" }),
  };
});

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/* ───────────────────────────── the fixture ───────────────────────────── */

/** Both sides of a row must clear `MATCHED_BUCKET_MIN_SIDE_N` to be comparable. */
const SIDE_N = 2000;

/**
 * One row of the specimen, written as the two errors a reader sees rather than
 * as winner counts, so the property ARM 5 asserts is legible here.
 *
 * `errorPp = actual − predicted`, and `predicted` is pinned to the middle of the
 * bucket so every row lands in the band its index names.
 */
type Spec = { idx: number; movedErrPp: number; unchangedErrPp: number };

const SPECS: Spec[] = [
  // gap −4.5, and the MOVED side is 8x FURTHER from the line.
  { idx: 4, movedErrPp: -4.0, unchangedErrPp: +0.5 },
  // gap −2.5, and the MOVED side is 6x CLOSER. Same sign, opposite verdict.
  { idx: 6, movedErrPp: +0.5, unchangedErrPp: +3.0 },
  // gap −1.0, inside the close band, so the sentence has something to count.
  { idx: 2, movedErrPp: -0.5, unchangedErrPp: +0.5 },
];

const WIDEST = SPECS[0];
const WIDEST_GAP_PP = WIDEST.movedErrPp - WIDEST.unchangedErrPp; // −4.5

function bucket(source: string, idx: number, errPp: number, priceMoved: boolean) {
  const predicted = idx / 10 + 0.05; // middle of the band
  const sumProb = predicted * SIDE_N;
  // winners chosen so `winners/n − sumProb/n` is exactly `errPp/100`.
  const winners = Math.round((predicted + errPp / 100) * SIDE_N);
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: priceMoved,
    n: SIDE_N,
    winners,
    avg_prob: predicted,
    sum_prob: sumProb,
    sum_sq_err: SIDE_N * 0.2,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

const BUCKETS = SPECS.flatMap(s => [
  bucket("kalshi", s.idx, s.movedErrPp, true),
  bucket("polymarket", s.idx, s.unchangedErrPp, false),
]);

function payload(): CalibrationData {
  const total = BUCKETS.reduce((s, b) => s + b.n, 0);
  return {
    buckets: BUCKETS,
    total_markets: total,
    total_outcomes: total,
    total_winners: BUCKETS.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.33,
    mce_ci_upper: 1.19,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T07:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-20" },
    by_source: [
      { source: "kalshi", ece: 1.0, mce: 1.3, n: total / 2 },
      { source: "polymarket", ece: 0.9, mce: 1.1, n: total / 2 },
    ],
    by_category: [{ category: "baseball", ece: 0.9, n: total }],
  } as unknown as CalibrationData;
}

(global as unknown as { __calPayload: CalibrationData }).__calPayload = payload();
const HTML = renderToStaticMarkup(<CalibrationPage />);

const COMPARISON = compareMatchedBuckets(BUCKETS);

/* ──────────────────────────── reading the table ──────────────────────────── */

type RenderedRow = {
  bucket: number;
  gapAttr: string;
  /** Visible text of the four cells, inner tags stripped. */
  cells: string[];
};

/**
 * Visible text of a markup fragment.
 *
 * A SCAN, not `.replace(/<[^>]*>/g, "")`. That one-liner is an HTML sanitizer's
 * exact shape, is wrong on nested angle brackets, and CodeQL fails the PR for it
 * with a HIGH `js/incomplete-multi-character-sanitization` — which it did to this
 * file's first draft, the fourth time that has happened on this page's tests.
 * Copied from `benchmarkRowCarriesItsPerBucketWord7225.test.tsx`, where the same
 * two alerts and the same remedy are written out at length.
 *
 * No entity table is needed here: every cell this reads holds digits, `pp`, a
 * comma, `%` or U+2212, and the only entity in the row markup — `&mdash;`, in the
 * absent-side cells — is JSX, so React emits the character itself.
 */
function cellText(fragment: string): string {
  let out = "";
  let inTag = false;
  for (const ch of fragment) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.replace(/\s+/g, " ").trim();
}

function renderedRows(html: string): RenderedRow[] {
  return html
    .split("<tr ")
    .filter(chunk => chunk.includes('data-testid="calibration-matched-row"'))
    .map(chunk => {
      const tr = chunk.slice(0, chunk.indexOf("</tr>"));
      const cells = tr
        .split("<td ")
        .slice(1)
        .map(td => td.slice(td.indexOf(">") + 1, td.indexOf("</td>")))
        .map(cellText);
      return {
        bucket: Number(/data-bucket="([^"]*)"/.exec(tr)?.[1]),
        gapAttr: /data-gap-pp="([^"]*)"/.exec(tr)?.[1] ?? "",
        cells,
      };
    });
}

const ROWS = renderedRows(HTML);
const byBucket = new Map(ROWS.map(r => [r.bucket, r]));

/** Every character this page uses for a sign. `fmt` emits U+2212, attrs "-". */
const SIGNS = ["+", "−", "-"];
const hasSign = (s: string) => SIGNS.some(c => s.includes(c));

/* ──────────────────────────────── arm 0 ──────────────────────────────── */

describe("the specimen renders at all", () => {
  test("the matched table is on the page with one row per spec", () => {
    // Without this, every arm below passes vacuously over an empty list.
    expect(HTML).toContain('data-testid="calibration-matched-buckets"');
    expect(ROWS).toHaveLength(SPECS.length);
    for (const s of SPECS) expect(byBucket.has(s.idx)).toBe(true);
  });

  test("each row rendered four cells", () => {
    for (const r of ROWS) expect(r.cells).toHaveLength(4);
  });

  test("the errors the fixture asked for are the errors the page computed", () => {
    // The fixture states errors and stores winners; if the conversion drifts,
    // every magnitude assertion below is measuring the wrong specimen.
    for (const s of SPECS) {
      const row = COMPARISON.rows.find(r => r.bucketIdx === s.idx)!;
      expect(row.moved!.errorPp).toBeCloseTo(s.movedErrPp, 5);
      expect(row.unchanged!.errorPp).toBeCloseTo(s.unchangedErrPp, 5);
      expect(row.comparable).toBe(true);
    }
  });
});

/* ──────────────────────────────── arm 5 ──────────────────────────────── */
/* First, because arms 1-4 only matter if the specimen has the property.     */

describe("the specimen is one where the sign and the verdict disagree", () => {
  test("both rows of interest have a NEGATIVE gap", () => {
    for (const s of [SPECS[0], SPECS[1]]) {
      const row = COMPARISON.rows.find(r => r.bucketIdx === s.idx)!;
      expect(row.gapPp).toBeLessThan(0);
    }
  });

  test("in one the moved cohort is further from the line, in the other closer", () => {
    const further = COMPARISON.rows.find(r => r.bucketIdx === SPECS[0].idx)!;
    const closer = COMPARISON.rows.find(r => r.bucketIdx === SPECS[1].idx)!;
    expect(Math.abs(further.moved!.errorPp)).toBeGreaterThan(
      Math.abs(further.unchanged!.errorPp)
    );
    expect(Math.abs(closer.moved!.errorPp)).toBeLessThan(
      Math.abs(closer.unchanged!.errorPp)
    );
    // Which is the whole argument: one sign, two opposite answers to the
    // question the section's heading asks.
    expect(Math.sign(further.gapPp!)).toBe(Math.sign(closer.gapPp!));
  });
});

/* ──────────────────────────────── arm 1 ──────────────────────────────── */

describe("the gap cell is unsigned and its two neighbours are not", () => {
  test("no gap cell carries a sign", () => {
    for (const r of ROWS) expect(hasSign(r.cells[3])).toBe(false);
  });

  test("both error cells in every row still carry one", () => {
    // The non-vacuity arm. Deleting `fmt`'s sign entirely would satisfy the
    // test above and silently strip the column whose sign is its content.
    for (const r of ROWS) {
      expect(hasSign(r.cells[1])).toBe(true);
      expect(hasSign(r.cells[2])).toBe(true);
    }
  });

  test("the fold's sign rule, which governs those two columns, is still stated", () => {
    expect(HTML).toContain("negative = the outcome");
  });
});

/* ──────────────────────────────── arm 2 ──────────────────────────────── */

describe("the measurement keeps the sign the render drops", () => {
  test("data-gap-pp is negative wherever the moved cohort sits lower", () => {
    for (const s of SPECS) {
      const expected = s.movedErrPp - s.unchangedErrPp;
      expect(expected).toBeLessThan(0);
      expect(Number(byBucket.get(s.idx)!.gapAttr)).toBeCloseTo(expected, 5);
    }
  });

  test("compareMatchedBuckets still returns a signed gap", () => {
    // Guards against the wrong fix: absolute-valuing at source instead of at
    // the cell would pass arm 1 and destroy direction for every consumer.
    for (const s of SPECS) {
      const row = COMPARISON.rows.find(r => r.bucketIdx === s.idx)!;
      expect(row.gapPp).toBeCloseTo(s.movedErrPp - s.unchangedErrPp, 5);
    }
  });
});

/* ──────────────────────────────── arm 3 ──────────────────────────────── */

describe("the gap cell is the magnitude, not something else", () => {
  test("it equals |gap| at display precision", () => {
    for (const s of SPECS) {
      const expected = `${Math.abs(s.movedErrPp - s.unchangedErrPp).toFixed(1)}pp`;
      expect(byBucket.get(s.idx)!.cells[3]).toBe(expected);
    }
  });

  test("it is not one of the two errors it was built from", () => {
    // The mutation that renders `moved.errorPp` unsigned reads plausibly and is
    // wrong in every row; these three specs make it wrong by a visible margin.
    for (const s of SPECS) {
      const cell = byBucket.get(s.idx)!.cells[3];
      expect(cell).not.toBe(`${Math.abs(s.movedErrPp).toFixed(1)}pp`);
      expect(cell).not.toBe(`${Math.abs(s.unchangedErrPp).toFixed(1)}pp`);
    }
  });
});

/* ──────────────────────────────── arm 4 ──────────────────────────────── */

describe("the cell and the sentence beneath it print one quantity", () => {
  test("the widest row's cell is the string the sentence uses", () => {
    const magnitude = `${Math.abs(WIDEST_GAP_PP).toFixed(1)}pp`;
    expect(byBucket.get(WIDEST.idx)!.cells[3]).toBe(magnitude);
    // `compareMatchedBuckets` writes "— a 4.5pp difference on N outcomes."
    expect(COMPARISON.sentence).toContain(`${magnitude} difference`);
    expect(HTML).toContain(`${magnitude} difference`);
  });

  test("the sentence is describing the row the table highlights", () => {
    expect(COMPARISON.widest!.bucketIdx).toBe(WIDEST.idx);
    expect(HTML).toContain(`data-widest-bucket="${WIDEST.idx}"`);
  });

  test("the 'within Npp' finding is now checkable against the column as printed", () => {
    // The claim is about |gap|. With signs in the cells a reader had to abs ten
    // rows by hand to verify it; unsigned, the column IS the quantity claimed.
    const close = COMPARISON.rows.filter(
      r => r.comparable && Math.abs(r.gapPp as number) <= 2
    );
    expect(COMPARISON.closeCount).toBe(close.length);
    for (const r of close) {
      expect(byBucket.get(r.bucketIdx)!.cells[3]).toBe(
        `${Math.abs(r.gapPp as number).toFixed(1)}pp`
      );
    }
  });
});

/* ──────────────────────────────── arm 6 ──────────────────────────────── */

describe("the fold says what the third column is", () => {
  const NAMING = "Difference is the two subtracted";

  test("it names the column as the gap between the two errors", () => {
    expect(HTML).toContain(NAMING);
  });

  test("it is inside a disclosure, not in the body", () => {
    // Notice 34 / D102: a method note folds. The reader sees the number.
    const at = HTML.indexOf(NAMING);
    expect(at).toBeGreaterThan(-1);
    const open = HTML.lastIndexOf("<details", at);
    expect(open).toBeGreaterThan(-1);
    expect(HTML.slice(open, at)).not.toContain("</details>");
  });

  test("it is in the fold that already decodes the columns", () => {
    const at = HTML.indexOf(NAMING);
    const open = HTML.lastIndexOf("<details", at);
    expect(HTML.slice(open, at)).toContain("Reading this table");
  });
});
