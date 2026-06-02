"use client";

import { useState } from "react";
import Link from "next/link";
import { trackEvent } from "@/lib/analytics";
import { buildDiscoverShareUrl } from "@/lib/share";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import { CATEGORY_GRADIENTS, getCat } from "./constants";
import { getSessionId, generateThreshold } from "./utils";

interface GuessCardProps {
  item: FeedItem;
  onGuessCompleted?: () => void;
  showNextButton?: boolean;
  nextButtonLabel?: string;
  onNextQuestion?: () => void;
}

export function GuessCard({
  item,
  onGuessCompleted,
  showNextButton = true,
  nextButtonLabel = "Next question →",
  onNextQuestion,
}: GuessCardProps) {
  const isEvent = item.type === "event";
  const futuresData = isEvent ? null : (item.data as FeedFuturesData);
  const eventData = isEvent ? (item.data as FeedEventData) : null;

  const leader = futuresData?.top_outcomes?.[0];
  const actualProb = isEvent
    ? (eventData!.current_odds?.home_probability ?? 0)
    : (leader?.probability ?? 0);
  const subjectName = isEvent
    ? `${eventData!.home_team} to win`
    : (leader?.name ?? "");
  const cardTitle = isEvent
    ? `${eventData!.away_team} vs ${eventData!.home_team}`
    : (futuresData!.name);
  const itemId = isEvent ? eventData!.id : futuresData!.id;
  const detailLink = isEvent ? `/events/${eventData!.id}` : `/futures/${futuresData!.id}`;
  const sportCat = isEvent ? (eventData!.sport ?? "") : (futuresData!.llm_sport_category ?? "");

  const [guess, setGuess] = useState<"higher" | "lower" | null>(null);
  const [threshold] = useState(() => generateThreshold(actualProb));
  const [streak, setStreak] = useState<number | null>(null);
  const actualPct = Math.round(actualProb * 100);
  const correct = guess === "higher" ? actualPct > threshold : actualPct < threshold;

  const catStyle = getCat(sportCat);
  const category = (isEvent ? eventData!.sport_name : futuresData!.sport_name) || sportCat || "Markets";
  const catGradient = CATEGORY_GRADIENTS[sportCat.toLowerCase()] || "linear-gradient(135deg, #0f172a, #1e293b)";

  const submitGuess = async (g: "higher" | "lower") => {
    setGuess(g);
    const isCorrect = g === "higher" ? actualPct > threshold : actualPct < threshold;
    onGuessCompleted?.();
    trackEvent("prediction_submit", {
      market_id: itemId,
      guess: g,
      threshold,
      actual_probability: actualProb,
      correct: isCorrect,
      content_type: isEvent ? "event" : "futures",
      category: sportCat,
      surface: "discover",
    }, { immediate: true });
    try {
      await fetch("/api/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-session-id": getSessionId() },
        body: JSON.stringify({ market_id: itemId, guess: g, threshold, actual_probability: actualProb, correct: isCorrect }),
      });
      const statsRes = await fetch("/api/predictions/stats", { headers: { "x-session-id": getSessionId() } });
      if (statsRes.ok) {
        const stats = await statsRes.json();
        setStreak(stats.current_streak);
      }
    } catch {}
  };

  const handleShare = async () => {
    const text = `${correct ? "I got it right!" : "So close!"} ${cardTitle} — actual odds: ${actualPct}%. Can you beat me?`;
    const shareUrl = buildDiscoverShareUrl("/discover", isEvent ? "event" : "futures", itemId);
    const trackGuessShare = (method: string) => {
      trackEvent("share", {
        content_type: isEvent ? "event" : "futures",
        item_id: itemId,
        method,
        item_name: cardTitle,
        source_section: "discover_guess",
        url: shareUrl,
      }, { immediate: true });
    };
    if (navigator.share) {
      try {
        await navigator.share({ title: text, text, url: shareUrl });
        trackGuessShare("native");
      } catch {}
    } else {
      await navigator.clipboard.writeText(`${text}\n${shareUrl}`);
      trackGuessShare("clipboard");
    }
  };

  if (!isEvent && (!leader || leader.probability == null || leader.probability === 0)) return null;
  if (isEvent && (eventData!.current_odds?.home_probability == null || eventData!.current_odds?.home_probability === 0)) return null;

  return (
    <div data-guess-card data-market-id={itemId} className="rounded-2xl overflow-hidden border-2 border-amber-400/50 bg-surface-card shadow-lg">
      <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: catGradient }}>
        <span className="text-white text-sm">🎯</span>
        <span className="text-white/90 text-xs font-bold uppercase tracking-wider">What are the odds?</span>
        <span className={`${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ml-auto`}>
          {catStyle.emoji} {category}
        </span>
      </div>

      <div className="p-4">
        <h3 className="font-bold text-lg leading-tight mb-3">{cardTitle}</h3>

        {!guess ? (
          <>
            <p className="text-sm text-text-secondary mb-4">
              {subjectName} — are the odds <span className="font-bold">higher</span> or <span className="font-bold">lower</span> than <span className="text-lg font-black">{threshold}%</span>?
            </p>
            <div className="flex gap-3">
              <button onClick={() => submitGuess("higher")} className="flex-1 py-3 rounded-xl bg-green-500/10 text-green-700 font-bold text-sm hover:bg-green-500/20 transition-colors border border-green-500/20">
                ↑ Higher than {threshold}%
              </button>
              <button onClick={() => submitGuess("lower")} className="flex-1 py-3 rounded-xl bg-red-500/10 text-red-700 font-bold text-sm hover:bg-red-500/20 transition-colors border border-red-500/20">
                ↓ Lower than {threshold}%
              </button>
            </div>
          </>
        ) : (
          <div className="text-center">
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-bold mb-3 ${correct ? "bg-green-500/15 text-green-700" : "bg-red-500/15 text-red-700"}`}>
              {correct ? "✓ Correct!" : "✗ Not quite!"}
            </div>

            <div className="mb-3">
              <div className="text-4xl font-black tabular-nums">{actualPct}%</div>
              <div className="text-sm text-text-secondary mt-1">{subjectName}</div>
            </div>

            {streak != null && streak > 1 && (
              <div className="text-xs font-bold text-amber-600 mb-2">🔥 {streak} correct in a row!</div>
            )}

            <div className="text-xs text-text-muted mb-3">
              You guessed {guess} than {threshold}% — actual is {actualPct}%
            </div>

            <div className="flex items-center justify-center gap-3 mb-3">
              <Link href={detailLink} className="text-xs text-blue-600 hover:text-blue-700 font-medium">
                See details →
              </Link>
              <button onClick={handleShare} className="text-xs text-text-muted hover:text-text-secondary font-medium flex items-center gap-1">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                </svg>
                Share result
              </button>
            </div>
            {showNextButton && (
              <button
                onClick={() => {
                  if (onNextQuestion) {
                    onNextQuestion();
                    return;
                  }
                  const allGuessCards = document.querySelectorAll("[data-guess-card]");
                  const currentCard = document.querySelector(`[data-guess-card][data-market-id="${itemId}"]`);
                  let nextCard: Element | null = null;
                  let foundCurrent = false;
                  for (const card of allGuessCards) {
                    if (card === currentCard) { foundCurrent = true; continue; }
                    if (foundCurrent) { nextCard = card; break; }
                  }
                  if (nextCard) nextCard.scrollIntoView({ behavior: "smooth", block: "center" });
                }}
                className="w-full py-2.5 rounded-xl bg-amber-500/10 text-amber-700 font-bold text-sm hover:bg-amber-500/20 transition-colors border border-amber-500/20"
              >
                {nextButtonLabel}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
