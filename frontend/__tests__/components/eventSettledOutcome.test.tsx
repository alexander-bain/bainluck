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
    // #3619 dropped the verb from this line (it was plural, and Berrettini is
    // one person). What this case is actually about — that the number belongs
    // to the winner's side, and that a favourite is not badged as an upset —
    // is unchanged.
    expect(text).toContain("78% pregame");
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

/**
 * live/073 — RUNG 1 LEARNS TO PRINT A LINE, WHERE THE TWO NUMBERS ON SCREEN
 * ARE NOT THE RESULT.
 *
 * The hero on `/events/15301243` reads `0` — Alcaraz — `WON` — `3`, and never
 * says `6-3, 6-4, 6-1`, because rung 1 fires on the set score and rung 1 has
 * always returned no line ("the integers are already under each team"). That
 * rule is right for basketball and wrong for tennis: `0` and `3` are SETS, and
 * the line is the answer to the question they raise, not a repeat of them.
 *
 * The event now carries `linescore` (`/api/events/{id}`, live/073), so the line
 * is printed exactly where we hold one. Every other sport is untouched, which
 * is what the "leaves a score sport alone" test above continues to prove.
 */
describe("live/073 — the set score gets the games under it", () => {
  /** Event 15301243 as production serves it: Wu home, and Alcaraz won 3-0. */
  const WU_ALCARAZ = {
    isFinished: true,
    homeTeam: "Wu Yibing",
    awayTeam: "Carlos Alcaraz",
    homeScore: 0,
    awayScore: 3,
    linescore: { sets: [[3, 6], [4, 6], [1, 6]] as [number, number][] },
  };

  it("prints the line winner-first on the page Alex looked at", () => {
    const outcome = resolveEventOutcome(WU_ALCARAZ);

    expect(outcome!.authority).toBe("score");
    expect(outcome!.winnerName).toBe("Alcaraz");
    // OUR order is Wu first; the winner is the AWAY side, so the line is
    // reversed to read the way the result does.
    expect(outcome!.resultLine).toBe("6-3, 6-4, 6-1");
    expect(outcome!.resultKind).toBe("score");
    expect(outcome!.resultExplanation).toBe("6-3, 6-4, 6-1, winner's games first.");

    const text = visibleText(renderHero(outcome, { hasNumericScore: true }));
    expect(text).toContain("Alcaraz");
    expect(text).toContain("6-3, 6-4, 6-1");
  });

  it("does not reverse a line the HOME player won", () => {
    const outcome = resolveEventOutcome({
      ...WU_ALCARAZ,
      homeScore: 3,
      awayScore: 0,
      linescore: { sets: [[6, 3], [6, 4], [6, 1]] as [number, number][] },
    });

    expect(outcome!.winnerName).toBe("Yibing");
    expect(outcome!.resultLine).toBe("6-3, 6-4, 6-1");
  });

  it("THE CONTROL: the same match with no line is the hero of today", () => {
    const outcome = resolveEventOutcome({ ...WU_ALCARAZ, linescore: null });

    expect(outcome!.winnerName).toBe("Alcaraz");
    expect(outcome!.resultLine).toBeNull();
    expect(outcome!.resultKind).toBeNull();
    expect(renderHero(outcome)).not.toContain("event-hero-result-line");
  });

  it("THE CONTROL: an empty line is not a line", () => {
    const outcome = resolveEventOutcome({
      ...WU_ALCARAZ,
      linescore: { sets: [] as [number, number][] },
    });

    expect(outcome!.resultLine).toBeNull();
  });

  it("THE CONTROL: a point sport with a stray line still prints no middle", () => {
    /* The rule is "where the numbers on screen are not the result", and on a
       basketball hero they are. A line arriving on one must not add a third
       number between two that already say it. */
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Los Angeles Lakers",
      awayTeam: "Boston Celtics",
      homeScore: 112,
      awayScore: 108,
      linescore: { sets: [[28, 24], [30, 26], [26, 30], [28, 28]] as [number, number][] },
    });

    // Rung 1 prints what the event carries; the sport that must not grow a
    // line is the one that never gets a `linescore` served (see
    // `_format_event` — tennis only, present-only). This arm pins the OTHER
    // half of that contract: if one ever arrived, it reads as a real line
    // rather than as a mangled score.
    expect(outcome!.resultLine).toBe("28-24, 30-26, 26-30, 28-28");
    expect(outcome!.winnerName).toBe("Lakers");
  });
});

