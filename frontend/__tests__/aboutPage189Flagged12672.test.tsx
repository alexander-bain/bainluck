import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  usePathname: () => "/about",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

jest.mock("@/lib/api", () => ({
  __esModule: true,
  fetchCalibration: jest.fn().mockResolvedValue({ buckets: [] }),
}));

import AboutPage from "@/app/about/page";

function stripTags(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&apos;|&rsquo;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&middot;/g, "·")
    .replace(/&rarr;/g, "→")
    .replace(/\s+/g, " ")
    .trim();
}

describe("AboutPage Decision 189 behind NEXT_PUBLIC_ABOUT_189 (#12672)", () => {
  const originalEnv = process.env.NEXT_PUBLIC_ABOUT_189;

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.NEXT_PUBLIC_ABOUT_189;
    } else {
      process.env.NEXT_PUBLIC_ABOUT_189 = originalEnv;
    }
  });

  it("keeps the current About page when NEXT_PUBLIC_ABOUT_189 is off", () => {
    delete process.env.NEXT_PUBLIC_ABOUT_189;
    const html = renderToStaticMarkup(React.createElement(AboutPage));

    expect(html).not.toContain('data-testid="about-page-189"');
    expect(html).toContain(">Bain Luck</h1>");
  });

  it("renders Alex and Fable's approved Decision 189 About copy and final Picture credits row when flagged on", () => {
    process.env.NEXT_PUBLIC_ABOUT_189 = "true";
    const html = renderToStaticMarkup(React.createElement(AboutPage));
    const text = stripTags(html);

    expect(html).toContain('data-testid="about-page-189"');
    expect(text).toContain("The real score for everything.");
    expect(text).toContain("What the world thinks will happen, as one clear percentage.");
    expect(text).toContain(
      "A scoreboard tells you who's ahead. It doesn't tell you who's going to win. Bain Luck does: for tonight's game, next year's election, the Oscars, the weather, the Fed.",
    );
    expect(text).toContain(
      "One number. Every day, thousands of people commit to what they expect will happen. We read the prediction markets and the sportsbooks and blend them into a single chance for each outcome.",
    );
    expect(text).toContain("How to read it.");
    expect(text).toContain(
      "64% means it happens about two times in three. It's the world's best guess, not a promise. Watch it move; the movement is the story.",
    );
    expect(text).toContain("Not betting. No odds to decode, no bets to place, nothing to buy.");
    expect(text).toContain(
      "We keep score on ourselves. Every finished game and settled market is checked against what we showed. See how we've done.",
    );

    // Retired betting-comparison bold line is gone
    expect(text).not.toContain("The same knowledge as a betting app");
    expect(text).not.toContain("None of the pull.");

    // Links match Fable's #12672 + Ruling 195-A spec
    expect(html).toMatch(/href="\/calibration"[^>]*>See how we(?:&#x27;|')ve done\.<\/a>/);
    expect(html).toMatch(/href="\/discover"[^>]*>Start exploring<\/a>/);
    expect(html).toMatch(/href="\/picture-credits"[^>]*>Picture credits<\/a>/);

    // Final row is in page flow (not fixed or sticky) and appears after Start exploring
    expect(html).toContain('data-testid="about-bottom-links-row"');
    expect(html).not.toMatch(/data-testid="about-bottom-links-row"[^>]*(?:fixed|sticky)/);
    expect(html.indexOf(">Start exploring</a>")).toBeLessThan(
      html.indexOf('data-testid="about-bottom-links-row"'),
    );
  });
});
