// #12601 — Switch off the web quiz (Daily Challenge and guess cards) until it's done well.
//
// Completes the web checklist corresponding to the iPhone's #6445 / #6501 / #7075:
//   1. One switch (`CHALLENGE_SURFACES_ENABLED = false` in `lib/launchSurfaces.ts`)
//      controls the entire web quiz surface, gated rather than deleted.
//   2. Every quiz route page (`/daily`, `/challenge/[id]`, `/discover/scorecard`,
//      `/discover/stats`) reads `CHALLENGE_SURFACES_ENABLED`, skips its quiz/stats
//      API fetch, sends the reader to `/discover` (no dead end), and renders a
//      held-back fallback linking to `/discover` with all three GA4 hooks
//      (`usePageTracking`, `useScrollDepth`, `useEngagementTime`) preserved.
//   3. `/play` (the unlisted kids' rating game) stays on by design and is
//      explicitly documented as excluded from the public quiz switch.
//   4. Both a component-mount scan and a route-page scan across `app/` and
//      `components/` (with synthetic controls) fail if any page under `daily`,
//      `challenge`, `discover/stats`, or `discover/scorecard`, or any page calling
//      the predictions/challenges API, does not read `CHALLENGE_SURFACES_ENABLED`.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({
    track: jest.fn(),
  }),
}));

const mockRedirect = jest.fn();
const mockReplace = jest.fn();

