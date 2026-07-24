"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Check, Heart, Share2 } from "lucide-react";
import { trackEvent } from "@/lib/analytics";
import { sentencePreview } from "./utils";
import type { ActionBarProps } from "./types";
import {
  CONFIDENCE_TIER_BARS,
  CONFIDENCE_TIER_LABEL,
  CONFIDENCE_TOOLTIP,
  normalizeTier,
  type ConfidenceTier,
} from "@/lib/confidence";

// ── Animated Counter ──

export function AnimatedProbability({ value, className, resolved }: { value: number; className?: string; resolved?: boolean }) {
  const [displayed, setDisplayed] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const animated = useRef(false);

  useEffect(() => {
    if (animated.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !animated.current) {
        animated.current = true;
        const duration = 400; // L2-160 — handoff rule: "400ms probability", no bounce
        const start = performance.now();
        const animate = (now: number) => {
          const elapsed = now - start;
          const progress = Math.min(elapsed / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          setDisplayed(Math.round(value * eased));
          if (progress < 1) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
      }
    }, { threshold: 0.5 });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [value]);

  // If value is 0 on a non-resolved market, the probability is missing/unknown
  if (value === 0 && !resolved) {
    return <span ref={ref} className={className}>&mdash;</span>;
  }

  return <span ref={ref} className={className}>{displayed}<span className="text-3xl">%</span></span>;
}

// ── Movement Badge ──

export function MovementBadge({ m, prob }: { m: number | null | undefined; prob?: number | null }) {
  if (!m || Math.abs(m) < 0.02) return null;
  // L2-160 — respect the 5% placeholder floor: an illiquid outcome rendered at the
  // ~5% minimum is a placeholder, so any "movement" on it is noise, not a signal.
  // (Mirrors the isTrending / eventConcept 0.05 floor.)
  if (prob != null && prob <= 0.05) return null;
  const up = m > 0;
  const pts = Math.abs(Math.round(m * 100));
  // L2-156 Item 3 — the arrow is a 24h PROBABILITY move, not a rank change. Casual
  // fans can't tell without a label, so spell it out on hover / for screen readers.
  const label = `${up ? "Up" : "Down"} ${pts} point${pts === 1 ? "" : "s"} in the last 24h`;
  return (
    <span
      title={label}
      aria-label={label}
      className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${up ? "bg-green-500/15 text-green-600" : "bg-red-500/15 text-red-600"}`}
    >
      <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor" aria-hidden="true">{up ? <path d="M4 1L7 5H1z" /> : <path d="M4 7L1 3h6z" />}</svg>
      {pts}%
    </span>
  );
}

// ── Expandable Context Text ──

export function ExpandableContextText({ text, expandedText, className, onExpand, onCollapse }: {
  text: string;
  expandedText?: string;
  className?: string;
  onExpand?: () => void;
  onCollapse?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const normalizedText = text.trim().replace(/\s+/g, " ");
  const fullText = (expandedText || text).trim().replace(/\s+/g, " ");
  const compact = sentencePreview(normalizedText);
  const canExpand = fullText !== normalizedText || compact !== normalizedText;

  const toggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) onExpand?.();
    else onCollapse?.();
  };

  return (
    <p className={className}>
      {expanded || !canExpand ? fullText : compact}
      {canExpand && (
        <button
          type="button"
          onClick={toggle}
          className="ml-1 text-xs font-semibold text-accent-brand hover:underline"
        >
          {expanded ? "Show less" : "See more"}
        </button>
      )}
    </p>
  );
}

// ── Dismiss Button ──

export function DismissBtn({ onDismiss }: { onDismiss?: () => void }) {
  if (!onDismiss) return null;
  return (
    <button
      onClick={onDismiss}
      title="Less like this"
      aria-label="Less like this"
      className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white/80 hover:text-white hover:bg-black/50 transition-colors"
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
    </button>
  );
}

// ── Trend Badge ──

export function TrendBadge() {
  return (
    <div className="absolute top-3 right-12 z-10 flex items-center gap-1 bg-orange-500/90 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full">
      🔥 Trending
    </div>
  );
}

// ── Temporal Badge ──

const TEMPORAL_BADGE_STYLES: Record<string, { bg: string; text: string }> = {
  Live: { bg: "bg-red-500/90", text: "text-white" },
  "Closing Soon": { bg: "bg-amber-500/90", text: "text-white" },
  New: { bg: "bg-emerald-500/90", text: "text-white" },
};

export function TemporalBadge({ badge }: { badge: string | null | undefined }) {
  if (!badge) return null;
  const style = TEMPORAL_BADGE_STYLES[badge];
  if (!style) return null;
  return (
    <span
      className={[style.bg, style.text, "text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"].join(" ")}
    >
      {badge === "Live" && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-white animate-pulse mr-1 align-middle" />
      )}
      {badge}
    </span>
  );
}

// ── Confidence Signal Bars (#490) ──
// A cell-signal-style 1-3 bar glyph showing how much we trust the probability
// (sources + liquidity + freshness). Alex ruling 2026-07-23: signal bars. Ships
// WITH its own tooltip/aria-label so it's never unexplained chrome. Renders
// nothing when the tier is absent (render-only-where-present).

const CONFIDENCE_TIER_FILL: Record<ConfidenceTier, string> = {
  high: "bg-accent-brand",
  moderate: "bg-accent-brand/70",
  low: "bg-text-muted",
};

export function SignalBars({
  tier,
  className,
}: {
  tier: string | null | undefined;
  className?: string;
}) {
  const t = normalizeTier(tier);
  if (!t) return null;
  const filled = CONFIDENCE_TIER_BARS[t];
  const label = `${CONFIDENCE_TIER_LABEL[t]} — ${CONFIDENCE_TOOLTIP}`;
  // Three ascending bars; filled ones take the tier color, the rest sit muted.
  const heights = ["h-1.5", "h-2.5", "h-3.5"];
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={["inline-flex items-end gap-0.5", className].filter(Boolean).join(" ")}
    >
      {heights.map((h, i) => (
        <span
          key={i}
          className={[
            "w-1 rounded-sm",
            h,
            i < filled ? CONFIDENCE_TIER_FILL[t] : "bg-surface-border",
          ].join(" ")}
        />
      ))}
    </span>
  );
}

// ── Action Bar ──

export function ActionBar({ liked, setLiked, shareUrl, shareTitle, shareText, contentType, itemId, onShare }: ActionBarProps) {
  const [copied, setCopied] = useState(false);

  const trackShare = (method: string) => {
    trackEvent("share", {
      content_type: contentType,
      item_id: itemId,
      method,
      item_name: shareTitle,
      source_section: "discover",
      url: shareUrl,
    }, { immediate: true });
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: shareTitle, text: shareText, url: shareUrl });
        trackShare("native");
        onShare?.();
        return;
      } catch {
        return;
      }
    }

    if (navigator.clipboard?.writeText) {
      const text = shareText ? `${shareText}\n${shareUrl}` : shareUrl;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
      trackShare("clipboard");
      onShare?.();
    }
  };

  return (
    <div className="flex items-center gap-1 mt-3 pt-3 border-t border-surface-border">
      <button onClick={() => setLiked(!liked)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-sm ${liked ? "bg-red-500/10 text-red-500" : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"}`}>
        <Heart size={16} fill={liked ? "currentColor" : "none"} strokeWidth={2} />
        {liked ? "Liked" : "Like"}
      </button>
      <div className="flex-1" />
      <button
        onClick={handleShare}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-elevated transition-colors text-sm"
        title={copied ? "Copied" : "Share"}
        aria-label={copied ? "Copied share link" : "Share this card"}
      >
        {copied ? <Check size={14} strokeWidth={2.4} /> : <Share2 size={14} strokeWidth={2} />}
        {copied ? "Copied" : "Share"}
      </button>
    </div>
  );
}

