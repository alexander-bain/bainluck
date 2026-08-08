// UX-P017 / #1496 — the pin merge, where the durable cross-account write
// actually happened.
//
// #1496's acceptance asks for a NEGATIVE to be proven: "no `addPin` of an
// A-only id". A negative is only provable at the point of decision, so the
// decision was moved out of the React effect and into `mergeForMigration`.

import { parseIds, serializeIds, mergeForMigration } from "@/lib/pinnedIds";

describe("parseIds — tolerate anything a device can hand back", () => {
  it("reads a well-formed list", () => {
    expect(parseIds("[1,2,3]")).toEqual([1, 2, 3]);
  });

  it("treats absent, empty, corrupt, or wrong-typed values as no pins", () => {
    expect(parseIds(null)).toEqual([]);
    expect(parseIds("")).toEqual([]);
    expect(parseIds("not json")).toEqual([]);
    expect(parseIds('{"a":1}')).toEqual([]);
    expect(parseIds('["1","2"]')).toEqual([]);
    expect(parseIds("[1,\"2\"]")).toEqual([]);
  });

  it("round-trips", () => {
    expect(parseIds(serializeIds([4, 5]))).toEqual([4, 5]);
  });
});

describe("mergeForMigration", () => {
  it("pushes ONLY ids the account did not already have", () => {
    const { merged, toPush } = mergeForMigration([1, 2], [2, 3], 6);
    expect(merged).toEqual([1, 2, 3]);
    expect(toPush).toEqual([3]);
  });

  it("pushes nothing when there is nothing to migrate — the A→B case", () => {
    // With the storage policy refusing to hand over another account's bucket,
    // `migrateIds` is empty for B. Zero writes must follow.
    const { merged, toPush } = mergeForMigration([1, 2], [], 6);
    expect(merged).toEqual([1, 2]);
    expect(toPush).toEqual([]);
  });

  it("never drops an id the account already owns", () => {
    const { merged } = mergeForMigration([1, 2, 3], [4], 6);
    expect(merged.slice(0, 3)).toEqual([1, 2, 3]);
  });

  it("truncates the MIGRATED tail at the cap, never the server's own pins", () => {
    const server = [1, 2, 3, 4, 5];
    const { merged, toPush } = mergeForMigration(server, [6, 7, 8], 6);

    expect(merged).toEqual([1, 2, 3, 4, 5, 6]);
    expect(toPush).toEqual([6]);
    // Nothing pushed that the user cannot see.
    expect(toPush.every((id) => merged.includes(id))).toBe(true);
  });

  it("an account already at the cap adopts nothing", () => {
    const server = [1, 2, 3, 4, 5, 6];
    const { merged, toPush } = mergeForMigration(server, [7, 8], 6);

    expect(merged).toEqual(server);
    expect(toPush).toEqual([]);
  });

  it("de-duplicates within the migrating set", () => {
    const { merged, toPush } = mergeForMigration([], [3, 3, 4], 6);
    expect(merged).toEqual([3, 4]);
    expect(toPush).toEqual([3, 4]);
  });

  it("every pushed id is in the merged set, always (invariant)", () => {
    const cases: Array<[number[], number[], number]> = [
      [[], [], 6],
      [[1], [1], 6],
      [[1, 2, 3], [3, 4, 5, 6, 7], 6],
      [[], [1, 2, 3, 4, 5, 6, 7, 8], 6],
      [[1, 2, 3, 4, 5, 6], [7], 6],
    ];
    for (const [server, migrate, max] of cases) {
      const { merged, toPush } = mergeForMigration(server, migrate, max);
      expect(merged.length).toBeLessThanOrEqual(Math.max(max, server.length));
      expect(toPush.every((id) => merged.includes(id))).toBe(true);
      expect(toPush.every((id) => !server.includes(id))).toBe(true);
      expect(new Set(merged).size).toBe(merged.length);
    }
  });
});
