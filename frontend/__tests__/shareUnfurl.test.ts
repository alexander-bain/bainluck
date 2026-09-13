/**
 * A PASTED LINK UNFURLS WITH A PICTURE, AND THE SITE NAMES ONE HOST.
 *
 * ═══ WHAT THIS GUARDS, AND WHY IT READS BUILT HTML ═══
 *
 * Alex's distribution audit (2026-09-08) found the home page unfurling as a
 * small grey card with no image, and every canonical URL naming the apex while
 * `www` is the host that serves. LAT-P278 fixed both. This is the guard.
 *
 * It reads `.next/server/app/**\/*.html` — the prerendered bytes Vercel
 * uploads — and NOT the source, for one reason: the bug class here is
 * "declared correctly, resolved to nothing". Next's metadata resolution merges
 * a route's `openGraph` over its parents' with rules that are not obvious, and
 * the failure is silent — a valid build, a fine-looking page, and a small grey
 * card in someone else's iMessage. Only the rendered `<meta>` tag is evidence.
 *
 * ═══ THE ONE THAT ACTUALLY BIT, AND IS PINNED BELOW ═══
 *
 * A root `app/opengraph-image.tsx` is inherited by SOME descendant segments and
 * not others, and LAT-P278 guessed the rule wrong twice:
 *
 *   guess 1 — "descendants inherit it".      Falsified by the three dynamic
 *             sport routes (`/sport/[sport]`, `[league]`, `team/[team]`), which
 *             rendered no `og:image` at all. Those are the team and league
 *             pages: the URLs a fan actually pastes into a group chat.
 *   guess 2 — "only `generateMetadata` loses it". Falsified by `/discover/stats`
 *             — a plain static `metadata` export, sibling of `/discover` (which
 *             DID inherit), asking for `summary_large_image` and supplying no
 *             picture.
 *
 * So this file does not encode a theory of Next's merge rules. It encodes the
 * only thing that survived both falsifications: **a route that declares
 * `openGraph` declares its own `images`** — enforced over the app directory —
 * **and the rendered HTML is read back to prove it**. The source rule is the
 * cheap early warning; the built-HTML rule is the evidence.
 *
 * ═══ WHY THE HTML LAYER IS CONDITIONAL, AND WHY THAT IS NOT A SILENT SKIP ═══
 *
 * A guard that no-ops when its input is missing is worse than no guard: it
 * reports green and teaches everyone to trust it. CI runs `npm run build`
 * before this suite, so `.next` is always there in CI — and `ciRequiresBuild`
 * makes its ABSENCE a hard failure under `CI`, where a missing build means the
 * gate was skipped rather than satisfied. Locally it logs the exact command.
 */

import fs from "node:fs";
import path from "node:path";

import { CRAWLER_DISALLOWED_PREFIXES, isCrawlerDisallowed } from "@/lib/crawlPolicy";
import { assertRoutePath, selfCanonical } from "@/lib/routeMetadata";
import { defaultShareCard } from "@/lib/shareCard";
import { SITE_URL, getSiteUrl } from "@/lib/siteUrl";

const APP_DIR = path.join(process.cwd(), "app");
const BUILT_HTML_DIR = path.join(process.cwd(), ".next", "server", "app");

/** The host that answers 200. The apex 301s to it; see `lib/siteUrl.ts`. */
const CANONICAL_ORIGIN = "https://www.bainluck.com";
/** The bare host that must never be emitted, because it only redirects. */
const APEX_HOST = "bainluck.com";
/** The host that must never be emitted, because it only redirects. */
const APEX_ORIGIN = `https://${APEX_HOST}`;

/* ───────────────────────── the one-host rules ───────────────────────── */

