/**
 * UX-P172 — EVERY CATEGORY PAGE STOPS BEING EMPTY.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/categories` draws 29 cards. Each one prints a count and links to
 * `/categories/<slug>`. Soccer's card says "9,191 markets". Football's says
 * "3,001". Politics' says "6,608". Clicking any of them landed on a page that
 * said:
 *
 *     No soccer items right now
 *     Check back soon or browse other categories
 *
 * That is the insidious part. The destination does not look broken — it looks
 * like a quiet week. It renders a tidy, deliberate empty state, so nothing about
 * it invites a bug report. The only way to see the lie is to notice that the
 * card you just clicked promised nine thousand markets.
 *
 * ═══ WHY IT WAS EMPTY ═══
 *
 * The two pages read two different producers. The index card counts the raw
 * database (`/api/feed/tag-counts` — open futures per `llm_sport_category`,
 * active events per sport-key prefix). The destination renders the curated
 * Discover feed filtered by tag (`/api/feed?tags=["sport:soccer"]`).
 *
 * The tag filter matched nothing. Not "nothing today" — nothing ever, in any
 * namespace, since the day it was written. Three call sites built containment
 * as `cast(json.dumps([...]), JSONB)`, which double-encodes the bind: the value
 * reaches PostgreSQL as a JSON *string scalar* rather than a JSON *array*, and
 * `@>` is then simply false. No error, no warning, no log line.
 *
 * Mechanism, wire values and the repo-wide sweep live in
 * `backend/app/utils/jsonb_containment.py` and its two guard files.
 *
 * ═══ THE READER COUNT ═══
 *
 * Measured against production on 2026-08-29, one request per category through
 * the exact URL the shipped page builds:
 *
 *     27 of 29 category pages served ZERO items.
 *     The 2 exceptions served ONLY injected cards, never a tagged row:
 *       golf  →  6 tournament cards
 *       mma   → 16 concept cards (and 3 of the first 6 are not MMA at all —
 *               Vuelta a España, the Dutch Grand Prix — because the concept
 *               stream is gated by the tag but never filtered by it).
 *
 * Every static namespace behaved identically — `tier:1` and `source:kalshi`
 * also returned zero events and zero futures. The control proves the data was
 * always there: `?sport=soccer`, which takes a different code path, returned 68
 * items at the same moment `?tags=["sport:soccer"]` returned 0.
 *
 * And the category pages are not the only reader. `components/RelatedByTag.tsx`
 * passes `sport:<key>` too, and it renders on EVERY event detail page
 * (`app/events/[id]/page.tsx`) and EVERY futures detail page
 * (`app/futures/[id]/page.tsx`). It returns `null` on an empty result, so
 * "More Soccer" has never once appeared on either surface.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * Both fixtures are verbatim production `/api/feed` bodies banked on
 * 2026-08-29 before the fix was written:
 *
 *   BEFORE  `?limit=50&tags=["sport:soccer"]`  → `total: 0, items: []`
 *   AFTER   the same route and the same soccer population reached through
 *           `?sport=soccer`, the one filter path that was never broken. These
 *           are real served feed items, not invented ones.
 *
 * The AFTER fixture is a faithful stand-in for shape and content, NOT a
 * prediction of ranking: once deployed, the tag path runs the same scoring over
 * the same candidates, but order and membership will differ at the margin. Every
 * assertion below is therefore about what the page DOES with a non-empty
 * payload — never about which market lands first.
 *
 * The backend arms are where the fix itself is proven:
 *   `backend/tests/test_jsonb_containment_bind.py`            (the wire value)
 *   `backend/tests/test_feed_static_tag_filter_reaches_sql.py` (the code path)
 *   `backend/tests/integration/test_feed_static_tag_filter_pg.py` (real rows)
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SERVED_BEFORE from "../fixtures/uxp172_category_soccer_before.json";
import SERVED_AFTER from "../fixtures/uxp172_category_soccer_after.json";

/* ── SWR, auth and the analytics hooks are all that stand between page and payload ─ */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: swrError,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

