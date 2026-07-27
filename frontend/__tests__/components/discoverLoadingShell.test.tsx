/**
 * L2-189 Item 3 — server-visible loading shell.
 *
 * Renders the shell to STATIC markup (the server-HTML path, no hydration) and
 * asserts it contains the loading structure with stable dimensions, and that it
 * is purely presentational (no data, no fetch). renderToStaticMarkup runs in
 * the jest 'node' environment, mirroring the App Router server render.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import DiscoverSkeletonGrid from "@/components/discover/DiscoverSkeletonGrid";
import DiscoverLoading from "@/app/discover/loading";

describe("DiscoverSkeletonGrid", () => {
  it("renders the default 9 stable-dimension card placeholders in server HTML", () => {
    const html = renderToStaticMarkup(React.createElement(DiscoverSkeletonGrid));
    // Loading structure present.
    expect(html).toContain("animate-pulse");
    expect(html).toContain('data-testid="discover-skeleton"');
    // Stable dimensions: fixed media band height + masonry columns.
    expect(html).toContain("h-44");
    expect(html).toContain("columns-1");
    expect(html).toContain("lg:columns-3");
    // 9 media bands (one per placeholder card).
    expect((html.match(/h-44/g) || []).length).toBe(9);
    // Decorative only.
    expect(html).toContain('aria-hidden="true"');
  });

  it("honors an explicit count", () => {
    const html = renderToStaticMarkup(
      React.createElement(DiscoverSkeletonGrid, { count: 3 })
    );
    expect((html.match(/h-44/g) || []).length).toBe(3);
  });
});

describe("DiscoverLoading boundary", () => {
  it("renders header chrome + skeleton grid, with no feed data in the HTML", () => {
    const html = renderToStaticMarkup(React.createElement(DiscoverLoading));
    expect(html).toContain("Discover");
    expect(html).toContain('data-testid="discover-skeleton"');
    expect(html).toContain("min-h-screen");
    // No personalized / feed payload markers leak into the shell HTML.
    expect(html).not.toContain("%");
    expect(html.toLowerCase()).not.toContain("probability");
  });
});
