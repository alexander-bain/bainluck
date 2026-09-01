// #1602 (UX-P034): the matchups-&-props rail's family grouping.
//
// Gotcha #43 says a cap's guard tests must assert BOTH directions. Here that is:
// the 52,000px wall gets bounded into family headers AND a normal-sized event
// (UFC card, cycling GC, soccer bracket) keeps rendering exactly as it does
// today, rather than becoming a pile of collapsed groups each holding one row.

import {
  MATCHUP_GROUPING_THRESHOLD,
  groupMatchupsByFamily,
  matchupFamilyKey,
} from "@/lib/matchupFamilies";

/** Names lifted verbatim from the live tennis envelope censused for #1602. */
const REAL_NAMES: [string, string][] = [
  ["National Bank Open: Completed Match: Arthur Rinderknech vs Brandon Nakashima", "completed"],
  ["Mubadala Citi DC Open, Qualification: Completed Match: Polina Kudermetova vs Mei Yamaguchi", "completed"],
  ["Will Hugh Jackman attend the US Open Finals?", "appearance"],
  ["Carlos Alcaraz to play in the US Open", "appearance"],
  ["What will the announcers say during Fritz vs Zverev", "appearance"],
  ["Jenson Brooksby vs Ignacio Buse: Set 1 Winner", "set_winner"],
  ["Set 1 Winner: Bublik vs Etcheverry", "set_winner"],
  ["Set Handicap: Borges (-1.5) vs Burruchaga (+1.5)", "set_handicap"],
  ["Sebastian Baez vs. Arthur Rinderknech: Total Sets O/U 2.5", "set_total"],
  ["Denis Shapovalov vs Pablo Carreno Busta: Total Games", "game_total"],
  ["Jiri Lehecka vs Alexander Zverev: Set 1 Games O/U 9.5", "game_total"],
  ["Jiri Lehecka vs Alexander Zverev: Game Spread", "game_spread"],
  ["Denis Shapovalov vs Pablo Carreno Busta: Exact Match Score", "exact_score"],
  ["Zachary Svajda vs Kamil Majchrzak: Aces", "serve"],
  // Plain match winners, with and without a tournament prefix, singles and doubles.
  ["Duckworth / Kecmanovic vs Bonzi / Rinderknech", "match_winner"],
  ["National Bank Open: Tallon Griekspoor vs Daniel Merida Aguilar", "match_winner"],
  ["Hanfmann vs Vacherot", "match_winner"],
  // Nothing recognisable at all still lands somewhere.
  ["2026 Men’s US Open Winner (Tennis)", "other"],
];

const mk = (market_name: string) => ({ market_name });

describe("matchupFamilyKey", () => {
  it.each(REAL_NAMES)("classifies %s as %s", (name, expected) => {
    expect(matchupFamilyKey(name)).toBe(expected);
  });

  it("puts 'Completed Match' ahead of the match-winner fallback", () => {
    // Both contain "vs"; order in the table is what keeps them apart, and a
    // reordering would silently merge 338 completed matches into the winners.
    expect(matchupFamilyKey("Open: Completed Match: A vs B")).toBe("completed");
    expect(matchupFamilyKey("Open: A vs B")).toBe("match_winner");
  });

  it("never throws on an empty or missing name", () => {
    expect(matchupFamilyKey("")).toBe("other");
    expect(matchupFamilyKey(undefined as unknown as string)).toBe("other");
  });
});