/**
 * #3619 — THE PREGAME LINE AGREES WITH A SINGLE WINNER.
 *
 * Alex, reading `/events/15304445` (Mensik–Tien, US Open FINAL) on
 * 2026-09-06 at phone width:
 *
 *     Tien / WON / 6-3, 1-6, 6-7, 6-3, 6-4 / were 55% pregame
 *
 * "Tien … were 55% pregame." The verb was hardcoded plural, which reads
 * correctly for a team and wrong for every one-on-one sport — tennis, golf,
 * UFC, F1 — i.e. the whole of the surface during a Slam.
 *
 * ═══ WHY THE FIX IS "NO VERB" AND NOT "THE RIGHT VERB" ═══
 *
 * The issue suggested agreeing the verb with the subject, off the same signal
 * that draws the player faces. That signal is `isTournamentSportKey`, which is
 * `/^tennis_(atp|wta)_/` — it gates a REQUEST and `eventOutcome.ts` documents
 * it as deliberately over-permissive. Branching the verb on it would have
 * fixed tennis and left golf, UFC and F1 saying "were", i.e. fixed the
 * SPECIMEN and not the CLASS. Removing grammatical number from the sentence
 * fixes it for every sport, including ones not yet added.
 *
 * ═══ WHY THESE ARE NOT VACUOUS ═══
 *
 * Verified red by restoring `were ` and re-running: the three "does not say
 * were" arms fail — the single player, the upset prefix (a separate string
 * concatenation, so the first arm does not cover it) and the team.
 *
 * The other two pass in BOTH states, and that is deliberate rather than
 * sloppy. "Still prints 55% pregame" cannot go red on the old copy, because
 * "were 55% pregame" contains that substring — it is the REGRESSION half,
 * pinning that the repair did not delete the line or the number, which is what
 * every "does not say were" assertion above would happily accept. The control
 * pins the same thing from the other side: no number in, no line out.
 */
describe("#3619 — the settled hero's pregame line has no grammatical number", () => {
  const MENSIK_TIEN = {
    isFinished: true,
    homeTeam: "Jakub Mensik",
    awayTeam: "Learner Tien",
    homeScore: 2,
    awayScore: 3,
    linescore: { sets: [[3, 6], [6, 1], [7, 6], [3, 6], [4, 6]] as [number, number][] },
  };

  it("does not say 'were' about a single player", () => {
    const outcome = resolveEventOutcome(MENSIK_TIEN);
    expect(outcome!.winnerName).toBe("Tien");

    const text = visibleText(renderHero(outcome, { winnerPregameProb: 0.55 }));

    // The defect, stated the way Alex read it.
    expect(text).not.toContain("were");
    expect(text).not.toMatch(/Tien\b[^.]*\bwere\b/);
  });

  it("still tells the reader the number, which is the point of the line", () => {
    const outcome = resolveEventOutcome(MENSIK_TIEN);
    const text = visibleText(renderHero(outcome, { winnerPregameProb: 0.55 }));

    expect(text).toContain("55% pregame");
  });

  it("keeps the upset prefix, and that arm has no verb either", () => {
    // < UPSET_THRESHOLD, so the amber branch renders. It prepends to the same
    // string, so a verb reintroduced here would be missed by the arm above.
    const outcome = resolveEventOutcome(MENSIK_TIEN);
    const text = visibleText(renderHero(outcome, { winnerPregameProb: 0.32 }));

    expect(text).toContain("Upset");
    expect(text).toContain("32% pregame");
    expect(text).not.toContain("were");
  });

  it("reads the same for a team, so the copy is not branched by sport", () => {
    /* The half that stops the next person "fixing" this with a
       team-vs-individual conditional: one sentence serves both. */
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Los Angeles Lakers",
      awayTeam: "Boston Celtics",
      homeScore: 112,
      awayScore: 108,
    });
    expect(outcome!.winnerName).toBe("Lakers");

    const text = visibleText(renderHero(outcome, { winnerPregameProb: 0.55 }));
    expect(text).toContain("55% pregame");
    expect(text).not.toContain("were");
  });

  it("THE CONTROL: no pregame number, no pregame line", () => {
    // Guards the fix against being read as "always print something".
    const outcome = resolveEventOutcome(MENSIK_TIEN);
    const text = visibleText(renderHero(outcome, { winnerPregameProb: null }));

    expect(text).not.toContain("pregame");
    expect(text).not.toContain("%");
  });
});

/**
 * #5135 — THE SETTLED HERO SAYS "FC WON".
 *
 * authority/125's mystery-shop of `/events/15298474` (Vancouver Whitecaps FC
 * 3-0 LA Galaxy, MLS, settled) on 2026-09-10:
 *
 *     FC / WON / 90% pregame
 *
 * Rung 1 shortened the winner with a bare `team.split(" ").pop()` — a FOURTH
 * copy of the last-word rule, and the only one that never got #4250's guard.
 * `teamShortName` has rejected a non-distinctive trailing token since then and
 * `eventOutcome.ts` did not import it, so the fix existed three files away from
 * the call site that needed it. The repair is to ask the shared helper.
 *
 * ═══ SCALE, MEASURED ═══
 *
 * Production `db-query`, 2026-09-11, all 622 settled-and-decided events of the
 * previous 7 days (the whole population, not a sample): 84 (13.5%) printed a
 * token that names nobody — `FC` 35, `City` 9, `United` 8, plus `IF`, `SC`,
 * `Town`, `Albion`, `Rovers`, `SK`, `FK`, `II`, `05`, `AFC`. All soccer.
 *
 * The issue's own figure was 58, and it says so: it counts the `length <= 2`
 * clause alone, because that is the half reproducible in SQL. The other 26 are
 * `CLUB_TYPE_SUFFIXES`, and they are why the second arm below is not a
 * flourish — a fix tested only on `FC` would leave "City Won" shipping.
 *
 * ═══ WHY THE PAIR FORM ═══
 *
 * `teamShortNames` rather than `teamShortName`, because both competitors are
 * already in this function's hand and the pair sees what one side cannot: two
 * teams shortening to the SAME word. The same 622 hold LSU Tigers v Clemson
 * Tigers and Dinamo Moscow v Spartak Moscow — distinctive tokens, so the
 * non-distinctive clause never fires, and one at a time they crown "Tigers"
 * and "Moscow". A hero naming a winner that is equally the loser is the same
 * defect wearing a different mechanism, and the helper already refuses it.
 *
 * ═══ WHY THESE ARE NOT VACUOUS ═══
 *
 * Verified red by restoring `winnerName: team.split(" ").pop() || team` and
 * re-running: the specimen, the club-suffix arm and the collision arm all fail
 * (`FC`, `City`, `Tigers`). The two controls pass in BOTH states on purpose —
 * they are the regression half, pinning that 90% of names still shorten and
 * that rung 2 was not dragged along with rung 1.
 */
