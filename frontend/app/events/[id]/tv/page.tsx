"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import useSWR from "swr";
import {
  fetchEvent,
  fetchEventHistory,
  formatProbability,
} from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import OddsChart from "@/components/OddsChart";
import ProbabilityBar from "@/components/ProbabilityBar";
import Confetti from "@/components/party/Confetti";
import PulseECG from "@/components/party/PulseECG";
import PropBets from "@/components/party/PropBets";
import type {
  OddsHistoryPoint,
  ESPNHistoryPoint,
} from "@/lib/types";

interface TVPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000;
const SCHEDULED_REFRESH_INTERVAL = 60000;

// ------ Key Moments Detection ------
interface KeyMoment {
  time: string;
  timestamp: number;
  description: string;
  probShift: number;
}

function detectKeyMoments(
  history: OddsHistoryPoint[],
  homeTeam: string,
  awayTeam: string,
  commenceTime?: string
): KeyMoment[] {
  if (!history || history.length < 2) return [];

  const moments: KeyMoment[] = [];
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  // Only look at post-start data if commence_time is available
  const cutoff = commenceTime ? new Date(commenceTime).getTime() : 0;
  const relevant = history.filter(
    (p) => new Date(p.timestamp).getTime() >= cutoff && p.home_probability != null
  );

  for (let i = 1; i < relevant.length; i++) {
    const prev = relevant[i - 1];
    const curr = relevant[i];
    if (prev.home_probability == null || curr.home_probability == null) continue;

    const shift = curr.home_probability - prev.home_probability;
    const absShift = Math.abs(shift);

    if (absShift >= 0.03) {
      // 3%+ shift is notable
      const team = shift > 0 ? homeShort : awayShort;
      const pct = Math.round(Math.abs(shift) * 100);
      const newProb = Math.round(
        (shift > 0 ? curr.home_probability : 1 - curr.home_probability) * 100
      );

      let desc = "";
      if (absShift >= 0.10) {
        desc = `Big swing to ${team} (+${pct}%) \u2192 ${newProb}%`;
      } else if (absShift >= 0.05) {
        desc = `${team} surges +${pct}% \u2192 ${newProb}%`;
      } else {
        desc = `${team} gains momentum (+${pct}%) \u2192 ${newProb}%`;
      }

      // Check for lead change (crosses 50%)
      if (
        (prev.home_probability < 0.5 && curr.home_probability >= 0.5) ||
        (prev.home_probability >= 0.5 && curr.home_probability < 0.5)
      ) {
        const newFav = curr.home_probability >= 0.5 ? homeShort : awayShort;
        desc = `Lead change! ${newFav} takes the lead at ${newProb}%`;
      }

      const d = new Date(curr.timestamp);
      moments.push({
        time: d.toLocaleTimeString("en-US", {
          hour: "numeric",
          minute: "2-digit",
        }),
        timestamp: d.getTime(),
        description: desc,
        probShift: shift,
      });
    }
  }

  // Return most recent first, max 20
  return moments.reverse().slice(0, 20);
}

// ------ Momentum Calculation ------
function calculateMomentum(
  history: OddsHistoryPoint[],
  homeTeam: string,
  awayTeam: string
): { team: string; delta: number; direction: "up" | "down" | "flat" } | null {
  if (!history || history.length < 2) return null;

  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  // Look at last 5 minutes of data
  const fiveMinAgo = Date.now() - 5 * 60 * 1000;
  const recent = history.filter(
    (p) =>
      new Date(p.timestamp).getTime() > fiveMinAgo &&
      p.home_probability != null
  );

  if (recent.length < 2) {
    // Fall back to last 2 data points
    const valid = history.filter((p) => p.home_probability != null);
    if (valid.length < 2) return null;
    const last = valid[valid.length - 1];
    const prev = valid[valid.length - 2];
    const delta =
      (last.home_probability ?? 0) - (prev.home_probability ?? 0);
    if (Math.abs(delta) < 0.01) return null;
    return {
      team: delta > 0 ? homeShort : awayShort,
      delta: Math.abs(delta),
      direction: delta > 0 ? "up" : "down",
    };
  }

  const first = recent[0];
  const last = recent[recent.length - 1];
  const delta =
    (last.home_probability ?? 0) - (first.home_probability ?? 0);

  if (Math.abs(delta) < 0.01) return null;

  return {
    team: delta > 0 ? homeShort : awayShort,
    delta: Math.abs(delta),
    direction: delta > 0 ? "up" : "down",
  };
}

