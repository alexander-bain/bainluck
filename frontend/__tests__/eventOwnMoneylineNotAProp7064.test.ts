/**
 * #7064 — the game's own moneyline stops being served into the props body.
 *
 * The defect as a reader met it on `/events/15314172`: THE DIVERGENCE opened with the game itself,
 * listed twice under two venues' spellings, each disagreeing with the hero and with the other
 * (56 + 46 = 102%). The fixtures below are the production payload's real shapes, verbatim.
 *
 * THE CONTROLS ARE THE POINT OF THIS FILE. A filter is only as good as what it refuses to delete,
 * so most of what follows asserts rows that must SURVIVE. In particular:
 *   - the PREMISE control proves the unfiltered payload really does carry the offender, so a green
 *     run cannot mean "the fixture had nothing to find";
 *   - the SCOPE controls pin the near-misses a blunter rule would eat (a race market, a team-named
 *     outcome on a non-matchup market, another game's matchup);
 *   - the WIRING control fails if the page stops calling the filter, which is the one mutant a
 *     pure-function battery structurally cannot see.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  isEventOwnMoneylineMarket,
  labelNamesSide,
  withoutEventOwnMoneyline,
} from "@/lib/eventOwnMoneyline";

const HOME = "Tampa Bay Rays";
const AWAY = "Boston Red Sox";

/** The two offenders, exactly as the two venues spelled them on 2026-09-18. */
const KALSHI_NAME = "Boston vs Tampa Bay";
const POLYMARKET_NAME = "Boston Red Sox vs. Tampa Bay Rays";

function payload(over: Partial<Parameters<typeof withoutEventOwnMoneyline>[0]> = {}) {
  return {
    home_team: HOME,
    away_team: AWAY,
    player_props: [
      { market_name: "Ranger Suarez: Strikeouts O/U 4.5" },
      { market_name: KALSHI_NAME },
      { market_name: "Trevor Story: Home Runs O/U 0.5" },
    ],
    props_script: [
      { key: "Ranger Suarez: Strikeouts O/U 4.5|Over" },
      { key: `${KALSHI_NAME}|Boston` },
      { key: `${KALSHI_NAME}|Tampa Bay` },
    ],
    ...over,
  };
}

describe("#7064 labelNamesSide — the short form a venue uses for a club", () => {
  it.each([
    ["Boston", "Boston Red Sox"],
    ["Tampa Bay", "Tampa Bay Rays"],
    ["Boston Red Sox", "Boston Red Sox"],
    ["boston red sox", "Boston Red Sox"],
    ["Red Sox", "Boston Red Sox"],
  ])("%s names %s", (label, team) => {
    expect(labelNamesSide(label, team)).toBe(true);
  });

  it.each([
    ["Bo", "Boston Red Sox"], // a bare prefix is not a word — the space in the affix test
    ["Boston Bruins", "Boston Red Sox"],
    ["", "Boston Red Sox"],
    ["Boston", ""],
    [null, "Boston Red Sox"],
    ["Boston", undefined],
  ])("%s does NOT name %s", (label, team) => {
    expect(labelNamesSide(label as string, team as string)).toBe(false);
  });
});

describe("#7064 isEventOwnMoneylineMarket — keyed on the matchup, never on the wording", () => {
  it("catches BOTH venues' spellings of the same question", () => {
    // This is the whole reason the rule is shaped this way: these two strings differ only in how
    // each venue spells the clubs, and they produced two rows for one question.
    expect(isEventOwnMoneylineMarket(KALSHI_NAME, HOME, AWAY)).toBe(true);
    expect(isEventOwnMoneylineMarket(POLYMARKET_NAME, HOME, AWAY)).toBe(true);
  });

  it.each(["Boston at Tampa Bay", "Boston @ Tampa Bay", "Boston v Tampa Bay", "Boston VS. Tampa Bay"])(
    "catches the separator %s",
    (name) => {
      expect(isEventOwnMoneylineMarket(name, HOME, AWAY)).toBe(true);
    },
  );

  it("catches it written home-first as well as away-first", () => {
    expect(isEventOwnMoneylineMarket("Tampa Bay vs Boston", HOME, AWAY)).toBe(true);
  });

  // ---- SCOPE: every one of these must survive ----
  it.each([
    ["a qualified market on the same fixture", "Boston vs Tampa Bay: Race to 14 Points"],
    ["a team stat market", "Boston vs Tampa Bay: Total Runs"],
    ["an ordinary player prop", "Ranger Suarez: Strikeouts O/U 4.5"],
    ["another game's matchup", "New York vs Baltimore"],
    ["one side named twice", "Boston vs Boston"],
    ["a non-matchup market naming a side", "Which team scores first?"],
    ["empty", ""],
  ])("does NOT claim %s", (_label, name) => {
    expect(isEventOwnMoneylineMarket(name, HOME, AWAY)).toBe(false);
  });

  it("refuses when the event does not name two sides", () => {
    expect(isEventOwnMoneylineMarket(KALSHI_NAME, "", AWAY)).toBe(false);
    expect(isEventOwnMoneylineMarket(KALSHI_NAME, HOME, "")).toBe(false);
  });
});

