"use client";

// L2-176 — Game mode 1: "Cool or Boring?" Full-screen swipeable cards from the
// (kid-safe) feed pool. Right/👍 = Cool = like; left/👎 = Boring = unlike. Votes
// write to the existing feed-interaction endpoint under the kid session id.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSwipe } from "@/components/discover/shared";
import { getCat, CATEGORY_GRADIENTS } from "@/components/discover/constants";
import { getDiscoverItemAnalytics } from "@/lib/discoverInteractions";
import type {
  FeedItem,
  FeedFuturesData,
  FeedEventData,
} from "@/lib/types";
import { bumpRated, sendKidInteraction } from "@/lib/play/session";
import s from "./play.module.css";

interface CoolOrBoringProps {
  deck: FeedItem[];
  playerName: string;
  playerEmoji: string;
  initialRated: number;
  onRatedChange: (total: number) => void;
  onNeedMore: () => void;
  onExit: () => void;
}

const RAIN_EMOJI = ["🎉", "⭐", "🔥", "🏆", "✨", "🎊", "🍀", "💥"];

function cardImage(item: FeedItem): string | null {
  if (item.type === "futures") return (item.data as FeedFuturesData).image_url || null;
  return null;
}

function cardProbability(item: FeedItem): number | null {
  if (item.type === "futures") {
    return (item.data as FeedFuturesData).top_outcomes?.[0]?.probability ?? null;
  }
  if (item.type === "event") {
    return (item.data as FeedEventData).current_odds?.home_probability ?? null;
  }
  return null;
}

function probLeader(item: FeedItem): string | null {
  if (item.type === "futures") {
    return (item.data as FeedFuturesData).top_outcomes?.[0]?.name ?? null;
  }
  if (item.type === "event") {
    return (item.data as FeedEventData).home_team ?? null;
  }
  return null;
}

