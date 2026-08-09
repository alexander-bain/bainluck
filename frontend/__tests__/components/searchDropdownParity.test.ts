/**
 * #1620 — the anti-drift guard for the two search dropdowns.
 *
 * ## The class of bug this catches
 *
 * `SearchBar` (desktop, mounted in a `hidden md:block` container) and
 * `MobileSearchOverlay` (phone, mounted in a `md:hidden` one) render the SAME
 * typeahead payload on mutually exclusive viewports. Their row JSX used to be
 * duplicated, so an improvement written into one silently skipped the other.
 *
 * That is exactly what happened to #993 Slice A — "lead with the answer". It
 * shipped to desktop, and phones never got it. Nobody noticed, because no test
 * rendered either dropdown and nothing tied the two implementations together.
 *
 * The fix moved the logic into `lib/searchSuggestionDisplay.ts`. This file makes
 * that stick: a future edit that re-implements the row inside a component reds
 * here instead of quietly stranding the other surface for months.
 *
 * Source inspection is the right instrument for this specific invariant —
 * "these two components share an implementation" is a property of the source,
 * not of any single rendered output, so no amount of render-testing one
 * component can prove it. Same reasoning as `ciTypecheckGate.test.ts`.
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

describe("both search dropdowns share one row implementation", () => {
  test.each(SURFACES)("%s imports the shared module", (file) => {
    expect(source(file)).toMatch(/from\s+"@\/lib\/searchSuggestionDisplay"/);
  });

  test.each(SURFACES)("%s renders its title through suggestionDisplayText", (file) => {
    expect(source(file)).toMatch(/suggestionDisplayText\(/);
  });

  test.each(SURFACES)("%s renders its subtitle through suggestionSubtitle", (file) => {
    expect(source(file)).toMatch(/suggestionSubtitle\(/);
  });

  test.each(SURFACES)("%s renders its type chip through suggestionTypeLabel", (file) => {
    expect(source(file)).toMatch(/suggestionTypeLabel\(/);
  });

  // The drift always starts as a local copy of a helper.
  test.each(SURFACES)("%s does not re-declare the shared helpers locally", (file) => {
    const src = source(file);
    expect(src).not.toMatch(/function\s+formatFuturesName\b/);
    expect(src).not.toMatch(/function\s+formatEventTime\b/);
  });

  // A hand-rolled `top_outcomes` reader in a component is the #993 drift itself.
  test.each(SURFACES)("%s does not read top_outcomes directly", (file) => {
    expect(source(file)).not.toMatch(/\.top_outcomes\b/);
  });

  // The metric drifted the same way the UI did: only desktop counted, so
  // `answer_visible_typeahead` described the half of the user base that already
  // had the feature. Both surfaces must report, and report distinguishably.
  test.each(SURFACES)("%s reports answer exposure through the shared counter", (file) => {
    const src = source(file);
    expect(src).toMatch(/countAnswersShown\(/);
    expect(src).toMatch(/answer_visible_typeahead/);
  });

  test("the two surfaces tag their analytics distinguishably", () => {
    expect(source("SearchBar.tsx")).toMatch(/surface:\s*"desktop"/);
    expect(source("MobileSearchOverlay.tsx")).toMatch(/surface:\s*"mobile"/);
  });

  test("the phone dropdown can render the answer at all", () => {
    // The specific regression: MobileSearchOverlay used to have only the
    // `market_type_label` fallback, so it was permanently running the desktop
    // code's `else` branch. Both branches must now be reachable from its JSX.
    const src = source("MobileSearchOverlay.tsx");
    expect(src).toMatch(/futures-answer/);
    expect(src).toMatch(/futures-label/);
  });
});
