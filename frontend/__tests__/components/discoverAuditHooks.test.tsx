// L2-223 Item 3 — the browser-audit rail's Discover hooks.
//
// The rail used to identify a rendered card by `main div.break-inside-avoid`,
// a Tailwind LAYOUT class that `DiscoverSkeletonGrid` also carries. A Discover
// stuck on skeletons therefore satisfied "a real card was visible", recorded a
// plausible first-card latency, and the audit reported GREEN — the C96 [P1]
// false green, reached through the selector instead of the `.catch()` L2-221
// removed. It identified the empty state by the copy string "You're all caught
// up", so an editorial reword would silently have turned a proven empty state
// into an unproven blank page.
//
// These hooks are now load-bearing evidence, not conveniences. This suite is
// the tripwire: if a hook is dropped, renamed, or leaks onto the skeleton, CI
// fails here rather than the audit quietly going green on nothing. Runs in the
// node/SSR env (renderToStaticMarkup) — no jsdom. SWR is not avoided; it is
// mocked at its module boundary inside `isolateModules`, which is what lets the
// page states below be asserted in the DOM instead of grepped for (UX-P228).
//
// And the tripwire now takes its own list FROM the rail: see PACK_HOOKS. A
// hand-kept list drifted once already, which is what left the pack's
// `discover-feed-unavailable` selector guarded by nothing.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("@/lib/analytics", () => ({
  trackEvent: jest.fn(),
}));

import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

import EndOfFeedCard from "../../components/discover/EndOfFeedCard";
import DiscoverSkeletonGrid from "../../components/discover/DiscoverSkeletonGrid";
import FeedUnavailableNotice from "../../components/discover/FeedUnavailableNotice";

const noop = () => {};

/** Count non-overlapping occurrences of a literal in a string. */
function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/**
 * Every `discover-*` hook the browser-audit pack actually selects, read FROM
 * the pack.
 *
 * UX-P228: this used to be implicit — the suite asserted the hooks somebody had
 * remembered to add, and nothing compared that set against the rail. It had
 * already drifted. `discover-feed-unavailable` is selected by
 * `discover-smoke.spec.ts` (the `ERROR_STATE` selector, added by L2-238) and is
 * the testId of `FeedUnavailableNotice`'s DEFAULT reason, and no test in this
 * file mentioned it. Dropping or renaming it was a green CI and a rail that had
 * silently lost the one distinction L2-238 added it to make: "the deploy served
 * an unavailable feed" versus "the page was blank" — which is the C96 [P1]
 * false-green class named at the top of this file, reached the other way round.
 *
 * Adding the missing string would have left the NEXT hook to be forgotten
 * identically, so the list is derived instead. A hook added to the pack reds
 * here until it is covered.
 */
const SPEC_DIR = path.join(__dirname, "..", "..", "e2e", "specs");

/**
 * The pack is read through the TypeScript AST, not as text.
 *
 * UX-P228 round 2, after CERT-584. Round 1 read `data-testid="..."` out of the
 * raw source, and the cert defeated it by splitting the ATTRIBUTE NAME:
 * `"[data-" + "testid=\"discover-computed-attr\"]"` contains no contiguous
 * `data-testid`, so both the census and the extraction saw nothing while
 * Playwright received a perfectly valid selector.
 *
 * Patching that regex would have moved the hole one level out again — the same
 * shape the latency lane hit three certs running. A text guard cannot prove
 * "the pack selects nothing I have not seen", because the pack is code. So the
 * selector strings are RESOLVED instead: a selector either evaluates to a
 * string this file can compute, and its hooks are extracted and demanded, or it
 * does not, and that fails LOUDLY. There is no third outcome.
 *
 * Two useful consequences. Comments need no stripping — the parser never sees
 * them, so UX-P213-2's census hazard does not arise. And concatenation is now
 * *supported* rather than banned, so the guard costs the pack no expressiveness.
 */
type Resolution = {
  file: string;
  selectors: string[];
  unresolved: string[];
  /** Every function name called anywhere in the spec. */
  calledNames: Set<string>;
};