export default function TVPage({ params }: TVPageProps) {
  const eventId = parseInt(params.id, 10);
  const [confettiActive, setConfettiActive] = useState(false);
  const prevFavoriteRef = useRef<string | null>(null);
  const [confettiColors, setConfettiColors] = useState<string[]>([]);

  // Fetch event data
  const { data: event } = useSWR(
    ["event", eventId],
    () => fetchEvent(eventId),
    {
      refreshInterval: (data) =>
        data?.status === "live"
          ? LIVE_REFRESH_INTERVAL
          : SCHEDULED_REFRESH_INTERVAL,
    }
  );

  const isLive = event?.status === "live";
  const isFinished =
    event?.status === "completed" || event?.status === "closed";

  // Fetch history
  const { data: historyData } = useSWR(
    event ? ["history", eventId] : null,
    () => fetchEventHistory(eventId, 48),
    {
      refreshInterval: isLive
        ? LIVE_REFRESH_INTERVAL
        : SCHEDULED_REFRESH_INTERVAL,
    }
  );

  const odds = event?.current_odds;
  const homeProb = odds?.home_probability;
  const awayProb = odds?.away_probability;

  // Detect lead changes for confetti
  useEffect(() => {
    if (!event || homeProb == null) return;

    const currentFavorite =
      homeProb >= 0.5 ? event.home_team : event.away_team;

    if (
      prevFavoriteRef.current &&
      prevFavoriteRef.current !== currentFavorite &&
      isLive
    ) {
      // Lead changed! Fire confetti with the new favorite's team colors
      const newFavData =
        currentFavorite === event.home_team
          ? event.home_team_data
          : event.away_team_data;
      const colors = newFavData?.primary_color
        ? [
            newFavData.primary_color,
            newFavData.secondary_color || "#FFD700",
            "#FFFFFF",
            newFavData.primary_color,
          ]
        : undefined;
      if (colors) setConfettiColors(colors);
      setConfettiActive(true);
      setTimeout(() => setConfettiActive(false), 4000);
    }

    prevFavoriteRef.current = currentFavorite;
  }, [event, homeProb, isLive]);

  // Key moments
  const keyMoments = useMemo(
    () =>
      detectKeyMoments(
        historyData?.history ?? [],
        event?.home_team ?? "",
        event?.away_team ?? "",
        event?.commence_time
      ),
    [historyData?.history, event?.home_team, event?.away_team, event?.commence_time]
  );

  // Momentum
  const momentum = useMemo(
    () =>
      calculateMomentum(
        historyData?.history ?? [],
        event?.home_team ?? "",
        event?.away_team ?? ""
      ),
    [historyData?.history, event?.home_team, event?.away_team]
  );

  // Loading state
  if (!event) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-white/50 text-2xl animate-pulse">
          Loading game...
        </div>
      </div>
    );
  }

  const sportEmoji = event.sport ? getEmojiForLeague(event.sport) : "\uD83C\uDFC6";
  const leagueName = event.sport ? getLeagueDisplay(event.sport) : "";
  const homeShort = event.home_team.split(" ").pop() || event.home_team;
  const awayShort = event.away_team.split(" ").pop() || event.away_team;
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  // Pulse color based on score
  const pulseScore = event.pulse?.score ?? 0;
  const pulseColor =
    pulseScore >= 81
      ? "#ef4444"
      : pulseScore >= 61
      ? "#f97316"
      : pulseScore >= 41
      ? "#eab308"
      : "#64748b";

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white overflow-hidden">
      <Confetti
        active={confettiActive}
        colors={confettiColors.length > 0 ? confettiColors : undefined}
      />

      {/* === TOP BAR === */}
      <header className="bg-gradient-to-r from-[#111118] to-[#16161f] border-b border-white/10 px-6 py-3">
        <div className="max-w-[1800px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="text-2xl">{sportEmoji}</span>
            <span className="text-white/70 font-semibold text-lg tracking-wide uppercase">
              {leagueName}
            </span>
            {isLive && (
              <span className="flex items-center gap-2 bg-red-500/20 text-red-400 px-3 py-1 rounded-full text-sm font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
                LIVE
              </span>
            )}
            {isFinished && (
              <span className="text-white/40 text-sm px-3 py-1 rounded-full bg-white/5">
                FINAL
              </span>
            )}
          </div>

          <div className="flex items-center gap-6">
            {/* ESPN info */}
            {event.espn?.broadcast && (
              <span className="text-white/40 text-sm">
                {event.espn.broadcast}
              </span>
            )}
            {isLive && event.espn?.game_clock && event.espn?.period && (
              <span className="text-emerald-400 font-mono font-bold text-lg">
                {event.espn.period} &middot; {event.espn.game_clock}
              </span>
            )}
            {/* Pulse badge */}
            {event.pulse && (
              <div className="flex items-center gap-2">
                <span className="text-white/40 text-xs uppercase tracking-wider">
                  Pulse
                </span>
                <span
                  className="font-bold text-xl font-mono px-3 py-0.5 rounded-lg"
                  style={{
                    color: pulseColor,
                    backgroundColor: `${pulseColor}20`,
                  }}
                >
                  {event.pulse.emoji} {event.pulse.score}
                </span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* === MAIN CONTENT === */}
      <div className="max-w-[1800px] mx-auto px-6 py-4">
        {/* Score + Probability Hero */}
        <div className="mb-4">
          <div className="flex items-center justify-center gap-8 md:gap-16 mb-4">
            {/* Home Team */}
            <div className="flex flex-col items-center gap-2 flex-1">
              {event.home_team_data?.logo_large && (
                <img
                  src={event.home_team_data.logo_large}
                  alt=""
                  className="w-20 h-20 md:w-28 md:h-28 object-contain drop-shadow-2xl"
                />
              )}
              <span className="text-white/80 font-semibold text-lg md:text-2xl tracking-wide">
                {event.home_team}
              </span>
              {event.home_team_data?.record && (
                <span className="text-white/30 text-sm">
                  {event.home_team_data.record}
                </span>
              )}
            </div>

            {/* Score */}
            <div className="text-center">
              {(isLive || isFinished) &&
              event.home_score != null &&
              event.away_score != null ? (
                <div className="flex items-center gap-4 md:gap-8">
                  <span className="text-6xl md:text-8xl font-bold font-mono text-white tabular-nums">
                    {event.home_score}
                  </span>
                  <span className="text-3xl md:text-5xl text-white/30">
                    &mdash;
                  </span>
                  <span className="text-6xl md:text-8xl font-bold font-mono text-white tabular-nums">
                    {event.away_score}
                  </span>
                </div>
              ) : (
                <div className="text-white/30 text-2xl">VS</div>
              )}
            </div>

            {/* Away Team */}
            <div className="flex flex-col items-center gap-2 flex-1">
              {event.away_team_data?.logo_large && (
                <img
                  src={event.away_team_data.logo_large}
                  alt=""
                  className="w-20 h-20 md:w-28 md:h-28 object-contain drop-shadow-2xl"
                />
              )}
              <span className="text-white/80 font-semibold text-lg md:text-2xl tracking-wide">
                {event.away_team}
              </span>
              {event.away_team_data?.record && (
                <span className="text-white/30 text-sm">
                  {event.away_team_data.record}
                </span>
              )}
            </div>
          </div>

          {/* Giant Probability Display */}
          <div className="flex items-center justify-center gap-6 md:gap-12 mb-3">
            <span
              className={`font-mono text-5xl md:text-7xl font-bold tabular-nums ${
                homeFavorite ? "text-white" : "text-white/40"
              }`}
            >
              {formatProbability(homeProb)}
            </span>
            <span className="text-white/20 text-2xl">WIN PROBABILITY</span>
            <span
              className={`font-mono text-5xl md:text-7xl font-bold tabular-nums ${
                !homeFavorite ? "text-white" : "text-white/40"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>

          {/* Probability Bar */}
          <div className="max-w-4xl mx-auto mb-2">
            <div className="h-5 w-full rounded-full overflow-hidden flex bg-white/10">
              <div
                className="transition-all duration-700 ease-out rounded-l-full"
                style={{
                  width: `${Math.round((homeProb ?? 0.5) * 100)}%`,
                  backgroundColor:
                    event.home_team_data?.primary_color || (homeFavorite ? "#10b981" : "#475569"),
                }}
              />
              <div
                className="transition-all duration-700 ease-out rounded-r-full"
                style={{
                  width: `${Math.round((awayProb ?? 0.5) * 100)}%`,
                  backgroundColor:
                    event.away_team_data?.primary_color || (!homeFavorite ? "#10b981" : "#475569"),
                }}
              />
            </div>
          </div>

          {/* Momentum Indicator */}
          {momentum && (
            <div className="text-center">
              <span className="inline-flex items-center gap-2 bg-white/5 px-4 py-1.5 rounded-full text-sm">
                <span
                  className={`text-lg ${
                    momentum.delta >= 0.05
                      ? "animate-bounce"
                      : ""
                  }`}
                >
                  {momentum.direction === "up" ? "\u2197\uFE0F" : "\u2197\uFE0F"}
                </span>
                <span className="text-white/60">Momentum:</span>
                <span className="text-white font-semibold">
                  {momentum.team}
                </span>
                <span className="text-emerald-400 font-mono text-xs">
                  +{Math.round(momentum.delta * 100)}% in 5 min
                </span>
              </span>
            </div>
          )}
        </div>

        {/* === BOTTOM SECTION: Chart + Sidebar === */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Win Probability Chart - takes 2 columns */}
          <div className="lg:col-span-2 bg-[#111118] rounded-2xl p-4 border border-white/5">
            <h3 className="text-white/50 text-xs uppercase tracking-wider mb-2 font-semibold">
              Win Probability
            </h3>
            {historyData?.history && historyData.history.length > 0 ? (
              <div className="[&_.recharts-cartesian-grid_line]:!stroke-white/10 [&_.recharts-xAxis_text]:!fill-white/40 [&_.recharts-yAxis_text]:!fill-white/40 [&_.recharts-reference-line_line]:!stroke-white/20">
                <OddsChart
                  history={historyData.history}
                  homeTeam={event.home_team}
                  awayTeam={event.away_team}
                  commenceTime={event.commence_time}
                  isLive={isLive}
                  bookmakerHistory={historyData?.bookmaker_history}
                  espnHistory={historyData?.espn_history}
                  eventStatus={event.status}
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-white/20">
                Waiting for data...
              </div>
            )}

            {/* Pulse ECG Animation */}
            {event.pulse && (
              <div className="mt-2 border-t border-white/5 pt-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-white/30 text-xs uppercase tracking-wider">
                    {event.pulse.emoji} Pulse: {event.pulse.label}
                  </span>
                  <span
                    className="font-mono text-sm font-bold"
                    style={{ color: pulseColor }}
                  >
                    {event.pulse.score}/100
                  </span>
                </div>
                <PulseECG score={event.pulse.score} color={pulseColor} height={50} />
              </div>
            )}
          </div>

          {/* Sidebar: Key Moments + Props */}
          <div className="space-y-4">
            {/* Key Moments */}
            <div className="bg-[#111118] rounded-2xl p-4 border border-white/5">
              <h3 className="text-white/50 text-xs uppercase tracking-wider mb-3 font-semibold">
                Key Moments
              </h3>
              {keyMoments.length > 0 ? (
                <div className="space-y-2 max-h-[250px] overflow-y-auto pr-1">
                  {keyMoments.map((moment, i) => (
                    <div
                      key={`${moment.timestamp}-${i}`}
                      className={`flex gap-3 py-1.5 ${
                        i === 0
                          ? "text-white"
                          : "text-white/50"
                      }`}
                    >
                      <span className="text-xs font-mono whitespace-nowrap opacity-60 pt-0.5">
                        {moment.time}
                      </span>
                      <span className="text-sm leading-tight">
                        {moment.description}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-white/20 text-sm text-center py-6">
                  {isLive
                    ? "Waiting for notable shifts..."
                    : "Moments appear during live games"}
                </div>
              )}
            </div>

            {/* Player Props */}
            <div className="bg-[#111118] rounded-2xl p-4 border border-white/5">
              <PropBets eventId={eventId} />
            </div>
          </div>
        </div>
      </div>

      {/* Exit TV mode link */}
      <div className="fixed bottom-4 left-4 z-50">
        <a
          href={`/events/${eventId}`}
          className="text-white/20 hover:text-white/60 text-xs transition-colors bg-black/50 px-3 py-1.5 rounded-full backdrop-blur"
        >
          Exit TV Mode
        </a>
      </div>
    </div>
  );
}
