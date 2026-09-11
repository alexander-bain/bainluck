/**
 * #5197 — a typeahead row's distinguishing words must reach the reader at 390px.
 *
 * ## What shipped broken
 *
 * `yankee` at 390px returned five consecutive rows whose titles rendered
 * character-for-character identical:
 *
 *     New York Mets vs. New York Yank…    Draw 56% · New York Yankees 23%
 *     New York Mets vs. New York Yank…    Draw 56% · New York Yankees 23%
 *
 * The real titles are `… - 7th Inning Winner`, `- 3rd`, `- 4th`, `- 2nd`. The
 * shared matchup is 36 characters and the row holds about 30, so `truncate`
 * (`white-space: nowrap` + ellipsis) cut off precisely the words that tell the
 * rows apart. Two of them were identical down to the subtitle, so nothing on
 * the screen distinguished them at all.
 *
 * ## Why this guard reads the SOURCE
 *
 * Inherited whole from #5161, whose lesson this is: `textContent` is the
 * complete string at every width, because this is a CSS clip and not missing
 * data — a rail that reads text cannot see a `text-overflow: ellipsis`, and
 * jsdom does not lay out text, so a render test cannot see it either. The
 * property that is actually true here — "this title is allowed to wrap" — is a
 * property of the classes, so the classes are what we assert.
 *
 * **These assertions are a proxy and are not the proof.** The proof is
 * `artifacts/ux-1193/AFTER-5197-yankee-390-local.png`. ux/1192 shipped a fix
 * for #5161 that passed nine class-name assertions and rendered one hard-clipped
 * line; only the picture said so. Keep these, do not trust them alone.
 *
 * ## Why wrap, and why NOT drop the matchup
 *
 * #4866 is the same defect on the event page, and there the answer was to drop
 * the matchup, because the hero one section up already stated it. A dropdown
 * has no page context: the matchup is how a reader knows these rows belong to
 * the game they typed for, so dropping it here would be a different bug.
 *
 * Shortening the label client-side was rejected on #5161's grounds — the label
 * is authored server-side and a responsive re-wording is the client forming a
 * second opinion about what is being asked. If a short form is ever wanted it
 * gets authored beside the long one as `label_short`.
 *
 * The clamp is TWO lines, not unbounded: a row can grow by exactly one line, so
 * the dropdown's height stays bounded by its row count.
 */
import { readFileSync } from "fs";
import { join } from "path";

const COMPONENTS = join(__dirname, "..", "..", "components");
const SURFACES = [
  ["SearchBar.tsx", "desktop dropdown"],
  ["MobileSearchOverlay.tsx", "phone dropdown"],
] as const;

function source(file: string): string {
  return readFileSync(join(COMPONENTS, file), "utf8");
}

/**
 * The `className` of the element carrying `data-testid="search-suggestion-title"`.
 *
 * Null when the title is not found at all, and every caller asserts non-null
 * FIRST — without that, "the title does not carry `truncate`" would pass with
 * the title element deleted, which is the vacuous-guard failure where removing
 * the feature turns the test green.
 */
function titleClasses(file: string): string | null {
  const m = source(file).match(
    /className="([^"]*)"\s*data-testid="search-suggestion-title"/,
  );
  return m ? m[1] : null;
}

describe("#5197 typeahead titles are not clipped to one identical line", () => {
  test.each(SURFACES)("%s still renders a suggestion title at all", (file) => {
    expect(titleClasses(file)).not.toBeNull();
  });

  test.each(SURFACES)("%s title still renders the display text", (file) => {
    // Pins the anchor to the real title element rather than any div that
    // happens to carry the testid.
    expect(source(file)).toMatch(
      /data-testid="search-suggestion-title">\s*\{suggestionDisplayText\(/,
    );
  });

  // The defect itself. `truncate` is nowrap + ellipsis: one line, always.
  test.each(SURFACES)("%s title is not clipped to a single line", (file) => {
    const classes = titleClasses(file);
    expect(classes).not.toBeNull();
    expect(classes).not.toMatch(/\btruncate\b/);
    expect(classes).not.toMatch(/\bwhitespace-nowrap\b/);
    expect(classes).not.toMatch(/\bline-clamp-1\b/);
  });

  // Wrapping without a bound would let one long title push the rest of the
  // dropdown off the screen. Two lines is the ship.
  test.each(SURFACES)("%s title is bounded at two lines", (file) => {
    expect(titleClasses(file)).toMatch(/\bline-clamp-2\b/);
  });

  // The row must still be able to shrink inside its flex parent; without
  // `min-w-0` a flex child refuses to shrink below its content width and the
  // clamp never engages, which is a layout the classes on the title alone
  // cannot reveal.
  //
  // Asserted STRUCTURALLY, not by byte distance. The first version of this
  // test looked back a fixed 400 characters and was broken by the explanatory
  // comment added directly above the title in one of the two files — a guard
  // whose truth depends on how much prose sits next to the code is measuring
  // the prose.
  test.each(SURFACES)("%s title is a direct child of a min-w-0 column", (file) => {
    const src = source(file);
    const at = src.indexOf('data-testid="search-suggestion-title"');
    expect(at).toBeGreaterThan(-1);
    const before = src.slice(0, at);
    const col = before.lastIndexOf("min-w-0");
    const titleTag = before.lastIndexOf("<div");
    expect(col).toBeGreaterThan(-1);
    expect(titleTag).toBeGreaterThan(col);
    // Nothing may open BETWEEN that column and the title's own tag, or the
    // title is some other element's child and the column proves nothing.
    expect(before.slice(col, titleTag)).not.toMatch(/<div/);
  });

  // Both dropdowns are one surface to a reader (notice 35). If one is fixed
  // and the other is not, a phone and a laptop disagree about the same query.
  test("both dropdowns clamp the title the same way", () => {
    const [a, b] = SURFACES.map(([f]) => titleClasses(f));
    const clamp = (c: string | null) => (c ?? "").match(/\bline-clamp-\d\b/)?.[0];
    expect(clamp(a)).toBeDefined();
    expect(clamp(a)).toBe(clamp(b));
  });
});