export default function CoolOrBoring({
  deck,
  playerName,
  playerEmoji,
  initialRated,
  onRatedChange,
  onNeedMore,
  onExit,
}: CoolOrBoringProps) {
  const [index, setIndex] = useState(0);
  const [rated, setRated] = useState(initialRated);
  const [exiting, setExiting] = useState<"like" | "dismiss" | null>(null);
  const [confetti, setConfetti] = useState<number[]>([]);
  const [rain, setRain] = useState<number[]>([]);
  const burstId = useRef(0);

  const item = deck[index];

  // Ask the parent for more cards when the deck runs low.
  useEffect(() => {
    if (deck.length - index <= 3) onNeedMore();
  }, [deck.length, index, onNeedMore]);

  const fireBurst = useCallback((total: number) => {
    if (total > 0 && total % 10 === 0) {
      const ids = Array.from({ length: 14 }, () => burstId.current++);
      setRain((r) => [...r, ...ids]);
      window.setTimeout(() => setRain((r) => r.filter((x) => !ids.includes(x))), 1500);
    } else if (total > 0 && total % 5 === 0) {
      const ids = Array.from({ length: 10 }, () => burstId.current++);
      setConfetti((c) => [...c, ...ids]);
      window.setTimeout(() => setConfetti((c) => c.filter((x) => !ids.includes(x))), 1000);
    }
  }, []);

  const vote = useCallback(
    (action: "like" | "unlike") => {
      if (!item || exiting) return;
      setExiting(action === "like" ? "like" : "dismiss");
      sendKidInteraction(playerName, item, action);
      const next = rated + 1;
      setRated(next);
      bumpRated(playerName, 1);
      onRatedChange(next);
      fireBurst(next);
      window.setTimeout(() => {
        setExiting(null);
        setIndex((i) => i + 1);
      }, 260);
    },
    [item, exiting, playerName, rated, onRatedChange, fireBurst]
  );

  const { ref, offset, swipeAction, handlers } = useSwipe(
    () => vote("unlike"),
    () => vote("like")
  );

  const analytics = useMemo(() => (item ? getDiscoverItemAnalytics(item) : null), [item]);
  const cat = getCat(analytics?.category);
  const gradient =
    CATEGORY_GRADIENTS[(analytics?.category || "").toLowerCase()] ||
    "linear-gradient(135deg, #0f172a, #1e293b)";
  const image = item ? cardImage(item) : null;
  const prob = item ? cardProbability(item) : null;
  const leader = item ? probLeader(item) : null;

  if (!item) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] text-center px-6 gap-4">
        <div className="text-6xl">🍿</div>
        <h2 className="text-2xl font-black text-text-primary">Whew — you rated them all!</h2>
        <p className="text-text-secondary">You rated {rated} things. Come back later for more!</p>
        <button
          onClick={onExit}
          className="mt-2 rounded-2xl bg-accent-brand px-6 py-3 text-white font-bold text-lg"
        >
          Back to menu
        </button>
      </div>
    );
  }

  const tilt = offset * 0.06;
  const exitClass = exiting === "like" ? s.flyRight : exiting === "dismiss" ? s.flyLeft : "";

  return (
    <div className="relative flex flex-col items-center px-4 pt-3 pb-6 select-none">
      {/* Header: player + counter */}
      <div className="w-full max-w-md flex items-center justify-between mb-3">
        <button onClick={onExit} className="text-sm font-bold text-text-muted px-2 py-2">
          ← Menu
        </button>
        <div className="text-sm font-black text-text-primary">
          {playerEmoji} You rated <span className="text-accent-brand">{rated}</span>!
        </div>
      </div>

      {/* Card */}
      <div className="relative w-full max-w-md" style={{ minHeight: "60vh" }}>
        {/* swipe hint backdrops */}
        <div
          className={`absolute inset-0 rounded-3xl grid place-items-center text-6xl transition-opacity ${
            swipeAction === "like" ? "opacity-100" : "opacity-0"
          }`}
          style={{ background: "rgba(34,197,94,0.12)" }}
        >
          😎
        </div>
        <div
          className={`absolute inset-0 rounded-3xl grid place-items-center text-6xl transition-opacity ${
            swipeAction === "dismiss" ? "opacity-100" : "opacity-0"
          }`}
          style={{ background: "rgba(148,163,184,0.14)" }}
        >
          😴
        </div>

        <div
          ref={ref}
          {...handlers}
          className={`${s.card} ${s.cardEnter} ${exitClass} relative rounded-3xl overflow-hidden border-2 border-surface-border bg-surface-card shadow-xl`}
          style={{
            minHeight: "60vh",
            transform: exiting ? undefined : `translateX(${offset}px) rotate(${tilt}deg)`,
            transition: offset === 0 && !exiting ? "transform 200ms ease" : undefined,
          }}
          key={index}
        >
          {/* hero */}
          <div className="relative h-56 w-full" style={{ background: gradient }}>
            {image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={image}
                alt=""
                className="absolute inset-0 h-full w-full object-cover opacity-90"
              />
            )}
            <div className="absolute top-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-white/90 px-3 py-1 text-xs font-black uppercase tracking-wide">
              <span>{cat.emoji}</span>
              <span className="text-text-primary">{analytics?.category}</span>
            </div>
          </div>

          {/* body */}
          <div className="p-5">
            <h2 className="text-2xl font-black leading-tight text-text-primary mb-3">
              {analytics?.item_name}
            </h2>
            {prob != null && leader && (
              <div className="mb-3 rounded-2xl bg-surface-elevated px-4 py-3">
                <div className="text-4xl font-black tabular-nums text-text-primary">
                  {Math.round(prob * 100)}%
                </div>
                <div className="text-sm text-text-secondary">chance: {leader}</div>
              </div>
            )}
            {analytics?.headline && (
              <p className="text-base text-text-secondary leading-snug">{analytics.headline}</p>
            )}
          </div>
        </div>
      </div>

      {/* Big buttons */}
      <div className="mt-6 flex items-center justify-center gap-10">
        <button
          aria-label="Boring"
          onClick={() => vote("unlike")}
          className={`${s.voteBtn} bg-white text-slate-500 border-2 border-surface-border`}
        >
          👎
        </button>
        <div className="text-sm font-bold text-text-muted select-none">Cool or Boring?</div>
        <button
          aria-label="Cool"
          onClick={() => vote("like")}
          className={`${s.voteBtn} bg-white text-green-500 border-2 border-green-300`}
        >
          👍
        </button>
      </div>

      {/* Bursts */}
      {(confetti.length > 0 || rain.length > 0) && (
        <div className={s.burstLayer} aria-hidden>
          {confetti.map((id, i) => (
            <span
              key={`c${id}`}
              className={s.confetti}
              style={{ left: `${8 + (i * 9) % 84}%`, animationDelay: `${(i % 5) * 40}ms` }}
            >
              {RAIN_EMOJI[i % RAIN_EMOJI.length]}
            </span>
          ))}
          {rain.map((id, i) => (
            <span
              key={`r${id}`}
              className={s.rainDrop}
              style={{ left: `${(i * 7 + 3) % 96}%`, animationDelay: `${(i % 7) * 90}ms` }}
            >
              {RAIN_EMOJI[i % RAIN_EMOJI.length]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
