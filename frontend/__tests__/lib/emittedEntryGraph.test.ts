/**
 * LAT-P201 — THE GUARD READS THE EMITTED ENTRY GRAPH, NOT THE SOURCE.
 *
 * ═══ WHY THIS EXISTS ALONGSIDE serverLayoutDynamicImports.test.ts ═══
 *
 * CERT-732 fixed a real defect: `app/layout.tsx` declared three pieces of
 * header chrome as `dynamic(..., { ssr: false })`, and because a Server
 * Component cannot lazily reference a Client Component, all three shipped in
 * the EAGER entry chunk of every route anyway. Measured on production:
 * 660,971 → 638,599 raw, 211,090 → 203,392 brotli-as-served.
 *
 * The guard written with that fix — `serverLayoutDynamicImports.test.ts` — is
 * a SOURCE-level guard. It fails if `next/dynamic` reappears in any Server
 * Component. That is the right guard for the shape the defect happened to
 * take, and it is not the right guard for the CLASS.
 *
 * The class is: *code that is supposed to be off the first load is on it.*
 * `dynamic()`-in-a-server-file is one way to land there. A plain static import
 * added to the layout is another. A barrel file that re-exports the heavy
 * module is another. A `React.lazy` whose module is already in the graph is
 * another. None of those import `next/dynamic`, so none of them are visible to
 * a source scan, and every one of them puts the same bytes back on the
 * critical path of every route.
 *
 * So this file asserts the ARTIFACT instead of the intent: build, then read
 * the `<script src>` set out of each prerendered HTML — the exact bytes a
 * browser fetches before hydration — and require that the deferred modules are
 * not in it. That is mechanism-independent. It cannot be satisfied by writing
 * the deferral more convincingly; it can only be satisfied by the chunk
 * actually not being there.
 *
 * ═══ WHY THE `<script>` TAGS AND NOT `next build`'s TABLE ═══
 *
 * `next build` printed `/` at 185 kB → 186 kB for the CERT-732 fix — i.e. it
 * reported the 22 kB REMOVAL as a small regression, because its route table
 * counts newly-created async chunks into the route's attribution whether or
 * not the HTML requests them. It does not request them: the prerendered HTML
 * carried the same 2 `<link rel="preload">` before and after. A build tool's
 * summary of a bundle is not the bundle. The `<script src>` set is.
 *
 * ═══ THE THREE CONTROLS, AND WHY EACH ONE IS LOAD-BEARING ═══
 *
 * Every assertion here is of the form "this list is empty", which is the
 * easiest kind of test to make vacuously green. Three separate things are
 * therefore proven before the emptiness means anything:
 *
 * 1. THE PARSE SEES A REAL ARTIFACT. If the HTML glob returned nothing, or the
 *    script regex matched nothing, "no offenders" would be true and worthless.
 *    Route count, `/`'s own script count and the presence of the layout/page
 *    entry chunks are all asserted.
 *
 * 2. EVERY MARKER IS A KNOWN HIT SOMEWHERE. A marker string that has been
 *    renamed out of existence matches zero chunks, and then "absent from the
 *    entry graph" is trivially true forever. So each marker must be found in
 *    at least one emitted chunk — it has to still be a string this app ships,
 *    just not one it ships eagerly.
 *
 * 3. EVERY MARKER IS STILL ANCHORED TO ITS SOURCE. Even a marker that survives
 *    (2) could have drifted to some unrelated module. Each one is also
 *    required to appear in the specific component it is standing in for, so a
 *    rename reds this file rather than hollowing it.
 *
 * ═══ WHY A MISSING BUILD IS NOT A SKIP UNDER CI ═══
 *
 * CI runs `npm run build` before `npm run test:ci` (`.github/workflows/ci.yml`,
 * the `frontend-build` job — the ordering is deliberate and commented there,
 * because part of this suite reads the build OUTPUT). So in CI `.next` is
 * always present, and its absence means the gate was skipped rather than
 * satisfied. That is a hard failure. Locally, where a fresh clone legitimately
 * has no `.next` yet, the suite says so loudly and names the command instead
 * of quietly reporting green. Same shape as
 * `__tests__/components/shippedCopyBans.test.ts`.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "fs";
import { basename, join } from "path";

const FRONTEND_ROOT = join(__dirname, "..", "..");
const PRERENDER_DIR = join(FRONTEND_ROOT, ".next", "server", "app");
const CHUNKS_DIR = join(FRONTEND_ROOT, ".next", "static", "chunks");

/**
 * What must stay off the first load, why, and how to recognise it in a
 * minified chunk.
 *
 * `source` is not documentation — it is control 3. Each marker must still be
 * present in the component it names.
 */
