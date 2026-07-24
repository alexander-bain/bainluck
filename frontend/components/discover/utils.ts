import type {
  FeedItem,
  FeedEventData,
  FeedFuturesData,
  FeedConceptData,
  FeedTournamentData,
} from "@/lib/types";
import { marketEventKey, tournamentEventKey, eventPath } from "@/lib/eventKey";

// L2-175 Item 1: the single detail destination for a feed card, mirroring each leaf
// card's own <Link href>. Used for whole-card tap navigation so the hero (which is
// NOT a link) is clickable, not just the small title. Returns null for card types
// that own their internal navigation (bundles/groups/comparison sub-links).
export function feedItemHref(item: FeedItem): string | null {
  switch (item.type) {
    case "event": {
      const d = item.data as FeedEventData;
      return d?.id != null ? `/events/${d.id}` : null;
    }
    case "futures": {
      const d = item.data as FeedFuturesData;
      const conceptKey = marketEventKey(d);
      if (conceptKey) return eventPath(conceptKey);
      return d?.id != null ? `/futures/${d.id}` : null;
    }
    case "concept": {
      const d = item.data as FeedConceptData;
      return d?.key ? eventPath(d.key) : null;
    }
    case "tournament": {
      const d = item.data as FeedTournamentData;
      const key = tournamentEventKey(d);
      return key ? eventPath(key) : "/sport/golf";
    }
    default:
      return null;
  }
}

export function resolvesLabel(d: string | null | undefined): string {
  if (!d) return "";
  const date = new Date(d);
  const diffH = (date.getTime() - Date.now()) / 36e5;
  if (diffH < 0) return "Resolved";
  if (diffH < 1) return `Closes in ${Math.max(1, Math.round(diffH * 60))}m`;
  if (diffH < 24) return `Closes in ${Math.round(diffH)}h`;
  if (diffH < 48) return "Closes tomorrow";
  if (diffH < 168) return `Closes ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  // Beyond 7 days: don't show on the card (available in detail view)
  return "";
}

/**
 * L2-164 Item 3 — 0% card display guard (web parity with #240's native
 * suppression). A default futures card's hero is its LEADING outcome's
 * probability; a leader sitting below 1% renders as a bare, live-looking "0%" —
 * the stale post-Open golf-card class Alex flagged. This is the belt-and-
 * suspenders DISPLAY check (the real ranking-side suppression is #240's backend):
 * a futures card is suppressed when its leader is sub-1% AND it carries no
 * settled/resolved context to label the number honestly.
 *
 * Never suppresses:
 *  - distribution / heatmap formats — they render a ladder (with "—" for zeros),
 *    not a bare live hero, so a low leader reads fine there.
 *  - settled markets — a resolved flag, a named winner, a settled status, or a
 *    past resolution_date already give the card a "Resolved" label, so the low
 *    number is contextual, not bare-live.
 * Non-futures items are never affected.
 */
export function suppressBareZeroFuturesCard(
  item: FeedItem,
  now: number = Date.now(),
): boolean {
  if (item.type !== "futures") return false;
  const data = item.data as FeedFuturesData;
  // `discover_card` isn't in the shared FeedFuturesData type yet (same loose access
  // as DiscoverCard/FuturesCard); read it via a narrow local cast to stay
  // self-contained and avoid editing lib/types.ts.
  const format = (data as { discover_card?: { suggested_format?: string } }).discover_card
    ?.suggested_format;
  // Ladder-style formats don't show a bare hero number — leave them alone.
  if (format === "outcome_distribution" || format === "threshold_heatmap") return false;
  const leaderProb = data.top_outcomes?.[0]?.probability ?? null;
  // Only the sub-1% ("0%" when rounded) leader is the problem; a null leader
  // already renders name-only (no bare hero), so it's fine.
  if (leaderProb == null || leaderProb >= 0.01) return false;
  const status = (data.status || "").toLowerCase();
  const settledByState =
    data.resolved === true ||
    !!data.winner ||
    ["resolved", "closed", "settled", "finalized", "final"].includes(status);
  const settledByDate =
    !!data.resolution_date && new Date(data.resolution_date).getTime() < now;
  return !(settledByState || settledByDate);
}

export function isTrending(item: FeedItem): boolean {
  if (item.type === "futures") {
    const m = (item.data as FeedFuturesData).top_outcomes?.[0]?.movement;
    return !!m && Math.abs(m) >= 0.05;
  }
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    return ed.status === "live" || (ed.ei?.score ?? 0) >= 70;
  }
  return false;
}

export function feedContextSnippet(item: FeedItem): string {
  if (item.context_summary) return item.context_summary;
  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    return item.headline || item.reason || data.hook_description || "";
  }
  return item.headline || item.reason || "";
}

export function feedExpandedContext(item: FeedItem): string {
  const snippet = feedContextSnippet(item);
  const candidates: string[] = [];

  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    if (data.hook_description) candidates.push(data.hook_description);
  }
  if (item.reason) candidates.push(item.reason);

  // Expanded must be a superset: start with the full snippet text,
  // then append any distinct additional context that isn't already
  // contained within the snippet (near-duplicate check via word overlap).
  const snippetWords = new Set(snippet.trim().replace(/\s+/g, " ").toLowerCase().split(/\s+/));
  const extras = candidates.filter((c) => {
    const norm = c.trim().replace(/\s+/g, " ").toLowerCase();
    if (norm.length <= 10) return false;
    const candidateWords = norm.split(/\s+/);
    const overlap = candidateWords.filter((w) => snippetWords.has(w)).length;
    const ratio = overlap / Math.max(candidateWords.length, 1);
    return ratio < 0.7; // less than 70% word overlap = genuinely distinct
  });

  if (extras.length > 0) {
    return snippet + " — " + extras[0];
  }
  return snippet;
}

const CONTEXT_PREVIEW_CHARS = 145;

export function sentencePreview(text: string, maxChars = CONTEXT_PREVIEW_CHARS): string {
  const trimmed = text.trim().replace(/\s+/g, " ");
  if (trimmed.length <= maxChars) return trimmed;
  const sentenceEnd = trimmed.slice(0, maxChars + 1).search(/[.!?]\s/);
  if (sentenceEnd >= 64) return trimmed.slice(0, sentenceEnd + 1);
  const cut = trimmed.slice(0, maxChars);
  const wordBoundary = cut.lastIndexOf(" ");
  return `${cut.slice(0, wordBoundary > 80 ? wordBoundary : maxChars).trim()}...`;
}

export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("bainluck_session_id");
  if (!id) {
    id = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("bainluck_session_id", id);
  }
  return id;
}

export function generateThreshold(actualProb: number): number {
  const minGap = 0.10;
  // Randomly go higher or lower, at least 10% away
  const goHigher = Math.random() > 0.5;
  const offset = minGap + Math.random() * 0.15; // 10-25% away
  let threshold = goHigher ? actualProb + offset : actualProb - offset;
  // Clamp to 5%-95% range
  threshold = Math.max(0.05, Math.min(0.95, threshold));
  // Ensure still at least 10% away after clamping
  if (Math.abs(threshold - actualProb) < minGap) {
    threshold = actualProb > 0.5 ? actualProb - offset : actualProb + offset;
    threshold = Math.max(0.05, Math.min(0.95, threshold));
  }
  return Math.round(threshold * 100);
}
