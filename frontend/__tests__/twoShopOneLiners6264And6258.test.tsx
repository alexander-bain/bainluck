/**
 * #6264 + #6258 — TWO SHOP ONE-LINERS, ONE REAL RENDER AND ONE SCOPED SCAN.
 *
 * ═══ #6264 — `/privacy` PRINTS "is notcovered" ═══
 *
 * `app/privacy/page.tsx:301`, in the Vercel Web Analytics bullet:
 *
 *     ... it runs on every visit and is <em>not</em>
 *     covered by the analytics choice — a declined visit is still counted.
 *
 * JSX deletes a newline that is ADJACENT TO A TAG. The newline after `</em>` is
 * adjacent to it, so it does not collapse to a space — it disappears, and the
 * reader gets **"is notcovered by the analytics choice"** in the one paragraph
 * on the site that explains why an analytics vendor ignores their consent
 * choice. `{" "}` restores it.
 *
 * ═══ THE SIBLING SCAN — 21 SITES SHARE THE SHAPE AND 20 ARE FINE ═══
 *
 * `</(em|strong|b|i|code|span|a)>\n\s*[A-Za-z(]` matches 21 places across
 * `app/` and `components/`. Every one of the other 20 — calibration:1326,
 * futures/[id]:743/762/853/896/923, LeagueBinaryBoard:132, CommentaryBox:33,
 * WeatherHero:82, TournamentCard:84 and the rest — sits inside a
 * `flex items-center gap-2` container, where each child is its own flex item
 * and the gap supplies the space. They are icon-then-label headings, not prose.
 *
 * The privacy bullet is the only one of the 21 in a plain inline `<li>`, which
 * is why it is the only one that shows. That is why this file renders ONE page
 * and does not carry a repo-wide regex: a repo-wide version of this rule would
 * be 20 parts false, and a guard that must be suppressed 20 times is a guard
 * nobody will keep.
 *
 * ═══ #6258 — `/discover/stats` EMPTY STATE LINKS IN RAW TAILWIND BLUE ═══
 *
 * `app/discover/stats/page.tsx:137` styled its "Discover" link
 * `text-blue-600`. The site is light-mode-only with a token set in
 * `globals.css`, and `text-accent-brand` (#10B981) is the link colour with 212
 * uses across `app/` and `components/`. A raw palette blue is both off-system
 * and, here, the only blue link on a page whose every other colour is a token.
 *
 * 🔴 **The issue's premise is wrong in its specifics and the comment on it says
 * so.** #6258 calls this "the only non-token class in its own file". It is not
 * — three more survive this fix, deliberately:
 *
 *     :183  bg-amber-50 … border-amber-200      the streak tile
 *     :185  text-amber-700                       the streak tile
 *     :249  text-green-600 / text-red-500        correct / incorrect marks
 *
 * `--accent-warning` is a single #F59E0B; there is no amber-50 surface or
 * amber-200 border token to convert the streak tile to without inventing two.
 * `text-red-500` is byte-exact `--accent-danger` (#EF4444) and `text-green-600`
 * is near `--accent-brand`, so both are convertible — but a correct/incorrect
 * mark is a semantic decision, not a link colour, and this is a p3 one-liner in
 * launch week. Named in the issue, not swept in here.
 *
 * So this file asserts the LINK, not the file. A whole-file "no raw palette"
 * scan would be red on master today and red after this fix — it would be
 * measuring the three sites nobody asked for.
 *
 * ═══ ON THE ORACLES ═══
 *
 * #6264 is RENDERED: `/privacy` takes only the three GA4 hooks, so the real
 * page goes through `renderToStaticMarkup` and the assertion reads the string a
 * person reads.
 *
 * #6258 is a SCOPED SOURCE READ, and that is not a fallback to a weaker oracle
 * — it is the only one available AND the right one. `/discover/stats` opens
 * with `loading = true` and clears it from a `useEffect`, which a static render
 * never runs, so the empty-state branch is structurally unreachable here. And a
 * Tailwind class has no runtime behaviour to observe: the class string IS the
 * defect and IS the fix. The read is pinned to the one line, so it cannot drift
 * into the file-wide claim the issue got wrong.
 *
 *   TZ=UTC npx jest --testPathPatterns=twoShopOneLiners6264And6258
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";

const ANALYTICS_HOOKS = {
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
};

/**
 * 🔴 THIS FILE ASSERTS ON MARKUP, AND THE TWO HELPERS IT DOES NOT HAVE ARE THE
 * FINDING.
 *
 * 1. The house `visibleText` replaces every tag with a SPACE. Against a defect
 *    that IS a missing space it manufactures the answer: `is <em>not</em>covered`
 *    reads back as `is  not covered`, so the broken page passed
 *    `toContain("is not covered")` and M1 — reverting the fix — survived the
 *    first sweep green. That helper is right for every other file (it stops
 *    block-level siblings gluing) and wrong for exactly this one.
 *
 * 2. The obvious replacement, stripping tags to `""` the way an inline element
 *    actually renders, is **`js/incomplete-multi-character-sanitization`,
 *    CodeQL HIGH** — `<scr<script>ipt>` survives a single pass, so a regex that
 *    deletes tags is a broken sanitiser wherever it appears. It refused this
 *    sha at notice 32 and it was right to: the fix for that rule is to loop
 *    until stable, and writing a loop here would be building a sanitiser inside
 *    a test that has no untrusted input, purely to satisfy a scanner.
 *
 * The defect is an ADJACENCY in the markup — whether anything sits between
 * `</em>` and `covered` — so the markup is the honest oracle, not a proxy for
 * it. `renderToStaticMarkup` emits no comment separators, so `<em>not</em>`
 * followed immediately by `covered` is exactly what a reader sees glued
 * together, verified by reading the rendered string on master:
 *
 *     "it runs on every visit and is <em>not</em>covered by the analytics"
 *
 * Every assertion below reads that string. Nothing is stripped, so nothing can
 * be manufactured by the stripping.
 */

