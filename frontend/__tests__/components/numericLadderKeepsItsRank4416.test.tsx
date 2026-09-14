/**
 * #4416 — A NUMERIC LADDER GETS ITS RANK COLUMN BACK.
 *
 * ── WHAT THE READER SAW ──────────────────────────────────────────────────────
 *
 * `bainluck.com/search?q=Fed rate be at the end of 2026` at 390px, market
 * `114367` (`llm_sport_category = politics`, `market_type = quantity`, $6.7M
 * volume). The badge column, which is meant to read `1 2 3 4 5` with the leader
 * in amber, read:
 *
 *     4    4.0%     42%
 *     3    3.75%    23%
 *     4    4.25%    23%
 *     3    3.5%      7%
 *     ≥4   ≥ 4.5%    5%
 *
 * Three rows share the badge `4`, two share `3`, the amber leader is gone, and
 * the column carries no ordering at all while looking exactly like one.
 *
 * ── THE MECHANISM ────────────────────────────────────────────────────────────
 *
 * `OutcomeRow` swapped the rank badge for a Wikipedia avatar on the eight
 * non-sports categories:
 *
 *     {isNonSports ? <EntityImage type="wikipedia" name={outcome.name} …/>
 *                  : <span …>{rank}</span>}
 *
 * The false premise is "non-sports ⇒ the outcome names are entities". It holds
 * for *Next Prime Minister* and *Best Picture*; it fails for every threshold
 * ladder — Fed rates, index closes, seat counts, temperatures, post counts. For
 * those, `EntityImage` can never resolve a picture and reaches its initials
 * fallback (`.map(w => w.charAt(0))`), which for `"4.25%"` is `4` and for
 * `"≤49"` is `≤`. The badge was not wrong; it had been replaced.
 *
 * ── WHY THE TEST IS THE SET AND NOT THE ROW ──────────────────────────────────
 *
 * The obvious predicate — "the name starts with a digit or a comparator" — is
 * the one the issue proposed, and it is a trap in both directions. It misses
 * most of the real population, which was measured on production rather than
 * guessed: the non-sports names in the wild are `At least 50%`, `Above 250K`,
 * `Before Jan 1, 2027`, `30°C`, `Republicans, 21+ pts`, `Over 0.5 goals scored`
 * — phrases that begin with a WORD. And it fires on real entities that happen
 * to begin with a number: `50 Cent`, `21 Savage`, `3 Doors Down`, all of which
 * live in the `entertainment` category this branch serves.
 *
 * So `isNumericLadder` asks whether a rung has a SIBLING that is the same name
 * with a different number in it. `At least 50%` and `At least 44%` both reduce
 * to `at least %`; `50 Cent` and `Drake` reduce to two different things. A field
 * of rappers therefore cannot trip it however many digits it carries, and a
 * ladder trips it whatever words it is dressed in.
 *
 * All-or-nothing over the whole shipped set, because the badge is a COLUMN: a
 * market that is half quantity and half entity keeps its avatars rather than
 * renumbering some rows and not others. Those mixed `field` markets are the
 * deliberate remainder, and the last test here pins that they are untouched.
 *
 * Measured over 900 live non-sports markets, 2026-09-14: flips 96.3% of
 * `quantity` markets, and 0% of `container_member` (5,044 pure-entity outcomes)
 * and `duel` — no false positive found.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import { isNumericLadder } from "../../lib/images";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";

function outcome(
  id: number,
  name: string,
  probability: number | null,
): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
    last_updated: null,
  } as unknown as FuturesOutcome;
}

function market(
  name: string,
  category: string,
  outcomes: FuturesOutcome[],
): FuturesMarket {
  return {
    id: 114367,
    name,
    description: null,
    source: "kalshi",
    category: null,
    sport: null,
    sport_name: null,
    llm_sport_category: category,
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: outcomes.length,
    created_at: null,
    updated_at: null,
    status: "open",
    outcomes,
  } as unknown as FuturesMarket;
}

function render(m: FuturesMarket): string {
  return renderToStaticMarkup(<FuturesCard market={m} />);
}

/**
 * The contents of the 20px badge cell for every row, in render order.
 *
 * Read off the rank `span`'s own class signature rather than "any short string",
 * so an avatar rendering the initials `4` cannot be mistaken for a rank `4` —
 * telling those two apart is the entire point of this file. Throws when it finds
 * nothing, so a selector that stops matching fails loudly instead of passing an
 * empty array to `toEqual([])` (the vacuous-guard trap).
 */
