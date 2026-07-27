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
  malformed: number; // cards dropped for missing/malformed stable identity (observable, not silent)
}

export type PlayPoolAction =
  | { type: "START_LOAD" }
  // Freshness refresh (L2-195): restart at offset 0 with a NEW generation while
  // keeping `seen`/`items` so already-consumed cards aren't replayed and only
  // genuinely new first-page cards (newest-first pagination) land. Distinct from
  // START_LOAD, which resumes at the current offset for an error retry / scan.
  | { type: "REFRESH" }
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
    malformed: 0,
  };
}

// Stable identity for a feed card. Returns null (NOT a sentinel string) when the
// card lacks a usable id/key so a partially-malformed page surfaces an observable
// decode/reject count instead of collapsing every id-less card of one type into a
// single `type:undefined` dedupe key (C39 P2). The `typeof` segment keeps numeric
// 1 and string "1" ids distinct.
export function itemKey(it: FeedItem): string | null {
  const type = typeof it?.type === "string" ? it.type : "";
  if (!type) return null;
  const data = (it.data ?? {}) as { id?: unknown; key?: unknown };
  const raw = data.id ?? data.key;
  if (raw === undefined || raw === null) return null;
  if (typeof raw !== "string" && typeof raw !== "number") return null;
  if (typeof raw === "number" && !Number.isFinite(raw)) return null;
  return `${type}:${typeof raw}:${raw}`;
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

    case "REFRESH":
      if (state.inFlight) return state; // never refresh over an in-flight page
      // Restart at page zero for a freshness pass, but KEEP seen/items so the
      // pump dedups against everything already consumed. Bump the generation so
      // any straggler response can't be applied against the refreshed stream.
      return {
        ...state,
        offset: 0,
        emptyScan: 0,
        inFlight: true,
        status: "loading",
        gen: state.gen + 1,
      };

    case "PAGE_ERR":
      if (action.gen !== state.gen) return state; // superseded response — ignore
      // Retain the last good deck; surface a retryable error instead of a
      // false "you rated them all" / perpetual spinner.
      return { ...state, inFlight: false, status: "error" };

    case "PAGE_OK": {
      if (action.gen !== state.gen) return state; // superseded/cancelled — ignore

      const seen = new Set(state.seen);
      const fresh: FeedItem[] = [];
      let malformed = state.malformed;
      for (const it of action.items) {
        const k = itemKey(it);
        if (k === null) {
          // Missing/malformed identity — count it observably; NEVER admit it under
          // a shared sentinel key that would silently discard distinct cards.
          malformed += 1;
          continue;
        }
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
          malformed,
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
        malformed,
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

// "scan_paused" is the truthful state when the client scan bound is reached but
// the SERVER still reports more pages: we haven't found a usable card yet, but we
// are NOT caught up. Only genuine server exhaustion (hasMore=false) is caught_up.
export type PlayView =
  | "play"
  | "loading"
  | "error"
  | "scan"
  | "scan_paused"
  | "caught_up";

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
  if (status === "ready" && hasMore) {
    // More pages exist server-side: keep scanning up to the cap, then PAUSE
    // (never lie "caught up" while hasMore is still true — C39 P2).
    return scanAttempts < maxScan ? "scan" : "scan_paused";
  }
  return "caught_up"; // exhausted (hasMore=false) — the only honest caught-up
}

// ---- Page contract validation -------------------------------------------------
//
// The server page boundary MUST be typed data, not truthiness-coerced. An omitted
// `has_more` silently became `false` (false exhaustion) and a string `"false"`
// became `true` (scan past the end); a malformed `items` payload became an empty
// page. Both hid a backend/decode regression as authoritative pagination state.
// `validatePage` rejects those into a typed error so the pump routes them to the
// retryable error state instead (C39 P2).

export interface PlayPoolPage {
  items: FeedItem[];
  hasMore: boolean;
}

export class PlayPageContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PlayPageContractError";
  }
}

export function validatePage(raw: unknown): PlayPoolPage {
  const r = (raw ?? {}) as { items?: unknown; has_more?: unknown };
  if (!Array.isArray(r.items)) {
    throw new PlayPageContractError("feed page `items` is not an array");
  }
  if (typeof r.has_more !== "boolean") {
    throw new PlayPageContractError("feed page `has_more` is not a boolean");
  }
  return { items: r.items as FeedItem[], hasMore: r.has_more };
}
