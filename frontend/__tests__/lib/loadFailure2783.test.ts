// A THROTTLED PAGE MUST NOT SAY THE EVENT DOES NOT EXIST — #2783.
//
// Measured on production 2026-09-03: a client over the API's 60-requests-per-
// minute limit gets a 429, and the event page rendered
//
//   Event not found
//   Rate limit exceeded: 60/minute
//   Tap to retry
//
// — the heading contradicting the sentence directly beneath it, and both
// contradicting the truth, which is that the event is fine and the request was
// throttled. The same heading was printed for a 500, a timeout and a dropped
// connection. "Not found" is the one thing none of those are.
//
// The distinction is behavioural, not cosmetic: a reader told a thing does not
// exist stops looking for it, and a reader told we could not reach it reloads.
//
// BOTH DIRECTIONS PER GOTCHA #43. Every "it stopped saying not found" case has a
// sibling proving a REAL 404 still says exactly that — a module that never said
// "not found" would pass the whole first half and lose the one true case.

import { describeLoadFailure } from "@/lib/loadFailure";

function apiError(status: number | undefined, message: string) {
  const e = new Error(message) as Error & { status?: number };
  if (status !== undefined) e.status = status;
  return e;
}

describe("a 404 — and only a 404 — says not found", () => {
  it("names the subject", () => {
    expect(describeLoadFailure(apiError(404, "Event not found"), "event")).toEqual({
      title: "Event not found",
      message: "Event not found",
      retryable: false,
    });
  });

  it("offers no retry, because reloading a 404 reloads a 404", () => {
    expect(describeLoadFailure(apiError(404, ""), "event").retryable).toBe(false);
  });

  it("writes its own sentence when the server sent none", () => {
    expect(describeLoadFailure(apiError(404, ""), "market").message).toBe(
      "This market does not exist, or it has been removed.",
    );
  });
});

describe("the failures that are NOT a missing thing", () => {
  it.each([
    [429, "Too many requests"],
    [500, "Couldn't load this event"],
    [502, "Couldn't load this event"],
    [503, "Couldn't load this event"],
    [403, "Couldn't load this event"],
    [400, "Couldn't load this event"],
  ])("status %i does not claim the event is missing", (status, title) => {
    const failure = describeLoadFailure(apiError(status, "boom"), "event");
    expect(failure.title).toBe(title);
    expect(failure.title.toLowerCase()).not.toContain("not found");
    expect(failure.retryable).toBe(true);
  });

  it("keeps the server's own words as the message", () => {
    // THE production specimen. The most specific true thing available is what
    // the server said, and the heading is only ever a heading over it.
    const failure = describeLoadFailure(
      apiError(429, "Rate limit exceeded: 60/minute"),
      "event",
    );
    expect(failure.title).toBe("Too many requests");
    expect(failure.message).toBe("Rate limit exceeded: 60/minute");
  });

  it("writes a sentence for a throttle the server did not explain", () => {
    expect(describeLoadFailure(apiError(429, ""), "event").message).toBe(
      "We are being rate limited right now. Wait a moment and try again.",
    );
  });
});

describe("no status at all — a timeout, an abort, an offline device", () => {
  it("says we could not reach the server, not that the event is gone", () => {
    // `apiFetch` throws a plain Error for these, so the ABSENCE of a status is
    // the signal. This is the case a `status >= 400` chain silently drops into
    // its else branch.
    const failure = describeLoadFailure(apiError(undefined, ""), "event");
    expect(failure.title).toBe("Couldn't reach the server");
    expect(failure.title.toLowerCase()).not.toContain("not found");
    expect(failure.retryable).toBe(true);
  });

  it("handles a null error, which is the `!event` arm", () => {
    // The page renders this branch for `eventError || !event`, so `null` is a
    // real input and must not throw.
    const failure = describeLoadFailure(null, "event");
    expect(failure.title).toBe("Couldn't reach the server");
    expect(failure.message).toContain("event");
  });

  it("handles undefined", () => {
    expect(() => describeLoadFailure(undefined, "event")).not.toThrow();
  });
});

describe("the subject is a parameter, so one module serves every page", () => {
  it("capitalizes it in the heading and leaves it lower case mid-sentence", () => {
    expect(describeLoadFailure(apiError(404, ""), "tournament").title).toBe(
      "Tournament not found",
    );
    expect(describeLoadFailure(apiError(undefined, ""), "tournament").message).toContain(
      "this tournament",
    );
  });

  it("defaults to a neutral noun rather than guessing", () => {
    expect(describeLoadFailure(apiError(404, ""), undefined).title).toBe(
      "Page not found",
    );
  });
});