jest.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => mockRedirect(...args),
  useRouter: () => ({
    replace: mockReplace,
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

const QUIZ_ROUTE_PREFIXES = [
  "app/daily/",
  "app/challenge/",
  "app/discover/stats/",
  "app/discover/scorecard/",
] as const;

const QUIZ_API_NEEDLES = [
  "/api/predictions",
  "/api/challenges",
  "fetchResolutions",
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

/**
 * Returns the reason a route `page.tsx` file is part of the public quiz/prediction
 * surface and must read `CHALLENGE_SURFACES_ENABLED`, or `null` if it is not.
 *
 * `/play` (`app/play/**`) is the unlisted kids' rating game and stays on by
 * design (Fable 2026-11-11 on #12606).
 */
function quizRoutePageReason(relPath: string, rawSource: string): string | null {
  if (!relPath.endsWith("/page.tsx")) return null;
  if (relPath.startsWith("app/play/") || relPath.startsWith("app/admin/")) return null;

  for (const prefix of QUIZ_ROUTE_PREFIXES) {
    if (relPath.startsWith(prefix)) {
      return `route:${prefix}`;
    }
  }

  const code = stripComments(rawSource);
  for (const needle of QUIZ_API_NEEDLES) {
    if (code.includes(needle)) {
      return `api:${needle}`;
    }
  }

  return null;
}

describe("#12601 — `/daily` is switched off behind CHALLENGE_SURFACES_ENABLED and sends readers to Discover", () => {
  beforeEach(() => {
    mockRedirect.mockClear();
    mockReplace.mockClear();
  });

  function renderDailyPage(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Page = require("@/app/daily/page").default as React.ComponentType;
    return renderToStaticMarkup(React.createElement(Page));
  }

  it("redirects in `app/daily/layout.tsx` on the server so `/daily` never flashes before landing on `/discover`", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const DailyLayout = require("@/app/daily/layout").default as React.ComponentType<{
      children: React.ReactNode;
    }>;
    renderToStaticMarkup(React.createElement(DailyLayout, null, "child"));
    expect(mockRedirect).toHaveBeenCalledWith("/discover");
  });

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
    const earlyReturn = source.indexOf(`if (!${FLAG_TOKEN}) {\n    return (`);
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

describe("#12601 — `/discover/scorecard` is switched off behind CHALLENGE_SURFACES_ENABLED and sends readers to Discover", () => {
  beforeEach(() => {
    mockRedirect.mockClear();
  });

  async function renderScorecardPage(): Promise<string> {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Page = require("@/app/discover/scorecard/page").default as (props: {
      searchParams: Promise<Record<string, string>>;
    }) => Promise<React.ReactElement>;
    const el = await Page({ searchParams: Promise.resolve({}) });
    return renderToStaticMarkup(el);
  }

  it("calls `redirect('/discover')`, renders the held-back state, and never prompts `Start Predicting`", async () => {
    const html = await renderScorecardPage();
    expect(mockRedirect).toHaveBeenCalledWith("/discover");
    expect(html).toContain('data-testid="scorecard-held-back"');
    expect(html).toContain('href="/discover"');
    expect(html).not.toContain("Think you can do better?");
    expect(html).not.toContain("Start Predicting");
  });

  it("GATED, NOT DELETED: `/discover/scorecard` renders the scorecard when CHALLENGE_SURFACES_ENABLED is true", async () => {
    let html = "";
    await new Promise<void>((resolve, reject) => {
      jest.isolateModules(() => {
        jest.doMock("@/lib/launchSurfaces", () => ({ CHALLENGE_SURFACES_ENABLED: true }));
        /* eslint-disable @typescript-eslint/no-var-requires */
        const ReactLocal = require("react") as typeof React;
        const { renderToStaticMarkup: render } =
          require("react-dom/server") as typeof import("react-dom/server");
        const Page = require("@/app/discover/scorecard/page").default as (props: {
          searchParams: Promise<Record<string, string>>;
        }) => Promise<React.ReactElement>;
        /* eslint-enable @typescript-eslint/no-var-requires */
        Page({
          searchParams: Promise.resolve({
            accuracy: "64",
            total: "11",
            correct: "7",
            streak: "2",
            best: "5",
          }),
        })
          .then((el) => {
            html = render(ReactLocal.cloneElement(el));
            resolve();
          })
          .catch(reject);
      });
    });
    jest.dontMock("@/lib/launchSurfaces");

    expect(html).not.toContain('data-testid="scorecard-held-back"');
    expect(html).toContain("64%");
    expect(html).toContain("Start Predicting");
  });
});

describe("#12601 — `/challenge/[id]` is switched off behind CHALLENGE_SURFACES_ENABLED and sends readers to Discover", () => {
  function renderChallengePage(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Page = require("@/app/challenge/[id]/page").default as React.ComponentType<{
      params: { id: string };
    }>;
    return renderToStaticMarkup(React.createElement(Page, { params: { id: "demo-code" } }));
  }

  it("renders the held-back state, not the friend challenge quiz or loader", () => {
    const html = renderChallengePage();
    expect(html).toContain('data-testid="challenge-held-back"');
    expect(html).toContain('href="/discover"');
    expect(html).not.toContain('data-testid="challenge-page"');
    expect(html).not.toContain('aria-label="Loading challenge"');
  });

  it("redirects `/challenge/[id]` to `/discover` and skips the `/api/challenges/` fetch when CHALLENGE_SURFACES_ENABLED is false", () => {
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "challenge", "[id]", "page.tsx"),
      "utf8",
    );

    const redirectGuard = source.indexOf(`if (!${FLAG_TOKEN}) {\n      router.replace("/discover");`);
    expect(redirectGuard).toBeGreaterThan(-1);

    const loadGuard = source.indexOf(`if (!${FLAG_TOKEN}) return;`);
    const fetchCall = source.indexOf("/api/challenges/");
    expect(loadGuard).toBeGreaterThan(-1);
    expect(fetchCall).toBeGreaterThan(-1);
    expect(loadGuard).toBeLessThan(fetchCall);
  });

  it("keeps the early return below the three mandatory GA4 analytics hooks", () => {
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "challenge", "[id]", "page.tsx"),
      "utf8",
    );
    const earlyReturn = source.indexOf(`if (!${FLAG_TOKEN}) {\n    return (`);
    expect(earlyReturn).toBeGreaterThan(-1);

    for (const hook of ["usePageTracking(", "useScrollDepth(", "useEngagementTime("]) {
      const at = source.indexOf(hook);
      expect(at).toBeGreaterThan(-1);
      expect(at).toBeLessThan(earlyReturn);
    }
  });

  it("GATED, NOT DELETED: `/challenge/[id]` remains intact when CHALLENGE_SURFACES_ENABLED is true", () => {
    let html = "";
    jest.isolateModules(() => {
      jest.doMock("@/lib/launchSurfaces", () => ({ CHALLENGE_SURFACES_ENABLED: true }));
      /* eslint-disable @typescript-eslint/no-var-requires */
      const ReactLocal = require("react") as typeof React;
      const { renderToStaticMarkup: render } =
        require("react-dom/server") as typeof import("react-dom/server");
      const Page = require("@/app/challenge/[id]/page").default as React.ComponentType<{
        params: { id: string };
      }>;
      /* eslint-enable @typescript-eslint/no-var-requires */
      html = render(ReactLocal.createElement(Page, { params: { id: "demo-code" } }));
    });
    jest.dontMock("@/lib/launchSurfaces");

    expect(html).not.toContain('data-testid="challenge-held-back"');
    expect(html).toContain('aria-label="Loading challenge"');
  });
});

