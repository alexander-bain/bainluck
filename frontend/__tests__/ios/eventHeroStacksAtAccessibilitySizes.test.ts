/**
 * #3978 (Alex, D93 = A) — at the accessibility text sizes the event hero stacks
 * vertically: away team, then the percentage, then home team.
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

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass.
const d = existsSync(DETAIL) ? describe : describe.skip;

d("#3978 — the event hero restacks at accessibility text sizes", () => {
  const detail = () => readFileSync(DETAIL, "utf8");
  const code = () => stripComments(detail());

  /**
   * `heroSection`'s body alone.
   *
   * Scoped for the reason the #3966 guard had to be: `EventDetailView` is ~2,000
   * lines and draws several unrelated rows, at least one of which is legitimately
   * a fixed-size HStack. A whole-file assertion here would not read as strict, it
   * would read as wrong, and the only way to green it would be to change layouts
   * nobody asked about.
   */
  function heroBody(): string {
    const source = code();
    const start = source.indexOf("private func heroSection(");
    expect(start).toBeGreaterThan(-1);
    const next = source.indexOf("\n    private ", start + 1);
    expect(next).toBeGreaterThan(start);
    return source.slice(start, next);
  }

  it("the view reads the reader's text size from the environment", () => {
    // Not `UIApplication.shared.preferredContentSizeCategory`: that reads the
    // APP's setting and ignores any `.dynamicTypeSize` a parent has applied, so
    // it measures a different size from the one being drawn.
    expect(code()).toMatch(
      /@Environment\(\\\.dynamicTypeSize\) private var dynamicTypeSize/
    );
  });

  it("the decision is `isAccessibilitySize`, taken once and shared by both rows", () => {
    // One `let`, not two call sites: the meta row and the team row must agree.
    // A hero whose badge row stacked while its teams did not would be a third
    // layout nobody designed.
    const body = heroBody();
    expect(body).toMatch(/let stacked = dynamicTypeSize\.isAccessibilitySize/);
    expect(body).toMatch(/let heroLayout = stacked\n\s*\? AnyLayout\(VStackLayout/);
    expect(body).toMatch(/let metaLayout = stacked\n\s*\? AnyLayout\(VStackLayout/);
    // …and the non-accessibility arm is still the row it always was.
    expect(body).toMatch(/: AnyLayout\(HStackLayout\(spacing: 0\)\)/);
    expect(body).toMatch(/: AnyLayout\(HStackLayout\(spacing: 8\)\)/);
  });

  it("both rows are drawn THROUGH the switching layout, not beside it", () => {
    // The hazard `AnyLayout` invites: declare the layout, then forget to use it
    // and leave the literal `HStack` in place. Both `let`s above would still be
    // there and the page would be unchanged.
    const body = heroBody();
    expect(body).toMatch(/metaLayout \{/);
    expect(body).toMatch(/heroLayout \{/);
    expect(body).not.toMatch(/\n\s*HStack\(spacing: 0\) \{\n\s*\/\/ Away team/);
  });

  it("THE MUTANT: the centre column does not go back to a hard fixed size", () => {
    // `.fixedSize(horizontal: true, vertical: false)` is the pre-fix line,
    // verbatim from origin/master d448e172. One word, and the bleed is back.
    const body = heroBody();
    expect(body).toMatch(/\.fixedSize\(horizontal: !stacked, vertical: false\)/);
    expect(body).not.toMatch(/\.fixedSize\(horizontal: true, vertical: false\)/);
  });

  it("the mutant check is looking at the right function, and would still fire", () => {
    // A silently-empty slice would make every assertion above vacuous.
    const body = heroBody();
    expect(body).toMatch(/Giant probabilities centered|heroStatusBadge\(event\)/);
    const mutated = body.replace(
      /\.fixedSize\(horizontal: !stacked, vertical: false\)/,
      ".fixedSize(horizontal: true, vertical: false)"
    );
    expect(mutated).toMatch(/\.fixedSize\(horizontal: true, vertical: false\)/);
    expect(mutated).not.toMatch(/\.fixedSize\(horizontal: !stacked, vertical: false\)/);
  });

  it("the row arrangement keeps its Spacer and the column does not", () => {
    // A `Spacer` pushes to both ends of a row; in a column it is a blank line
    // that shoves the date away from the badge. Gating it is not tidiness — an
    // ungated Spacer is a visible gap in the stacked hero.
    expect(heroBody()).toMatch(/if !stacked \{ Spacer\(\) \}/);
  });
});