/**
 * Name -> which argument carries the selector. It is not always the first:
 * `measureMainRegion(page, SELECTOR)` takes the page in slot 0.
 *
 * Module scope so a test can assert the map still COVERS what the specs call.
 * Battery M16: deleting `locator` from here made every `locator()` argument
 * stop being checked, and the run stayed green — the resolver reported nothing
 * unresolved because it was no longer looking. A fail-closed check that can be
 * silently unwired is not fail-closed.
 */
const SELECTOR_ARG: Record<string, number> = {
  locator: 0,
  waitForSelector: 0,
  getByTestId: 0,
  $: 0,
  $$: 0,
  measureMainRegion: 1,
};

/**
 * The selector-taking APIs that MUST be understood if a spec uses them.
 *
 * Hardcoded on purpose: it is the one list a reviewer has to eyeball, and it is
 * short. Anything here that a Discover spec calls but `SELECTOR_ARG` does not
 * know is a hole, and reds.
 */
const REQUIRED_SELECTOR_APIS = [
  "locator",
  "waitForSelector",
  "getByTestId",
  "measureMainRegion",
] as const;

function resolveSpec(file: string, src: string): Resolution {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true);

  // Module-level string constants, resolved first: `SKELETON` is handed to a
  // helper rather than to `locator()`, so a selector-call-only read would miss
  // `discover-skeleton` entirely and then red on its own guarded list.
  const consts = new Map<string, string>();

  function literalOf(n: ts.Node): string | null {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text;
    if (ts.isIdentifier(n)) return consts.get(n.text) ?? null;
    if (ts.isParenthesizedExpression(n) || ts.isAsExpression(n)) {
      return literalOf(n.expression);
    }
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const l = literalOf(n.left);
      const r = literalOf(n.right);
      return l !== null && r !== null ? l + r : null;
    }
    // `event-page.spec.ts` composes `HERO_ANY` from two other constants. A
    // template whose every substitution resolves is just as static as a
    // literal, and refusing it would red a spec that is doing nothing wrong.
    if (ts.isTemplateExpression(n)) {
      let out = n.head.text;
      for (const span of n.templateSpans) {
        const v = literalOf(span.expression);
        if (v === null) return null;
        out += v + span.literal.text;
      }
      return out;
    }
    return null;
  }

  for (const st of sf.statements) {
    if (!ts.isVariableStatement(st)) continue;
    for (const d of st.declarationList.declarations) {
      if (ts.isIdentifier(d.name) && d.initializer) {
        const v = literalOf(d.initializer);
        if (v !== null) consts.set(d.name.text, v);
      }
    }
  }

  // Every API that turns a string into an element reference. `getByTestId`
  // takes a BARE hook name with no `data-testid` in the text at all, so it is
  // resolved here rather than merely banned. `measureMainRegion` is this
  // repo's own selector-taking helper — `event-page.spec.ts` reaches
  // `discover-skeleton` only through it.
  //
  // STATED GAP (battery M17, a scored survivor): this is a list of NAMES. A new
  // project helper that takes a selector is covered for literal arguments — the
  // literal scan below sees those wherever they appear — but a COMPUTED
  // argument to a helper not named here would be missed. Closing that needs a
  // type checker, not a parser, and it is not this slice.
  const selectors: string[] = [];
  const unresolved: string[] = [];
  const calledNames = new Set<string>();

  function walk(n: ts.Node): void {
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const name = ts.isPropertyAccessExpression(callee)
        ? callee.name.text
        : ts.isIdentifier(callee)
          ? callee.text
          : "";
      if (name) calledNames.add(name);
      const idx = SELECTOR_ARG[name];
      if (idx !== undefined && n.arguments.length > idx) {
        const arg = n.arguments[idx];
        const value = literalOf(arg);
        if (value === null) {
          unresolved.push(`${name}(${arg.getText().replace(/\s+/g, " ").slice(0, 80)})`);
        } else {
          // `getByTestId` is given the bare name; normalise it to the attribute
          // form so one extraction reads both spellings.
          selectors.push(name === "getByTestId" ? `data-testid="${value}"` : value);
        }
      }
    }
    // Over-covering extraction: ANY string literal mentioning the attribute is
    // read, wherever it sits. This is the safe direction — it cannot hide a
    // hook, it can only demand one that turns out to be prose — and it is what
    // catches a selector handed straight to a helper without a constant.
    if (
      (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) &&
      n.text.includes("data-testid")
    ) {
      selectors.push(n.text);
    }
    ts.forEachChild(n, walk);
  }
  walk(sf);

  return { file, selectors: [...selectors, ...consts.values()], unresolved, calledNames };
}

