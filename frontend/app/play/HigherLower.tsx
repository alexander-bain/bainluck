"use client";

// L2-176 — Game mode 2: "Higher or Lower?" Reuses the Today's Challenge mechanic
// (threshold guess against the real probability) and the /api/predictions endpoint
// (user_predictions keys on session_id) — under the kid session id. Score / streak
// / best-streak are the reward; nothing here is "wrong-answer" punishing.

import { useCallback, useMemo, useState } from "react";
import { generateThreshold } from "@/components/discover/utils";
import { getCat } from "@/components/discover/constants";
import { getDiscoverItemAnalytics } from "@/lib/discoverInteractions";
import type { FeedItem, FeedFuturesData, FeedEventData } from "@/lib/types";
import { recordBestStreak, sendKidPrediction } from "@/lib/play/session";
import s from "./play.module.css";

interface HigherLowerProps {
  deck: FeedItem[];
  playerName: string;
  playerEmoji: string;
  initialBestStreak: number;
  onExit: () => void;
  onNeedMore: () => void;
}

interface Question {
  item: FeedItem;
  marketId: number;
  title: string;
  subject: string;
  category: string;
  prob: number;
  threshold: number;
}

function usableProb(item: FeedItem): { prob: number; subject: string; marketId: number } | null {
  if (item.type === "futures") {
    const d = item.data as FeedFuturesData;
    const leader = d.top_outcomes?.[0];
    if (leader?.probability && leader.probability > 0) {
      return { prob: leader.probability, subject: leader.name, marketId: d.id };
    }
  }
  if (item.type === "event") {
    const d = item.data as FeedEventData;
    const p = d.current_odds?.home_probability;
    if (p && p > 0) return { prob: p, subject: `${d.home_team} to win`, marketId: d.id };
  }
  return null;
}

