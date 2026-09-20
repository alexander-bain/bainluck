/**
 * #7363 — the corrections log may not advertise a per-entry field that some of
 * its entries do not have.
 *
 * ═══ THE DEFECT ═══
 *
 * `/calibration` → "Technical: data corrections log (13)" opened with:
 *
 *   "A calibration page is only trustworthy if it fixes its own mistakes.
 *    Every data-quality correction we've made — WITH DATES AND ROWS AFFECTED —
 *    is on the record here."
 *
 * and rendered the row count behind a correct defensive guard:
 *
 *   {c.rows != null && <span>{c.rows.toLocaleString()} rows</span>}
 *
 * On the live payload (`population_version q271`, generated 2026-09-15T11:16:10Z)
 * **11 of the 13 corrections carry `rows: null`.** Only the Polymarket hockey
 * sign-flip (36,207) and the premature golf resolutions (230) have a number.
 * Every exclusion-class correction from 2026-07-09 onward has none. A reader
 * told to expect "rows affected" found the field on two entries in thirteen.
 *
 * 🔴 **THE GUARD IS NOT THE DEFECT; THE SENTENCE IS.** Inventing a number for a
 * null would be worse, and the counts in the exclusions list are a DIFFERENT
 * population — what a rule sets aside today, not what one correction changed
 * once. So the promise shrinks to the field every entry actually has (the
 * date), and the row count stays where the payload supplies one.
 *
 * ═══ WHY THIS IS A CLASS GUARD AND NOT A STRING BAN ═══
 *
 * `expect(text).not.toContain("rows affected")` would pass on the day someone
 * writes "with dates and the rows each one touched". So the assertion is the
 * PREDICATE the sentence makes, not its spelling: for every per-entry field the
 * intro names, every entry in the payload must carry that field. `PROMISES`
 * maps the phrasings that promise a field to the field they promise, and the
 * check fires on any of them — the next promise is caught by adding one line,
 * and the arithmetic (does the payload keep it?) is already written.
 *
 * ═══ WHY THE FIXTURE MIXES NULL AND NON-NULL ═══
 *
 * 🔴 `supplierWordsFromCalibrationPayloadDoNotReachRenderedPage4067`'s fixture
 * holds ONE correction and it has `rows: 1_234`. That suite asserts
 * `toContain("1,234 rows")` and its comment said the intro "keeps that
 * promise" — true of its fixture and false of production. A fixture that never
 * contains the defect is a fixture that cannot see it. This one carries both
 * shapes on purpose, and the null entry is the specimen.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import CalibrationPage from "@/app/calibration/page";
import type { CalibrationData } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: (global as unknown as { __calPayload: CalibrationData }).__calPayload }),
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

/** Attributes are not copy — dropping each tag whole takes them with it. */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// ---------------------------------------------------------------------------
// THE PRODUCTION SPECIMENS, verbatim from /api/calibration on 2026-09-19
// (`population_version q271`). Two entries with a row count and two without —
// the live list's exact shape, at four thirteenths of its length.
// ---------------------------------------------------------------------------
const CORRECTIONS = [
  { date: "2026-07-09", title: "Polymarket hockey sign-flip", rows: 36_207, description: "" },
  { date: "2026-07-08", title: "Premature golf resolutions", rows: 230, description: "" },
  { date: "2026-07-09", title: "DataGolf survivorship exclusion", rows: null, description: "" },
  {
    date: "2026-09-13",
    title: "The one-question markets we were throwing away are now scored",
    rows: null,
    description: "",
  },
];

/**
 * Each phrasing that promises a per-entry field, and the field it promises.
 *
 * The keys are read against the whole rendered page rather than against the
 * intro paragraph alone. That is deliberate and it is safe in the only
 * direction that matters: a promise moved into the section heading, a tooltip
 * or a caption is still a promise, and none of these phrasings has any other
 * home on this page.
 */
const PROMISES: ReadonlyArray<{ phrase: RegExp; field: "rows" | "date"; label: string }> = [
  { phrase: /rows affected/i, field: "rows", label: '"rows affected"' },
  { phrase: /rows each one (?:touched|changed)/i, field: "rows", label: '"rows each one touched"' },
  { phrase: /how many rows/i, field: "rows", label: '"how many rows"' },
  { phrase: /with dates/i, field: "date", label: '"with dates"' },
];

