/**
 * UX-P031 (#1599) — the terminal-state decision for the shared event-concept
 * shell (`app/event/[domain]/[slug]/page.tsx`).
 *
 * Extracted as a pure function because the bug it fixes was a bug of REACHABILITY,
 * not of rendering: the page could enter a state from which the "Event not found"
 * terminal was unreachable, and no amount of looking at the JSX showed it. A
 * three-line boolean inlined in a component is a three-line boolean nobody tests.
 *
 * The defect (browser-audit runs 30864618239 and 31323268137, five days apart,
 * both viewports): a concept URL whose event 404s sat on "Loading event…"
 * indefinitely — still spinning at the rail's 45-second capture — instead of
 * showing "Event not found".
 *
 * The mechanism is worth recording, because the obvious fix does not fix it.
 * L2-175 Item 2d added an anti-flash guard: hold the skeleton while SWR is still
 * retrying, so a slow-but-successful load never flashes "Event not found" first
 * (#249's cold-backend half). It held the spinner on `!!error && !retriesExhausted`,
 * and set `retriesExhausted` ONLY from inside SWR's `onErrorRetry` at
 * `retryCount >= 3`. But SWR invokes `onErrorRetry` only under
 * `shouldStartNewRequest && callbackSafeguard()` (swr@2.4.x,
 * `dist/index/index.mjs`), so an errored request that is deduped or arrives on a
 * double-mounted effect never advances the counter. The flag is never set, and
 * the guard holds the spinner forever.
 *
 * So "the flag never gets set" IS the failure mode, and any fix that still
 * depends on the flag being set correctly inherits the same class. Hence two
 * independent escapes that do not go through `onErrorRetry` at all:
 *
 *   1. A 404 is a KNOWN-DEAD key. The backend has answered definitively; there is
 *      nothing to retry and no reason to wait. Terminal immediately.
 *   2. Every other error path is bounded by a wall-clock ceiling.
 *
 * What is deliberately NOT bounded: a slow load that has not errored. That is
 * exactly L2-175's case, and cutting it off would trade this bug for that one.
 * The asymmetry is the point — the ceiling releases the ERROR branch only.
 */

/**
 * Wall-clock ceiling on a spinner that is only still up because of errors.
 *
 * 30s is chosen against the actual budgets underneath it, not by feel:
 * `apiFetch` uses a 20s per-attempt timeout with its own internal retry ladder,
 * and SWR adds 2s + 4s of backoff on top. A cold backend that answers on a
 * retry lands comfortably inside 30s. Past that, with nothing but errors to
 * show for it, a spinner is no longer "loading" — it is a lie the page is
 * telling. It also sits below the browser-audit journey's 45s capture, so the
 * rail can observe the terminal state rather than timing out on the spinner.
 */
export const CONCEPT_LOADING_CEILING_MS = 30_000;

/**
 * Did the backend definitively say this key does not exist?
 *
 * Only a 404 counts. A 5xx or a timeout means "ask again"; a 404 means "stop
 * asking". Reads `status` structurally so it works for both `ApiError` (which
 * `apiFetch` throws with `.status` set) and anything else carrying the field —
 * never throws on a null, a string, or a plain `Error`.
 */
export function isDeadKeyError(error: unknown): boolean {
  if (error === null || typeof error !== "object") return false;
  return (error as { status?: unknown }).status === 404;
}

export type ConceptRenderState = "ready" | "loading" | "not-found";

export interface ConceptRenderInput {
  /** Has the envelope arrived? Stale-while-revalidate data still counts. */
  hasData: boolean;
  /** SWR's `error` — the last error, or null/undefined when none. */
  error: unknown;
  isLoading: boolean;
  isValidating: boolean;
  /** Set by `onErrorRetry` once the retry ladder is genuinely spent. */
  retriesExhausted: boolean;
  /** Has `CONCEPT_LOADING_CEILING_MS` elapsed since this key started loading? */
  ceilingReached: boolean;
}

/**
 * Which terminal the concept shell should render.
 *
 * Data always wins, including stale data during a background revalidate — a
 * refresh that errors must never blank out a page that is already showing an
 * event.
 */
export function conceptRenderState(input: ConceptRenderInput): ConceptRenderState {
  if (input.hasData) return "ready";

  const errored = input.error !== null && input.error !== undefined;

  // No error yet: honour the in-flight request for as long as it takes. This is
  // L2-175's protected case and the ceiling deliberately does not apply to it.
  // A settled request that produced neither data nor an error has nothing left
  // to wait for, so it falls through to the honest empty terminal.
  if (!errored) {
    return input.isLoading || input.isValidating ? "loading" : "not-found";
  }

  // Errored. Three independent ways to stop waiting, only one of which depends
  // on `onErrorRetry` having fired.
  const givenUp =
    isDeadKeyError(input.error) || input.retriesExhausted || input.ceilingReached;

  return givenUp ? "not-found" : "loading";
}