const RESOLUTIONS: Resolution[] = fs
  .readdirSync(SPEC_DIR)
  .filter((f) => f.endsWith(".spec.ts"))
  .sort()
  .map((f) => resolveSpec(f, fs.readFileSync(path.join(SPEC_DIR, f), "utf8")));

/**
 * The specs that reach a Discover hook at all — the ones this suite answers for.
 *
 * Deliberately decided on the RAW text, which is the broader reading: a file is
 * held to the strict resolvability rule below if the word appears anywhere in
 * it, including a comment. Over-inclusion costs nothing here and under-inclusion
 * would be the hole.
 */
const DISCOVER_SPECS = RESOLUTIONS.filter((r) =>
  fs.readFileSync(path.join(SPEC_DIR, r.file), "utf8").includes("discover-")
);

const PACK_HOOKS: string[] = [
  ...new Set(
    RESOLUTIONS.flatMap((r) => r.selectors).flatMap((s) =>
      [...s.matchAll(/data-testid="([^"]+)"/g)].map((m) => m[1])
    ).filter((id) => id.startsWith("discover-"))
  ),
].sort();

/**
 * The hooks this file asserts. Every entry is checked below — in the DOM where
 * the state is reachable by rendering, and at the source level where it is not,
 * with the measured reason given at that test.
 */
const GUARDED_HOOKS: string[] = [
  "discover-card",
  "discover-empty-state",
  "discover-feed-error",
  "discover-feed-unavailable",
  "discover-skeleton",
];

describe("the guarded set still covers the pack", () => {
  test("the pack selects hooks at all — the extraction is not silently empty", () => {
    // Without this the whole describe passes vacuously the day the spec
    // directory moves, which is precisely when the tripwire is needed.
    expect(RESOLUTIONS.length).toBeGreaterThan(0);
    expect(PACK_HOOKS.length).toBeGreaterThan(0);
  });

  test("every selector the Discover specs build is one this file can resolve", () => {
    // The fail-closed joint, and the whole answer to CERT-584.
    //
    // A selector assembled at runtime — from a helper, a variable the parser
    // cannot follow, a template with a computed part — is a selector Playwright
    // honours and this file cannot read. Rather than trying to enumerate the
    // spellings that could hide one (which is what round 1 did, and lost), any
    // selector argument that does not resolve to a concrete string fails here.
    //
    // Scoped to the specs that reach Discover: calibration, daily-challenge and
    // search-answer legitimately interpolate over their own hook lists, and a
    // guard that taxes files it does not answer for is a guard someone deletes.
    expect(DISCOVER_SPECS.length).toBeGreaterThan(0);
    for (const r of DISCOVER_SPECS) {
      expect(`${r.file}: ${JSON.stringify(r.unresolved)}`).toBe(`${r.file}: []`);
    }
  });

  test("the resolver still understands every selector API the Discover specs call", () => {
    // Anti-vacuity for the check above, and the reason it is not enough to
    // assert "some selectors were found". Battery M16 deleted `locator` from
    // SELECTOR_ARG: the resolvability test stayed green because the resolver
    // had simply stopped looking at `locator()` calls, while module constants
    // and the literal scan kept the selector list non-empty. A check that can
    // be unwired without anything going red is decoration.
    for (const r of DISCOVER_SPECS) {
      const used = REQUIRED_SELECTOR_APIS.filter((api) => r.calledNames.has(api));
      const unknown = used.filter((api) => !(api in SELECTOR_ARG));
      expect(`${r.file}: ${JSON.stringify(unknown)}`).toBe(`${r.file}: []`);
      expect(`${r.file}: ${r.selectors.length > 0}`).toBe(`${r.file}: true`);
    }
  });

  test.each(PACK_HOOKS)("%s is guarded by this suite", (hook) => {
    expect(GUARDED_HOOKS).toContain(hook);
  });

  test("nothing is guarded that the pack does not select", () => {
    // The other direction: a hook retired from the rail should not keep taxing
    // this file. Equality both ways makes the two lists one list.
    expect(GUARDED_HOOKS).toEqual(PACK_HOOKS);
  });
});

