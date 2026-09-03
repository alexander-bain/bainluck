// The icon beside an event-concept card's domain label (#2711).
//
// THE DEFECT. `FeedCard`'s concept arm hardcoded 🥊 and printed
// `data.domain?.toUpperCase()` next to it, so every concept card wore a boxing
// glove whatever it was about. The component was written for UFC and boxing
// cards and was never generalised when the cycling, F1 and golf concept
// adapters were added, so "🥊 CYCLING" over the Vuelta a España and "🥊 F1" over
// the Dutch Grand Prix are not a mapping miss — there was no mapping.
//
// A concept's `domain` is its event-key namespace (`event:<domain>:<slug>`), NOT
// a category, so the two vocabularies do not line up: the combat adapter emits
// `ufc`, the category map calls it `mma`; the F1 adapter emits `f1`, the
// category map calls it `motorsports`. This is that alias, kept small and in one
// place so the emojis themselves stay in `CATEGORY_COLORS` and cannot fork.

import { getCat } from "@/components/discover/constants";

/**
 * Concept domains whose name differs from the category that owns their emoji.
 * A domain absent here is looked up under its own name.
 */
const DOMAIN_TO_CATEGORY: Record<string, string> = {
  ufc: "mma",
  f1: "motorsports",
};

/**
 * The emoji for a concept card's domain.
 *
 * Falls through to `getCat`'s DEFAULT_CAT (📊) for a domain nothing knows —
 * which is the point of routing through it. A generic chart is uninformative;
 * a boxing glove over a bike race is wrong, and wrong is the worse of the two.
 */
export function conceptDomainIcon(domain: string | null | undefined): string {
  if (!domain) return getCat(null).emoji;
  const key = domain.toLowerCase();
  return getCat(DOMAIN_TO_CATEGORY[key] ?? key).emoji;
}
