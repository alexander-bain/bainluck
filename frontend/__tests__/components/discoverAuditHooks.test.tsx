// L2-223 Item 3 — the browser-audit rail's Discover hooks.
//
// The rail used to identify a rendered card by `main div.break-inside-avoid`,
// a Tailwind LAYOUT class that `DiscoverSkeletonGrid` also carries. A Discover
// stuck on skeletons therefore satisfied "a real card was visible", recorded a
// plausible first-card latency, and the audit reported GREEN — the C96 [P1]
// false green, reached through the selector instead of the `.catch()` L2-221
// removed. It identified the empty state by the copy string "You're all caught
// up", so an editorial reword would silently have turned a proven empty state
// into an unproven blank page.
//
// These hooks are now load-bearing evidence, not conveniences. This suite is
// the tripwire: if a hook is dropped, renamed, or leaks onto the skeleton, CI
// fails here rather than the audit quietly going green on nothing. Runs in the
// node/SSR env (renderToStaticMarkup) — no jsdom, no SWR.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("@/lib/analytics", () => ({
  trackEvent: jest.fn(),
}));

import EndOfFeedCard from "../../components/discover/EndOfFeedCard";
import DiscoverSkeletonGrid from "../../components/discover/DiscoverSkeletonGrid";

const noop = () => {};

/** Count non-overlapping occurrences of a literal in a string. */
function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("Discover empty state carries a stable, named audit hook", () => {
  test("renders data-testid and a machine-readable state name", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={0} onRefresh={noop} />);
    expect(html).toContain('data-testid="discover-empty-state"');
    // The NAME is data, not scraped prose — the audit records this attribute
    // rather than the visible copy, so a reword cannot invalidate the evidence.
    expect(html).toContain('data-empty-state-name="no-markets"');
  });

  test("distinguishes an exhausted feed from a feed that never had anything", () => {
    const exhausted = renderToStaticMarkup(<EndOfFeedCard count={137} onRefresh={noop} />);
    expect(exhausted).toContain('data-empty-state-name="end-of-feed"');
    expect(exhausted).not.toContain('data-empty-state-name="no-markets"');
  });

  test("the hook is unique — one element, not a class sprayed across children", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={5} onRefresh={noop} />);
    expect(occurrences(html, 'data-testid="discover-empty-state"')).toBe(1);
  });

  test("keeps the accessible semantics alongside the test hook", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={5} onRefresh={noop} />);
    // A status role announces the state to assistive tech; the hook is additive.
    expect(html).toContain('role="status"');
    expect(html).toContain("all caught up");
    expect(html).toContain("Refresh feed");
  });
});

describe("the loading skeleton is never mistaken for content", () => {
  test("carries its own hook and NOT the card hook", () => {
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid />);
    expect(html).toContain('data-testid="discover-skeleton"');
    // This is the entire point of the change: the skeleton must be
    // distinguishable from a rendered card by the audit's selector.
    expect(html).not.toContain('data-testid="discover-card"');
    expect(html).not.toContain('data-testid="discover-empty-state"');
  });

  test("is still hidden from assistive tech", () => {
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid />);
    expect(html).toContain('aria-hidden="true"');
  });

  test("still shares the layout class with real cards — which is why the hook was needed", () => {
    // Documents the collision rather than asserting it away: `break-inside-avoid`
    // is a masonry primitive both states legitimately use. The selector was
    // wrong; the styling is not.
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid count={2} />);
    expect(html).toContain("break-inside-avoid");
  });
});

describe("the Discover page source renders the hooks the audit selects", () => {
  // The feed grid and the error branch live inside a large client component
  // with hooks and SWR, so they are asserted at the source level rather than
  // rendered. A rendering test here would prove less and break more.
  const source: string = jest.requireActual("fs").readFileSync(
    require("path").join(__dirname, "..", "..", "app", "discover", "page.tsx"),
    "utf8"
  );

  test("the feed item wrapper carries the card hook", () => {
    expect(source).toContain('data-testid="discover-card"');
  });

  test("the load-failure branch has its own hook and is not an empty state", () => {
    expect(source).toContain('data-testid="discover-feed-error"');
    expect(source).toContain('role="alert"');
    // "Failed to load feed" must never be reachable through the empty-state
    // hook — an error is not a legitimate empty feed, and conflating them is
    // how a broken deploy reads as a quiet day.
    const errorBlockIndex = source.indexOf('data-testid="discover-feed-error"');
    const errorBlock = source.slice(errorBlockIndex, errorBlockIndex + 400);
    expect(errorBlock).not.toContain("discover-empty-state");
  });
});