describe("Discover empty state carries a stable, named audit hook", () => {
  test("renders data-testid and a machine-readable state name", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={0} onRefresh={noop} />);
    expect(html).toContain('data-testid="discover-empty-state"');
    // The NAME is data, not scraped prose — the audit records this attribute
    // rather than the visible copy, so a reword cannot invalidate the evidence.
    expect(html).toContain('data-empty-state-name="no-markets"');
  });

  test("distinguishes an exhausted feed from a feed that never had anything", () => {
    const exhausted = renderToStaticMarkup(<EndOfFeedCard count={137} onRefresh={noop} />);
    expect(exhausted).toContain('data-empty-state-name="end-of-feed"');
    expect(exhausted).not.toContain('data-empty-state-name="no-markets"');
  });

  test("the hook is unique — one element, not a class sprayed across children", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={5} onRefresh={noop} />);
    expect(occurrences(html, 'data-testid="discover-empty-state"')).toBe(1);
  });

  test("keeps the accessible semantics alongside the test hook", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={5} onRefresh={noop} />);
    // A status role announces the state to assistive tech; the hook is additive.
    expect(html).toContain('role="status"');
    expect(html).toContain("all caught up");
    expect(html).toContain("Refresh feed");
  });
});

describe("the loading skeleton is never mistaken for content", () => {
  test("carries its own hook and NOT the card hook", () => {
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid />);
    expect(html).toContain('data-testid="discover-skeleton"');
    // This is the entire point of the change: the skeleton must be
    // distinguishable from a rendered card by the audit's selector.
    expect(html).not.toContain('data-testid="discover-card"');
    expect(html).not.toContain('data-testid="discover-empty-state"');
  });

  test("is still hidden from assistive tech", () => {
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid />);
    expect(html).toContain('aria-hidden="true"');
  });

  test("still shares the layout class with real cards — which is why the hook was needed", () => {
    // Documents the collision rather than asserting it away: `break-inside-avoid`
    // is a masonry primitive both states legitimately use. The selector was
    // wrong; the styling is not.
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid count={2} />);
    expect(html).toContain("break-inside-avoid");
  });
});

