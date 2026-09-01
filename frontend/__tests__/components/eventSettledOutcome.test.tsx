/**
 * THE PAGE SAYS FINAL — SO IT SAYS WHO WON, AND BY WHAT (#2443).
 *
 * Alex, reading `/events/15293846` (Berrettini–Wawrinka) on 2026-08-31:
 *
 *     the page renders the FINAL badge and the two players, and nowhere states
 *     the winner or the score … the single most obviously broken thing on it
 *
 * while `/tournaments/us-open`, one click away, printed the same match with its
 * full score.
 *
 * ═══ WHAT IS ACTUALLY HELD HERE ═══
 *
 * Every assertion is against RENDERED markup, because the defect is a render
 * defect: the resolver could return a perfect outcome and the hero could still
 * print nothing, which is a state this page has literally been in — the
 * `result` block these fixtures are copied from has been served by
 * `/api/tournaments/by-event/15293846` the whole time and no component read it.
 *
 * The fixtures are the PRODUCTION payload, fetched 2026-08-31, not a
 * hand-written shape that agrees with the parser. `WAWRINKA_BERRETTINI` is
 * verbatim from that endpoint, images and prematch numbers trimmed.
 *
 * ═══ THE FOUR CASES, AND WHY EACH IS NOT VACUOUS ═══
 *
 * 1. **Tennis, decided by the container.** Fails on the shipped code: with the
 *    score rung alone the hero renders the word "Final" and no name.
 * 2. **Nothing authoritative.** Same event, container result withheld → back
 *    to "Final". This is the control that proves case 1 is reading the
 *    fixture and not printing a constant.
 * 3. **A score sport is untouched, and does NOT gain a duplicate line.** The
 *    integers already sit under each team; a middle line reading "112-108"
 *    would be the duplication L2-112 took out of this hero.
 * 4. **The pregame mark follows the WINNER's side.** The regression this
 *    invites is crediting the home opening number to an away winner, which is
 *    silently wrong rather than visibly broken.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SettledOutcomeHero from "@/components/event/SettledOutcomeHero";
import {
  isTournamentSportKey,
  resolveEventOutcome,
} from "@/lib/eventOutcome";
import type { TournamentResult } from "@/lib/tournamentResults";

/** Everything a reader can actually see. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Verbatim from `/api/tournaments/by-event/15293846`, 2026-08-31. */
const WAWRINKA_BERRETTINI: TournamentResult = {
  matchup_key: "mens-singles:matteo-berrettini-vs-stan-wawrinka:2026-08-30",
  draw: "mens-singles",
  draw_label: "Men's Singles",
  round: "Round 1",
  players: [
    {
      entity_key: "stan-wawrinka",
      display_name: "Stan Wawrinka",
      seed: null,
      is_winner: false,
      prematch_probability: 0.217172,
    },
    {
      entity_key: "matteo-berrettini",
      display_name: "Matteo Berrettini",
      seed: null,
      is_winner: true,
      prematch_probability: 0.782828,
    },
  ],
  winner_entity_key: "matteo-berrettini",
  score: "7-6, 7-6, 6-0",
  completion: "final",
  completed_at: "2026-08-31T19:45Z",
  source_round: "Round 1",
  source: "espn",
};

/** The event row as production actually holds it: no integers, by nature. */
const TENNIS_EVENT = {
  isFinished: true,
  homeTeam: "Matteo Berrettini",
  awayTeam: "Stan Wawrinka",
  homeScore: null,
  awayScore: null,
};

function renderHero(
  outcome: ReturnType<typeof resolveEventOutcome>,
  opts: { hasNumericScore?: boolean; winnerPregameProb?: number | null } = {}
): string {
  return renderToStaticMarkup(
    <SettledOutcomeHero
      outcome={outcome}
      hasNumericScore={opts.hasNumericScore ?? false}
      winnerPregameProb={opts.winnerPregameProb ?? null}
    />
  );
}

