"use client";

// L2-176 — Game mode 2: "Higher or Lower?" Reuses the Today's Challenge mechanic
// (threshold guess against the real probability) and the /api/predictions endpoint
// (user_predictions keys on session_id) — under the kid session id. Score / streak
// / best-streak are the reward; nothing here is "wrong-answer" punishing.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCat } from "@/components/discover/constants";
import { getDiscoverItemAnalytics } from "@/lib/discoverInteractions";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { kidSessionId, recordBestStreak, sendKidPrediction } from "@/lib/play/session";
import { deterministicThreshold } from "@/lib/play/threshold";
import { decidePlayView, type PlayPoolStatus } from "@/lib/play/poolState";
import PlayStateScreen from "./PlayStateScreen";
import s from "./play.module.css";

// A best-streak celebration only fires for a genuine run (not the first correct
// answer) and auto-dismisses so the game keeps flowing.
const RECORD_CELEBRATION_MIN = 3;
const RECORD_CELEBRATION_MS = 2600;

// How many events-only server pages we will scan looking for a page that carries
// a usable Higher/Lower question before showing an honest caught-up state. This
// is the usable-question bound; it's separate from the pool's page-boundary scan.
const MAX_QUESTION_SCAN = 6;

interface HigherLowerProps {
  deck: FeedItem[];
  playerName: string;
  playerEmoji: string;
  initialBestStreak: number;
  poolStatus: PlayPoolStatus;
  hasMore: boolean;
  onExit: () => void;
  onNeedMore: () => void;
  onRetry: () => void;
  onRefresh: () => void;
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

// Only FUTURES cards become Higher/Lower questions. `marketId` is submitted to
// /api/predictions as `market_id`, which the backend (and all its downstream
// stats/resolution joins) treats strictly as a FuturesMarket id — see
// predictions.py. Event cards carry an events-table id with no linked
// futures-market id on the feed payload, so submitting one poisons
// user_predictions (the FuturesOutcome lookup misses → the client `correct` is
// trusted, and the row joins to an unrelated market by numeric-id collision).
// L2-178: skip event cards from the guess pool entirely rather than send a
// mis-namespaced id. (CoolOrBoring still uses events — it writes interactions,
// not predictions.)
function usableProb(item: FeedItem): { prob: number; subject: string; marketId: number } | null {
  if (item.type === "futures") {
    const d = item.data as FeedFuturesData;
    const leader = d.top_outcomes?.[0];
    if (leader?.probability && leader.probability > 0) {
      return { prob: leader.probability, subject: leader.name, marketId: d.id };
    }
  }
  return null;
}

export default function HigherLower({
  deck,
  playerName,
  playerEmoji,
  initialBestStreak,
  poolStatus,
  hasMore,
  onExit,
  onNeedMore,
  onRetry,
  onRefresh,
}: HigherLowerProps) {
  const [pos, setPos] = useState(0);
  const [guess, setGuess] = useState<"higher" | "lower" | null>(null);
  const [streak, setStreak] = useState(0);
  const [best, setBest] = useState(initialBestStreak);
  const [confetti, setConfetti] = useState<number[]>([]);
  // L2-177 — full-screen "NEW RECORD" celebration. Only a genuine streak
  // (>= this many in a row) that also beats the prior best earns the big moment,
  // so the very first correct answer doesn't fire an anticlimactic "record".
  const [recordStreak, setRecordStreak] = useState<number | null>(null);

  // Only cards with a real probability can be questions. The threshold is a PURE
  // function of (probability, player+market identity), so rebuilding this list on
  // a background page append yields the IDENTICAL threshold for every existing
  // question — an append/render/retry/Strict-Mode replay can never change the
  // displayed comparison or the correctness already recorded for it (L2-195 P1).
  const questions = useMemo<Question[]>(() => {
    const out: Question[] = [];
    const sid = kidSessionId(playerName);
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
        threshold: deterministicThreshold(u.prob, `${sid}:${u.marketId}`),
      });
    }
    return out;
  }, [deck, playerName]);

  const q = questions[pos];
  const remaining = questions.length - pos;

  // Bounded scan for a page that actually carries a usable question. A safe
  // page can be events-only (no futures with a positive leader); rather than
  // showing "Loading questions..." forever, resolve to a real view and, while
  // work remains, request the next server page — capped by MAX_QUESTION_SCAN.
  const scanRef = useRef(0);
  const view = decidePlayView({
    usableCount: Math.max(0, remaining),
    status: poolStatus,
    hasMore,
    scanAttempts: scanRef.current,
    maxScan: MAX_QUESTION_SCAN,
  });

  useEffect(() => {
    if (remaining > 0) scanRef.current = 0;
  }, [remaining]);

  useEffect(() => {
    if (view === "scan") {
      scanRef.current += 1;
      onNeedMore();
    }
  }, [view, onNeedMore]);

  const handleRetry = useCallback(() => {
    scanRef.current = 0;
    onRetry();
  }, [onRetry]);

  // "Keep looking" from a paused scan resumes the bounded scan from zero attempts.
  const handleContinue = useCallback(() => {
    scanRef.current = 0;
    onNeedMore();
  }, [onNeedMore]);

  // "Check for more" from genuine exhaustion is a freshness refresh (page zero).
  const handleRefresh = useCallback(() => {
    scanRef.current = 0;
    onRefresh();
  }, [onRefresh]);

  const actualPct = q ? Math.round(q.prob * 100) : 0;
  const correct = q && guess ? (guess === "higher" ? actualPct > q.threshold : actualPct < q.threshold) : false;

  const fireConfetti = useCallback(() => {
    const ids = Array.from({ length: 12 }, (_, i) => Date.now() + i);
    setConfetti(ids);
    window.setTimeout(() => setConfetti([]), 1000);
  }, []);

  const dismissRecord = useCallback(() => setRecordStreak(null), []);

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
          // A real streak that beats the prior best = the full-screen moment.
          if (nextStreak >= RECORD_CELEBRATION_MIN) {
            setRecordStreak(nextStreak);
            window.setTimeout(() => setRecordStreak(null), RECORD_CELEBRATION_MS);
          }
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

  // No current question: render the honest terminal — loading only while a
  // request is actually in flight, otherwise a retryable error or caught-up.
  // ("scan" briefly shows loading while the effect above requests the next page.)
  if (view !== "play") {
    const variant =
      view === "error"
        ? "error"
        : view === "caught_up"
          ? "caught_up"
          : view === "scan_paused"
            ? "scan_paused"
            : "loading"; // "scan" briefly shows loading while the effect requests more
    return (
      <PlayStateScreen
        variant={variant}
        bestStreakLabel={`Best streak: ${best} 🔥`}
        onRetry={handleRetry}
        onRefresh={handleRefresh}
        onContinue={handleContinue}
        onExit={onExit}
      />
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

      {recordStreak !== null && (
        <div
          className={s.recordOverlay}
          role="dialog"
          aria-label="New best streak record"
          onClick={dismissRecord}
        >
          <div className={s.burstLayer} aria-hidden>
            {Array.from({ length: 18 }, (_, i) => (
              <span
                key={i}
                className={s.rainDrop}
                style={{ left: `${(i * 5.5) % 96}%`, animationDelay: `${(i % 6) * 90}ms` }}
              >
                {["🎉", "⭐", "🔥", "✨", "🏆", "🎊"][i % 6]}
              </span>
            ))}
          </div>
          <div className={s.recordCard}>
            <div className={s.recordTrophy}>🏆</div>
            <div className="mt-3 text-2xl font-black tracking-tight text-accent-brand">
              NEW RECORD!
            </div>
            <div className="mt-1 text-5xl font-black tabular-nums text-text-primary">
              {recordStreak}
            </div>
            <div className="mt-1 text-base font-bold text-text-secondary">
              in a row, {playerName}! 🔥
            </div>
            <button
              onClick={dismissRecord}
              className="mt-5 rounded-2xl bg-accent-brand px-6 py-3 text-white font-black text-lg active:scale-95 transition-transform"
              style={{ minHeight: 56 }}
            >
              Keep going →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
