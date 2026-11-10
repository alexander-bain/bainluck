/**
 * #11937 (127-A): /grade?slate=<date or id> opens that saved slate's spread deck.
 * The pure half: reading the slate from the URL and building the deck request.
 */
import { gradeDeckInit, gradeDeckPath, slateFromSearch, deckHeadline } from "@/lib/ranking/gradeSession";

describe("slateFromSearch", () => {
  it("reads a Pacific date or a slate id", () => {
    expect(slateFromSearch("?slate=2026-11-10")).toBe("2026-11-10");
    expect(slateFromSearch("?slate=327293405b250480&x=1")).toBe("327293405b250480");
  });
  it("ignores a missing, empty or unsafe value", () => {
    expect(slateFromSearch("")).toBeNull();
    expect(slateFromSearch("?slate=")).toBeNull();
    expect(slateFromSearch("?slate=../../x")).toBeNull();
    expect(slateFromSearch("?slate=" + "a".repeat(65))).toBeNull();
  });
});

describe("gradeDeckPath", () => {
  it("is today's opening ten with no slate, and names the slate otherwise", () => {
    expect(gradeDeckPath(null)).toBe("/api/admin/ranking/grade-deck");
    expect(gradeDeckPath("327293405b250480")).toBe("/api/admin/ranking/grade-deck?slate=327293405b250480");
  });
});

describe("gradeDeckInit", () => {
  it("sends the grader's name in a header, never the URL", () => {
    expect(gradeDeckInit(null)).toBeUndefined();
    expect(gradeDeckInit("Alex Bain")).toEqual({ headers: { "X-Grader-Name": "Alex%20Bain" } });
    expect(gradeDeckPath("2026-11-09")).not.toMatch(/grader/);
  });
});

describe("deckHeadline", () => {
  const base = { switch_on: true, slate_id: "s", surface: "discover", captured_at: "2026-11-09T15:15:00+00:00", ranker_version: "v", items: [] };
  it("keeps today's line for the opening ten", () => {
    expect(deckHeadline({ ...base, items: new Array(10).fill(null) } as never)).toMatch(/^The top 10 Discover cards from /);
  });
  it("says a spread deck covers the slate top to bottom and how many are already done", () => {
    const line = deckHeadline({ ...base, mode: "spread", candidates: 157, already_graded: 3, items: new Array(27).fill(null) } as never);
    expect(line).toMatch(/^27 cards from the Discover slate of /);
    expect(line).toMatch(/a spread down the rest of its 157/);
    expect(line).toMatch(/3 you've already graded are skipped/);
  });
});
