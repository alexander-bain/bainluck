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
    marker: "nprogress",
    source: join("components", "NavigationProgress.tsx"),
  },
  {
    what: "SearchBar (the whole typeahead subsystem)",
    marker: "Search teams, games, and futures",
    source: join("components", "SearchBar.tsx"),
  },
  {
    what: "MobileSearchTrigger (and its overlay)",
    marker: "Open search",
    source: join("components", "MobileSearchTrigger.tsx"),
  },
] as const;

const buildPresent = existsSync(PRERENDER_DIR) && existsSync(CHUNKS_DIR);

/* ─────────────────────────── the artifact readers ─────────────────────────── */

/** Every prerendered route HTML, by filename. */
function prerenderedRoutes(): string[] {
  return readdirSync(PRERENDER_DIR)
    .filter((f) => f.endsWith(".html"))
    .sort();
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

    for (const { what, marker, source } of DEFERRED) {
      // Control 3: still anchored to the component it stands in for.
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
});

describeBuild("LAT-P201 deferred chrome is off the first load of every route", () => {
  test("no route's entry graph carries the deferred modules", () => {
    // Every prerendered route, not just `/`. This chrome lives in the ROOT
    // layout, so a regression puts it on the critical path of the whole app,
    // and checking one route would let 22 others rot.
    const offenders: string[] = [];

    for (const route of prerenderedRoutes()) {
      for (const file of entryScripts(route)) {
        const text = chunkText(file);
        for (const { what, marker } of DEFERRED) {
          if (text.includes(marker)) {
            offenders.push(`${route}: ${basename(file)} carries ${what}`);
          }
        }
      }
    }

    // On master at 9c1629e8 this list is empty across all 23 prerendered
    // routes. Before CERT-732 it named `app/layout-*.js` on every one of them.
    expect(offenders).toEqual([]);
  });
});
