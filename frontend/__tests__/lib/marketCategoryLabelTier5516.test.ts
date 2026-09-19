// #5516, defect 2 — "a 6th-inning prop is badged Championship".
//
// #2710 made the chip read as English. It could not make it read as TRUE: it
// title-cases `FuturesMarket.category` faithfully, and Polymarket's poller
// returns the single value `championship` from every arm of its cascade that
// lands on a sport (`tasks/polymarket.py`), so the column there means "this is
// sport", spelled with the wrong word.
//
// ARM 1 OF THIS ISSUE IS ALREADY LIVE (v4766) and is NOT what this file tests.
// It corrects the category at INGEST for names of the `A vs B - Nth Inning
// Winner` shape, via `game_prop_category`. This is the residue that predicate
// cannot see: rows whose NAME is not a fixture-prop string, so the writer leaves
// them `championship` while `compute_market_tier` — reading the same name —
// files them tier 5.
//
// THE POPULATION IS MEASURED, NOT IMAGINED. Production 2026-09-19:
// `SELECT source, market_tier, count(*) FROM futures_markets WHERE
// status='open' AND category='championship' GROUP BY source, market_tier`
// returned 12,724 rows at tier 5 (11,025 Polymarket, 1,698 Kalshi, 1 Odds API),
// against 524 at tier 1.
//
// THE SPECIMEN IS FROM A 390px LOOK at https://bainluck.com/search?q=chiefs on
// 2026-09-19 (artifacts-lane1b-389/chiefs-390.png): five of the ten futures rows
// that query serves carry `category: "championship"` with
// `market_type_label: "Prop"` — the backend contradicting itself inside one
// payload, which is what makes this decidable without inventing a word.

import { marketCategoryLabel } from "@/lib/marketCategoryLabel";

/**
 * The five rows `GET /api/events/search?q=chiefs` served on 2026-09-19, verbatim.
 * Two are correctly categorised and are the controls.
 */
const CHIEFS_PAYLOAD: ReadonlyArray<{
  readonly id: number;
  readonly name: string;
  readonly category: string;
  readonly market_tier: number;
  readonly chip: string | null;
}> = [
  // The LOOK specimen: a novelty prop in the same purple pill as a real title race.
  {
    id: 61441990,
    name: "What will the announcers say during the Colts vs Chiefs game?",
    category: "championship",
    market_tier: 5,
    chip: null,
  },
  { id: 59659429, name: "IND Colts vs KC Chiefs", category: "championship", market_tier: 5, chip: null },
  {
    id: 56722505,
    name: "Pro Football: Broncos vs. Chiefs Season Series Winner",
    category: "championship",
    market_tier: 5,
    chip: null,
  },
  // CONTROL — a real championship, on the same rail, must be untouched.
  { id: 129037, name: "Pro Football: 2027 Champion", category: "championship", market_tier: 1, chip: "Championship" },
  // CONTROL — tier 5 too, but its category is already right. This is the row
  // that fails if the rule keys on the TIER instead of on the contradiction.
  {
    id: 61184052,
    name: "IND Colts vs KC Chiefs: 1st Half Spread",
    category: "game_prop",
    market_tier: 5,
    chip: "Game Props",
  },
];

describe("#5516 — the chip does not claim a rung the row's own tier denies", () => {
  it.each(CHIEFS_PAYLOAD)("$name -> $chip", ({ category, market_tier, chip }) => {
    expect(marketCategoryLabel(category, market_tier)).toBe(chip);
  });

  it("the specimen loses the claim and the real championship keeps it", () => {
    // Stated as one assertion as well as row-wise, because the pair IS the ship:
    // suppressing both would be a regression dressed as a fix.
    expect(marketCategoryLabel("championship", 5)).toBeNull();
    expect(marketCategoryLabel("championship", 1)).toBe("Championship");
  });
});

describe("#5516 — an absent tier keeps today's behaviour, it does not blank the card", () => {
  // Vercel ships ahead of Heroku, so every deploy has a window in which the
  // payload carries no `market_tier`. Suppressing on absent would blank the chip
  // on EVERY card for the length of that window — a far larger regression than
  // the defect. The gate therefore reads an explicit 5 and nothing else.
  it.each([undefined, null])("tier %p still prints Championship", (tier) => {
    expect(marketCategoryLabel("championship", tier)).toBe("Championship");
  });

  it("the whole #2710 call shape — one argument — is unchanged", () => {
    // `marketCategoryLabel2710.test.ts` calls this way throughout, so that file
    // is this ship's regression suite. Pinned here too so the compatibility is
    // an assertion and not an accident of another file's style.
    expect(marketCategoryLabel("championship")).toBe("Championship");
    expect(marketCategoryLabel("game_prop")).toBe("Game Props");
  });
});

describe("#5516 — the scope is the maximal contradiction, and that is deliberate", () => {
  // Tiers 2-4 are adjacent rungs of the same hierarchy (conference / award /
  // division), where "Championship" is imprecise rather than false. ~750 open
  // rows sit there on production and are LEFT. Pinned so that widening the fix
  // is a decision someone makes, not a drift that happens.
  it.each([2, 3, 4])("tier %i still prints Championship", (tier) => {
    expect(marketCategoryLabel("championship", tier)).toBe("Championship");
  });

  it("only a category that NAMES a rung can be contradicted", () => {
    // `politics` and the rest claim no tier, so tier 5 tells us nothing about
    // them and must not silence them.
    for (const category of ["politics", "economics", "entertainment", "weather", "placement"]) {
      expect(marketCategoryLabel(category, 5)).not.toBeNull();
    }
  });

  it("the contradiction test is case- and whitespace-tolerant like the map above it", () => {
    expect(marketCategoryLabel("  CHAMPIONSHIP  ", 5)).toBeNull();
  });
});
