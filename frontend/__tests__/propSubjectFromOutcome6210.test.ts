/**
 * #6210 — a prop row's SUBJECT is whoever the outcome names.
 *
 * Mystery-shopped on production 2026-09-14 at 390px, `/events/14638896`
 * (Denver Broncos @ Kansas City Chiefs). THE SCRIPT read:
 *
 *     Team's 4+ touchdowns opened at 40% — it's 9% now.
 *     Team's 4+ sacks   opened at 66% — it's 37% now.
 *     Fantasy's 9+ points opened at 50% — it's 26% now.
 *
 * beside honest rows reading "Walker's 15+ receiving yards". The possessive was
 * being applied to a market QUALIFIER: `parsePlayerName` stripped a known stat
 * off the end of the market's after-colon phrase and kept the leftover as the
 * person. On that page it invented 131 of 374 rows and 19 of 46 cards, and
 * "Team's 4+ touchdowns" on a two-team page cannot even say which team — while
 * `outcome_name` said "Denver" the whole time.
 *
 * These guards pin the RULE (the subject is read, never derived) rather than the
 * three spellings that were sighted, because "Team Touchdowns", "Fantasy Points",
 * "Team Corners" and "Player Longest Rush" are one shape with many spellings and
 * a vocabulary fix re-opens on the next venue phrase. `aNovelQualifierNeverSeen`
 * below is the test a blocklist fails.
 */
import {
  parsePlayerName,
  groupPlayerProps,
  type PlayerPropRow,
} from "../lib/playerPropsGrouping";

const HOME = "Kansas City Chiefs";
const AWAY = "Denver Broncos";

function row(
  market: string,
  outcome: string,
  extra: Partial<PlayerPropRow> = {},
): PlayerPropRow {
  return {
    market_name: market,
    outcome_name: outcome,
    threshold: 4,
    over_probability: 0.4,
    source: "kalshi",
    ...extra,
  } as PlayerPropRow;
}

describe("#6210 the subject is read from the outcome, never derived from the market", () => {
  // The three rows a reader actually saw, verbatim from the payload.
  it.each([
    ["Denver vs Kansas City: Team Touchdowns", "Denver: 4+", "Denver", "Team"],
    ["Denver vs Kansas City: Team Sacks", "Denver: 4+", "Denver", "Team"],
    [
      "Denver vs Kansas City: Fantasy Points",
      "KC Chiefs D/ST: Over 8.5 fantasy points",
      "KC Chiefs D/ST",
      "Fantasy",
    ],
  ])("%s | %s names %s", (market, outcome, subject, invented) => {
    const parsed = parsePlayerName(market, outcome);
    expect(parsed?.player).toBe(subject);
    expect(parsed?.player).not.toBe(invented);
  });

  /**
   * Every fabricated subject MEASURED on production, across 7,208 distinct
   * (market_name, outcome_name) pairs from 15 live events in NFL, NCAAF, MLB,
   * NBA, soccer and NHL. Each one is a market qualifier standing where a person
   * belongs; each must now resolve to the subject the outcome states.
   */
  it.each([
    ["Denver vs Kansas City: Team Total Yards", "Kansas City: 250+", "Kansas City"],
    ["Oklahoma vs Michigan: Team Rushing Touchdowns", "Michigan: 1+", "Michigan"],
    ["Oklahoma vs Michigan: Team Receiving Yards", "Oklahoma: 175+", "Oklahoma"],
    ["Denver vs Kansas City: Team Field Goals", "Denver: 1+", "Denver"],
    ["Denver vs Kansas City: Passing Touchdowns", "Patrick Mahomes: 1+", "Patrick Mahomes"],
    ["Denver vs Kansas City: Passing Interceptions", "Bo Nix: 1+", "Bo Nix"],
    [
      "Denver vs Kansas City: Rushing + Receiving Yards",
      "Kenneth Walker III: 80+",
      "Kenneth Walker III",
    ],
    ["Denver vs Kansas City: Passing Attempts", "Patrick Mahomes: 28+", "Patrick Mahomes"],
    ["Denver vs Kansas City: Player Longest Rush", "Bo Nix: over 9.5 yards", "Bo Nix"],
    ["Pittsburgh vs Chicago C: Outs Recorded", "Clay Holmes: 17+", "Clay Holmes"],
  ])("%s | %s", (market, outcome, subject) => {
    expect(parsePlayerName(market, outcome)?.player).toBe(subject);
  });

  /**
   * THE TEST A BLOCKLIST FAILS. Clearly-labelled SYNTHETIC: no production row
   * carries this phrase. A fix keyed on the words "Team" or "Fantasy" passes
   * every case above and fails this one, which is the whole point of widening
   * the rule instead of naming the vocabulary.
   */
  it("aNovelQualifierNeverSeen — an unknown market phrase still yields the outcome's subject", () => {
    const parsed = parsePlayerName(
      "Denver vs Kansas City: Squad Blorptastic Yards", // SYNTHETIC
      "Kansas City: 275+",
    );
    expect(parsed?.player).toBe("Kansas City");
    expect(parsed?.stat).toBe("Squad Blorptastic Yards");
  });

  it("the subject is never a substring left over after stripping a stat", () => {
    // "Team Field Goals" used to strip "Goals" and keep "Team Field".
    expect(parsePlayerName("A vs B: Team Field Goals", "A: 1+")?.player).toBe("A");
    // "Rushing + Receiving Yards" used to strip "Receiving Yards" -> "Rushing +".
    expect(
      parsePlayerName("A vs B: Rushing + Receiving Yards", "Someone: 80+")?.player,
    ).toBe("Someone");
  });
});

