/**
 * searchAnswerState — did this search find nothing, or did we fail to finish it?
 *
 * #2239. `/api/events/search` carries a 20,000 ms deadline and sheds stages
 * rather than erroring when it runs out, declaring each one it dropped in
 * `degraded`. The route states the contract at the payload site:
 *
 *     A stage we could not complete must be distinguishable from a stage that
 *     honestly found nothing.
 *
 * It was distinguishable on the wire and nowhere else. `SearchResponse` did not
 * model the field, so the page saw four empty arrays and printed "No results for
 * X — we couldn't find any teams, games, or markets matching that." That is a
 * claim about the world, made from a request we abandoned, and #2239's user
 * retyped the same word four times against it.
 *
 * This is ruling 025 clause 4's distinction on the surface that never got it.
 * `lib/leaguePageChrome.ts` has kept it for the league page since UX-P062, and
 * its sentence is the whole design: one says "nothing is happening", the other
 * says "we failed to look".
 *
 * Pure, for the reason `leaguePageChrome` gives: jest runs
 * `testEnvironment: 'node'` here with no jsdom, so a decision left as a JSX
 * condition cannot be tested at all.
 */

export type SearchAnswerState = "present" | "degraded" | "empty";

/**
 * Which of the three the page should render.
 *
 * CONTENT WINS OVER `degraded`, deliberately, and it is the narrower half of the
 * fix. A partial answer still renders what it has: the page only lies when it
 * asserts ABSENCE, and showing three markets while silently omitting a shed
 * futures stage is incomplete rather than false. Widening this to warn on every
 * partial answer is a real question, and a different one — it would put an
 * outage banner over pages that are visibly working.
 *
 * The four section flags are the page's own, and they are the same four the
 * backend recorder counts (`_answered_result_count`), on purpose: the log and
 * the screen must not be able to disagree about whether a search was answered.
 */
export function searchAnswerState(input: {
  hasEvents: boolean;
  hasFutures: boolean;
  hasTeams: boolean;
  hasEventConcepts: boolean;
  degraded?: readonly string[] | null;
}): SearchAnswerState {
  if (
    input.hasEvents ||
    input.hasFutures ||
    input.hasTeams ||
    input.hasEventConcepts
  ) {
    return "present";
  }
  // Nothing to show. WHY there is nothing is the entire question, and `degraded`
  // is the only thing that can answer it. Additive on the wire, so absent — or
  // an empty list — means the answer really was complete.
  return input.degraded && input.degraded.length > 0 ? "degraded" : "empty";
}
