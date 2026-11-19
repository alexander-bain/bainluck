/** 227-A point 6: each Discover card names its form for the screen capture. */
import { discoverCardForm } from "@/lib/discoverCardForm";
import type { FeedItem } from "@/lib/types";

const item = (type: string, data: Record<string, unknown> = {}) => ({ type, data }) as unknown as FeedItem;

describe("discoverCardForm", () => {
  it("names each card type's form", () => {
    expect(discoverCardForm(item("event"))).toBe("game");
    expect(discoverCardForm(item("futures"))).toBe("futures");
    expect(discoverCardForm(item("tournament"))).toBe("tournament");
    expect(discoverCardForm(item("concept"))).toBe("concept");
    expect(discoverCardForm(item("bundle", { kind: "theme" }))).toBe("theme");
    expect(discoverCardForm(item("bundle", { kind: "comparison" }))).toBe("comparison");
  });

  it("tells a distribution futures card from a plain one, as DiscoverCard draws them", () => {
    const four = [1, 2, 3, 4].map((i) => ({ name: `o${i}` }));
    const dist = { discover_card: { suggested_format: "outcome_distribution" }, top_outcomes: four };
    expect(discoverCardForm(item("futures", dist))).toBe("futures-distribution");
    expect(discoverCardForm(item("futures", { ...dist, top_outcomes: four.slice(0, 3) }))).toBe("futures");
  });

  it("carries a round-up's machinery form when it has one", () => {
    expect(discoverCardForm(item("bundle", { kind: "roundup", roundup: { machinery_card: { form_id: "matchup_slate" } } }))).toBe("roundup:matchup_slate");
    expect(discoverCardForm(item("bundle", { kind: "roundup", roundup: {} }))).toBe("roundup");
  });
});
