/**
 * #12095 Phase 2 — the pure half of the /grade page: the deck it grades, the
 * three grades, and the family tally line. The page owns fetching and state.
 */

import { isAdminAuthError } from "@/lib/adminFetch";
import type { FeedItem } from "@/lib/types";

export const GRADES = ["shareable", "interesting", "neither"] as const;
export type Grade = (typeof GRADES)[number];

export const GRADE_LABELS: Record<Grade, string> = {
  shareable: "Shareable",
  interesting: "Interesting",
  neither: "Neither",
};

/** One card of `GET /api/admin/ranking/grade-deck`. */
export interface GradeDeckItem {
  position: number;
  item_key: string;
  title: string | null;
  probability: number | null;
  /** The card exactly as it was served; null on a slate captured before cards were kept. */
  card: FeedItem | null;
}

export interface GradeDeck {
  switch_on: boolean;
  slate_id: string;
  surface: string;
  captured_at: string | null;
  ranker_version: string;
  items: GradeDeckItem[];
  /** #11937: "opening" (today's ten) or "spread" (a named slate, top to bottom). */
  mode?: "opening" | "spread";
  /** Spread deck only: the slate's whole candidate list length. */
  candidates?: number;
  /** Spread deck only: cards of this deck the grader graded before (skipped). */
  already_graded?: number;
  /** #11937: cards of this deck left out because the slate stored no drawing. */
  left_out_no_drawing?: number;
}

/**
 * #11937: the page never deals a card it can't draw. A title with no number
 * isn't a card, and a grade on it isn't a grade (Fable, Nov 10). The server
 * already leaves these out; this also covers a deck from an older server.
 */
export function drawnOnly(deck: GradeDeck): GradeDeck {
  const items = deck.items.filter((i) => i.card != null);
  const dropped = deck.items.length - items.length;
  return { ...deck, items, left_out_no_drawing: (deck.left_out_no_drawing ?? 0) + dropped };
}

/** "12 cards left out: no stored drawing"; empty when none were. */
export function leftOutLine(deck: GradeDeck): string {
  const n = deck.left_out_no_drawing ?? 0;
  if (n <= 0) return "";
  return `${n} ${n === 1 ? "card" : "cards"} left out: no stored drawing`;
}

const SLATE_REF = /^[A-Za-z0-9-]{1,64}$/;

/** #11937: the `?slate=` a link names (a Pacific date or a slate id), or null. */
export function slateFromSearch(search: string): string | null {
  const raw = new URLSearchParams(search).get("slate");
  return raw && SLATE_REF.test(raw) ? raw : null;
}

/** #11937 (159-A): the `?set=` a link names (an extra card set for that slate), or null. */
export function setFromSearch(search: string): string | null {
  const raw = new URLSearchParams(search).get("set");
  return raw && SLATE_REF.test(raw) ? raw : null;
}

/** The deck request: today's opening ten, or a named slate's deck (with an
 * extra set mixed in when the link names one). */
export function gradeDeckPath(slate: string | null, set: string | null = null): string {
  if (!slate) return "/api/admin/ranking/grade-deck";
  const params: Record<string, string> = { slate };
  if (set) params.set = set;
  return `/api/admin/ranking/grade-deck?${new URLSearchParams(params).toString()}`;
}

/** The grader's name rides in a header, never the URL (request logs), so the
 * named slate's deck can skip what they already graded there. */
export function gradeDeckInit(grader: string | null): RequestInit | undefined {
  return grader ? { headers: { "X-Grader-Name": encodeURIComponent(grader) } } : undefined;
}

/** The line under "Who's grading?". */
export function deckHeadline(deck: GradeDeck): string {
  const when = deck.captured_at ? new Date(deck.captured_at).toLocaleString() : "the latest capture";
  if (deck.mode !== "spread") return `The top ${deck.items.length} Discover cards from ${when}.`;
  const day = deck.captured_at
    ? new Date(deck.captured_at).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "America/Los_Angeles" })
    : "that day";
  const skipped = deck.already_graded ? ` (${deck.already_graded} you've already graded are skipped)` : "";
  return `${deck.items.length} cards from the Discover slate of ${day}: its top cards, then a spread down the rest of its ${deck.candidates ?? "?"} candidates${skipped}.`;
}

/** #11937: the longest a save waits for the server before its one retry
 * (the limiter's window is one minute, so a longer wait is never needed). */
export const MAX_RETRY_WAIT_MS = 60000;

type Answer = {
  status: number;
  headers: { get(name: string): string | null };
  clone(): { json(): Promise<unknown> };
};

/**
 * #11937: how long a rate-limited save should wait before trying again, or
 * null when the answer isn't a 429. The seconds come from `Retry-After`, else
 * the body's `retry_after`: the API is on another origin and doesn't expose
 * `Retry-After` to the page, so the body is what the browser can actually read.
 * 1 s when neither is readable; capped at `MAX_RETRY_WAIT_MS`.
 */
export async function retryWaitMs(res: Answer): Promise<number | null> {
  if (res.status !== 429) return null;
  let seconds = Number(res.headers.get("Retry-After"));
  if (!(Number.isFinite(seconds) && seconds > 0)) {
    try {
      seconds = Number(((await res.clone().json()) as { retry_after?: unknown })?.retry_after);
    } catch {
      seconds = NaN;
    }
  }
  const ms = Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 1000;
  return Math.min(ms, MAX_RETRY_WAIT_MS);
}

/**
 * #11937: send a grade, and if the server says "too many requests", wait what
 * it asks and send it once more, so a grader never has to press twice or
 * wonder whether it saved. `onWait` gets the wait so the page can say so.
 */
export async function saveWithOneRetry<R extends Answer>(
  send: () => Promise<R>,
  sleep: (ms: number) => Promise<void>,
  onWait?: (ms: number) => void,
): Promise<R> {
  const first = await send();
  const wait = await retryWaitMs(first);
  if (wait == null) return first;
  onWait?.(wait);
  await sleep(wait);
  return send();
}

export interface TallyEntry {
  grader: string;
  kid: boolean;
  today: number;
}

/** A grader's name as stored: trimmed, inner spaces collapsed, at most 40 chars. */
export function normalizeGraderName(raw: string): string {
  return raw.trim().split(/\s+/).filter(Boolean).join(" ").slice(0, 40);
}

/** "Alex 10 · Sam 10 · Robin 7 today"; empty when nobody has graded today. */
export function formatTally(tally: TallyEntry[]): string {
  const parts = tally.filter((t) => t.today > 0).map((t) => `${t.grader} ${t.today}`);
  return parts.length ? `${parts.join(" · ")} today` : "";
}

/**
 * #5952 / #6024 — when the initial deck read on `/grade` or `/grade/groupings`
 * fails with 401/403, send the tab back to the secret prompt with
 * `rejected: true` instead of stranding the grader on a bare error line with
 * no way back. Non-auth failures still surface as an error message.
 */
export function handleGradeDeckReadError(
  err: unknown,
  fallbackMessage: string,
  actions: {
    clearSecret: (opts?: { rejected?: boolean }) => void;
    setError: (message: string) => void;
  },
): void {
  if (isAdminAuthError(err)) {
    actions.clearSecret({ rejected: true });
    return;
  }
  actions.setError(err instanceof Error ? err.message : fallbackMessage);
}
