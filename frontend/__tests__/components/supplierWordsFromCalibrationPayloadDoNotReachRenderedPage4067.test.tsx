/**
 * #4067 / CERT-2295 — `4067-CALIBRATION-DOES-NOT-RENDER-BANNED-SERVER-PROSE`.
 *
 * ═══ WHY THERE IS A THIRD GUARD FOR ONE BANNED WORD ═══
 *
 * Notice 33 bans four spellings from everything a reader sees. #4067 swept the
 * repo for them twice and was blocked twice, and the two blocks are the same
 * finding at different depths:
 *
 *   CERT-2290  the sweep read `components/*.tsx`, so it never reached the
 *              calibration page's own copy or its local label map.
 *   CERT-2295  the sweep then read the page's copy — and the surviving words
 *              were not in this repo at all. They arrive at render time inside
 *              `/api/calibration`, in `corrections[7].description` and
 *              `soccer_2way_filter.rule`, and the page printed them verbatim.
 *
 * 🔴 **A GUARD OVER SOURCE CANNOT SEE A STRING THAT IS NOT IN THE SOURCE.**
 * `noBooksWordAnywhere4067.test.tsx` renders two components with fixtures we
 * write, so every word it checks is a word we already control. That is the
 * wrong instrument for a payload field, and it is exactly why two sweeps came
 * back clean while production said `per-bookmaker` on a page Alex reads. So
 * this suite plants the REAL production strings — copied from the live payload
 * at 2026-09-08 23:5xZ, banned words and all — and renders the whole page
 * around them.
 *
 * ═══ WHAT IT ASSERTS, AND WHY THE POSITIVE ARMS COME FIRST ═══
 *
 * The ship is a REMOVAL, which makes this a suite that could pass by rendering
 * nothing at all — the failure mode this repo has already been bitten by (an
 * empty render satisfies every `not.toContain`). So each arm proves the section
 * is on the page, by its label and by its COUNT, before it claims the prose is
 * gone. If the exclusions list stops rendering, these go red.
 *
 * ═══ THE FIELDS NO BULLET READS TODAY ARE PLANTED TOO, DELIBERATELY ═══
 *
 * `quarantine[].note`, and `source_labels` for a source key the house-style map
 * has never heard of. Neither renders on today's payload — there is no
 * `quarantine` key, and every live source key is mapped. Planting them is what
 * makes this a guard over the CLASS rather than a record of the two fields a
 * cert happened to name: the next `{data.x.rule}` fails here on the day it is
 * written. A denylist of the known survivors hands the claim to the first new
 * one.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import CalibrationPage from "@/app/calibration/page";
import type { CalibrationData } from "@/lib/api";

// ---------------------------------------------------------------------------
// The page is a `"use client"` component behind SWR. Mocking the hook — rather
// than the fetcher — is what lets a single synchronous render see the payload:
// `renderToStaticMarkup` never runs an effect, so a real SWR would hand the
// page `undefined` and this suite would photograph the loading state.
// ---------------------------------------------------------------------------
let payload: CalibrationData;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: (global as unknown as { __calPayload: CalibrationData }).__calPayload }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

// The curve itself draws no text from these fields, and recharts in a static
// render is slow and noisy. Stubbing it keeps the suite about the copy.
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

/** The four spellings, exactly as notice 33 lists them. */
const BANNED = /\b(books?|bookmakers?|per-bookmaker)\b/i;

/**
 * Visible text only — attributes are not copy.
 *
 * Same helper, same reasoning, as `noBooksWordAnywhere4067.test.tsx`: dropping
 * each tag WHOLE takes its attributes with it, so `data-source="odds_api_
 * bookmaker"` is invisible here exactly as it is to a reader. The source KEYS
 * are a wire contract and must survive this ship untouched.
 */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// ---------------------------------------------------------------------------
// THE LEGACY PROSE, VERBATIM. Every string below was served by
// https://api.bainluck.com/api/calibration on 2026-09-08 and rendered on
// https://bainluck.com/calibration. They are quoted rather than paraphrased
// because a paraphrase would be a string this ship has already made safe.
// ---------------------------------------------------------------------------
const LEGACY_CORRECTION_DESCRIPTION =
  "Soccer game-odds were captured 2-way (home/away only) — no draw column — so every " +
  "soccer moneyline row summed to ~1.0 and structurally dropped the ~25% draw mass (#1011), " +
  "in BOTH the events aggregate and the per-bookmaker curve.";

