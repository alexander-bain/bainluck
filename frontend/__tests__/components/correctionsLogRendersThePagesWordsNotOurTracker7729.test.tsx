/**
 * #7729, the render half — the reader's screen, not the helper's return value.
 *
 * `__tests__/lib/correctionsLogDoesNotQuoteOurTracker7729.test.ts` proves
 * `correctionTitle` is right. That is not the ship. The page rendered
 * `{c.title}` for eleven weeks, and a `correctionTitle` that is perfect and
 * uncalled leaves "Queue #186" exactly where it was: on production, at 390px, in
 * the trust panel.
 *
 * So this suite renders the actual page with the actual production specimen in
 * its payload and reads the section's visible text — the same discipline the
 * #7363 suite next door uses, and the reason it could assert a promise rather
 * than a spelling.
 *
 * ── WHY THE SECTION IS CUT OUT AND NOT SEARCHED WHOLE ───────────────────────
 *
 * `not.toContain("Queue #186")` over the whole page is satisfied by a page that
 * failed to render the corrections log at all — and this page renders the log
 * behind `data.corrections && data.corrections.length > 0`, so an empty
 * haystack is one payload shape away. `correctionsSection` throws when the
 * section is absent, which converts that silent pass into a red.
 *
 * ── AND WHY THE ATTRIBUTE IS CHECKED ON THE MARKUP, NOT THE TEXT ────────────
 *
 * `data-corrections-needing-copy` is the page's published gap counter. It is
 * deliberately not prose (notice 34), so `visibleText` — which drops every tag
 * and takes the attributes with it — cannot see it. It is read off the raw HTML.
 */

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

/** The corrections log's markup, cut out by `<section>` depth counting. */
function correctionsMarkup(html: string): string {
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
    if (depth === 0) return html.slice(open, nextClose);
    depth -= 1;
    i = nextClose;
  }
}

/** The production specimen, verbatim from `/api/calibration` on 2026-09-21. */
const SPECIMEN =
  "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)";

/**
 * Four live entries: the specimen, the two that carry a row count, and one
 * clean null-rows entry.
 *
 * The two row-count entries are here so this suite fails if #7729 knocks over
 * #7363's contract — the row count must still render beside the title it
 * belongs to, and a title helper is exactly the thing that could detach it.
 */
const CORRECTIONS = [
  { date: "2026-07-09", title: "Polymarket hockey sign-flip", rows: 36_207, description: "" },
  { date: "2026-07-08", title: "Premature golf resolutions", rows: 230, description: "" },
  { date: "2026-07-13", title: SPECIMEN, rows: null, description: "" },
  {
    date: "2026-09-13",
    title: "The one-question markets we were throwing away are now scored",
    rows: null,
    description: "",
  },
];

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
    generated_at: "2026-09-21T07:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-21" },
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

describe("#7729 — what the corrections log puts on a reader's screen", () => {
  it("renders the section it is claiming about", () => {
    // The precondition for every `not.toContain` below. An absent section is
    // free to pass all of them. Anchored on a DATE rather than a title: #7734
    // gave eight of the thirteen titles reader copy, so a title is no longer a
    // fixed string, while the date column is the payload's own and is not the
    // page's to reword.
    const text = visibleText(correctionsMarkup(renderPage()));
    expect(text).toContain("data corrections log");
    expect(text).toContain("2026-07-09");
    expect(text).toContain("Premature golf resolutions");
  });

  it("does not print our queue id", () => {
    const text = visibleText(correctionsMarkup(renderPage()));
    expect(text).not.toContain("Queue #186");
    expect(text).not.toContain("Queue");
    expect(text).not.toContain("#186");
  });

  it("does not print 'discriminator'", () => {
    expect(visibleText(correctionsMarkup(renderPage())).toLowerCase()).not.toContain(
      "discriminator"
    );
  });

  it("prints the page's words for that entry instead, beside its date", () => {
    // Pinned by value AND adjacency: a row that rendered the right words under
    // the wrong date would satisfy a bare `toContain`.
    const text = visibleText(correctionsMarkup(renderPage()));
    expect(text).toContain(
      "2026-07-13 Player-prop prices (Kalshi): corrected the test for which prices to drop"
    );
  });

  it("leaves the two entries no fix has re-worded exactly as the payload wrote them", () => {
    const text = visibleText(correctionsMarkup(renderPage()));
    for (const title of [
      "Premature golf resolutions",
      "The one-question markets we were throwing away are now scored",
    ]) {
      expect(text).toContain(title);
    }
  });

  it("prints #7734's words for the hockey entry, and not the producer's", () => {
    // The fourth fixture row. It rendered verbatim until #7734 and is the reason
    // this suite's other assertions could not stay keyed on it.
    const text = visibleText(correctionsMarkup(renderPage()));
    expect(text).toContain(
      "Hockey player props (Polymarket): over and under prices were the wrong way round, now re-scored"
    );
    expect(text).not.toContain("sign-flip");
  });

  it("still puts #7363's row counts beside their own titles", () => {
    const text = visibleText(correctionsMarkup(renderPage()));
    // The adjacency check that matters most after #7734: the count belongs to the
    // row, and the row now renders a string the page chose rather than the one the
    // payload sent. A helper that detached the two would show up exactly here.
    expect(text).toContain(
      "Hockey player props (Polymarket): over and under prices were the wrong way round, now re-scored 36,207 rows"
    );
    expect(text).toContain("Premature golf resolutions 230 rows");
    // And still exactly two, not four.
    expect(text.match(/ rows/g)?.length).toBe(2);
  });

  it("publishes the gap counter as an attribute, at zero, and not as prose", () => {
    const markup = correctionsMarkup(renderPage());
    expect(markup).toContain('data-corrections-needing-copy="0"');
    expect(visibleText(markup)).not.toContain("needing copy");
  });

  it("counts a title nobody has written words for, without printing the count", () => {
    // The control the assertion above needs: `="0"` is also what a hardcoded
    // zero looks like. This moves the payload and requires the number to move.
    const markup = correctionsMarkup(
      renderPage([
        ...CORRECTIONS,
        { date: "2026-10-01", title: "Queue #500 changed how we price a draw", rows: null, description: "" },
      ])
    );
    expect(markup).toContain('data-corrections-needing-copy="1"');
    expect(visibleText(markup)).not.toContain("1 entry");
  });
});
