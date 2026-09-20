import { EVENT_BOOT_CLAIM_TIMEOUT_MS } from "./detailBoot";

/**
 * What the Event page shows WHILE ITS OWN FETCH IS STILL IN FLIGHT (#5607).
 *
 * This module exists because the page used to answer that question with a
 * failure. After 12 s of loading it replaced the whole page — score, chart,
 * markets — with a red card reading "Loading timed out / The event is taking
 * too long to load", terminal until the reader tapped it. Measured on
 * production 2026-09-12: 1 in 12 cold loads of the same URL at the same width
 * in the same ten minutes, against an API answering that URL in 0.216 s.
 *
 * THE DEFECT WAS A DEADLINE INVERSION, NOT A MISSING RETRY. `fetchEvent` is a
 * two-stage chain and the page's stopwatch was shorter than its FIRST stage:
 *
 *   page's terminal card ............................. 12,000 ms
 *   stage 1 — `claimEventBooted` boot race ........... 20,000 ms
 *   stage 2 — `apiFetch` ............................. 20,000 ms/attempt, ×3
 *
 * So the page declared a failure at 12 s over a fetch that had not failed and
 * could not yet have failed — while the mechanism written to survive exactly
 * that stall was still running. `detailBoot.ts` says so in its own words: the
 * claim is "RACED against this deadline and falls through to the normal
 * retrying path when it expires". The page never waited for the fallthrough.
 * That is also why the rate was measured on COLD loads specifically — the
 * parked boot record only exists on a cold document load.
 *
 * Raising the 12 s constant is not the repair: the chain's worst case is
 * 20 + 20×3 ≈ 80 s and nobody watches a spinner for 80 s. Adding a retry is not
 * the repair either — `apiFetch` already retries twice and SWR retries on
 * error; a third layer underneath a deadline that fires before either is
 * reached changes nothing. The repair is that a stopwatch which knows nothing
 * about the fetch does not get to declare the fetch dead.
 *
 * So: while loading, this module can only ever return a LOADING view. The
 * terminal claim belongs to the page's real failure branch, which already
 * exists and is already good — `describeLoadFailure(eventError)` under the
 * `!event` gate, which reads the actual status and picks the actual sentence.
 * This is the same lesson #5016 taught this same file, one signal along: there
 * it was `eventError || !event` throwing away a page that had arrived, here it
 * is a timer throwing away a page that is still coming.
 */
export type EventLoadingPresentation = "spinner" | "spinner-with-retry";

export interface EventLoadingView {
  presentation: EventLoadingPresentation;
  /**
   * The words under the spinner. Owned here rather than inlined in the page so
   * the guard can assert what they do NOT say: the whole defect was one
   * sentence claiming an outcome the fetch had not reached.
   */
  text: string;
  /**
   * Whether a manual retry is offered beside the spinner.
   *
   * The card being replaced had a `Tap to retry`, so dropping it would trade
   * one defect for a capability regression. It is kept — as an OFFER next to a
   * live spinner rather than as the only way out of a dead page.
   */
  offersRetry: boolean;
}

/**
 * The earliest instant at which `fetchEvent` can have failed AT ALL.
 *
 * Stage 1 owns the first 20 s and resolves to "fall through to the retrying
 * path", never to an error, so nothing the reader could honestly be told about
 * a failure exists before this mark. Named, and asserted against below, so the
 * inversion that caused #5607 cannot quietly return: any future terminal
 * deadline on this page has to be measured against this number.
 */
export const EVENT_FETCH_FIRST_POSSIBLE_FAILURE_MS = EVENT_BOOT_CLAIM_TIMEOUT_MS;

/**
 * When the page stops being silent and says it is still working.
 *
 * Deliberately EARLIER than the first possible failure, which is the opposite
 * constraint from the one the old constant was under. Reassurance has to reach
 * the reader DURING the stall window, so it must land before stage 1 can
 * expire; a failure claim would have to land after. Twelve seconds is the
 * shipped number, kept so the reader's wait does not get quieter than it was —
 * only the sentence at the end of it changes.
 */
export const EVENT_SLOW_LOAD_NOTICE_MS = 12000;

/**
 * @param pastSlowMark whether `EVENT_SLOW_LOAD_NOTICE_MS` has elapsed with the
 *   fetch still in flight.
 */
export function eventLoadingView(pastSlowMark: boolean): EventLoadingView {
  if (pastSlowMark) {
    return {
      presentation: "spinner-with-retry",
      // Present tense, and about US, not about the event. "Still loading" is
      // true at 12 s, at 40 s and at 80 s; "timed out" was false at all three.
      text: "Still loading this event…",
      offersRetry: true,
    };
  }
  return {
    presentation: "spinner",
    text: "Loading event...",
    offersRetry: false,
  };
}
