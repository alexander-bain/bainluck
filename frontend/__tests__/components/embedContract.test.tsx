// #5914 — the WIRING of the embed contract, which the predicate's own test
// cannot see.
//
// `lib/embed.test.ts` proves the decision is right. It would pass in full with
// `EmbedGate` mounted nowhere, the chrome drawn unconditionally and the ship
// entirely absent — the defect native photographed is a wiring fact, so it is
// asserted here, at the source level.
//
// Source-level rather than rendered, for the same reason
// `calibrationAuditHooks.test.tsx` gives: the root layout is a Server Component
// that mounts the auth provider, SWR, three deferred-chrome split points and
// the analytics stack. Rendering it would prove less and break more. What has
// to be true is structural — WHICH elements sit inside a gate — and that is
// exactly what the source shows.

import * as fs from "fs";
import * as path from "path";

const read = (...p: string[]) =>
  fs.readFileSync(path.join(__dirname, "..", "..", ...p), "utf8");

const LAYOUT = read("app", "layout.tsx");
const ABOUT_PAGE = read("app", "about", "page.tsx");
const ABOUT_LAYOUT = read("app", "about", "layout.tsx");
const GATE = read("components", "EmbedGate.tsx");
const LINK = read("components", "EmbedAwareLink.tsx");

/** Strip comments — otherwise every assertion below can be satisfied by prose. */
const code = (s: string) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const LAYOUT_CODE = code(LAYOUT);
const ABOUT_CODE = code(ABOUT_PAGE);

describe("the root layout gates every piece of chrome native photographed", () => {
  test("EmbedGate is imported and used, not merely present in the tree", () => {
    expect(LAYOUT_CODE).toContain('from "@/components/EmbedGate"');
    // Four wraps: header, Footer, BottomNav, and the TelemetryGate/ConsentBanner
    // pair. Fewer means one of the photographed defects survives.
    expect((LAYOUT_CODE.match(/<EmbedGate[\s>]/g) ?? []).length).toBeGreaterThanOrEqual(4);
  });

  // Each of these is one of the three things in the photograph (plus Footer,
  // which native left to ux). The assertion is CONTAINMENT — the element sits
  // between a gate's open and close — because "both strings appear in the file"
  // is satisfied by a gate wrapped around nothing.
  test.each([
    ["the site header", "<header"],
    ["the bottom tab nav", "<BottomNav"],
    ["the consent banner", "<ConsentBanner"],
    ["the site footer", "<Footer"],
    ["the telemetry gate", "<TelemetryGate"],
  ])("%s is inside an EmbedGate", (_name, needle) => {
    const at = LAYOUT_CODE.indexOf(needle);
    expect(at).toBeGreaterThan(-1);
    const before = LAYOUT_CODE.slice(0, at);
    const opens = (before.match(/<EmbedGate[\s>]/g) ?? []).length;
    const closes = (before.match(/<\/EmbedGate>/g) ?? []).length;
    // Strictly more opens than closes means we are inside one.
    expect(opens).toBeGreaterThan(closes);
  });

  // THE PAIRING THAT MUST NOT COME APART. codex's directive is explicit that the
  // embed omits the tracking rather than hiding the banner that asks about it:
  // a suppressed banner over a live GA4 rail is the one outcome worse than
  // changing nothing. Gating the banner while leaving the rail mounted would
  // satisfy every other test in this file.
  test("the telemetry rail is gated whenever the banner is", () => {
    const bannerGated = /<EmbedGate[^>]*>\s*<ConsentBanner/.test(LAYOUT_CODE);
    const railGated = /<EmbedGate[^>]*>\s*<TelemetryGate/.test(LAYOUT_CODE);
    expect(bannerGated).toBe(true);
    expect(railGated).toBe(true);
  });

  // The one wrap whose children have a SIDE EFFECT. With the default fallback
  // the static shell would mount the rail and hydration would unmount it —
  // gtag.js already loaded, cookie already set. You cannot un-fire a beacon.
  test("the telemetry wrap passes fallback={null}, not the default", () => {
    expect(LAYOUT_CODE).toMatch(/<EmbedGate\s+fallback=\{null\}>\s*<TelemetryGate/);
  });

  // D30 / D96: the two COOKIELESS Vercel providers are mounted outside the
  // consent gate by explicit ruling. They are not chrome and not consent-gated,
  // so this ship has no business moving them.
  test.each([["<SpeedInsights", "SpeedInsights"], ["<Analytics", "Analytics"]])(
    "%s is left OUTSIDE any EmbedGate (D30/D96 untouched)",
    (needle) => {
      const at = LAYOUT_CODE.indexOf(needle);
      expect(at).toBeGreaterThan(-1);
      const before = LAYOUT_CODE.slice(0, at);
      const opens = (before.match(/<EmbedGate[\s>]/g) ?? []).length;
      const closes = (before.match(/<\/EmbedGate>/g) ?? []).length;
      expect(opens).toBe(closes);
    }
  );

  test("every EmbedGate opened is closed", () => {
    const opens = (LAYOUT_CODE.match(/<EmbedGate[\s>]/g) ?? []).length;
    const closes = (LAYOUT_CODE.match(/<\/EmbedGate>/g) ?? []).length;
    expect(opens).toBe(closes);
  });
});

