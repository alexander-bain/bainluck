// L2-173 — Team-cluster adjudication session state machine (pure).
//
// #247's team-identity merge auto-folds only the clean stubs and SKIPS ~189
// ambiguous clusters (espn_id collisions, real-team lookalikes). This is the
// Alex-speed queue for those: one cluster at a time, keyboard verdicts
// (m/k/d), a live progress strip, one-key undo, and OPTIMISTIC advance (the
// next cluster slides in the instant a key is pressed — the POST reconciles in
// the background).
//
// Mirrors labelPassSession.ts: jest env is 'node', so the velocity logic lives
// here as pure functions and the page (page.tsx) is a thin wiring shell. Guard
// tests target this module directly.

export type Verdict = "merge" | "keep_separate" | "defer";
export type SessionAction = Verdict | "undo" | "prev" | "next";

// One committed (or in-flight) verdict. `uid` is a client-stable id so the
// background POST can reconcile / roll back the exact entry it created.
export interface VerdictEntry {
  uid: number;
  clusterKey: string;
  verdict: Verdict;
  reversible: boolean; // false for merge (FKs already re-pointed, stub deleted)
  pending: boolean; // POST still in flight (optimistic)
}

export interface SessionState {
  index: number;
  history: VerdictEntry[];
}

export const INITIAL_SESSION: SessionState = { index: 0, history: [] };

// Keyboard bindings. m/k/d verdicts, u undo, arrows navigate without a verdict.
export function keyToAction(key: string): SessionAction | null {
  switch (key) {
    case "m":
    case "M":
      return "merge";
    case "k":
    case "K":
      return "keep_separate";
    case "d":
    case "D":
      return "defer";
    case "u":
    case "U":
      return "undo";
    case "ArrowRight":
      return "next";
    case "ArrowLeft":
      return "prev";
    default:
      return null;
  }
}

// merge is terminal (data re-pointed); keep/defer are reversible records.
export function isReversible(verdict: Verdict): boolean {
  return verdict !== "merge";
}

// Optimistic advance: append the verdict and step to the next cluster immediately.
export function recordVerdict(state: SessionState, entry: VerdictEntry): SessionState {
  return { index: state.index + 1, history: [...state.history, entry] };
}

// Background POST resolved — clear the pending flag on the matching entry.
export function reconcileVerdict(state: SessionState, uid: number): SessionState {
  return {
    ...state,
    history: state.history.map((h) => (h.uid === uid ? { ...h, pending: false } : h)),
  };
}

// Background POST failed — drop the phantom entry. If it was the most recent
// verdict, step the pointer back so the cluster is re-shown for a retry.
export function rollbackVerdict(state: SessionState, uid: number): SessionState {
  const idx = state.history.findIndex((h) => h.uid === uid);
  if (idx === -1) return state;
  const isTail = idx === state.history.length - 1;
  return {
    index: isTail ? Math.max(0, state.index - 1) : state.index,
    history: state.history.filter((h) => h.uid !== uid),
  };
}

// Undo the most recent verdict: pop it and step the pointer back so the cluster
// reappears. Returns the popped entry so the caller can DELETE its server row.
export function undoLast(state: SessionState): {
  state: SessionState;
  undone: VerdictEntry | null;
} {
  if (state.history.length === 0) return { state, undone: null };
  const undone = state.history[state.history.length - 1];
  return {
    state: {
      index: Math.max(0, state.index - 1),
      history: state.history.slice(0, -1),
    },
    undone,
  };
}

// Arrow navigation: move the pointer without recording a verdict, bounded to
// [0, total] (total == the completion sentinel position).
export function navigate(
  state: SessionState,
  dir: "prev" | "next",
  total: number
): SessionState {
  const next = dir === "next" ? state.index + 1 : state.index - 1;
  const clamped = Math.max(0, Math.min(next, total));
  return { ...state, index: clamped };
}

export interface SessionTotals {
  reviewed: number;
  merged: number;
  kept: number;
  deferred: number;
}

export function sessionTotals(state: SessionState): SessionTotals {
  const t: SessionTotals = { reviewed: 0, merged: 0, kept: 0, deferred: 0 };
  for (const h of state.history) {
    t.reviewed += 1;
    if (h.verdict === "merge") t.merged += 1;
    else if (h.verdict === "keep_separate") t.kept += 1;
    else if (h.verdict === "defer") t.deferred += 1;
  }
  return t;
}

// "14 of 189 · 6 merged · 5 kept" (deferred appended only when non-zero).
export function progressLabel(state: SessionState, total: number): string {
  const t = sessionTotals(state);
  const parts = [`${t.reviewed} of ${total}`, `${t.merged} merged`, `${t.kept} kept`];
  if (t.deferred > 0) parts.push(`${t.deferred} deferred`);
  return parts.join(" · ");
}
