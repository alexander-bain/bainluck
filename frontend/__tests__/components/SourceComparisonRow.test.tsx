// UX-P128 — the n=0 RENDER, asserted against the HTML a reader would receive.
//
// `calibrationAuditHooks.test.tsx` asserts the calibration page at SOURCE level
// and gives its reason: the page is a 2,000-line client component behind SWR,
// so "rendering it would prove less and break more". That holds for the page.
// It does not hold for a defect in what a CELL PRINTS — a grep cannot tell you
// that `(0).toFixed(1)` reached the DOM as "0.0pp". So the cells were extracted
// into `components/SourceComparisonRow.tsx` and are mounted here, on the same
// `renderToStaticMarkup` rail every other component suite in this repo uses.
//
// THE SPECIMEN IS PRODUCTION'S. `GET /api/calibration`, 2026-08-24: `datagolf`
// publishes 171 outcomes across 9 buckets at a server ECE of 11.88pp — the
// WORST-calibrated source on the page — and all 9 bucket rows carry
// `price_moved: false`, so the default cohort (`price_moved !== false`) empties
// it. What the page rendered for it was `0 | 0.0pp | 0.0pp | 0.0000`, coloured
// green, sorted into FIRST place under a subhead reading "sorted by ECE …
// Lower is better."

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import SourceComparisonRow from "../../components/SourceComparisonRow";
import { orderSourceRows, type SourceRowInput } from "../../lib/calibrationSourceRows";

const TOGGLE = "Include never-moved outcomes";
const label = (s: string) => s;

/** datagolf, exactly as `providerMetrics` hands it over on the live payload. */
const EMPTY_INPUT: SourceRowInput = {
  provider: "datagolf",
  label: "DataGolf",
  sources: ["datagolf"],
  n: 0,
  ece: 0,
  mce: 0,
  brier: 0,
};

const KALSHI_INPUT: SourceRowInput = {
  provider: "kalshi",
  label: "Kalshi",
  sources: ["kalshi"],
  n: 287922,
  ece: 1.25,
  mce: 1.25,
  brier: 0.1712,
};

const SPORTSBOOKS_INPUT: SourceRowInput = {
  provider: "odds_api_family",
  label: "Sportsbooks (Odds API)",
  sources: ["odds_api", "odds_api_bookmaker", "odds_api_spreads", "odds_api_totals"],
  n: 136173,
  ece: 1.4,
  mce: 1.4,
  brier: 0.2011,
};

/** Render one or more inputs through the real ordering, as the table does. */
function renderRows(...inputs: SourceRowInput[]): string {
  const rows = orderSourceRows(inputs);
  return renderToStaticMarkup(
    <table>
      <tbody>
        {rows.map(r => (
          <SourceComparisonRow key={r.provider} row={r} sourceLabel={label} toggleLabel={TOGGLE} />
        ))}
      </tbody>
    </table>
  );
}

/** The visible text, tags stripped — what a reader actually reads. */
function textOf(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&mdash;/g, "—")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

describe("SourceComparisonRow — a source with no outcomes in the cohort", () => {
  const html = renderRows(EMPTY_INPUT);
  const text = textOf(html);

  test("prints no fabricated numbers at all", () => {
    // THE BUG, pinned as text. Every one of these was on the live page.
    expect(text).not.toContain("0.0pp");
    expect(text).not.toContain("0.0000");
    expect(text).not.toMatch(/\b0 outcomes\b/);
    // No bare zero survives anywhere in the row.
    expect(text).not.toMatch(/(^|\s)0(\s|$)/);
  });

  test("says so explicitly instead of leaving a blank", () => {
    expect(text).toContain("No outcomes in this cohort");
    expect(text).toContain("not measured, not ranked");
  });

  test("names the control that recovers the data", () => {
    // An absence a reader cannot act on is just a smaller mystery. The remedy
    // is the REAL toggle label, threaded from `describeCohort`, not a literal.
    expect(text).toContain(TOGGLE);
  });

  test("still names the source — the row is present, not dropped", () => {
    expect(text).toContain("DataGolf");
    expect(html).toContain('data-provider="datagolf"');
    expect(html).toContain('data-provider-n="0"');
  });

  test("publishes its state as a data attribute the audit rail can read", () => {
    expect(html).toContain('data-row-state="no-cohort-data"');
    expect(html).toContain('data-testid="calibration-provider-no-data"');
  });

  test("carries no green treatment — 0.0 was being coloured as excellent", () => {
    expect(html).not.toContain("text-green-600");
  });

  test("spans the four number columns so the table does not shear", () => {
    expect(html).toContain('colSpan="4"');
  });
});

describe("SourceComparisonRow — a measured source is unchanged", () => {
  test("prints n, ECE, MCE and Brier exactly as before", () => {
    const text = textOf(renderRows(KALSHI_INPUT));
    expect(text).toContain("287,922");
    expect(text).toContain("1.3pp"); // 1.25 at the page's display precision
    expect(text).toContain("0.1712");
    expect(renderRows(KALSHI_INPUT)).toContain('data-row-state="measured"');
    expect(renderRows(KALSHI_INPUT)).not.toContain("calibration-provider-no-data");
  });

  test("keeps the ECE colour bands", () => {
    expect(renderRows(KALSHI_INPUT)).toContain("text-green-600");
    expect(renderRows({ ...KALSHI_INPUT, ece: 3.9 })).toContain("text-blue-600");
    // datagolf's REAL published error, once the toggle includes it.
    expect(renderRows({ ...KALSHI_INPUT, ece: 11.88 })).toContain("text-orange-600");
  });

  test("lists the pooled source keys for a multi-shape provider", () => {
    expect(textOf(renderRows(SPORTSBOOKS_INPUT))).toContain(
      "odds_api · odds_api_bookmaker · odds_api_spreads · odds_api_totals"
    );
  });

  test("renders 0.0pp when a source genuinely measured zero error", () => {
    // The distinction the whole fix rests on: 0.0 with outcomes behind it is a
    // real result and must still print, in green, in first place.
    const html = renderRows({ ...KALSHI_INPUT, provider: "oracle", label: "Oracle", ece: 0, mce: 0, brier: 0 });
    expect(html).toContain('data-row-state="measured"');
    expect(textOf(html)).toContain("0.0pp");
    expect(html).toContain("text-green-600");
  });
});

describe("SourceComparisonRow — the whole table, in order", () => {
  test("puts the unmeasured source last and never first", () => {
    const html = renderRows(EMPTY_INPUT, KALSHI_INPUT, SPORTSBOOKS_INPUT);
    const order = [...html.matchAll(/data-provider="([^"]+)"/g)].map(m => m[1]);

    // Under the old `sort((a, b) => a.ece - b.ece)` this array began "datagolf".
    const naive = [EMPTY_INPUT, KALSHI_INPUT, SPORTSBOOKS_INPUT]
      .sort((a, b) => a.ece - b.ece)
      .map(r => r.provider);
    expect(naive[0]).toBe("datagolf");

    expect(order).toEqual(["kalshi", "odds_api_family", "datagolf"]);
    expect(html.split("calibration-provider-no-data").length - 1).toBe(1);
  });
});
