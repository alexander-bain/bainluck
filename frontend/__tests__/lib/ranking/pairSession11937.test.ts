/**
 * #11937 (171-A): /grade/pair reads only a slate and an opaque pair name from the
 * link, and asks the server for two unlabelled sides.
 */
import { PAIR_CHOICES, PAIR_CHOICE_LABELS, gradeDeckHref, pairFromSearch, pairPath } from "@/lib/ranking/pairSession";

describe("pairFromSearch", () => {
  it("needs both a slate and a pair, each a safe reference", () => {
    expect(pairFromSearch("?slate=59da9307253a78dc&pair=p1")).toEqual({ slate: "59da9307253a78dc", pair: "p1" });
    expect(pairFromSearch("?slate=59da9307253a78dc")).toBeNull();
    expect(pairFromSearch("?pair=p1")).toBeNull();
    expect(pairFromSearch("?slate=x&pair=../p")).toBeNull();
  });
});

describe("pairPath", () => {
  it("names only the slate and the pair", () => {
    expect(pairPath("59da9307253a78dc", "p1")).toBe("/api/admin/ranking/pair?slate=59da9307253a78dc&pair=p1");
  });
});

describe("the three answers", () => {
  it("are left, right and no difference, and none names a side's origin", () => {
    expect(PAIR_CHOICES).toEqual(["left", "right", "none"]);
    for (const label of Object.values(PAIR_CHOICE_LABELS)) {
      expect(label).not.toMatch(/served|candidate|today|new|current/i);
    }
  });
});

describe("gradeDeckHref", () => {
  it("goes on to the same slate's deck after the pick", () => {
    expect(gradeDeckHref("59da9307253a78dc")).toBe("/grade?slate=59da9307253a78dc");
  });
});
