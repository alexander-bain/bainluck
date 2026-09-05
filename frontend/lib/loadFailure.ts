/**
 * What a page says when a fetch did not come back — #2783.
 *
 * The event page answered EVERY failure of `/api/events/{id}` with the title
 * "Event not found". That is true for exactly one of them. Measured on
 * production 2026-09-03, a client over the 60-requests-per-minute limit gets a
 * 429, and the page then tells the reader the event does not exist while the
 * body underneath reads "Rate limit exceeded: 60/minute" — the title
 * contradicting the sentence beneath it, and both contradicting the truth,
 * which is that the event is fine and we were throttled.
 *
 * The same shape covers a 500, a timeout and a dropped connection: all three
 * printed "not found", which is the one thing they are not. A reader who is
 * told a thing does not exist stops looking for it; a reader who is told we
 * could not reach it reloads. Naming the failure correctly is the difference
 * between those two behaviours, and it costs nothing.
 *
 * This is the page-level twin of `SectionErrorBoundary`'s stated rule — never
 * render "there is nothing here" when the truth is "we could not show it".
 *
 * The `detail` the server sent is always preserved as the message: it is the
 * most specific true thing available, and the title is only ever a heading over
 * it. When the server said nothing, the message is written here.
 */

/** The status-carrying error shape `apiFetch` throws (`lib/api.ts`). */
type MaybeApiError = {
  status?: number;
  message?: string;
} | null | undefined;

export interface LoadFailure {
  title: string;
  message: string;
  /** True when a retry is worth offering — i.e. the thing may well be there. */
  retryable: boolean;
}

/**
 * The honest heading, message and retry posture for a failed load.
 *
 * `subject` is the thing that failed, lower case and singular ("event",
 * "market"), so one module serves every page instead of each inventing its own
 * wording.
 */
export function describeLoadFailure(
  error: MaybeApiError,
  subject = "page",
): LoadFailure {
  const status = error?.status;
  const served = typeof error?.message === "string" ? error.message.trim() : "";

  // 404 — and ONLY 404 — means the thing is not there.
  if (status === 404) {
    return {
      title: `${capitalize(subject)} not found`,
      message: served || `This ${subject} does not exist, or it has been removed.`,
      // Not retryable: reloading a 404 reloads a 404, and offering the button
      // invites the reader to keep pressing it.
      retryable: false,
    };
  }

  // 410 — the thing WAS here and we took it down on purpose (lane1/132).
  //
  // `GET /api/events/{id}` answers 410 for a row marked retired: a duplicate
  // whose markets moved to the row that keeps them, or a fixture that will not
  // be played. Without this branch a 410 falls into the generic 4xx arm below
  // and the reader is told "The server refused the request (410)" over a retry
  // button — a machine's sentence for a decision we made, and a button that
  // will return the same answer every time it is pressed.
  //
  // Distinct from 404 for the reason 404 is distinct from 500: not-found means
  // "you may have the wrong address", gone means "the address was right and
  // there is nothing to come back for".
  if (status === 410) {
    return {
      title: `This ${subject} is no longer listed`,
      message:
        served ||
        `This ${subject} was removed from the site and is not coming back.`,
      // Not retryable, and for a stronger reason than 404's: this is a
      // deliberate, recorded removal, not an absence we are unsure about.
      retryable: false,
    };
  }

  if (status === 429) {
    return {
      title: "Too many requests",
      message:
        served ||
        "We are being rate limited right now. Wait a moment and try again.",
      retryable: true,
    };
  }

  if (typeof status === "number" && status >= 500) {
    return {
      title: `Couldn't load this ${subject}`,
      message: served || "The server had a problem. Try again in a moment.",
      retryable: true,
    };
  }

  if (typeof status === "number" && status >= 400) {
    return {
      title: `Couldn't load this ${subject}`,
      message: served || `The server refused the request (${status}).`,
      retryable: true,
    };
  }

  // No status at all: a timeout, an abort, DNS, an offline device. `apiFetch`
  // throws a plain Error for these, so the absence of a status IS the signal.
  return {
    title: `Couldn't reach the server`,
    message:
      served || `We could not load this ${subject}. Check your connection and try again.`,
    retryable: true,
  };
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}
