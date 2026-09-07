// #3702 — ONE LINK, ONE ARROW.
//
// What the reader saw, `/events/15304939` and `/events/15306225`, production,
// 390px, reconfirmed by ux/1116 on `f1b36c81` and again by ux/1118 this
// session:
//
//     ‹ US Open 2026   ‹ ← Back to events
//
// Three arrows across two links, and one of the links carries two of them.
//
// ── THE MECHANISM ───────────────────────────────────────────────────────────
//
// The generic back link in `app/events/[id]/page.tsx` drew BOTH an inline
// `<svg>` chevron (`d="M15 19l-7-7 7-7"`) AND a literal `←` baked into the
// label text. On its own that was a small rendering glitch that had been there
// a long time. #2448 then landed `TournamentBackLink` immediately to its left
// — same component row, same chevron path, no literal arrow — and the doubling
// stopped being subtle, because the reader now has a correct link sitting one
// gap away from the incorrect one to compare it against.
//
// The fix drops the glyph, not the chevron: the `<svg>` is the shared
// affordance both links use, and it is what makes them look like one control.
//
// ── WHY THE GUARD IS A SOURCE SCAN ──────────────────────────────────────────
//
// The defect is a literal character inside JSX, not a value any function
// returns, so there is nothing to call. Rendering the page component to reach
// it would mean standing up SWR, the analytics hooks and a full event payload
// to assert on one string. The scan states the rule directly and cannot pass
// for the wrong reason, because the positive control below proves the same
// predicate DOES fire on the text that shipped.
//
// The rule is stated over BOTH links in the header row rather than just the
// one that was wrong, because "the two back links agree" is the property the
// reader actually perceives — fixing one and letting the other drift back
// reproduces the same defect with the roles swapped.

import { readFileSync } from "fs";
import { join } from "path";

/** The chevron both back links draw. Its presence is half the assertion. */
const CHEVRON_PATH = 'd="M15 19l-7-7 7-7"';

/**
 * Arrow GLYPHS — characters that a reader sees as an arrow. Deliberately not a
 * test for the ASCII `<-`, which appears in prose and comments and would make
 * this guard fire on documentation.
 */
const ARROW_GLYPHS = ["←", "→", "⟵", "⟶", "⬅", "➜"];

const containsArrowGlyph = (text: string): boolean =>
  ARROW_GLYPHS.some((glyph) => text.includes(glyph));

/**
 * The rendered TEXT of a JSX element: everything outside a tag, outside a
 * `{...}` expression and outside a `{/* ... *\/}` comment. That last exclusion
 * is what lets the fix carry a comment explaining itself — a comment is not
 * something the reader sees, and a guard that could not tell the two apart
 * would forbid documenting the rule it enforces.
 */
function renderedText(jsx: string): string {
  return jsx
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, " ") // JSX comments
    .replace(/\{[\s\S]*?\}/g, " ") // expression containers
    .replace(/<[^>]*>/g, " ") // tags
    .replace(/\s+/g, " ")
    .trim();
}

function readSource(relativePath: string): string {
  return readFileSync(join(process.cwd(), relativePath), "utf8");
}

/**
 * The `<Link ...>…</Link>` element whose RENDERED LABEL contains `phrase`.
 *
 * Scans real elements rather than seeking the phrase directly: `page.tsx`
 * mentions "Back to events" in #2448's prose comment above the header, and a
 * naive `indexOf` lands on that comment — which has no `<Link` before it at
 * all. Matching on rendered text also means the guard is anchored to what the
 * reader sees, which is the thing it is asserting about.
 */
function linkContaining(source: string, phrase: string): string {
  const matches: string[] = [];
  for (let at = source.indexOf("<Link"); at !== -1; at = source.indexOf("<Link", at + 1)) {
    const close = source.indexOf("</Link>", at);
    if (close === -1) continue;
    const element = source.slice(at, close + "</Link>".length);
    if (renderedText(element).includes(phrase)) matches.push(element);
  }
  // Exactly one, or the assertions below would be about an arbitrary pick.
  expect(matches).toHaveLength(1);
  return matches[0];
}

describe("#3702: the events back link draws one arrow, not two", () => {
  const page = readSource("app/events/[id]/page.tsx");
  const backLink = linkContaining(page, "Back to events");

  it("still draws the chevron — the fix removed the duplicate, not the affordance", () => {
    expect(backLink).toContain(CHEVRON_PATH);
  });

  it("prints no arrow glyph in the label the reader reads", () => {
    expect(containsArrowGlyph(renderedText(backLink))).toBe(false);
  });

  it("still says where it goes", () => {
    expect(renderedText(backLink)).toContain("Back to events");
  });

  it("POSITIVE CONTROL — the predicate fires on the markup that shipped", () => {
    // The label exactly as it was before this fix. If this ever stops failing
    // the predicate, the two assertions above are vacuous.
    const asShipped = backLink.replace("Back to events", "← Back to events");
    expect(containsArrowGlyph(renderedText(asShipped))).toBe(true);
  });

  it("POSITIVE CONTROL — a comment mentioning ← does NOT trip the guard", () => {
    // Otherwise the fix could not explain itself in the file it fixes.
    const commented = backLink.replace(
      "Back to events",
      "{/* was: ← Back to events */}Back to events",
    );
    expect(containsArrowGlyph(renderedText(commented))).toBe(false);
  });
});

describe("#3702: its sibling in the same header row agrees", () => {
  // #2448's tournament link renders immediately to the left of the one above.
  // The reader sees the pair, so the rule is a property of the pair.
  const extensions = readSource("components/event/TournamentExtensions.tsx");
  const start = extensions.indexOf("export function TournamentBackLink");
  const backLink = extensions.slice(start);

  it("draws the same chevron", () => {
    expect(backLink).toContain(CHEVRON_PATH);
  });

  it("prints no arrow glyph either", () => {
    expect(containsArrowGlyph(renderedText(backLink))).toBe(false);
  });
});