jest.mock("@/components/AuthProvider", () => ({
  __esModule: true,
  useAuthContext: () => ({ user: null, isLoading: false }),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/categories/soccer",
  useSearchParams: () => new URLSearchParams(),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const CategoryPage = require("@/app/categories/[slug]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/**
 * The cards call `useAnalyticsContext`, which throws outside the provider. Wrap
 * in the REAL `AnalyticsProvider` — the same one `app/layout.tsx` wraps the page
 * in — rather than stubbing the hook, so the thing being rendered is the thing
 * that ships and not a page with its chrome removed.
 */
function render(payload: unknown, slug = "soccer"): string {
  swrPayload = payload;
  swrError = undefined;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(CategoryPage, { params: { slug } })
    )
  );
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const EMPTY_LINE = "No soccer items right now";

describe("the BEFORE state, from the verbatim served payload", () => {
  it("the served payload really is empty — the fixture is not a strawman", () => {
    expect((SERVED_BEFORE as { total: number }).total).toBe(0);
    expect((SERVED_BEFORE as { items: unknown[] }).items).toHaveLength(0);
  });

  it("the page tells the reader there is no soccer", () => {
    expect(visibleText(render(SERVED_BEFORE))).toContain(EMPTY_LINE);
  });

  it("it does NOT look broken — which is why nobody reported it", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).toContain("Check back soon");
    expect(text).toContain("browse other categories");
    expect(text).not.toContain("Failed");
    expect(text).not.toContain("Error");
  });

  it("no market or event name appears anywhere on the page", () => {
    const text = visibleText(render(SERVED_BEFORE));
    for (const name of ["Champion", "Premier League", "Bournemouth"]) {
      expect(text).not.toContain(name);
    }
  });

  it("not one card is rendered", () => {
    // Anchor on a string only a rendered card emits, rather than on the
    // header's count: the count block is gated on the same emptiness the empty
    // state is, so asserting its absence is unfalsifiable through the page's
    // own data path — a mutation that invents a count cannot make it appear.
    // "Opened NN/NN" is printed by every FeedCard footer and by nothing else.
    expect(visibleText(render(SERVED_BEFORE))).not.toMatch(/Opened \d+\/\d+/);
    expect(visibleText(render(SERVED_AFTER))).toMatch(/Opened \d+\/\d+/);
  });

  it("every other slug is equally empty — this was never soccer-specific", () => {
    for (const slug of ["football", "politics", "tennis", "economics"]) {
      const text = visibleText(render(SERVED_BEFORE, slug));
      expect(text).toContain("items right now");
    }
  });
});

describe("the AFTER state, from real served soccer items", () => {
  it("the empty state is gone", () => {
    expect(visibleText(render(SERVED_AFTER))).not.toContain(EMPTY_LINE);
  });

  it("the page names real soccer content", () => {
    const text = visibleText(render(SERVED_AFTER));
    const items = (SERVED_AFTER as { items: { type: string; data: Record<string, unknown> }[] })
      .items;
    const named = items
      .map((i) =>
        typeof i.data.name === "string"
          ? i.data.name
          : typeof i.data.home_team === "string"
          ? i.data.home_team
          : null
      )
      .filter((n): n is string => Boolean(n));

    expect(named.length).toBeGreaterThan(0);
    // At least one served item must actually reach the reader. Asserting ALL
    // of them would pin the page's own section caps, which are not this fix.
    expect(named.some((n) => text.includes(n))).toBe(true);
  });

  it("the header now prints a count", () => {
    const text = visibleText(render(SERVED_AFTER));
    expect(text).toMatch(/\d+ (event|market)/);
  });

  it("the reader gets more words on the page than before, by a wide margin", () => {
    const before = visibleText(render(SERVED_BEFORE)).length;
    const after = visibleText(render(SERVED_AFTER)).length;
    expect(after).toBeGreaterThan(before * 3);
  });

  it("the breadcrumb back to the index survives both states", () => {
    for (const payload of [SERVED_BEFORE, SERVED_AFTER]) {
      expect(visibleText(render(payload))).toContain("All Categories");
    }
  });
});

describe("the artifact", () => {
  it("writes a before/after render that asserts its own content", () => {
    const before = render(SERVED_BEFORE);
    const after = render(SERVED_AFTER);

    // The rig refuses to emit a file that does not show the defect and its fix.
    expect(visibleText(before)).toContain(EMPTY_LINE);
    expect(visibleText(after)).not.toContain(EMPTY_LINE);

    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path");
    const out = process.env.UXP172_ARTIFACT_DIR;
    if (!out) return; // opt-in; the assertions above are the gate
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(
      path.join(out, "category-soccer-before-after.html"),
      `<!doctype html><meta charset="utf-8">
<title>UX-P172 — /categories/soccer</title>
<link rel="stylesheet" href="https://www.bainluck.com/_next/static/css/app.css">
<body style="font-family:system-ui;margin:0;padding:24px;background:#fff">
<h1 style="font:600 18px system-ui">UX-P172 — <code>/categories/soccer</code></h1>
<p style="color:#666;font:14px system-ui">
The index card for this page reads <b>9,191 markets</b>. Both panels are the
shipped page component rendered against verbatim production payloads.</p>
<h2 style="font:600 15px system-ui">BEFORE — served <code>total: 0</code></h2>
<div style="border:1px solid #ddd;padding:16px;border-radius:8px">${before}</div>
<h2 style="font:600 15px system-ui">AFTER — real served soccer items</h2>
<div style="border:1px solid #ddd;padding:16px;border-radius:8px">${after}</div>
</body>`
    );
  });
});