describe("#6210 the shapes that already parsed keep parsing exactly as they did", () => {
  it("Kalshi <matchup>: <known stat> / <player>: <line> is unchanged", () => {
    const parsed = parsePlayerName(
      "Denver vs Kansas City: Receiving Yards",
      "Kenneth Walker III: 15+",
    );
    expect(parsed).toEqual({
      player: "Kenneth Walker III",
      stat: "Receiving Yards",
      team: "Denver vs Kansas City",
      identified: true,
    });
  });

  it("UX-P097 Polymarket <Player>: <Stat> O/U <line> is unchanged — subject BEFORE the colon", () => {
    const parsed = parsePlayerName("Bubba Chandler: Strikeouts O/U 4.5", "Over");
    expect(parsed).toEqual({
      player: "Bubba Chandler",
      stat: "Strikeouts",
      team: "",
      identified: true,
    });
  });

  it("#1639 matchup rows (no colon, no stat) still read the player out of the outcome", () => {
    const parsed = parsePlayerName(
      "Tampa Bay Rays vs. Seattle Mariners - Player Props",
      "Junior Caminero: Home Runs O/U 0.5",
    );
    expect(parsed).toEqual({
      player: "Junior Caminero",
      stat: "Home Runs",
      team: "",
      identified: true,
    });
  });

  /**
   * UX-P044 / #1642's poisoning refusal, which this change must not weaken: a
   * matchup market whose outcome `parsePropLabel` cannot read still falls back
   * to the whole market name AND still reports `identified: false`, so the
   * caller refuses the group's verdict rather than publishing a grade against a
   * bucket that 17 players share. The colon in the outcome must NOT be enough
   * on its own to claim a subject when the market names no stat at all.
   */
  it("an unreadable matchup row still refuses to claim it identified anyone", () => {
    const parsed = parsePlayerName(
      "Tampa Bay Rays vs. Seattle Mariners - Player Props",
      "Junior Caminero: Over 0.5 Home Runs",
    );
    expect(parsed?.player).toBe(
      "Tampa Bay Rays vs. Seattle Mariners - Player Props",
    );
    expect(parsed?.identified).toBe(false);
  });

  it("a market with no colon and an unparseable outcome is still refused", () => {
    expect(parsePlayerName("", "")).toBeNull();
  });
});