export default function HigherLower({
  deck,
  playerName,
  playerEmoji,
  initialBestStreak,
  onExit,
  onNeedMore,
}: HigherLowerProps) {
  const [pos, setPos] = useState(0);
  const [guess, setGuess] = useState<"higher" | "lower" | null>(null);
  const [streak, setStreak] = useState(0);
  const [best, setBest] = useState(initialBestStreak);
  const [confetti, setConfetti] = useState<number[]>([]);

  // Only cards with a real probability can be questions.
  const questions = useMemo<Question[]>(() => {
    const out: Question[] = [];
    for (const item of deck) {
      const u = usableProb(item);
      if (!u) continue;
      const a = getDiscoverItemAnalytics(item);
      out.push({
        item,
        marketId: u.marketId,
        title: a.item_name,
        subject: u.subject,
        category: a.category,
        prob: u.prob,
        threshold: generateThreshold(u.prob),
      });
    }
    return out;
  }, [deck]);

  const q = questions[pos];
  const actualPct = q ? Math.round(q.prob * 100) : 0;
  const correct = q && guess ? (guess === "higher" ? actualPct > q.threshold : actualPct < q.threshold) : false;

  const fireConfetti = useCallback(() => {
    const ids = Array.from({ length: 12 }, (_, i) => Date.now() + i);
    setConfetti(ids);
    window.setTimeout(() => setConfetti([]), 1000);
  }, []);

  const submit = useCallback(
    (g: "higher" | "lower") => {
      if (!q || guess) return;
      setGuess(g);
      const isCorrect = g === "higher" ? actualPct > q.threshold : actualPct < q.threshold;
      sendKidPrediction(playerName, {
        market_id: q.marketId,
        guess: g,
        threshold: q.threshold,
        actual_probability: q.prob,
        correct: isCorrect,
      });
      if (isCorrect) {
        const nextStreak = streak + 1;
        setStreak(nextStreak);
        fireConfetti();
        if (nextStreak > best) {
          setBest(nextStreak);
          recordBestStreak(playerName, nextStreak);
        }
      } else {
        setStreak(0);
      }
    },
    [q, guess, actualPct, playerName, streak, best, fireConfetti]
  );

  const next = useCallback(() => {
    setGuess(null);
    setPos((p) => p + 1);
    if (questions.length - pos <= 3) onNeedMore();
  }, [questions.length, pos, onNeedMore]);

  if (!q) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] text-center px-6 gap-4">
        <div className="text-6xl">🎯</div>
        <h2 className="text-2xl font-black text-text-primary">Loading questions…</h2>
        <p className="text-text-secondary">Best streak: {best} 🔥</p>
        <button onClick={onExit} className="mt-2 rounded-2xl bg-accent-brand px-6 py-3 text-white font-bold text-lg">
          Back to menu
        </button>
      </div>
    );
  }

  const cat = getCat(q.category);

  return (
    <div className="relative flex flex-col items-center px-4 pt-3 pb-8">
      <div className="w-full max-w-md flex items-center justify-between mb-4">
        <button onClick={onExit} className="text-sm font-bold text-text-muted px-2 py-2">
          ← Menu
        </button>
        <div className="flex items-center gap-3 text-sm font-black">
          <span className={streak > 0 ? s.streakPulse : ""} key={streak}>
            🔥 {streak}
          </span>
          <span className="text-text-muted">Best {best}</span>
        </div>
      </div>

      <div className="w-full max-w-md rounded-3xl border-2 border-surface-border bg-surface-card shadow-xl overflow-hidden">
        <div className="px-5 py-3 flex items-center gap-2 bg-surface-elevated">
          <span>{cat.emoji}</span>
          <span className="text-xs font-black uppercase tracking-wide text-text-secondary">{q.category}</span>
          <span className="ml-auto text-lg">{playerEmoji}</span>
        </div>

        <div className="p-6">
          <h2 className="text-xl font-black leading-tight text-text-primary mb-2">{q.title}</h2>

          {!guess ? (
            <>
              <p className="text-base text-text-secondary mb-6">
                Is the chance of <span className="font-bold text-text-primary">{q.subject}</span> higher or
                lower than <span className="text-2xl font-black text-accent-brand">{q.threshold}%</span>?
              </p>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => submit("higher")}
                  className="py-6 rounded-2xl bg-green-500/10 text-green-700 font-black text-xl border-2 border-green-400/40 active:scale-95 transition-transform"
                  style={{ minHeight: 72 }}
                >
                  ⬆️ Higher
                </button>
                <button
                  onClick={() => submit("lower")}
                  className="py-6 rounded-2xl bg-blue-500/10 text-blue-700 font-black text-xl border-2 border-blue-400/40 active:scale-95 transition-transform"
                  style={{ minHeight: 72 }}
                >
                  ⬇️ Lower
                </button>
              </div>
            </>
          ) : (
            <div className="text-center">
              <div
                className={`inline-flex items-center gap-2 px-5 py-2 rounded-full text-lg font-black mb-4 ${
                  correct ? "bg-green-500/15 text-green-700" : "bg-orange-500/15 text-orange-700"
                }`}
              >
                {correct ? "🎉 YES!" : "😅 Nope!"}
              </div>
              <div className="text-6xl font-black tabular-nums text-text-primary mb-1">{actualPct}%</div>
              <div className="text-sm text-text-secondary mb-6">{q.subject}</div>
              <button
                onClick={next}
                className="w-full py-5 rounded-2xl bg-accent-brand text-white font-black text-xl active:scale-95 transition-transform"
                style={{ minHeight: 64 }}
              >
                Next question →
              </button>
            </div>
          )}
        </div>
      </div>

      {confetti.length > 0 && (
        <div className={s.burstLayer} aria-hidden>
          {confetti.map((id, i) => (
            <span
              key={id}
              className={s.confetti}
              style={{ left: `${6 + (i * 8) % 88}%`, animationDelay: `${(i % 5) * 40}ms` }}
            >
              {["🎉", "⭐", "🔥", "✨", "🏆"][i % 5]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