function renderedRankBadges(html: string): string[] {
  const found = [
    ...html.matchAll(
      /<span class="[^"]*w-5 h-5 flex items-center justify-center text-\[10px\][^"]*">([^<]*)<\/span>/g,
    ),
  ].map((m) => m[1]);
  if (found.length === 0) {
    throw new Error(
      "no rank-badge spans rendered — the extractor is blind, or the card drew avatars",
    );
  }
  return found;
}

/**
 * True when the card drew at least one Wikipedia entity avatar.
 *
 * Keyed on `EntityImage`'s own `data-testid`, which it carries on both fallback
 * treatments (UX-P235's placeholder chip and the coloured-initials disc). NOT on
 * `rounded-full` — the first draft of this helper did that and read `true` on a
 * card with no avatars at all, because the mini probability bar under every row
 * is also `rounded-full`. An oracle that matches the thing it is supposed to
 * prove absent is worth less than no oracle.
 *
 * Under `renderToStaticMarkup` the `useEffect` that fetches the Wikipedia image
 * never runs, so an avatar is always in one of these two states and never an
 * `<img>` — which is exactly the pre-resolution frame a reader sees first.
 */
function drewEntityAvatars(html: string): boolean {
  return /data-testid="entity-image-/.test(html);
}

/** The amber leader treatment, which lives only on the rank badge. */
function hasAmberLeader(html: string): boolean {
  return /bg-accent-warning\/15/.test(html);
}

// The five rows production shipped for market 114367, in production order.
const FED_RATE_ROWS = [
  outcome(1, "4.0%", 0.42),
  outcome(2, "3.75%", 0.23),
  outcome(3, "4.25%", 0.23),
  outcome(4, "3.5%", 0.07),
  outcome(5, "≥ 4.5%", 0.05),
];

// A real politics field of people, from the same category.
const CANDIDATE_ROWS = [
  outcome(1, "Donald Trump", 0.42),
  outcome(2, "Kamala Harris", 0.31),
  outcome(3, "Gavin Newsom", 0.15),
];

describe("#4416 — a numeric ladder keeps its rank, an entity field keeps its face", () => {
  it("numbers the Fed-rate ladder 1..5 instead of printing its own digits", () => {
    // RED BEFORE THIS SHIP: the badges read 4, 3, 4, 3, ≥ — the first character
    // of each outcome name — and `renderedRankBadges` finds nothing at all.
    const html = render(
      market(
        "What will the Fed rate be at the end of 2026?",
        "politics",
        FED_RATE_ROWS,
      ),
    );
    expect(renderedRankBadges(html)).toEqual(["1", "2", "3", "4", "5"]);
    expect(drewEntityAvatars(html)).toBe(false);
  });

  it("gives the ladder its amber leader back", () => {
    const html = render(
      market("What will the Fed rate be at the end of 2026?", "politics", FED_RATE_ROWS),
    );
    expect(hasAmberLeader(html)).toBe(true);
  });

  // ── THE OTHER DIRECTION (gotcha #43) ──────────────────────────────────────
  // Every assertion above has a sibling proving the ship did not simply delete
  // the entity branch, which is the cheapest way to make the tests above pass.

  it("still draws avatars for a politics field of PEOPLE", () => {
    const html = render(
      market("Who will be the next president?", "politics", CANDIDATE_ROWS),
    );
    expect(drewEntityAvatars(html)).toBe(true);
  });

  it("still draws avatars for entities that BEGIN with a number", () => {
    // The regex the issue proposed (`^[<>≤≥]?\s*[0-9]`) strips all three of
    // these of their faces. The sibling test is what makes them safe.
    const html = render(
      market("Rap album of the year", "entertainment", [
        outcome(1, "50 Cent", 0.4),
        outcome(2, "21 Savage", 0.35),
        outcome(3, "3 Doors Down", 0.25),
      ]),
    );
    expect(drewEntityAvatars(html)).toBe(true);
  });

  it("leaves a sports market's ranks exactly as they were", () => {
    const html = render(
      market("Omega European Masters - Winner", "golf", [
        outcome(1, "Todd Clements", 0.38),
        outcome(2, "Marco Penge", 0.07),
      ]),
    );
    expect(renderedRankBadges(html)).toEqual(["1", "2"]);
  });

  it("leaves a MIXED market alone — the deliberate remainder", () => {
    // `#1 Paid App in the US Apple App Store`: one digit-bearing entity among
    // three plain ones. Flipping this column would take three correct avatars
    // away to fix nothing, so the all-or-nothing rule declines it.
    const html = render(
      market("#1 Paid App in the US Apple App Store", "tech", [
        outcome(1, "Shadowrocket", 0.4),
        outcome(2, "M8 Music Tracker", 0.3),
        outcome(3, "Procreate Pocket", 0.3),
      ]),
    );
    expect(drewEntityAvatars(html)).toBe(true);
  });
});

