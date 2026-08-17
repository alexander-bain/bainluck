// UX-P087 (#1909) — Discover's honest state when the feed cannot be loaded.
//
// ── WHAT WAS ACTUALLY MEASURED, BECAUSE THE FILED PREMISE WAS WRONG ──
//
// #1909 reports "Discover renders a BLANK main region when /api/feed fails". It
// does not. Browser-audit run 32009921496, journey `consent.two_tabs`, is the
// evidence the issue cites, and its terminal screenshot — opened this cycle —
// shows the page rendering "Failed to load feed / Try again" while every request
// on it 429'd. The header, nav and search all painted normally.
//
// What made the rail say "main region rendered blank" is that the consent spec's
// `mainNonBlank` helper is `text.trim().length > 40` and that state's whole text
// is 29 characters. A correct short state and a genuinely empty one are the same
// number to that check, and the assertion's detail states the emptier reading as
// a fact (gotcha #53). The instrument half is fixed in `helpers/journey.js`.
//
// The product half is real and is what this file guards. TWO defects, both
// visible in that screenshot once you know what you are looking at:
//
//   1. The state named neither a why nor a when — the exact empty state ruling
//      027 calls the specific death of an auto-generated page. A reader could
//      not tell a rate limit from an outage from their own dead wifi.
//   2. `Try again` was `window.location.reload()`. On a 429 — the failure that
//      actually happens, several household members or several tabs behind one
//      address — a full document reload re-fires every request on the page and
//      is rate-limited again. The single control offered was the one action
//      guaranteed not to work.
//
// Both directions, per gotcha #43: the honest state must appear when the feed
// fails AND must not latch over a feed that recovers.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import FeedUnavailableNotice, {
  type FeedFailureReason,
} from "../../components/discover/FeedUnavailableNotice";

const PAGE_SOURCE: string = jest.requireActual("fs").readFileSync(
  require("path").join(__dirname, "..", "..", "app", "discover", "page.tsx"),
  "utf8",
);

const render = (reason: FeedFailureReason) =>
  renderToStaticMarkup(
    <FeedUnavailableNotice onRetry={() => {}} variant="empty" reason={reason} />,
  );

/**
 * The text a reader actually sees, which is what the blank-region check measures.
 *
 * The entity decode matters: `renderToStaticMarkup` escapes apostrophes to
 * `&#x27;`, so a naive tag-strip turns "didn't" into "didn&#x27;t" and a copy
 * assertion silently stops matching the words on screen — a test measuring the
 * markup while claiming to measure the reading.
 */
const visibleText = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();

describe("#1909 — every feed failure class renders a NAMED, non-blank state", () => {
  const CLASSES: FeedFailureReason[] = ["rate_limited", "error", "unavailable"];

  test.each(CLASSES)("%s: names a why and a when, and offers a retry", (reason) => {
    const html = render(reason);
    expect(html).toContain('role="alert"');
    expect(html).toContain(`data-reason="${reason}"`);
    expect(html).toContain("<button");
    expect(html).toContain('aria-label="Try again to load the feed"');

    // Ruling 027's named death: "an empty state that says 'check back later' and
    // names neither a why nor a when". Each state must say what happened...
    const text = visibleText(html);
    expect(text.length).toBeGreaterThan(60);
    // ...and when it changes. Every class states a time horizon or an explicit
    // "we don't know which side failed"; none of them is a bare "try again".
    expect(text).toMatch(/minute|second|didn't come back/i);
  });

  test.each(CLASSES)("%s: clears the rail's blank-region threshold by a margin", (reason) => {
    // The consent pack grades `main` at `> 40` characters. Every honest state
    // must be unambiguously above it — not because the threshold is the bar, but
    // because a state that sits near it is one that can be graded blank while
    // being correct, which is the misfiling this issue came from.
    expect(visibleText(render(reason)).length).toBeGreaterThan(80);
  });

  test("the three classes say DIFFERENT things — a shared sentence is no diagnosis", () => {
    const texts = CLASSES.map((r) => visibleText(render(r)));
    expect(new Set(texts).size).toBe(CLASSES.length);
    // A rate limit is the one a reader can act on by waiting; it must say so.
    expect(visibleText(render("rate_limited"))).toMatch(/clears on its own within a minute/i);
  });

  test("no class claims the feed ENDED — an outage is not a quiet day", () => {
    for (const reason of CLASSES) {
      const text = visibleText(render(reason)).toLowerCase();
      expect(text).not.toContain("caught up");
      expect(text).not.toContain("that's everything");
      expect(text).not.toContain("no more");
      expect(text).not.toContain("check back later");
    }
  });
});

describe("#1909 — the retry is a feed revalidation, not a document reload", () => {
  test("the failure branch's handler mutates the feed", () => {
    expect(PAGE_SOURCE).toContain("const handleRetryFailedLoad");
    const handler = PAGE_SOURCE.slice(
      PAGE_SOURCE.indexOf("const handleRetryFailedLoad"),
      PAGE_SOURCE.indexOf("const handleRetryFailedLoad") + 200,
    );
    expect(handler).toContain("mutateFeed()");
    expect(handler).not.toContain("location.reload");
  });

  test("NO surviving reload in Discover's feed-failure path", () => {
    // The regression this pins: the old branch's only control was
    // `window.location.reload()`, which on a 429 re-fires every request on the
    // page. The ErrorBoundary fallback keeps its reload deliberately — a render
    // crash genuinely does want a fresh document — so this asserts the count,
    // not the absence.
    //
    // Counting CALL SITES, not the string: the first draft matched
    // `/location\.reload\(\)/g` and found two, the second being this queue's own
    // doc comment explaining why the reload was removed. A grep that cannot tell
    // code from prose about the code reports the fix as the defect.
    const reloads = PAGE_SOURCE.match(/onClick=\{\(\) => window\.location\.reload\(\)\}/g) ?? [];
    expect(reloads).toHaveLength(1);
    const boundary = PAGE_SOURCE.slice(
      PAGE_SOURCE.indexOf("<ErrorBoundary"),
      PAGE_SOURCE.indexOf("<ErrorBoundary") + 400,
    );
    expect(boundary).toContain("location.reload()");
  });
});

describe("#1909 — the other direction (gotcha #43): a recovering feed is not latched", () => {
  test("the failure branch is derived from SWR state, holding no error flag of its own", () => {
    // `{!isLoading && feedError && !data && (` — three live values, no useState.
    // A `setHasError(true)` anywhere in this path would survive the recovery that
    // clears `feedError`, and the reader would be stuck on an error over a
    // working feed. Asserting the SHAPE is what keeps that from being reintroduced.
    expect(PAGE_SOURCE).toContain("{!isLoading && feedError && !data && (");
    expect(PAGE_SOURCE).not.toMatch(/set(Feed)?(Load)?Error\s*\(/);
  });

  test("the class is computed from the live error, not remembered", () => {
    expect(PAGE_SOURCE).toContain("const feedFailureReason: FeedFailureReason =");
    const decl = PAGE_SOURCE.slice(
      PAGE_SOURCE.indexOf("const feedFailureReason"),
      PAGE_SOURCE.indexOf("const feedFailureReason") + 220,
    );
    expect(decl).toContain("feedError");
    expect(decl).toContain("429");
    expect(decl).not.toContain("useState");
  });
});
