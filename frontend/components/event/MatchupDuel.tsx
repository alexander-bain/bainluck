"use client";

// L2-130 Event Concept Page — soccer matchup DUEL card. The soccer World Cup
// adapter is the first to fuse the events data-plane into concept children: each
// bracket game is a team duel (home vs away crest + blended win probability +
// live/settled score), not a fight-card outcome list. Reused by both the container
// hero (featured) and the matchups rail (compact). Probability-only, no odds, no
// source names; light design tokens.

import { useEffect, useState } from "react";
import { formatProbability } from "@/lib/api";
import { matchupKickoffLabel } from "@/lib/eventConceptDisplay";
import type { EventConceptChild, EventConceptMatchupSide } from "@/lib/types";

/** National-team crest. Renders the logo when the team resolved (honest gap → a
 *  neutral initials disc otherwise), with an onError fallback so a dead crest URL
 *  never leaves a broken-image icon. */
export function TeamCrest({
  side,
  size = 28,
}: {
  side: EventConceptMatchupSide | undefined;
  size?: number;
}) {
  const [broken, setBroken] = useState(false);
  const logo = side?.logo;
  const label = (side?.abbreviation || side?.name || "?").slice(0, 3).toUpperCase();
  if (logo && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logo}
        alt=""
        width={size}
        height={size}
        onError={() => setBroken(true)}
        className="rounded-full object-contain bg-surface-elevated shrink-0"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      aria-hidden
      className="rounded-full bg-surface-elevated text-text-muted font-semibold flex items-center justify-center shrink-0"
      style={{ width: size, height: size, fontSize: Math.max(9, size * 0.32) }}
    >
      {label}
    </span>
  );
}

function statusChipClass(kind: "live" | "final" | "upcoming"): string {
  if (kind === "live") return "bg-accent-live/15 text-accent-live";
  if (kind === "final") return "bg-text-muted/15 text-text-secondary";
  return "bg-accent-brand/10 text-accent-brand";
}

/** One team row: crest · name · (score or win %). Winner of a settled game is
 *  emphasized; the loser is dimmed (settled-means-settled — no live % on a final). */
function TeamRow({
  side,
  isFinal,
  isWinner,
  showProbability,
  crestSize,
  big,
}: {
  side: EventConceptMatchupSide | undefined;
  isFinal: boolean;
  isWinner: boolean;
  showProbability: boolean;
  crestSize: number;
  big?: boolean;
}) {
  const name = side?.name || "TBD";
  const score = side?.score;
  return (
    <div
      className={`flex items-center gap-2.5 ${
        isFinal && !isWinner ? "opacity-60" : ""
      }`}
    >
      <TeamCrest side={side} size={crestSize} />
      <span
        className={`flex-1 min-w-0 truncate ${
          big ? "text-base" : "text-sm"
        } ${isFinal && isWinner ? "font-semibold text-text-primary" : "text-text-primary"}`}
      >
        {name}
      </span>
      {isFinal ? (
        <span
          className={`font-mono tabular-nums shrink-0 ${
            big ? "text-xl" : "text-base"
          } ${isWinner ? "font-bold text-text-primary" : "font-semibold text-text-secondary"}`}
        >
          {typeof score === "number" ? score : "—"}
        </span>
      ) : (
        showProbability && (
          <span
            className={`font-mono font-semibold text-text-primary tabular-nums shrink-0 ${
              big ? "text-lg" : "text-sm"
            }`}
          >
            {formatProbability(side?.probability ?? null)}
          </span>
        )
      )}
    </div>
  );
}

/** The duel split bar — home vs away win probability as one two-segment bar.
 *  Hidden when neither side carries a probability (an upcoming game with no
 *  priced market yet — we never fabricate a 50/50). */
function DuelSplit({
  home,
  away,
}: {
  home: EventConceptMatchupSide | undefined;
  away: EventConceptMatchupSide | undefined;
}) {
  const hp = home?.probability;
  const ap = away?.probability;
  if (typeof hp !== "number" && typeof ap !== "number") return null;
  const h = typeof hp === "number" ? hp : 0;
  const a = typeof ap === "number" ? ap : 0;
  const total = h + a;
  const hPct = total > 0 ? Math.round((h / total) * 100) : 50;
  return (
    <div className="mt-2.5 flex h-1.5 rounded-full overflow-hidden bg-surface-elevated">
      <div className="h-full bg-accent-brand" style={{ width: `${hPct}%` }} />
      <div className="h-full bg-text-muted/40" style={{ width: `${100 - hPct}%` }} />
    </div>
  );
}

export default function MatchupDuel({
  child,
  featured = false,
}: {
  child: EventConceptChild;
  featured?: boolean;
}) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
  }, []);

  const status = (child.status || "").toLowerCase();
  const isLive = status === "live";
  const isFinal = child.settled === true || status === "completed" || status === "closed";
  const chipKind: "live" | "final" | "upcoming" = isLive ? "live" : isFinal ? "final" : "upcoming";
  // Live/settled labels are clock-independent (render pre-mount); only the relative
  // upcoming countdown waits for the mounted `now` (avoids a hydration mismatch).
  const label =
    now != null
      ? matchupKickoffLabel(child, now)
      : isLive
        ? "Live"
        : isFinal
          ? "Final"
          : null;

  const home = child.home;
  const away = child.away;
  const homeScore = home?.score;
  const awayScore = away?.score;
  const homeWon =
    isFinal && typeof homeScore === "number" && typeof awayScore === "number"
      ? homeScore > awayScore
      : false;
  const awayWon =
    isFinal && typeof homeScore === "number" && typeof awayScore === "number"
      ? awayScore > homeScore
      : false;

  const crestSize = featured ? 44 : 28;

  return (
    <div
      className={`bg-surface-card rounded-card border border-surface-border ${
        featured ? "p-5 shadow-card" : "flex-shrink-0 w-60 md:w-auto p-3.5 shadow-card hover:shadow-card-hover transition-shadow"
      } ${isFinal ? "opacity-95" : ""}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2.5">
        {label && (
          <span
            className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded inline-flex items-center gap-1 ${statusChipClass(
              chipKind,
            )}`}
          >
            {isLive && (
              <span className="w-1.5 h-1.5 rounded-full bg-accent-live inline-block animate-pulse" />
            )}
            {label}
          </span>
        )}
      </div>
      <div className={featured ? "space-y-3" : "space-y-2"}>
        <TeamRow
          side={home}
          isFinal={isFinal}
          isWinner={homeWon}
          showProbability
          crestSize={crestSize}
          big={featured}
        />
        <TeamRow
          side={away}
          isFinal={isFinal}
          isWinner={awayWon}
          showProbability
          crestSize={crestSize}
          big={featured}
        />
      </div>
      {!isFinal && <DuelSplit home={home} away={away} />}
    </div>
  );
}
