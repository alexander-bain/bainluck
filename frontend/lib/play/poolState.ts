// L2-194 — the explicit /play card-pool state machine.
//
// C32 (P1/P2) found that Play swallowed the pool-load outcome: a failed request
// looked identical to honest exhaustion, and a decoded page with no *usable*
// content left Higher/Lower saying "Loading questions..." forever. This module
// is the pure, deterministic core that fixes it. It carries the server's page
// boundary (`hasMore`) SEPARATELY from how many kid-safe cards actually landed,
// so the UI can always resolve to a real terminal: loading, retryable error, or
// honest caught-up.
//
// Kept framework-free on purpose — every transition is unit-testable in the
// node jest env (no jsdom). `usePlayPool` is the thin React wrapper.

import type { FeedItem } from "@/lib/types";

export type PlayPoolStatus = "loading" | "ready" | "error" | "exhausted";

// How many consecutive server pages that add ZERO new kid-safe cards
// (duplicate-only or fully-filtered pages) we will auto-advance through before
// pausing at "ready". This bounds the "advance by the page boundary" scan so a
// pathological run of empty pages can never loop forever.
export const MAX_EMPTY_SCAN = 5;

export interface PlayPoolState {
  items: FeedItem[];
  seen: Set<string>; // dedupe keys, in insertion order via items
  status: PlayPoolStatus;
  hasMore: boolean; // the SERVER's page boundary — not the usable-card count
  offset: number; // next server offset to request
  inFlight: boolean;
  emptyScan: number; // consecutive zero-new-card fetches (bounded by MAX_EMPTY_SCAN)
  gen: number; // generation token; a PAGE_OK/PAGE_ERR from a superseded request is ignored
}

export type PlayPoolAction =
  | { type: "START_LOAD" }
  | {
      type: "PAGE_OK";
      gen: number;
      items: FeedItem[];
      hasMore: boolean;
      pageSize: number;
    }
  | { type: "PAGE_ERR"; gen: number };

export function initialPoolState(): PlayPoolState {
  return {
    items: [],
    seen: new Set<string>(),
    status: "loading",
    hasMore: true,
    offset: 0,
    inFlight: false,
    emptyScan: 0,
    gen: 0,
  };
}

// Stable identity for a feed card, matching the original page.tsx dedupe key so
// pages that re-surface the same cards don't inflate the deck.
export function itemKey(it: FeedItem): string {
  const data = (it.data ?? {}) as { id?: unknown; key?: unknown };
  return `${it.type}:${JSON.stringify(data.id ?? data.key)}`;
}

// The pump keeps fetching while this is true: a load has been requested and the
// machine still wants the next page (initial request or an auto-advance).
export function pendingFetch(state: PlayPoolState): boolean {
  return state.inFlight && state.status === "loading";
}

export function reducePool(
  state: PlayPoolState,
  action: PlayPoolAction
): PlayPoolState {
  switch (action.type) {
    case "START_LOAD":
      if (state.inFlight) return state; // never two concurrent page requests
      return { ...state, inFlight: true, status: "loading" };

    case "PAGE_ERR":
      if (action.gen !== state.gen) return state; // superseded response — ignore
      // Retain the last good deck; surface a retryable error instead of a
      // false "you rated them all" / perpetual spinner.
      return { ...state, inFlight: false, status: "error" };

    case "PAGE_OK": {
      if (action.gen !== state.gen) return state; // superseded/cancelled — ignore

      const seen = new Set(state.seen);
      const fresh: FeedItem[] = [];
      for (const it of action.items) {
        const k = itemKey(it);
        if (!seen.has(k)) {
          seen.add(k);
          fresh.push(it);
        }
      }
      const added = fresh.length;
      const items = added ? [...state.items, ...fresh] : state.items;
      const offset = state.offset + action.pageSize;

      // A page that added no new kid-safe cards (duplicate-only or fully
      // filtered) advances the server page boundary and keeps scanning — but
      // only while the server says there's more AND we're under the scan cap.
      if (added === 0 && action.hasMore && state.emptyScan < MAX_EMPTY_SCAN) {
        return {
          ...state,
          items,
          seen,
          offset,
          hasMore: action.hasMore,
          emptyScan: state.emptyScan + 1,
          inFlight: true,
          status: "loading",
        };
      }

      // Otherwise settle: honest exhaustion ONLY when the server says no more
      // pages; a scan-capped empty run pauses at "ready" (retry/caught-up is a
      // UI decision), never a loop.
      return {
        ...state,
        items,
        seen,
        offset,
        hasMore: action.hasMore,
        emptyScan: added ? 0 : state.emptyScan,
        inFlight: false,
        status: action.hasMore ? "ready" : "exhausted",
      };
    }

    default:
      return state;
  }
}

// ---- View decision (shared by both game modes) --------------------------------
//
// Given how many cards THIS mode can actually use (Higher/Lower: futures with a
// positive leader; Cool/Boring: any remaining kid-safe card) plus the pool
// state, resolve exactly one view. "scan" tells the caller to request another
// page (bounded by its own scanAttempts) then show loading — this is how a safe
// page that is events-only advances to a later page that carries questions.

export type PlayView = "play" | "loading" | "error" | "scan" | "caught_up";

export function decidePlayView(args: {
  usableCount: number;
  status: PlayPoolStatus;
  hasMore: boolean;
  scanAttempts: number;
  maxScan: number;
}): PlayView {
  const { usableCount, status, hasMore, scanAttempts, maxScan } = args;
  if (usableCount > 0) return "play";
  if (status === "loading") return "loading";
  if (status === "error") return "error";
  if (status === "ready" && hasMore && scanAttempts < maxScan) return "scan";
  return "caught_up";
}