describe("#12601 — scan: every quiz route page and component across the web app is gated", () => {
  const files = SCANNED_DIRS.flatMap((d) => walk(path.join(FRONTEND_ROOT, d)));

  it("CONTROL: `quizRoutePageReason` catches an ungated quiz route page (by path or API call) and ignores `/play` and ordinary pages", () => {
    expect(
      quizRoutePageReason(
        "app/discover/scorecard/page.tsx",
        `export default function ScorecardPage() { return <div>Start Predicting</div>; }`,
      ),
    ).toBe("route:app/discover/scorecard/");

    expect(
      quizRoutePageReason(
        "app/challenge/[id]/page.tsx",
        `export default function ChallengePage() { return <div />; }`,
      ),
    ).toBe("route:app/challenge/");

    expect(
      quizRoutePageReason(
        "app/some-new-quiz/page.tsx",
        `fetch("/api/predictions/detailed-stats");`,
      ),
    ).toBe("api:/api/predictions");

    expect(
      quizRoutePageReason(
        "app/play/page.tsx",
        `fetch("/api/predictions");`,
      ),
    ).toBeNull();

    expect(
      quizRoutePageReason(
        "app/sports/page.tsx",
        `export default function SportsPage() { return <div />; }`,
      ),
    ).toBeNull();
  });

  it("every route page under `daily`, `challenge`, `discover/stats`, or `discover/scorecard` — or calling the predictions/challenges API — reads CHALLENGE_SURFACES_ENABLED", () => {
    const gatedInventory: string[] = [];
    const ungated: string[] = [];

    for (const file of files) {
      const rel = path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
      const raw = fs.readFileSync(file, "utf8");
      const reason = quizRoutePageReason(rel, raw);
      if (!reason) continue;

      const code = stripComments(raw);
      if (code.includes(FLAG_TOKEN)) {
        gatedInventory.push(`${rel} (${reason})`);
      } else {
        ungated.push(`${rel} (${reason})`);
      }
    }

    expect(ungated).toEqual([]);
    expect(gatedInventory.sort()).toEqual([
      "app/challenge/[id]/page.tsx (route:app/challenge/)",
      "app/daily/page.tsx (route:app/daily/)",
      "app/discover/page.tsx (api:fetchResolutions)",
      "app/discover/scorecard/page.tsx (route:app/discover/scorecard/)",
      "app/discover/stats/page.tsx (route:app/discover/stats/)",
    ]);
  });

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
      expect(src).not.toContain('"/discover/scorecard"');
      expect(src).not.toContain("Daily Challenge");
    }
  });
});