describe("the About page's outgoing links survive a tap", () => {
  // next/link navigates with pushState, and WKWebView never shows its
  // navigation delegate a same-document navigation — so native's policy cannot
  // fire, the reader lands on /calibration INSIDE the About screen, and the
  // client route drops ?embed=1 so the chrome returns one tap later.
  test("no bare next/link remains on the page", () => {
    expect(ABOUT_CODE).not.toMatch(/<Link[\s>]/);
    expect(ABOUT_CODE).not.toContain('from "next/link"');
  });

  test.each([["/calibration"], ["/privacy"], ["/discover"]])(
    "%s is an EmbedAwareLink",
    (href) => {
      const at = ABOUT_CODE.indexOf(`href="${href}"`);
      expect(at).toBeGreaterThan(-1);
      // Walk back to the nearest opening tag and check which one it is.
      const openedBy = ABOUT_CODE.slice(0, at).lastIndexOf("<");
      expect(ABOUT_CODE.slice(openedBy, at)).toMatch(/^<EmbedAwareLink/);
    }
  );

  test("the mailto stays a plain anchor", () => {
    // It always was one, and it is the reason native needs a navigation policy
    // at all: WKWebView cancels unhandled schemes silently, so today it does
    // nothing. Converting it would be a regression.
    expect(ABOUT_CODE).toMatch(/<a\s+[^>]*href="mailto:bugs@bainluck\.com"/);
  });
});

describe("the embed resolves on the server, so the chrome never flashes", () => {
  // Measured before this file existed: with /about statically prerendered,
  // /about?embed=1 shipped header=1 and bottomnav=1 in its HTML and removed
  // them at hydration — a visible flash and a layout shift on the one screen
  // the ship is for.
  test("/about is force-dynamic", () => {
    expect(code(ABOUT_LAYOUT)).toMatch(/export const dynamic\s*=\s*["']force-dynamic["']/);
  });

  test("the segment config is scoped to /about, NOT the root layout", () => {
    // native/168 rejected a headers() read in the root layout because it makes
    // every route on the site dynamic. The same objection applies to this, which
    // is why it lives in app/about/.
    expect(LAYOUT_CODE).not.toMatch(/export const dynamic/);
  });
});

describe("the two gates differ only where they must", () => {
  test("both read the SAME predicate, neither re-spells it", () => {
    for (const src of [GATE, LINK]) {
      expect(code(src)).toContain('from "@/lib/embed"');
      expect(code(src)).toContain("isEmbeddedAbout(");
      // A second spelling of the rule is how two halves of one contract drift.
      expect(code(src)).not.toMatch(/["']\/about["']\s*===|===\s*["']\/about["']/);
      expect(code(src)).not.toMatch(/===\s*["']1["']/);
    }
  });

  test("each wraps its own Suspense boundary, so no call site has to", () => {
    // useSearchParams() bails a statically prerendered route out unless it sits
    // under one, and these mount in the ROOT layout — "any route" is the site.
    for (const src of [GATE, LINK]) {
      expect(code(src)).toContain("<Suspense");
      expect(code(src)).toContain("fallback=");
    }
  });

  test("EmbedAwareLink's fallback is the Link, which is safe because a tap needs hydration", () => {
    expect(code(LINK)).toMatch(/fallback=\{\s*\n?\s*<Link/);
  });
});
