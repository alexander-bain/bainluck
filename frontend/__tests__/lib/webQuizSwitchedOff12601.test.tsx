// #12601 — Switch off the web quiz (Daily Challenge and guess cards) until it's done well.
//
// Completes the web checklist corresponding to the iPhone's #6445 / #6501 / #7075:
//   1. One switch (`CHALLENGE_SURFACES_ENABLED = false` in `lib/launchSurfaces.ts`)
//      controls the entire web quiz surface, gated rather than deleted.
//   2. `/daily` (`app/daily/page.tsx`) reads `CHALLENGE_SURFACES_ENABLED`, skips
//      `fetchFeed` and its timer, calls `router.replace("/discover")` in `useEffect`
//      so visiting `/daily` lands on Discover (no dead end), and renders a held-back
//      fallback (`data-testid="daily-held-back"`) linking to `/discover` with all
//      three GA4 hooks (`usePageTracking`, `useScrollDepth`, `useEngagementTime`)
//      preserved above the early return.
//   3. Every quiz component (`DailyChallengeCard`, `GuessCard`, `ResolutionCard`,
//      `ResolutionGroup`, `ChallengeModal`) across `app/` and `components/` is
//      scanned to ensure no ungated mount exists anywhere in the web app, and
//      nav/footer/sitemap/sign-in prompts carry no ungated quiz entry points.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: jest.fn(),
    push: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

const FRONTEND_ROOT = path.join(__dirname, "..", "..");
const SCANNED_DIRS = ["app", "components"];
const FLAG_TOKEN = "CHALLENGE_SURFACES_ENABLED";

const QUIZ_COMPONENTS = [
  "DailyChallengeCard",
  "GuessCard",
  "ResolutionCard",
  "ResolutionGroup",
  "ChallengeModal",
] as const;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (/\.tsx?$/.test(entry.name)) out.push(full);
  }
  return out;
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");
}

function mountedQuizComponents(source: string): string[] {
  const code = stripComments(source);
  return QUIZ_COMPONENTS.filter((comp) => {
    const openTag = new RegExp(`<${comp}\\b`);
    return openTag.test(code);
  });
}

describe("#12601 — `/daily` is switched off behind CHALLENGE_SURFACES_ENABLED and sends readers to Discover", () => {
  function renderDailyPage(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Page = require("@/app/daily/page").default as React.ComponentType;
    return renderToStaticMarkup(React.createElement(Page));
  }

  it("renders the held-back redirect shell, not the Daily Challenge quiz", () => {
    const html = renderDailyPage();
    expect(html).toContain('data-testid="daily-held-back"');
    expect(html).toContain('href="/discover"');
    expect(html).not.toContain('data-testid="daily-page"');
    expect(html).not.toContain("Five probability calls");
    expect(html).not.toContain("Question 1 of");
    expect(html).not.toContain("Today&#x27;s Questions");
    expect(html).not.toContain("Your record");
  });

  it("redirects `/daily` to `/discover` and skips `fetchFeed` when CHALLENGE_SURFACES_ENABLED is false", () => {
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "daily", "page.tsx"),
      "utf8",
    );

    const redirectGuard = source.indexOf(`if (!${FLAG_TOKEN}) {\n      router.replace("/discover");`);
    expect(redirectGuard).toBeGreaterThan(-1);

    const loadGuard = source.indexOf(`if (!${FLAG_TOKEN}) return;`);
    const fetchCall = source.indexOf("fetchFeed(");
    expect(loadGuard).toBeGreaterThan(-1);
    expect(fetchCall).toBeGreaterThan(-1);
    expect(loadGuard).toBeLessThan(fetchCall);
  });

  it("keeps the early return below the three mandatory GA4 analytics hooks", () => {
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "daily", "page.tsx"),
      "utf8",
    );
    const earlyReturn = source.indexOf(
      `if (!${FLAG_TOKEN}) {\n    return (`,
    );
    expect(earlyReturn).toBeGreaterThan(-1);

    for (const hook of ["usePageTracking(", "useScrollDepth(", "useEngagementTime("]) {
      const at = source.indexOf(hook);
      expect(at).toBeGreaterThan(-1);
      expect(at).toBeLessThan(earlyReturn);
    }
  });

  it("GATED, NOT DELETED: `/daily` remains intact when CHALLENGE_SURFACES_ENABLED is true", () => {
    let html = "";
    jest.isolateModules(() => {
      jest.doMock("@/lib/launchSurfaces", () => ({ CHALLENGE_SURFACES_ENABLED: true }));
      /* eslint-disable @typescript-eslint/no-var-requires */
      const ReactLocal = require("react") as typeof React;
      const { renderToStaticMarkup: render } =
        require("react-dom/server") as typeof import("react-dom/server");
      const Page = require("@/app/daily/page").default as React.ComponentType;
      /* eslint-enable @typescript-eslint/no-var-requires */
      html = render(ReactLocal.createElement(Page));
    });
    jest.dontMock("@/lib/launchSurfaces");

    expect(html).not.toContain('data-testid="daily-held-back"');
    expect(html).toContain("animate-spin");
  });
});

