// #8187 — the web has no ungated door into the predictions experience.
//
// #6445 switched the Higher/Lower prediction game off for the initial release.
// Two sweeps then found surfaces it had missed — #6501 (the signed-out My Stuff
// wall) and #6646 (Browse's challenge tile) — and #8187 found a third on the
// most reachable surface of all: an unlabelled 18x18 icon in the Discover
// header, on the DEFAULT LANDING PAGE, opening `/discover/stats`.
//
// ── WHY THIS FILE IS A SCAN AND NOT THREE MORE ASSERTIONS ───────────────────
//
// `challengeSurfacesHiddenForLaunch6445.test.ts` already asserts that three
// NAMED render sites on `app/discover/page.tsx` read the flag. Those assertions
// were all passing on the day the fourth door was photographed, because a guard
// that names its sites can only ever confirm the sites someone already thought
// of — and the whole failure mode here is the site nobody thought of. The iOS
// twin records the same history twice over: `ReleaseSurfaces`' docstring says a
// scan keyed on `Route.predictionStats` is what made its "one flip restores it"
// claim true, and then #7075 found a seventh and eighth entry point that
// contained no route token at all.
//
// So the first describe below does not know about any particular door. It walks
// the app and asks a general question — does anything navigate a reader into the
// predictions route family without reading the launch flag — and a fifth door
// added in a file nobody has edited yet fails it.
//
// ── THE CONTROL IS THE PART THAT MAKES THE SCAN WORTH HAVING ────────────────
//
// A scan over a tree that currently has zero violations passes identically to a
// scan whose matcher is broken, whose route list is misspelled, or whose file
// walk returns nothing. All three have shipped in this repo. The synthetic
// control below runs the SAME matcher over a fabricated ungated door and
// requires it to be caught, so a green run here means "looked and found none"
// rather than "did not look".

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// The three GA4 hooks reach for `usePathname` and the analytics context, which
// exist only under a router and a provider. They are not what is being proved
// here, so they are stubbed — and because stubbing them would also hide the one
// way this change could break them, the last test in the final describe reads
// the source to check the new early return still sits BELOW all three.
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

const FRONTEND_ROOT = path.join(__dirname, "..", "..");
const SCANNED_DIRS = ["app", "components"];

// The routes that make up the held-back experience. `/discover/stats` is the
// door #8187 found; the other three are its siblings, reachable by URL but
// currently linked from nowhere, and they are in the list so that a future edit
// cannot quietly promote one of them instead.
const PREDICTION_ROUTES = [
  "/discover/stats",
  "/discover/scorecard",
  "/play",
  "/daily",
];

const FLAG_TOKEN = "CHALLENGE_SURFACES_ENABLED";

/**
 * Every way this codebase actually sends a reader somewhere: a `Link`/anchor
 * `href`, and the imperative router verbs. Deliberately NOT a bare search for
 * the route string — `/play` appears inside prose, class names and unrelated
 * paths, and a matcher that fires on those would be turned off within a week.
 */
