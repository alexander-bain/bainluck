/**
 * #3978 (Alex, D93 = A) — at the accessibility text sizes the event hero stacks
 * into bounded rows. #10796 keeps teams together above the percentage and
 * begins this layout at xxLarge so modest increases remain readable.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * With Larger Accessibility Sizes on, `bainluck://events/416567` (Clemson 10 –
 * LSU 51) had no margins at all. The hero's three columns cannot fit side by
 * side at `.accessibility3`, so the row overflowed its parent and was CENTRED in
 * the overflow — bleeding off BOTH edges at once. `Clemson Tigers` rendered as
 * `Cle m…`, the `FINAL` chip was cut off the left edge while "Sep 5 at 6:40 PM"
 * was cut off the right, in the same frame.
 *
 * ═══ THE MECHANISM, AND THE ONE LINE THAT CAUSED IT ═══
 *
 * `.fixedSize(horizontal: true, vertical: false)` on the centre column. In a ROW
 * that is correct and deliberate: the column holds "LSU Tigers Win" and a 36pt
 * duel, and letting SwiftUI squeeze it produces `LSU Ti…` beside two logos with
 * room to spare. In a COLUMN it is the whole defect.
 *
 * A `VStack` sizes to its widest child, so ONE child wider than the phone drags
 * the whole content column past the screen and every sibling gets centred in
 * that overflow with it. **That is why fixing the hero also fixed `Game
 * Segments`, `Score by period`, the chart header and the segmented control** —
 * measured, not argued
 * (`artifacts-native-071/{BEFORE,AFTER}-3978-ax-xl-ncaaf-416567.png`). #3978's
 * body reasons that "every affected section is affected independently rather
 * than the page being one wide sheet" and therefore expects a page-level
 * containment rule as well; the renders say those sections were downstream of
 * one overflowing child, and no containment rule was added.
 *
 * WHAT IS STILL BROKEN, SO NOBODY READS THE ABOVE AS "THE PAGE IS FIXED": on the
 * MLB specimen (`15304933`) the Game Segments table is TEN columns (innings 1–9
 * plus T) and still runs past the right edge at `accessibility-extra-large` —
 * `AFTER-3978-ax-xl-mlb-15304933.png`. That is a genuinely too-wide table
 * overflowing one edge, not the symmetric both-edges bleed this ship fixed, and
 * it is filed on its own rather than folded in here.
 *
 * ═══ WHY A SOURCE SCAN ═══
 *
 * CI COMPILES NO SWIFT. `heroSection` is a `private func` on a view returning
 * `some View`; XCTest cannot reach a layout container or a modifier argument, so
 * restoring the single word `true` on the `fixedSize` below leaves the entire
 * Swift suite green while putting the bleed back on the page. This file is the
 * only thing between that mutant and production.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const DETAIL = join(IOS_ROOT, "Views/EventDetailView.swift");
const CARD = join(IOS_ROOT, "Components/EventSportHeadlineCard12472.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass.
const d = existsSync(DETAIL) && existsSync(CARD) ? describe : describe.skip;

d("#3978 — the event hero restacks at accessibility text sizes", () => {
  const detail = () => readFileSync(DETAIL, "utf8");
  const card = () => readFileSync(CARD, "utf8");
  const code = () => stripComments(detail());
  const cardCode = () => stripComments(card());

  function heroBody(): string {
    const source = code();
    const start = source.indexOf("private func heroSection(");
    expect(start).toBeGreaterThan(-1);
    const next = source.indexOf("\n    static ", start + 1);
    const nextPriv = source.indexOf("\n    private ", start + 1);
    const end = [next, nextPriv].filter((idx) => idx > start).sort((a, b) => a - b)[0];
    expect(end).toBeGreaterThan(start);
    return source.slice(start, end);
  }

  it("the view and unified headline card read the reader's text size from the environment", () => {
    expect(code()).toMatch(
      /@Environment\(\\\.dynamicTypeSize\) private var dynamicTypeSize/
    );
    expect(cardCode()).toMatch(
      /@Environment\(\\\.dynamicTypeSize\) private var dynamicTypeSize/
    );
  });

  it("heroSection unconditionally mounts EventSportHeadlineCard12472 with one shared stacking predicate", () => {
    expect(heroBody()).toMatch(/EventSportHeadlineCard12472\(/);
    expect(cardCode()).toMatch(
      /private var stacksRowsVertically: Bool \{\s*dynamicTypeSize\.isAccessibilitySize\s*\}/
    );
  });

  it("top bar and competitor rows restack vertically at accessibility sizes", () => {
    const body = cardCode();
    expect(body).toMatch(
      /let layout = stacksRowsVertically\s*\? AnyLayout\(VStackLayout\(alignment: \.leading, spacing: 6\)\)\s*: AnyLayout\(HStackLayout\(alignment: \.center, spacing: 8\)\)/
    );
    expect(body).toMatch(/layout \{/);
    expect(body).toMatch(/if stacksRowsVertically \{\s*VStack\(alignment: \.leading, spacing: 4\)/);
  });

  it("THE MUTANT: live league text never forces horizontal fixedSize when stacked", () => {
    const body = cardCode();
    expect(body).toMatch(
      /\.fixedSize\(horizontal: !stacksRowsVertically, vertical: stacksRowsVertically\)/
    );
  });

  it("the mutant check is looking at the right component, and would still fire", () => {
    const body = cardCode();
    expect(body).toMatch(/private func competitorRowView\(/);
    const mutated = body.replace(
      /\.fixedSize\(horizontal: !stacksRowsVertically, vertical: stacksRowsVertically\)/,
      ".fixedSize(horizontal: true, vertical: false)"
    );
    expect(mutated).not.toMatch(
      /\.fixedSize\(horizontal: !stacksRowsVertically, vertical: stacksRowsVertically\)/
    );
  });

  it("the row arrangement keeps its Spacer and the stacked column gates it", () => {
    expect(cardCode()).toMatch(/if !stacksRowsVertically \{\s*Spacer\(minLength: 6\)\s*\}/);
  });
});
