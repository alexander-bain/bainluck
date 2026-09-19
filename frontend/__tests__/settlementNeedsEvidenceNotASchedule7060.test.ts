// #7060 (+ #7058's frontend half) — `/futures/[id]` may announce settlement only
// from settlement EVIDENCE, and may not print a scheduled date as history.
//
// The defect, as a reader met it. Production 2026-09-18 23:43Z, 390px,
// `/futures/61317401` — "Detroit Tigers vs. Chicago White Sox · 1st Inning
// Winner", a game in its first innings:
//
//     This market resolved on 9/18/2026. Showing final probabilities.
//     53%  ↑ 4.0 pts · last move Sep 18
//     Draw 53% · Chicago White Sox 26% · Detroit Tigers 21%
//
// `status: "open"`, `settled_at` absent from the payload, venue quoting all
// three legs. 937 open markets carried a passed `resolution_date` that minute.
//
// Two arms here, and they guard different failures:
//
//  1. The DECISION, in `lib/settlementBanner.ts`. The page is a client component
//     that loads through SWR, so no test can render it; the rule lives in a pure
//     module for exactly that reason.
//  2. The CALL SITE, read as source. Arm 1 cannot see a future edit that
//     re-introduces the date arm in JSX beside the function — which is precisely
//     how this defect was written the first time, next to a line that already
//     knew the rule.

import { readFileSync } from "fs";
import { join } from "path";

import { settlementBannerText } from "@/lib/settlementBanner";

const PAGE = join(__dirname, "..", "app", "futures", "[id]", "page.tsx");

/** A date in any format a reader would read as one. */
const PRINTS_A_DATE = /\d/;

/** The banner exactly as it stood on production, kept as the control's subject. */
const PRE_FIX_BANNER = `
      {(isResolved || (market.resolution_date && new Date(market.resolution_date) < new Date())) && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 text-sm text-amber-400">
          {isResolved
            ? \`This market has been settled.\${market.resolution_date ? \` Resolved \${new Date(market.resolution_date).toLocaleDateString()}.\` : ""}\`
            : \`This market resolved on \${new Date(market.resolution_date!).toLocaleDateString()}. Showing final probabilities.\`}
        </div>
      )}`;

const BANNER_PHRASES = [
  "This market has been settled.",
  "This market resolved on",
  "Showing final probabilities",
  " Resolved $",
];

