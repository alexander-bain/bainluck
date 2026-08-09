// UX-P031 (#1599) — the concept shell's terminal-state decision.
//
// The bug was that "Event not found" became UNREACHABLE: a concept URL whose
// event 404s sat on "Loading event…" indefinitely (browser-audit runs
// 30864618239 and 31323268137, five days apart, both viewports, still spinning
// at the 45s capture). So these tests are reachability tests first — for every
// state the shell can be in, does it terminate?
//
// Gotcha #43: both directions. The flood gets bounded (a dead key terminates)
// AND the adjacent surface stays populated (a slow-but-successful load is never
// cut off, which is the L2-175 Item 2d regression this fix must not re-open).

import {
  CONCEPT_LOADING_CEILING_MS,
  conceptRenderState,
  isDeadKeyError,
  type ConceptRenderInput,
} from "../../lib/conceptLoadingState";

/** A settled, idle SWR state with nothing wrong. Override per case. */
function state(partial: Partial<ConceptRenderInput> = {}): ConceptRenderInput {
  return {
    hasData: false,
    error: null,
    isLoading: false,
    isValidating: false,
    retriesExhausted: false,
    ceilingReached: false,
    ...partial,
  };
}

function apiError(status: number): Error & { status: number } {
  const e = new Error(`API error: ${status}`) as Error & { status: number };
  e.status = status;
  return e;
}

describe("isDeadKeyError", () => {
  it("treats a 404 as definitive", () => {
    expect(isDeadKeyError(apiError(404))).toBe(true);
  });

  it("does NOT treat retryable failures as definitive", () => {
    // A 5xx or a timeout means "ask again". Only a 404 means "stop asking" —
    // widening this would turn a transient backend blip into a permanent
    // "Event not found" on a page that exists.
    expect(isDeadKeyError(apiError(500))).toBe(false);
    expect(isDeadKeyError(apiError(502))).toBe(false);
    expect(isDeadKeyError(apiError(429))).toBe(false);
    expect(isDeadKeyError(new Error("Request timeout: /api/event/x"))).toBe(false);
  });

  it("never throws on a non-object or absent error", () => {
    expect(isDeadKeyError(null)).toBe(false);
    expect(isDeadKeyError(undefined)).toBe(false);
    expect(isDeadKeyError("404")).toBe(false);
    expect(isDeadKeyError(404)).toBe(false);
    expect(isDeadKeyError({})).toBe(false);
  });
});

describe("conceptRenderState — the reported defect (#1599)", () => {
  it("terminates IMMEDIATELY on a 404, without waiting out any retry ladder", () => {
    // The audited case: /event/f1/no-live-specimen. The backend answered
    // definitively; there is nothing a retry can change.
    expect(
      conceptRenderState(state({ error: apiError(404), isValidating: true })),
    ).toBe("not-found");
  });

  it("terminates on the ceiling even when onErrorRetry NEVER fires", () => {
    // THE regression test. This is the exact state the shell was stuck in:
    // an error is present, SWR skipped `onErrorRetry` (deduped / double-mounted
    // request), so `retriesExhausted` is false and always will be. Before this
    // fix that combination rendered "loading" forever.
    const stuck = state({
      error: apiError(500),
      isValidating: true,
      retriesExhausted: false,
    });
    expect(conceptRenderState(stuck)).toBe("loading");
    expect(conceptRenderState({ ...stuck, ceilingReached: true })).toBe("not-found");
  });

  it("terminates when the retry ladder does exhaust normally", () => {
    expect(
      conceptRenderState(state({ error: apiError(500), retriesExhausted: true })),
    ).toBe("not-found");
  });

  it("has no error state from which the terminal is unreachable", () => {
    // Exhaustive reachability sweep: for every combination of the in-flight
    // flags, an errored load must reach "not-found" once the ceiling fires.
    // A single surviving "loading" here is the bug coming back.
    for (const isLoading of [false, true]) {
      for (const isValidating of [false, true]) {
        for (const retriesExhausted of [false, true]) {
          expect(
            conceptRenderState(
              state({
                error: apiError(503),
                isLoading,
                isValidating,
                retriesExhausted,
                ceilingReached: true,
              }),
            ),
          ).toBe("not-found");
        }
      }
    }
  });
});

describe("conceptRenderState — L2-175 Item 2d must NOT regress (the other direction)", () => {
  it("keeps the spinner up for a slow load that has not errored", () => {
    // #249's cold-backend half. No error means nothing has gone wrong yet, so
    // we wait — flashing "Event not found" in front of a load that is about to
    // succeed is the regression L2-175 was written to prevent.
    expect(conceptRenderState(state({ isLoading: true }))).toBe("loading");
    expect(conceptRenderState(state({ isValidating: true }))).toBe("loading");
  });

  it("does NOT let the ceiling cut off a slow load that has not errored", () => {
    // The asymmetry is deliberate and load-bearing: the ceiling releases the
    // ERROR branch only. A request still honestly in flight outlives it.
    expect(
      conceptRenderState(state({ isLoading: true, ceilingReached: true })),
    ).toBe("loading");
    expect(
      conceptRenderState(state({ isValidating: true, ceilingReached: true })),
    ).toBe("loading");
  });

  it("keeps the spinner up during the retry window, before any escape fires", () => {
    expect(
      conceptRenderState(state({ error: apiError(500), isValidating: true })),
    ).toBe("loading");
  });
});

describe("conceptRenderState — data always wins", () => {
  it("renders the event once data exists", () => {
    expect(conceptRenderState(state({ hasData: true }))).toBe("ready");
  });

  it("keeps rendering stale data when a background revalidate errors", () => {
    // A refresh failing must never blank out a page that is already showing an
    // event — including on a 404, and including past the ceiling.
    expect(
      conceptRenderState(
        state({
          hasData: true,
          error: apiError(404),
          isValidating: true,
          retriesExhausted: true,
          ceilingReached: true,
        }),
      ),
    ).toBe("ready");
  });
});

describe("conceptRenderState — settled with neither data nor error", () => {
  it("shows the honest empty terminal rather than spinning", () => {
    // Nothing in flight, nothing to wait for, nothing to show.
    expect(conceptRenderState(state())).toBe("not-found");
  });
});

describe("CONCEPT_LOADING_CEILING_MS", () => {
  it("is finite, and below the browser-audit journey's 45s capture", () => {
    // If the ceiling ever exceeds the rail's bound, the rail can only ever
    // observe the spinner and this defect becomes unverifiable from production.
    expect(Number.isFinite(CONCEPT_LOADING_CEILING_MS)).toBe(true);
    expect(CONCEPT_LOADING_CEILING_MS).toBeLessThan(45_000);
  });

  it("leaves room for apiFetch's 20s timeout plus SWR's 6s of backoff", () => {
    expect(CONCEPT_LOADING_CEILING_MS).toBeGreaterThanOrEqual(26_000);
  });
});
