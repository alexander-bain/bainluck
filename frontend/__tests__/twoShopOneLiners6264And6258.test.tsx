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

/** Strip tags so the assertion reads what a PERSON reads. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[’]/g, "'")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

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

  it("renders the analytics bullet at all", () => {
    // Without this, both assertions below pass vacuously on an empty render.
    const text = visibleText(renderPrivacy());
    expect(text).toContain("Vercel Web Analytics");
    expect(text).toContain("a declined visit is still counted");
  });

  it("reads 'is not covered', not 'is notcovered'", () => {
    const text = visibleText(renderPrivacy());

    // The photographed defect.
    expect(text).not.toContain("notcovered");
    expect(text).toContain("it runs on every visit and is not covered by the analytics choice");
  });

  it("the emphasis survives — the fix is a space, not a deleted tag", () => {
    // Deleting `<em>` would satisfy the row above and lose the emphasis that
    // carries the sentence's meaning: it is *not* covered.
    const markup = renderPrivacy();
    expect(markup).toContain("<em>not</em>");
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
