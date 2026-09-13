"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Check, Heart, Share2 } from "lucide-react";
import { trackEvent } from "@/lib/analytics";
import { sentencePreview } from "./utils";
import { PinButton } from "@/components/PinButton";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import type { ActionBarProps } from "./types";
import type { ForYouCue } from "@/lib/discover/forYouCue";
import {
  CONFIDENCE_TIER_BARS,
  CONFIDENCE_TIER_LABEL,
  CONFIDENCE_TOOLTIP,
  normalizeTier,
  type ConfidenceTier,
} from "@/lib/confidence";
import { movementPoints } from "@/lib/probabilityDisplay";
import { animatedProbabilityReading } from "@/lib/animatedProbabilityReading";

// ── Animated Counter ──

export function AnimatedProbability({ value, className, resolved }: { value: number; className?: string; resolved?: boolean }) {
  const [displayed, setDisplayed] = useState(0);
  // #3119: whether the count-up has BEGUN, as state rather than the `animated`
  // ref below — a ref cannot re-render, and this decides what is on screen.
  const [started, setStarted] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const animated = useRef(false);

  useEffect(() => {
    if (animated.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !animated.current) {
        animated.current = true;
        setStarted(true);
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

  // #3119: a counter that has not started counting has no reading to print.
  // It used to print `0%` — a fully-styled, confident zero — for as long as the
  // card was off screen, which on a live golf hero read "0%  ▲17%" beside a
  // payload that said 25.2%. The em-dash below was ALREADY this component's
  // word for "we have no probability"; it just was not applied to this zero.
  // Full reasoning: `lib/animatedProbabilityReading.ts`.
  const reading = animatedProbabilityReading({ value, resolved, started, displayed });
  if (reading.kind === "unknown") {
    return <span ref={ref} className={className}>&mdash;</span>;
  }

  return <span ref={ref} className={className}>{reading.percent}<span className="text-3xl">%</span></span>;
}

// ── Movement Badge ──

/**
 * How big a 24h move must be, IN POINTS, before this badge shows it.
 * UX-P048 (#1695): the pre-existing 0.02-fraction floor, unchanged in value and
 * restated in the unit it always meant. See `HERO_MIN_MOVEMENT_POINTS` in
 * FuturesCard for why the two bars are deliberately still different.
 */
const BADGE_MIN_MOVEMENT_POINTS = 2;

export function MovementBadge({ m, prob }: { m: number | null | undefined; prob?: number | null }) {
  // UX-P048 (#1695): the fraction -> points conversion lives in exactly one
  // place. This badge was already correct; it delegates so that it and the hero
  // cannot drift apart again, which is how the hero came to print a 64-point
  // move as "0.6".
  const points = movementPoints(m);
  if (points == null || Math.abs(points) < BADGE_MIN_MOVEMENT_POINTS) return null;
  // L2-160 — respect the 5% placeholder floor: an illiquid outcome rendered at the
  // ~5% minimum is a placeholder, so any "movement" on it is noise, not a signal.
  // (Mirrors the isTrending / eventConcept 0.05 floor.)
  if (prob != null && prob <= 0.05) return null;
  const up = points > 0;
  // POINTS, and the badge now SAYS points. `movementPoints` already returned
  // percentage points, and the `aria-label` below has always read them out
  // correctly ("Up 10 points in the last 24h") — but the visible body printed
  // `{pts}%`. So this badge told a screen reader the right unit and the eye the
  // wrong one, and the eye's version understated every move: a 37.8% -> 47.8%
  // leader rendered "10%", which reads as a tenth more than he had rather than
  // the ten points he actually gained (#4066 / D1 clause (a)). The label was the
  // spec sitting next to the bug the whole time.
  const pts = Math.abs(Math.round(points));
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
      {pts} pts
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

// ── The dismiss button's corner (#3777) ──

/**
 * Keeps the rest of a card clear of the corner `DismissBtn` occupies.
 *
 * `DismissBtn` is `absolute`, so it reserves NO layout space. Anything else
 * that reaches the same corner — an in-flow row ending flush right, or a
 * second badge pinned to `top-3 right-3` — is simply painted underneath it,
 * and the button's opaque `bg-black/30` means "underneath" is "invisible".
 *
 * Measured on production 2026-09-08 at 390px, by intersecting the button's
 * rect with every text run and glyph in its own card: 23 of 35 dismissible
 * Discover cards had something under it. Every leaderboard card (16/16) lost
 * all three confidence bars at 100% coverage, and every heatmap card (7/7)
 * lost the year off its "Resolves …" date. The image variants A and B were
 * clean, and clean by construction — their top rows are left-aligned, so
 * nothing reaches the corner in the first place.
 *
 * `TrendBadge` below already solved this for itself with `right-12`, so 48px
 * from the card's right edge is this file's existing line. These two helpers
 * extend that line to the other claimants rather than inventing a second
 * convention:
 *
 * - `dismissCornerBadge` — for a badge that is itself `absolute top-3`.
 * - `dismissCornerPad`   — for an in-flow row. `pr-9` (36px) sits inside a
 *   `p-3` container's 12px inset to land on the same 48px line. A row in a
 *   `p-4` container over-reserves by 4px, which is deliberate: one constant
 *   that is always safe beats per-container arithmetic that drifts the first
 *   time someone changes a padding.
 *
 * Both are no-ops when the card is not dismissible. `FuturesCard` also renders
 * on `/preferences`, inside `ThemeBundleCard` and in `GroupedFeedRenderer`,
 * none of which pass `onDismiss`; those must not pay for a button that is
 * never drawn.
 *
 * ⚠️ THESE RESERVE THE ✕, AND NOTHING ELSE (#4131). The corner has a second
 * claimant — `TrendBadge` at `right-12`, 91px wide — and 36px does not clear
 * it. The answer is NOT a bigger number here: a pad sized to today's longest
 * string is a pad that breaks on tomorrow's. A second corner element joins the
 * row's flow instead (`TrendBadge inFlow`), so the only thing these two helpers
 * ever have to reserve is the one 28px button they were measured against.
 */
export function dismissCornerPad(onDismiss?: () => void): string {
  return onDismiss ? "pr-9" : "";
}

export function dismissCornerBadge(onDismiss?: () => void): string {
  return onDismiss ? "right-12" : "right-3";
}

// ── Trend Badge ──

/** The pill's own look, shared by both placements so they cannot drift apart. */
const TREND_SKIN =
  "items-center gap-1 bg-orange-500/90 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full";

/**
 * "🔥 Trending", in one of two placements.
 *
 * `corner` (default) floats it over a hero photo or gradient strip — Variant A,
 * Variant B and `EventCard`, whose top rows are left-aligned so nothing of the
 * reader's is under it.
 *
 * `inFlow` puts it in a text card's meta row, where the corner is NOT free.
 * #4131: on the three text cards the corner placement painted the pill straight
 * over the "Resolves …" date. Measured on production 2026-09-08 at 390px: the
 * pill is 91px wide and its left edge sits 139px from the card's right, while
 * `dismissCornerPad` reserves 36px — so the pill covered the rightmost 87px of
 * the row's 264px of usable width and the reader got "Resolves Se" and no date.
 *
 * Widening the pad was rejected deliberately. Reserving the real 123px leaves
 * 177px for a row whose two runs measure ~172px ("📊 CYCLING" + "Resolves Sep
 * 14, 2026") — correct for exactly today's strings, broken by the next longer
 * category word. In the flow the row wraps instead of hiding anything, which is
 * the same argument `ForYouChip` above already makes: a card's meta row takes
 * layout space; a fourth floating chip is how a card becomes unreadable.
 *
 * This is #3777 recurring with the second corner element — that fix measured
 * the ✕ and padded for it, and the badge was never added to the sum.
 */
export function TrendBadge({ inFlow = false }: { inFlow?: boolean } = {}) {
  if (inFlow) {
    return (
      <span className={`inline-flex shrink-0 ${TREND_SKIN}`} data-trend-placement="flow">
        🔥 Trending
      </span>
    );
  }
  return (
    <div className={`absolute top-3 right-12 z-10 flex ${TREND_SKIN}`} data-trend-placement="corner">
      🔥 Trending
    </div>
  );
}

// ── "For you" cue (UX-P248 / Alex D-D, 2026-09-01) ──

/**
 * Says why a card is in front of THIS reader.
 *
 * The decision is `lib/discover/forYouCue.ts` and it is deliberately not
 * inline: a cue driven by the payload's `personalized` flag would label
 * DOWNRANKED cards, because that flag counts penalties as personalization.
 *
 * ⚠️ NOT AN ABSOLUTE BADGE. `TrendBadge` and `DismissBtn` already own the
 * card's top-right corner and the category pill owns top-left; a fourth
 * floating chip is how a hero photo becomes unreadable. This is an inline chip
 * for the card's meta row, so it takes layout space and can wrap.
 *
 * Deliberately quiet — muted text on a hairline, not an accent fill. It is a
 * provenance note, not a status: `LIVE` and `FINAL` earn colour, "one of your
 * teams" does not (design-system.md, semantic accents).
 */
export function ForYouChip({ cue, tone = "light" }: { cue: ForYouCue | null; tone?: "light" | "onImage" }) {
  if (!cue) return null;
  const skin =
    tone === "onImage"
      ? "text-white/90 bg-black/30 border-white/20 backdrop-blur-sm"
      : "text-text-muted bg-surface-deep border-surface-border";
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.04em] px-1.5 py-0.5 rounded border ${skin}`}
      data-testid="for-you-cue"
      data-for-you-reason={cue.reasonId}
      // The visible text is the MARK; the title carries the whole sentence, so a
      // reader who wonders why the feed is showing them this gets the answer
      // without a settings page.
      //
      // #4429 — Alex: "far too big — a small mark, not a badge". The chip was
      // already 10px with 6px/2px padding, so the size was never the problem:
      // `A category you follow` is a 21-character sentence, and set uppercase
      // with letter-spacing it ran as a bar across the card. The mark is one or
      // two words; the sentence did not go anywhere, it moved into the hover.
      title={`In your feed because: ${cue.label.toLowerCase()}`}
    >
      {cue.mark}
    </span>
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

export function ActionBar({ liked, setLiked, shareUrl, shareTitle, shareText, contentType, itemId, onShare, pin, priceObservedAt, priceStatus }: ActionBarProps) {
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
      {/* #5752 — HOW OLD THE NUMBER ABOVE THIS BAR IS.
          It sits in the gap the layout already had (`flex-1` either side), so a
          card that draws no mark is byte-identical to before and one that does
          takes no room from Like, the pin or Share.
          `PriceAgeMark` decides whether to draw at all: nothing inside the
          cadence's threshold, nothing for a stamp it cannot read.

          #5843 — THE CADENCE, NOT THE FLAT 30 MINUTES. The measurement this
          comment used to quote (p50 133m over 76 cards, "47 of 76 draw") read as
          a healthy split and was not one: those cards are polled TOGETHER on an
          hourly beat, so the feed crosses a 30-minute line together and the mark
          came on for the back half of every hour and then emptied.

          Re-measured on the request THIS PAGE actually makes — `limit=20&
          event_pct=0.15`, the three pages a full scroll fetches — at 2026-09-13
          10:53Z: 18 of 48 datable cards would draw at 30 minutes, 7 under the
          cadence. At the peak twelve minutes earlier, 30 of 30 against 5. Read
          in the rendered DOM at 10:51Z, production against this build at 390px
          over the same 34 action bars: 5 marks became 3.

          🔴 Three counts because ONE would have been dishonest: the population
          is a sawtooth on the hourly beat, so the same page truthfully reads 7,
          32 or 9 depending on the minute. The survivors are the point — a PGA
          ladder at 12h, two Kalshi futures at 30h, the House market at 123 days,
          and one LIVE card at 2h49m. */}
      <PriceAgeMark
        observedAt={priceObservedAt}
        scope="card"
        cadence={priceStatus === "live" ? "live" : "futures"}
      />
      <div className="flex-1" />
      {/* UX-P234 (board item 16): Discover was the one surface with no pin at all,
          while search, my-stuff and preferences all had one on the very same market.
          It sits in the action bar — beside Like and Share, where a reader already
          looks for what they can DO with a card — so every card variant that renders
          an ActionBar inherits it from one place rather than growing a fourth copy
          of the button. `stopPropagation` because these cards are wrapped in
          `useSwipe` and, in some variants, a <Link>: without it a pin click also
          navigates away and the pin looks like it did nothing. */}
      {pin && (
        <PinButton
          pinned={pin.pinned}
          onToggle={pin.onToggle}
          atMax={pin.atMax}
          noun={pin.noun}
          variant="labelled"
          stopPropagation
          className="text-text-muted hover:text-text-secondary"
        />
      )}
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

  // Declared above onPointerMove because that handler now depends on it.
  const releaseCapture = useCallback(() => {
    if (capturedId.current !== null) {
      ref.current?.releasePointerCapture?.(capturedId.current);
      capturedId.current = null;
    }
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "touch") return;
    if (!swiping.current) return;
    // #4431: a move with no button held is a HOVER, not a drag — end the gesture.
    //
    // onPointerDown deliberately does not capture (L2-175 Item 1, above), so
    // there is a window where the card is "swiping" and has captured nothing.
    // If the pointer leaves the card before any pointermove reaches it — a fast
    // trackpad flick — no capture is taken AND the card never sees the
    // pointerup, so nothing clears the flag: onPointerUp/onPointerCancel cannot
    // fire on an element that is neither under the pointer nor holding capture.
    // Without this check every later bare hover ran updateSwipe, so the card
    // followed the cursor forever and a wander past 80px armed a real dismiss.
    // Measured on production: hover left drew -75px and "Less like this".
    if (e.buttons === 0) {
      swiping.current = false;
      setOffset(0);
      setSwipeAction(null);
      releaseCapture();
      return;
    }
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
  }, [updateSwipe, releaseCapture]);

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