describe("#6264 — /privacy does not glue a word to the end of an emphasis", () => {
  function renderPrivacy(): string {
    let markup = "";
    jest.isolateModules(() => {
      jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
      /* eslint-disable @typescript-eslint/no-var-requires */
      const render = require("react-dom/server").renderToStaticMarkup;
      const Page = require("@/app/privacy/page").default;
      /* eslint-enable @typescript-eslint/no-var-requires */
      markup = render(React.createElement(Page));
    });
    return markup;
  }

  /**
   * The ONE bullet under test.
   *
   * 🔴 The privacy page carries two near-identical sentences, in adjacent
   * bullets, and only one was broken:
   *
   *   :291  Speed Insights  `<em>not</em> covered` — space on the same line, fine
   *   :301  Web Analytics   `<em>not</em>\ncovered` — the newline JSX deletes
   *
   * The first version of this file asserted over the whole page, so the healthy
   * Speed Insights bullet satisfied every claim about the broken Web Analytics
   * one — M2, which deleted the `<em>` from :301 entirely, survived green on
   * :291's surviving tag. Scoped to the bullet, neither mutant can hide behind
   * its neighbour.
   */
  /**
   * Keyed on the `<strong>` heading, NOT on the vendor's name in prose.
   *
   * `split("<li")[0]` is everything BEFORE the first bullet, and the Analytics
   * section up there says "See Vercel Speed Insights and Vercel Web Analytics
   * in the third-party list below" — so a `.find` on the bare vendor name
   * returns the preamble, which contains neither sentence. The vacuity row
   * below caught it; the marker is what fixes it.
   */
  function bulletFor(markup: string, vendor: string): string {
    return (
      markup
        .split("<li")
        .find((chunk) => chunk.includes(`<strong>${vendor}</strong>`)) ?? ""
    );
  }

  function webAnalyticsBullet(markup: string): string {
    return bulletFor(markup, "Vercel Web Analytics");
  }

  /** The sentence as it stands in the markup once the emphasis is closed. */
  const JOINED = "it runs on every visit and is <em>not</em>covered by the analytics choice";
  const SPACED = "it runs on every visit and is <em>not</em> covered by the analytics choice";

  it("finds the Web Analytics bullet, and finds it apart from its twin", () => {
    // Without this, every assertion below passes vacuously on "".
    const bullet = webAnalyticsBullet(renderPrivacy());
    expect(bullet).not.toBe("");
    expect(bullet).toContain("a declined visit is still counted");
    // The neighbouring Speed Insights bullet must NOT be in this slice, or the
    // scoping bought nothing.
    expect(bullet).not.toContain("Speed Insights");
  });

  it("reads 'is not covered', not 'is notcovered'", () => {
    const bullet = webAnalyticsBullet(renderPrivacy());

    // The photographed defect, in the exact form the renderer produced it on
    // master. Both directions: the glued form is gone AND the spaced form is
    // there, so deleting the sentence does not pass.
    expect(bullet).not.toContain(JOINED);
    expect(bullet).toContain(SPACED);
  });

  it("the emphasis survives — the fix is a space, not a deleted tag", () => {
    // Deleting `<em>` would satisfy `not.toContain(JOINED)` above and lose the
    // emphasis that carries the sentence's meaning: it is *not* covered.
    // `SPACED` already embeds the tag, so this is belt-and-braces on the tag
    // existing at all in the bullet.
    expect(webAnalyticsBullet(renderPrivacy())).toContain("<em>not</em>");
  });

  it("the healthy twin bullet is untouched", () => {
    // Speed Insights says the same thing one bullet up and was always correct.
    // A repair that reflowed the whole list, or "fixed" both, would show here.
    const speedInsights = bulletFor(renderPrivacy(), "Vercel Speed Insights");
    expect(speedInsights).not.toBe("");
    expect(speedInsights).toContain(SPACED);
    expect(speedInsights).not.toContain(JOINED);
  });
});

describe("#6258 — the /discover/stats empty state links in the accent token", () => {
  const source = readFileSync(
    join(__dirname, "..", "app", "discover", "stats", "page.tsx"),
    "utf8"
  );

  /** The one line the issue names — the "Discover" link in the empty state. */
  const linkLine =
    source.split("\n").find((l) => l.includes('href="/discover"') && l.includes("to start tracking")) ?? "";

  it("finds the line it claims to be reading", () => {
    // A `find` that missed would leave every assertion below testing "".
    expect(linkLine).not.toBe("");
    expect(linkLine).toContain(">Discover</Link>");
  });

  it("uses the design-system accent, not a raw palette blue", () => {
    expect(linkLine).toContain("text-accent-brand");
    expect(linkLine).not.toMatch(/text-blue-[0-9]/);
  });

  it("keeps the underline-on-hover affordance", () => {
    // A swap that dropped `hover:underline` would satisfy the row above and
    // leave the only link on an empty state with no hover affordance at all.
    expect(linkLine).toContain("hover:underline");
  });
});
