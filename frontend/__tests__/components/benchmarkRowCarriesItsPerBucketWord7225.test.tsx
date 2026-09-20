/**
 * #7225 — the "How We Compare" row says WHICH average it is, next to the number.
 *
 * Shopped on production at 390px, 2026-09-19 13:05Z. Two figures, ~1,200px
 * apart, both correct, both labelled, and a reader had nothing to tell them
 * apart with:
 *
 *     Across every traded market we track, prices land within about
 *     0.9 percentage points of what actually happened.
 *     HOW FAR OFF, ON AVERAGE — 0.9pp                        <- hero, n-weighted ECE
 *
 *     … 1,200px of page …
 *
 *     Bain Luck (all sources) [TRADED]   1.0pp (95% CI: 0.3-1.2pp) | 449,027 outcomes
 *                                        ^^^^^                 <- unweighted per-bucket mean
 *
 * They agree on every property a reader uses to separate two statistics — same
 * cohort word ("traded"), same denominator (449,027 outcomes, printed on both
 * the RESOLVED OUTCOMES card and this row), same unit, same green bold — and
 * disagree only on the digit. The single distinguishing word, "per-bucket",
 * lived in a grey subtitle above the list, which is not where the reader meets
 * the number.
 *
 * Both are right: 0.9 is `ece()`, n-weighted, recomputed as 0.917 from the
 * Calibration Table's ten rows; 1.0 is `mce()`, the ten buckets averaged with
 * EQUAL weight — the same value the Source Comparison table prints in its
 * `Bucket` column. So the fix is label-only and no number moves.
 *
 * ═══ WHY "per-bucket" AND NOT A NEW WORD (D102 / notice 34) ═══
 *
 * It is the page's own existing vocabulary in two places already: "show the
 * math" reads "Per-bucket error, the ten buckets averaged with equal weight",
 * and #7174 renamed this statistic's column header from "MCE" to "Bucket" for
 * exactly this class of defect — a mean labelled as something it is not. This
 * reuses that word rather than coining one.
 *
 * ═══ WHY THE FIXTURE LOOKS LIKE THIS ═══
 *
 * The guard is vacuous unless the two statistics DISAGREE. A fixture with
 * equal-sized buckets makes `ece()` and `mce()` identical, the page prints one
 * number twice, and every assertion below passes against the bug. So the
 * fixture is built to separate them the way production does — one large bucket
 * with a small error, one small bucket with a large one:
 *
 *     bucket    n          error     ECE contribution
 *     0-10%     400,000     0.5pp    n-weighted
 *     10-20%     40,000     3.0pp    equal-weighted
 *     ECE = (400000x0.5 + 40000x3.0) / 440000 = 0.727  -> "0.7pp"
 *     MCE = (0.5 + 3.0) / 2          = 1.75            -> "1.8pp"
 *
 * Both render in the confusable `N.Npp` shape, which the harness asserts before
 * anything else, so the separation cannot silently disappear.
 *
 * ═══ THE WORD IS PINNED INSIDE THE NUMBER'S OWN NOWRAP TOKEN ═══
 *
 * Not decoration. CAL-P1261's after-LOOK found this row's figures wrapping
 * mid-number at 390px, which is why each figure is its own `whitespace-nowrap`
 * span. A qualifier that wraps onto the line below has stopped qualifying the
 * number — the reader is back to a bare "1.8pp" — so `theNumberToken()` below
 * reads the nowrap span as a unit and requires both halves inside it. Placing
 * `per-bucket` as a sibling fragment (the shape the CI clause uses) passes a
 * naive `toContain` and fails here, deliberately.
 *
 * ═══ AND ONLY OUR ROW ═══
 *
 * Metaculus, the IEM paper and the Arrow consensus range are someone else's
 * published figures; we do not know how they were averaged. Labelling them
 * "per-bucket" would publish a claim about another party's method, which is the
 * rule CAL-P1261 established for this exact list when it stopped colour-grading
 * them on our thresholds.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";

// The page is a `"use client"` component behind SWR. Mock the hook, not the
// fetcher: `renderToStaticMarkup` never runs an effect, so a real SWR hands the
// page `undefined` and the suite photographs the loading state instead. (#6265)
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

jest.mock("@/components/CalibrationChart", () => ({ __esModule: true, default: () => null }));

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

/** What the two statistics come out at, given the buckets below. */
const HERO_ECE_TEXT = "0.7pp";
const BENCHMARK_MCE_TEXT = "1.8pp";

