/**
 * #7892 — the niche card's held-back categories become reachable.
 *
 * Seen on production https://bainluck.com/calibration at 390px, 2026-09-21
 * 23:07Z. The card "What About Niche & Long-Shot Markets?" carried
 * `data-parked-count="42"`, rendered eight chips under CLOSEST TO THE BAR —
 *
 *     NCAA Lacrosse 829 · Chess 809 · PLL 530 · Rugby 344
 *     Boxing 283 · Lacrosse 268 · Pickleball 188 · Uncategorized 113
 *
 * — and then, in the same chip row, the text `+34 more`.
 *
 * `+34 more` was a bare `<span class="text-xs px-2.5 py-1 text-text-muted">`.
 * Not a link, not a button, not a `<summary>`; no `cursor-pointer`. A probe
 * clicked it on production and re-read the DOM: unchanged, chip count still 8.
 *
 * So the card named a quantity of withheld categories and gave the reader no
 * way to reach them. THE THIRTY-FOUR NAMES REACHED NO SCREEN — not in this
 * card, not elsewhere on the page. 8 + 34 = 42, so the arithmetic was honest;
 * the promise was the thing that was dead.
 *
 * ═══ WHY THIS IS THE PAGE'S OWN IDIOM, NOT A NEW ONE ═══
 *
 * ~600 lines below in the same file, under notice 34 / D102 ("present,
 * openable, no real estate when closed"), the exclusions list renders
 * "Other exclusion rules (N more)" as a `<summary className="cursor-pointer">`
 * inside a `<details>`. Same promise, kept. The niche chips were the one place
 * that made it and didn't.
 *
 * ═══ WHY THE FIXTURE IS SHAPED LIKE THIS ═══
 *
 * ELEVEN parked categories, all genuinely below the 1,000 bar, none of them
 * inside a published parent. Eleven and not two because the remainder only
 * exists above eight: a fixture with `parked <= 8` renders no fold at all and
 * every assertion below would pass on the broken code as vacuously as on the
 * fix. The split is 8 visible + 3 folded.
 *
 * `football` is published (30,000) so the page renders its normal furniture and
 * a fix that deletes the card, or one that empties the breakdown table, cannot
 * pass by making the chips vanish.
 *
 * ═══ WHAT THESE TESTS PIN ═══
 *
 * Read FROM THE RENDERED MARKUP, never recomputed from the page's own helpers —
 * a guard that re-derives `thin.slice(8)` here would agree with the page by
 * construction and go quiet exactly when the slice regresses. The expected
 * remainder count is this file's own literal (11 - 8 = 3).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import path from "path";
import type { CalibrationData } from "@/lib/api";
import { normalizeCat } from "@/lib/calibrationCategories";

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

jest.mock("@/components/CalibrationChart", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/** One published category, so the page renders its normal furniture. */
const PUBLISHED_KEY = { category: "americanfootball_nfl", n: 30_000 };

/**
 * Eleven parked raw keys, outcomes strictly descending so the visible/folded
 * split is unambiguous and order-checkable by eye.
 */
const PARKED_RAW = [
  { category: "lacrosse_ncaa", outcomes: 990 },
  { category: "chess", outcomes: 900 },
  { category: "pll", outcomes: 830 },
  { category: "rugby", outcomes: 740 },
  { category: "boxing", outcomes: 650 },
  { category: "lacrosse", outcomes: 560 },
  { category: "pickleball", outcomes: 470 },
  { category: "darts", outcomes: 380 },
  // --- the fold starts here: everything below is the tail the card withheld ---
  { category: "snooker", outcomes: 290 },
  { category: "sailing", outcomes: 200 },
  { category: "uncategorized", outcomes: 110 },
].map(c => ({ ...c, ece: 5.0, disposition: "parked_below_publish_bar", publish_bar: 1000 }));

const VISIBLE_EXPECTED = PARKED_RAW.slice(0, 8).map(c => c.category);
const FOLDED_EXPECTED = PARKED_RAW.slice(8).map(c => c.category);

