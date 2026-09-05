"use client";

import { teamShortName, teamShortNames } from "@/lib/teamShortName";
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
import {
  SUSPENDED_LABEL,
  isFinishedStatus,
  isSuspendedStatus,
  suspendedSummary,
} from "@/lib/eventState";
import { PREMATCH_SAID, prematchReading } from "@/lib/prematchReading";

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
  const isDone = isFinishedStatus(data.status);
  // live/048 + CERT-786. This card had the worst fall-through of the three,
  // because its "upcoming" arm is a COUNTDOWN computed from `commence_time`:
  // a suspended row's commence time is in the past by construction, so the
  // crest strip printed a NEGATIVE number of minutes to a start that already
  // happened. Not a wrong label — an impossible one.
  const isSuspended = isSuspendedStatus(data.status);
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
  // ux/1036 — the settled card's pre-match pair, resolved server-side down
  // Alex's ladder (Kalshi → Polymarket → books) and labelled when it is not a
  // prediction market. `lib/prematchReading.ts` carries the argument.
  const prematch = isDone ? prematchReading(data) : null;
  // The spoken sentence names NO rung (D65). It used to fork — "the market
  // gave" vs "sportsbooks opened" — because the first is false of a sportsbook
  // median; Alex ruled that "pre-match probability" is true of all of them, so
  // the fork is gone rather than corrected. One phrase, owned by
  // `prematchReading`, so this card and `FeedCard` cannot drift apart.
  const prematchSaid = PREMATCH_SAID;
  const catStyle = getCat(data.sport?.split("_")[0]);
  const sportCat = data.sport?.split("_")[0] || "sports";

  const headline = item.headline || (isLive ? "Live now" : isDone ? "Final" : isSuspended ? SUSPENDED_LABEL : data.highlight?.label || "");
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
  // "Paused" and not the full badge: this slot sits between two 64px crests and
  // is sized for "Q3". The full sentence lives in the row below the crests,
  // where the settled card puts its winner line — same place, same weight, so a
  // reader's eye finds the state in the position it already looks for it.
  const timeLabel = isLive ? (formatLiveClockLabel(data.espn?.period, null) || "Live") : isDone ? "Final" : isSuspended ? "Paused" : (() => {
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
    <article className="relative rounded-[10px] overflow-hidden border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={`${data.away_team} vs ${data.home_team}${isLive ? " - Live" : isDone ? " - Final" : isSuspended ? ` - ${SUSPENDED_LABEL}` : ""}`} data-card-format="event">
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className="relative h-44 flex items-center justify-center gap-6" style={{ background: CATEGORY_GRADIENTS[sportCat] || `linear-gradient(135deg, ${awayColor}33, ${homeColor}33)` }}>
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>{catStyle.emoji} {data.sport_label || data.sport_name || "Sports"}</div>
        {isLive && <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-red-500/90 text-white text-[10px] font-bold uppercase px-2.5 py-1 rounded-full"><span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />LIVE</div>}

        <div className="flex flex-col items-center gap-2">
          {data.away_team_data?.logo_small ? <img src={data.away_team_data.logo_small} alt="" aria-hidden="true" className="w-16 h-16 object-contain drop-shadow-lg" /> : <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: awayColor }}>{teamShortName(data.away_team).slice(0, 3).toUpperCase()}</div>}
          {(isLive || isDone || isSuspended) && data.away_score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.away_score}</span>}
        </div>
        <span className="text-white/70 text-sm font-semibold">{timeLabel}</span>
        <div className="flex flex-col items-center gap-2">
          {data.home_team_data?.logo_small ? <img src={data.home_team_data.logo_small} alt="" aria-hidden="true" className="w-16 h-16 object-contain drop-shadow-lg" /> : <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: homeColor }}>{teamShortName(data.home_team).slice(0, 3).toUpperCase()}</div>}
          {(isLive || isDone || isSuspended) && data.home_score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.home_score}</span>}
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
        {!isDone && !isSuspended && homeProb != null && awayProb != null && (
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
                {/* UX-1065 (#2936): the winner is named by the pair-aware short
                    name, so this sentence can never read "FC won". */}
                {(() => {
                  const pair = teamShortNames(
                    { name: data.home_team, abbreviation: data.home_team_data?.abbreviation },
                    { name: data.away_team, abbreviation: data.away_team_data?.abbreviation },
                  );
                  return data.home_score > data.away_score ? pair.home : pair.away;
                })()} won
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

        {/* Suspended treatment — the settled row's sibling (live/048), in the
            same slot and at the same weight, because a reader looking for "how
            did it end" looks HERE. It says the two things that are true and
            stops: the match left the live board with no reported result, and
            this is where the score stood. Deliberately NOT the settled row's
            "X won" line — the whole defect CERT-752 caught was a winner
            declared off a partial score. */}
        {isSuspended && (
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span
              className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-surface-elevated text-text-muted"
              data-testid="event-card-suspended"
            >
              {/* #2786 — AWAY-HOME, unchanged. This is the one surface whose
                  own scores really are away-first: the hero above paints
                  `away_score` on the left and `home_score` on the right. */}
              {suspendedSummary(data.away_score, data.home_score, "away-home")}
            </span>
          </div>
        )}

        {/* ═══ WHAT THE MARKET THOUGHT BEFORE IT (ux/1036 Tier A) ═══

            Alex found this on /sports, but the defect is the card grammar and
            not the page: a settled Discover card told a reader who won and said
            nothing whatever about what was expected — on a probability product,
            the half of the story that is ours.

            THE LIVE STRIP'S LAYOUT, DELIBERATELY. Away on the left, home on the
            right, caption between — the same three slots, in the same order as
            the two crests above and the `Away @ Home` heading, so the number a
            reader picks up is unambiguously the one beside the name they read.

            WHAT IT DOES NOT KEEP is the split BAR and the full-authority
            colour. A settled card that draws a live-style coloured bar reads as
            a live one (L2-112 Item 2), and this figure is history: muted, and
            captioned with the tense that makes it history. */}
        {isDone && prematch && prematch.awayPercent !== null && prematch.homePercent !== null && (
          <div
            className="mt-2 flex items-center justify-between text-sm"
            data-testid="event-card-prematch"
            data-prematch-source={prematch.source}
          >
            <span
              className="font-mono tabular-nums text-text-muted"
              data-testid="event-card-prematch-away"
              data-prematch={prematch.awayProbability}
            >
              <span className="sr-only">
                {prematchSaid} {data.away_team}{" "}
              </span>
              {prematch.awayPercent}%
            </span>
            <span className="text-text-muted text-[10px]">
              {/* Alex: label it when it is not a prediction market. A books
                  median is a different claim from a prediction-market opening
                  and must not be printed as one — ux/1034 A3's lesson. */}
              Pre-match{prematch.label ? ` · ${prematch.label}` : ""}
            </span>
            <span
              className="font-mono tabular-nums text-text-muted"
              data-testid="event-card-prematch-home"
              data-prematch={prematch.homeProbability}
            >
              <span className="sr-only">
                {prematchSaid} {data.home_team}{" "}
              </span>
              {prematch.homePercent}%
            </span>
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