describe("#4416 — isNumericLadder, on the name sets production actually serves", () => {
  // Every array below is a real `array_agg(futures_outcomes.name)` read from
  // production on 2026-09-14 for an open non-sports market.
  const LADDERS: [string, string[]][] = [
    ["Fed rate (quantity/politics)", ["4.0%", "3.75%", "4.25%", "3.5%", "≥ 4.5%"]],
    ["unemployment (quantity/economics)", ["At least 50%", "At least 44%", "At least 56%"]],
    ["jobs (quantity/economics)", ["Above 250K", "Above 260K", "Above 280K"]],
    ["Miami low temp (quantity/weather)", ["78-79°F", "90°F or higher", "88-89°F", "86-87°F"]],
    ["Elon tweets (quantity/entertainment)", ["65-89", "165-189", "140-164", "<40"]],
    ["album sales (quantity/entertainment)", ["50-60k", "90k+", "70-80k", "60-70k"]],
    ["senators (quantity/politics)", ["54", "56", "55", "≤49", "53"]],
    ["house margin (field/politics)", ["Republicans, 21+ pts", "Republicans, 18+ pts"]],
    // Why the skeleton collapses whitespace. A venue that emits one rung with a
    // stray double space would otherwise hand us two different skeletons for one
    // ladder and the column would stay broken for that market alone. Unobserved
    // in the 900-market read, so this pins the clause rather than reports it.
    ["a rung with inconsistent internal spacing", ["Above  250K", "Above 260K"]],
    // Same reasoning for the case fold: `90K+` and `90k+` both occur in the live
    // data, just never yet inside one market. Pinned so the clause is guarded
    // rather than incidental.
    ["rungs whose unit differs only in case", ["Above 250K", "above 260k"]],
    ["soccer spread (field/other)", [
      "Persib Bandung wins by more than 1.5 goals",
      "Persib Bandung wins by more than 2.5 goals",
      "Persija wins by more than 1.5 goals",
      "Persija wins by more than 2.5 goals",
    ]],
  ];

  const NOT_LADDERS: [string, string[]][] = [
    ["a field of people", ["Donald Trump", "Kamala Harris", "Gavin Newsom"]],
    ["entities carrying digits", ["50 Cent", "21 Savage", "3 Doors Down"]],
    ["one digit-bearing app among three", [
      "Shadowrocket",
      "M8 Music Tracker",
      "Procreate Pocket",
      "AnkiMobile Flashcards",
    ]],
    // The all-or-nothing clause, stated as its own case: a REAL ladder pair
    // sitting beside a real entity. Drop the "every rung carries a number" test
    // and this set collides on `above k` and flips, taking Shadowrocket's face
    // away to renumber two rows. That is the mixed-market regression the
    // remainder is deliberately accepting, so it gets a guard of its own.
    ["a ladder pair beside an entity", ["Above 250K", "Shadowrocket", "Above 260K"]],
    ["a binary with a dated question", ["Yes", "No"]],
    ["a single rung on its own", ["Above 250K"]],
    ["dates that share no month", ["Before Jan 1, 2027", "Before Oct 1, 2026"]],
  ];

  it.each(LADDERS)("reads %s as a ladder", (_label, names) => {
    expect(isNumericLadder(names)).toBe(true);
  });

  it.each(NOT_LADDERS)("leaves %s alone", (_label, names) => {
    expect(isNumericLadder(names)).toBe(false);
  });

  it("needs a SIBLING, not just a digit — one numeric name is not a ladder", () => {
    // The clause that protects `50 Cent`. Without the shared-skeleton test this
    // returns true and a field of rappers loses its faces.
    expect(isNumericLadder(["50 Cent", "Drake"])).toBe(false);
    expect(isNumericLadder(["50 Cent", "60 Cent"])).toBe(true);
  });
});