describe("#7060 the settled banner reads settlement, not the calendar", () => {
  it("prints a sentence for a settled market (anti-vacuity)", () => {
    // Without this, every `toBeNull()` below would pass on a function that
    // returns null unconditionally.
    expect(settlementBannerText({ status: "resolved" })).toBe(
      "This market has been settled.",
    );
  });

  it("says nothing on an open market whose scheduled date has passed", () => {
    // THE DEFECT. `resolution_date` is passed here and the market is trading.
    expect(
      settlementBannerText({
        status: "open",
        // @ts-expect-error — the subject type deliberately does not accept a
        // date. Passing one proves the decision cannot be reached by it.
        resolution_date: "2026-09-18T23:40:00+00:00",
      }),
    ).toBeNull();
  });

  it("says nothing on an open market whose scheduled date is in the future", () => {
    expect(
      settlementBannerText({
        status: "open",
        // @ts-expect-error — see above.
        resolution_date: "2027-01-01T00:00:00+00:00",
      }),
    ).toBeNull();
  });

  it("says nothing on an open market with no date at all", () => {
    expect(settlementBannerText({ status: "open" })).toBeNull();
  });

  it("says nothing for a missing or empty market", () => {
    expect(settlementBannerText(null)).toBeNull();
    expect(settlementBannerText(undefined)).toBeNull();
    expect(settlementBannerText({})).toBeNull();
  });

  it("never states a date on a settled market — #7058's half", () => {
    // The banner used to append " Resolved <resolution_date>.", and on 9,993
    // resolved markets that date is in the FUTURE ("Resolved 9/25/2026" on a
    // market settled today).
    const text = settlementBannerText({
      status: "resolved",
      // @ts-expect-error — a date must not be able to influence the words.
      resolution_date: "2026-09-25T00:00:00+00:00",
    });
    expect(text).toBe("This market has been settled.");
    expect(text).not.toMatch(PRINTS_A_DATE);
  });

  it("stays silent even once `settled_at` is served — #7058's second half", () => {
    // NOT the same arm as above, and not a spare. #7058 asked for `settled_at`
    // on the detail payload and for this module to print it; the day some lane
    // serves the field, the ONLY thing standing between it and the banner is
    // that `SettlementBannerSubject` refuses it. This pins that refusal.
    //
    // Printing it would install a second false date rather than remove one:
    // measured on production 2026-09-19 over the issue's own population (9,347
    // resolved markets with a future `resolution_date` and a `settled_at`),
    // 4,765 carry a stamp more than 24h after their game started and 1,256 more
    // than 30 days after — because `settled_at` is when a SWEEP saw the row, not
    // when the market resolved. 137 unrelated markets share one such stamp to
    // the microsecond. The five specimens in the issue are games played
    // 2026-09-11 that all carry 2026-09-18 22:55:08.995192Z.
    //
    // Full measurement, both methods, and the witness to use if a date is ever
    // actually wanted: the header of `lib/settlementBanner.ts`.
    const text = settlementBannerText({
      status: "resolved",
      // @ts-expect-error — the lagged stamp must not reach the words, nor the
      // schedule sitting beside it as it does on every one of the 9,347 rows.
      // ONE directive covers both: TS reports an excess-property literal once,
      // at its first offending key, and a second directive here reads as unused
      // (TS2578) and fails the typecheck gate.
      settled_at: "2026-09-18T22:55:08.995192+00:00",
      resolution_date: "2026-09-25T00:00:00+00:00",
    });
    expect(text).toBe("This market has been settled.");
    expect(text).not.toMatch(PRINTS_A_DATE);
  });

  it("treats every non-resolved status as unsettled", () => {
    // `lib/types.ts` declares a third value, `closed`, that production does not
    // hold (measured: `resolved` 1,026,367 / `open` 42,839, no other row). If it
    // ever appears it must not be guessed into a settlement claim.
    for (const status of ["open", "closed", "", "RESOLVED", "settled", null]) {
      expect(settlementBannerText({ status })).toBeNull();
    }
  });
});

describe("#7060 the page cannot say it another way", () => {
  const source = readFileSync(PAGE, "utf8");

  it("reads the page and finds its JSX (anti-vacuity)", () => {
    expect(source.length).toBeGreaterThan(10_000);
    expect(source).toContain("<FuturesHero");
  });

  it("gets the banner from the guarded decision", () => {
    expect(source).toContain('from "@/lib/settlementBanner"');
    expect(source).toContain("settlementBannerText(market)");
  });

  it("holds no settlement wording of its own", () => {
    // The words live in the module the arm above tests. A second copy here is
    // a second answer to one question, which is how the page came to contradict
    // itself three lines apart.
    //
    // The phrases are FULL sentence fragments on purpose: a first draft of this
    // test banned "resolved on" and failed on the comment "a resolved one whose
    // winner is at 100%". A loose probe reports a defect that is not there, and
    // the next reader loosens the assertion to get green.
    for (const phrase of BANNER_PHRASES) {
      expect(source).not.toContain(phrase);
    }
  });

  it("would notice if those phrases came back (control)", () => {
    // The arm above is an ABSENCE claim, so it passes just as well on three
    // phrases that never existed. This runs the same probe over the text that
    // WAS on production and requires every one of them to hit.
    for (const phrase of BANNER_PHRASES) {
      expect(PRE_FIX_BANNER).toContain(phrase);
    }
  });

  it("derives nothing rendered from `resolution_date < now`", () => {
    const gate = /new Date\(market\??\.?resolution_date\)\s*<\s*new Date\(\)/g;
    const hits = [...source.matchAll(gate)];

    // Exactly one survives, and it is NOT a claim to the reader: `historyHours`
    // widens the chart's fetch window for a market that is probably over. It is
    // named rather than banned because it was measured — these markets were
    // created days ago, so that window floors at 168h either way.
    expect(hits).toHaveLength(1);

    const jsxStart = source.indexOf('  return (\n    <div className="space-y-6">');
    expect(jsxStart).toBeGreaterThan(0);
    expect(hits[0].index).toBeLessThan(jsxStart);
  });
});
