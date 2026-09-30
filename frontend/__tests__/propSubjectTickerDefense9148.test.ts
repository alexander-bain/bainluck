/**
 * #9148 — a team defense is named once, by its nickname.
 *
 * Mystery-shopped on production 2026-09-27 at 390px, `/events/14781702`
 * (Seattle Seahawks @ Washington Commanders). THE SCRIPT read:
 *
 *     SEA Seahawks D/ST's 10+ fantasy points opened at 17% — it's 46% now.
 *     WAS Commanders D/ST: 6+ fantasy points
 *
 * Kalshi's outcome names a defense `<ABBR> <Nickname> D/ST`, and #6210 (rightly)
 * made the outcome's subject the prop's subject — so the ticker came with it. The
 * team is named twice, and "WAS" is not the spelling the page uses anywhere else
 * (its margin maps say WSH).
 *
 * The rows below are the production payload's own strings
 * (`/api/events/14781702/game-markets`, 13:35Z), and the ten subjects are every
 * D/ST shape served across the day's five NFL events on `/api/feed?mode=sports`.
 */
import {
  parsePlayerName,
  propSubjectDisplay,
  groupPlayerProps,
  type PlayerPropRow,
} from "../lib/playerPropsGrouping";
import { divergenceSentence, selectDivergenceRows } from "../lib/propDivergence";

const HOME = "Washington Commanders";
const AWAY = "Seattle Seahawks";

const PAYLOAD: PlayerPropRow[] = [
  {
    market_name: "Seattle vs Washington: Fantasy Points",
    outcome_name: "Jason Myers: Over 8",
    threshold: 8.0,
    over_probability: 0.53,
    pregame_mark: 0.385,
    source: "kalshi",
    movement: 0.145,
    player_team: "away",
  },
  {
    market_name: "Seattle vs Washington: Fantasy Points",
    outcome_name: "SEA Seahawks D/ST: Over 9.2",
    threshold: 9.2,
    over_probability: 0.455,
    pregame_mark: 0.17,
    source: "kalshi",
    movement: 0.285,
  },
  {
    market_name: "Seattle vs Washington: Fantasy Points",
    outcome_name: "WAS Commanders D/ST: Over 5.7",
    threshold: 5.7,
    over_probability: 0.355,
    pregame_mark: 0.17,
    source: "kalshi",
    movement: 0.185,
  },
  {
    market_name: "Seattle vs Washington: Touchdowns",
    outcome_name: "SEA Seahawks D/ST: 1+",
    threshold: 1.0,
    over_probability: 0.145,
    pregame_mark: 0.1,
    source: "kalshi",
    movement: 0.045,
  },
  {
    market_name: "Seattle vs Washington: Touchdowns",
    outcome_name: "WAS Commanders D/ST: 1+",
    threshold: 1.0,
    over_probability: 0.1,
    pregame_mark: 0.08,
    source: "kalshi",
    movement: 0.02,
  },
] as unknown as PlayerPropRow[];

describe("#9148 the ticker prefix of a team defense is dropped", () => {
  it.each([
    ["CAR Panthers D/ST", "Panthers D/ST"],
    ["CLE Browns D/ST", "Browns D/ST"],
    ["DET Lions D/ST", "Lions D/ST"],
    ["HOU Texans D/ST", "Texans D/ST"],
    ["IND Colts D/ST", "Colts D/ST"],
    ["KC Chiefs D/ST", "Chiefs D/ST"],
    ["MIA Dolphins D/ST", "Dolphins D/ST"],
    ["NY Jets D/ST", "Jets D/ST"],
    ["SEA Seahawks D/ST", "Seahawks D/ST"],
    ["WAS Commanders D/ST", "Commanders D/ST"],
  ])("%s → %s", (served, shown) => {
    expect(propSubjectDisplay(served)).toBe(shown);
  });

  it("a shared city stays two units", () => {
    expect(propSubjectDisplay("NY Jets D/ST")).not.toBe(propSubjectDisplay("NY Giants D/ST"));
    expect(propSubjectDisplay("LA Rams D/ST")).not.toBe(propSubjectDisplay("LA Chargers D/ST"));
  });

  // Controls: the shape is exact, so nothing that is not a ticker-prefixed
  // defense moves — including players whose first name is initials.
  it.each([
    "Jason Myers",
    "AJ Brown",
    "DJ Moore",
    "CJ Stroud",
    "Kenneth Walker III",
    "Denver",
    "Kansas City",
    "Chiefs D/ST",
    "KC D/ST",
    "D/ST",
  ])("%s is unchanged", (subject) => {
    expect(propSubjectDisplay(subject)).toBe(subject);
  });

  it("parsePlayerName names the defense once", () => {
    const parsed = parsePlayerName(
      "Seattle vs Washington: Fantasy Points",
      "SEA Seahawks D/ST: Over 9.2",
    );
    expect(parsed?.player).toBe("Seahawks D/ST");
    expect(parsed?.stat).toBe("Fantasy Points");
  });
});

describe("#9148 what the page renders from the production rows", () => {
  it("the prop cards are titled by nickname and keep their side", () => {
    const result = groupPlayerProps({ playerProps: PAYLOAD, homeTeam: HOME, awayTeam: AWAY });
    const byName = new Map(result.players.map((p) => [p.name, p]));
    expect([...byName.keys()].sort()).toEqual(["Commanders D/ST", "Jason Myers", "Seahawks D/ST"]);
    // The side came from the nickname before the fix and still does: card
    // colour does not move.
    expect(byName.get("Seahawks D/ST")?.team).toBe("away");
    expect(byName.get("Commanders D/ST")?.team).toBe("home");
    for (const name of byName.keys()) {
      expect(name).not.toMatch(/^(SEA|WAS) /);
    }
  });

  it("THE SCRIPT's rows and sentence say 'Seahawks D/ST', never 'SEA Seahawks'", () => {
    const { rows } = selectDivergenceRows({ playerProps: PAYLOAD, status: "scheduled" });
    const dst = rows.find((r) => r.stat === "Fantasy Points" && r.threshold === 9.2);
    expect(dst).toBeDefined();
    expect(dst!.player).toBe("Seahawks D/ST");
    expect(dst!.label.startsWith("Seahawks D/ST: ")).toBe(true);
    const sentence = divergenceSentence(
      dst!.player,
      dst!.label,
      dst!.pregameMark,
      dst!.current,
      false,
      null,
      dst!.matchup,
    );
    expect(sentence.startsWith("Seahawks D/ST's ")).toBe(true);
    for (const r of rows) {
      expect(r.label).not.toMatch(/\b(SEA|WAS) (Seahawks|Commanders)\b/);
    }
  });
});