describe("#12601 — scan: every quiz component and entry point across the web app is gated", () => {
  const files = SCANNED_DIRS.flatMap((d) => walk(path.join(FRONTEND_ROOT, d)));

  it("CONTROL: mountedQuizComponents catches a fabricated JSX mount and ignores comments", () => {
    expect(mountedQuizComponents(`<DailyChallengeCard guessesToday={0} onStart={fn} />`)).toEqual([
      "DailyChallengeCard",
    ]);
    expect(mountedQuizComponents(`<GuessCard item={item} />`)).toEqual(["GuessCard"]);
    expect(mountedQuizComponents(`// <GuessCard item={item} />`)).toEqual([]);
  });

  it("no file outside `app/discover/page.tsx` mounts any quiz card or modal", () => {
    const mounts: string[] = [];
    for (const file of files) {
      const rel = path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
      const found = mountedQuizComponents(fs.readFileSync(file, "utf8"));
      for (const comp of found) {
        mounts.push(`${rel} → <${comp}>`);
      }
    }

    expect(mounts.sort()).toEqual([
      "app/discover/page.tsx → <ChallengeModal>",
      "app/discover/page.tsx → <DailyChallengeCard>",
      "app/discover/page.tsx → <GuessCard>",
      "app/discover/page.tsx → <ResolutionCard>",
      "app/discover/page.tsx → <ResolutionGroup>",
    ]);
  });

  it("gates ChallengeModal and startChallenge on CHALLENGE_SURFACES_ENABLED in `app/discover/page.tsx`", () => {
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "discover", "page.tsx"),
      "utf8",
    );
    const lines = source.split("\n");
    const modalLine = lines.findIndex((l) => l.includes("<ChallengeModal"));
    expect(modalLine).toBeGreaterThan(-1);
    const windowAbove = lines.slice(Math.max(0, modalLine - 3), modalLine + 1).join("\n");
    expect(windowAbove).toContain(`${FLAG_TOKEN} && challengeOpen &&`);

    const startChallengeIdx = source.indexOf("const startChallenge = useCallback(() => {");
    expect(startChallengeIdx).toBeGreaterThan(-1);
    const startBlock = source.slice(startChallengeIdx, startChallengeIdx + 160);
    expect(startBlock).toContain(`if (!${FLAG_TOKEN}) return;`);
  });

  it("keeps `/daily` and prediction routes out of the public sitemap and navigation chrome", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const sitemapFn = require("@/app/sitemap").default as () => Array<{ url: string }>;
    const urls = sitemapFn().map((entry) => entry.url);
    for (const route of ["/daily", "/discover/stats", "/discover/scorecard", "/challenge", "/play"]) {
      expect(urls.some((u) => u.endsWith(route))).toBe(false);
    }

    for (const rel of [
      "components/DesktopNav.tsx",
      "components/BottomNav.tsx",
      "components/Footer.tsx",
      "components/UserMenu.tsx",
      "components/discover/SignInToPersonalizeInvite.tsx",
      "app/my-stuff/page.tsx",
      "app/onboarding/page.tsx",
    ]) {
      const src = stripComments(fs.readFileSync(path.join(FRONTEND_ROOT, rel), "utf8"));
      expect(src).not.toContain('"/daily"');
      expect(src).not.toContain('"/discover/stats"');
      expect(src).not.toContain("Daily Challenge");
    }
  });
});