describe("groupMatchupsByFamily — the wall gets bounded", () => {
  /** 300 cards spread over several families, the shape the tennis page has. */
  const bigField = [
    ...Array.from({ length: 150 }, (_, i) => mk(`Open: Player ${i}A vs Player ${i}B`)),
    ...Array.from({ length: 100 }, (_, i) => mk(`Open: Completed Match: P${i}A vs P${i}B`)),
    ...Array.from({ length: 40 }, (_, i) => mk(`P${i}A vs P${i}B: Total Games`)),
    ...Array.from({ length: 10 }, (_, i) => mk(`P${i}A vs P${i}B: Set 1 Winner`)),
  ];

  it("turns hundreds of rows into a handful of family headers", () => {
    const groups = groupMatchupsByFamily(bigField);
    expect(groups).not.toBeNull();
    expect(groups!.length).toBe(4);
    expect(groups!.map((g) => g.label)).toEqual([
      "Completed matches",
      "Set winners",
      // #2442: was "Game totals" — the betting noun for an over/under.
      "Combined score",
      "Match winners",
    ]);
    expect(groups!.map((g) => g.items.length)).toEqual([100, 10, 40, 150]);
  });

  it("drops nothing — the groups union back to the input", () => {
    const groups = groupMatchupsByFamily(bigField)!;
    const flat = groups.flatMap((g) => g.items);
    expect(flat).toHaveLength(bigField.length);
    expect(new Set(flat.map((i) => i.market_name)).size).toBe(
      new Set(bigField.map((i) => i.market_name)).size,
    );
  });

  it("preserves input order inside a group", () => {
    const groups = groupMatchupsByFamily(bigField)!;
    const winners = groups.find((g) => g.key === "match_winner")!;
    expect(winners.items[0].market_name).toBe("Open: Player 0A vs Player 0B");
    expect(winners.items[149].market_name).toBe("Open: Player 149A vs Player 149B");
  });

  it("keys groups by family, not by index, so open state survives a refresh", () => {
    // The page polls every 30s and swaps data in place. If a group's React key
    // moved when the item count changed, an opened <details> would collapse.
    const before = groupMatchupsByFamily(bigField)!;
    const after = groupMatchupsByFamily([...bigField, mk("Open: New vs Player")])!;
    expect(after.map((g) => g.key)).toEqual(before.map((g) => g.key));
  });

  it("falls back rather than dropping an unrecognised market", () => {
    const groups = groupMatchupsByFamily([
      ...Array.from({ length: 30 }, (_, i) => mk(`Open: A${i} vs B${i}`)),
      mk("Something nobody has seen before"),
    ])!;
    const other = groups.find((g) => g.key === "other")!;
    expect(other.items).toHaveLength(1);
    expect(groups[groups.length - 1].key).toBe("other"); // kept last
  });
});

describe("groupMatchupsByFamily — a normal event does not get worse", () => {
  it("returns null at or below the threshold", () => {
    const card = Array.from({ length: MATCHUP_GROUPING_THRESHOLD }, (_, i) =>
      mk(i % 2 ? `Fighter ${i} vs Fighter ${i + 1}` : `Bout ${i}: Total Games`),
    );
    expect(card).toHaveLength(24);
    // A 12-fight UFC card, a 24-market Tour de France GC: unchanged, flat.
    expect(groupMatchupsByFamily(card)).toBeNull();
    expect(groupMatchupsByFamily(card.slice(0, 12))).toBeNull();
    expect(groupMatchupsByFamily([])).toBeNull();
  });

  it("engages one card above the threshold", () => {
    const justOver = Array.from({ length: MATCHUP_GROUPING_THRESHOLD + 1 }, (_, i) =>
      mk(i % 2 ? `A${i} vs B${i}` : `A${i} vs B${i}: Total Games`),
    );
    expect(groupMatchupsByFamily(justOver)).not.toBeNull();
  });

  it("returns null when a large field is all one family", () => {
    // A soccer bracket is 64 team duels and nothing else. One header wrapping
    // the whole grid buys nothing and would hide the bracket behind a click.
    const bracket = Array.from({ length: 64 }, (_, i) => mk(`Nation ${i} vs Nation ${i + 1}`));
    expect(groupMatchupsByFamily(bracket)).toBeNull();
  });

  it("returns null for a large field of unnamed matchup children", () => {
    // Soccer/World-Cup children carry home/away, not always a market_name.
    const unnamed = Array.from({ length: 64 }, () => ({}) as { market_name?: string });
    expect(groupMatchupsByFamily(unnamed)).toBeNull();
  });
});
