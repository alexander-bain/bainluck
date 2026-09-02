/**
 * LAT-P202 — THE NUMBER FONT IS NOT PRELOADED AHEAD OF THE PAGE.
 *
 * ═══ THE DEFECT THIS LOCKS OUT ═══
 *
 * `next/font` preloads by default. That emitted
 * `<link rel="preload" as="font" href="…woff2">` into the head of every
 * prerendered route. A font preload is a HIGH-priority fetch, so on a slow
 * connection those 31 kB were scheduled ahead of the render-blocking CSS and
 * the entry JS that actually draw the page.
 *
 * That trade only pays if the font draws the page, and this one does not.
 * JetBrains Mono is wired into `fontFamily.mono` (tailwind.config.ts) and
 * `--font-mono` (globals.css) — the probability numbers. Body copy and
 * headings run on the system sans stack, and the measured LCP element on
 * Discover is a plain `text-2xl font-black` DIV that never waits on it.
 *
 * Measured on production by simulating this exact edit before making it —
 * stripping the preload tag out of the live HTML, serving both arms from the
 * same bytes, interleaved, 3G + 4x CPU, 390 ms TTFB on both arms, n=6/6
 * (`tools/cold-load.mjs`, `COLD_ABLATE=fontpreload`):
 *
 *     FCP  1810 -> 1422 ms  (-388)      LCP  2726 -> 2516 ms  (-210)
 *     DCL  1820 -> 1431 ms  (-389)      load 2655 -> 2452 ms  (-203)
 *     CLS 0.062 -> 0.062    (unchanged)
 *
 * ═══ WHY THIS READS THE ARTIFACT, NOT layout.tsx ═══
 *
 * Same reasoning as `emittedEntryGraph.test.ts` (LAT-P201): the class is
 * "a high-priority font fetch is on the critical path", and `preload: true`
 * coming back is only ONE way to land there. A second `next/font` call added
 * anywhere in the tree, a hand-written `<link rel="preload" as="font">`, or a
 * third-party CSS import that preloads its own face would all reintroduce the
 * defect without touching the line this fix edited. A source scan of
 * `layout.tsx` sees none of them. The emitted HTML sees all of them.
 *
 * ═══ THE CONTROLS, AND WHY EACH IS LOAD-BEARING ═══
 *
 * The headline assertion is "this list is empty", which is the easiest kind of
 * test to make vacuously green. Three things are proven before that emptiness
 * is allowed to mean anything:
 *
 * 1. THE PARSE SEES A REAL ARTIFACT — routes exist, and every one of them has
 *    a non-trivial `<head>`. An empty glob would satisfy "no font preloads".
 *
 * 2. THE REGEX CAN STILL FIND A PRELOAD THAT IS GENUINELY THERE. Next still
 *    emits `<link rel="preload" as="script">` for the webpack runtime. If the
 *    preload matcher stopped matching — an attribute-order change, a quoting
 *    change, a Next upgrade that switches to a header-based hint — every
 *    "absent" assertion here would go green while the font preload was right
 *    there in the document. So a KNOWN HIT must still be found. This is the
 *    control that keeps the whole file honest.
 *
 * 3. THE FONT IS STILL SHIPPED AND STILL REACHABLE. "No font preload" is also
 *    satisfied by deleting the font, which is not the fix — it is a different,
 *    worse change. The woff2 must still be emitted and still be referenced by
 *    a stylesheet, i.e. discovered via CSS instead of hoisted into the head.
 *
 * ═══ WHY A MISSING BUILD IS NOT A SKIP UNDER CI ═══
 *
 * CI runs `npm run build` before `npm run test:ci` (`.github/workflows/ci.yml`,
 * `frontend-build`), so in CI `.next` is always present and its absence means
 * this gate never ran. That is a hard failure. Locally a fresh clone may
 * legitimately have no `.next`, so it says so loudly and names the command.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const FRONTEND_ROOT = join(__dirname, "..", "..");
const PRERENDER_DIR = join(FRONTEND_ROOT, ".next", "server", "app");
const STATIC_DIR = join(FRONTEND_ROOT, ".next", "static");

const buildPresent = existsSync(PRERENDER_DIR) && existsSync(STATIC_DIR);

/** Every prerendered route HTML, by filename. */
function prerenderedRoutes(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (full.endsWith(".html")) out.push(full);
    }
  };
  walk(PRERENDER_DIR);
  return out.sort();
}