describe("the site names one host", () => {
  it("the canonical origin is www, because that is the host that serves 200", () => {
    expect(SITE_URL).toBe(CANONICAL_ORIGIN);
    expect(getSiteUrl()).toBe(CANONICAL_ORIGIN);
  });

  it("no file under app/ hardcodes the apex origin", () => {
    // The literal was in 21 places before LAT-P278. It is a fact about the
    // deployment, not about a page, and it now lives once in lib/siteUrl.ts.
    //
    const offenders: string[] = [];
    for (const file of walk(APP_DIR, (n) => /\.tsx?$/.test(n))) {
      if (mentionsApexOrigin(fs.readFileSync(file, "utf8"))) {
        offenders.push(path.relative(process.cwd(), file));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("that search is precise — the www origin is not read as the apex", () => {
    // The one way this guard could invert: if `https://www.bainluck.com`
    // counted as containing `https://bainluck.com`, the rule above would flag
    // every correctly-fixed file and the whole thing would be noise.
    //
    // Asserted through `mentionsApexOrigin` against SOURCE-LINE fixtures, not
    // by comparing two URL constants directly — the loop and its control must
    // run the identical predicate or the control is for a different check.
    expect(mentionsApexOrigin('metadataBase: new URL("https://www.bainluck.com")')).toBe(false);
    expect(mentionsApexOrigin('metadataBase: new URL("https://bainluck.com")')).toBe(true);
    expect(mentionsApexOrigin('url: "https://bainluck.com/sports"')).toBe(true);
    expect(mentionsApexOrigin('url: "/sports"')).toBe(false);

    // A host is a parsed field, so a subdomain that merely ENDS in the apex is
    // a different host and must not trip the guard.
    expect(mentionsApexOrigin('url: "https://staging.bainluck.com/sports"')).toBe(false);
    // ...and a lookalike host that merely BEGINS with it is not the apex either.
    expect(mentionsApexOrigin('url: "https://bainluck.com.example.net/"')).toBe(false);

    // The spellings the previous substring test let through. These are the
    // reason the predicate parses instead of matching characters.
    expect(mentionsApexOrigin('url: "http://bainluck.com/sports"')).toBe(true);
    expect(mentionsApexOrigin('src: "//bainluck.com/og.png"')).toBe(true);
  });

  it("the apex and the canonical origin are actually different strings", () => {
    // A negative control. If someone "simplifies" SITE_URL back to the apex,
    // the rule above would still pass vacuously against a constant that
    // matched, so assert the two hosts have not quietly become one.
    expect(APEX_ORIGIN).not.toBe(CANONICAL_ORIGIN);
    expect(CANONICAL_ORIGIN.startsWith("https://www.")).toBe(true);
  });
});

/* ─────────────── the rule that the measured failure needs ─────────────── */

describe("a route that declares openGraph declares its image too", () => {
  it("because inheriting the root card is NOT something we can predict", () => {
    // The first version of this rule was narrower — "a `generateMetadata`
    // route must declare images" — on the theory that a static `metadata`
    // export inherits the root `opengraph-image` and only the dynamic ones
    // lose it. `/sports`, `/calibration` and `/politics` all supported that.
    //
    // `/discover/stats` falsified it: a plain static `metadata` export, a
    // sibling of `/discover` (which DID inherit), asking for
    // `summary_large_image` and rendering no `og:image` at all.
    //
    // So the rule is no longer about HOW the metadata is declared. Any route
    // that declares `openGraph` states its own `images`, and we stop
    // depending on a merge rule whose behaviour we have now twice guessed
    // wrong. The exception is a segment holding its own `opengraph-image.tsx`
    // — that file IS the declaration, and `/about` deliberately ships a better,
    // page-specific card than the default.
    const offenders: string[] = [];

    for (const file of walk(APP_DIR, (n) => /\.tsx?$/.test(n))) {
      if (/opengraph-image\.tsx$/.test(file)) continue;
      const src = fs.readFileSync(file, "utf8");
      if (!/openGraph\s*:/.test(src)) continue;
      if (/\bimages\s*:/.test(src)) continue;
      if (segmentShipsItsOwnCard(file)) continue;
      offenders.push(path.relative(process.cwd(), file));
    }

    expect(offenders).toEqual([]);
  });

  it("the default card is relative, so it resolves against the one host", () => {
    // An absolute apex URL here would reintroduce the split identity through
    // the back door, and a build-hashed URL would 404 after the next deploy.
    const [card] = defaultShareCard();
    expect(card.url).toBe("/opengraph-image");
    expect(card.width).toBe(1200);
    expect(card.height).toBe(630);
  });

  it("the rule can actually fail — an openGraph without images is caught", () => {
    // Negative control. The rule above is regexes over real files; if one
    // silently stopped matching it would report green forever.
    const planted = "export const metadata = { openGraph: { title: 'x' } };";
    expect(/openGraph\s*:/.test(planted)).toBe(true);
    expect(/\bimages\s*:/.test(planted)).toBe(false);

    const compliant =
      "export const metadata = { openGraph: { images: defaultShareCard } };";
    expect(/\bimages\s*:/.test(compliant)).toBe(true);
  });

  it("the sweep reads a real, non-empty set of routes", () => {
    // The rule is a loop that pushes offenders. A broken walk() would find no
    // files and pass. Assert the denominator: the routes really were read.
    const withOpenGraph = walk(APP_DIR, (n) => /\.tsx?$/.test(n)).filter((f) =>
      /openGraph\s*:/.test(fs.readFileSync(f, "utf8"))
    );
    expect(withOpenGraph.length).toBeGreaterThanOrEqual(10);
  });
});

/* ─────── a dynamic route does not inherit the ROOT's identity ─────── */

/**
 * ═══ THE HOLE #5813 CAME THROUGH ═══
 *
 * `/tournaments/us-open` — a real hub, with two priced boards — unfurled as the
 * home page: the site title, the site card, and `canonical`/`og:url` reading
 * `https://www.bainluck.com`. A real slug, a second real slug and a slug that
 * does not exist were byte-identical in metadata.
 *
 * It was not a regression. It was never measured, by anything:
 *
 *   * **#4193's census** read *"the built HTML of all 40 PRERENDERED pages"*,
 *     plus `/categories/politics` and `/playoffs/nfl` added by hand. A dynamic
 *     route prerenders nothing, and `/tournaments/[slug]` was not one of the two.
 *   * **The source sweep above** opens with `if (!/openGraph\s*:/.test(src))
 *     continue;`. A route declaring NO metadata is skipped by construction — the
 *     rule is "declared `openGraph` implies declared `images`", which is silent
 *     on declaring nothing.
 *   * **The built-HTML rules below** walk `BUILT_HTML_DIR` for `.html`. Same
 *     blind spot as #4193's census, for the same reason.
 *
 * Three layers, one shared denominator: pages that already say something. So
 * this rule reads SOURCE and asks the opposite question — which routes say
 * nothing — over the population none of the others can see.
 *
 * ═══ WHY THE ROOT, AND NOT "DECLARES METADATA" ═══
 *
 * Inheriting is normal and usually right: `/events/[id]/models` takes
 * `/events/[id]`'s layout, and `/sports/[key]` takes `/sports`'s. Those name a
 * real neighbouring page. Inheriting the ROOT is the defect, because the root's
 * `canonical: "/"` and `og:url: "/"` are correct for exactly one page and are
 * inherited literally by everyone else (#4193). So the rule walks to the
 * nearest ancestor that declares, and fires only when that ancestor is the root.
 *
 * ═══ WHY A LIST, WHEN `lib/crawlPolicy.ts` ARGUES AGAINST ONE ═══
 *
 * That file's warning is against a SILENT exemption list — one that swallows a
 * route and never speaks again. This is the other thing: a ratchet, the shape
 * `frontend/typecheck-baseline.json` already uses. It fails in BOTH directions.
 * An unlisted route that inherits the root fails, and a LISTED route that has
 * since been fixed also fails, with "delete this line". You cannot quietly join
 * it and you cannot quietly leave it behind, so it can only shrink.
 */
const INHERITS_THE_ROOT_IDENTITY: readonly string[] = [
  "/challenge/[id]",
  // A `permanentRedirect` and nothing else — the legacy single-segment key
  // `/event/event%3A<domain>%3A<slug>`. It renders no HTML, so it cannot unfurl
  // as anything: measured 2026-09-13, it answers `308 → /event/ufc/26sep15`,
  // and an unfurler follows that to the route #5833 fixed. It stays listed
  // because this rule reads SOURCE and it genuinely declares no metadata; the
  // list would be lying in the other direction if it were removed on a reason
  // the rule cannot see.
  "/event/[domain]",
  "/hub/[competition]",
];

/** `export const metadata` or `generateMetadata`, in a page or its own layout. */
const DECLARES_METADATA = /generateMetadata|export\s+const\s+metadata\b/;

function fileDeclaresMetadata(file: string): boolean {
  return fs.existsSync(file) && DECLARES_METADATA.test(read(file));
}

/** Does this route segment declare its own metadata, in `page` or `layout`? */
function declaresOwnMetadata(dir: string): boolean {
  return (
    fileDeclaresMetadata(path.join(dir, "page.tsx")) ||
    fileDeclaresMetadata(path.join(dir, "layout.tsx"))
  );
}

/**
 * The nearest ANCESTOR layout that declares metadata, or `null` when the only
 * one above this route is `app/layout.tsx` — i.e. it inherits the root.
 */
function nearestMetadataAncestor(dir: string): string | null {
  let current = path.dirname(dir);
  while (current !== APP_DIR && current.startsWith(APP_DIR)) {
    if (fileDeclaresMetadata(path.join(current, "layout.tsx"))) return current;
    current = path.dirname(current);
  }
  return null;
}

/** `app/tournaments/[slug]` -> `/tournaments/[slug]`, on any separator. */
function routeOfDir(dir: string): string {
  return `/${path.relative(APP_DIR, dir).split(path.sep).join("/")}`;
}

const dynamicRoutes = walk(APP_DIR, (n) => n === "page.tsx")
  .map((file) => path.dirname(file))
  .filter((dir) => routeOfDir(dir).includes("["))
  .map((dir) => ({ dir, route: routeOfDir(dir) }))
  .filter(({ route }) => !isCrawlerDisallowed(route))
  .sort((a, b) => a.route.localeCompare(b.route));

/** Routes with no identity of their own that fall all the way back to the root. */
const rootInheritors = dynamicRoutes
  .filter(({ dir }) => !declaresOwnMetadata(dir))
  .filter(({ dir }) => nearestMetadataAncestor(dir) === null)
  .map(({ route }) => route);

describe("a dynamic route does not unfurl as the home page", () => {
  it("declares its own identity, or is on the shrinking list", () => {
    const offenders = rootInheritors.filter(
      (route) => !INHERITS_THE_ROOT_IDENTITY.includes(route)
    );
    expect(offenders).toEqual([]);
  });

  it("the list holds nothing that has since been fixed", () => {
    // The ratchet's other direction, and the half that makes the list honest.
    // Without it, `/tournaments/[slug]` would have stayed listed after #5813
    // shipped and the next reader would have believed it was still broken.
    const fixed = INHERITS_THE_ROOT_IDENTITY.filter(
      (route) => !rootInheritors.includes(route)
    );
    expect(fixed).toEqual([]);
  });

  it("the sweep reads a real set of dynamic routes, including the fixed one", () => {
    // Both rules above are `.filter(...)` over a walk. A walk that found
    // nothing satisfies both and reports green forever, so assert the
    // denominator by name — and assert that the route this rule was written
    // for is on the DECLARING side of it, not merely absent from the list.
    const routes = dynamicRoutes.map((r) => r.route);
    expect(routes).toContain("/tournaments/[slug]");
    expect(routes).toContain("/events/[id]");
    expect(routes).toContain("/futures/[id]");
    expect(routes.length).toBeGreaterThanOrEqual(12);

    expect(rootInheritors).not.toContain("/tournaments/[slug]");
  });

  it("the rule can actually fail — the predicates are not stuck on true", () => {
    // Negative control for the two regex-driven predicates, because a rule
    // built on `fs.existsSync` plus a regex has two silent ways to pass: a path
    // that never resolves, and a pattern that never matches.
    expect(DECLARES_METADATA.test("export async function generateMetadata() {}")).toBe(true);
    expect(DECLARES_METADATA.test("export const metadata = { title: 'x' };")).toBe(true);
    expect(DECLARES_METADATA.test('export default function Page() { return null; }')).toBe(false);

    // `/events/[id]/models` declares nothing itself, so it exercises the
    // ancestor walk rather than the cheap first branch — and its answer must be
    // the events layout, NOT the root, or the walk is not walking.
    const models = path.join(APP_DIR, "events", "[id]", "models");
    expect(fs.existsSync(models)).toBe(true);
    expect(declaresOwnMetadata(models)).toBe(false);
    expect(nearestMetadataAncestor(models)).toBe(path.join(APP_DIR, "events", "[id]"));
  });
});

/* ───────── an entity route unfurls with its OWN picture, not the site's ───── */

/**
 * ═══ THE HOLE #5888 CAME THROUGH ═══
 *
 * #5813 and #5833 gave `/tournaments/[slug]` and `/event/[domain]/[slug]` their
 * WORDS. Every rule above was then satisfied: they declared `openGraph`, they
 * declared `images`, they named themselves as canonical, and they were off the
 * root-inheritor list. What they declared was the SITE's card.
 *
 * So a reader pasting three unrelated links got one picture. Measured with a
 * crawler UA on 2026-09-13 at 10:13:53Z:
 *
 *   /tournaments/us-open                              -> /opengraph-image
 *   /event/election/2026-midterms                     -> /opengraph-image
 *   /event/ufc/contender-series-hunt-vs-perea-26sep15 -> /opengraph-image
 *
 * all md5 `99618661539802337202ef69dc6595bc`, beside titles as specific as
 * "US Open 2026: Alexander Zverev 57%, Elena Rybakina 99%".
 *
 * The rule above cannot see this by construction: `images: defaultShareCard()`
 * satisfies "declares its own images". It asks WHETHER a route names a picture.
 * This asks WHICH.
 *
 * ═══ WHY A RATCHET AND NOT A FLAT RULE ═══
 *
 * Not every dynamic route should draw a per-entity card: a league index is not
 * an entity with a probability. Rather than encode a theory of which ones
 * deserve one — the kind of guess this file has already been wrong about twice —
 * the list below is the shape `INHERITS_THE_ROOT_IDENTITY` uses. It fails in
 * BOTH directions, so a route cannot quietly join it and cannot quietly leave
 * it behind. It can only shrink, and it names the next piece of work out loud.
 */
const SHARES_THE_SITE_CARD: readonly string[] = [
  "/categories/[slug]",
  "/playoffs/[sport]",
  "/sport/[sport]",
  "/sport/[sport]/[league]",
  "/sport/[sport]/[league]/team/[team]",
];

/** Dynamic routes that say something about themselves, and so could say this. */
const selfDescribingDynamicRoutes = dynamicRoutes.filter(({ dir }) =>
  declaresOwnMetadata(dir)
);

/** ...of those, the ones with no `opengraph-image.tsx` of their own. */
const siteCardRoutes = selfDescribingDynamicRoutes
  .filter(({ dir }) => !fs.existsSync(path.join(dir, "opengraph-image.tsx")))
  .map(({ route }) => route);

describe("an entity route unfurls with its own picture", () => {
  it("ships an opengraph-image, or is on the shrinking list", () => {
    const offenders = siteCardRoutes.filter(
      (route) => !SHARES_THE_SITE_CARD.includes(route)
    );
    expect(offenders).toEqual([]);
  });

  it("the list holds nothing that has since been fixed", () => {
    // The half that makes the list honest. Without it `/tournaments/[slug]`
    // would sit here forever after #5888 and the next reader would believe the
    // picture was still generic.
    const fixed = SHARES_THE_SITE_CARD.filter(
      (route) => !siteCardRoutes.includes(route)
    );
    expect(fixed).toEqual([]);
  });

  it("the routes #5888 fixed are on the CARD-SHIPPING side, by name", () => {
    // Both rules above are `.filter()` over a walk, and a walk that found
    // nothing satisfies both. Assert the denominator, and assert the four
    // routes that ship a card are not merely absent from the list but actually
    // present in the population and actually holding the file.
    const routes = selfDescribingDynamicRoutes.map((r) => r.route);
    expect(routes).toContain("/tournaments/[slug]");
    expect(routes).toContain("/event/[domain]/[slug]");
    expect(routes.length).toBeGreaterThanOrEqual(8);

    for (const route of [
      "/tournaments/[slug]",
      "/event/[domain]/[slug]",
      "/events/[id]",
      "/futures/[id]",
    ]) {
      expect(siteCardRoutes).not.toContain(route);
      expect(
        fs.existsSync(path.join(APP_DIR, ...route.split("/").filter(Boolean), "opengraph-image.tsx"))
      ).toBe(true);
    }
  });

  it("those routes name their OWN path in openGraph.images, not the site card", () => {
    // The file convention overrides `og:image` on these segments, so this reads
    // the source rather than the built HTML — a dynamic route prerenders no
    // HTML for the layer below to check. What it catches is a layout that
    // silently goes back to `defaultShareCard()`: the state #5888 started from,
    // which every other rule in this file scored as a pass.
    for (const route of ["/tournaments/[slug]", "/event/[domain]/[slug]"]) {
      const layout = path.join(
        APP_DIR,
        ...route.split("/").filter(Boolean),
        "layout.tsx"
      );
      const src = read(layout);
      // Both the resolved and the dead branch, and both built FROM THE ROUTE'S
      // OWN PATH. Asserting the bare string `/opengraph-image` is not enough —
      // `buildShareUrl("/opengraph-image")` contains it and is exactly the
      // regression this rule exists to stop (caught by mutation, 2026-09-13).
      expect(src).toContain("buildShareUrl(`${path}/opengraph-image`)");
      expect(src).toContain("buildShareUrl(`${deadPath}/opengraph-image`)");
      expect(src).not.toContain("defaultShareCard");
    }
  });

  it("the rule can actually fail — the file probe is not stuck on true", () => {
    // Negative control. `fs.existsSync` over a built path has the same silent
    // failure mode as everything else here: a path that never resolves reports
    // "no card" for every route, which would empty `siteCardRoutes` in the
    // other direction and fail loudly — but a path that resolves for EVERY
    // route would pass both rules with an empty list forever.
    expect(
      fs.existsSync(path.join(APP_DIR, "tournaments", "[slug]", "opengraph-image.tsx"))
    ).toBe(true);
    expect(
      fs.existsSync(path.join(APP_DIR, "tournaments", "[slug]", "no-such-file.tsx"))
    ).toBe(false);

    // And the population is genuinely split — a list that is everything or
    // nothing is not a ratchet.
    expect(siteCardRoutes.length).toBeGreaterThan(0);
    expect(siteCardRoutes.length).toBeLessThan(selfDescribingDynamicRoutes.length);
  });
});

/* ──────────────── the layer that reads what actually shipped ──────────── */

/**
 * Next's own generated 404 shell. It is not a shareable surface — nobody pastes
 * a link *in order to* show a 404 — and we do not author its metadata, so it
 * carries no `openGraph` block for the root card to merge into. Exempted by
 * name so the exemption is one file rather than a pattern that could quietly
 * swallow a real page.
 */
const NOT_A_SHAREABLE_SURFACE = new Set(["_not-found.html"]);

const builtPages = (
  fs.existsSync(BUILT_HTML_DIR)
    ? walk(BUILT_HTML_DIR, (n) => n.endsWith(".html"))
    : []
).filter((f) => !NOT_A_SHAREABLE_SURFACE.has(rel(f)));

describe("every prerendered page unfurls with a picture", () => {
  it("the build exists — otherwise this whole layer proved nothing", () => {
    const ciRequiresBuild = process.env.CI === "true" || process.env.CI === "1";
    if (builtPages.length === 0) {
      const message =
        `No built HTML under ${path.relative(process.cwd(), BUILT_HTML_DIR)}. ` +
        `This layer is the only one that reads what a reader receives; it did ` +
        `NOT run. Build first:  cd frontend && npm run build`;
      if (ciRequiresBuild) throw new Error(message);
      console.warn(`[shareUnfurl] SKIPPED (not a pass): ${message}`);
    }
    expect(builtPages.length >= 0).toBe(true);
  });

  it("declares an absolute og:image on every prerendered page", () => {
    const offenders = builtPages
      .map((f) => ({ page: rel(f), image: meta(read(f), "og:image") }))
      .filter((r) => !r.image || !r.image.startsWith("https://"));
    expect(offenders).toEqual([]);
  });

  it("declares the large twitter card, so a 1200x630 image is not cropped square", () => {
    const offenders = builtPages
      .map((f) => ({ page: rel(f), card: meta(read(f), "twitter:card") }))
      .filter((r) => r.card !== "summary_large_image");
    expect(offenders).toEqual([]);
  });

  it("names www — never the redirecting apex — in og:url, og:image and canonical", () => {
    const offenders: { page: string; tag: string; value: string }[] = [];

    for (const file of builtPages) {
      const html = read(file);
      const checks: [string, string | null][] = [
        ["og:url", meta(html, "og:url")],
        ["og:image", meta(html, "og:image")],
        ["canonical", canonical(html)],
      ];
      for (const [tag, value] of checks) {
        if (!value) continue;
        // Same parsed-host predicate the source scan uses, so a tag and a
        // source line cannot disagree about what "the apex" means.
        if (isApexUrl(value)) {
          offenders.push({ page: rel(file), tag, value });
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("read at least the pages the ship names, so the sweep is not empty", () => {
    // The three rules above are `.filter(...)` over a list. An empty list
    // passes all of them. This asserts the DENOMINATOR: the routes the audit
    // named were actually among the files read.
    if (builtPages.length === 0) return;
    const pages = builtPages.map(rel);
    for (const required of ["index.html", "sports.html", "discover.html"]) {
      expect(pages.some((p) => p.endsWith(required))).toBe(true);
    }
  });
});

/* ──────────────── a page says it is itself, not the home page ─────────── */

/**
 * Routes whose canonical is deliberately NOT their own URL, with the reason.
 *
 * `/golf` is a `redirect()` to `/categories/golf`. A redirect's canonical names
 * its DESTINATION — that is what consolidating a duplicate means — so "canonical
 * equals own route" is the wrong rule for it, and it is listed here rather than
 * exempted, so the intended value is still pinned.
 */
const CANONICAL_ALIASES: Record<string, string> = {
  "/golf": "/categories/golf",
};

describe("every prerendered page says it is itself, not the home page", () => {
  // #4193. The root sets `canonical: "/"` and `og:url: "/"`, and Next inherits
  // both LITERALLY. Measured on production 2026-09-09, twelve static routes and
  // both dynamic hub families (`/categories/politics`, `/playoffs/nfl`) shipped
  // `<link rel="canonical" href="https://www.bainluck.com">` — every one of them
  // telling search engines to index the home page instead.
  //
  // This reads built HTML for the same reason the rules above do: the bug is
  // "declared nowhere, resolved to the parent's value". Only the rendered tag
  // is evidence.

  const checked = builtPages
    .map((f) => ({ file: f, route: routeOf(rel(f)) }))
    .filter((p) => !isCrawlerDisallowed(p.route));

  it("declares its own route as canonical", () => {
    const offenders = checked
      .map(({ file, route }) => ({
        route,
        expected: absolute(CANONICAL_ALIASES[route] ?? route),
        actual: canonical(read(file)),
      }))
      .filter((r) => r.actual !== r.expected);
    expect(offenders).toEqual([]);
  });

  it("declares its own route as og:url, so a share is not a share of the home page", () => {
    // The same inheritance, one tag over. Worth its own rule because the two
    // drifted apart once already: LAT-P278 gave `/sport` an `og:url` and left
    // its canonical inheriting, so the page was right for sharing and wrong for
    // search at the same time.
    const offenders = checked
      .map(({ file, route }) => ({
        route,
        expected: absolute(CANONICAL_ALIASES[route] ?? route),
        actual: meta(read(file), "og:url"),
      }))
      .filter((r) => r.actual !== r.expected);
    expect(offenders).toEqual([]);
  });

  it("the sweep read the pages the fix names — not an empty list", () => {
    // Both rules above are `.filter(...)`. An empty `checked` passes them and
    // reports green forever, so assert the DENOMINATOR: the routes measured as
    // broken on production are actually among the pages being read.
    if (builtPages.length === 0) return;
    const routes = checked.map((p) => p.route);
    for (const required of [
      "/",
      "/privacy",
      "/search",
      "/categories",
      "/categories/golf",
      "/playoffs",
      "/daily",
      "/my-stuff",
      "/preferences",
      "/onboarding",
      "/kernels-preview",
      "/sport",
    ]) {
      expect(routes).toContain(required);
    }
    expect(checked.length).toBeGreaterThanOrEqual(20);
  });

  it("the exemption is robots.txt's list, and it does not swallow the site", () => {
    // The only pages allowed to skip the rule are the ones robots.txt already
    // tells crawlers not to fetch (`lib/crawlPolicy.ts` explains why a meta tag
    // on a Disallow-ed path is unreachable advice). Two ways that could rot:
    // the exemption could grow to cover real content, or it could stop matching
    // and make the rule vacuous. Pin both ends.
    if (builtPages.length === 0) return;
    const exempted = builtPages
      .map((f) => routeOf(rel(f)))
      .filter((r) => isCrawlerDisallowed(r));

    expect(exempted.length).toBeGreaterThan(0); // it still matches something
    for (const route of exempted) {
      expect(
        CRAWLER_DISALLOWED_PREFIXES.some((p) => route.startsWith(p))
      ).toBe(true);
    }
    // No public surface hides behind it.
    for (const publicRoute of ["/", "/about", "/sports", "/discover", "/privacy"]) {
      expect(exempted).not.toContain(publicRoute);
    }
  });

  it("the rule can actually fail — an inherited canonical is caught", () => {
    // Negative control. If `canonical()` or `routeOf()` silently stopped
    // returning what the rule compares, every page would "match" and the guard
    // would be decoration.
    const inherited = '<link rel="canonical" href="https://www.bainluck.com"/>';
    expect(canonical(inherited)).toBe(absolute("/"));
    expect(canonical(inherited)).not.toBe(absolute("/privacy"));

    expect(routeOf("index.html")).toBe("/");
    expect(routeOf("privacy.html")).toBe("/privacy");
    expect(routeOf("categories/golf.html")).toBe("/categories/golf");
  });
});

describe("selfCanonical() cannot be the thing that reintroduces the apex", () => {
  it("emits a relative canonical and og:url plus the default card", () => {
    const md = selfCanonical("/privacy");
    expect(md.alternates?.canonical).toBe("/privacy");
    expect(md.openGraph).toMatchObject({ url: "/privacy" });
    // `openGraph` without `images` is the silent-grey-card bug from #4149; the
    // helper supplies both so no caller can declare one without the other.
    expect(md.openGraph?.images).toEqual(defaultShareCard());
  });

  it("refuses an absolute URL, including the protocol-relative spelling", () => {
    // These throw at build time on purpose. `//bainluck.com/x` is the case that
    // matters: it starts with "/" so a `startsWith` check would wave it through,
    // and it is an absolute URL naming the redirecting apex.
    expect(() => assertRoutePath("https://www.bainluck.com/privacy")).toThrow();
    expect(() => assertRoutePath("https://bainluck.com/privacy")).toThrow();
    expect(() => assertRoutePath("//bainluck.com/privacy")).toThrow();
    expect(() => assertRoutePath("privacy")).toThrow();
    // ...and accepts the shape every caller actually uses.
    expect(() => assertRoutePath("/privacy")).not.toThrow();
    expect(() => assertRoutePath("/categories/golf")).not.toThrow();
  });
});

/* ────────────────────────────── helpers ────────────────────────────── */

/** `index.html` -> `/`; `categories/golf.html` -> `/categories/golf`. */
function routeOf(relativeHtmlPath: string): string {
  const withoutExt = relativeHtmlPath.replace(/\.html$/, "");
  return withoutExt === "index" ? "/" : `/${withoutExt}`;
}

/** The absolute URL Next renders for a root-relative route. */
function absolute(route: string): string {
  return route === "/" ? CANONICAL_ORIGIN : `${CANONICAL_ORIGIN}${route}`;
}

function walk(dir: string, keep: (name: string) => boolean): string[] {
  if (!fs.existsSync(dir)) return [];
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full, keep));
    else if (keep(entry.name)) out.push(full);
  }
  return out;
}

function read(file: string): string {
  return fs.readFileSync(file, "utf8");
}

function rel(file: string): string {
  return path.relative(BUILT_HTML_DIR, file);
}

/** Reads a `<meta>` content value by `property=` or `name=`, either order. */
function meta(html: string, key: string): string | null {
  const patterns = [
    new RegExp(`<meta[^>]+(?:property|name)="${key}"[^>]*content="([^"]*)"`, "i"),
    new RegExp(`<meta[^>]+content="([^"]*)"[^>]*(?:property|name)="${key}"`, "i"),
  ];
  for (const re of patterns) {
    const m = html.match(re);
    if (m) return m[1];
  }
  return null;
}

/**
 * Is this an absolute URL whose host is exactly the redirecting apex?
 *
 * Decided by PARSING the URL and comparing `hostname` for equality — never by
 * testing whether one URL string contains another. Two earlier versions of this
 * predicate were written as string tests and both were right to be rejected:
 * an unanchored regex (`/https:\/\/bainluck\.com/`, alert 2234) and a substring
 * test (`.includes(APEX_ORIGIN)`, alert 2238). A host is a parsed field, not a
 * span of characters, so the parse is the honest test as well as the quiet one.
 *
 * Equality also makes the predicate stricter than the substring version it
 * replaces: that one only ever matched the `https://` spelling, so `http://` and
 * a protocol-relative `//bainluck.com` walked straight past the guard.
 */
function isApexUrl(raw: string): boolean {
  try {
    return new URL(raw, "https://example.invalid").hostname === APEX_HOST;
  } catch {
    return false;
  }
}

/**
 * Does this file's SOURCE TEXT hardcode the redirecting apex origin?
 *
 * The parameter is a file's contents, not a URL — the question is "does this
 * source hardcode the wrong host", not "is this URL safe". Kept as a named
 * helper so the loop and its negative control run the identical predicate: a
 * control that re-implements the check is a control for a different check.
 *
 * Works by lifting every URL-shaped token out of the text and asking `isApexUrl`
 * about each one. The regex only finds candidates; it decides nothing.
 */
function mentionsApexOrigin(sourceText: string): boolean {
  const candidates = sourceText.match(/(?:https?:)?\/\/[^\s"'`)]+/g) ?? [];
  return candidates.some(isApexUrl);
}

/** True when the route's own segment directory holds an `opengraph-image.tsx`. */
function segmentShipsItsOwnCard(file: string): boolean {
  return fs.existsSync(path.join(path.dirname(file), "opengraph-image.tsx"));
}

function canonical(html: string): string | null {
  const m = html.match(/<link[^>]+rel="canonical"[^>]+href="([^"]*)"/i);
  return m ? m[1] : null;
}
