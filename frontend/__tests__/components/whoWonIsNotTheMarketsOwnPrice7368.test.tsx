/**
 * #7368 — the methodology section may not answer "how do we know who won?" with the
 * market's own price.
 *
 * ═══ THE CLASS ═══
 *
 * `truth_evidence.rule` (produced by `_build_truth_evidence` in
 * `backend/app/tasks/precompute_calibration.py`) grades a published forecast only on
 * a winner established INDEPENDENTLY of that market's own price; price-derived truth
 * is excluded from the curve, with one exception (D112 / #997: a lone-claim market,
 * where no sibling's price can be grading the row). Until this suite, the page said
 * the opposite — "a market's final price settles at $1.00 (happened) or $0.00 (didn't
 * happen)" — and nothing repaired the impression, because `truth_evidence` is not
 * rendered anywhere in `frontend/` and the corrections log's web rendering drops
 * `description` (#4067; see `d112DisclosureReachesAWebReader997.test.tsx`).
 *
 * So the defect is not a typo, it is a standing claim about method, and the guard is
 * written against the SHAPE of that claim rather than its spelling: any sentence in
 * this section that mentions a price and then hands that price settlement authority.
 * A literal ban on the old string would pass the day someone re-words it.
 *
 * ═══ SCOPING, AND WHY IT IS NOT THE WHOLE PAGE ═══
 *
 * The rest of the page legitimately says prices settle — the corrections log, the
 * exclusion bullets and the Sources card all describe venue mechanics. The claim this
 * bans is specifically the METHODOLOGY section's answer to who-won, so the haystack is
 * cut to `<section id="methodology">` and `cutMethodology` THROWS when that section is
 * absent: an empty haystack satisfies every `not.toMatch` (this repo's oldest own-goal),
 * and a page that stopped rendering the section must fail here, not pass quietly.
 *
 * ═══ MUTATIONS, source restored byte-identical afterwards ═══
 *
 *   M1  restore the pre-fix sentence verbatim                          → 4 fail
 *   M2  re-word it ("the closing price tells us who won")              → 2 fail, incl. the shape arm
 *   M3  delete the lone-claim exception sentence (the over-claim)      → 1 fail
 *   M4  delete the `<section id="methodology">` block                  → cutMethodology throws, 4 fail
 *   M5  "left out of the curve" → "set aside"                          → 1 fail
 *
 * M2 is the one that matters: its wording appears nowhere in the repo's history, so
 * only the shape arm can see it. A literal-string suite would have passed it.
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

/**
 * Visible text only, entities DECODED — `renderToStaticMarkup` writes `&#x27;` for an
 * apostrophe, so a raw-markup assertion about "the market's own price" would pass
 * whether or not the sentence is on the page (the finding that survived the first
 * draft of the #997 suite).
 */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x([0-9a-f]+);/gi, (_m, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_m, dec) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&mdash;/g, "—")
    .replace(/&rsquo;/g, "’")
    .replace(/&ldquo;/g, "“")
    .replace(/&rdquo;/g, "”")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Cut the methodology `<section>` out of the raw markup by counting `<section` /
 * `</section>` — the section holds no nested `<section>` today, and counting means it
 * keeps working if one is added. THROWS when the section is not on the page: every
 * assertion below is about what this section does and does not say, and all of the
 * negative ones are vacuously true over an empty string.
 */
function cutMethodology(html: string): string {
  const open = html.indexOf('<section id="methodology"');
  if (open === -1) {
    throw new Error(
      'the methodology section is not on the page — every assertion in this suite is ' +
        "about its text, so an absent section is a failure, not a pass",
    );
  }
  let depth = 0;
  const tag = /<\/?section\b/g;
  tag.lastIndex = open;
  for (let m = tag.exec(html); m !== null; m = tag.exec(html)) {
    depth += m[0] === "</section" ? -1 : 1;
    if (depth === 0) return html.slice(open, m.index + "</section>".length);
  }
  throw new Error("the methodology section is never closed — markup this suite cannot read");
}

function bucket(idx: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
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

function makePayload(): CalibrationData {
  return {
    buckets: [0, 1, 2, 3, 4].map(bucket),
    total_markets: 12_000,
    total_outcomes: 48_000,
    total_winners: 24_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-13T23:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-13" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: [{ category: "baseball", ece: 0.02, n: 4_000 }],
    corrections: [],
  } as unknown as CalibrationData;
}

function methodologyText(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return visibleText(cutMethodology(renderToStaticMarkup(React.createElement(CalibrationPage))));
}

/**
 * The shape of the banned claim: a price, then that price being handed the authority
 * to say what happened. Split by sentence so "we do NOT take the winner from the
 * market's own closing price" — a denial, in the same paragraph — is read as the
 * sentence it is rather than as a substring of the section.
 */
const PRICE_DECIDES = [
  /\bprice\b[^.]*\bsettles? at\b/i,
  /\bprice\b[^.]*\b(tells?|telling) us (who won|what happened)\b/i,
  /\bprice\b[^.]*\b(determines?|decides?|establishes?)\b[^.]*\b(winner|who won|outcome|result)\b/i,
  /\b(winner|who won|the result)\b[^.]*\b(is|are) (set|decided|determined|established) by\b[^.]*\bprice\b/i,
  /\bhow we know who won\b[^.]*\bprice\b/i,
];

describe("#7368 — the accuracy page's answer to 'how do we know who won?'", () => {
  it("names the venue's settlement as the evidence, and says price-only rows are dropped", () => {
    const text = methodologyText();

    // Positive arms first: the section, the bullet, then what it must say.
    expect(text).toContain("How We Measure This");
    expect(text).toContain("How do we know who won?");
    expect(text).toContain("the venue’s own settlement");
    expect(text).toContain("left out of the curve");
  });

  it("leaves room for the lone-claim exception, which is real (D112, #997)", () => {
    const text = methodologyText();

    // Without this the copy becomes its own over-claim: price-derived truth IS
    // accepted on a market with exactly one captured outcome.
    expect(text).toContain("How do we know who won?");
    expect(text).toContain("a single yes-or-no question");
  });

  it("hands no price the authority to say what happened — any wording of it", () => {
    const text = methodologyText();

    // The section rendered (above), so these absences mean something.
    expect(text).toContain("How do we know who won?");

    const offenders = text
      .split(/(?<=[.!?])\s+/)
      .filter((sentence) => PRICE_DECIDES.some((shape) => shape.test(sentence)));
    expect(offenders).toEqual([]);
  });

  it("does not carry the pre-fix sentence, in the letters it was written in", () => {
    const text = methodologyText();

    expect(text).toContain("How do we know who won?");
    expect(text).not.toContain("final price settles at");
    expect(text).not.toContain("$1.00 (happened)");
  });
});
