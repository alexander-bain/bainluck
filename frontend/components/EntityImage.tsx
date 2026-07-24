"use client";

import { useState, useEffect } from "react";
import {
  espnHeadshotUrl,
  sportKeyToEspnHeadshotSport,
  getWikipediaImage,
  flagUrl,
} from "@/lib/images";

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
  fallbackColor = "#6B7280",
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

  // Fallback: colored initial circle
  const initials = name
    .split(" ")
    .map((w) => w.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div
      className={`rounded-full flex-shrink-0 flex items-center justify-center font-bold text-white/90 ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: fallbackColor,
        fontSize: Math.max(8, size * 0.38),
      }}
    >
      {initials}
    </div>
  );
}
