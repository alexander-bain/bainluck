"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Check, Heart, Share2 } from "lucide-react";
import { trackEvent } from "@/lib/analytics";
import { sentencePreview } from "./utils";
import type { ActionBarProps } from "./types";

// ── Animated Counter ──

export function AnimatedProbability({ value, className }: { value: number; className?: string }) {
  const [displayed, setDisplayed] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const animated = useRef(false);

  useEffect(() => {
    if (animated.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !animated.current) {
        animated.current = true;
        const duration = 800;
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

  return <span ref={ref} className={className}>{displayed}<span className="text-3xl">%</span></span>;
}

// ── Movement Badge ──

export function MovementBadge({ m }: { m: number | null | undefined }) {
  if (!m || Math.abs(m) < 0.02) return null;
  const up = m > 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${up ? "bg-green-500/15 text-green-600" : "bg-red-500/15 text-red-600"}`}>
      <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">{up ? <path d="M4 1L7 5H1z" /> : <path d="M4 7L1 3h6z" />}</svg>
      {Math.abs(Math.round(m * 100))}%
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

export function useSwipe(onSwipeLeft?: () => void, onSwipeRight?: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const startX = useRef(0);
  const currentX = useRef(0);
  const swiping = useRef(false);
  const suppressClick = useRef(false);
  const [offset, setOffset] = useState(0);
  const [swipeAction, setSwipeAction] = useState<"like" | "dismiss" | null>(null);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    startX.current = e.touches[0].clientX;
    currentX.current = startX.current;
    swiping.current = true;
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!swiping.current) return;
    currentX.current = e.touches[0].clientX;
    const dx = currentX.current - startX.current;
    setOffset(dx * 0.5);
    setSwipeAction(dx > 60 ? "like" : dx < -60 ? "dismiss" : null);
  }, []);

  const onTouchEnd = useCallback((e: React.TouchEvent) => {
    swiping.current = false;
    const dx = currentX.current - startX.current;
    if (Math.abs(dx) > 80) {
      suppressClick.current = true;
      window.setTimeout(() => {
        suppressClick.current = false;
      }, 350);
      e.preventDefault();
      e.stopPropagation();
      if (dx > 80 && onSwipeRight) onSwipeRight();
      else if (dx < -80 && onSwipeLeft) onSwipeLeft();
    }
    setOffset(0);
    setSwipeAction(null);
  }, [onSwipeLeft, onSwipeRight]);

  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (!suppressClick.current) return;
    e.preventDefault();
    e.stopPropagation();
  }, []);

  return { ref, offset, swipeAction, handlers: { onTouchStart, onTouchMove, onTouchEnd, onClickCapture } };
}
