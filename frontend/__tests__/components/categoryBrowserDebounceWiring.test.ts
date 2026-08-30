/**
 * LAT-P142 — the debounce has to be WIRED, not merely present.
 *
 * `searchDebounce.test.ts` proves the primitive coalesces. It would stay green
 * if someone put `searchQuery` back into the SWR key and left the debouncer
 * running beside it doing nothing — the exact failure this repo has hit before
 * (a pure-library guard passing while the render dropped the thing it proved).
 *
 * This suite cannot render the component to check: the frontend jest suite runs
 * `testEnvironment: 'node'` with no jsdom and no react-test-renderer available,
 * so an effect-and-timer render is not reachable from CI. It asserts the source
 * instead — the same technique `__tests__/ios/*` uses for the Swift it cannot
 * execute, and for the same stated reason: jest is a deploy gate here.
 */

import { readFileSync } from "fs";
import { join } from "path";

const SOURCE = join(__dirname, "../../components/CategoryBrowser.tsx");
const src = readFileSync(SOURCE, "utf8");

/** The `useSWR(...)` call that fetches a category's markets, key argument only. */
function swrKeyArgument(): string {
  const at = src.indexOf('["futures-browse"');
  expect(at).toBeGreaterThan(-1); // the browse fetch must still exist at all
  return src.slice(at, src.indexOf("]", at) + 1);
}

describe("CategoryBrowser search debounce wiring", () => {
  it("the SWR key reads the COMMITTED query, never the raw input", () => {
    const key = swrKeyArgument();
    expect(key).toContain("committedQuery");
    // The regression in one line: putting the keystroke value back in the key.
    expect(key).not.toContain("searchQuery");
  });

  it("the request's `q` is the committed query too", () => {
    // The key could be right while the fetch still sends the raw value — SWR
    // would then serve one cache entry per keystroke's worth of stale content.
    expect(src).toContain("q: committedQuery || undefined");
    expect(src).not.toContain("q: searchQuery");
  });

  it("the input's onChange only sets local state — it does not fetch", () => {
    // `handleSearch` was the old path: it set the query AND reset paging, so the
    // list flashed skeletons on every letter. Its removal is part of the ship.
    expect(src).toContain("onChange={(e) => setSearchQuery(e.target.value)}");
    expect(src).not.toContain("handleSearch");
  });

  it("the input still shows what was typed, immediately", () => {
    // Debouncing the REQUEST must never debounce the character appearing. If
    // this flips to `committedQuery` the box lags 200 ms behind the keyboard.
    expect(src).toContain("value={searchQuery}");
  });

  it("the debouncer is created from the shared primitive, held across renders", () => {
    expect(src).toContain('from "@/lib/searchDebounce"');
    // In a ref: rebuilding it every render would give each keystroke its own
    // timer and coalesce nothing at all.
    expect(src).toContain("useRef(createSearchDebouncer(SEARCH_DEBOUNCE_MS))");
  });

  it("the pending commit is cancelled when the effect tears down", () => {
    expect(src).toContain("return () => debouncer.cancel()");
  });

  it("the effect short-circuits when the query is already committed", () => {
    // This is the MOUNT guard. Both values start "" — without the early return
    // the timer fires and wipes the first page that had just loaded.
    expect(src).toContain("if (searchQuery === committedQuery) return;");
  });

  it("paging resets inside the commit, not on the keystroke", () => {
    const commitBody = src.slice(
      src.indexOf("debouncer.schedule(searchQuery"),
      src.indexOf("return () => debouncer.cancel()")
    );
    expect(commitBody).toContain("setOffset(0)");
    expect(commitBody).toContain("setAllItems([])");
  });

  it("the shipped delay is the one the guards exercise", () => {
    // Read the constant out of the source rather than trusting a copy of it.
    const declared = /export const SEARCH_DEBOUNCE_MS = (\d+);/.exec(src);
    expect(declared).not.toBeNull();
    expect(Number(declared![1])).toBe(200);
  });
});
