import {
  groupRelatedMarkets,
  RELATED_SECTIONS,
  RELATED_FALLBACK,
} from "@/lib/golfRelatedSections";

const mk = (id: number, market_name: string) => ({ market_id: id, market_name });

describe("groupRelatedMarkets (#951 tournament prop layout)", () => {
  it("buckets the live U.S. Open related_futures shape into labeled sections", () => {
    // The exact set the backend returned for u-s-open during Queue #92.
    const markets = [
      mk(1, "Will there be a hole in one at the 2026 U.S. Open?"),
      mk(2, "2026 U.S. Open: First Round Leader"),
      mk(3, "2026 U.S. Open: Second Round Leader"),
      mk(4, "U.S. Open: Hole-in-One"),
      mk(5, "Golfers to compete in US Open this year"),
      mk(6, "2026 U.S. Open: Third Round Leader"),
      mk(7, "2026 U.S. Open: Player to Shoot Best Round"),
      mk(8, "Will there be a playoff at the 2026 U.S. Open?"),
    ];
    const sections = groupRelatedMarkets(markets);
    const byId = Object.fromEntries(sections.map((s) => [s.id, s]));

    expect(byId.round_leaders.markets.map((m) => m.market_id)).toEqual([2, 3, 6]);
    expect(byId.specials.markets.map((m) => m.market_id)).toEqual([1, 4, 8]);
    expect(byId.scoring.markets.map((m) => m.market_id)).toEqual([7]);
    expect(byId.field.markets.map((m) => m.market_id)).toEqual([5]);
    // nothing should fall into the generic bucket for this set
    expect(byId.other).toBeUndefined();
  });

  it("preserves the section display order and drops empty sections", () => {
    const markets = [
      mk(1, "Will there be a playoff?"), // specials
      mk(2, "First Round Leader"), // round_leaders
    ];
    const ids = groupRelatedMarkets(markets).map((s) => s.id);
    // round_leaders is defined before specials, so it renders first regardless
    // of input order; no empty sections appear.
    expect(ids).toEqual(["round_leaders", "specials"]);
  });

  it("routes finish-position and unknown markets correctly", () => {
    const markets = [
      mk(1, "Top 40 Finish: Scottie Scheffler"),
      mk(2, "Make the Cut: Rory McIlroy"),
      mk(3, "Some unclassifiable novelty market"),
    ];
    const byId = Object.fromEntries(
      groupRelatedMarkets(markets).map((s) => [s.id, s]),
    );
    expect(byId.finish.markets.map((m) => m.market_id)).toEqual([1, 2]);
    expect(byId.other.title).toBe(RELATED_FALLBACK.title);
    expect(byId.other.markets.map((m) => m.market_id)).toEqual([3]);
  });

  it("every section regex is anchored to a stable id", () => {
    expect(RELATED_SECTIONS.map((s) => s.id)).toEqual([
      "round_leaders",
      "finish",
      "scoring",
      "specials",
      "field",
    ]);
  });
});