const DEFERRED = [
  {
    what: "NavigationProgress (the nprogress package)",
    // Was `"nprogress"`, which control 5 (LAT-P206) rejected: it is a substring
    // of `"inprogress"`, so it also matched `components/event/PropsSection.tsx`
    // and `lib/propDivergence.ts`. Neither is in any route's entry graph today,
    // so the guard was green by luck rather than by construction — put either
    // of them on the critical path and the assertion below would have kept
    // passing while reporting on the wrong module. This is the config call, and
    // it exists nowhere else.
    marker: "showSpinner",
    source: join("components", "NavigationProgress.tsx"),
  },
  {
    what: "SearchBar (the whole typeahead subsystem)",
    // Was the placeholder copy "Search teams, games, and futures", which
    // `components/MobileSearchOverlay.tsx` carries verbatim — two components
    // with the same visible string, so the marker could not tell which of them
    // an entry chunk contained. This cache key is SearchBar's own.
    marker: "bainluck:trending",
    source: join("components", "SearchBar.tsx"),
  },
  {
    what: "MobileSearchTrigger (and its overlay)",
    marker: "Open search",
    source: join("components", "MobileSearchTrigger.tsx"),
  },
  // ─── LAT-P205: two Discover screens no cold reader is looking at ───────────
  //
  // Same class, one layer down. These are not root-layout chrome; they are
  // branches of `/` itself, reachable only after a tap (the challenge) or a
  // scroll to the bottom of the feed (the end card). The guard is identical
  // because the failure is identical: a `dynamic()` that stops splitting puts
  // them back on the critical path of the landing page and nothing says so.
  {
    what: "ChallengeModal (the daily challenge overlay)",
    marker: "The daily challenge draws its questions from the live feed.",
    source: join("components", "discover", "ChallengeModal.tsx"),
  },
  // `EndOfFeedCard` is NOT on this list, and its absence is a measurement: its
  // chunk was fetched on all six treatment runs of the LAT-P205 A/B without any
  // scrolling, so deferring it moved bytes rather than removing them. The
  // reasoning lives at the `dynamic()` block in `app/discover/page.tsx`.
  {
    what: "ResolutionGroup (a signed-in reader's settled guesses)",
    // The visible heading is "Your results · settled" and it is NOT usable as a
    // marker: the minifier emits the middot as the escape `\xb7`, so the literal
    // string appears in no chunk and control 2 fails — which is the control
    // doing its job. This aria-label survives minification verbatim.
    marker: "Your resolved guesses",
    source: join("components", "discover", "ResolutionGroup.tsx"),
  },
  {
    what: "ResolutionCard (one settled guess)",
    marker: "✓ You got it right",
    source: join("components", "discover", "ResolutionCard.tsx"),
  },
  // ─── LAT-P206: the sign-in implementation, and the daily game ─────────────
  {
    what: "lib/firebase.ts (the whole sign-in implementation)",
    // NOT an `auth/...` error code: the Firebase SDK's own vendor chunk ships
    // those same strings, so a marker like `auth/popup-closed-by-user` would
    // flag whichever route legitimately loads the SDK and prove nothing about
    // OUR module. This console string exists only in our file.
    marker: "Backend response missing id_token",
    source: join("lib", "firebase.ts"),
    // `/admin/*` is behind an admin token, is not on anyone's cold path, and
    // reads `getIdToken` straight from this module. Scoped out by NAME rather
    // than by loosening the assertion, so adding a route here is a visible act.
    exceptRoutes: ["admin/labeling.html", "admin/discover-quality.html"],
  },
  {
    what: "GuessCard (the daily game's question card)",
    // The card's visible header is "What are the odds?" and it is NOT usable:
    // `app/discover/stats/page.tsx` QUOTES that phrase in its own empty-state
    // prose, so the marker flagged `/discover/stats` for carrying a component
    // it does not import. Control 5 below now refuses an ambiguous marker
    // outright rather than leaving the next one to be caught by luck.
    marker: "data-guess-card",
    source: join("components", "discover", "GuessCard.tsx"),
  },
  {
    what: "DailyChallengeCard (the daily game's progress bar)",
    marker: "Come back tomorrow for a new set",
    source: join("components", "discover", "DailyChallengeCard.tsx"),
  },
  // ─── LAT-P207: the account menu ───────────────────────────────────────────
  //
  // The first entry on this list that is still SERVER-RENDERED. Everything
  // above is `ssr: false`, so "not in the entry graph" and "not in the HTML"
  // coincide; `UserMenu` renders its signed-out button into the HTML of every
  // route and only its CLIENT chunk is deferred. That is exactly why the guard
  // reads the `<script src>` set rather than the markup — the markup is
  // supposed to still contain this component, and a guard that looked for the
  // string in the HTML would red on the correct state.
  //
  // Not the visible "Sign in" copy, which `app/my-stuff/page.tsx` also ships
  // (it carries its own provider buttons), and not "Continue with Google" for
  // the same reason — control 5 refuses both. This dropdown's aria-label is
  // UserMenu's alone.
  {
    what: "UserMenu (the header account menu and its provider dropdown)",
    marker: "Sign in options",
    source: join("components", "UserMenu.tsx"),
  },
  // ─── LAT-P208: the wider API client ───────────────────────────────────────
  //
  // The first entry that is SUPPOSED to be eager — on 17 routes. Everything
  // above is deferred app-wide, so "absent from every route" is the right
  // claim. `lib/api.ts` is not deferred at all: `/categories/golf` needs the
  // golf wrappers on its first load and should have them. The claim is
  // narrower and is about ONE page: the wider client must not be on the entry
  // graph of the LANDING page, whose own endpoints now live in `lib/apiCore.ts`.
  //
  // Hence `onlyRoutes` rather than `exceptRoutes`. Inverting the existing
  // mechanism would have meant listing 17 exemptions that grow with the app and
  // silently swallow the 18th; naming the two routes the claim covers keeps the
  // gate honest as routes are added. Control 6 below is what stops the scoping
  // from being a way to assert nothing.
  //
  // Not a function name — those are minified. Not `/api/sports/hierarchy`
  // either, which control 5 refuses: `app/sport/[sport]/[league]/page.tsx`
  // builds that path itself. This one is `lib/api.ts`'s alone and survives
  // minification verbatim.
  {
    what: "lib/api.ts (the wider API client — golf, admin, onboarding, the themed dashboards)",
    marker: "/api/golf/leaderboard",
    source: join("lib", "api.ts"),
    onlyRoutes: ["index.html", "discover.html", "discover/stats.html"],
  },
  // ─── LAT-P209: the sport-category table behind the GA4 event catalog ──────
  //
  // Back to `exceptRoutes`, and deliberately — LAT-P208's warning against it
  // does not apply here, because the ratio is inverted. `lib/api.ts` was
  // legitimately eager on 17 of 40 routes and absent from 3, so an exemption
  // list was the majority of the app and would silently swallow route 18.
  // This table is legitimately eager on 8 and absent from 29. Default-deny is
  // therefore the behaviour we want: a NEW route that pulls the table onto its
  // first load should red, and under `onlyRoutes` it would be silently
  // unchecked instead. Pick the mechanism by which side is the default, not by
  // which one the last cycle used.
  //
  // ═══ WHY THIS ENTRY NAMES THE TABLE AND NOT THE CATALOG IT GUARDS ═══
  //
  // The cut was `hooks/useAnalytics.ts` — the GA4 event catalog — which the
  // `@/hooks` barrel used to launder onto every route that wanted only the
  // three mandated page-tracking hooks. The catalog cannot be marked. It has
  // ZERO source-unique string literals (measured, not assumed): every event
  // name it passes to `track()` is also a member of `KNOWN_EVENT_NAMES` in
  // `lib/analytics/sanitize.ts`, and sanitize.ts stays eager BY DESIGN, since
  // `core.ts` sanitizes every event including the page_view that fires on a
  // cold load. So any event-name marker would be present in both arms and
  // green on a regression — the expensive failure direction control 5 exists
  // to prevent.
  //
  // The table is the catalog's own eager dependency (`getCategoryByKey`), and
  // nothing else put it on these 29 routes: it left all 29 entry graphs on the
  // same diff. So it reds when the catalog comes back, which is the regression
  // this guards. It can also red if some future module imports the table
  // eagerly on its own — a false red, the cheap direction, and still a true
  // statement about the critical path.
  //
  // Not a league key like `basketball_nba`: control 5 refuses all of them, and
  // they are exactly the strings sanitize.ts keeps alive. These two prefixes
  // (`racing_`, `rugbyunion_`) were the ONLY source-unique strings among the
  // 132 that left `/`'s entry graph on this diff.
  {
    what: "lib/sportCategories.ts (the sport-category table the GA4 event catalog drags with it)",
    marker: "rugbyunion_",
    source: join("lib", "sportCategories.ts"),
    exceptRoutes: [
      "calibration.html",
      "categories/golf.html",
      "categories.html",
      "my-stuff.html",
      "onboarding.html",
      "preferences.html",
      "search.html",
      "sports.html",
    ],
  },
  // ─── LAT-P211: the Tailwind class-conflict resolver ───────────────────────
  //
  // The first entry whose deferred module is a PACKAGE, not one of our files,
  // and that is why `packageSource` exists — see the note on control 5.
  //
  // `cn` is `twMerge(clsx(...))`. `tailwind-merge` is 26,985 raw / 7,398 brotli
  // and eleven components use it, so it is not deferrable app-wide — LAT-P201
  // measured that properly and the answer has not changed: 1,299 of 1,530 `cn`
  // calls have a genuinely conflicting class that `twMerge` resolves, and
  // dropping it changes the padding and background of every card in the app.
  //
  // What LAT-P201 did not ask is whether the LANDING page needs it. It did not.
  // Exactly one module in `/`'s eager graph reached `lib/utils`:
  // `components/PinButton.tsx`, via `components/discover/shared.tsx` — two of
  // those 1,530 calls. The Discover ActionBar passed
  // `className="text-text-muted hover:text-text-secondary"` and leaned on
  // `twMerge` to drop the button's own conflicting colour; that override is now
  // a `tone` prop and a total lookup table, so no conflict is emitted and
  // nothing has to resolve one. `/` went 21 scripts → 20, −26,708 raw /
  // −7,414 brotli, with byte-identical prerendered markup.
  //
  // ═══ WHY `exceptRoutes` HERE WHEN LAT-P208 USED `onlyRoutes` ═══
  //
  // By LAT-P209's rule: pick by which side is the default. `lib/api.ts` was
  // eager on 17 of 40, so an exemption list was the majority of the app. This
  // is eager on 5 of 40 and absent from 35, so default-deny is what we want —
  // a NEW route that puts a class-conflict resolver on its cold path should
  // red and be a visible act, not be silently unchecked.
  {
    what: "tailwind-merge (the Tailwind class-conflict resolver behind `cn`)",
    // Not a class-group key like `bg-blend`: those are real Tailwind class
    // prefixes, so app source could legitimately grow one (`bg-blend-multiply`)
    // and control 5 would then red on a string that is not this package's
    // alone. This is tailwind-merge's own v3 config key, it cannot appear in a
    // Tailwind class name, and terser does not mangle properties.
    marker: "orderSensitiveModifiers",
    packageSource: join(
      "node_modules",
      "tailwind-merge",
      "dist",
      "bundle-mjs.mjs",
    ),
    // The five routes that legitimately render a `cn`-based card on their first
    // load. Measured on the emitted artifact, not from the import graph.
    exceptRoutes: [
      "daily.html",
      "my-stuff.html",
      "preferences.html",
      "search.html",
      "sports.html",
    ],
  },
] as const;

