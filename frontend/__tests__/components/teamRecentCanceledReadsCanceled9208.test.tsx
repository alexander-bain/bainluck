/**
 * #9208 — the Yankees page's Recent Results said "No result reported" for a game ESPN called off.
 *
 * Production, 390px, 2026-10-01 10:38Z, `/sport/baseball/mlb/team/new-york-yankees-mlb`
 * (`artifacts/ux-1001-search/nyy1.png`, ux worktree):
 *
 *     vs Baltimore Orioles                                 Sep 27
 *     No result reported
 *
 * while the search card for the same row (15319530) read "Canceled · Sep 27" and so did its
 * own page. The brief carried no period. The fixture is the served `recent_events` brief
 * verbatim, plus the `stoppage` key the backend half of this change adds.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { RecentGameCard } from "@/components/TeamGameCards";
import type { TeamGameBrief } from "@/lib/api";

const SPECIMEN = {
  "id": 15319530,
  "home_team": "New York Yankees",
  "away_team": "Baltimore Orioles",
  "home_score": null,
  "away_score": null,
  "status": "suspended",
  "commence_time": "2026-09-27T17:05:00+00:00",
  "start_is_tbd": false,
  "sport_key": "baseball_mlb",
  "is_home": true,
  "opponent": "Baltimore Orioles",
  "win_probability": 0.522,
  "pregame_win_probability": 0.522,
  "completed_at": null,
  "stoppage": "Canceled"
} as TeamGameBrief;

function text(game: TeamGameBrief): string {
  return renderToStaticMarkup(<RecentGameCard game={game} />)
    .replace(/<!-- -->/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
}

describe("#9208 — a called-off game on the team page says so", () => {
  it("the specimen brief is the served suspended row with no score", () => {
    expect(SPECIMEN.id).toBe(15319530);
    expect(SPECIMEN.status).toBe("suspended");
    expect(SPECIMEN.home_score).toBeNull();
  });

  it("reads 'Canceled', not 'No result reported'", () => {
    const t = text(SPECIMEN);
    expect(t).toContain("Canceled");
    expect(t).not.toContain("No result reported");
    expect(t).toContain("vs Baltimore Orioles");
  });

  it("Postponed reads Postponed; ESPN's 0-0 filler under a stoppage word is not a last score", () => {
    const t = text({ ...SPECIMEN, stoppage: "Postponed", home_score: 0, away_score: 0 });
    expect(t).toContain("Postponed");
    expect(t).not.toContain("last score");
  });

  it("a game stopped mid-play keeps its last score, team first", () => {
    const t = text({ ...SPECIMEN, stoppage: "Postponed", home_score: 3, away_score: 1 });
    expect(t).toContain("Postponed · last score 3-1");
    const away = text({
      ...SPECIMEN,
      is_home: false,
      stoppage: "Postponed",
      home_score: 3,
      away_score: 1,
    });
    expect(away).toContain("Postponed · last score 1-3");
  });

  it("control: a suspended row with no stoppage word keeps the honest sentence", () => {
    const t = text({ ...SPECIMEN, stoppage: null });
    expect(t).toContain("No result reported");
    expect(t).not.toContain("Canceled");
  });

  it("control: a word outside the allowlist is never printed", () => {
    const t = text({ ...SPECIMEN, stoppage: "Top 7th" });
    expect(t).toContain("No result reported");
    expect(t).not.toContain("Top 7th");
  });
});
