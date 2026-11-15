/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

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

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("AboutPage Decision 189 behind NEXT_PUBLIC_ABOUT_189 (#12672)", () => {
  const originalEnv = process.env.NEXT_PUBLIC_ABOUT_189;
  let host: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeAll(() => {
    Object.defineProperty(global, "IntersectionObserver", {
      writable: true,
      configurable: true,
      value: class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    });
  });

  beforeEach(() => {
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
    if (originalEnv === undefined) {
      delete process.env.NEXT_PUBLIC_ABOUT_189;
    } else {
      process.env.NEXT_PUBLIC_ABOUT_189 = originalEnv;
    }
  });

  it("keeps the current About page when NEXT_PUBLIC_ABOUT_189 is off", () => {
    delete process.env.NEXT_PUBLIC_ABOUT_189;
    act(() => {
      root.render(React.createElement(AboutPage));
    });

    expect(host.querySelector('[data-testid="about-page-189"]')).toBeNull();
    expect(host.querySelector("h1")?.textContent).toBe("Bain Luck");
  });

  it("renders Alex and Fable's approved Decision 189 About copy and final Picture credits row when flagged on", () => {
    process.env.NEXT_PUBLIC_ABOUT_189 = "true";
    act(() => {
      root.render(React.createElement(AboutPage));
    });

    const pageRoot = host.querySelector('[data-testid="about-page-189"]');
    expect(pageRoot).not.toBeNull();
    const text = (host.textContent ?? "").replace(/\s+/g, " ").trim();

    expect(text).toContain("The real score for everything.");
    expect(text).toContain("What the world thinks will happen, as one clear percentage.");
    expect(text).toContain(
      "A scoreboard tells you who's ahead. It doesn't tell you who's going to win. Bain Luck does: for tonight's game, next year's election, the Oscars, the weather, the Fed.",
    );
    expect(text).toContain("One number.");
    expect(text).toContain(
      "Every day, thousands of people commit to what they expect will happen. We read the prediction markets and the sportsbooks and blend them into a single chance for each outcome.",
    );
    expect(text).toContain("How to read it.");
    expect(text).toContain(
      "64% means it happens about two times in three. It's the world's best guess, not a promise. Watch it move; the movement is the story.",
    );
    expect(text).toContain("Not betting.");
    expect(text).toContain("No odds to decode, no bets to place, nothing to buy.");
    expect(text).toContain("We keep score on ourselves.");
    expect(text).toContain(
      "Every finished game and settled market is checked against what we showed. See how we've done.",
    );

    // Retired betting-comparison bold line is gone
    expect(text).not.toContain("The same knowledge as a betting app");
    expect(text).not.toContain("None of the pull.");

    // Links match Fable's #12672 + Ruling 195-A spec
    const calibrationLink = host.querySelector('a[href="/calibration"]');
    expect(calibrationLink?.textContent).toBe("See how we've done.");

    const exploreLink = host.querySelector('a[href="/discover"]');
    expect(exploreLink?.textContent).toBe("Start exploring");

    const bottomRow = host.querySelector('[data-testid="about-bottom-links-row"]');
    expect(bottomRow).not.toBeNull();
    expect(bottomRow?.className).not.toMatch(/fixed|sticky/);
    const creditsLink = bottomRow?.querySelector('a[href="/picture-credits"]');
    expect(creditsLink?.textContent).toBe("Picture credits");
    expect(pageRoot?.lastElementChild).toBe(bottomRow);
  });
});