/**
 * The whole ship as one function: which promises does this text make that this
 * payload cannot keep? Returns a human-readable list, empty when honest.
 *
 * Exported through the test body rather than a helper module because it is the
 * assertion, and a predicate that lives beside its own mutation arm cannot
 * quietly stop being applied.
 */
function brokenPromises(text: string, corrections: typeof CORRECTIONS): string[] {
  return PROMISES.filter(p => p.phrase.test(text))
    .map(p => {
      const missing = corrections.filter(
        c => (c as Record<string, unknown>)[p.field] == null,
      ).length;
      return missing > 0
        ? `${p.label} is promised, but ${missing} of ${corrections.length} entries carry no \`${p.field}\``
        : null;
    })
    .filter((x): x is string => x !== null);
}

/**
 * The corrections log's own visible text, cut out of the page.
 *
 * Cut from the `data-testid` to the end of that `<section>`'s markup by brace
 * counting on `<section`/`</section`, so it cannot silently widen into the
 * Further Reading card below it and start finding strings that belong to
 * someone else. Throws rather than returning "" when the section is absent —
 * an empty haystack passes every `not.toContain` ever written.
 */
function correctionsSection(html: string): string {
  const start = html.indexOf('data-testid="calibration-corrections"');
  if (start < 0) throw new Error("the corrections log did not render");
  const open = html.lastIndexOf("<section", start);
  let depth = 0;
  let i = open;
  for (;;) {
    const nextOpen = html.indexOf("<section", i + 1);
    const nextClose = html.indexOf("</section", i + 1);
    if (nextClose < 0) throw new Error("unterminated <section> around the corrections log");
    if (nextOpen >= 0 && nextOpen < nextClose) {
      depth += 1;
      i = nextOpen;
      continue;
    }
    if (depth === 0) return visibleText(html.slice(open, nextClose));
    depth -= 1;
    i = nextClose;
  }
}

function bucket(source: string, idx: number) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: true,
    n: 400,
    winners: 200,
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: 400 * (0.05 + idx * 0.1),
    sum_sq_err: 40,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(corrections: unknown[] = CORRECTIONS): CalibrationData {
  const sources = ["kalshi", "polymarket", "odds_api"];
  return {
    buckets: sources.flatMap(s => [0, 1, 2, 3, 4].map(i => bucket(s, i))),
    total_markets: 12_000,
    total_outcomes: 48_000,
    total_winners: 24_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T23:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: sources.map(source => ({ source, ece: 0.02, mce: 0.05, n: 2_000 })),
    source_labels: {},
    by_category: [{ category: "baseball", ece: 0.02, n: 4_000 }],
    corrections,
    liquidity_filter: {
      applies_to: "kalshi",
      rule: "",
      kalshi_included: 9_000,
      kalshi_excluded: 1_000,
    },
  } as unknown as CalibrationData;
}

function renderPage(corrections: unknown[] = CORRECTIONS): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(corrections);
  return renderToStaticMarkup(<CalibrationPage />);
}

