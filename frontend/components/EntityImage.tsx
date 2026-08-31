"use client";

import { useState, useEffect } from "react";
import {
  espnHeadshotUrl,
  sportKeyToEspnHeadshotSport,
  getWikipediaImage,
  flagUrl,
} from "@/lib/images";

/**
 * The "we have no colour for this" slate. UX-P235 keys the placeholder treatment
 * off this exact value: a caller that passes a REAL colour (a team's own) is giving
 * information and keeps the solid disc; the default is a non-answer and becomes a
 * visible placeholder instead of impersonating a brand mark.
 */
const DEFAULT_FALLBACK_COLOR = "#6B7280";

interface EntityImageProps {
  /** Image source type */
  type: "player" | "wikipedia" | "flag";
  /** Entity name (player name, country name, coin name, person name) */
  name: string;
  /** ESPN player ID — required for type="player" */
  espnId?: string;
  /** Sport key — used for player headshot sport path */
  sport?: string | null;
  /** Fallback background color for initial circle */
  fallbackColor?: string;
  /** Image size in pixels (default 24) */
  size?: number;
  /** Additional CSS class */
  className?: string;
}

/**
 * Shared image component for entity enrichment across futures/events.
 *
 * Renders a circular image with graceful fallback to colored-initial circle.
 * Loads asynchronously for Wikipedia type.
 */
export default function EntityImage({
  type,
  name,
  espnId,
  sport,
  fallbackColor = DEFAULT_FALLBACK_COLOR,
  size = 24,
  className = "",
}: EntityImageProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    // Reset per-identity state so a recycled instance never shows the previous
    // entity's stale image or a sticky `failed` fallback (wrong-face bug). React
    // reuses this component when a list re-orders; without this reset a prior
    // entity whose image 404'd would suppress the new entity's valid image, and
    // the old imageUrl could flash under the new name during the wikipedia await.
    setFailed(false);
    if (type === "wikipedia") {
      setImageUrl(null);
    }

    if (type === "player" && espnId) {
      const espnSport = sportKeyToEspnHeadshotSport(sport ?? null);
      setImageUrl(espnHeadshotUrl(espnId, espnSport));
    } else if (type === "flag") {
      setImageUrl(flagUrl(name));
    } else if (type === "wikipedia") {
      getWikipediaImage(name).then((url) => {
        if (!cancelled) setImageUrl(url);
      });
    }

    return () => {
      cancelled = true;
    };
  }, [type, name, espnId, sport]);

  // Show image if loaded and not failed
  if (imageUrl && !failed) {
    return (
      <img
        src={imageUrl}
        alt={name}
        width={size}
        height={size}
        loading="lazy"
        className={`object-cover flex-shrink-0 ${type === "flag" ? "rounded-sm" : "rounded-full"} ${className}`}
        style={{ width: size, height: size }}
        onError={() => setFailed(true)}
      />
    );
  }

  // UX-P235 (board item 14) — THE FALLBACK NOW LOOKS LIKE A FALLBACK.
  //
  // Alex: *"love that when I click in it tries to show logos for the companies"* —
  // the ambition stays. But the old chip was a SOLID slate disc with bold white
  // initials, which on a row of real brand marks reads as a designed logo tile:
  // Amazon's grey "A" looked like Amazon's mark rather than like "we don't know".
  // A wrong logo is worse than no logo, and a fallback that impersonates one is a
  // quiet version of the same lie.
  //
  // So: a muted outlined chip, not a filled disc. Same size and position, so
  // nothing shifts; visibly a placeholder, so a reader can tell at a glance which
  // rows we actually resolved. `aria-label` says so too, because the initials
  // alone are not an accessible name for the entity.
  //
  // 🔴 UNLESS THE CALLER GAVE US A REAL COLOUR, AND THAT DISTINCTION IS THE POINT.
  // `RelatedFutures` and `TeamPropFamilies` pass a TEAM colour: that disc is not
  // impersonating a logo, it IS information — the team's own colour, which a reader
  // recognises. Only the default slate is a non-answer dressed as an answer, so
  // only the default becomes a placeholder. Both paths keep the same geometry.
  const initials = name
    .split(" ")
    .map((w) => w.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const isPlaceholder = fallbackColor === DEFAULT_FALLBACK_COLOR;

  return (
    <div
      role="img"
      aria-label={isPlaceholder ? `${name} (no logo available)` : name}
      title={name}
      data-testid={isPlaceholder ? "entity-image-placeholder" : "entity-image-initials"}
      className={`rounded-full flex-shrink-0 flex items-center justify-center ${
        isPlaceholder
          ? "font-medium border border-dashed border-surface-border bg-surface-elevated text-text-muted"
          : "font-bold text-white/90"
      } ${className}`}
      style={{
        width: size,
        height: size,
        ...(isPlaceholder ? {} : { backgroundColor: fallbackColor }),
        fontSize: Math.max(8, size * (isPlaceholder ? 0.34 : 0.38)),
      }}
    >
      {initials}
    </div>
  );
}
