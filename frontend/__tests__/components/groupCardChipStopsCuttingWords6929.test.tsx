/**
 * #6929 — A GROUP CARD'S CATEGORY CHIP RAN OUTSIDE ITS OWN CARD AND WAS CUT MID-WORD.
 *
 * ── WHAT THE READER SAW ─────────────────────────────────────────────────────
 *
 * bainluck.com Discover, page one, 390px, 2026-09-18 ~11:40Z, during a D48 walk.
 * The first thing on a golf group card:
 *
 *     ⛳ NATIONWIDE CHILDREN'S HOSPITAL CHAMPIONSHI
 *
 * Cut mid-word at the card's right edge, no ellipsis, nothing to tell the reader a
 * word is missing. Not a wrap, not a truncation — the card's own `overflow-hidden`
 * performing a cut on ink that had already left the card.
 *
 * ── THE CAUSE ───────────────────────────────────────────────────────────────
 *
 * `GroupCard.tsx` and `ThemeBundleCard.tsx` carried byte-identical chip markup:
 * `whitespace-nowrap` with NO width cap. `whitespace-nowrap` forbids wrapping, and a
 * flex item's default `min-width: auto` refuses to shrink below its content, so the
 * chip claimed its full intrinsic width — past the column, past the card — and the
 * card clipped it.
 *
 * The `min-w-0` on the parent flex column is not enough and is the trap here: it lets
 * the COLUMN shrink, which is why the defect looks like it should already be handled.
 * The chip itself was never shrinkable.
 *
 * ThemeBundleCard's own comment states the design intent — "The chip stays the
 * category badge it was" — i.e. a short word like "⛳ Golf". But `title` is whatever
 * the bundle is called, here a 45-character tournament name, and the chip cannot
 * enforce that intent from where it sits. So the fix constrains the chip rather than
 * trusting its input: any label degrades to an ellipsis instead of a cut.
 *
 * ── THE MEASUREMENT, BECAUSE A SCREENSHOT CANNOT GRADE THIS ─────────────────
 *
 * A clipped node renders identically to a node that simply ends. The numbers come off
 * the layout engine, not an eyeball.
 *
 * The natural specimen ROTATED OFF THE FEED between filing and fixing — the merged
 * sweep `tools/card-horiz-overflow-6929.mjs` read CARD-ESCAPE=1 on `/` at 11:40Z and
 * CARD-ESCAPE=0 at 13:30Z with both source files byte-unchanged. An absent specimen
 * grades nothing in either direction, so one was MANUFACTURED against production's own
 * CSS in a real browser at 390px (`tools/ux1334-chip-escape-6929.mjs`): clone a real
 * card off the live page, swap ONLY the chip's class string, hold everything else
 * identical.
 *
 *     OLD (shipped)   escape=+13.5px  ellipsis=false  text-overflow=clip
 *     NEW (this fix)  escape=-44.0px  ellipsis=true   text-overflow=ellipsis
 *
 * The manufactured OLD reproduces the filed measurement — 13.5px against latency's
 * 13.6px — which is what licenses the NEW row to stand for the real fix.
 *
 * ── WHAT THIS FILE ASSERTS, AND WHY IT IS NOT THE MEASUREMENT ───────────────
 *
 * jsdom does not lay out: it would report this chip as fine both before and after, so
 * a rendered-geometry assertion here would be green on the broken code. The division
 * of labour is therefore explicit —
 *
 *   * the browser probe proves the NEW class string does not escape and the OLD one
 *     does (that is a fact about CSS, and it is measured once, above);
 *   * THIS FILE proves the shipped components actually put the NEW string on the chip,
 *     on BOTH branches, and that a future edit cannot quietly take it off again.
 *
 * Neither half is sufficient alone, which is the reason both exist.
 *
 * It asserts over the RENDERED markup rather than the source text, so the chip's
 * class has to survive `getCat()`'s interpolation and the whole `DiscoverCard` routing
 * to count — a source scan would pass on a class string that never reached the DOM.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";

/** The production specimen's title, verbatim from the issue. 43 chars + the emoji the chip adds. */
const LONG_TITLE = "Nationwide Children's Hospital Championship";

/** The short label the chip was designed for — the other side of the range it must cover. */
const SHORT_TITLE = "Golf";

function member(id: number, name: string): FeedItem {
  return {
    type: "futures",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id,
      name,
      llm_sport_category: "golf",
      top_outcomes: [{ id, name: "Yes", probability: 0.42, movement: null }],
      outcome_count: 3,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

const MEMBERS = [member(1, "Scheffler to win"), member(2, "Morikawa to win")];

/**
 * `kind` picks the branch: "theme" routes to ThemeBundleCard, anything else to
 * GroupCard (`DiscoverCard.tsx:179`). Both carried the defect, so both are rendered.
 */
function render(kind: string, title: string): string {
  const item = {
    type: "bundle",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id: `${kind}:golf:1-2`,
      title,
      kind,
      shared_question: "What happens at the Nationwide Children's Hospital Championship?",
      item_count: MEMBERS.length,
      member_ids: [1, 2],
      items: MEMBERS,
    } as unknown as FeedBundleData,
  } as unknown as FeedItem;
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
  );
}

