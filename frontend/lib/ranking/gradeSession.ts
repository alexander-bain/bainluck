/**
 * #12095 Phase 2 — the pure half of the /grade page: the deck it grades, the
 * three grades, and the family tally line. The page owns fetching and state.
 */

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

/** "Alex 10 · Dexter 10 · Daphne 7 today"; empty when nobody has graded today. */
export function formatTally(tally: TallyEntry[]): string {
  const parts = tally.filter((t) => t.today > 0).map((t) => `${t.grader} ${t.today}`);
  return parts.length ? `${parts.join(" · ")} today` : "";
}