const LEGACY_SOCCER_RULE =
  "Excludes historical soccer game-odds (moneyline) from the curve — BOTH the events " +
  "aggregate (odds_api) and the per-bookmaker (odds_api_bookmaker) sources.";

const LEGACY_LIQUIDITY_RULE =
  "Excludes outcomes that never showed a real bid (yes_bid > 0) or trade (last_price > 0) " +
  "in any snapshot — pure one-sided, never-traded placeholder prices.";

const LEGACY_ESPORTS_RULE =
  "Excludes esports 'match bundle' markets — Polymarket packs a whole match into one " +
  "non-partition market, priced by the books rather than by a single question.";

const LEGACY_VOID_RULE =
  "Excludes resolved outcomes for players who never participated (did_not_play / withdrew) " +
  "— VOIDs with no real outcome to score, not losses.";

const LEGACY_BUNDLE_RULE =
  "Excludes non-exclusive BUNDLES — markets of >=3 outcomes that are not proved " +
  "single-winner partitions, as quoted by the bookmakers behind them.";

const LEGACY_QUARANTINE_NOTE =
  "Held while we reconcile the per-bookmaker rows against the events aggregate.";

const LEGACY_UNMAPPED_LABEL = "Per-Bookmaker (Odds API)";

/**
 * A source key no house-style map has an opinion about.
 *
 * In the `odds_api` family on purpose. A lone unmapped source is absorbed into
 * its PROVIDER's label ("Sportsbooks (Odds API)") and its own name never
 * renders — which is how the first draft of this suite passed while proving
 * nothing. Three shapes in one family open the per-shape breakdown, and that is
 * the surface where `sourceLabel` prints a source's own name.
 */
const UNMAPPED_SOURCE = "odds_api_bookmaker_closing";

function bucket(source: string, idx: number, over: Record<string, unknown> = {}) {
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
    ...over,
  };
}

function makePayload(): CalibrationData {
  const sources = ["kalshi", "polymarket", "odds_api", "odds_api_spreads", UNMAPPED_SOURCE];
  const buckets = sources.flatMap((s) => [0, 1, 2, 3, 4].map((i) => bucket(s, i)));

  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: 48_000,
    total_winners: 24_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-08T23:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-08" },
    by_source: sources.map((source) => ({ source, ece: 0.02, mce: 0.05, n: 2_000 })),
    // The server names a source this client has never mapped. Before this ship
    // `makeSourceLabeller` printed that name verbatim, which is how the label
    // CERT-2290 found got onto the page in the first place.
    source_labels: {
      [UNMAPPED_SOURCE]: { label: LEGACY_UNMAPPED_LABEL, declared: true },
    },
    by_category: [{ category: "baseball", ece: 0.02, n: 4_000 }],
    corrections: [
      {
        date: "2026-07-11",
        title: "Soccer 2-way (draw-omission) historical exclusion",
        rows: 1_234,
        description: LEGACY_CORRECTION_DESCRIPTION,
      },
    ],
    liquidity_filter: {
      applies_to: "kalshi",
      rule: LEGACY_LIQUIDITY_RULE,
      kalshi_included: 9_000,
      kalshi_excluded: 1_000,
    },
    esports_multi_bundle_filter: {
      applies_to: "polymarket",
      rule: LEGACY_ESPORTS_RULE,
      excluded: 777,
    },
    soccer_2way_filter: {
      applies_to: "odds_api, odds_api_bookmaker",
      rule: LEGACY_SOCCER_RULE,
      excluded: 555,
    },
    void_filter: {
      applies_to: "datagolf",
      rule: LEGACY_VOID_RULE,
      excluded: 333,
    },
    nonexclusive_bundle_filter: {
      applies_to: "kalshi/economics",
      rule: LEGACY_BUNDLE_RULE,
      excluded: 2_200,
      excluded_by_cell: { "kalshi/economics": 1_500, "polymarket/baseball": 700 },
      temporary_by_cell: { "polymarket/baseball": "the writer is repaired" },
      temporary_excluded: 700,
      historical_excluded: 1_500,
    },
    quarantine: [
      {
        reason: "Soccer draw-omission rows",
        outcomes: 410,
        status: "under_review",
        note: LEGACY_QUARANTINE_NOTE,
      },
    ],
  } as unknown as CalibrationData;
}

function renderPage(): string {
  payload = makePayload();
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = payload;
  return renderToStaticMarkup(<CalibrationPage />);
}

