// L2-194 — deterministic coverage for the /play pool state machine and the
// shared view decision. Pure (node env, no jsdom): drives the exact reducer the
// hook uses, so loading/retry/exhaustion/scan behavior is provable without a
// live feed. Maps 1:1 to the C32 P1/P2 findings and the queue's required cases.

import {
  MAX_EMPTY_SCAN,
  PlayPageContractError,
  decidePlayView,
  initialPoolState,
  itemKey,
  pendingFetch,
  reducePool,
  validatePage,
  type PlayPoolAction,
  type PlayPoolState,
} from "@/lib/play/poolState";
import type { FeedItem } from "@/lib/types";

const PAGE = 120;

function ev(id: number): FeedItem {
  return {
    type: "event",
    score: 1,
    reason: "",
    headline: null,
    data: { id } as unknown as FeedItem["data"],
  };
}

function fut(id: number, prob = 0.6): FeedItem {
  return {
    type: "futures",
    score: 1,
    reason: "",
    headline: null,
    data: {
      id,
      top_outcomes: [{ name: `Outcome ${id}`, probability: prob }],
    } as unknown as FeedItem["data"],
  };
}

// Apply a full "fetch page" round: START_LOAD (if idle) then PAGE_OK. Auto-
// advance chaining is exercised by re-issuing PAGE_OK while pendingFetch stays
// true, exactly as the hook's pump loop does.
function fetchPage(
  state: PlayPoolState,
  items: FeedItem[],
  hasMore: boolean
): PlayPoolState {
  let s = reducePool(state, { type: "START_LOAD" });
  s = reducePool(s, { type: "PAGE_OK", gen: s.gen, items, hasMore, pageSize: PAGE });
  return s;
}

describe("reducePool — load lifecycle", () => {
  it("START_LOAD moves initial → loading and marks in flight", () => {
    const s = reducePool(initialPoolState(), { type: "START_LOAD" });
    expect(s.status).toBe("loading");
    expect(s.inFlight).toBe(true);
    expect(pendingFetch(s)).toBe(true);
  });

  it("never starts a second concurrent request", () => {
    const s = reducePool(initialPoolState(), { type: "START_LOAD" });
    const again = reducePool(s, { type: "START_LOAD" });
    expect(again).toBe(s); // unchanged reference — no duplicate page request
  });

  it("a page with new cards + more available settles to ready", () => {
    const s = fetchPage(initialPoolState(), [ev(1), fut(2)], true);
    expect(s.status).toBe("ready");
    expect(s.inFlight).toBe(false);
    expect(s.items).toHaveLength(2);
    expect(s.offset).toBe(PAGE);
    expect(s.hasMore).toBe(true);
  });

  it("honest exhaustion only when the server says no more pages", () => {
    const s = fetchPage(initialPoolState(), [fut(1)], false);
    expect(s.status).toBe("exhausted");
    expect(s.hasMore).toBe(false);
  });
});

describe("reducePool — dedupe across pages", () => {
  it("re-surfaced cards do not inflate the deck", () => {
    let s = fetchPage(initialPoolState(), [ev(1), fut(2)], true);
    s = fetchPage(s, [fut(2), fut(3)], true); // fut(2) is a duplicate
    expect(s.items).toHaveLength(3);
    expect(s.items.map((it) => itemKey(it))).toEqual([
      itemKey(ev(1)),
      itemKey(fut(2)),
      itemKey(fut(3)),
    ]);
  });
});

describe("reducePool — empty / duplicate-only pages advance the boundary, never loop", () => {
  it("a zero-new-card page auto-advances (stays loading) while more exist", () => {
    const ready = fetchPage(initialPoolState(), [fut(1)], true);
    // Next page returns only the already-seen card → zero new.
    let s = reducePool(ready, { type: "START_LOAD" });
    s = reducePool(s, { type: "PAGE_OK", gen: s.gen, items: [fut(1)], hasMore: true, pageSize: PAGE });
    expect(s.status).toBe("loading"); // auto-advance requested
    expect(s.inFlight).toBe(true);
    expect(s.emptyScan).toBe(1);
    expect(s.offset).toBe(PAGE * 2); // page 1 + this page each advanced by the boundary
  });

  it("all-filtered pages terminate at the scan cap without looping (still hasMore)", () => {
    let s = reducePool(initialPoolState(), { type: "START_LOAD" });
    // Every page is empty and hasMore stays true.
    for (let i = 0; i < MAX_EMPTY_SCAN + 3; i++) {
      s = reducePool(s, { type: "PAGE_OK", gen: s.gen, items: [], hasMore: true, pageSize: PAGE });
      if (pendingFetch(s)) continue; // the pump would fetch again
      break;
    }
    expect(s.emptyScan).toBe(MAX_EMPTY_SCAN);
    expect(s.status).toBe("ready"); // paused, NOT exhausted (server may have more)
    expect(s.inFlight).toBe(false);
    expect(s.items).toHaveLength(0);
  });

  it("a zero-new-card page with no more pages is exhausted", () => {
    const ready = fetchPage(initialPoolState(), [fut(1)], true);
    let s = reducePool(ready, { type: "START_LOAD" });
    s = reducePool(s, { type: "PAGE_OK", gen: s.gen, items: [], hasMore: false, pageSize: PAGE });
    expect(s.status).toBe("exhausted");
  });
});

