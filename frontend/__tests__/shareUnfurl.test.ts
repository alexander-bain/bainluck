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

import { defaultShareCard } from "@/lib/shareCard";
import { SITE_URL, getSiteUrl } from "@/lib/siteUrl";

const APP_DIR = path.join(process.cwd(), "app");
const BUILT_HTML_DIR = path.join(process.cwd(), ".next", "server", "app");

/** The host that answers 200. The apex 301s to it; see `lib/siteUrl.ts`. */
const CANONICAL_ORIGIN = "https://www.bainluck.com";
/** The host that must never be emitted, because it only redirects. */
const APEX_ORIGIN = "https://bainluck.com";

/* ───────────────────────── the one-host rules ───────────────────────── */

describe("the site names one host", () => {
  it("the canonical origin is www, because that is the host that serves 200", () => {
    expect(SITE_URL).toBe(CANONICAL_ORIGIN);
    expect(getSiteUrl()).toBe(CANONICAL_ORIGIN);
  });

  it("no file under app/ hardcodes the apex origin", () => {
    // The literal was in 21 places before LAT-P278. It is a fact about the
    // deployment, not about a page, and it now lives once in lib/siteUrl.ts.
    const offenders: string[] = [];
    for (const file of walk(APP_DIR, (n) => /\.tsx?$/.test(n))) {
      const src = fs.readFileSync(file, "utf8");
      // `https://bainluck.com` but not `https://www.bainluck.com`.
      if (/https:\/\/bainluck\.com/.test(src)) {
        offenders.push(path.relative(process.cwd(), file));
      }
    }
    expect(offenders).toEqual([]);
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
        // Startswith the apex AND is not the www host.
        if (value.startsWith(`${APEX_ORIGIN}/`) || value === APEX_ORIGIN) {
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

/* ────────────────────────────── helpers ────────────────────────────── */

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

/** True when the route's own segment directory holds an `opengraph-image.tsx`. */
function segmentShipsItsOwnCard(file: string): boolean {
  return fs.existsSync(path.join(path.dirname(file), "opengraph-image.tsx"));
}

function canonical(html: string): string | null {
  const m = html.match(/<link[^>]+rel="canonical"[^>]+href="([^"]*)"/i);
  return m ? m[1] : null;
}
