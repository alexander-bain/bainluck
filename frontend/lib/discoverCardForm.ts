/**
 * 227-A point 6: the form a Discover card is drawn in, as a data attribute
 * (`data-card-form`) the weekly screen capture reads to count forms, runs and
 * content kinds per phone screen. Attribute only: nothing a reader sees changes.
 */
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";

export function discoverCardForm(item: FeedItem): string {
  if (item.type === "event") return "game";
  if (item.type === "futures") {
    const d = item.data as FeedFuturesData;
    return d.discover_card?.suggested_format === "outcome_distribution" && (d.top_outcomes?.length ?? 0) >= 4
      ? "futures-distribution"
      : "futures";
  }
  if (item.type === "bundle") {
    const d = item.data as FeedBundleData;
    if (d.kind === "roundup") {
      const form = d.roundup?.machinery_card?.form_id;
      return form ? `roundup:${form}` : "roundup";
    }
    return d.kind === "theme" ? "theme" : "comparison";
  }
  return String(item.type);
}