describe("reducePool — request failure and retry", () => {
  it("failure surfaces a retryable error and retains the prior deck", () => {
    const ready = fetchPage(initialPoolState(), [fut(1), ev(2)], true);
    let s = reducePool(ready, { type: "START_LOAD" });
    s = reducePool(s, { type: "PAGE_ERR", gen: s.gen });
    expect(s.status).toBe("error");
    expect(s.inFlight).toBe(false);
    expect(s.items).toHaveLength(2); // deck preserved
  });

  it("initial-load failure never claims exhaustion", () => {
    let s = reducePool(initialPoolState(), { type: "START_LOAD" });
    s = reducePool(s, { type: "PAGE_ERR", gen: s.gen });
    expect(s.status).toBe("error");
    expect(s.status).not.toBe("exhausted");
  });

  it("retry after error recovers to ready", () => {
    let s = reducePool(initialPoolState(), { type: "START_LOAD" });
    s = reducePool(s, { type: "PAGE_ERR", gen: s.gen });
    s = fetchPage(s, [fut(1)], true); // retry = START_LOAD + PAGE_OK
    expect(s.status).toBe("ready");
    expect(s.items).toHaveLength(1);
  });
});

describe("reducePool — cancellation via generation token", () => {
  it("ignores a PAGE_OK from a superseded request", () => {
    const s = reducePool(initialPoolState(), { type: "START_LOAD" });
    const stale: PlayPoolAction = {
      type: "PAGE_OK",
      gen: s.gen + 1, // came from a different generation (unmounted/superseded)
      items: [fut(9)],
      hasMore: true,
      pageSize: PAGE,
    };
    expect(reducePool(s, stale)).toBe(s); // unchanged
  });

  it("ignores a PAGE_ERR from a superseded request", () => {
    const s = reducePool(initialPoolState(), { type: "START_LOAD" });
    expect(reducePool(s, { type: "PAGE_ERR", gen: s.gen + 1 })).toBe(s);
  });
});

describe("decidePlayView — the single honest terminal", () => {
  const base = { status: "ready" as const, hasMore: true, scanAttempts: 0, maxScan: 6 };

  it("a usable card always plays", () => {
    expect(decidePlayView({ ...base, usableCount: 1 })).toBe("play");
    // even mid-load, an available card keeps playing (no false spinner)
    expect(decidePlayView({ ...base, usableCount: 3, status: "loading" })).toBe("play");
  });

  it("no usable card while a request is in flight → loading", () => {
    expect(decidePlayView({ ...base, usableCount: 0, status: "loading" })).toBe("loading");
  });

  it("no usable card after a failed request → error", () => {
    expect(decidePlayView({ ...base, usableCount: 0, status: "error" })).toBe("error");
  });

  it("safe-but-unusable page with more pages left → scan", () => {
    expect(decidePlayView({ ...base, usableCount: 0 })).toBe("scan");
  });

  it("scan stops at the cap → scan_paused, NEVER caught_up while has_more=true", () => {
    // C39 P2: reaching the client scan bound must not lie "all caught up" while
    // the server still reports more pages.
    const v = decidePlayView({ ...base, usableCount: 0, scanAttempts: 6 });
    expect(v).toBe("scan_paused");
    expect(v).not.toBe("caught_up");
  });

  it("zero usable questions with has_more=false → caught_up", () => {
    expect(decidePlayView({ ...base, usableCount: 0, hasMore: false })).toBe("caught_up");
  });

  it("exhausted pool → caught_up", () => {
    expect(decidePlayView({ ...base, usableCount: 0, status: "exhausted", hasMore: false })).toBe("caught_up");
  });
});

