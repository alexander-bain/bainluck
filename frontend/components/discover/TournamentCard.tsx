"use client";

import Link from "next/link";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import type { FeedTournamentData } from "@/lib/types";
import { AnimatedProbability, DismissBtn, ActionBar, MovementBadge } from "./shared";

interface TournamentCardProps {
  data: FeedTournamentData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  onDetailClick?: () => void;
  onShare?: () => void;
}

export function TournamentCard({ data, liked, setLiked, onDismiss, onDetailClick, onShare }: TournamentCardProps) {
  const leader = data.golfers?.[0];
  const leaderProbability = formatShareProbability(leader?.probability);
  const shareText = leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${data.name} on Bain Luck.`
    : `Track ${data.name} on Bain Luck.`;
  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissBtn onDismiss={onDismiss} />
      <div className="relative h-44 flex flex-col items-center justify-center" style={{ background: "linear-gradient(135deg, #14532d, #166534)" }}>
        <div className="absolute top-3 left-3 bg-lime-600/15 text-lime-700 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">⛳ Golf</div>
        {leader && (
          <>
            <AnimatedProbability value={Math.round((leader.probability ?? 0) * 100)} className="text-5xl font-black text-white tabular-nums drop-shadow-lg" />
            <div className="text-white/70 text-sm mt-1">{leader.name}</div>
            <MovementBadge m={leader.movement_24h} />
          </>
        )}
      </div>
      <div className="p-4">
        <Link href="/sport/golf" onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.name}</h3>
        </Link>
        {data.venue && <p className="text-sm text-text-secondary">{data.venue}</p>}
        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={buildDiscoverShareUrl("/sport/golf", "grid", data.name)}
          shareTitle={data.name}
          shareText={shareText}
          contentType="grid"
          itemId={data.name}
          onShare={onShare}
        />
      </div>
    </div>
  );
}