// ── Swipe Hook ──

// L2-175 Item 1: how far the mouse must move before a press becomes a drag. Below
// this a press is a plain CLICK and must reach the card's link/tap handler — we do
// NOT capture the pointer until a real drag starts (see onPointerDown note).
const DRAG_THRESHOLD_PX = 8;

export function useSwipe(
  onSwipeLeft?: () => void,
  onSwipeRight?: () => void,
  // L2-175 Item 1: a genuine (non-swipe, unmodified) click anywhere on the card.
  // The card body/hero is not itself a link, so without this a plain click on the
  // top Discover cards did NOTHING (only the small title <Link> was clickable, and
  // even that was swallowed by pointer capture). Fires only for real taps.
  onTap?: (e: React.MouseEvent) => void,
) {
  const ref = useRef<HTMLDivElement>(null);
  const startX = useRef(0);
  const currentX = useRef(0);
  const swiping = useRef(false);
  const suppressClick = useRef(false);
  // L2-175 Item 1: the pointerId we captured, or null while none is captured. We
  // defer setPointerCapture until a drag actually starts so plain clicks are not
  // retargeted off the inner <Link> (the dead-click bug).
  const capturedId = useRef<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [swipeAction, setSwipeAction] = useState<"like" | "dismiss" | null>(null);

  const beginSwipe = useCallback((clientX: number) => {
    startX.current = clientX;
    currentX.current = clientX;
    swiping.current = true;
  }, []);

  const updateSwipe = useCallback((clientX: number) => {
    if (!swiping.current) return;
    currentX.current = clientX;
    const dx = currentX.current - startX.current;
    setOffset(dx * 0.5);
    setSwipeAction(dx > 60 ? "like" : dx < -60 ? "dismiss" : null);
  }, []);

  const finishSwipe = useCallback((e?: { preventDefault: () => void; stopPropagation: () => void }) => {
    swiping.current = false;
    const dx = currentX.current - startX.current;
    if (Math.abs(dx) > 80) {
      suppressClick.current = true;
      window.setTimeout(() => {
        suppressClick.current = false;
      }, 350);
      e?.preventDefault();
      e?.stopPropagation();
      if (dx > 80 && onSwipeRight) onSwipeRight();
      else if (dx < -80 && onSwipeLeft) onSwipeLeft();
    }
    setOffset(0);
    setSwipeAction(null);
  }, [onSwipeLeft, onSwipeRight]);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    beginSwipe(e.touches[0].clientX);
  }, [beginSwipe]);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    updateSwipe(e.touches[0].clientX);
  }, [updateSwipe]);

  const onTouchEnd = useCallback((e: React.TouchEvent) => {
    finishSwipe(e);
  }, [finishSwipe]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "touch") return;
    beginSwipe(e.clientX);
    // L2-175 Item 1: do NOT setPointerCapture here. Capturing on pointerdown makes
    // Chromium retarget the subsequent `click` to this wrapper div, so the inner
    // Next.js <Link> never receives it — plain-click was dead while ctrl-click (a
    // native modified activation) still worked. Capture is deferred to the first
    // real drag in onPointerMove.
  }, [beginSwipe]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "touch") return;
    if (!swiping.current) return;
    // Once the press moves past the drag threshold it's a swipe, not a click:
    // capture the pointer so the drag keeps tracking if it leaves the card.
    if (capturedId.current === null) {
      const dx = Math.abs(e.clientX - startX.current);
      if (dx > DRAG_THRESHOLD_PX) {
        ref.current?.setPointerCapture?.(e.pointerId);
        capturedId.current = e.pointerId;
      }
    }
    updateSwipe(e.clientX);
  }, [updateSwipe]);

  const releaseCapture = useCallback(() => {
    if (capturedId.current !== null) {
      ref.current?.releasePointerCapture?.(capturedId.current);
      capturedId.current = null;
    }
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "touch") return;
    finishSwipe(e);
    releaseCapture();
  }, [finishSwipe, releaseCapture]);

  const onPointerCancel = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "touch") return;
    swiping.current = false;
    setOffset(0);
    setSwipeAction(null);
    releaseCapture();
  }, [releaseCapture]);

  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (!suppressClick.current) return;
    e.preventDefault();
    e.stopPropagation();
  }, []);

  // L2-175 Item 1: whole-card tap navigation. A genuine click (not a swipe — those
  // are stopped in onClickCapture above) fires onTap. The caller guards against
  // clicks that land on real interactive children (links/buttons handle themselves)
  // and against modified clicks (ctrl/cmd = open-in-new-tab via the anchor).
  const onClick = useCallback((e: React.MouseEvent) => {
    if (!onTap) return;
    onTap(e);
  }, [onTap]);

  return {
    ref,
    offset,
    swipeAction,
    handlers: {
      onTouchStart,
      onTouchMove,
      onTouchEnd,
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel,
      onClickCapture,
      onClick,
    },
  };
}
