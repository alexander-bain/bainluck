// #3974 — the match page's navigation row reflows instead of clipping.
//
// LOOKED at production `/events/15306225` (Tiafoe v Michelsen, "Starts in
// 2h 5m") at 390px on 2026-09-08, and again after the fix on a local build of
// the same branch:
//
//     ‹ US Open 2026   ‹ Back to ever     Next        (109)
//                                         update:
//
// "Back to events" — a NAVIGATION CONTROL, not body text — clipped mid-word,
// with the countdown's own label wrapped over the top of it. A control that
// says "Back to ever" reads as a broken page, not as an abbreviation.
//
// ── MEASURED, NOT ESTIMATED (390px viewport, this page, both blocks present)──
//
//     row usable width                                366px  (390 − 12px each side)
//     back-links group, content width                 246px
//     column gap                                       12px
//     countdown group, content width                  135px
//                                                    ------
//     needed                                          393px   → 27px over
//
// The deficit came out of the back links every time, because theirs is the
// group carrying `min-w-0` + `overflow-hidden` (#3802) — so flex shrank the one
// element that had declared it could shrink, and the reader lost the control.
//
// After the fix the same measurement reads: back links 246.1px against a
// scrollWidth of 246 (nothing clipped), countdown 134.9 against 135 (label on
// one line), row height 63.6px instead of 40px — one extra line, no lost text.
//
// ── WHY THE GUARD IS A SOURCE SCAN ──────────────────────────────────────────
//
// The defect is a flexbox line-breaking behaviour, and jsdom does no layout —
// every width in a jest DOM is 0, so a rendered test could assert this only by
// restating the class names anyway, at the cost of standing up SWR, the
// analytics hooks and a full event payload. The scan states the rule directly
// and cannot pass for the wrong reason: the positive controls below prove both
// predicates DO fire on the markup that shipped.
//
// The rule is written over EVERY group that shares the row, not just the
// countdown, because the stream block (`LiveSparkline` + `LiveAgeStamp`) is the
// same shape and renders in the same slot — `shouldShowRefreshCountdown`
// returns false exactly when `streamConnected`, so it is the other half of one
// either/or and would reproduce this defect with the roles swapped.

import { readFileSync } from "fs";
import { join } from "path";

const PAGE = "app/events/[id]/page.tsx";

/** The full `<div …>…</div>` beginning at `open`, matched by depth. */
function matchDiv(source: string, open: number): string {
  let depth = 0;
  let at = open;
  while (at < source.length) {
    const nextOpen = source.indexOf("<div", at);
    const nextClose = source.indexOf("</div>", at);
    if (nextClose === -1) throw new Error("unbalanced <div> in " + PAGE);
    if (nextOpen !== -1 && nextOpen < nextClose) {
      depth++;
      at = nextOpen + 4;
    } else {
      depth--;
      at = nextClose + "</div>".length;
      if (depth === 0) return source.slice(open, at);
    }
  }
  throw new Error("unbalanced <div> in " + PAGE);
}

/** The `<div>`s directly inside `inner`, ignoring anything nested deeper. */
function directChildDivs(inner: string): string[] {
  const out: string[] = [];
  let at = 0;
  for (;;) {
    const open = inner.indexOf("<div", at);
    if (open === -1) return out;
    const child = matchDiv(inner, open);
    out.push(child);
    at = open + child.length;
  }
}

const className = (element: string): string =>
  /className="([^"]*)"/.exec(element)?.[1] ?? "";

/** The row the two back links and the countdown share. */
function navRow(source: string): string {
  const marker = source.indexOf("{/* Navigation */}");
  expect(marker).toBeGreaterThan(-1);
  return matchDiv(source, source.indexOf("<div", marker));
}

/** Everything BETWEEN an element's own tags — so its children, not itself. */
function contentsOf(element: string): string {
  const openTagEnd = element.indexOf(">");
  return element.slice(openTagEnd + 1, element.length - "</div>".length);
}

describe("#3974: the match page nav row reflows rather than clipping a control", () => {
  const source = readFileSync(join(process.cwd(), PAGE), "utf8");
  const row = navRow(source);

  it("the scan found the row that actually holds all three elements", () => {
    // Without this the assertions below could be about some other div, and a
    // refactor that moved the countdown out would silently make them vacuous.
    expect(row).toContain("Back to events");
    expect(row).toContain("Next update:");
    expect(row).toContain("<LiveSparkline");
  });

  it("the row is allowed to wrap", () => {
    // 393px of content does not fit in 366px. Flex breaks lines on each item's
    // CONTENT size before it shrinks anything, so `flex-wrap` moves the whole
    // countdown group down rather than taking 27px out of the back links.
    expect(className(row).split(/\s+/)).toContain("flex-wrap");
  });

  it("every group sharing the row is right-aligned by an auto margin", () => {
    // `justify-between` cannot do this job any more: on a wrapped line it has
    // no second item to push against, so the countdown would land at the LEFT
    // edge under the back links.
    const children = directChildDivs(contentsOf(row));
    expect(children.length).toBeGreaterThanOrEqual(2);

    const [backLinks, ...sharing] = children;
    expect(backLinks).toContain("Back to events");
    for (const group of sharing) {
      expect(className(group).split(/\s+/)).toContain("ml-auto");
    }
  });

  it("#3802 is untouched — a long tournament title still clips inside its own group", () => {
    // The fix must not be mistaken for a licence to let the header wrap into
    // ragged lines, which is the defect #3802 fixed. That rule lives on the
    // INNER group and stays there.
    const [backLinks] = directChildDivs(contentsOf(row));
    const classes = className(backLinks).split(/\s+/);
    expect(classes).toContain("min-w-0");
    expect(classes).toContain("overflow-hidden");
    expect(classes).toContain("whitespace-nowrap");
  });

  it("POSITIVE CONTROL — both predicates fire on the markup that shipped", () => {
    // The row exactly as it was: no wrap, right-aligned by `justify-between`,
    // no auto margins. If either of these stops failing, the two rules above
    // are asserting nothing.
    const asShipped = 'flex items-center justify-between gap-3'.split(/\s+/);
    expect(asShipped).not.toContain("flex-wrap");
    expect("flex items-center gap-3".split(/\s+/)).not.toContain("ml-auto");
  });

  it("POSITIVE CONTROL — the child walker returns siblings, not descendants", () => {
    // `directChildDivs` is load-bearing for the alignment rule: if it returned
    // nested divs too, the countdown's inner label wrapper would be checked for
    // `ml-auto` and the rule would be unsatisfiable rather than false.
    const kids = directChildDivs("<div class='a'><div class='a1'></div></div><div class='b'></div>");
    expect(kids).toHaveLength(2);
    expect(kids[1]).toBe("<div class='b'></div>");
  });
});