/**
 * The file a marker is anchored to for control 3, and whether that anchor is
 * one of ours or a package's.
 *
 * Everything above LAT-P211 defers a module we wrote, so "the marker still
 * lives in the component it stands in for" and "the marker names exactly one
 * source file" are the same claim. A package has no file under `app/`,
 * `components/`, `lib/` or `hooks/`, so control 5's one-holder rule would
 * report zero holders and fail on a perfectly good marker.
 *
 * The honest translation is not to exempt package entries from control 5 but to
 * INVERT it: for a package the requirement is that the marker appears in
 * **zero** app source files. That is strictly stronger evidence of uniqueness
 * than one-holder is — it says the app cannot emit this string by itself, so a
 * chunk carrying it is carrying the package.
 */
function anchor(entry: (typeof DEFERRED)[number]): {
  path: string;
  isPackage: boolean;
} {
  return "packageSource" in entry
    ? { path: entry.packageSource, isPackage: true }
    : { path: entry.source, isPackage: false };
}

const buildPresent = existsSync(PRERENDER_DIR) && existsSync(CHUNKS_DIR);

/* ─────────────────────────── the artifact readers ─────────────────────────── */

/**
 * Every prerendered route HTML, as a path relative to the prerender dir.
 *
 * LAT-P206 made this RECURSIVE. It used to read the top level only, which is
 * 23 of the app's 40 prerendered routes — `discover/stats`, `categories/golf`,
 * `share/my-odds` and every `/admin/*` page were silently outside the gate, so
 * a regression that landed only in a nested route's entry chunk would have gone
 * unseen by a guard that reported green.
 */
