// A ROW WE TOOK DOWN ON PURPOSE MUST NOT READ AS A SERVER MALFUNCTION — lane1/132.
//
// `GET /api/events/{id}` now answers **410 Gone** for a row whose `status` is a
// retirement marker (`merged`, `voided`): a duplicate whose markets moved to the
// row that keeps them, or a fixture that will not be played. The production
// specimen is event 14751059 — Denver Broncos at Arizona Cardinals on
// 2026-12-27, a game that will never happen, which rendered with a price, a
// countdown and a win-probability chart on it.
//
// Without a 410 branch that response falls into `loadFailure`'s generic 4xx arm
// and the reader is shown
//
//   Couldn't load this event
//   The server refused the request (410).
//   Tap to retry
//
// which is a machine's sentence for a decision we made, over a button that will
// return the same answer every time it is pressed. #2783 fixed exactly this
// shape for 429 and 500; this is the same lesson arriving at a new status.
//
// WHY NOT 404. Both are "there is no page here", and they are different
// instructions to the reader: not-found means *you may have the wrong address*,
// gone means *the address was right and there is nothing to come back for*. The
// backend distinguishes them, so this module has to as well or the distinction
// dies one layer below the only person it is for.
//
// BOTH DIRECTIONS PER GOTCHA #43. Every "410 is its own thing" case has a
// sibling proving the arms either side of it — 404 and the generic 4xx — are
// untouched. A module that answered everything with the gone wording would pass
// the first half of this file and be a worse bug than the one it replaced.

import { describeLoadFailure } from "@/lib/loadFailure";

function apiError(status: number | undefined, message: string) {
  const e = new Error(message) as Error & { status?: number };
  if (status !== undefined) e.status = status;
  return e;
}

// The sentence the backend actually sends (`routes/events.py`, `get_event`).
const SERVED_DETAIL =
  "This fixture was removed from the schedule — it was either a duplicate of " +
  "another game or a game that will not be played.";

describe("410 — the thing was here and we took it down", () => {
  it("says it is no longer listed, not that the request was refused", () => {
    const failure = describeLoadFailure(apiError(410, SERVED_DETAIL), "event");

    expect(failure.title).toBe("This event is no longer listed");
    expect(failure.title.toLowerCase()).not.toContain("couldn't load");
    expect(failure.title.toLowerCase()).not.toContain("not found");
  });

  it("keeps the server's own sentence, which is the specific true thing", () => {
    const failure = describeLoadFailure(apiError(410, SERVED_DETAIL), "event");
    expect(failure.message).toBe(SERVED_DETAIL);
  });

  it("offers no retry, because the removal was deliberate and recorded", () => {
    expect(describeLoadFailure(apiError(410, SERVED_DETAIL), "event").retryable).toBe(
      false,
    );
  });

  it("writes its own sentence when the server sent none", () => {
    expect(describeLoadFailure(apiError(410, ""), "event").message).toBe(
      "This event was removed from the site and is not coming back.",
    );
  });

  it("carries the subject, so one module still serves every page", () => {
    expect(describeLoadFailure(apiError(410, ""), "market").title).toBe(
      "This market is no longer listed",
    );
  });
});

describe("the arms either side of 410 are untouched", () => {
  it("404 still says not found — a wrong address is not a removal", () => {
    const failure = describeLoadFailure(apiError(404, "Event not found"), "event");
    expect(failure.title).toBe("Event not found");
    expect(failure.retryable).toBe(false);
  });

  it.each([
    [400, "Couldn't load this event"],
    [403, "Couldn't load this event"],
    [409, "Couldn't load this event"],
    [411, "Couldn't load this event"],
    [429, "Too many requests"],
    [500, "Couldn't load this event"],
  ])("status %i is still retryable and does not borrow the gone wording", (
    status,
    title,
  ) => {
    const failure = describeLoadFailure(apiError(status, "boom"), "event");
    expect(failure.title).toBe(title);
    expect(failure.title).not.toContain("no longer listed");
    expect(failure.retryable).toBe(true);
  });

  it("a missing status is still a connection problem, not a removal", () => {
    const failure = describeLoadFailure(apiError(undefined, ""), "event");
    expect(failure.title).toBe("Couldn't reach the server");
    expect(failure.retryable).toBe(true);
  });
});
