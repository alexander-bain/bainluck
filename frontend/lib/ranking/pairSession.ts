/**
 * #11937 (171-A): the pure half of /grade/pair, the blind side-by-side. For one
 * slate, the served first ten and a candidate's first ten, sides assigned at
 * random by the server and never labelled; the grader picks left, right or no
 * difference. Nothing here can tell which side is which, and neither can the
 * page: the response carries only the drawings.
 */

import type { FeedItem } from "@/lib/types";

export const PAIR_CHOICES = ["left", "right", "none"] as const;
export type PairChoice = (typeof PAIR_CHOICES)[number];

export const PAIR_CHOICE_LABELS: Record<PairChoice, string> = {
  left: "Left is better",
  right: "Right is better",
  none: "No difference",
};

/** One side of `GET /api/admin/ranking/pair`: ten drawings, nothing else. */
export interface PairSide {
  card: FeedItem;
}

export interface PairDeck {
  slate_id: string;
  pair: string;
  captured_at?: string | null;
  left: PairSide[];
  right: PairSide[];
}

export const MORNING_NOT_READY_MESSAGE =
  "This morning's cards are not ready yet. They arrive at 7:15 AM.";

const PT_DATE_FORMAT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Los_Angeles",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const PT_DAY_LABEL_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  weekday: "short",
  month: "short",
  day: "numeric",
});

/** Pacific calendar day of a capture ISO stamp (e.g. "Thu, Nov 19"), or "". */
export function formatCaptureDayPt(capturedAt: string | null | undefined): string {
  if (!capturedAt) return "";
  const dt = new Date(capturedAt);
  if (Number.isNaN(dt.getTime())) return "";
  return PT_DAY_LABEL_FORMAT.format(dt);
}

/** Whether a capture ISO stamp falls on today's calendar day in Pacific time. */
export function isCapturedTodayPt(
  capturedAt: string | null | undefined,
  now: Date = new Date(),
): boolean {
  if (!capturedAt) return false;
  const dt = new Date(capturedAt);
  if (Number.isNaN(dt.getTime())) return false;
  return PT_DATE_FORMAT.format(dt) === PT_DATE_FORMAT.format(now);
}

/** Surface the plain-English morning-not-ready message cleanly without HTTP status noise. */
export function normalizeMorningError(message: string): string {
  if (message.includes(MORNING_NOT_READY_MESSAGE)) return MORNING_NOT_READY_MESSAGE;
  return message;
}

const REF = /^[A-Za-z0-9-]{1,64}$/;

/** The `?slate=` and `?pair=` a link names, or null when either is missing or unsafe. */
export function pairFromSearch(search: string): { slate: string; pair: string } | null {
  const params = new URLSearchParams(search);
  const slate = params.get("slate");
  const pair = params.get("pair");
  return slate && pair && REF.test(slate) && REF.test(pair) ? { slate, pair } : null;
}

/**
 * #11937: one-link morning target.
 * - Bare `/grade/pair` (neither `slate` nor `pair` in the query) returns
 *   `{ slate: null, pair: null }` so the page loads today's newest slate and
 *   default blind morning pair without needing query parameters.
 * - Explicit `?slate=&pair=` still works when both pass `REF`.
 * - Half-specified or unsafe query params return `null`.
 */
export function pairTargetFromSearch(
  search: string,
): { slate: string | null; pair: string | null } | null {
  const params = new URLSearchParams(search);
  const slate = params.get("slate");
  const pair = params.get("pair");
  if (!slate && !pair) return { slate: null, pair: null };
  return slate && pair && REF.test(slate) && REF.test(pair) ? { slate, pair } : null;
}

export function pairPath(slate: string | null, pair: string | null): string {
  if (!slate || !pair) return "/api/admin/ranking/pair";
  return `/api/admin/ranking/pair?${new URLSearchParams({ slate, pair }).toString()}`;
}

/** After a pick, the morning goes on to that slate's deck (amendment 2). */
export function gradeDeckHref(slateId: string): string {
  return `/grade?${new URLSearchParams({ slate: slateId }).toString()}`;
}
