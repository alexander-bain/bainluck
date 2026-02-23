"use client";

/**
 * Shared personalization badge component.
 * Shows "Your team", "Local", "Alma mater", etc. on feed items
 * that have been boosted by the personalization system.
 *
 * Used by: FeedCard, EventCard, FuturesCard
 */

interface PersonalizedBadgeProps {
  personalized?: boolean;
  multiplier?: number;
  personalizationReasons?: string[];
}

export function getPersonalizationLabel(reasons?: string[]): string {
  if (!reasons || reasons.length === 0) return "For you";

  for (const r of reasons) {
    if (r.startsWith("your_team")) return "Your team";
    if (r.startsWith("rival_losing")) return "Rival losing";
    if (r.startsWith("rival")) return "Rival watch";
    if (r.startsWith("local_team")) return "Local";
    if (r.startsWith("alma_mater")) return "Alma mater";
    if (r.startsWith("pinned")) return "Pinned";
    if (r.startsWith("sport_boost")) return "For you";
  }

  return "For you";
}

export default function PersonalizedBadge({
  personalized,
  multiplier,
  personalizationReasons,
}: PersonalizedBadgeProps) {
  if (!personalized) return null;

  const label = getPersonalizationLabel(personalizationReasons);

  return (
    <span
      className="inline-flex items-center gap-1 bg-accent-brand/15 text-accent-brand px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0"
      title={
        multiplier
          ? `Boosted ${multiplier}x because: ${personalizationReasons?.join(", ")}`
          : undefined
      }
    >
      <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
      {label}
    </span>
  );
}
