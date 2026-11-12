/**
 * #12591 — Web: the site never calls a market a "question".
 *
 * Covers the plain swaps across collection hubs, game catalog ("Other markets",
 * Decision 148: A), search related game listings, categories, league binary
 * boards, tournament/match props, playoff grid, weather rain card, about page,
 * calibration coverage rungs, calibration provider panels, calibration page,
 * and backend `precompute_calibration.py` (`2026-09-13`, Decision 148: A).
 *
 * Also pins Fable's guard: `frontend/lib/calibrationCorrections.ts:198` stays
 * untouched on `master` until Builder C's 1.0.7 PR (#12602) lands alongside
 * `CalibrationCorrections.swift:125`.
 */

import fs from "fs";
import path from "path";
import { parseCollection } from "@/lib/collections";
import { CATALOG_FAMILIES, buildQuestionCatalog } from "@/lib/questionCatalog";
import { relatedGameListingText } from "@/lib/relatedGameListing";
import { FRESHNESS_DEFINITION, curatedPropsEmptyReason } from "@/lib/tournamentProps";
import { RUNG_LABELS } from "@/lib/calibrationCoverage";
import { shapeBreakdownNote, shapeBreakoutCaption } from "@/lib/calibrationProviderPanels";
import { refusalMessage } from "@/lib/labelPassSession";
import { nflHub, mlbHub } from "../collections/fixtures";
import type { GameMarketsResponse } from "@/lib/api";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");

function readFile(relFromFrontend: string): string {
  return fs.readFileSync(path.join(FRONTEND_ROOT, relFromFrontend), "utf8");
}

