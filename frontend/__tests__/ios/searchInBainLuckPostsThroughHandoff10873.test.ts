/**
 * #10873 / #12315 — `SearchInBainLuckIntent10873` declares in-app search
 * (`ShowInAppSearchResultsIntent` + `@AppIntent(schema: .system.search)`) and
 * posts its destination through `IntentRouteHandoff10873.shared`, so any open
 * sheet or full-screen chart is dismissed before switching to My Stuff or
 * Search (#12478).
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";

const SEARCH_INTENT = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Intents/SearchInBainLuck10873.swift"
);
const SHORTCUTS = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Intents/BainLuckIntents10873.swift"
);

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
}

const d = existsSync(SEARCH_INTENT) && existsSync(SHORTCUTS) ? describe : describe.skip;

d("SearchInBainLuckIntent10873 routes through IntentRouteHandoff10873 (#10873)", () => {
  const searchSource = stripComments(readFileSync(SEARCH_INTENT, "utf8"));
  const shortcutsSource = stripComments(readFileSync(SHORTCUTS, "utf8"));

  it("declares ShowInAppSearchResultsIntent with the system search schema and posts via IntentRouteHandoff10873", () => {
    expect(searchSource).toContain("@AppIntent(schema: .system.search)");
    expect(searchSource).toContain("ShowInAppSearchResultsIntent");
    expect(searchSource).toContain("StringSearchCriteria");
    expect(searchSource).toContain("IntentRouteHandoff10873.shared.post(");
  });

  it("registers Search Bain Luck and non-search-shaped My Stuff phrases in BainLuckShortcuts10873", () => {
    expect(shortcutsSource).toContain("SearchInBainLuckIntent10873()");
    expect(shortcutsSource).toContain("Search \\(.applicationName)");
    expect(shortcutsSource).toContain("Go to My Stuff in \\(.applicationName)");
    expect(shortcutsSource).toContain("\\(.applicationName) My Stuff");
  });
});
