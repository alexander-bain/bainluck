/**
 * #2239 — the wiring pin. THE ONE THAT MATTERS, and the one most likely to be
 * deleted as ugly, so the reason is written down.
 *
 * The other two guards in this change test a pure function and a leaf component.
 * Both stay green if `app/search/page.tsx` simply never calls them — which is
 * the shape the original bug had: the backend published `degraded`, the contract
 * was correct, documented and unread. A guard that cannot fail when the page
 * drops the module is not guarding the page (gotcha: a plant must hit the
 * render).
 *
 * The render itself cannot be driven here. `SearchContent` fetches in a
 * `useEffect`, and `useEffect` does not run under `renderToStaticMarkup`, so any
 * SSR of the page yields the loading state and can never reach the terminal
 * branch. jsdom is not installed and the npm registry is unreachable from this
 * sandbox, so that is not fixable in this change.
 *
 * So the source is read instead, and only for facts a rename cannot fake: the
 * decision is imported, and it is consulted BEFORE the zero-state is returned.
 * If this file starts failing because the page was legitimately restructured,
 * the fix is to re-point it at the new decision site — not to delete it.
 */

import fs from "node:fs";
import path from "node:path";

const PAGE = path.resolve(__dirname, "../../app/search/page.tsx");
const source = fs.readFileSync(PAGE, "utf8");

describe("app/search/page.tsx consumes the degraded contract", () => {
  it("imports the decision rather than re-deriving it inline", () => {
    expect(source).toMatch(/from\s+["']@\/lib\/searchAnswerState["']/);
  });

  it("renders a degraded state distinct from the zero state", () => {
    expect(source).toContain("SearchDegradedState");
    expect(source).toContain("SearchZeroState");
  });

  it("decides the answer state BEFORE it can return the zero state", () => {
    // Ordering is the whole assertion. A `searchAnswerState` call that happens
    // after the `SearchZeroState` return is dead code, and it would satisfy a
    // naive "does the page mention it" check.
    const decided = source.indexOf("searchAnswerState({");
    const zeroState = source.indexOf("<SearchZeroState");
    expect(decided).toBeGreaterThan(-1);
    expect(zeroState).toBeGreaterThan(-1);
    expect(decided).toBeLessThan(zeroState);
  });

  it("passes the wire field through, not a hardcoded value", () => {
    // `degraded:` must be fed from the response. `degraded: []` or `degraded:
    // undefined` would make the branch permanently unreachable while every other
    // test in this change stayed green.
    expect(source).toMatch(/degraded:\s*results\?\.degraded/);
  });

  it("still models degraded on the response type", () => {
    const types = fs.readFileSync(
      path.resolve(__dirname, "../../lib/types.ts"),
      "utf8",
    );
    const searchResponse = types.slice(
      types.indexOf("export interface SearchResponse"),
    );
    const body = searchResponse.slice(0, searchResponse.indexOf("}"));
    expect(body).toMatch(/degraded\?:/);
  });
});