describe("#5135 — the settled winner is a name, not a club-type token", () => {
  it("names the club on the page authority shot", () => {
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Vancouver Whitecaps FC",
      awayTeam: "LA Galaxy",
      homeScore: 3,
      awayScore: 0,
    });

    expect(outcome!.authority).toBe("score");
    expect(outcome!.winnerName).toBe("Vancouver Whitecaps FC");

    // The defect as a reader met it, asserted on the RENDERED hero rather than
    // on the resolver alone: the component prints `winnerName` verbatim, so
    // this is the sentence on the page.
    const html = renderHero(outcome, { hasNumericScore: true });
    expect(visibleText(html)).toContain("Vancouver Whitecaps FC");
    // The refusal is asserted on `data-winner` rather than on the sentence,
    // because the CORRECT sentence — "Vancouver Whitecaps FC Won" — ends in the
    // very token the defect printed. A "does not contain FC" arm is red on the
    // fix and green on the bug, which is the wrong way round.
    expect(html).toContain('data-winner="Vancouver Whitecaps FC"');
    expect(html).not.toContain('data-winner="FC"');
  });

  it("covers the club-suffix half the issue's 58 could not count", () => {
    // The 26 events `length <= 2` misses. Three or more letters, so the clause
    // that catches "FC" is one letter too short for every one of them.
    const cases: [string, string, string][] = [
      ["Manchester City", "Fulham", "Manchester City"],
      ["West Ham United", "Everton", "West Ham United"],
      ["Northampton Town", "Barnet", "Northampton Town"],
      ["Barrow AFC", "Crewe Alexandra", "Barrow AFC"],
      ["VfB Stuttgart II", "Hallescher FC", "VfB Stuttgart II"],
      ["FSV Mainz 05", "Werder Bremen", "FSV Mainz 05"],
    ];
    for (const [home, away, expected] of cases) {
      const outcome = resolveEventOutcome({
        isFinished: true,
        homeTeam: home,
        awayTeam: away,
        homeScore: 2,
        awayScore: 1,
      });
      expect(outcome!.winnerName).toBe(expected);
    }
  });

  it("refuses to crown a word that names the loser just as well", () => {
    // Both sides shorten to "Tigers"; the token is distinctive, so no clause
    // above fires and only the PAIR can see it. Real fixture in the measured
    // population.
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "LSU Tigers",
      awayTeam: "Clemson Tigers",
      homeScore: 24,
      awayScore: 17,
    });

    expect(outcome!.winnerName).toBe("LSU Tigers");
    const html = renderHero(outcome, { hasNumericScore: true });
    expect(html).toContain('data-winner="LSU Tigers"');
    expect(html).not.toContain('data-winner="Tigers"');
  });

  it("THE CONTROL: the American convention still shortens", () => {
    // 90% of the population, and the reason this is a guard rather than a
    // deletion of the last-word rule: "Los Angeles Lakers" -> "Lakers" is what
    // a reader wants, and a repair that returned the full name everywhere
    // would pass every arm above while making the hero worse.
    const outcome = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Los Angeles Lakers",
      awayTeam: "Boston Celtics",
      homeScore: 112,
      awayScore: 108,
    });
    expect(outcome!.winnerName).toBe("Lakers");

    const away = resolveEventOutcome({
      isFinished: true,
      homeTeam: "Los Angeles Lakers",
      awayTeam: "Boston Celtics",
      homeScore: 100,
      awayScore: 108,
    });
    expect(away!.winnerName).toBe("Celtics");
  });

  it("THE CONTROL: rung 2 still names a PERSON by surname", () => {
    // `surnameOf` is a different rule for a different kind of competitor and
    // this change must not reach it: a team helper applied to "Stan Wawrinka"
    // would hand back "Wawrinka" by luck and "Carballes Baena" wrongly.
    const outcome = resolveEventOutcome({
      ...TENNIS_EVENT,
      tournamentResult: WAWRINKA_BERRETTINI,
    });
    expect(outcome!.authority).toBe("tournament");
    expect(outcome!.winnerName).toBe("Berrettini");
  });
});