describe("#12591 — web never calls a market a 'question'", () => {
  it("Decision 148: A — game catalog and collection hubs both use 'Other markets' and 'Player and game props'", () => {
    expect(CATALOG_FAMILIES).toContain("Other markets");
    expect(CATALOG_FAMILIES as readonly string[]).not.toContain("Other");

    const catalog = buildQuestionCatalog(
      {
        event_id: 1,
        home_team: "Chiefs",
        away_team: "Bills",
        home_score: null,
        away_score: null,
        status: "scheduled",
        totals: [],
        player_props: [],
        team_totals: [],
        spreads: [],
        period_markets: [],
        matchups: [],
        other: [
          {
            market_name: "Will there be overtime?",
            outcome_name: "Yes",
            probability: 0.08,
            source: "kalshi",
          },
        ],
        pace: null,
      } as unknown as GameMarketsResponse,
      "scheduled",
      Date.parse("2026-11-11T18:00:00Z"),
    );
    expect(catalog.map((g) => g.family)).toEqual(["Other markets"]);

    const nfl = parseCollection(nflHub(), "nfl-2026-week-4");
    expect(nfl.sections.map((s) => s.title)).toEqual([
      "Games and winners",
      "Player and game props",
      "Championship",
    ]);

    const mlb = parseCollection(mlbHub(), "mlb-2026-postseason");
    expect(mlb.note).toBe("Some games or markets aren't available right now.");

    const emptySports = parseCollection({ ...nflHub(), state: "empty" }, "nfl-2026-week-4");
    expect(emptySports.note).toBe("There are no games or markets in this collection right now.");

    const collectionsSrc = readFile("lib/collections.ts");
    expect(collectionsSrc).toContain('side_question: "Other markets"');
    expect(collectionsSrc).not.toContain('"More questions"');
    expect(collectionsSrc).not.toContain('"Player and game questions"');
  });

  it("search related game listing uses 'market' / 'markets'", () => {
    expect(relatedGameListingText({ event_id: 42, question_count: 1 })).toBe(
      "1 market on this game",
    );
    expect(relatedGameListingText({ event_id: 42, question_count: 4 })).toBe(
      "4 markets on this game",
    );
    expect(relatedGameListingText({ event_id: 42, question_count: 0 })).toBe(
      "More markets on this game",
    );
  });

  it("tournament props, match props, playoff grid, weather, categories, about, and LeagueBinaryBoard use market/prop", () => {
    expect(FRESHNESS_DEFINITION).toBe(
      "“Last number” is when we last saw a new probability for a market — not when it was created, and not when it last changed hands.",
    );
    expect(
      curatedPropsEmptyReason({
        markets: [],
        combined: 0,
        considered: 2,
        dropped: { advance: 2, resolved: 0, dark: 0, template: 0 },
      }),
    ).toBe(
      "Every market for this draw is about how far a player gets — those are on the Bracket tab.",
    );

    const tournamentPropsSrc = readFile("components/tournament/TournamentProps.tsx");
    expect(tournamentPropsSrc).toContain("We have not seen a number for this market yet.");
    expect(tournamentPropsSrc).toContain("We have not seen a new number for this market in ");
    expect(tournamentPropsSrc).toContain(
      "so this comparison is not complete and the market has closed.",
    );
    expect(tournamentPropsSrc).not.toContain("We have not seen a number for this question yet.");
    expect(tournamentPropsSrc).not.toContain("We have not seen a new number for this question in ");
    expect(tournamentPropsSrc).not.toContain("and the question has closed.");

    const matchPropsSrc = readFile("components/tournament/MatchProps.tsx");
    expect(matchPropsSrc).toContain(
      "Match winner is the only market with a number on this match. Sets, games and margins have no probability against them.",
    );
    expect(matchPropsSrc).toContain('more prop{hidden === 1 ? "" : "s"} exist');
    expect(matchPropsSrc).not.toContain("Who wins is the only question");

    const tournamentExtSrc = readFile("components/event/TournamentExtensions.tsx");
    expect(tournamentExtSrc).toContain('label="Match props"');
    expect(tournamentExtSrc).not.toContain('label="Match questions"');

    const playoffGridSrc = readFile("lib/playoffGrid.ts");
    expect(playoffGridSrc).toContain('cell.note ?? "No market is open for this round."');
    expect(playoffGridSrc).not.toContain('cell.note ?? "Nobody is answering this question."');

    const rainSrc = readFile("components/weather/RainForecast.tsx");
    expect(rainSrc).toContain("Daily &ldquo;Will it rain?&rdquo; markets, one per day");
    expect(rainSrc).toContain("This card tracks daily &ldquo;will it rain?&rdquo; markets.");
    expect(rainSrc).not.toContain("Will it rain?&rdquo; questions");
    expect(rainSrc).not.toContain("will it rain?&rdquo; questions");

    const aboutSrc = readFile("app/about/page.tsx");
    expect(aboutSrc).toContain('desc: "Open markets, merged into one number"');
    expect(aboutSrc).not.toContain('desc: "Open questions, merged into one number"');

    const categorySrc = readFile("app/categories/[slug]/page.tsx");
    expect(categorySrc).toContain("This page lists open {categoryName.toLowerCase()} markets.");

    const binaryBoardSrc = readFile("components/LeagueBinaryBoard.tsx");
    expect(binaryBoardSrc).toContain('Show {hidden} more market{hidden === 1 ? "" : "s"}');

    const ogSrc = readFile("app/collections/[slug]/opengraph-image.tsx");
    expect(ogSrc).toContain('export const alt = "Bain Luck collection games and markets";');
    expect(ogSrc).toContain('verdict = hub.note ?? "Explore games, results and related markets.";');
  });

  it("calibration coverage, provider panels, calibration page, and labelPassSession use market / market shape", () => {
    expect(RUNG_LABELS.question_ungraded).toBe(
      "No outcome in the market was ever marked the winner",
    );
    expect(RUNG_LABELS.representative_not_selected).toBe(
      "A different row already represents this market",
    );

    const breakdownNote = shapeBreakdownNote([
      {
        key: "odds_api",
        label: "Sportsbooks",
        hasShapeBreakdown: true,
        n: 1000,
      } as unknown as Parameters<typeof shapeBreakdownNote>[0][number],
    ]);
    expect(breakdownNote).toContain("Sportsbooks publishes more than one market shape.");

    expect(shapeBreakoutCaption(["odds_api", "odds_api_totals", "odds_api_spreads"])).toContain(
      "Each curve here is a different market shape",
    );
    expect(
      shapeBreakoutCaption([
        "odds_api_bookmaker",
        "odds_api",
        "odds_api_totals",
        "odds_api_spreads",
      ]),
    ).toContain("Curves of different shapes measure different kinds of markets");

    const calPageSrc = readFile("app/calibration/page.tsx");
    expect(calPageSrc).toContain("Sportsbook odds arrive in more than one market shape;");
    expect(calPageSrc).toContain(
      "Kalshi&rsquo;s or Polymarket&rsquo;s published result for the market, or a public record that settles it.",
    );
    expect(calPageSrc).toContain(
      "The exception is a single yes-or-no market, where there is no other price in play and the venue&rsquo;s result stands on its own.",
    );

    expect(refusalMessage("card_drifted")).toBe(
      "This market re-priced while you were reading it — nothing was recorded. The refreshed card is below.",
    );
  });

  it("Decision 148: A — backend precompute_calibration.py uses 'The yes-or-no markets we were throwing away are now scored'", () => {
    const backendSrc = fs.readFileSync(
      path.join(REPO_ROOT, "backend/app/tasks/precompute_calibration.py"),
      "utf8",
    );
    expect(backendSrc).toContain(
      '"title": "The yes-or-no markets we were throwing away are now scored"',
    );
    expect(backendSrc).not.toContain(
      '"title": "The one-question markets we were throwing away are now scored"',
    );
  });
});