describe("#6210 distinct markets stop collapsing into one ladder", () => {
  /**
   * The suffix strip also merged markets: "Team Total Touchdowns", "Team Rushing
   * Touchdowns" and "Team Receiving Touchdowns" all reduced to the stat
   * "Touchdowns", so three different questions about one team stacked into a
   * single ladder. The stat is now the market's own phrase.
   */
  it("Team Total / Rushing / Receiving Touchdowns are three stats, not one", () => {
    const stats = [
      "Team Total Touchdowns",
      "Team Rushing Touchdowns",
      "Team Receiving Touchdowns",
    ].map((m) => parsePlayerName(`Oklahoma vs Michigan: ${m}`, "Michigan: 1+")?.stat);
    expect(new Set(stats).size).toBe(3);
    expect(stats).toEqual([
      "Team Total Touchdowns",
      "Team Rushing Touchdowns",
      "Team Receiving Touchdowns",
    ]);
  });

  it("a QB's passing interceptions no longer share a bucket with a defense's", () => {
    expect(
      parsePlayerName("A vs B: Passing Interceptions", "Bo Nix: 1+")?.stat,
    ).toBe("Passing Interceptions");
    expect(parsePlayerName("A vs B: Interceptions", "Bo Nix: 1+")?.stat).toBe(
      "Interceptions",
    );
  });
});

describe("#6210 a team card carries its OWN side, not the matchup's first mention", () => {
  /**
   * `detectTeam("Denver vs Kansas City")` answers "away" for BOTH teams' rows by
   * first-mention ordering. Once these cards stopped all being called "Team",
   * they would all still have worn the visitor's colour — a card reading
   * "Kansas City" in Denver's colour on a Denver-at-Kansas-City page.
   */
  it("Kansas City is home and Denver is away on Denver @ Kansas City", () => {
    const result = groupPlayerProps({
      playerProps: [
        row("Denver vs Kansas City: Team Sacks", "Kansas City: 2+"),
        row("Denver vs Kansas City: Team Sacks", "Denver: 2+"),
      ],
      homeTeam: HOME,
      awayTeam: AWAY,
    });
    const sides = new Map(result.players.map((p) => [p.name, p.team]));
    expect(sides.get("Kansas City")).toBe("home");
    expect(sides.get("Denver")).toBe("away");
  });

  it("a matchup taken from the MARKET name never names a side", () => {
    // "Set 1 Winner: Bosio vs Cabrera" | "Yes" parses to the matchup, not a
    // subject. Handing that to detectTeam would pick a side for a card naming
    // both players. It must stay whatever the market context said.
    const result = groupPlayerProps({
      playerProps: [row("Set 1 Winner: Bosio vs Cabrera", "Yes")],
      homeTeam: "Bosio",
      awayTeam: "Cabrera",
    });
    const card = result.players.find((p) => p.name === "Bosio vs Cabrera");
    expect(card?.team).toBe("unknown");
  });

  it("a player's own name still takes the previous path and keeps its colour", () => {
    const result = groupPlayerProps({
      playerProps: [row("Denver vs Kansas City: Receiving Yards", "Travis Kelce: 40+")],
      homeTeam: HOME,
      awayTeam: AWAY,
    });
    // "Travis Kelce" matches no team word, so the matchup fallback decides — the
    // behaviour this change deliberately leaves alone.
    expect(result.players.find((p) => p.name === "Travis Kelce")?.team).toBe("away");
  });
});

describe("#6210 the card list a reader sees", () => {
  it("names the two teams and the quarterback instead of Team, Fantasy and Passing", () => {
    const result = groupPlayerProps({
      playerProps: [
        row("Denver vs Kansas City: Team Touchdowns", "Kansas City: 2+"),
        row("Denver vs Kansas City: Team Sacks", "Denver: 2+"),
        row("Denver vs Kansas City: Passing Touchdowns", "Patrick Mahomes: 1+"),
        row("Denver vs Kansas City: Fantasy Points", "KC Chiefs D/ST: Over 8.5 fantasy points"),
      ],
      homeTeam: HOME,
      awayTeam: AWAY,
    });
    const names = result.players.map((p) => p.name).sort();
    expect(names).toEqual([
      "Denver",
      "KC Chiefs D/ST",
      "Kansas City",
      "Patrick Mahomes",
    ]);
    for (const invented of ["Team", "Fantasy", "Passing", "Team Field", "Rushing +"]) {
      expect(names).not.toContain(invented);
    }
  });
});
