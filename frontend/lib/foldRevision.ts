/**
 * #9051 — which of two served blends is NEWER, by the rows it was folded from.
 *
 * The page holds blends other payloads delivered: the detail hero, the history
 * payload's pinned edge, pushed frames. Each is dated by the newest PRICE it
 * folded, and price clocks cannot see a removal: after a source is retired the
 * fresh blend is dated by the survivors' last quote, which can be older than a
 * blend the page already holds that still folds the retired source. Nor can a
 * removal TIMESTAMP order them (Codex, twin-contract/CONTRACT-REVIEW.md): a
 * hero folds its canonical row and its eligible twins, each row commits
 * independently, and `clock_timestamp()` is statement time, not commit order —
 * a twin removal stamped 20 that commits at 40 and a canonical removal stamped
 * 30 that commits at 31 leave "max removal = 30" on both sides of the twin's
 * commit, so the old blend passes as current.
 *
 * So the producer serves a REVISION VECTOR with every blend:
 * `{ "<row id>": rev }` for every row the fold read (contributing or not), where
 * `rev` is bumped by a database trigger on each change to that row's sources.
 * A row lock serialises writers to one row, so each component is that row's
 * commit order; a later read of the database sees every component at least as
 * high. That makes the comparison exact:
 *
 * - `newer` — at least as high on every row, higher on one, same rows. Adopt its
 *   value AND its price clock, even an older one (a removal can leave only an
 *   older surviving quote), and keep its vector.
 * - `same` — the same snapshot; ordinary price ordering decides.
 * - `older` — refuse.
 * - `incomparable` — different rows (a twin joined or left the fold) or mixed
 *   directions: neither can be trusted over the other; keep what is held and
 *   let an authoritative detail read settle it.
 *
 * An absent or malformed vector makes no claim: every pre-contract rule applies,
 * and it never erases a vector the page already holds.
 */

export type FoldRevision = Record<string, number>;

export type FoldOrder = "newer" | "same" | "older" | "incomparable";

/** A served vector, or `null` when it is absent or malformed (no claim). */
export function parseFoldRevision(value: unknown): FoldRevision | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return null;
  for (const [, rev] of entries) {
    // Safe integers only: a JSON number past 2^53 has already been rounded.
    if (typeof rev !== "number" || !Number.isSafeInteger(rev) || rev < 0) return null;
  }
  return value as FoldRevision;
}

/** How `incoming` orders against `held`. Both must be parsed vectors. */
export function compareFoldRevision(incoming: FoldRevision, held: FoldRevision): FoldOrder {
  const rows = Object.keys(held);
  if (Object.keys(incoming).length !== rows.length || rows.some((row) => !(row in incoming))) {
    return "incomparable";
  }
  let higher = false;
  let lower = false;
  for (const row of rows) {
    if (incoming[row] > held[row]) higher = true;
    else if (incoming[row] < held[row]) lower = true;
  }
  if (higher && lower) return "incomparable";
  return higher ? "newer" : lower ? "older" : "same";
}

/**
 * A pushed frame speaks for ONE row's write. It can be ordered against a held
 * blend only when that blend was folded from that one row; a folded hero
 * (canonical + twins) is a value the frame's raw-row aggregate never computed.
 * That holds whether or not the frame carries a vector, so a held folded
 * vector makes every frame `incomparable`. Returns `null` (no claim) when the
 * held blend has no vector, or when it is single-row and the frame has none.
 */
export function frameFoldOrder(held: unknown, frame: unknown): FoldOrder | null {
  const heldRev = parseFoldRevision(held);
  if (!heldRev) return null;
  if (Object.keys(heldRev).length !== 1) return "incomparable";
  const frameRev = parseFoldRevision(frame);
  if (!frameRev) return null;
  if (Object.keys(frameRev).length !== 1) return "incomparable";
  return compareFoldRevision(frameRev, heldRev);
}