describe("#4067 — no supplier word from /api/calibration reaches the rendered page", () => {
  it("renders the page it is claiming about", () => {
    // THE ANTI-VACUOUS ARM. Every assertion below this one is an absence, and
    // an absence is free on a page that failed to render. Two headings and a
    // count prove there is a page here to be judged.
    const text = visibleText(renderPage());
    expect(text).toContain("Calibration");
    expect(text).toContain("Liquidity filter (Kalshi)");
    expect(text).toContain("9,000 included");
  });

  it("prints no banned word anywhere on the page, from any payload field", () => {
    // The whole ship in one line. Seven live prose fields carry a banned word in
    // this fixture; the rendered text may carry none of them.
    const text = visibleText(renderPage());
    const hit = text.match(BANNED);
    expect(hit ? `"${hit[0]}" in: ${text.slice(Math.max(0, hit.index! - 90), hit.index! + 90)}` : null)
      .toBeNull();
  });

  it("drops the backend's exclusion prose and keeps the label and the count", () => {
    const text = visibleText(renderPage());

    // Kept: what the exclusion IS and how big it is — the disclosure Alex ruled
    // on (CAL-P114/P117) lives in the label, the counts and this repo's own
    // sentences, never in the payload's explanation of itself.
    expect(text).toContain("Soccer 2-way (draw-omission) filter");
    expect(text).toContain("555 excluded");
    expect(text).toContain("Esports match-bundle filter");
    expect(text).toContain("777 excluded");
    expect(text).toContain("Void filter (did-not-play / withdrew)");
    expect(text).toContain("333 excluded");
    expect(text).toContain("Non-partition bundle filter");

    // Dropped: the method note. Asserted by a distinctive fragment of each rule
    // that carries no banned word, so these arms stay meaningful even if the
    // backend one day launders the vocabulary and keeps the paragraph.
    expect(text).not.toContain("yes_bid > 0");
    expect(text).not.toContain("did_not_play / withdrew)");
    expect(text).not.toContain("Soccer h2h is 3-way");
    expect(text).not.toContain("non-partition market");
  });

  it("keeps Alex's ruled disclosure clauses, which are ours and not the server's", () => {
    // CAL-P114/P117/P119 + CERT-647. The repair removed payload prose; if it had
    // taken the ruling's own sentences with it, that is a different regression
    // wearing the same diff.
    const text = visibleText(renderPage());
    expect(text).toContain("kalshi/economics 1,500");
    expect(text).toMatch(/shrank the curve rather than improving it/i);
    expect(text).toMatch(/never read as a fixed one/i);
    expect(text).toMatch(/temporary by design/i);
  });

  it("keeps the corrections log's date, title and row count without its paragraph", () => {
    const text = visibleText(renderPage());
    expect(text).toContain("2026-07-11");
    expect(text).toContain("Soccer 2-way (draw-omission) historical exclusion");
    expect(text).toContain("1,234 rows");
    // The intro above the log promises "dates and rows affected". It keeps that
    // promise; what goes is the engineer's paragraph beneath each entry.
    expect(text).not.toContain("structurally dropped");
  });

  it("house-styles a source name the client has never mapped", () => {
    // CERT-2290's original finding, at its last remaining entrance. Every source
    // key on today's payload is in `SOURCE_DISPLAY_NAMES`, so the server label is
    // only reachable through a key nobody has mapped yet — which is precisely the
    // case the map cannot cover and the one a new source key arrives as.
    const text = visibleText(renderPage());
    expect(text).not.toContain("Per-Bookmaker");
    expect(text).toContain("Per-Sportsbook");

    // And the KEY is untouched: the wire contract is not copy.
    expect(renderPage()).toContain(UNMAPPED_SOURCE);
  });

  it("the predicate is not vacuous — every planted string trips it", () => {
    // A banned-word test that has never seen a banned word is a test whose regex
    // is wrong. These are the exact strings the page was handed above.
    for (const legacy of [
      LEGACY_CORRECTION_DESCRIPTION,
      LEGACY_SOCCER_RULE,
      LEGACY_ESPORTS_RULE,
      LEGACY_BUNDLE_RULE,
      LEGACY_QUARANTINE_NOTE,
      LEGACY_UNMAPPED_LABEL,
    ]) {
      expect(legacy).toMatch(BANNED);
    }
    // `liquidity_filter.rule` and `void_filter.rule` carry no banned word and are
    // planted anyway — they are the arm that proves the fix is the BINDING and
    // not a word swap. If a later edit restores `{data.liquidity_filter.rule}`,
    // the `yes_bid > 0` assertion above is what catches it.
    expect(LEGACY_LIQUIDITY_RULE).not.toMatch(BANNED);
    expect(LEGACY_VOID_RULE).not.toMatch(BANNED);
  });
});
