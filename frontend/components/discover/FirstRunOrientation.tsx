import { BRAND_TAGLINE } from "@/lib/brandCopy";

/**
 * Queue 309 Item 1 — one quiet line between the Discover header and the feed,
 * for a first-run anonymous reader only. It answers "what ARE these numbers?"
 * before the reader has to infer it from a grid of percentages.
 *
 * Presentational on purpose: the cohort decision and its persistence live in
 * lib/discoverFirstRun.ts and the page, never in here. There is no dismiss
 * affordance and no timer — the line is spent by engagement, not by waiting.
 */
export default function FirstRunOrientation({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="max-w-7xl mx-auto px-4 pt-3" data-testid="discover-orientation">
      <p className="text-[12px] leading-relaxed text-text-muted">{BRAND_TAGLINE}</p>
    </div>
  );
}
