"use client";

// L2-113 combat concept-page polish — fighter avatars. UFC/boxing fighters have no
// ESPN athlete-id bridge (unlike team logos), so we resolve a headshot the same way
// the rest of the app resolves person images: the free, CORS-friendly Wikipedia
// thumbnail API (lib/images.getWikipediaImage), localStorage-cached, with an
// initials-avatar fallback so a missing image never leaves a blank hole. Fully
// client-side — no backend enrichment task (keeps this off the shared beat schedule).

import { useEffect, useState } from "react";
import { getWikipediaImage } from "@/lib/images";

/** First-letter(s) initials for the fallback avatar (e.g. "Dricus Du Plessis" → "DD"). */
function initialsOf(name: string): string {
  const parts = (name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

interface FighterAvatarProps {
  name: string;
  /** px diameter (default 36). */
  size?: number;
  /** Dim a decided/settled fighter's avatar. */
  dim?: boolean;
}

export default function FighterAvatar({ name, size = 36, dim = false }: FighterAvatarProps) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setUrl(null);
    if (!name) return;
    getWikipediaImage(name)
      .then((u) => {
        if (!cancelled) setUrl(u);
      })
      .catch(() => {
        /* fall through to initials */
      });
    return () => {
      cancelled = true;
    };
  }, [name]);

  const dim_ = dim ? "opacity-60" : "";
  const dimension = { width: size, height: size };

  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={name}
        style={dimension}
        className={`rounded-full object-cover bg-surface-elevated shrink-0 ${dim_}`}
        loading="lazy"
      />
    );
  }

  return (
    <div
      style={{ ...dimension, fontSize: Math.round(size * 0.36) }}
      className={`rounded-full bg-surface-elevated text-text-secondary font-semibold flex items-center justify-center shrink-0 select-none ${dim_}`}
      aria-label={name}
      title={name}
    >
      {initialsOf(name)}
    </div>
  );
}