/** One wire bucket. `error` falls out of `winners/n - sum_prob/n`. */
function bucket(idx: number, priceMoved: boolean, n: number, avgProb: number, actual: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category: "baseball",
    price_moved: priceMoved,
    n,
    winners: Math.round(actual * n),
    avg_prob: avgProb,
    sum_prob: avgProb * n,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

const TRADED = [
  // big bucket, small error: 0.055 - 0.050 = +0.5pp on 400,000 outcomes
  bucket(0, true, 400_000, 0.05, 0.055),
  // small bucket, large error: 0.180 - 0.150 = +3.0pp on 40,000 outcomes
  bucket(1, true, 40_000, 0.15, 0.18),
];

// An untraded population, so the default (TRADED) cohort is a real filter and
// the row's cohort tag has something to mean.
const UNTRADED = [
  bucket(0, false, 90_000, 0.05, 0.06),
  bucket(1, false, 10_000, 0.15, 0.17),
];

function makePayload(): CalibrationData {
  const buckets = [...TRADED, ...UNTRADED];
  const total = buckets.reduce((s, b) => s + b.n, 0);
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: total,
    total_winners: buckets.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.3,
    mce_ci_upper: 1.2,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: total }],
    by_category: [{ category: "baseball", ece: 0.02, n: total }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/* ─────────────────────────── reading the page ─────────────────────────── */

const ROW_RE = /<div data-testid="calibration-benchmark-row"[^>]*>/g;

/** Every benchmark row's own HTML, sliced at the NEXT row (or the section end). */
function benchmarkRows(html: string): { highlighted: boolean; html: string }[] {
  const starts: { at: number; highlighted: boolean }[] = [];
  ROW_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = ROW_RE.exec(html)) !== null) {
    starts.push({ at: m.index, highlighted: /data-benchmark-highlight="1"/.test(m[0]) });
  }
  return starts.map((s, i) => ({
    highlighted: s.highlighted,
    html: html.slice(s.at, i + 1 < starts.length ? starts[i + 1].at : s.at + 4000),
  }));
}

/** The entities `renderToStaticMarkup` emits, in ONE table. */
const ENTITIES: Readonly<Record<string, string>> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&nbsp;": " ",
};

/**
 * Visible text of a markup fragment: tags dropped, entities decoded, whitespace
 * collapsed.
 *
 * Written as a SCAN and a single-pass decode on purpose, and the first draft of
 * this file was neither — it was `.replace(/<[^>]*>/g, "")` followed by four
 * more `.replace` calls, which CodeQL correctly failed the PR for with two HIGH
 * alerts (`js/incomplete-multi-character-sanitization`, `js/double-escaping`).
 * Both are real, not test-only excuses: a one-pass `<...>` delete is an HTML
 * sanitizer's exact shape and is wrong on nested angle brackets, and decoding
 * `&amp;` in its own pass means an earlier pass's output can be re-read by a
 * later one. The scan cannot mis-handle a nested bracket, and the decode is one
 * regex over one table, so no replacement's output is ever re-processed.
 */