function prerenderedRoutes(): string[] {
  const out: string[] = [];
  const walk = (dir: string, prefix: string) => {
    for (const entry of readdirSync(dir).sort()) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, `${prefix}${entry}/`);
      else if (entry.endsWith(".html")) out.push(`${prefix}${entry}`);
    }
  };
  walk(PRERENDER_DIR, "");
  return out;
}

/**
 * The scripts a browser actually fetches for a route, before hydration.
 *
 * `noModule` scripts are dropped: that is the legacy polyfill bundle, which no
 * modern browser executes, and counting it would put ~113 kB of noise into
 * every number here.
 */
function entryScripts(routeHtml: string): string[] {
  const html = readFileSync(join(PRERENDER_DIR, routeHtml), "utf8");
  return [...html.matchAll(/<script[^>]*\ssrc="([^"]+)"[^>]*>/g)]
    .filter((m) => !/\bnoModule\b/.test(m[0]))
    .map((m) => m[1])
    .filter((src) => src.startsWith("/_next/"))
    .map((src) => join(FRONTEND_ROOT, ".next", src.slice("/_next/".length)));
}

const chunkText = (() => {
  const cache = new Map<string, string>();
  return (file: string): string => {
    let text = cache.get(file);
    if (text === undefined) {
      text = existsSync(file) ? readFileSync(file, "utf8") : "";
      cache.set(file, text);
    }
    return text;
  };
})();

