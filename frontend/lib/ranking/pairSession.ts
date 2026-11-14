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
  left: PairSide[];
  right: PairSide[];
}

const REF = /^[A-Za-z0-9-]{1,64}$/;

/** The `?slate=` and `?pair=` a link names, or null when either is missing or unsafe. */
export function pairFromSearch(search: string): { slate: string; pair: string } | null {
  const params = new URLSearchParams(search);
  const slate = params.get("slate");
  const pair = params.get("pair");
  return slate && pair && REF.test(slate) && REF.test(pair) ? { slate, pair } : null;
}

export function pairPath(slate: string, pair: string): string {
  return `/api/admin/ranking/pair?${new URLSearchParams({ slate, pair }).toString()}`;
}

/** After a pick, the morning goes on to that slate's deck (amendment 2). */
export function gradeDeckHref(slateId: string): string {
  return `/grade?${new URLSearchParams({ slate: slateId }).toString()}`;
}
