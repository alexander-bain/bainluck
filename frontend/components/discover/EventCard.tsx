"use client";

import { useState } from "react";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import type { FeedItem, FeedEventData } from "@/lib/types";
import { CATEGORY_GRADIENTS, getCat } from "./constants";
import { feedContextSnippet, feedExpandedContext } from "./utils";
import { DismissBtn, TrendBadge, ActionBar, ExpandableContextText, SignalBars, ForYouChip } from "./shared";
import { forYouCue } from "@/lib/discover/forYouCue";
import type { CardActionCallbacks } from "./types";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import { formatFinishedGameLabel, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import { probabilityAuthorityClass } from "@/lib/confidence";
import { servedDuelPercents } from "@/lib/servedDuelPercents";

interface EventCardProps extends CardActionCallbacks {
  item: FeedItem;
  data: FeedEventData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  trending: boolean;
}

export function EventCard({ item, data, liked, setLiked, onDismiss, trending, onDetailClick, onShare, onContextExpand, onContextCollapse }: EventCardProps) {
  const [showContext, setShowContext] = useState(false);
  const homeColor = data.home_team_data?.primary_color || "#374151";
  const awayColor = data.away_team_data?.primary_color || "#6b7280";
  const isLive = data.status === "live";
  const isDone = data.status === "completed" || data.status === "closed";
  // UX-P042 (#1640) — withhold a probability manufactured from an untraded
  // Polymarket midpoint; `current_odds` presents it as a confident 0.5/0.5.
  const probWithheld = shouldWithholdProbability(data);
  const homeProb = probWithheld ? null : data.current_odds?.home_probability;
  const awayProb = probWithheld ? null : data.current_odds?.away_probability;
  // UX-P114 — the two numbers below are two sides of ONE question (the feed
  // derives away as `1 - home`), so they are decided together or they sum to 101.
  // Measured 2026-08-21: 34 of 414 live/upcoming events printed 101 here, all 101
  // and never 99, because a blend landing on an exact half-percent rounds BOTH
  // sides up. Green Bay @ Denver read 33 + 68.
  //
  // The server decides it. The local `renderedDuelPercents` is the fallback for a
  // payload predating the field — a Discover response is cached, and the native and
  // widget arms ship on their own schedule, so "the backend deployed" is not the
  // same as "every payload carries it". Both arms are driven by the same contract
  // table, so the fallback cannot answer differently from the served value.
  //
  // #2279 — BOTH SERVED OR NEITHER. This site coalesced per side, so a payload
  // carrying one field and not the other printed a served value beside a derived
  // one — the same 101 from the other direction. `probWithheld` already nulls the
  // two together; the payload is what could not.
  const servedAwayPct = probWithheld ? null : data.current_odds?.away_rendered_percent;
  const servedHomePct = probWithheld ? null : data.current_odds?.home_rendered_percent;
  const [awayPct, homePct] = servedDuelPercents(
    awayProb,
    homeProb,
    servedAwayPct,
    servedHomePct,
  );
  // UX-P052 (#1690) — the two percentages below are the card's answer to the
  // north-star "read the probability" task, and they were drawn at full
  // authority whatever the SignalBars beside them said. Measured live
  // 2026-08-10: Phillies @ Cardinals carried a 45-POINT source spread
  // (mlb 34%, stat_model 27%, espn 68%, polymarket 72%) with
  // `sources_agree: false`, and painted a bold, full-strength 68 / 32.
  const authorityClass = probabilityAuthorityClass(data.confidence_tier);
  const catStyle = getCat(data.sport?.split("_")[0]);
  const sportCat = data.sport?.split("_")[0] || "sports";

  const headline = item.headline || (isLive ? "Live now" : isDone ? "Final" : data.highlight?.label || "");
  // UX-P045 — a settled card used to collapse to the bare word "Final", so a game
  // that ended 20 minutes ago and one that ended 19 hours ago read identically.
  // Measured 2026-08-10 07:04 PT: 15 of 15 event cards were finished games and 14
  // were over 12 hours old. Empty string means "render no date" (an unparseable
  // time, or the impossible future-dated final the shared guard rejects).
  const finishedLabel = isDone ? formatFinishedGameLabel(data.commence_time) : "";
  const contextSnippet = feedContextSnippet(item) || headline;
  const expandedContext = feedExpandedContext(item);
  // UX-P051 (#1710) — this slot is sized for "Q3", and it was painting ESPN's
  // PRE-GAME sentence: "Mon, August 10th at 8:00 PM EDT", 30 characters of prose
  // between two 64px crests, on the default landing page, at kickoff. The clock
  // is deliberately still not shown here — this card only ever read `period`, and
  // adding the clock would be a restyle rather than the fix.
  const timeLabel = isLive ? (formatLiveClockLabel(data.espn?.period, null) || "Live") : isDone ? "Final" : (() => {
    const d = new Date(data.commence_time);
    const diffH = (d.getTime() - Date.now()) / 36e5;
    if (diffH < 1) return `${Math.round(diffH * 60)}m`;
    if (diffH < 24) return `${Math.round(diffH)}h`;
    if (diffH < 48) return "Tomorrow";
    return d.toLocaleDateString("en-US", { weekday: "short" });
  })();

  // Build context blurb from tags
  const contextLines: string[] = [];
  if (data.event_tags) {
    const tags = data.event_tags;
    if (tags.some(t => t.includes("elimination"))) contextLines.push("Elimination game — loser goes home");
    if (tags.some(t => t.includes("clinch"))) contextLines.push("Winner clinches a playoff spot");
    if (tags.some(t => t.includes("rivalry"))) contextLines.push("Historic rivalry matchup");
    if (tags.some(t => t.includes("upset"))) contextLines.push("Upset alert — underdog has a real chance");
    if (tags.some(t => t.includes("playoff"))) contextLines.push("Playoff implications on the line");
  }
  const shareUrl = buildDiscoverShareUrl(`/events/${data.id}`, "event", data.id);
  const homeProbability = formatShareProbability(homeProb);
  const awayProbability = formatShareProbability(awayProb);
  const shareText = homeProbability && awayProbability
    ? `${data.home_team} ${homeProbability}, ${data.away_team} ${awayProbability} on Bain Luck.`
    : `Track ${data.away_team} vs ${data.home_team} on Bain Luck.`;

  return (
    <article className="relative rounded-[10px] overflow-hidden border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={`${data.away_team} vs ${data.home_team}${isLive ? " - Live" : isDone ? " - Final" : ""}`}>
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className="relative h-44 flex items-center justify-center gap-6" style={{ background: CATEGORY_GRADIENTS[sportCat] || `linear-gradient(135deg, ${awayColor}33, ${homeColor}33)` }}>
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>{catStyle.emoji} {data.sport_label || data.sport_name || "Sports"}</div>
        {isLive && <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-red-500/90 text-white text-[10px] font-bold uppercase px-2.5 py-1 rounded-full"><span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />LIVE</div>}

        <div className="flex flex-col items-center gap-2">
          {data.away_team_data?.logo_small ? <img src={data.away_team_data.logo_small} alt="" aria-hidden="true" className="w-16 h-16 object-contain drop-shadow-lg" /> : <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: awayColor }}>{(data.away_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}</div>}
          {(isLive || isDone) && data.away_score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.away_score}</span>}
        </div>
        <span className="text-white/70 text-sm font-semibold">{timeLabel}</span>
        <div className="flex flex-col items-center gap-2">
          {data.home_team_data?.logo_small ? <img src={data.home_team_data.logo_small} alt="" aria-hidden="true" className="w-16 h-16 object-contain drop-shadow-lg" /> : <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: homeColor }}>{(data.home_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}</div>}
          {(isLive || isDone) && data.home_score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.home_score}</span>}
        </div>
      </div>

      <div className="p-4">
        <Link href={`/events/${data.id}`} onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.away_team} {isDone ? "" : "@"} {data.home_team}</h3>
        </Link>

        {/* UX-P248 / Alex D-D — why this card is in front of THIS reader. Sits
            under the matchup rather than over the crest strip: the strip already
            carries the category pill, the LIVE chip and both scores. */}
        <ForYouChip cue={forYouCue(item)} />

        {/* Live/pregame win-probability strip — a settled game drops it for the
            winner treatment below (L2-112 Item 2: FINAL cards don't carry live chips). */}
        {!isDone && homeProb != null && awayProb != null && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-sm mb-1">
              {/* UX-P003: the card's half of "card == hero == chart". These
                  data attributes let the browser rail read the number this card
                  actually PAINTED and compare it against the hero on the page it
                  links to, without scraping styled prose. */}
              <span
                className={`font-bold ${authorityClass}`.trim()}
                style={{ color: awayColor }}
                data-testid="event-card-away-probability"
                data-probability={awayProb}
                data-rendered-percent={awayPct ?? undefined}
                data-authority-tier={data.confidence_tier ?? undefined}
              >
                {formatProbability(awayProb, { rendered: awayPct })}
              </span>
              <span className="flex items-center gap-1.5 text-text-muted text-[10px]">
                Win Probability
                <SignalBars tier={data.confidence_tier} />
              </span>
              <span
                className={`font-bold ${authorityClass}`.trim()}
                style={{ color: homeColor }}
                data-testid="event-card-home-probability"
                data-probability={homeProb}
                data-rendered-percent={homePct ?? undefined}
                data-authority-tier={data.confidence_tier ?? undefined}
              >
                {formatProbability(homeProb, { rendered: homePct })}
              </span>
            </div>
            <div className="h-2.5 rounded-full overflow-hidden flex">
              <div className="transition-all duration-500" style={{ width: `${awayProb * 100}%`, backgroundColor: awayColor }} />
              <div className="transition-all duration-500" style={{ width: `${homeProb * 100}%`, backgroundColor: homeColor }} />
            </div>
          </div>
        )}

        {/* Settled treatment — score is shown on the crest above (L2-112 Item 2).
            UX-P045: the row now renders for EVERY settled card, not only the
            decisive-score ones, because the finished-at date has to be readable on
            a draw and on a card whose scores never arrived. The winner line stays
            conditional; the "Final" badge matches the crest label, which already
            said "Final" for all of these. */}
        {isDone && (
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            {data.home_score != null && data.away_score != null && data.home_score !== data.away_score && (
              <span className="text-sm font-semibold text-text-primary">
                {(data.home_score > data.away_score ? data.home_team : data.away_team).split(" ").pop()} won
              </span>
            )}
            <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-live/15 text-accent-live">Final</span>
            {finishedLabel && (
              <span
                className="text-[11px] text-text-muted"
                data-testid="event-card-finished-at"
              >
                {finishedLabel}
              </span>
            )}
          </div>
        )}

        {contextSnippet && (
          <ExpandableContextText
            text={contextSnippet}
            expandedText={expandedContext}
            className="text-sm text-text-secondary mt-2"
            onExpand={onContextExpand}
            onCollapse={onContextCollapse}
          />
        )}

        {/* Expandable context */}
        {contextLines.length > 0 && (
          <button onClick={() => setShowContext(!showContext)} className="text-xs text-accent-brand hover:underline mt-1 font-medium">
            {showContext ? "Less context" : "Why this matters"}
          </button>
        )}
        {showContext && (
          <div className="mt-2 space-y-1 text-xs text-text-secondary bg-surface-elevated/50 rounded-lg p-2.5">
            {contextLines.map((line, i) => <p key={i}>• {line}</p>)}
          </div>
        )}

        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={shareUrl}
          shareTitle={`${data.away_team} vs ${data.home_team}`}
          shareText={shareText}
          contentType="event"
          itemId={data.id}
          onShare={onShare}
        />
      </div>
    </article>
  );
}
