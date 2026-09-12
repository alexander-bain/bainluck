/**
 * #5760 — an iOS Search event row dropped the end of its own title, and the
 * words it dropped were the ones the reader had just typed.
 *
 * Photographed on the iPhone 17 simulator against production, 2026-09-12
 * 2:41pm PT, `bainluck://search?q=red%20sox`
 * (`artifacts-native-020/n137-walk-search-redsox.png`). Three of the four
 * visible Events rows truncated:
 *
 *     Kansas City Royals vs Bos…          MLB  ● LIVE        12%  ⚡66
 *     Worcester Red Sox vs Lehigh Valle…  MILB ⏱ In 53m      49%
 *     Kansas City Royals vs Boston Red…   MLB  ⏱ In 19h 53m  38%
 *     Boston Red Sox vs Texas Rangers     MLB  ⏱ In 3d 2h
 *
 * The title is `"\(awayTeam) vs \(homeTeam)"`, so what tail truncation always
 * eats is the HOME side — and the home side is half of what any team search
 * can match. Row four escaped only because it has no price to draw: the right
 * arm (short name, probability, EI badge) is what takes the width away.
 *
 * The fix is one line: the same `lineLimit(2)` every other title on this screen
 * already had. The after-frame is
 * `artifacts-native-020/n137-after-5760-search-redsox.png` — all three titles
 * read in full.
 *
 * WHY THIS FILE, AND NOT A SWIFT TEST. `lineLimit` is a SwiftUI modifier on an
 * expression inside a `some View` body. XCTest cannot see it, cannot render it,
 * and cannot measure the string against the width it was given — the whole
 * 2,144-test Swift suite stays green with the modifier set back to `1`. A
 * source scan is what can kill that mutant, and CI compiles no Swift at all
 * (#4302), so this is also the only arm of the fix that runs on every push.
 *
 * WHAT IT DOES NOT CLAIM. It does not prove any particular title FITS — that is
 * a raster question, answered by the two frames above and by nothing in this
 * file. It pins the rule: every title on the Search screen gets two lines, so
 * the event row cannot silently go back to being the one that gets one.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const SEARCH_VIEW = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Views/SearchView.swift",
);

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/** The body of one `private func <name>(...) -> some View { ... }`, to the next `private func`. */
function rowBuilder(source: string, name: string): string {
  const start = source.indexOf(`private func ${name}(`);
  if (start === -1) {
    throw new Error(
      `SearchView.swift no longer has a 'private func ${name}('. ` +
        `If the row builder was renamed, re-aim this file at the new name — ` +
        `do not delete the assertion.`,
    );
  }
  const rest = source.slice(start + 1);
  const next = rest.indexOf("private func ");
  return next === -1 ? rest : rest.slice(0, next);
}

/**
 * The modifier chain hanging off a `Text(...)`, i.e. everything from that
 * `Text(` up to the next line that starts a sibling view. Modifiers are the
 * `.foo(...)` lines that follow at a deeper or equal indent; the first line
 * that is not one ends the chain.
 */
function modifierChain(body: string, textLiteral: string): string {
  const at = body.indexOf(textLiteral);
  if (at === -1) {
    throw new Error(
      `could not find ${textLiteral} in the row builder — re-aim, do not delete`,
    );
  }
  const lines = body.slice(at).split("\n");
  const chain: string[] = [lines[0]];
  for (const line of lines.slice(1)) {
    if (/^\s*\./.test(line)) {
      chain.push(line);
      continue;
    }
    if (line.trim() === "") continue;
    break;
  }
  return chain.join("\n");
}

describe("#5760 — Search titles get two lines", () => {
  const source = (() => {
    expect(existsSync(SEARCH_VIEW)).toBe(true);
    return stripComments(readFileSync(SEARCH_VIEW, "utf8"));
  })();

  it("the event row's title is lineLimit(2), so the home side survives", () => {
    const chain = modifierChain(
      rowBuilder(source, "searchEventRow"),
      'Text("\\(event.awayTeam) vs \\(event.homeTeam)")',
    );

    // The mutant this exists for: `.lineLimit(1)`, which is what shipped for
    // months and which the entire Swift suite is blind to.
    expect(chain).not.toMatch(/\.lineLimit\(1\)/);
    // And the mutant where it is simply deleted — an unbounded title is a
    // different row height on every result, which the iPad masonry then has to
    // absorb. Two lines is the rule, not "at least two".
    expect(chain).toMatch(/\.lineLimit\(2\)/);
  });

  it("the title is still away-first, which is why truncation cost the home side", () => {
    // Not a restatement: it is the premise of the paragraph above. If the
    // title is ever flipped to home-first, the reasoning in this file (and its
    // measurement) describes a screen that no longer exists.
    const body = rowBuilder(source, "searchEventRow");
    expect(body).toContain('Text("\\(event.awayTeam) vs \\(event.homeTeam)")');
  });

  it("the futures rows this borrowed the rule from still keep it", () => {
    // The event row was the outlier on this screen, not the rule-setter. If
    // the futures titles are ever cut to one line, "every title on Search gets
    // two" has quietly stopped being true and the event row is alone again.
    const futures = rowBuilder(source, "searchFuturesRow");
    expect(futures).toMatch(/\.lineLimit\(2\)/);
    expect(futures).not.toMatch(/\.lineLimit\(1\)\s*\n\s*\n?\s*HStack/);
  });

  it("exactly one title on the Search screen is still capped at one line, and it is the typeahead", () => {
    // The screen-wide form of the rule, so a NEW row builder cannot
    // reintroduce the defect in a third place. It is written as an EQUALITY
    // rather than an emptiness so that the one deliberate exception has to
    // stay named: `Text(suggestion.text)`, the typeahead dropdown row.
    //
    // WHY THAT ONE IS LEFT ALONE, and it is not because it is fine. Its right
    // arm is the word "Game"/"Team"/"Futures" — about 48pt — where the results
    // row carries a short team name, a probability and an EI badge, so it has
    // roughly 266pt for the same string against the results row's ~250pt. A
    // long title would still clip there. What stopped it being fixed in this
    // ship is that the state is UNPHOTOGRAPHABLE: `LaunchRig` has
    // `launch_route`, `launch_debug_counts`, `launch_expand_sections` and
    // `launch_scroll`, and a route runs the full search — nothing lands the
    // app on an open dropdown, and the rig cannot tap. So the defect could be
    // reasoned about and not measured, and this ship does not change a layout
    // it has never seen. Recorded here rather than left to be rediscovered:
    // whoever can photograph the dropdown decides it, and deletes this test.
    const titleAtOneLine = /Text\((?![^)]*(?:shortPair|abbreviation|record))[^\n]*\)\s*\n\s*\.font\(\.subheadline\)(?:\s*\n\s*\.[^\n]*)*?\s*\n\s*\.lineLimit\(1\)/g;
    const offenders = (source.match(titleAtOneLine) ?? []).map((m) =>
      m.split("\n")[0].trim(),
    );
    expect(offenders).toEqual(["Text(suggestion.text)"]);
  });
});
