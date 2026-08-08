// UX-P017 / #1496 defect 4 (found in this queue, not in the original report) —
// the category-interest migration.
//
// Why this one is worse than it looks: the merge is max-wins, so a wrong-
// provenance write can only ever RAISE the receiving account's affinities. It
// steers B's Discover feed toward A's tastes and there is no subsequent read
// that would reveal the error.

import {
  INTERESTS_POLICY,
  parseInterests,
  serializeInterests,
  mergeInterests,
  mergeIsNoop,
} from "@/lib/categoryInterests";

describe("INTERESTS_POLICY", () => {
  it("keeps honouring the pre-existing done flag so devices do not re-migrate", () => {
    expect(INTERESTS_POLICY.base).toBe("bainluck_categoryInterests");
    expect(INTERESTS_POLICY.legacyDoneKey).toBe("bainluck_interestsSyncedToServer");
  });
});

describe("parseInterests", () => {
  it("reads a well-formed map", () => {
    expect(parseInterests('{"nba":1,"golf":0.3}')).toEqual({ nba: 1, golf: 0.3 });
  });

  it("treats absent or corrupt values as no interests", () => {
    expect(parseInterests(null)).toEqual({});
    expect(parseInterests("")).toEqual({});
    expect(parseInterests("nope")).toEqual({});
    expect(parseInterests("[1,2]")).toEqual({});
  });

  it("drops non-numeric and non-finite values rather than propagating them", () => {
    expect(parseInterests('{"nba":1,"nfl":"high","golf":null}')).toEqual({ nba: 1 });
    expect(parseInterests('{"nba":1e999}')).toEqual({});
  });

  it("round-trips", () => {
    expect(parseInterests(serializeInterests({ nba: 0.3 }))).toEqual({ nba: 0.3 });
  });
});

describe("mergeInterests — max wins", () => {
  it("takes the higher value per category", () => {
    expect(mergeInterests({ nba: 0.1, nfl: 1 }, { nba: 1, golf: 0.3 })).toEqual({
      nba: 1,
      nfl: 1,
      golf: 0.3,
    });
  });

  it("never lowers a value the account already had", () => {
    expect(mergeInterests({ nba: 1 }, { nba: 0 })).toEqual({ nba: 1 });
  });

  it("merging nothing changes nothing — the A→B case after the policy fix", () => {
    // B is offered no anonymous bucket, so this is what B's migration computes.
    const server = { nba: 0.3 };
    const merged = mergeInterests(server, {});
    expect(merged).toEqual(server);
    expect(mergeIsNoop(server, merged)).toBe(true);
  });

  it("does not mutate its inputs", () => {
    const server = { nba: 0.1 };
    const anon = { nba: 1 };
    mergeInterests(server, anon);
    expect(server).toEqual({ nba: 0.1 });
    expect(anon).toEqual({ nba: 1 });
  });
});

describe("mergeIsNoop — skip the server write when nothing changed", () => {
  it("detects an identical map", () => {
    expect(mergeIsNoop({ nba: 1 }, { nba: 1 })).toBe(true);
  });

  it("detects a new category", () => {
    expect(mergeIsNoop({ nba: 1 }, { nba: 1, golf: 0.3 })).toBe(false);
  });

  it("detects a raised value", () => {
    expect(mergeIsNoop({ nba: 0.3 }, { nba: 1 })).toBe(false);
  });

  it("handles the empty case", () => {
    expect(mergeIsNoop({}, {})).toBe(true);
    expect(mergeIsNoop({}, { nba: 1 })).toBe(false);
  });

  it("a genuine anonymous migration is NOT skipped (both directions)", () => {
    const server = { nfl: 1 };
    const merged = mergeInterests(server, { nba: 1 });
    expect(mergeIsNoop(server, merged)).toBe(false);
    expect(merged).toEqual({ nfl: 1, nba: 1 });
  });
});
