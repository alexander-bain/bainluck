/**
 * #997 / D112 (CAL-P1190) — a method-change disclosure has to reach a WEB reader.
 *
 * ═══ WHY THE BACKEND TEST CANNOT CLOSE THIS ═══
 *
 * `backend/tests/test_calibration_public_disclosure_d112.py` asserts the row is in
 * `CALIBRATION_CORRECTIONS`, which is the payload. Being in the payload is not
 * being on a page: #4067 / CERT-2295 took this panel's server prose OFF
 * bainluck.com/calibration, so the web renders a correction's DATE, TITLE and ROW
 * COUNT and drops `description` entirely — the app is the only surface that prints
 * the paragraph. D112's row also carries no count (`rows: null`), on purpose, until
 * a rebuild under the new rule publishes a measured one.
 *
 * So on the web the TITLE is the whole disclosure, and that is a claim about
 * rendered markup, not about a Python list. This suite renders the real page around
 * a planted payload and reads the visible text.
 *
 * ═══ THE ARMS, AND WHY THE POSITIVE ONES COME FIRST ═══
 *
 * Two of the three assertions are absences ("the paragraph is not there"), and an
 * empty render satisfies every `not.toContain` — the failure mode this repo has
 * been bitten by before. So the panel is proved present, by its label, its count
 * and both titles, before anything is claimed to be missing.
 *
 * Mutations run before this was written, source restored byte-identical:
 *   M1  delete the corrections `<section>` from `app/calibration/page.tsx`  → 3 fail
 *   M2  render `{c.description}` beside the title (the change this guards)  → 1 fail
 *   M3  plant the pre-fix title ("…we were throwing away", no outcome)      → 2 fail
 *
 * M2 survived the first draft and is the reason `visibleText` decodes entities;
 * the note on that helper carries the finding.
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
 * Visible text only — attributes are not copy, and entities are DECODED.
 *
 * The decode is load-bearing, not tidiness. `renderToStaticMarkup` escapes an
 * apostrophe to `&#x27;`, so a `not.toContain("the market's own price")` over raw
 * markup passes whether or not the sentence is on the page: mutation M2 (render
 * `{c.description}` beside the title) SURVIVED the first draft of this suite for
 * exactly that reason. Anything a reader's eye would see is compared as a reader
 * would read it.
 */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x([0-9a-f]+);/gi, (_m, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_m, dec) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&mdash;/g, "—")
    .replace(/&rsquo;/g, "’")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

// ---------------------------------------------------------------------------
// The D112 row, copied from `CALIBRATION_CORRECTIONS` in
// `backend/app/tasks/precompute_calibration.py`. The strings are planted rather
// than imported (this is a jest suite; that is a Python module), and that is
// fine: what this suite pins is the CHANNEL — a title reaches the page, a
// paragraph does not — not the wording, which the backend suite owns.
// ---------------------------------------------------------------------------
const D112_TITLE = "The one-question markets we were throwing away are now scored";

const D112_DESCRIPTION_OPENING =
  "We only score ourselves against an answer that came from somewhere other than " +
  "the market's own price";

const LEGACY_TITLE = "A price ladder is one forecast, not forty";

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
    corrections: [
      {
        date: "2026-09-06",
        title: LEGACY_TITLE,
        rows: 1_234,
        description: "A ladder of price bands is one question asked forty ways.",
      },
      {
        date: "2026-09-13",
        title: D112_TITLE,
        rows: null,
        description:
          D112_DESCRIPTION_OPENING +
          " — otherwise the price is marking its own homework.",
      },
    ],
  } as CalibrationData;
}

function renderPage(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return visibleText(renderToStaticMarkup(React.createElement(CalibrationPage)));
}

describe("the D112 disclosure on bainluck.com/calibration", () => {
  it("puts the corrections panel on the page, with every row counted", () => {
    const text = renderPage();

    expect(text).toContain("Technical: data corrections log");
    expect(text).toContain("(2)");
    // The absences below mean nothing unless the list itself rendered.
    expect(text).toContain(LEGACY_TITLE);
    expect(text).toContain("1,234 rows");
  });

  it("shows D112's date and title, which is all a web reader gets", () => {
    const text = renderPage();

    expect(text).toContain("2026-09-13");
    expect(text).toContain(D112_TITLE);
  });

  it("does not print the server's paragraph, so the title has to carry the change", () => {
    const text = renderPage();

    // Positive arm first: the row IS on the page (see the suite header).
    expect(text).toContain(D112_TITLE);

    expect(text).not.toContain(D112_DESCRIPTION_OPENING);
  });
});
