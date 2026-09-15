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
  buckets: [],
};

const KALSHI_INPUT: SourceRowInput = {
  provider: "kalshi",
  label: "Kalshi",
  sources: ["kalshi"],
  n: 287922,
  ece: 1.25,
  mce: 1.25,
  brier: 0.1712,
  buckets: [{ n: 287922, winners: 107971 }],
};

const SPORTSBOOKS_INPUT: SourceRowInput = {
  provider: "odds_api_family",
  label: "Sportsbooks (Odds API)",
  sources: ["odds_api", "odds_api_bookmaker", "odds_api_spreads", "odds_api_totals"],
  n: 136173,
  ece: 1.4,
  mce: 1.4,
  brier: 0.2011,
  buckets: [{ n: 136173, winners: 75848 }],
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
  });

  // #4118 / standing notice 34. The cell used to go on: "— not measured, not
  // ranked." That is an explanation of the emptiness, and the notice's rule for
  // a number that cannot be shown honestly is to leave the space empty rather
  // than annotate it. Pinned as a ban so the clause cannot drift back in under
  // a reword, and pinned NARROWLY — the two tests either side of it already
  // hold the fact and the remedy, which is what a reader needs.
  test("does not explain the emptiness", () => {
    expect(text).not.toContain("not measured");
    expect(text).not.toContain("not ranked");
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

  // #4214's SURVIVOR — and the reason it survived is in the test above.
  //
  // `label` on this rail is the identity function, so every assertion in this
  // suite reads raw payload keys. That models nothing a reader has seen since
  // CAL-P1024 gave the page a label vocabulary, and it is exactly why the
  // defect was invisible here: with real labels the row printed
  //
  //   Sportsbooks (Odds API)
  //   Per-sportsbook (Odds API) · Odds API · Totals (Odds API) · Spreads (Odds API)
  //
  // — the qualifier four more times, under a heading that had already said it,
  // in a first column narrow enough to wrap it to seven lines at 390px.
  //
  // The KPI tile's copy of this bug was fixed a commit earlier and this one was
  // not, because the two compose the same two vocabularies independently. They
  // now share `withoutGroupQualifier`. Found by photographing the deployed
  // page, not by reading the diff.
  describe("with the REAL labels a reader sees, not the identity fixture", () => {
    const realLabel = (s: string) =>
      ({
        odds_api: "Odds API",
        odds_api_bookmaker: "Per-sportsbook (Odds API)",
        odds_api_spreads: "Spreads (Odds API)",
        odds_api_totals: "Totals (Odds API)",
      })[s] ?? s;

    const realHtml = renderToStaticMarkup(
      <table><tbody>
        {orderSourceRows([SPORTSBOOKS_INPUT]).map(r => (
          <SourceComparisonRow key={r.provider} row={r} sourceLabel={realLabel} toggleLabel={TOGGLE} />
        ))}
      </tbody></table>
    );
    const realText = textOf(realHtml);

    test("says the provider qualifier once, in the row heading, not once per member", () => {
      expect(realText).toContain("Sportsbooks (Odds API)");
      expect(realText).toContain("Odds API · Per-sportsbook · Spreads · Totals");
    });

    test("the qualifier appears exactly once in the whole cell", () => {
      // The reader-visible symptom, counted rather than phrased: four repeats
      // was the bug and one is the fix, so this fails in both directions.
      expect(realText.split("Odds API").length - 1).toBe(2); // the heading, and the un-shaped moneyline key
    });

    test("still names every pooled key — the strip drops a word, never a source", () => {
      for (const shape of ["Per-sportsbook", "Odds API", "Totals", "Spreads"]) {
        expect(realText).toContain(shape);
      }
    });

    test("a provider whose label carries no qualifier is untouched", () => {
      const html = renderToStaticMarkup(
        <table><tbody>
          {orderSourceRows([{ ...SPORTSBOOKS_INPUT, provider: "acme", label: "Acme" }]).map(r => (
            <SourceComparisonRow key={r.provider} row={r} sourceLabel={realLabel} toggleLabel={TOGGLE} />
          ))}
        </tbody></table>
      );
      expect(textOf(html)).toContain(
        "Odds API · Per-sportsbook (Odds API) · Spreads (Odds API) · Totals (Odds API)"
      );
    });
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

// ---------------------------------------------------------------------------
// #6211 — the censored row, asserted as the HTML a reader receives.
//
// With the cohort toggle ON, this cell printed `36 | 36.5pp | 35.8pp | 0.1424`
// beside Kalshi's 318,956 at 0.9pp. All 36 outcomes are winners, so the 36.5pp
// is the n-weighted distance from a 0.44-0.83 price to certainty and cannot
// respond to how anything resolved. The three published figures below are
// production's, from #6211.
// ---------------------------------------------------------------------------
const CENSORED_INPUT: SourceRowInput = {
  provider: "datagolf",
  label: "DataGolf",
  sources: ["datagolf"],
  n: 36,
  ece: 36.5,
  mce: 35.8,
  brier: 0.1424,
  buckets: [
    { n: 3, winners: 3 },
    { n: 9, winners: 9 },
    { n: 14, winners: 14 },
    { n: 9, winners: 9 },
    { n: 1, winners: 1 },
  ],
};

describe("SourceComparisonRow — a source whose population has one side (#6211)", () => {
  const html = renderRows(CENSORED_INPUT);
  const text = textOf(html);

  test("prints none of the three price-determined figures", () => {
    // THE BUG, pinned as text. All three were on the live page.
    expect(text).not.toContain("36.5pp");
    expect(text).not.toContain("35.8pp");
    expect(text).not.toContain("0.1424");
  });

  test("keeps the row and its real outcome count — item 3, do not hide it", () => {
    // The count is honestly arrived at and is the alarm. Dropping the row
    // behind a min-sample floor "would delete the alarm and keep the defect".
    expect(text).toContain("DataGolf");
    expect(html).toContain('data-provider="datagolf"');
    expect(html).toContain('data-provider-n="36"');
    expect(text).toContain("36");
  });

  test("states the population instead, in one line", () => {
    expect(text).toContain("All 36 won");
    expect(text).toContain("no losses to measure against");
  });

  test("says which way it fell — an all-LOSER population reads the other way", () => {
    const lost = textOf(renderRows({
      ...CENSORED_INPUT,
      buckets: [{ n: 36, winners: 0 }],
    }));
    expect(lost).toContain("All 36 lost");
    expect(lost).toContain("no wins to measure against");
    expect(lost).not.toContain("36.5pp");
  });

  test("does not explain itself — notice 34 / D102", () => {
    // Same ban the no-data cell carries. The fact, and nothing written for a
    // reviewer: no method note, no "censored", no "not ranked", no apology.
    for (const jargon of ["censored", "not measured", "not ranked", "sample", "ECE", "population"]) {
      expect(text.toLowerCase()).not.toContain(jargon.toLowerCase());
    }
  });

  test("carries no colour grade — 36.5pp was being printed in orange", () => {
    expect(html).not.toContain("text-green-600");
    expect(html).not.toContain("text-blue-600");
    expect(html).not.toContain("text-orange-600");
  });

  test("publishes its state and its winner count for the audit rail", () => {
    expect(html).toContain('data-row-state="censored"');
    expect(html).toContain('data-testid="calibration-provider-censored"');
    expect(html).toContain('data-provider-winners="36"');
  });

  test("spans the three metric columns only, so the count keeps its own", () => {
    // colSpan 3, not 4: the outcome count is a real number in a real column.
    expect(html).toContain('colSpan="3"');
    expect(html).not.toContain('colSpan="4"');
  });

  test("is not the no-cohort-data cell wearing a different hat", () => {
    // The two absences render two different sentences, and the censored row
    // must not offer the toggle as a remedy — the reader already used it.
    expect(html).not.toContain("calibration-provider-no-data");
    expect(text).not.toContain("No outcomes in this cohort");
    expect(text).not.toContain(TOGGLE);
  });

  test("leaves the measured rows untouched beside it", () => {
    const both = renderRows(KALSHI_INPUT, CENSORED_INPUT);
    expect(textOf(both)).toContain("1.3pp");
    expect(textOf(both)).toContain("0.1712");
    expect(both).toContain('data-row-state="measured"');
    expect(both).toContain('data-row-state="censored"');
  });
});