describe("#7363 — the corrections log promises only what every entry carries", () => {
  it("renders the corrections log it is claiming about", () => {
    // THE ANTI-VACUOUS ARM. The load-bearing assertion below is that a phrase is
    // ABSENT, and an absence is free on a section that did not render. The
    // heading, the count and both entry titles prove there is a log here.
    const html = renderPage();
    const text = visibleText(html);
    expect(text).toContain("Technical: data corrections log");
    expect(text).toContain("(4)");
    expect(text).toContain("Polymarket hockey sign-flip");
    expect(text).toContain("DataGolf survivorship exclusion");
    expect(html).toContain('data-testid="calibration-corrections"');
  });

  it("makes no promise about a field that some entry does not carry", () => {
    // THE SHIP. On this fixture — two entries with `rows`, two without — any
    // wording that advertises a row count is a promise the payload breaks.
    expect(brokenPromises(visibleText(renderPage()), CORRECTIONS)).toEqual([]);
  });

  it("the predicate is not vacuous — the pre-fix sentence trips it", () => {
    // MUTATION ARM. `brokenPromises` returning [] is only meaningful if it can
    // return anything else. This is the exact sentence that shipped before this
    // fix, checked against the exact fixture above.
    const preFix =
      "A calibration page is only trustworthy if it fixes its own mistakes. Every " +
      "data-quality correction we've made — with dates and rows affected — is on the " +
      "record here.";
    const broken = brokenPromises(preFix, CORRECTIONS);
    expect(broken).toHaveLength(1);
    expect(broken[0]).toContain("rows affected");
    expect(broken[0]).toContain("2 of 4");

    // And the DATE half of that same sentence was always honest — so the
    // predicate is discriminating between the two clauses, not failing the
    // sentence wholesale.
    expect(PROMISES.some(p => p.field === "date" && p.phrase.test(preFix))).toBe(true);
  });

  it("still prints the row count on the entries that have one", () => {
    // The fix is a REMOVAL, so this is the arm that stops it removing too much.
    // A page that dropped the count entirely would satisfy every absence above.
    const text = visibleText(renderPage());
    expect(text).toContain("36,207 rows");
    expect(text).toContain("230 rows");
  });

  it("renders a null-rows entry as its date and title, with no empty count beside it", () => {
    // 🔴 Scoped to the log's own markup, and counted rather than substring-
    // matched. The first draft asserted `not.toContain("0 rows")` over the whole
    // page and went red on "23**0 rows**" — the real count of a real entry. A
    // digit-suffix ban is a substring collision waiting for a round number.
    const section = correctionsSection(renderPage());
    expect(section).toContain("DataGolf survivorship exclusion");
    expect(section).toContain("The one-question markets we were throwing away are now scored");

    // Exactly as many counts as the payload supplies — two, not four.
    //
    // #7599: compared as a SET, because this assertion never meant to own the
    // sequence. It was written as an ordered equality and the order it pinned
    // was the payload array's, which the page no longer renders — the log is
    // sorted by date now, so the 2026-07-08 entry's "230 rows" comes first.
    // Leaving it ordered would make this suite a second, silent owner of the
    // reading order, and the next change to that order would redden a test
    // about row-count coverage. Which rows carry a count, and how many, is this
    // file's claim; where they sit is `calibrationCorrectionsAreDateOrdered7599`.
    expect([...(section.match(/[\d,]+ rows/g) ?? [])].sort()).toEqual(
      ["36,207 rows", "230 rows"].sort(),
    );

    // And nothing stood in for the absent ones.
    expect(section).not.toContain("null");
    expect(section).not.toContain("undefined");
    expect(section).not.toContain("NaN");
  });

  it("publishes the gap as data attributes so it stays measurable without being printed", () => {
    // Notice 34's failing-self-audit remedy: the coverage count a reader must
    // not be shown is exactly the number a probe needs.
    const html = renderPage();
    expect(html).toContain('data-corrections="4"');
    expect(html).toContain('data-corrections-with-rows="2"');

    // Measured, not hardcoded: an all-null list reads 0 and an all-numbered one
    // reads its own length, which is what makes the pair a rail rather than two
    // constants that happen to match today's fixture.
    const allNull = renderPage(CORRECTIONS.map(c => ({ ...c, rows: null })));
    expect(allNull).toContain('data-corrections-with-rows="0"');
    const allRows = renderPage(CORRECTIONS.map(c => ({ ...c, rows: 7 })));
    expect(allRows).toContain('data-corrections-with-rows="4"');
  });

  it("keeps the promise honest on a list where every entry does carry a count", () => {
    // The rule is "promise what the payload keeps", not "never mention rows".
    // If the backend one day fills every `rows`, a future intro that advertises
    // them is fine — and this arm is what says so, so the guard does not
    // calcify into a permanent ban on a true sentence.
    const filled = CORRECTIONS.map(c => ({ ...c, rows: c.rows ?? 11 }));
    const preFix = "Every data-quality correction we've made — with dates and rows affected — is here.";
    expect(brokenPromises(preFix, filled as typeof CORRECTIONS)).toEqual([]);
  });
});