function text(fragment: string): string {
  let out = "";
  let inTag = false;
  for (const ch of fragment) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out
    .replace(/&(?:amp|lt|gt|quot|nbsp|#x27|#39);/g, m => ENTITIES[m])
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The text of the element carrying `data-testid`, read off the element itself.
 * A window sliced around a phrase is not usable here: the hero's sentence is
 * broken by a `<strong>`, so the phrase a reader sees does not exist as a
 * substring of the markup.
 */
function elementText(html: string, testId: string): string {
  const at = html.indexOf(`data-testid="${testId}"`);
  expect(at).toBeGreaterThan(-1);
  const open = html.indexOf(">", at);
  const close = html.indexOf("</", open);
  expect(close).toBeGreaterThan(open);
  // Walk to this element's own closing tag, not the first `</` inside it.
  let depth = 1;
  let i = open + 1;
  const tag = /<(\/?)(?:div|p|span|strong|em|a)\b[^>]*?(\/?)>/g;
  tag.lastIndex = i;
  let t: RegExpExecArray | null;
  let end = -1;
  while ((t = tag.exec(html)) !== null) {
    if (t[2] === "/") continue; // self-closing
    depth += t[1] === "/" ? -1 : 1;
    if (depth === 0) {
      end = t.index;
      break;
    }
  }
  expect(end).toBeGreaterThan(open);
  return text(html.slice(open + 1, end));
}

/**
 * The text of a row's FIRST `whitespace-nowrap` span, read as one unbreakable
 * unit — nested spans walked, so a qualifier placed inside the token is part of
 * it and a qualifier placed after the token is not.
 */
function theNumberToken(rowHtml: string): string {
  const opener = '<span class="whitespace-nowrap">';
  const at = rowHtml.indexOf(opener);
  expect(at).toBeGreaterThan(-1);
  let depth = 0;
  let i = at;
  let end = -1;
  const tag = /<(\/?)span\b[^>]*>/g;
  tag.lastIndex = at;
  let t: RegExpExecArray | null;
  while ((t = tag.exec(rowHtml)) !== null) {
    depth += t[1] === "/" ? -1 : 1;
    if (depth === 0) {
      end = t.index + t[0].length;
      break;
    }
    i = t.index;
  }
  expect(end).toBeGreaterThan(at);
  void i;
  return text(rowHtml.slice(at, end));
}

/* ═══════════ the harness proves itself, and proves the fixture bites ═══════════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: the page is built, not a loading shell", () => {
    // Every assertion below is satisfied by an empty string or a spinner.
    const html = render();
    expect(html).toContain("How We Compare");
    expect(html).toContain("Metaculus");
    expect(benchmarkRows(html).length).toBe(4);
  });

  test("exactly one benchmark row is ours", () => {
    const rows = benchmarkRows(render());
    expect(rows.filter(r => r.highlighted).length).toBe(1);
    expect(rows.filter(r => !r.highlighted).length).toBe(3);
  });

  test("the fixture makes the two statistics DISAGREE, in the confusable shape", () => {
    // Without this the page prints one number twice and the ship is untestable.
    const html = render();
    expect(HERO_ECE_TEXT).not.toBe(BENCHMARK_MCE_TEXT);
    for (const t of [HERO_ECE_TEXT, BENCHMARK_MCE_TEXT]) expect(t).toMatch(/^\d\.\dpp$/);
    // …and both are really on the page, so the pair above is not an assumption.
    expect(html).toContain(`data-plain-ece="${parseFloat(HERO_ECE_TEXT)}`);
    const ours = benchmarkRows(html).find(r => r.highlighted)!;
    expect(theNumberToken(ours.html)).toContain(BENCHMARK_MCE_TEXT);
  });

  test("the two figures still share the properties that made them confusable", () => {
    // The fix is label-only. If a later change separates them by cohort word or
    // denominator instead, this guard is testing a page that no longer exists.
    const html = render();
    const ours = benchmarkRows(html).find(r => r.highlighted)!;
    expect(text(ours.html)).toContain("Bain Luck (all sources)");
    // Same cohort word on both, which is half of why they read as one quantity.
    expect(elementText(html, "calibration-plain-headline")).toContain("traded");
    expect(text(ours.html)).toContain("Traded");
    // Same unit, same rendering, on both.
    expect(elementText(html, "calibration-stat-ece-value")).toBe(HERO_ECE_TEXT);
  });
});

/* ════════════ SHIP — the distinguishing word travels with the number ════════════ */

describe("#7225 — our benchmark row names which average it is", () => {
  test("the word is there, and it is the page's own word", () => {
    const ours = benchmarkRows(render()).find(r => r.highlighted)!;
    expect(text(ours.html)).toContain("per-bucket");
  });

  test("it sits INSIDE the number's unbreakable token, not beside it", () => {
    // A qualifier that can wrap to the next line leaves a bare "1.8pp" on the
    // reader's line, which is the defect. `theNumberToken` walks the nested
    // span, so a sibling fragment fails here while passing a naive `toContain`.
    const ours = benchmarkRows(render()).find(r => r.highlighted)!;
    expect(theNumberToken(ours.html)).toBe(`${BENCHMARK_MCE_TEXT} per-bucket`);
  });

  test("no number moved — it is a label change", () => {
    const html = render();
    const ours = benchmarkRows(html).find(r => r.highlighted)!;
    // Our row still prints the per-bucket mean and its population.
    expect(text(ours.html)).toContain(BENCHMARK_MCE_TEXT);
    expect(text(ours.html)).toContain("440,000 outcomes");
    // The hero is untouched: still the n-weighted figure, still unqualified.
    expect(html).toContain(`data-plain-ece="${parseFloat(HERO_ECE_TEXT)}`);
  });

  test("#7374 — and the row carries no interval to be confused with", () => {
    // This assertion used to read `toContain("95% CI: 0.3-1.2pp")`, and that
    // interval was the other half of the confusion #7225 is about: it is
    // bootstrapped n-weighted (`_bootstrap_mce_ci`, "n-weighted to match the
    // #137 weighted point estimate"), so it is an interval on the HERO's
    // statistic, and it sat inside this row's value span qualifying the
    // equal-weighted one. It is also a single payload scalar over the full
    // population, and this fixture's row is a 440,000-outcome traded cohort.
    // Both reasons point the same way: not here.
    const ours = benchmarkRows(render()).find(r => r.highlighted)!;
    expect(text(ours.html)).not.toContain("95% CI");
  });

  test("the three published benchmarks make no claim about their own method", () => {
    // We cannot say how Metaculus or a 2008 paper averaged; saying "per-bucket"
    // over their numbers is the claim CAL-P1261 removed from this list.
    for (const row of benchmarkRows(render()).filter(r => !r.highlighted)) {
      expect(text(row.html)).not.toContain("per-bucket");
    }
  });

  test("the hero does not grow the qualifier instead", () => {
    // The symmetrical wrong fix: label the hero rather than the row. The hero is
    // page-one copy for a casual reader and D102 keeps jargon out of it.
    const html = render();
    for (const id of [
      "calibration-plain-headline",
      "calibration-stat-ece-value",
      "calibration-stat-ece-detail",
    ]) {
      expect(elementText(html, id)).not.toContain("per-bucket");
    }
  });
});