function bucket(category: string, idx: number, n: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category,
    price_moved: true,
    n,
    winners: Math.round(n * (0.05 + idx * 0.1)),
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: n * (0.05 + idx * 0.1),
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(): CalibrationData {
  const keys = [PUBLISHED_KEY, ...PARKED_RAW.map(c => ({ category: c.category, n: c.outcomes }))];
  const buckets = keys.flatMap(k => [0, 1, 2, 3, 4].map(i => bucket(k.category, i, k.n / 5)));
  return {
    buckets,
    min_category_outcomes: 1000,
    small_sample_categories: PARKED_RAW,
    total_markets: 5_000,
    total_outcomes: keys.reduce((t, k) => t + k.n, 0),
    total_winners: 20_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-21T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-21" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: [],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** The niche card's own markup, so nothing below reads another section. */
function nicheSection(html: string): string {
  const start = html.indexOf('data-testid="calibration-niche-section"');
  expect(start).toBeGreaterThan(-1);
  return html.slice(start, start + 20_000);
}

/** Every `data-category` carried by a given testid, in render order. */
function categoriesFor(html: string, testid: string): string[] {
  const re = new RegExp(`data-testid="${testid}"[^>]*?data-category="([^"]*)"`, "g");
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out;
}

/**
 * Visible text of a markup fragment: tags dropped, whitespace collapsed.
 *
 * A SCAN, not `.replace(/<[^>]*>/g, "")`. That one-liner is an HTML sanitizer's
 * exact shape, is wrong on nested angle brackets, and CodeQL fails the PR for it
 * with a HIGH `js/incomplete-multi-character-sanitization` — which it did to the
 * first draft of this file, at the summary line below. Being a test is not an
 * exemption. The canonical version, with the full reasoning, is `text()` in
 * `benchmarkRowCarriesItsPerBucketWord7225.test.tsx`.
 *
 * No entity table: the only entity in the markup this file reads is the caret
 * `&#9662;`, which is decoration the callers strip by name anyway, and the chip
 * labels are words and digits.
 */
function visibleText(fragment: string): string {
  let out = "";
  let inTag = false;
  for (const ch of fragment) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.replace(/\s+/g, " ").trim();
}

/** The `<details>` holding the tail, sliced out of the card. */
function foldMarkup(html: string): string {
  const sec = nicheSection(html);
  const i = sec.indexOf('data-testid="calibration-parked-rest"');
  expect(i).toBeGreaterThan(-1);
  const open = sec.lastIndexOf("<details", i);
  const close = sec.indexOf("</details>", i);
  expect(open).toBeGreaterThan(-1);
  expect(close).toBeGreaterThan(-1);
  return sec.slice(open, close);
}

describe("#7892 the niche card's remainder is reachable", () => {
  test("the fixture reproduces the shape, or nothing below proves anything", () => {
    // More parked than the card shows: without this there is no remainder and
    // every assertion in this file is vacuous.
    expect(PARKED_RAW.length).toBeGreaterThan(8);
    expect(FOLDED_EXPECTED).toHaveLength(3);

    // Eleven DISTINCT normalized categories. If a future SPORT_KEY_MAP entry
    // folds two of these together the split stops being 8/3 and this fails
    // loudly, rather than the guards below quietly checking a shorter list.
    const normalized = new Set(PARKED_RAW.map(c => normalizeCat(c.category)));
    expect(normalized.size).toBe(11);

    // ...and none of them is the published one.
    expect(normalized.has(normalizeCat(PUBLISHED_KEY.category))).toBe(false);

    const html = render();
    expect(nicheSection(html)).toContain('data-parked-count="11"');
  });

  test("every parked category reaches the DOM — none is counted and withheld", () => {
    const html = render();
    const rendered = categoriesFor(nicheSection(html), "calibration-parked-category");
    // The defect in one line: this used to be 8 against a count of 11.
    expect(rendered).toHaveLength(PARKED_RAW.length);
    expect(new Set(rendered)).toEqual(new Set(PARKED_RAW.map(c => c.category)));
  });

  test("the eight closest to the bar stay visible, in order, outside the fold", () => {
    const html = render();
    const sec = nicheSection(html);
    const fold = foldMarkup(html);
    const visible = categoriesFor(sec.replace(fold, ""), "calibration-parked-category");
    // Sorted by outcomes descending, so CLOSEST TO THE BAR still means it.
    expect(visible).toEqual(VISIBLE_EXPECTED);
  });

  test("the other three are inside the fold, in the same order", () => {
    const html = render();
    expect(categoriesFor(foldMarkup(html), "calibration-parked-category")).toEqual(FOLDED_EXPECTED);
  });

  test("the fold is a real affordance, not a styled span", () => {
    const html = render();
    const fold = foldMarkup(html);
    // A <details>/<summary> the browser opens on its own, and a cursor that
    // says so. The defect was precisely an element that looked tappable and
    // was inert, so "it is openable" is the assertion, not "it exists".
    expect(fold).toMatch(/^<details/);
    expect(fold).toContain("<summary");
    expect(fold).toContain("cursor-pointer");
  });

  test("the summary names the remainder, and the number is the withheld count", () => {
    const html = render();
    const fold = foldMarkup(html);
    const summary = /<summary[^>]*>([\s\S]*?)<\/summary>/.exec(fold);
    expect(summary).not.toBeNull();
    const text = visibleText(summary![1])
      .replace(/&#x?[0-9a-f]+;|[▾▴▼▲]/gi, "") // the aria-hidden caret
      .replace(/\s+/g, " ")
      .trim();
    // 11 parked - 8 shown. This file's own arithmetic, not the page's.
    expect(text).toBe("The other 3");
  });

  test("the disclosure matches the card's other fold, caret and all", () => {
    const html = render();
    const fold = foldMarkup(html);
    // `list-none` + the rotating caret is `CalibrationCardNote`'s idiom, and
    // this card renders one of those two lines above. Without this the reader
    // gets the browser's default triangle beside a styled caret in one card.
    expect(fold).toContain("list-none");
    expect(fold).toContain("group-open:rotate-180");
    expect(fold).toMatch(/<details[^>]*class="[^"]*\bgroup\b/);
    // The caret is decoration; a screen reader gets the <summary> text.
    expect(fold).toContain('aria-hidden="true"');
  });

  test("the dead `+N more` span is gone from the card", () => {
    const html = render();
    const sec = nicheSection(html);
    const text = visibleText(sec);
    // The exact shape measured on production, and its unsigned sibling.
    expect(text).not.toMatch(/\+\s*\d[\d,]*\s+more/);
    expect(text).not.toMatch(/\bcursor-default\b/);
  });

  test("the fold costs no vertical space until it is opened", () => {
    const html = render();
    // `open` would defeat the point: notice 34 / D102 is "no real estate when
    // closed", and 34 chips unfurled by default is the wall Alex called madness.
    expect(foldMarkup(html)).not.toMatch(/<details[^>]*\sopen(\s|>|=)/);
  });

  test("the card's headline count and sentence are untouched", () => {
    const html = render();
    const sec = nicheSection(html);
    // The fix moves no number. 11 categories, and the outcome total in the fold
    // is still every parked outcome, visible and folded alike.
    expect(sec).toContain('data-parked-count="11"');
    expect(sec).toContain('<strong class="text-text-primary">11</strong>');
    const total = PARKED_RAW.reduce((t, c) => t + c.outcomes, 0);
    expect(sec).toContain(`${total.toLocaleString()} outcomes and counting`);
  });

  test("the chip hook is still declared exactly once in the source", () => {
    // Both call sites share one renderer ON PURPOSE.
    // `calibrationAuditHooks.test.tsx` counts this literal in the SOURCE and
    // requires exactly one — it is a COLLECTION hook, one `.map()` and many DOM
    // nodes. Inlining the chip a second time for the fold would redden that
    // guard for a reason unrelated to what it guards, so it is pinned here too,
    // beside the change that would be tempted to break it.
    const src = readFileSync(
      path.join(process.cwd(), "app/calibration/page.tsx"),
      "utf8",
    );
    const hits = src.split('data-testid="calibration-parked-category"').length - 1;
    expect(hits).toBe(1);
  });
});
