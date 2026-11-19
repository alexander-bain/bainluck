/**
 * #11937 (159-A): /grade?slate=<id>&set=<name> asks for the slate's deck with a
 * named extra set mixed in; with no set the request is exactly as before.
 */
import { gradeDeckPath, setFromSearch } from "@/lib/ranking/gradeSession";

describe("setFromSearch", () => {
  it("reads a safe set name", () => {
    expect(setFromSearch("?slate=c5a077361cd9e2dc&set=round-1")).toBe("round-1");
  });
  it("ignores a missing, empty or unsafe value", () => {
    expect(setFromSearch("?slate=x")).toBeNull();
    expect(setFromSearch("?set=")).toBeNull();
    expect(setFromSearch("?set=../x")).toBeNull();
  });
});

describe("gradeDeckPath with a set", () => {
  it("adds the set only with a slate", () => {
    expect(gradeDeckPath("c5a077361cd9e2dc", "round-1")).toBe(
      "/api/admin/ranking/grade-deck?slate=c5a077361cd9e2dc&set=round-1",
    );
    expect(gradeDeckPath(null, "round-1")).toBe("/api/admin/ranking/grade-deck");
  });
  it("is unchanged with no set", () => {
    expect(gradeDeckPath("2026-11-11")).toBe("/api/admin/ranking/grade-deck?slate=2026-11-11");
    expect(gradeDeckPath("2026-11-11", null)).toBe("/api/admin/ranking/grade-deck?slate=2026-11-11");
  });
});
