/**
 * How a surface reads an event's state — one module, so no two surfaces
 * disagree about what a status MEANS.
 *
 * This exists because `suspended` (live/048) landed in a vocabulary that every
 * card and page had been reading with its own inline `=== "closed"` chain. Each
 * of those chains buckets an unrecognised status into the "upcoming" branch by
 * falling through, and the upcoming branch renders a START TIME — so a match
 * suspended for rain would have advertised itself as about to begin. That is a
 * quieter lie than "Final", not a smaller one.
 *
 * The rule the ladder gives us (EVENT-GRAPH-DOCTRINE §R):
 *
 *   - `live`      — something that watches the match says it is being played.
 *   - `suspended` — the clock ran out and NOTHING that watches it said it
 *                   ended. Asserts no outcome. Never Final, never a start time.
 *   - `completed` / `closed` — something with standing said it is over.
 *
 * Keep this in step with `EventStatus` in `lib/types.ts` and with
 * `SETTLED_STATUSES` in `backend/app/utils/event_completion.py`.
 */

/** Something with standing said this event is over. Renders as Final. */
export function isFinishedStatus(status: string | null | undefined): boolean {
  return status === "completed" || status === "closed";
}

/**
 * The clock ran out and no authority, venue settlement or score feed said the
 * match ended. Non-terminal: it can still go back to `live`, and it can still
 * be settled later by something that actually watched.
 */
export function isSuspendedStatus(status: string | null | undefined): boolean {
  return status === "suspended";
}

/**
 * The short badge a suspended event wears.
 *
 * Deliberately NOT "Suspended" as a bare word: for a rain-delayed US Open match
 * that reads right, but the same state also covers a fixture whose only source
 * went dark, and telling a user that match is "suspended" invents a stoppage
 * nobody reported. What both cases actually share is that no result was ever
 * reported, so that is what the badge says.
 */
export const SUSPENDED_LABEL = "No result reported";

/**
 * The longer form, for surfaces with room for a sentence.
 *
 * Present tense only, and that is a constraint rather than a style note: the
 * shipped-copy ban rejects "we will update it if a source confirms the finish"
 * as will-populate language, and it is right to. A promise about a future
 * update is not a description of the state, and this state's whole job is to
 * describe exactly what is and is not known right now.
 */
export const SUSPENDED_DESCRIPTION =
  "This match left the live board and no source has reported a result.";