/** Every emitted JS chunk, entry or async. */
function allChunks(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (full.endsWith(".js")) out.push(full);
    }
  };
  walk(CHUNKS_DIR);
  return out;
}

/* ──────────────────────────────── the gate ──────────────────────────────── */

describe("LAT-P201 the build output is present", () => {
  test("`.next` exists, or CI has skipped its own gate", () => {
    if (buildPresent) {
      expect(buildPresent).toBe(true);
      return;
    }
    const message =
      "No build output at .next/server/app + .next/static/chunks. " +
      "Run `npm run build` in frontend/ before this suite. " +
      "In CI this is a FAILURE, not a skip: the frontend-build job runs " +
      "`npm run build` before `npm run test:ci`, so a missing .next there " +
      "means this guard never ran.";
    if (process.env.CI) throw new Error(message);
    // eslint-disable-next-line no-console
    console.warn(`[LAT-P201] SKIPPED — ${message}`);
  });
});

/**
 * `describe.skip` rather than a per-test guard: without a build there is no
 * artifact to make a claim about, and a test that "passes" against no artifact
 * is the exact failure mode this file exists to remove. The gate above is what
 * makes the skip visible.
 */
const describeBuild = buildPresent ? describe : describe.skip;

describeBuild("LAT-P201 the parse sees a real artifact", () => {
  test("control 1 — routes, scripts and the expected entry chunks are all there", () => {
    const routes = prerenderedRoutes();
    expect(routes.length).toBeGreaterThan(15);
    expect(routes).toContain("index.html");

    // `/` — the Discover landing page, and the route the CERT-732 measurement
    // was taken on. 21 modern scripts after that fix (22 before). Bounded
    // rather than pinned: this guard is about WHAT is in the graph, and a
    // pinned count would red on every unrelated page split.
    const home = entryScripts("index.html");
    expect(home.length).toBeGreaterThan(10);
    expect(home.length).toBeLessThan(40);

    // Every path resolved to a file that exists — a typo in the `/_next/`
    // rewrite above would otherwise yield empty strings that contain no
    // marker, and the whole file would go green on nothing.
    for (const file of home) expect(existsSync(file)).toBe(true);

    // The layout and the page entry chunks specifically, because those are the
    // two the defect class lands in.
    // Arrow, not a bare `basename` reference: `Array.map` passes the index as
    // a second argument and `basename`'s second parameter is `suffix`.
    const names = home.map((f) => basename(f));
    expect(names.some((n) => /^layout-[0-9a-f]+\.js$/.test(n))).toBe(true);
    expect(names.some((n) => /^page-[0-9a-f]+\.js$/.test(n))).toBe(true);
  });

  test("control 2 + 3 — every marker is still a real string, in its real component", () => {
    const chunks = allChunks();
    expect(chunks.length).toBeGreaterThan(50);

    for (const entry of DEFERRED) {
      const { what, marker } = entry;
      const { path: source } = anchor(entry);
      // Control 3: still anchored to the module it stands in for.
      const sourcePath = join(FRONTEND_ROOT, source);
      expect(existsSync(sourcePath)).toBe(true);
      if (!readFileSync(sourcePath, "utf8").includes(marker)) {
        throw new Error(
          `Marker ${JSON.stringify(marker)} for ${what} is no longer in ` +
            `${source}. It was renamed, so the entry-graph assertion below ` +
            `now matches nothing and proves nothing. Update the marker.`,
        );
      }

      // Control 2: still emitted somewhere, i.e. the app does ship it — just
      // not eagerly. Zero hits means the assertion below is vacuous.
      const carriers = chunks.filter((f) => chunkText(f).includes(marker));
      if (carriers.length === 0) {
        throw new Error(
          `Marker ${JSON.stringify(marker)} for ${what} appears in NO emitted ` +
            `chunk. Either the component stopped shipping, or minification ` +
            `now rewrites this string. Either way "absent from the entry ` +
            `graph" is trivially true and this guard is dead.`,
        );
      }
    }
  });

  /**
   * Control 5 (LAT-P206) — a marker must name ONE module.
   *
   * Controls 2 and 3 both check that a marker still hits. Neither checks that
   * it hits only what it means to. `GuessCard`'s visible header, "What are the
   * odds?", passed both and still produced a false RED: `/discover/stats`
   * quotes the phrase in its empty-state prose, so that route's own page chunk
   * matched and the guard reported a component the route does not import.
   *
   * A false red is the cheap direction of this failure — someone investigates
   * and finds nothing. The expensive direction is the same ambiguity pointing
   * the other way: a marker whose real carrier gets deferred while some
   * unrelated eager module keeps the string alive would leave the entry-graph
   * assertion passing on a regression. So the requirement is exactly one
   * source file, checked over the whole app rather than over a hand-list.
   */
  test("control 5 — every marker is unique to the source it names", () => {
    const roots = ["app", "components", "lib", "hooks"];
    const sources: string[] = [];
    const walk = (dir: string) => {
      if (!existsSync(dir)) return;
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full);
        else if (/\.(ts|tsx)$/.test(full)) sources.push(full);
      }
    };
    for (const root of roots) walk(join(FRONTEND_ROOT, root));
    expect(sources.length).toBeGreaterThan(100);

    for (const entry of DEFERRED) {
      const { what, marker } = entry;
      const { path: source, isPackage } = anchor(entry);
      const holders = sources
        .filter((f) => readFileSync(f, "utf8").includes(marker))
        .map((f) => f.slice(FRONTEND_ROOT.length + 1));

      // A package marker is inverted: the app must not be able to emit the
      // string on its own, so ANY app-source holder makes the marker ambiguous.
      if (isPackage) {
        if (holders.length !== 0) {
          throw new Error(
            `Marker ${JSON.stringify(marker)} for ${what} comes from ` +
              `${source} and must appear in NO app source file, but appears ` +
              `in ${holders.length}: ${holders.join(", ")}. A chunk carrying ` +
              `it would no longer prove the package is there. Pick a marker ` +
              `only the package has.`,
          );
        }
        continue;
      }

      if (holders.length !== 1 || holders[0] !== source) {
        throw new Error(
          `Marker ${JSON.stringify(marker)} for ${what} should appear in ` +
            `exactly one source file (${source}) but appears in ` +
            `${holders.length}: ${holders.join(", ")}. An ambiguous marker ` +
            `flags routes that do not import the module, and can hide a real ` +
            `regression behind an unrelated eager copy of the string. Pick a ` +
            `marker only this module has.`,
        );
      }
    }
  });
});

