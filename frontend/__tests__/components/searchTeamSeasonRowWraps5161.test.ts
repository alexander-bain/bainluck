/**
 * #5161 — the team row's SECOND season answer must reach the reader at 390px.
 *
 * ## What shipped broken
 *
 * T2-1 (#5058) gave the team suggestion both season answers on one line:
 *
 *     10+ regular-season wins 43% · Make Playoffs 49%
 *
 * The line carried Tailwind's `truncate` (`white-space: nowrap` +
 * `text-overflow: ellipsis`). At 430px and up it fits. At **390px — the most
 * common iPhone width — it clips to `… · Make Playoffs …` and the second
 * number never arrives.** The row exists to answer both season questions
 * without being opened; at the width most people hold, it answered one and a
 * half.
 *
 * ## Why no existing rail caught it
 *
 * `textContent` is the COMPLETE string at 390, 430 and 768 alike — this is a
 * CSS single-line clip, not missing data. lane1/243 confirmed it: their
 * after-read rig, the screenshot rig's own DOM dump and every jest assertion
 * read `textContent` and all passed. **A rail that reads text cannot see a
 * `text-overflow: ellipsis`.** Only the picture showed it.
 *
 * That is why this guard reads the SOURCE rather than a rendered string. jsdom
 * does not lay out text, so a render test cannot see the clip either; the
 * property that is actually true here — "this line is allowed to wrap" — is a
 * property of the classes, so the classes are what we assert.
 *
 * ## The fix, and the two-line bound
 *
 * The container drops `truncate` (so it wraps) and each ANSWER is
 * `whitespace-nowrap`, so a break can only ever fall BETWEEN answers, never
 * inside one — the number can never be orphaned from its label:
 *
 *     10+ regular-season wins 43% ·
 *     Make Playoffs 49%
 *
 * The load-bearing detail is WHERE the separator lives: outside the nowrap
 * span, because its spaces are the only break opportunity in the line. Put it
 * inside and the row silently stays on one line. See the last test.
 *
 * With N nowrap answers the row is at most N lines, so the height is bounded
 * by `TEAM_SEASON_ANSWER_LIMIT` and by nothing in the CSS. That is a real
 * coupling between two constants, and the last test here asserts it: raising
 * the answer limit silently makes every team row taller in a 7-row dropdown,
 * which is precisely the cost that made wrapping look expensive in the first
 * place. Raise it deliberately or not at all.
 *
 * Wrapping was chosen over shortening the label — `10+ wins 43%` — on the
 * grounds that that is not a shortening, it is a different question: the venue
 * prices REGULAR-SEASON wins, and "10+ wins" reads as including the
 * postseason. The label is authored server-side so the client does not form a
 * second opinion about what is being asked; a responsive re-wording would be
 * exactly that second opinion.
 */
import { readFileSync } from "fs";
import { join } from "path";

import { TEAM_SEASON_ANSWER_LIMIT } from "../../lib/searchSuggestionDisplay";

const COMPONENTS = join(__dirname, "..", "..", "components");
const SURFACES = [
  ["SearchBar.tsx", "desktop dropdown"],
  ["MobileSearchOverlay.tsx", "phone dropdown"],
] as const;

function source(file: string): string {
  return readFileSync(join(COMPONENTS, file), "utf8");
}

/**
 * The `className` of the element carrying `data-testid="search-team-season"`.
 *
 * Returns null when the row is not found at all, and every caller asserts
 * non-null FIRST. Without that, "the season line does not carry `truncate`"
 * would pass with the season line deleted — the vacuous-guard failure, where
 * removing the feature turns the test green.
 */
function seasonRowClasses(file: string): string | null {
  const m = source(file).match(
    /className="([^"]*)"\s*data-testid="search-team-season"/
  );
  return m ? m[1] : null;
}

/** The JSX of the season row's `.map(...)` body, or null if absent. */
function answerBlock(file: string): string | null {
  const src = source(file);
  const at = src.indexOf('data-testid="search-team-season"');
  if (at === -1) return null;
  const end = src.indexOf("))}", at);
  return end === -1 ? null : src.slice(at, end);
}

describe("#5161 the team row's second season answer is not clipped at 390px", () => {
  test.each(SURFACES)("%s still renders a season row at all", (file) => {
    expect(seasonRowClasses(file)).not.toBeNull();
    expect(answerBlock(file)).not.toBeNull();
  });

  // The defect itself. `truncate` is nowrap + ellipsis: one line, always.
  test.each(SURFACES)("%s season row is not clipped to a single line", (file) => {
    const classes = seasonRowClasses(file);
    expect(classes).not.toBeNull();
    expect(classes).not.toMatch(/\btruncate\b/);
    expect(classes).not.toMatch(/\bwhitespace-nowrap\b/);
  });

  // A too-long single answer clips at the row edge instead of spilling over
  // the type chip to its right.
  test.each(SURFACES)("%s season row contains its own overflow", (file) => {
    expect(seasonRowClasses(file)).toMatch(/\boverflow-hidden\b/);
  });

  // The break falls between answers, never inside one, so a probability can
  // never be orphaned from the label naming the question it answers.
  test.each(SURFACES)("%s keeps each answer on one line", (file) => {
    expect(answerBlock(file)).toMatch(/\bwhitespace-nowrap\b/);
  });

  /**
   * THE ONE THAT ACTUALLY CATCHES IT — learned the hard way.
   *
   * The first attempt at this fix dropped `truncate`, added `overflow-hidden`
   * and marked each answer `whitespace-nowrap`. Every assertion above passed.
   * **The rendered line was still one line, and now hard-clipped mid-number
   * (`Make Playoffs 4`) with no ellipsis to admit it** — strictly worse than
   * the bug, because a partial `4` reads as a value.
   *
   * The reason: the ` · ` separator was rendered INSIDE the nowrap span. Its
   * spaces are the only break opportunity in the whole line, and nowrap made
   * them non-breaking too, so the browser had nowhere to wrap.
   *
   * So the property that matters is not "something is nowrap" — it is **the
   * separator is outside it**. In source order that is exactly: the separator
   * appears BEFORE the `whitespace-nowrap` span it must not be inside.
   *
   * A class-level assertion is not a layout assertion, and jsdom cannot lay
   * text out. The screenshot is the real instrument here (see the PR); this
   * test is the cheap proxy that pins the one structural fact the screenshot
   * proved, so the next edit cannot quietly undo it.
   */
  test.each(SURFACES)("%s leaves the separator outside the nowrap span", (file) => {
    const block = answerBlock(file);
    expect(block).not.toBeNull();
    const separator = block!.indexOf("·");
    const nowrap = block!.indexOf("whitespace-nowrap");
    expect(separator).toBeGreaterThanOrEqual(0);
    expect(nowrap).toBeGreaterThanOrEqual(0);
    // Separator first => it sits outside the nowrap span that follows it.
    expect(separator).toBeLessThan(nowrap);
  });

  /**
   * Two constants describe one capability — how tall a team row may get — and
   * they must be read together. The CSS imposes no line cap, so the row's
   * height is exactly `TEAM_SEASON_ANSWER_LIMIT` lines in the worst case.
   */
  test("the row's line budget still matches the answer limit", () => {
    expect(TEAM_SEASON_ANSWER_LIMIT).toBe(2);
  });
});