/**
 * The chip's class attribute, located by the category colour pair `getCat("golf")`
 * produces. Anchored on what the chip IS (the category badge) rather than on a line
 * number or on the fix's own classes, so a guard cannot pass by finding itself.
 */
function chipClass(html: string): string {
  const m = html.match(/class="([^"]*bg-lime-600\/15[^"]*)"/);
  expect(m).not.toBeNull();
  return m![1];
}

/**
 * THE PREDICATE, stated once and used on both real markup and the positive control.
 *
 * All three properties, together, because each alone leaves the cut reachable:
 *   * `truncate` alone — sets overflow/ellipsis, but a flex item with `min-width:auto`
 *     never shrinks to a width where the ellipsis can engage, so nothing changes;
 *   * `min-w-0` alone — the chip shrinks and the text is cut with NO ellipsis, which
 *     is the original reader-visible defect with a smaller escape;
 *   * `max-w-full` alone — caps against the container, does not make the text legible
 *     about being cut.
 */
function isConstrained(cls: string): boolean {
  return /\bmin-w-0\b/.test(cls) && /\bmax-w-full\b/.test(cls) && /\btruncate\b/.test(cls);
}

/** The exact class string that shipped, from `GroupCard.tsx:72` before this fix. */
const SHIPPED_CHIP =
  "bg-lime-600/15 text-lime-700 text-[10px] font-bold uppercase tracking-wider " +
  "px-2 py-0.5 rounded-full whitespace-nowrap";

describe("#6929 a group card's category chip stays inside its card", () => {
  it.each([
    ["GroupCard (kind:comparison)", "comparison"],
    ["ThemeBundleCard (kind:theme)", "theme"],
  ])("%s constrains the chip so a long title ellipsises instead of being cut", (_label, kind) => {
    // BOTH branches, because the two files carried identical markup and a fix applied
    // to one of them leaves the other cutting words on the same page.
    expect(isConstrained(chipClass(render(kind, LONG_TITLE)))).toBe(true);
  });

  it.each([
    ["GroupCard (kind:comparison)", "comparison"],
    ["ThemeBundleCard (kind:theme)", "theme"],
  ])("%s no longer relies on a bare nowrap with nothing capping the width", (_label, kind) => {
    // The defect was not "nowrap" — it was nowrap with no cap. `truncate` supplies
    // `white-space: nowrap` itself, so the bare utility should now be gone from the
    // chip; if it comes back ALONGSIDE the cap that is harmless, which is why the
    // assertion above is the load-bearing one and this is the narrower statement.
    const cls = chipClass(render(kind, LONG_TITLE));
    expect(/\bwhitespace-nowrap\b/.test(cls) && !isConstrained(cls)).toBe(false);
  });

  it("still renders the short category label the chip was designed for", () => {
    // The fix must not be a regression for the 99% case. `truncate` on a chip that
    // fits changes nothing a reader can see, and the label must still be present in
    // full — a fix that ellipsised "⛳ Golf" would be worse than the bug.
    const html = render("comparison", SHORT_TITLE);
    expect(html).toContain("⛳ Golf");
    expect(isConstrained(chipClass(html))).toBe(true);
  });

  it("POSITIVE CONTROL: the predicate fires on the markup that shipped", () => {
    // Without this the three assertions above could be describing something other
    // than the bug, and would stay green if `isConstrained` were mis-written to be
    // satisfied by everything.
    expect(isConstrained(SHIPPED_CHIP)).toBe(false);
    expect(/\bwhitespace-nowrap\b/.test(SHIPPED_CHIP)).toBe(true);
    // And the locator finds it, so a green run above is a real read and not a miss.
    expect(chipClass(`<span class="${SHIPPED_CHIP}">x</span>`)).toBe(SHIPPED_CHIP);
  });

  it("CONTROL: the premise is intact — the card shell still clips its overflow", () => {
    // The guard must not be able to go green because the CARD stopped clipping. That
    // would "fix" the cut by letting the chip paint over the page instead, which is a
    // different and worse defect, and every assertion above would still pass.
    expect(render("comparison", LONG_TITLE)).toContain("overflow-hidden");
  });

  it("CONTROL: the sibling count keeps its nowrap — this was not a blanket sweep", () => {
    // THE FIX THAT WOULD HAVE BEEN WRONG. Running `truncate` over every nowrap in
    // these files also hits "· N related" / "N markets", a 9-character string that
    // must never wrap or ellipsise and never overflowed anything. A blanket edit
    // passes all six assertions above while quietly degrading a second label.
    // `sharedQuestion` is what hides that sibling, so it is dropped for this render.
    const item = {
      type: "bundle",
      score: 70,
      reason: "",
      headline: null,
      data: {
        id: "theme:golf:1-2",
        title: SHORT_TITLE,
        kind: "theme",
        item_count: MEMBERS.length,
        member_ids: [1, 2],
        items: MEMBERS,
      } as unknown as FeedBundleData,
    } as unknown as FeedItem;
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
    );

    // The sibling is present on this branch (premise), and it is still a plain nowrap.
    expect(html).toContain("related");
    const sibling = html.match(/class="([^"]*text-text-muted[^"]*whitespace-nowrap[^"]*)"/);
    expect(sibling).not.toBeNull();
    expect(/\btruncate\b/.test(sibling![1])).toBe(false);
  });
});