describe("itemKey — malformed identity is rejected, never collapsed (C39 P2)", () => {
  it("returns null for a card with no id/key instead of a shared sentinel", () => {
    const noId = { type: "futures", score: 1, reason: "", headline: null, data: {} } as unknown as FeedItem;
    const alsoNoId = { type: "futures", score: 1, reason: "", headline: null, data: { id: null } } as unknown as FeedItem;
    expect(itemKey(noId)).toBeNull();
    expect(itemKey(alsoNoId)).toBeNull();
  });

  it("keeps numeric and string ids distinct", () => {
    const numId = fut(7);
    const strId = { type: "futures", score: 1, reason: "", headline: null, data: { id: "7" } } as unknown as FeedItem;
    expect(itemKey(numId)).not.toBe(itemKey(strId));
  });

  it("PAGE_OK counts malformed cards observably and admits only identified ones", () => {
    const bad = { type: "futures", score: 1, reason: "", headline: null, data: {} } as unknown as FeedItem;
    const s = fetchPage(initialPoolState(), [fut(1), bad, ev(2), bad], true);
    expect(s.items).toHaveLength(2); // only fut(1) + ev(2)
    expect(s.malformed).toBe(2); // both id-less cards surfaced, not silently deduped
  });
});

describe("reducePool — REFRESH restarts at page zero without replaying consumed cards", () => {
  it("resets offset/emptyScan, bumps generation, keeps seen", () => {
    const ready = fetchPage(initialPoolState(), [fut(1), ev(2)], true);
    expect(ready.offset).toBe(PAGE);
    const refreshed = reducePool(ready, { type: "REFRESH" });
    expect(refreshed.offset).toBe(0);
    expect(refreshed.status).toBe("loading");
    expect(refreshed.inFlight).toBe(true);
    expect(refreshed.gen).toBe(ready.gen + 1);
    expect(refreshed.seen.size).toBe(2); // consumed identities preserved
    expect(refreshed.items).toHaveLength(2); // last-good deck preserved
  });

  it("a refresh page re-serving old cards adds nothing; a NEW first-page card lands", () => {
    let s = fetchPage(initialPoolState(), [fut(1), ev(2)], false); // exhausted
    expect(s.status).toBe("exhausted");
    s = reducePool(s, { type: "REFRESH" });
    // Newest-first: a brand-new card appears before the consumed ones on page 0.
    s = reducePool(s, { type: "PAGE_OK", gen: s.gen, items: [fut(9), fut(1), ev(2)], hasMore: false, pageSize: PAGE });
    expect(s.items.map((it) => itemKey(it))).toEqual([
      itemKey(fut(1)),
      itemKey(ev(2)),
      itemKey(fut(9)), // only the genuinely new card was appended
    ]);
  });

  it("REFRESH is ignored while a page is in flight", () => {
    const loading = reducePool(initialPoolState(), { type: "START_LOAD" });
    expect(reducePool(loading, { type: "REFRESH" })).toBe(loading);
  });
});

describe("validatePage — pagination contract is typed, not truthiness-coerced (C39 P2)", () => {
  it("accepts a well-formed page", () => {
    const p = validatePage({ items: [fut(1)], has_more: true });
    expect(p.items).toHaveLength(1);
    expect(p.hasMore).toBe(true);
  });

  it("rejects a missing/null has_more instead of faking exhaustion", () => {
    expect(() => validatePage({ items: [] })).toThrow(PlayPageContractError);
    expect(() => validatePage({ items: [], has_more: null })).toThrow(PlayPageContractError);
  });

  it("rejects a string has_more instead of scanning past the end", () => {
    expect(() => validatePage({ items: [], has_more: "false" })).toThrow(PlayPageContractError);
  });

  it("rejects a non-array items payload", () => {
    expect(() => validatePage({ items: null, has_more: true })).toThrow(PlayPageContractError);
    expect(() => validatePage({ has_more: true })).toThrow(PlayPageContractError);
  });
});

describe("integration — events-only page then a later futures page", () => {
  it("Higher/Lower scans past an events-only page and lands on questions", () => {
    // Page 1: kid-safe events only → cards land, but zero usable questions.
    let s = fetchPage(initialPoolState(), [ev(1), ev(2)], true);
    expect(s.status).toBe("ready");
    const usableAfterP1 = s.items.filter((it) => it.type === "futures").length;
    expect(usableAfterP1).toBe(0);
    // The mode, seeing 0 usable + ready + hasMore, asks for more (scan).
    expect(
      decidePlayView({ usableCount: usableAfterP1, status: s.status, hasMore: s.hasMore, scanAttempts: 0, maxScan: 6 })
    ).toBe("scan");
    // Page 2 carries a futures question.
    s = fetchPage(s, [fut(3)], true);
    const usableAfterP2 = s.items.filter((it) => it.type === "futures").length;
    expect(usableAfterP2).toBe(1);
    expect(
      decidePlayView({ usableCount: usableAfterP2, status: s.status, hasMore: s.hasMore, scanAttempts: 1, maxScan: 6 })
    ).toBe("play");
  });
});
