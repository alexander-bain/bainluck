// LAT-P142 — the in-category search box that ran a table scan for every letter.
//
// `CategoryBrowser`'s search input fed its value straight into the SWR key, so
// typing "super" issued five requests to `/api/futures/browse`. Measured on
// production 2026-08-30 with EXPLAIN (ANALYZE, BUFFERS), category=politics:
//
//     q='s'     132.8 ms   4,821 shared blocks   (no trigram below 3 chars)
//     q='sup'    16.1 ms      40 shared blocks   (ix_futures_name_trgm)
//
// The two cheapest keystrokes to type are the two most expensive to serve, and
// their results are discarded by the next letter. These are the guards that stop
// that coming back.

import { createSearchDebouncer } from "@/lib/searchDebounce";

const DELAY = 200;

describe("createSearchDebouncer", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("typing 'super' at speed commits ONCE, with the whole word", () => {
    // The ship, stated as a test: five keystrokes, one request, and the request
    // is for the query the person actually meant.
    const commit = jest.fn();
    const d = createSearchDebouncer(DELAY);

    for (const prefix of ["s", "su", "sup", "supe", "super"]) {
      d.schedule(prefix, commit);
      jest.advanceTimersByTime(40); // ~40 ms/char — ordinary typing
    }
    jest.advanceTimersByTime(DELAY);

    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith("super");
  });

  it("NEVER commits the sub-3-character prefixes — the unindexable ones", () => {
    // Stated in the terms the plan uses, so a regression reads as what it costs.
    const committed: string[] = [];
    const d = createSearchDebouncer(DELAY);

    for (const prefix of ["s", "su", "sup", "supe", "super"]) {
      d.schedule(prefix, (v) => committed.push(v));
      jest.advanceTimersByTime(40);
    }
    jest.advanceTimersByTime(DELAY);

    expect(committed).not.toContain("s");
    expect(committed).not.toContain("su");
    expect(committed).toEqual(["super"]);
  });

  it("does not fire early", () => {
    const commit = jest.fn();
    const d = createSearchDebouncer(DELAY);

    d.schedule("politics", commit);
    jest.advanceTimersByTime(DELAY - 1);
    expect(commit).not.toHaveBeenCalled();

    jest.advanceTimersByTime(1);
    expect(commit).toHaveBeenCalledTimes(1);
  });

  it("a slow typist still gets every prefix they PAUSE on", () => {
    // Gotcha #43's shape, and the honest bound on this fix: debouncing removes
    // the queries nobody asked for, not the ones somebody did. Cancelling too
    // eagerly would be a worse bug — a search box that never searches.
    const committed: string[] = [];
    const d = createSearchDebouncer(DELAY);

    d.schedule("us", (v) => committed.push(v));
    jest.advanceTimersByTime(DELAY);
    d.schedule("usa", (v) => committed.push(v));
    jest.advanceTimersByTime(DELAY);

    expect(committed).toEqual(["us", "usa"]);
  });

  it("clearing the box commits the empty query — back to the unfiltered list", () => {
    // The `q: committedQuery || undefined` at the call site turns "" into no
    // filter at all, so this is how a person gets the whole category back.
    const commit = jest.fn();
    const d = createSearchDebouncer(DELAY);

    d.schedule("super", commit);
    jest.advanceTimersByTime(DELAY);
    d.schedule("", commit);
    jest.advanceTimersByTime(DELAY);

    expect(commit).toHaveBeenNthCalledWith(1, "super");
    expect(commit).toHaveBeenNthCalledWith(2, "");
  });

  it("cancel() drops a pending commit — the unmount guard", () => {
    // The effect's cleanup calls this. Without it a commit lands after the
    // component is gone and React warns about a set on an unmounted tree.
    const commit = jest.fn();
    const d = createSearchDebouncer(DELAY);

    d.schedule("super", commit);
    d.cancel();
    jest.advanceTimersByTime(DELAY * 10);

    expect(commit).not.toHaveBeenCalled();
    expect(d.pendingValue).toBeUndefined();
  });

  it("pendingValue reports the value in flight, and clears once it fires", () => {
    const d = createSearchDebouncer(DELAY);
    expect(d.pendingValue).toBeUndefined();

    d.schedule("sup", () => {});
    expect(d.pendingValue).toBe("sup");

    jest.advanceTimersByTime(DELAY);
    expect(d.pendingValue).toBeUndefined();
  });

  it("a later schedule REPLACES an earlier one rather than queueing behind it", () => {
    const commit = jest.fn();
    const d = createSearchDebouncer(DELAY);

    d.schedule("aaa", commit);
    d.schedule("bbb", commit);
    jest.advanceTimersByTime(DELAY * 5);

    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith("bbb");
  });

  it("commit may schedule again from inside its own dispatch", () => {
    // The real call site sets React state inside `commit`, which re-renders and
    // can re-enter the effect. The primitive clears its handle BEFORE dispatch
    // precisely so this re-entrant schedule survives.
    const seen: string[] = [];
    const d = createSearchDebouncer(DELAY);

    d.schedule("first", (v) => {
      seen.push(v);
      if (v === "first") d.schedule("second", (w) => seen.push(w));
    });
    jest.advanceTimersByTime(DELAY);
    expect(seen).toEqual(["first"]);

    jest.advanceTimersByTime(DELAY);
    expect(seen).toEqual(["first", "second"]);
  });

  it("uses the injected timers, not the globals", () => {
    // Timer injection is what makes the above deterministic; if the primitive
    // silently fell back to globals these tests would be measuring nothing.
    // Both spies declare their parameters: `jest.fn()` with a bare arrow infers
    // an EMPTY argument tuple, and `mock.calls[0][1]` below would not typecheck.
    const setTimeoutSpy = jest.fn((_fn: () => void, _ms: number): unknown => 7);
    const clearTimeoutSpy = jest.fn((_handle: never): void => {});
    const d = createSearchDebouncer(DELAY, {
      setTimeout: setTimeoutSpy as never,
      clearTimeout: clearTimeoutSpy as never,
    });

    d.schedule("sup", () => {});
    expect(setTimeoutSpy).toHaveBeenCalledTimes(1);
    expect(setTimeoutSpy.mock.calls[0][1]).toBe(DELAY);

    d.cancel();
    expect(clearTimeoutSpy).toHaveBeenCalledWith(7);
  });
});
