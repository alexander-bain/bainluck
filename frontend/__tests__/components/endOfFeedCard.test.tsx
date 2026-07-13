// L2-109 Item 1: web Discover end-of-feed grace card (the #1087 web sibling).
// Replaces the abrupt silent stop / muted "N markets explored" line with a
// graceful "you're all caught up" card that offers a refresh affordance and
// category exploration links.

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

import EndOfFeedCard, { END_OF_FEED_CATEGORIES } from "../../components/discover/EndOfFeedCard";

const noop = () => {};

describe("EndOfFeedCard (L2-109 Item 1)", () => {
  test("shows the caught-up headline and market count when items were explored", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={137} onRefresh={noop} />);
    expect(html).toContain("all caught up");
    expect(html).toContain("137 markets explored");
    expect(html).toContain("check back soon");
  });

  test("omits the count phrasing in the empty (zero-item) state", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={0} onRefresh={noop} />);
    expect(html).toContain("all caught up");
    expect(html).not.toContain("markets explored");
    expect(html).toContain("new markets open throughout the day");
  });

  test("renders a refresh affordance (web has no pull-to-refresh)", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={10} onRefresh={noop} />);
    expect(html).toContain("Refresh feed");
  });

  test("renders category exploration links to every native category page", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={10} onRefresh={noop} />);
    for (const c of END_OF_FEED_CATEGORIES) {
      expect(html).toContain(`href="${c.href}"`);
      expect(html).toContain(c.label);
    }
    // Sanity: the abrupt silent-stop had none of these.
    expect(END_OF_FEED_CATEGORIES.length).toBeGreaterThanOrEqual(4);
  });
});