describe("#7064 withoutEventOwnMoneyline — both arrays, or the fix reaches half the page", () => {
  it("PREMISE: the unfiltered payload really does carry the offender", () => {
    // Without this, every assertion below could pass on a fixture that never had the defect.
    const served = payload();
    expect(served.player_props.map((p) => p.market_name)).toContain(KALSHI_NAME);
    expect(served.props_script.some((m) => String(m.key).startsWith(KALSHI_NAME))).toBe(true);
  });

  it("drops the moneyline from player_props and keeps every real prop", () => {
    const out = withoutEventOwnMoneyline(payload());
    expect(out.player_props.map((p) => p.market_name)).toEqual([
      "Ranger Suarez: Strikeouts O/U 4.5",
      "Trevor Story: Home Runs O/U 0.5",
    ]);
  });

  it("drops it from props_script too — THE SCRIPT and WHAT HIT read that array, not player_props", () => {
    const out = withoutEventOwnMoneyline(payload());
    expect(out.props_script).toEqual([{ key: "Ranger Suarez: Strikeouts O/U 4.5|Over" }]);
  });

  it("drops the SAME question served once per venue, which is what the reader actually saw", () => {
    const out = withoutEventOwnMoneyline(
      payload({
        player_props: [
          { market_name: KALSHI_NAME },
          { market_name: POLYMARKET_NAME },
          { market_name: "Trevor Story: Home Runs O/U 0.5" },
        ],
        props_script: [],
      }),
    );
    expect(out.player_props).toEqual([{ market_name: "Trevor Story: Home Runs O/U 0.5" }]);
  });

  it("takes soccer's Draw leg with its market, instead of orphaning it", () => {
    // Row-level suppression would leave "Draw" behind answering a question with no siblings.
    const out = withoutEventOwnMoneyline({
      home_team: "Arsenal",
      away_team: "Manchester City",
      player_props: [
        { market_name: "Manchester City vs Arsenal" },
        { market_name: "Erling Haaland: Goals O/U 0.5" },
      ],
      props_script: [
        { key: "Manchester City vs Arsenal|Manchester City" },
        { key: "Manchester City vs Arsenal|Draw" },
        { key: "Manchester City vs Arsenal|Arsenal" },
        { key: "Erling Haaland: Goals O/U 0.5|Over" },
      ],
    });
    expect(out.player_props).toEqual([{ market_name: "Erling Haaland: Goals O/U 0.5" }]);
    expect(out.props_script).toEqual([{ key: "Erling Haaland: Goals O/U 0.5|Over" }]);
  });

  it("keeps a props_script mark whose key carries no family — the concept page's numeric key", () => {
    const out = withoutEventOwnMoneyline(
      payload({ player_props: [], props_script: [{ key: 60850613 }] }),
    );
    expect(out.props_script).toEqual([{ key: 60850613 }]);
  });

  it("returns the payload BY REFERENCE when it drops nothing", () => {
    // The page passes this object as `resetKey` to its section error boundaries; a fresh object
    // every render would reset them continuously.
    const served = payload({
      player_props: [{ market_name: "Ranger Suarez: Strikeouts O/U 4.5" }],
      props_script: [{ key: "Ranger Suarez: Strikeouts O/U 4.5|Over" }],
    });
    expect(withoutEventOwnMoneyline(served)).toBe(served);
  });

  it("survives a payload with no props_script at all", () => {
    const served = { home_team: HOME, away_team: AWAY, player_props: [{ market_name: KALSHI_NAME }] };
    const out = withoutEventOwnMoneyline(served);
    expect(out.player_props).toEqual([]);
    expect("props_script" in out).toBe(false);
  });
});

describe("#7064 the call site — a filter nothing calls is not a fix", () => {
  const source = readFileSync(
    join(process.cwd(), "app", "events", "[id]", "page.tsx"),
    "utf8",
  );

  it("the event page imports the filter", () => {
    expect(source).toMatch(/import\s*\{\s*withoutEventOwnMoneyline\s*\}\s*from\s*"@\/lib\/eventOwnMoneyline"/);
  });

  it("the event page runs the served payload through it before anything reads gameMarkets", () => {
    // The served SWR result must not be called `gameMarkets` — the 30-odd downstream readers bind
    // to that name, so the filtered value is the one that has to carry it.
    expect(source).toMatch(/const\s*\{\s*data:\s*servedGameMarkets\s*\}\s*=\s*useSWR/);
    expect(source).toMatch(/const\s+gameMarkets\s*=\s*useMemo\(/);
    expect(source).toMatch(/withoutEventOwnMoneyline\(servedGameMarkets\)/);
  });
});

describe("#7064 the REAL production payload, driven through the real filter", () => {
  // Captured verbatim from GET /api/events/15314172/game-markets on 2026-09-19 — the very event in
  // the issue. A hand-written fixture proves the predicate does what I think it does; this proves
  // it does it to the rows production actually serves.
  const served = require("./fixtures/gameMarkets15314172-7064.json") as {
    home_team: string;
    away_team: string;
    player_props: { market_name: string }[];
    props_script: { key: string }[];
  };

  it("BEFORE: the served payload really carries the offender in both arrays", () => {
    expect(served.player_props).toHaveLength(66);
    expect(served.player_props.filter((p) => p.market_name === "Boston vs Tampa Bay")).toHaveLength(2);
    expect(served.props_script.filter((m) => m.key.startsWith("Boston vs Tampa Bay|"))).toHaveLength(2);
  });

  it("AFTER: exactly the two moneyline rows leave each array, and 64 real props stay", () => {
    const out = withoutEventOwnMoneyline(served);
    expect(out.player_props).toHaveLength(64);
    expect(out.props_script).toHaveLength(64);
    expect(out.player_props.some((p) => p.market_name === "Boston vs Tampa Bay")).toBe(false);
    expect(out.props_script!.some((m) => String(m.key).startsWith("Boston vs Tampa Bay|"))).toBe(false);
  });

  it("AFTER: every OTHER market on the real payload survives, name for name", () => {
    // The blunt-instrument check. A filter that deleted the offender and something else with it
    // would pass both assertions above.
    const before = served.player_props.map((p) => p.market_name).filter((n) => n !== "Boston vs Tampa Bay");
    const after = withoutEventOwnMoneyline(served).player_props.map((p) => p.market_name);
    expect(after).toEqual(before);
  });
});
