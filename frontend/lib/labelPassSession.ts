// L2-168 — Label Speed Pass session state machine (pure).
//
// The eval queue holds hundreds of `llm_proposed_*` proposals and Alex is the
// only rater. Velocity comes from friction removal: keyboard verdicts, a live
// progress strip, one-key undo, and OPTIMISTIC advance (the next card slides in
// the instant a key is pressed — the POST reconciles in the background).
//
// jest env is 'node', so all the session logic lives here as pure functions and
// the page (page.tsx) is a thin wiring shell over them. Guard tests target this
// module directly (accept → applied-count bump, undo → revert, key bindings,
// kill-switch-off leaves the applied count unchanged).

export type Verdict = "accept" | "reject" | "skip";
export type SessionAction = Verdict | "undo" | "prev" | "next";

// One committed (or in-flight) verdict. `uid` is a client-stable id so the
// background POST can reconcile / roll back the exact row it created optimistically.
export interface VerdictEntry {
  uid: number;
  id: number; // the proposal's DiscoverReviewDecision id (from /pending)
  verdict: Verdict;
  newId?: number; // the created verdict row id (needed for server-side undo)
  applied: boolean; // true only when an Accept applied a live Discover boost
  pending: boolean; // POST still in flight (optimistic)
}

export interface SessionState {
  index: number;
  history: VerdictEntry[];
}

export const INITIAL_SESSION: SessionState = { index: 0, history: [] };

// Keyboard bindings. Primary is a/r/s/u (queue L2-168); j/k are kept as aliases
// for muscle memory, space skips, arrows navigate the pointer without a verdict.
export function keyToAction(key: string): SessionAction | null {
  switch (key) {
    case "a":
    case "A":
    case "j":
    case "J":
      return "accept";
    case "r":
    case "R":
    case "k":
    case "K":
      return "reject";
    case "s":
    case "S":
    case " ":
      return "skip";
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

// Optimistic advance: append the verdict and step to the next card immediately.
export function recordVerdict(state: SessionState, entry: VerdictEntry): SessionState {
  return { index: state.index + 1, history: [...state.history, entry] };
}

// Background POST resolved — patch the matching entry (its server id + whether a
// live boost actually applied) and clear the pending flag.
export function reconcileVerdict(
  state: SessionState,
  uid: number,
  patch: { newId?: number; applied?: boolean }
): SessionState {
  return {
    ...state,
    history: state.history.map((h) =>
      h.uid === uid ? { ...h, ...patch, pending: false } : h
    ),
  };
}

// Background POST failed — drop the phantom entry. If it was the most recent
// verdict, step the pointer back so the card is re-shown for a retry.
export function rollbackVerdict(state: SessionState, uid: number): SessionState {
  const idx = state.history.findIndex((h) => h.uid === uid);
  if (idx === -1) return state;
  const isTail = idx === state.history.length - 1;
  return {
    index: isTail ? Math.max(0, state.index - 1) : state.index,
    history: state.history.filter((h) => h.uid !== uid),
  };
}

// Undo the most recent verdict: pop it and step the pointer back so the card
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
  accepted: number;
  rejected: number;
  skipped: number;
  applied: number; // the live applied-boosts count from THIS session's accepts
}

export function sessionTotals(state: SessionState): SessionTotals {
  const t: SessionTotals = {
    reviewed: 0,
    accepted: 0,
    rejected: 0,
    skipped: 0,
    applied: 0,
  };
  for (const h of state.history) {
    t.reviewed += 1;
    if (h.verdict === "accept") t.accepted += 1;
    else if (h.verdict === "reject") t.rejected += 1;
    else if (h.verdict === "skip") t.skipped += 1;
    if (h.applied) t.applied += 1;
  }
  return t;
}

// "14 of 354 · 9 applied · 2 rejected" (skipped appended only when non-zero).
export function progressLabel(state: SessionState, total: number): string {
  const t = sessionTotals(state);
  const parts = [
    `${t.reviewed} of ${total}`,
    `${t.applied} applied`,
    `${t.rejected} rejected`,
  ];
  if (t.skipped > 0) parts.push(`${t.skipped} skipped`);
  return parts.join(" · ");
}

/**
 * ── WHY A VERDICT CAN BOUNCE, AND WHY THE READER MUST BE TOLD (#1542/#1873) ───
 *
 * `/verdict` refuses, with a typed 409 and no row written, when the card moved
 * between the GET that showed it and the POST that graded it. The session state
 * machine already rolls the optimistic verdict back, so nothing false is
 * recorded — but silently. Alex taps Accept, the same card returns, and nothing
 * on screen says why. A guard whose whole purpose is to protect his label budget
 * cannot spend one of his labels and then decline to explain itself.
 *
 * `adminFetchJSON` throws an Error carrying the response body, so the typed
 * reason is recoverable without changing the shared helper. Substring, not JSON
 * parse: the body is truncated to 300 characters and a truncated JSON does not
 * parse — reaching for `JSON.parse` here is how this returns null in exactly the
 * case it exists for.
 */
export type VerdictRefusal =
  | "card_drifted"
  | "card_fingerprint_missing"
  | "lifecycle_terminal"
  | "lifecycle_past"
  | "market_missing"
  | "proposal_superseded"
  | "duplicate_verdict"
  | "posted_generation_mismatch";

const REFUSALS: VerdictRefusal[] = [
  "card_drifted",
  "card_fingerprint_missing",
  "lifecycle_terminal",
  "lifecycle_past",
  "market_missing",
  "proposal_superseded",
  "duplicate_verdict",
  "posted_generation_mismatch",
];

export function verdictRefusal(err: unknown): VerdictRefusal | null {
  const message = err instanceof Error ? err.message : String(err ?? "");
  if (!message.includes("409")) return null;
  return REFUSALS.find((r) => message.includes(r)) ?? null;
}

/** What to tell the person whose keystroke was refused. */
export function refusalMessage(reason: VerdictRefusal): string {
  switch (reason) {
    case "card_drifted":
      return "This question re-priced while you were reading it — nothing was recorded. The refreshed card is below.";
    case "card_fingerprint_missing":
      return "This page was loaded before the card it posted — nothing was recorded. Reload to grade the current card.";
    case "duplicate_verdict":
      return "This card already has a verdict — nothing was recorded.";
    default:
      return `This card went stale before the verdict landed (${reason}) — nothing was recorded.`;
  }
}
