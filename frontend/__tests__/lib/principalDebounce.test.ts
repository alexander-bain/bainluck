// UX-P017 / #1496, defect 3 — the debounced save that outlived its account.
//
// The reported failure verbatim: account A edits an interest, the 2s debounce is
// pending, the user switches to account B, the timer fires, and because the API
// client's auth-token getter is module-global by then, A's map is written to B.
// The fake-timer test below IS that sequence.

import { createPrincipalDebouncer } from "@/lib/principalDebounce";

type Interests = Record<string, number>;

const A = "user:acct-a";
const B = "user:acct-b";

describe("createPrincipalDebouncer", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("A edits → switch to B → advance the clock: A's map is NEVER dispatched", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, save);
    // The account changes before the timer fires.
    debouncer.retarget(B);
    jest.advanceTimersByTime(5000);

    expect(save).not.toHaveBeenCalled();
    expect(debouncer.pendingOwner).toBeUndefined();
  });

  it("the same edit still saves when the account does NOT change (both directions)", () => {
    // Gotcha #43: cancelling too eagerly would silently stop every save from
    // ever reaching the server, which is a worse bug than the one being fixed.
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, save);
    debouncer.retarget(A); // a re-render for the same account
    jest.advanceTimersByTime(2000);

    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ nba: 1.0 }, A);
  });

  it("does not fire early", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, save);
    jest.advanceTimersByTime(1999);
    expect(save).not.toHaveBeenCalled();

    jest.advanceTimersByTime(1);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("coalesces rapid clicks into one save carrying the LAST value", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 0.1 }, save);
    jest.advanceTimersByTime(500);
    debouncer.schedule(A, { nba: 0.3 }, save);
    jest.advanceTimersByTime(500);
    debouncer.schedule(A, { nba: 1.0 }, save);
    jest.advanceTimersByTime(2000);

    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ nba: 1.0 }, A);
  });

  it("cancel() drops a pending save — the unmount case", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, save);
    debouncer.cancel();
    jest.advanceTimersByTime(5000);

    expect(save).not.toHaveBeenCalled();
  });

  it("signing OUT mid-debounce also cancels — an anonymous owner is a different owner", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, save);
    debouncer.retarget(null);
    jest.advanceTimersByTime(5000);

    expect(save).not.toHaveBeenCalled();
  });

  it("retarget on an idle debouncer is harmless", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.retarget(B);
    expect(debouncer.pendingOwner).toBeUndefined();

    debouncer.schedule(B, { nfl: 1.0 }, save);
    jest.advanceTimersByTime(2000);
    expect(save).toHaveBeenCalledWith({ nfl: 1.0 }, B);
  });

  it("B's own edit after the switch saves as B, with B's data only", () => {
    const save = jest.fn();
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, save);
    debouncer.retarget(B);
    debouncer.schedule(B, { golf: 0.3 }, save);
    jest.advanceTimersByTime(2000);

    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ golf: 0.3 }, B);
  });

  it("tells the callback which owner it is firing for, so the call site can assert", () => {
    const seen: Array<string | null> = [];
    const debouncer = createPrincipalDebouncer<Interests>(2000);

    debouncer.schedule(A, { nba: 1.0 }, (_value, owner) => seen.push(owner));
    jest.advanceTimersByTime(2000);

    expect(seen).toEqual([A]);
  });
});
