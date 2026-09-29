import { parseFoldRevision } from "./foldRevision";

/** Quote transport eligibility is separate from the sporting phase. The server
 * remains authoritative for mapped, unresolved contracts and producer windows. */
export function isQuoteStreamStatus(status: string | null | undefined): boolean {
  return status === "live" || status === "scheduled" || status === "suspended";
}

export function canSubscribeEventQuotes(event: {
  status?: string | null; completed_at?: string | null;
} | null | undefined): boolean {
  return !!event && isQuoteStreamStatus(event.status) && !event.completed_at;
}

/** The read must contain every triggering row at or beyond its commit. Extra
 * fold members are allowed: a canonical invalidation can reveal a new twin. */
export function coversQuoteRevision(read: unknown, trigger: unknown): boolean {
  const wanted = parseFoldRevision(trigger);
  if (!wanted) return true;
  const actual = parseFoldRevision(read);
  return !!actual && Object.entries(wanted).every(([row, revision]) =>
    actual[row] !== undefined && actual[row] >= revision);
}

/** Both fresh responses arrive before the opening/nonblend presentation changes.
 * A history with no pinned blend makes no current-blend revision claim. */
export function quotePairCoversTrigger(
  detail: { id: number; status?: string | null; blend_fold_revision?: unknown },
  history: { event_id: number; blend_edge_pinned?: boolean | null; blend_edge_fold_revision?: unknown },
  eventId: number, trigger: unknown,
): boolean {
  if (detail.id !== eventId || history.event_id !== eventId) return false;
  // The authoritative terminal response always wins; do not hold an opening
  // forecast in front of a result while waiting for a quote revision.
  if (!isQuoteStreamStatus(detail.status)) return true;
  return coversQuoteRevision(detail.blend_fold_revision, trigger) &&
    (!history.blend_edge_pinned || coversQuoteRevision(history.blend_edge_fold_revision, trigger));
}