describe("the unavailable feed is a named state, not a blank page", () => {
  // UX-P228: the hook the derived list above caught missing. `unavailable` is
  // the component's DEFAULT reason, so this is the branch every pre-#1909 call
  // site lands on — the most-reached of the three, and the one that was
  // guarded by nothing.

  test("the default reason renders the hook the pack's ERROR_STATE selector names", () => {
    const html = renderToStaticMarkup(<FeedUnavailableNotice onRetry={noop} />);
    expect(html).toContain('data-testid="discover-feed-unavailable"');
    expect(html).toContain('data-reason="unavailable"');
  });

  test.each([
    ["unavailable", "discover-feed-unavailable"],
    ["rate_limited", "discover-feed-error"],
    ["error", "discover-feed-error"],
  ] as const)("reason %s carries hook %s", (reason, hook) => {
    // Three reasons, two hooks, and which maps to which is the contract the
    // rail binds to. A reason silently re-pointed at the other hook keeps this
    // file green under a per-hook existence check; it does not survive here.
    const html = renderToStaticMarkup(
      <FeedUnavailableNotice onRetry={noop} reason={reason} />
    );
    expect(html).toContain(`data-testid="${hook}"`);
  });

  test("is never mistaken for a legitimate empty feed or a skeleton", () => {
    // The same confusion the skeleton tests above exist for: an unavailable
    // feed read as "you're all caught up" is a broken deploy reported as a
    // quiet day.
    for (const reason of ["unavailable", "rate_limited", "error"] as const) {
      const html = renderToStaticMarkup(
        <FeedUnavailableNotice onRetry={noop} reason={reason} />
      );
      expect(html).not.toContain('data-testid="discover-empty-state"');
      expect(html).not.toContain('data-testid="discover-skeleton"');
      expect(html).toContain('role="alert"');
    }
  });

  test("the hook is unique — one element, not sprayed across children", () => {
    const html = renderToStaticMarkup(<FeedUnavailableNotice onRetry={noop} />);
    expect(occurrences(html, 'data-testid="discover-feed-unavailable"')).toBe(1);
  });
});

