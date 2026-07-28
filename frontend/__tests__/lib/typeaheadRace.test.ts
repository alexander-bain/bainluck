// L2-198 — deterministic stale-response / cancellation guard tests for the
// typeahead search surfaces (SearchBar + MobileSearchOverlay). These exercise
// the exact primitive both components use (lib/typeaheadRace.ts), so the race
// invariants are proven without needing a DOM renderer.
//
// Invariants (Alex): a result for an older query must never overwrite a newer
// query, a cleared field, or navigation away from search.

import { TypeaheadRequestGate } from "../../lib/typeaheadRace";

// A controllable fake transport: a request whose resolution we release by hand,
// so we can force out-of-order completion deterministically (no real timers).
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("TypeaheadRequestGate", () => {
  test("begin() aborts the previously in-flight request's signal", () => {
    const gate = new TypeaheadRequestGate();
    const first = gate.begin();
    expect(first.signal.aborted).toBe(false);
    const second = gate.begin();
    // Starting a newer request cancels the older one.
    expect(first.signal.aborted).toBe(true);
    expect(second.signal.aborted).toBe(false);
  });

  test("owns() is true only for the current generation", () => {
    const gate = new TypeaheadRequestGate();
    const first = gate.begin();
    expect(gate.owns(first)).toBe(true);
    const second = gate.begin();
    // Query N-1 no longer owns the gate once query N has started.
    expect(gate.owns(first)).toBe(false);
    expect(gate.owns(second)).toBe(true);
  });

  test("cancel() aborts and revokes ownership (cleared field / close / unmount)", () => {
    const gate = new TypeaheadRequestGate();
    const req = gate.begin();
    gate.cancel();
    expect(req.signal.aborted).toBe(true);
    // After a clear/close/unmount, the in-flight request may not publish.
    expect(gate.owns(req)).toBe(false);
  });

  test("cancel() on an idle gate is a no-op", () => {
    const gate = new TypeaheadRequestGate();
    expect(() => gate.cancel()).not.toThrow();
    const req = gate.begin();
    gate.cancel();
    gate.cancel(); // second cancel must not throw or re-own anything
    expect(gate.owns(req)).toBe(false);
  });
});

describe("stale-response suppression (out-of-order completion)", () => {
  // Models the components' fetchSuggestions ownership check: publish only if the
  // request still owns the gate after awaiting the transport.
  async function fetchAndMaybePublish(
    gate: TypeaheadRequestGate,
    transport: Promise<string>,
    publish: (result: string) => void,
  ): Promise<void> {
    const controller = gate.begin();
    const result = await transport;
    if (!gate.owns(controller)) return; // superseded / cleared / unmounted
    publish(result);
  }

  test("query N-1 cannot replace query N even when it resolves LAST", async () => {
    const gate = new TypeaheadRequestGate();
    const published: string[] = [];

    const older = deferred<string>();
    const newer = deferred<string>();

    // Start "raider" then "raiders" (newer supersedes older).
    const p1 = fetchAndMaybePublish(gate, older.promise, (r) => published.push(r));
    const p2 = fetchAndMaybePublish(gate, newer.promise, (r) => published.push(r));

    // Newer resolves first (correct result lands)...
    newer.resolve("raiders-results");
    // ...then the OLDER, slower request resolves last — the classic race.
    older.resolve("raider-results");

    await Promise.all([p1, p2]);

    // Only the newest query's result was published; the stale one was dropped.
    expect(published).toEqual(["raiders-results"]);
  });

  test("clearing the field drops an in-flight response (no repopulation)", async () => {
    const gate = new TypeaheadRequestGate();
    const published: string[] = [];

    const inFlight = deferred<string>();
    const p = fetchAndMaybePublish(gate, inFlight.promise, (r) => published.push(r));

    // User clears the field before the response arrives (components call cancel()).
    gate.cancel();
    inFlight.resolve("stale-results");

    await p;
    expect(published).toEqual([]); // cleared field stays empty
  });

  test("unmount / navigation drops a late response", async () => {
    const gate = new TypeaheadRequestGate();
    const published: string[] = [];

    const inFlight = deferred<string>();
    const p = fetchAndMaybePublish(gate, inFlight.promise, (r) => published.push(r));

    // Surface unmounts / navigates away → cleanup calls cancel().
    gate.cancel();
    inFlight.resolve("late-results");

    await p;
    expect(published).toEqual([]); // no setState on a dead surface
  });

  test("the newest query still publishes normally after churn", async () => {
    const gate = new TypeaheadRequestGate();
    const published: string[] = [];

    const a = deferred<string>();
    const b = deferred<string>();
    const c = deferred<string>();

    const pa = fetchAndMaybePublish(gate, a.promise, (r) => published.push(r));
    const pb = fetchAndMaybePublish(gate, b.promise, (r) => published.push(r));
    const pc = fetchAndMaybePublish(gate, c.promise, (r) => published.push(r));

    // All resolve out of order; only the last-started (c) owns the gate.
    b.resolve("b");
    a.resolve("a");
    c.resolve("c");

    await Promise.all([pa, pb, pc]);
    expect(published).toEqual(["c"]);
  });
});