describeBuild("LAT-P201 deferred chrome is off the first load of every route", () => {
  test("no route's entry graph carries the deferred modules", () => {
    // Every prerendered route, not just `/`. This chrome lives in the ROOT
    // layout, so a regression puts it on the critical path of the whole app,
    // and checking one route would let 22 others rot.
    const offenders: string[] = [];

    const routes = prerenderedRoutes();

    for (const route of routes) {
      for (const file of entryScripts(route)) {
        const text = chunkText(file);
        for (const entry of DEFERRED) {
          const exempt: readonly string[] =
            "exceptRoutes" in entry ? entry.exceptRoutes : [];
          if (exempt.includes(route)) continue;
          // A scoped entry (LAT-P208) makes its claim about the named routes
          // only; elsewhere the module is legitimately eager.
          const scoped: readonly string[] | null =
            "onlyRoutes" in entry ? entry.onlyRoutes : null;
          if (scoped && !scoped.includes(route)) continue;
          if (text.includes(entry.marker)) {
            offenders.push(`${route}: ${basename(file)} carries ${entry.what}`);
          }
        }
      }
    }

    // On master at 9c1629e8 this list was empty across the 23 top-level
    // prerendered routes; LAT-P206 widened the walk to all 40 and it is still
    // empty. Before CERT-732 it named `app/layout-*.js` on every one of them.
    expect(offenders).toEqual([]);

    // Control 4 (LAT-P206) — every scoped-out route must still EXIST. An
    // exemption for a route that has been renamed or deleted is an exemption
    // that silently covers nothing, and the next real offender inherits a name
    // nobody re-checked.
    const known = new Set(routes);
    for (const entry of DEFERRED) {
      if (!("exceptRoutes" in entry)) continue;
      for (const route of entry.exceptRoutes) {
        if (!known.has(route)) {
          throw new Error(
            `${entry.what} is scoped out of ${route}, but no such prerendered ` +
              `route exists. Drop the exemption or fix the path.`,
          );
        }
      }
    }

    // Control 4b (LAT-P208) — the same requirement for a scoped entry, which
    // fails the OTHER way round: a misspelt `onlyRoutes` entry checks nothing
    // at all, rather than checking one route too many.
    for (const entry of DEFERRED) {
      if (!("onlyRoutes" in entry)) continue;
      for (const route of entry.onlyRoutes) {
        if (!known.has(route)) {
          throw new Error(
            `${entry.what} is scoped TO ${route}, but no such prerendered ` +
              `route exists, so that part of the claim covers nothing. ` +
              `Fix the path.`,
          );
        }
      }
    }
  });

  /**
   * Control 6 (LAT-P208) — a scoped claim must be about a module that is
   * genuinely eager somewhere else.
   *
   * `onlyRoutes` narrows an assertion, and a narrowed assertion is a new way to
   * be vacuous that none of controls 1–5 can see. Control 2 only proves the
   * marker is in SOME emitted chunk — an async one counts. So if `lib/api.ts`
   * were one day deferred app-wide, or deleted, or its golf wrappers moved into
   * a lazily-loaded module, the `/`-scoped assertion would keep passing while
   * having stopped meaning anything: "not eager on `/`" is trivially true of a
   * module that is not eager anywhere.
   *
   * The claim only has content while some OTHER route still carries the module
   * on its first load. That is the state this cut deliberately left in place —
   * 17 routes did at the time of writing — and if it ever stops being true, the
   * right response is to delete this entry, not to keep a green tick.
   */
  test("control 6 — a route-scoped module is still eager on some route outside the scope", () => {
    const routes = prerenderedRoutes();

    for (const entry of DEFERRED) {
      if (!("onlyRoutes" in entry)) continue;
      // Widened deliberately: `as const` types each entry's `onlyRoutes` as a
      // tuple of its own literals, so `.includes(someRoute: string)` stops
      // compiling as soon as a second scoped entry (or, as in LAT-P209, an
      // `exceptRoutes`-only sibling) changes the union. Same widening the
      // entry-graph test above already does for `scoped`.
      const scopedRoutes: readonly string[] = entry.onlyRoutes;
      const outside = routes.filter((r) => !scopedRoutes.includes(r));
      const carriers = outside.filter((route) =>
        entryScripts(route).some((file) => chunkText(file).includes(entry.marker)),
      );
      if (carriers.length === 0) {
        throw new Error(
          `${entry.what} is scoped to ${entry.onlyRoutes.join(", ")}, but no ` +
            `route OUTSIDE that scope carries it eagerly. The module is no ` +
            `longer eager anywhere, so "absent from the scoped routes" is ` +
            `trivially true and this entry now guards nothing. Delete it, or ` +
            `widen it into an app-wide entry if the module really was deferred.`,
        );
      }
    }
  });
});