describe("the Discover page itself renders the hooks the audit selects", () => {
  /**
   * UX-P228: this block used to say a rendering test "would prove less and
   * break more", and asserted the page at the source level on that basis. Both
   * halves were measured and neither held. `useSWR` is a MODULE boundary, so a
   * mock settles it synchronously and the page renders — it is a `useState`
   * cleared in a `useEffect` that defeats a static render, and this page has
   * none on the path to these hooks. And a source grep cannot tell DECLARED
   * from REACHES-THE-DOM, which is the only thing the rail cares about.
   *
   * Every mock below replaces a MODULE boundary and lives inside
   * `isolateModules`, so none of them leaks into the component renders above
   * and none stands in for page-internal state: `isLoading` and `error` are
   * read from SWR, which is the boundary being mocked.
   */
  function domIds(swr: unknown): string[] {
    let html = "";
    jest.isolateModules(() => {
      // Keyed, because the page calls `useSWR` TWICE. Answering both with the
      // feed state made `resolutionsData.resolutions` undefined and the loaded
      // state un-renderable — which silently cost the gap assertion below its
      // most important case until a mutant found it.
      jest.doMock("swr", () => ({
        __esModule: true,
        default: (key: string) =>
          key === "discover-resolutions"
            ? { data: { resolutions: [] }, error: undefined, isLoading: false, mutate: noop }
            : swr,
      }));
      jest.doMock("next/navigation", () => ({
        useRouter: () => ({ push: noop, replace: noop, prefetch: noop }),
        useSearchParams: () => new URLSearchParams(),
        usePathname: () => "/discover",
      }));
      jest.doMock("@/components/Analytics", () => ({
        useAnalyticsContext: () => ({ track: noop }),
      }));
      jest.doMock("@/hooks", () => ({
        useEngagementTime: () => undefined,
        usePageTracking: () => undefined,
        useScrollDepth: () => undefined,
      }));
      jest.doMock("@/components/AuthProvider", () => ({
        useAuthContext: () => ({
          user: null,
          isLoading: false,
          isAuthenticated: false,
          isAuthAvailable: false,
          authError: null,
          signInWithGoogle: async () => {},
          signInWithApple: async () => {},
          signOut: async () => {},
          getToken: async () => null,
        }),
      }));
      // UX-P223-3: `isolateModules` gives the subject a FRESH `react`, so
      // `react-dom/server` must be required INSIDE the registry that will
      // render — the module-scope import above dies on the page's first hook.
      const { renderToStaticMarkup: render } = require("react-dom/server");
      const R = require("react");
      const Page = require("../../app/discover/page").default;
      html = render(R.createElement(Page));
    });
    return [...new Set([...html.matchAll(/data-testid="([^"]+)"/g)].map((m) => m[1]))];
  }

  const swrState = (over: Record<string, unknown>) => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    mutate: noop,
    ...over,
  });

  test("a loading feed reaches the skeleton hook and NOTHING that reads as content", () => {
    const ids = domIds(swrState({ isLoading: true }));
    expect(ids).toContain("discover-skeleton");
    expect(ids).not.toContain("discover-card");
    expect(ids).not.toContain("discover-empty-state");
  });

  test("a failed load reaches the error hook, and never the empty-state hook", () => {
    // The thing the source-level check could not see: that this branch is
    // actually reached, not merely present in the file.
    const ids = domIds(swrState({ error: new Error("boom") }));
    expect(ids).toContain("discover-feed-error");
    expect(ids).not.toContain("discover-empty-state");
    expect(ids).not.toContain("discover-skeleton");
  });

  test("a 429 is still an error state, not an empty one", () => {
    const ids = domIds(swrState({ error: Object.assign(new Error("rl"), { status: 429 }) }));
    expect(ids).toContain("discover-feed-error");
    expect(ids).not.toContain("discover-empty-state");
  });

  test("an empty feed reaches the named empty state, not an error and not a skeleton", () => {
    const ids = domIds(swrState({ data: { items: [] } }));
    expect(ids).toContain("discover-empty-state");
    expect(ids).not.toContain("discover-feed-error");
    expect(ids).not.toContain("discover-skeleton");
  });

  test("no page state reaches discover-feed-unavailable — it is component-level only", () => {
    // STATED GAP, measured rather than assumed. `feedFailureReason` is only
    // ever `rate_limited` or `error`, so the page's error branch cannot emit
    // this hook; the one site that can is gated on the `feedUnavailable`
    // useState, which is set only inside `useEffect`s that a static render
    // never runs. That is why the coverage for it above is a component render.
    // If the page ever grows a statically-reachable path to it, this fails and
    // the DOM assertion should move up here.
    //
    // The fourth state is load-bearing and was added because a mutant survived
    // without it: deleting the `feedUnavailable &&` guard makes the hook fall
    // out of the EMPTY branch, which none of the first three states reaches.
    // "No page state" has to mean every state, or it is an aggregate claim
    // dressed as an exhaustive one.
    for (const s of [
      swrState({ isLoading: true }),
      swrState({ error: new Error("boom") }),
      swrState({ error: Object.assign(new Error("rl"), { status: 429 }) }),
      swrState({ data: { items: [] } }),
    ]) {
      expect(domIds(s)).not.toContain("discover-feed-unavailable");
    }
  });

  const source: string = jest.requireActual("fs").readFileSync(
    require("path").join(__dirname, "..", "..", "app", "discover", "page.tsx"),
    "utf8"
  );

  test("the feed item wrapper carries the card hook", () => {
    // STATED GAP: still source-level. Reaching `discover-card` in the DOM needs
    // a captured `GET /api/feed` payload — a hand-written one silently
    // re-answers "does this render" as "no" (UX-P226-8) — and that fixture is
    // the follow-up slice, not this one.
    expect(source).toContain('data-testid="discover-card"');
  });

  test("the load-failure branch has its own hook and is not an empty state", () => {
    // UX-P087 (#1909): the branch's MARKUP moved into
    // `components/discover/FeedUnavailableNotice`, so the hook is asserted where
    // it now lives. What this test protects is unchanged and is the reason it
    // exists: the hook survives, and a load failure is never reachable through
    // the empty-state hook — an error is not a legitimate empty feed, and
    // conflating them is how a broken deploy reads as a quiet day.
    const notice: string = jest.requireActual("fs").readFileSync(
      require("path").join(
        __dirname, "..", "..", "components", "discover", "FeedUnavailableNotice.tsx",
      ),
      "utf8",
    );
    expect(notice).toContain('discover-feed-error');
    expect(notice).toContain('role="alert"');
    expect(notice).not.toContain("discover-empty-state");

    // And the page still routes its failure branch through that component
    // rather than growing a second, drifting copy of the markup.
    expect(source).toContain("<FeedUnavailableNotice");
    expect(source).not.toContain('data-testid="discover-feed-error"');
  });
});