describe("#2443 — a settled event page states its outcome", () => {
  it("names the winner and prints the score for a tennis match", () => {
    const outcome = resolveEventOutcome({
      ...TENNIS_EVENT,
      tournamentResult: WAWRINKA_BERRETTINI,
    });
    expect(outcome).not.toBeNull();
    expect(outcome!.authority).toBe("tournament");
    expect(outcome!.winnerSide).toBe("home");

    const text = visibleText(renderHero(outcome));
    // The two things the page did not say.
    expect(text).toContain("Berrettini");
    expect(text).toContain("7-6, 7-6, 6-0");
    // And it still says the winner WON, rather than leaving the reader to
    // infer it from a scoreline they have to parse.
    expect(text).toContain("Won");
    // The loser is not crowned by a name-matching slip.
    expect(text).not.toContain("Wawrinka");
  });

  it("falls back to a bare Final when nothing names a winner", () => {
    // Same event, no container result — a match we have not graded. The hero
    // must not invent an outcome, and this is what makes the case above a real
    // assertion rather than a constant.
    const outcome = resolveEventOutcome({ ...TENNIS_EVENT, tournamentResult: null });
    expect(outcome).toBeNull();

    const text = visibleText(renderHero(outcome));
    expect(text).toBe("Final");
    expect(text).not.toContain("7-6");
  });

  it("leaves a score sport alone, and adds no duplicate score line", () => {
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Los Angeles Lakers",
      awayTeam: "Boston Celtics",
      homeScore: 112,
      awayScore: 108,
    });
    expect(outcome!.authority).toBe("score");
    expect(outcome!.winnerName).toBe("Lakers");
    // The integers are already under each team in the hero; repeating them in
    // the middle is the duplication this hero had removed once already.
    expect(outcome!.resultLine).toBeNull();

    const html = renderHero(outcome, { hasNumericScore: true });
    expect(html).not.toContain("event-hero-result-line");
    expect(visibleText(html)).toContain("Lakers");
  });

  it("keeps the honest draw", () => {
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Arsenal",
      awayTeam: "Chelsea",
      homeScore: 2,
      awayScore: 2,
    });
    expect(outcome).toBeNull();
    expect(visibleText(renderHero(outcome, { hasNumericScore: true }))).toBe(
      "Final · Tied"
    );
  });

  it("marks the pregame number of the side that actually won", () => {
    // Wawrinka as the HOME row and Berrettini away — the same result, sides
    // swapped, which is the arrangement that catches a resolver reading the
    // home column regardless of who the winner is.
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Stan Wawrinka",
      awayTeam: "Matteo Berrettini",
      homeScore: null,
      awayScore: null,
      tournamentResult: WAWRINKA_BERRETTINI,
    });
    expect(outcome!.winnerName).toBe("Berrettini");
    expect(outcome!.winnerSide).toBe("away");

    // The caller feeds the AWAY opening number because the away side won; an
    // 78% favourite is not an upset and must not be dressed as one.
    const text = visibleText(renderHero(outcome, { winnerPregameProb: 0.783 }));
    expect(text).toContain("were 78% pregame");
    expect(text).not.toContain("Upset");
  });

  it("says a walkover was a walkover rather than printing no score", () => {
    // UX-P147's distinction, inherited whole: a match nobody played is a fact,
    // and "no score" is our gap. The hero must carry both without wording
    // either as the other.
    const walkover = resolveEventOutcome({
      ...TENNIS_EVENT,
      tournamentResult: { ...WAWRINKA_BERRETTINI, score: null, completion: "walkover" },
    });
    expect(walkover!.resultKind).toBe("walkover");
    expect(visibleText(renderHero(walkover))).toContain("walkover");

    const ungraded = resolveEventOutcome({
      ...TENNIS_EVENT,
      tournamentResult: { ...WAWRINKA_BERRETTINI, score: null, completion: null },
    });
    expect(ungraded!.resultKind).toBe("absent");
    expect(visibleText(renderHero(ungraded))).toContain("no score");
  });

  it("does not ask the tournament endpoint for a non-tournament event", () => {
    // The gate the hero and `TournamentExtensions` now SHARE. An event page
    // must not grow a round trip for a feature that applies to 94 events.
    expect(isTournamentSportKey("tennis_atp_us_open")).toBe(true);
    expect(isTournamentSportKey("tennis_wta_us_open")).toBe(true);
    expect(isTournamentSportKey("basketball_nba")).toBe(false);
    expect(isTournamentSportKey(null)).toBe(false);
    expect(isTournamentSportKey(undefined)).toBe(false);
  });
});
