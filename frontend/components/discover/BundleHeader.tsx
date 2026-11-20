"use client";

import { useState } from "react";
import { CATEGORY_GRADIENTS, getCat } from "./constants";

interface BundleHeaderProps {
  /** The bundle's category/theme label, printed as the eyebrow. */
  title: string;
  /** The question every member answers; the card's heading when present. */
  sharedQuestion?: string | null;
  /** Printed beside the eyebrow only when there is no shared question (old cached payloads). */
  fallbackCount: string;
  /** `llm_sport_category` of the first member — picks the eyebrow's emoji. */
  category: string | null | undefined;
  /** #12825 — resolved bundle banner image URL so every Discover story/group card is visual. */
  imageUrl?: string | null;
  imagePresentation?: string | null;
  expanded: boolean;
  canExpand: boolean;
  onToggle: () => void;
}

const MUSIC_BUNDLE_TITLE_RE = /\b(grammys?|latin\s+grammys?|album|song\s+of\s+the\s+year|spotify|billboard)\b/i;

/**
 * #9642 — the header both bundle cards share (selected design A, Alex 9/29).
 *
 * A group reads as one subject with its questions underneath: a small eyebrow
 * naming the category, then the shared question as the card's heading, on the
 * card's own white rather than a tinted band. The two bundle cards carried
 * identical header markup that had to be kept in step by hand (#6929 fixed the
 * same chip defect twice); one component is what keeps them one card family
 * (notice 35).
 */
export function BundleHeader({
  title,
  sharedQuestion,
  fallbackCount,
  category,
  imageUrl,
  imagePresentation,
  expanded,
  canExpand,
  onToggle,
}: BundleHeaderProps) {
  const [imgErrored, setImgErrored] = useState(false);
  const catStyle = getCat(category);
  const eyebrowEmoji = MUSIC_BUNDLE_TITLE_RE.test(title) ? "🎵" : catStyle.emoji;
  const effectiveImageUrl = imgErrored ? null : imageUrl?.trim() || null;
  const bgGradient =
    CATEGORY_GRADIENTS[category?.toLowerCase() ?? ""] ||
    "linear-gradient(135deg, #0f172a, #1e293b)";

  return (
    <div className="w-full">
      {effectiveImageUrl && (
        <div
          className="relative h-36 w-full overflow-hidden border-b border-surface-border"
          style={{ background: bgGradient }}
          data-testid="bundle-hero-banner"
        >
          <img
            src={effectiveImageUrl}
            alt=""
            aria-hidden="true"
            loading="lazy"
            decoding="async"
            onError={() => setImgErrored(true)}
            className={
              imagePresentation === "logo"
                ? "mx-auto h-full w-24 object-contain py-3 drop-shadow-md"
                : imagePresentation === "cover"
                  ? "mx-auto h-full w-28 object-contain py-2.5 drop-shadow-lg"
                  : imagePresentation === "portrait" &&
                      effectiveImageUrl.includes("espncdn.com/i/headshots/")
                    ? "mx-auto h-full w-40 object-contain object-bottom pt-2 drop-shadow-lg"
                    : imagePresentation === "portrait"
                      ? "h-full w-full object-cover object-top"
                      : "h-full w-full object-cover object-center"
            }
            data-testid="bundle-hero-image"
          />
        </div>
      )}
      <button
        type="button"
        onClick={onToggle}
        disabled={!canExpand}
        aria-expanded={canExpand ? expanded : undefined}
        className={`w-full flex items-start justify-between gap-3 px-4 pt-3.5 pb-3 text-left transition-colors ${canExpand ? "hover:bg-surface-elevated/40" : "cursor-default"}`}
      >
        <div className="flex flex-col gap-1.5 min-w-0">
          <span className="flex items-center gap-2 min-w-0">
            {/* #6929 — `title` is not always a short category word (a 45-character
                tournament name arrives here), so the eyebrow must be able to shrink
                and ellipsise: `min-w-0` lets the flex item shrink, `truncate` makes
                the shortfall legible, `max-w-full` caps it against the card. */}
            <span
              data-testid="bundle-eyebrow"
              className="text-[10px] font-bold uppercase tracking-wider text-text-secondary min-w-0 max-w-full truncate"
            >
              {eyebrowEmoji} {title}
            </span>
            {!sharedQuestion && (
              <span className="text-xs text-text-muted whitespace-nowrap">{fallbackCount}</span>
            )}
          </span>
          {sharedQuestion && (
            <span className="text-[17px] font-bold text-text-primary leading-tight tracking-tight">{sharedQuestion}</span>
          )}
        </div>
        {canExpand && (
          <svg className={`w-4 h-4 mt-0.5 text-text-muted shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>
    </div>
  );
}
