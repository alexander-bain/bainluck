// Shared stale-response / cancellation guard for the typeahead search surfaces
// (SearchBar + MobileSearchOverlay). L2-198.
//
// The invariant, in Alex's words: "A result for an older query must never
// overwrite a newer query, a cleared field, or navigation away from search."
//
// Both surfaces debounce keystrokes and fire an async typeahead request. Two
// mechanisms together make stale suppression deterministic:
//
//   1. Cancellation — `begin()` aborts the previous in-flight request's
//      AbortSignal, so a superseded fetch rejects instead of resolving.
//   2. Request-generation ownership — even if a transport ever resolves a
//      superseded/cleared/unmounted request (a mock, a cache hit, a fetch that
//      ignores the signal), `owns()` still returns false for it, so the caller
//      drops the response before publishing. Belt-and-suspenders: query N-1 can
//      never call setState with results after query N has started, and clearing
//      the field, closing the overlay, or unmounting (`cancel()`) drops any
//      response still in flight.
//
// Kept as a tiny framework-free class so it is unit-testable in the repo's
// node test environment (no jsdom/RTL) — same convention as `rankTeamsFirst`.

export class TypeaheadRequestGate {
  private controller: AbortController | null = null;

  /**
   * Start a new request generation. Aborts and supersedes any in-flight
   * request, then returns the fresh controller. Pass `controller.signal` to
   * the fetch and hold the returned controller to check `owns()` afterward.
   */
  begin(): AbortController {
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    return controller;
  }

  /**
   * True only for the request that is still the current generation. A caller
   * MUST check this after awaiting and before publishing results, so a
   * superseded/cleared/cancelled request cannot overwrite fresher state.
   */
  owns(controller: AbortController): boolean {
    return this.controller === controller;
  }

  /**
   * Abort the in-flight request and go idle — for a cleared/short field, an
   * overlay close, an unmount, or a committed navigation. After this, no prior
   * request `owns()` the gate, so a late response is dropped.
   */
  cancel(): void {
    this.controller?.abort();
    this.controller = null;
  }
}
