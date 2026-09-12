/**
 * #4094 — a settled card must not draw an empty footer row.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Alex, on My Stuff → "Just Happened", Tue 2026-09-08: *"every finished Red Sox
 * game says 'Line moving' and 'odds shifted 46% during the game'. Of course it
 * did: a game starts near 50/50 and ends at 100/0."* The backend half of #4094
 * stops both strings on a settled card — `highlights.get_highlight_label` no
 * longer labels a finished game "Line moving", and
 * `feed_reasons.generate_event_reason` no longer captions it "… odds shifted N%
 * during the game".
 *
 * ═══ WHY THAT NEEDED A CLIENT CHANGE TOO ═══
 *
 * `EventCardView.footer` was an unconditional child of the body's
 * `VStack(spacing: 8)`. An `HStack` holding only a `Spacer()` is NOT an
 * `EmptyView` — it still takes its turn in the stack and still draws the 8pt of
 * spacing above it. That state was already reachable before #4094 (a finished
 * card whose `reason` came back empty), but the backend fix turns it from a rare
 * card into most of Just Happened. Shipping the string fix alone would have
 * traded a wrong caption for a strip of dead space under every settled card.
 *
 * ═══ WHY A SOURCE SCAN ═══
 *
 * CI COMPILES NO SWIFT. `EventCardFooterEmptinessTests` pins
 * `EventCardFooter.hasContent`, which is a pure function and reachable from
 * XCTest — but nothing in XCTest can see whether `footer` actually CALLS it.
 * `footer` is a `private var` on a view returning `some View`; deleting the `if`
 * and rendering `footerRow` unconditionally puts the gap straight back with the
 * entire Swift suite still green, because every assertion over the helper keeps
 * passing. This file is the only thing between that mutant and production.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CARD = join(IOS_ROOT, "Components/EventCardView.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass.
const d = existsSync(CARD) ? describe : describe.skip;

d("#4094 — the settled card's footer is not drawn when it is empty", () => {
  const code = () => stripComments(readFileSync(CARD, "utf8"));

  /**
   * `footer`'s body alone, up to `footerRow`.
   *
   * Scoped to the property for the reason the #3966 and #3978 guards had to be:
   * `EventCardView` draws several unconditional rows that are legitimately
   * unguarded (`topBar`, `teamsAndOdds`). A whole-file rule would not read as
   * strict, it would read as wrong, and greening it would mean changing layouts
   * nobody asked about.
   */
  function footerBody(): string {
    const source = code();
    const start = source.indexOf("private var footer: some View {");
    expect(start).toBeGreaterThan(-1);
    const next = source.indexOf("private var footerRow: some View {", start + 1);
    expect(next).toBeGreaterThan(start);
    return source.slice(start, next);
  }

  it("THE MUTANT: `footerRow` is drawn only behind the emptiness check", () => {
    // The pre-fix shape, verbatim: `footer` WAS the `HStack`, with no guard at
    // all. Restoring it — or keeping the helper and dropping the `if` — is the
    // one-line change that puts 8pt of dead space under every settled card.
    const body = footerBody();
    expect(body).toMatch(/if EventCardFooter\.hasContent\(/);
    expect(body).toMatch(/\)\s*\{\s*footerRow\s*\}/);
    // Exactly once: a second, unguarded `footerRow` beside the guarded one
    // would satisfy the match above and still draw the empty row.
    expect(body.match(/\bfooterRow\b/g)).toHaveLength(1);
  });

  it("the check is asked about all four inputs the footer can draw from", () => {
    // A guard that only consulted `reason` would drop the live "Opened X/Y"
    // strip on any live card the backend gave no reason — a real regression
    // wearing the shape of a fix.
    const body = footerBody();
    expect(body).toMatch(/reason: reason/);
    expect(body).toMatch(/isLive: isLive/);
    expect(body).toMatch(/awayOpening: event\.openingOdds\?\.awayProbability/);
    expect(body).toMatch(/homeOpening: event\.openingOdds\?\.homeProbability/);
  });

  it("the helper still mirrors the row it is standing in for", () => {
    // `hasContent` earns its place only while it agrees with `footerRow`'s two
    // branches. If the row grows a third thing to draw, this fails and the
    // helper has to learn about it — rather than the gap coming back silently
    // on whatever rows the new branch covers.
    const source = code();
    const start = source.indexOf("static func hasContent(");
    expect(start).toBeGreaterThan(-1);
    const helper = source.slice(start, source.indexOf("\n    }", start));
    expect(helper).toMatch(/if let reason, !reason\.isEmpty \{ return true \}/);
    // #5363 — the row this mirrors grew a second branch: on a draw-priced
    // sport `footerRow` draws a NAMED single-sided caption ("Opened Boca 68%"),
    // so HOME alone is content there and the gate has to agree. Both arms are
    // pinned, in both directions: drop the guard and a dead card draws a
    // footer, drop the rule and a live soccer card hides one it draws.
    expect(helper).toMatch(
      /guard isLive, homeOpening != nil else \{ return false \}/
    );
    expect(helper).toMatch(
      /return awayOpening != nil \|\| DrawPricedWinner\.sportPricesADraw\(sport\)/
    );
  });

  it("the slice is the right one, and the mutant is still detectable inside it", () => {
    // A silently-empty slice makes every assertion above vacuous — the failure
    // mode that made both of native/071's first-draft guards useless.
    const body = footerBody();
    expect(body.length).toBeGreaterThan(80);
    expect(body).toMatch(/@ViewBuilder|footerRow/);

    const mutated = body.replace(
      /if EventCardFooter\.hasContent\([\s\S]*?\)\s*\{\s*footerRow\s*\}/,
      "footerRow"
    );
    expect(mutated).not.toEqual(body);
    expect(mutated).not.toMatch(/if EventCardFooter\.hasContent\(/);
  });
});