/**
 * Every `<link rel="preload">` in a document.
 *
 * Deliberately matches `rel="preload"` anywhere in the tag rather than
 * assuming attribute order, and RAISES on a document with no `<head>` at all
 * rather than reporting it as clean — an unparseable page must redden this
 * file, never satisfy it.
 */
function preloadLinks(file: string): string[] {
  const html = readFileSync(file, "utf8");
  if (!/<head[\s>]/i.test(html)) {
    throw new Error(`${file}: no <head> found — the parse cannot make a claim about this document`);
  }
  return [...html.matchAll(/<link\b[^>]*>/g)]
    .map((m) => m[0])
    .filter((tag) => /\brel="preload"/.test(tag));
}

const isFontPreload = (tag: string) => /\bas="font"/.test(tag) || /\.woff2?\b/.test(tag);

/** Every emitted file under .next/static, relative to that directory. */
function staticFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else out.push(full);
    }
  };
  walk(STATIC_DIR);
  return out;
}

/* ──────────────────────────────── the gate ──────────────────────────────── */

describe("LAT-P202 the build output is present", () => {
  test("`.next` exists, or CI has skipped its own gate", () => {
    if (buildPresent) {
      expect(buildPresent).toBe(true);
      return;
    }
    const message =
      "No build output at .next/server/app + .next/static. " +
      "Run `npm run build` in frontend/ before this suite. " +
      "In CI this is a FAILURE, not a skip: the frontend-build job runs " +
      "`npm run build` before `npm run test:ci`, so a missing .next there " +
      "means this guard never ran.";
    if (process.env.CI) throw new Error(message);
    // eslint-disable-next-line no-console
    console.warn(`[LAT-P202] SKIPPED — ${message}`);
  });
});

const describeBuild = buildPresent ? describe : describe.skip;

describeBuild("LAT-P202 the parse sees a real artifact", () => {
  test("control 1 — prerendered routes exist and every one of them parses", () => {
    const routes = prerenderedRoutes();
    expect(routes.length).toBeGreaterThan(10);
    // preloadLinks throws on a document with no <head>; calling it on all of
    // them is the assertion that every page was really read.
    for (const route of routes) expect(Array.isArray(preloadLinks(route))).toBe(true);
  });

  test("control 2 — the preload matcher still finds a preload that IS there", () => {
    // Next emits `<link rel="preload" as="script">` for the webpack runtime.
    // If this stops being found, the matcher has drifted and every absence
    // assertion below is vacuous — so this failing means "fix the matcher",
    // not "delete this test".
    const withAnyPreload = prerenderedRoutes().filter((r) => preloadLinks(r).length > 0);
    expect(withAnyPreload.length).toBeGreaterThan(0);

    const script = withAnyPreload
      .flatMap((r) => preloadLinks(r))
      .filter((tag) => /\bas="script"/.test(tag));
    expect(script.length).toBeGreaterThan(0);
  });

  test("control 3 — the font is still shipped and still reachable via CSS", () => {
    // "No font preload" is also satisfied by having no font. That is a
    // different change and this file must not accept it.
    const files = staticFiles();
    const woff2 = files.filter((f) => f.endsWith(".woff2"));
    expect(woff2.length).toBeGreaterThan(0);

    const css = files.filter((f) => f.endsWith(".css")).map((f) => readFileSync(f, "utf8"));
    expect(css.length).toBeGreaterThan(0);
    // At least one emitted stylesheet must reference a woff2, which is how the
    // browser now discovers the face instead of being told in the head.
    expect(css.some((text) => /\.woff2\b/.test(text))).toBe(true);
  });
});

describeBuild("LAT-P202 no route preloads a font ahead of the page", () => {
  test("not one prerendered route carries a font preload", () => {
    const offenders = prerenderedRoutes()
      .map((route) => ({ route, tags: preloadLinks(route).filter(isFontPreload) }))
      .filter(({ tags }) => tags.length > 0);

    expect(
      offenders.map(({ route, tags }) => `${route.slice(FRONTEND_ROOT.length)} :: ${tags.join(" ")}`),
    ).toEqual([]);
  });
});
