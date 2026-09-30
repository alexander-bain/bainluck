import { ImageResponse } from "next/og";
import { UnfurlCard, accentFor } from "@/components/og/UnfurlCard";
import { fetchCollection } from "@/lib/collections";

export const runtime = "edge";
export const alt = "Bain Luck collection games and questions";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let title = "Collection";
  let subtitle: string | null = null;
  let verdict = "This collection is temporarily unavailable.";
  let category: string | null = null;
  try {
    const hub = await fetchCollection(slug, AbortSignal.timeout(2500));
    title = hub.title ?? title;
    if (hub.state === "published") {
      subtitle = hub.edition;
      category = hub.edition?.startsWith("NFL") ? "football" : "baseball";
      verdict = hub.note ?? "Explore games, results and related questions.";
    } else verdict = hub.note ?? verdict;
  } catch { /* an unavailable read makes no claim about existence */ }
  return new ImageResponse(<UnfurlCard eyebrow="Collection" title={title} subtitle={subtitle} rows={[]} verdict={verdict} accent={accentFor(category)} />, size);
}
