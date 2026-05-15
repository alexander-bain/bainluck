import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";

export function resolvesLabel(d: string | null | undefined): string {
  if (!d) return "";
  const date = new Date(d);
  const diffH = (date.getTime() - Date.now()) / 36e5;
  if (diffH < 0) return "Resolved";
  if (diffH < 3) return `Resolves in ${Math.round(diffH * 60)}m`;
  if (diffH < 24) return `Resolves in ${Math.round(diffH)}h`;
  if (diffH < 48) return "Resolves tomorrow";
  if (diffH < 168) return `Resolves in ${Math.round(diffH / 24)} days`;
  return `Resolves ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
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
  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    return data.hook_description || item.reason || feedContextSnippet(item);
  }
  return item.reason || feedContextSnippet(item);
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
