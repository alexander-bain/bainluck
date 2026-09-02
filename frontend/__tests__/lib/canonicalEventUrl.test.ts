/**
 * Q050 — a duplicate event url corrects itself.
 *
 * THE SPECIMEN, production 2026-09-02: `/events/15300759` (Vallejo v Monfils,
 * "scheduled 2026-08-30") is a `kalshi_ticker` duplicate of `/events/15293804`,
 * which is completed 1-3 and which ESPN had final at 2026-09-01 23:05Z. The API
 * now answers the first url with the second row; this is what turns that into a
 * page whose CHART and MARKETS are also the real match's, because every sibling
 * fetch is keyed on the route's id.
 *
 * Layer 1 of the two-layer pattern (the primitive). Layer 2 — the source-shape
 * guard that the page actually calls this and hands it to `router.replace` — is
 * `__tests__/components/eventPageCorrectsADuplicateUrl.test.ts`. Neither is
 * sufficient alone: this file stays green if the page stops calling it.
 */
import { canonicalEventHref } from "@/lib/canonicalEventUrl";

const GHOST = 15300759;
const CANONICAL = 15293804;

describe("canonicalEventHref", () => {
  it("sends the reader to the row the api served", () => {
    expect(canonicalEventHref(GHOST, CANONICAL, "")).toBe(
      `/events/${CANONICAL}`,
    );
  });

  it("keeps the query string so a shared link keeps its attribution", () => {
    expect(
      canonicalEventHref(GHOST, CANONICAL, "utm_source=share&utm_medium=ios"),
    ).toBe(`/events/${CANONICAL}?utm_source=share&utm_medium=ios`);
  });

  it("does not move a url that was already right", () => {
    // The important half. Returning the current href here would hand
    // `router.replace` the page it is already on, every render — a redirect
    // loop, on every event page on the site, not just the 505 duplicates.
    expect(canonicalEventHref(CANONICAL, CANONICAL, "")).toBeNull();
  });

  it("waits for a payload rather than guessing", () => {
    expect(canonicalEventHref(GHOST, undefined, "")).toBeNull();
    expect(canonicalEventHref(GHOST, null, "")).toBeNull();
    expect(canonicalEventHref(GHOST, 0, "")).toBeNull();
  });

  it("leaves an unparseable route id to the page's own error handling", () => {
    expect(canonicalEventHref(Number.NaN, CANONICAL, "")).toBeNull();
  });

  it("omits the `?` when there is no query", () => {
    expect(canonicalEventHref(GHOST, CANONICAL, null)).toBe(
      `/events/${CANONICAL}`,
    );
    expect(canonicalEventHref(GHOST, CANONICAL)).toBe(`/events/${CANONICAL}`);
  });
});