function navigationsInto(source: string): string[] {
  const hits: string[] = [];
  for (const route of PREDICTION_ROUTES) {
    const escaped = route.replace(/\//g, "\\/");
    const patterns = [
      // href="/play"  |  href='/play'  |  href={"/play"}
      new RegExp(`href=\\{?["'\`]${escaped}["'\`]`),
      // router.push("/play") | .replace("/play") | .prefetch("/play")
      new RegExp(`\\.(push|replace|prefetch)\\(\\s*["'\`]${escaped}["'\`]`),
    ];
    if (patterns.some((p) => p.test(source))) hits.push(route);
  }
  return hits;
}

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

describe("#8187 — the scan: nothing navigates into the predictions family ungated", () => {
  const files = SCANNED_DIRS.flatMap((d) => walk(path.join(FRONTEND_ROOT, d)));

  it("actually walked the app (a scan over zero files passes vacuously)", () => {
    // Not a pinned count — a pinned count is a chore every time a page is
    // added. A floor, because the failure this catches is a walk that returned
    // nothing at all.
    expect(files.length).toBeGreaterThan(100);
    expect(files.some((f) => f.endsWith(path.join("app", "discover", "page.tsx")))).toBe(true);
  });

  it("CONTROL: the same matcher catches a fabricated ungated door", () => {
    // If this ever fails, every pass below is meaningless.
    const fabricated = `
      import Link from "next/link";
      export default function Nav() {
        return <Link href="/play">Play</Link>;
      }
    `;
    expect(navigationsInto(fabricated)).toEqual(["/play"]);
    expect(fabricated.includes(FLAG_TOKEN)).toBe(false);

    // …and the imperative form, which is the one a scan keyed on `href` misses.
    const imperative = `router.push("/discover/stats");`;
    expect(navigationsInto(imperative)).toEqual(["/discover/stats"]);

    // …and it does NOT fire on prose or on an unrelated path that merely
    // contains a route as a substring, which is what would get it disabled.
    expect(navigationsInto(`// the /play page is held back`)).toEqual([]);
    expect(navigationsInto(`<Link href="/players/mahomes">`)).toEqual([]);
  });

  it("finds no file that navigates into the family without reading the flag", () => {
    const ungated: string[] = [];

    for (const file of files) {
      const source = fs.readFileSync(file, "utf8");
      const routes = navigationsInto(source);
      if (routes.length === 0) continue;
      if (source.includes(FLAG_TOKEN)) continue;
      ungated.push(`${path.relative(FRONTEND_ROOT, file)} → ${routes.join(", ")}`);
    }

    expect(ungated).toEqual([]);
  });

  it("the full inventory of doors is the one door, and it is the gated one", () => {
    // THE TEST ABOVE HAS A HOLE AND THIS IS IT. Its rule is per-FILE — "a file
    // that navigates here must read the flag" — so a SECOND door added to
    // `app/discover/page.tsx`, which already reads the flag four times over,
    // passes it. That is not hypothetical: every door found so far was added to
    // a file that already had one.
    //
    // A pinned set rather than a pinned count, and pinned deliberately. The
    // invariant this ship establishes is that the web has exactly one door into
    // the held-back experience and it is closed; any change to that set — a new
    // door, a new route promoted, or this one removed — is a thing a person
    // should have to look at, not a number to bump.
    const inventory = files
      .flatMap((file) => {
        const routes = navigationsInto(fs.readFileSync(file, "utf8"));
        const rel = path.relative(FRONTEND_ROOT, file).split(path.sep).join("/");
        return routes.map((r) => `${rel} → ${r}`);
      })
      .sort();

    expect(inventory).toEqual(["app/discover/page.tsx → /discover/stats"]);
  });
});

describe("#8187 — the door itself: Discover's header icon reads the flag", () => {
  // A source read rather than a render, for the reason
  // `challengeSurfacesHiddenForLaunch6445.test.ts` sets out at length: this is a
  // client page hanging off SWR data, an auth context, localStorage cohorts and
  // an IntersectionObserver, so rendering it would prove the composition of all
  // of those rather than the rule. The rule is what is at issue.
  const source = fs.readFileSync(
    path.join(FRONTEND_ROOT, "app", "discover", "page.tsx"),
    "utf8",
  );

  it("puts the flag above the link, not merely somewhere in the file", () => {
    const lines = source.split("\n");
    const linkLine = lines.findIndex((l) => l.includes('href="/discover/stats"'));

    // Deleting the door outright is a legitimate way to satisfy #8187, so its
    // absence is a pass, not a failure. What must never happen is the link
    // present with no gate above it.
    if (linkLine === -1) return;

    // A proximity window rather than an exact neighbouring line: spelling out
    // the adjacent line's shape makes a guard that breaks on any legitimate
    // edit to the header and then reports the wrong defect.
    const window = lines.slice(Math.max(0, linkLine - 12), linkLine).join("\n");
    expect(window).toContain(`${FLAG_TOKEN} &&`);
  });
});

describe("#8187 — the destination stops claiming a measurement it never took", () => {
  // The flag ships `false`, so the default case needs no module surgery. It
  // deliberately does NOT run inside `jest.isolateModules`: a fresh registry
  // hands the page its own copy of React while `renderToStaticMarkup` keeps the
  // outer one, and two Reacts render as a null dispatcher rather than as a
  // failed assertion — a harness story dressed up as a result.
  function renderStatsPage(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Page = require("@/app/discover/stats/page").default as React.ComponentType;
    return renderToStaticMarkup(React.createElement(Page));
  }

  it("renders the held-back state, by its stable hook", () => {
    const html = renderStatsPage();
    expect(html).toContain('data-testid="prediction-stats-held-back"');
  });

  it("does not tell the reader they have made no predictions", () => {
    // THE DEFECT, STATED AS A TEST. `/api/predictions/*` is dark, so `stats`
    // was null for EVERY reader — including one with a long saved history — and
    // the page printed "No predictions yet" at all of them. That sentence is a
    // claim about the reader's history which the page's own data call never
    // established, and it read identically to one that had.
    const html = renderStatsPage();
    expect(html).not.toContain("No predictions yet");
  });

  it("does not send the reader off to play cards that are not there", () => {
    // The phrase occurs 0 times on `/`, `/my-stuff` and `/browse`.
    const html = renderStatsPage();
    expect(html).not.toContain("What are the odds");
  });

  it("does not sit on a loading state for data it will never request", () => {
    const html = renderStatsPage();
    expect(html).not.toContain("Loading stats");
  });

  it("still offers the way back to Discover", () => {
    const html = renderStatsPage();
    expect(html).toContain('href="/discover"');
  });

  it("HIDDEN, NOT DELETED: the real page is intact behind the flag", () => {
    // The same argument the #6445 suite makes for `areGamesUnlocked`: a "hide"
    // implemented by deleting the page would pass every assertion above. With
    // the flag forced on, the page must go back to asking for its data — which
    // on a server render means the loading state, not the held-back one.
    let html = "";
    jest.isolateModules(() => {
      jest.doMock("@/lib/launchSurfaces", () => ({ CHALLENGE_SURFACES_ENABLED: true }));
      /* eslint-disable @typescript-eslint/no-var-requires */
      // React and the renderer come from THIS registry, not the outer one —
      // see the note on `renderStatsPage`.
      const ReactLocal = require("react") as typeof React;
      const { renderToStaticMarkup: render } =
        require("react-dom/server") as typeof import("react-dom/server");
      const Page = require("@/app/discover/stats/page").default as React.ComponentType;
      /* eslint-enable @typescript-eslint/no-var-requires */
      html = render(ReactLocal.createElement(Page));
    });
    jest.dontMock("@/lib/launchSurfaces");

    expect(html).not.toContain('data-testid="prediction-stats-held-back"');
    expect(html).toContain("Loading stats");
  });

  it("does not request the dark endpoint at all", () => {
    // A SOURCE ORDERING CHECK, AND THE ONLY ONE HERE THAT IS NOT BEHAVIOURAL,
    // because the behaviour is structurally invisible to the rest of this file:
    // `renderToStaticMarkup` never runs effects, so deleting this guard changes
    // nothing any render above can see. It was a surviving mutant until this
    // test existed, and the whole suite is `testEnvironment: node` with no jsdom
    // precedent, so mounting the page for one assertion is not the trade.
    //
    // An ORDER rather than an adjacency: it survives reformatting, comment
    // edits and anything moved around it, and fails only if the fetch can be
    // reached with the surface held back.
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "discover", "stats", "page.tsx"),
      "utf8",
    );
    const guard = source.indexOf(`if (!${FLAG_TOKEN}) return;`);
    const fetchCall = source.indexOf(`fetch("/api/predictions/detailed-stats"`);

    expect(fetchCall).toBeGreaterThan(-1);
    expect(guard).toBeGreaterThan(-1);
    expect(guard).toBeLessThan(fetchCall);
  });

  it("keeps the early return below the three analytics hooks", () => {
    // Stubbing the hooks above means a render can no longer notice if the new
    // `if (!CHALLENGE_SURFACES_ENABLED) return` were hoisted above them — which
    // would both break the rules of hooks and silently drop this page out of
    // GA4, the one regression this change could plausibly cause.
    const source = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "discover", "stats", "page.tsx"),
      "utf8",
    );
    const earlyReturn = source.indexOf(`if (!${FLAG_TOKEN})`);
    expect(earlyReturn).toBeGreaterThan(-1);

    for (const hook of ["usePageTracking(", "useScrollDepth(", "useEngagementTime("]) {
      const at = source.indexOf(hook);
      expect(at).toBeGreaterThan(-1);
      expect(at).toBeLessThan(earlyReturn);
    }
  });
});
