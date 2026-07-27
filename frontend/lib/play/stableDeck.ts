"use client";

// L2-195 — stable per-round ordered deck.
//
// C39 P1: page.tsx computed `deck = useMemo(() => seedByAffinity(pool, loves))`,
// re-partitioning the ENTIRE growing pool (liked-first) on every append while
// both games tracked progress by a numeric index (`deck[index]` / `questions[pos]`).
// A later page adding a liked card moved it ahead of already-shown "rest" cards,
// so the same index suddenly pointed at a different market — repeats, skips, or a
// vote/prediction recorded against a card that changed mid-interaction.
//
// The fix: freeze a per-round ordered identity queue. The existing prefix NEVER
// reorders; only genuinely new cards are appended, affinity-ordered WITHIN the
// appended batch. The first round still gets full affinity delight (its "batch"
// is the whole first page); every later append preserves the visible prefix, the
// current card, and the active question by construction.

import { useEffect, useRef, useState } from "react";
import type { FeedItem } from "@/lib/types";
import { itemKey } from "@/lib/play/poolState";
import { seedByAffinity } from "@/lib/play/session";

/**
 * Merge freshly-arrived pool items onto a stable deck without reordering the
 * existing prefix. Pure and idempotent: calling again with the same pool returns
 * the SAME array reference (nothing new), so it can't loop a render effect.
 *
 * @param prev  the current stable deck (its order is preserved verbatim)
 * @param pool  the append-only, deduped pool from usePlayPool
 * @param loves the active player's chosen affinity chips
 */
export function mergeStableDeck(
  prev: FeedItem[],
  pool: FeedItem[],
  loves: string[]
): FeedItem[] {
  const seen = new Set<string>();
  for (const it of prev) {
    const k = itemKey(it);
    if (k !== null) seen.add(k);
  }
  const incoming: FeedItem[] = [];
  for (const it of pool) {
    const k = itemKey(it);
    if (k === null) continue; // malformed identity is rejected upstream; defensive here
    if (!seen.has(k)) {
      seen.add(k);
      incoming.push(it);
    }
  }
  if (incoming.length === 0) return prev; // stable reference — no new cards
  // Affinity-order only the NEW batch, then append after the frozen prefix.
  return [...prev, ...seedByAffinity(incoming, loves)];
}

/**
 * React binding for {@link mergeStableDeck}. Accumulates a prefix-stable deck
 * across pool appends; `roundKey` (e.g. the active player's slug) starts a fresh
 * round — a deliberate new generation — clearing the frozen prefix.
 */
export function useStableDeck(
  pool: FeedItem[],
  loves: string[],
  roundKey: string
): FeedItem[] {
  const [round, setRound] = useState(roundKey);
  const [deck, setDeck] = useState<FeedItem[]>([]);
  const deckRef = useRef<FeedItem[]>([]);

  // Round change (profile switch) = new generation: reset synchronously via the
  // documented "adjust state during render" pattern so this render already yields
  // the empty new-round deck instead of leaking the prior player's cards.
  if (round !== roundKey) {
    setRound(roundKey);
    deckRef.current = [];
    setDeck([]);
  }

  useEffect(() => {
    const merged = mergeStableDeck(deckRef.current, pool, loves);
    if (merged !== deckRef.current) {
      deckRef.current = merged;
      setDeck(merged);
    }
    // roundKey in deps so a reset re-merges from the empty prefix.
  }, [pool, loves, roundKey]);

  return deck;
}
