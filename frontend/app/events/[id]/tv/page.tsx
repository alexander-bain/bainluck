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
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import ProbabilityBar from "@/components/ProbabilityBar";
import Confetti from "@/components/party/Confetti";
import PulseECG from "@/components/party/PulseECG";
import CommercialLeaderboard from "@/components/party/CommercialLeaderboard";
import type {
  OddsHistoryPoint,
  ESPNHistoryPoint,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Contest Types
// ---------------------------------------------------------------------------
interface ContestProp {
  id: string;
  question: string;
  category: string;
  choices: Record<string, number>;
  resolved: boolean;
  correct_answer: string | null;
  resolved_at: string | null;
  has_other: boolean;
  other_probability: number;
  is_tiebreaker?: boolean;
}

interface ContestPendingPick {
  prop_id: string;
  question: string;
  pick: string;
  probability: number;
}

interface ContestKeyProp {
  prop_id: string;
  question: string;
  pick: string;
  probability: number;
  impact_score: number;
  uniqueness: number;
}

interface ContestEntrant {
  rank: number;
  name: string;
  actual_points: number;
  forecasted_points: number;
  max_possible: number;
  correct_picks: { prop_id: string; question: string; pick: string }[];
  incorrect_picks: { prop_id: string; question: string; pick: string; correct_answer: string }[];
  pending_picks: ContestPendingPick[];
  key_props: ContestKeyProp[];
  best_possible_finish: number;
  can_still_win: boolean;
  eliminated: boolean;
  tiebreaker: number | null;
  total_picks: number;
}

interface ContestSummary {
  total_props: number;
  resolved_count: number;
  open_count: number;
  entrant_count: number;
}

interface ContestData {
  leaderboard: ContestEntrant[];
  props: ContestProp[];
  summary: ContestSummary;
}

// ---------------------------------------------------------------------------
// Page Types
// ---------------------------------------------------------------------------
interface TVPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000;
const SCHEDULED_REFRESH_INTERVAL = 60000;
const CONTEST_REFRESH_INTERVAL = 20000;
const COMMENTARY_REFRESH_INTERVAL = 90000;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

// ---------------------------------------------------------------------------
// Contest TV Components
// ---------------------------------------------------------------------------
const MEDAL_COLORS = ["#FFD700", "#C0C0C0", "#CD7F32"];

function TVLeaderboard({
  leaderboard,
  resolvedCount,
  totalProps,
}: {
  leaderboard: ContestEntrant[];
  resolvedCount: number;
  totalProps: number;
}) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between mb-[0.6vh]">
        <h3 className="text-white/50 text-[1.3vh] uppercase tracking-wider font-semibold">
          Contest Leaderboard
        </h3>
        <span className="text-white/30 text-[1.2vh] font-mono">
          {resolvedCount}/{totalProps} props
        </span>
      </div>

      {/* Column headers */}
      <div className="shrink-0 flex items-center gap-[0.5vw] text-[1.1vh] text-white/30 uppercase tracking-wider mb-[0.3vh] px-[0.5vw]">
        <span className="w-[2.5vw]">#</span>
        <span className="flex-1">Name</span>
        <span className="w-[4vw] text-right">Pts</span>
        <span className="w-[4vw] text-right">Fcast</span>
        <span className="w-[3vw] text-right">Best</span>
        <span className="flex-1 text-right">Key Prop</span>
      </div>

      {/* Scrollable rows */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-[0.2vh]">
        {leaderboard.map((entry) => {
          const isTop3 = entry.rank <= 3;
          const bestKeyProp = entry.key_props[0];

          return (
            <div
              key={entry.name}
              className={`flex items-center gap-[0.5vw] px-[0.5vw] py-[0.4vh] rounded-lg transition-all ${
                entry.eliminated
                  ? "opacity-40"
                  : isTop3
                    ? "bg-white/5"
                    : ""
              }`}
            >
              {/* Rank */}
              <div
                className="w-[2.5vw] text-center font-bold text-[1.6vh] shrink-0"
                style={{
                  color: isTop3 ? MEDAL_COLORS[entry.rank - 1] : "rgba(255,255,255,0.4)",
                }}
              >
                {entry.rank}
              </div>

              {/* Name + status */}
              <div className="flex-1 min-w-0 flex items-center gap-[0.4vw]">
                <span
                  className={`truncate text-[1.5vh] ${
                    isTop3 ? "text-white font-semibold" : "text-white/70"
                  }`}
                >
                  {entry.name}
                </span>
                {entry.can_still_win && entry.rank > 1 && (
                  <span className="shrink-0 text-[0.9vh] px-[0.4vw] py-[0.1vh] bg-amber-500/20 text-amber-400 rounded font-bold">
                    CAN WIN
                  </span>
                )}
                {entry.eliminated && (
                  <span className="shrink-0 text-[0.9vh] px-[0.4vw] py-[0.1vh] bg-red-500/20 text-red-400 rounded font-bold">
                    OUT
                  </span>
                )}
              </div>

              {/* Actual points */}
              <div className="w-[4vw] text-right font-mono font-bold text-[1.8vh] text-white shrink-0">
                {entry.actual_points}
              </div>

              {/* Forecasted */}
              <div className="w-[4vw] text-right font-mono text-[1.4vh] text-emerald-400 shrink-0">
                {entry.forecasted_points}
              </div>

              {/* Best possible */}
              <div className="w-[3vw] text-right font-mono text-[1.2vh] text-white/30 shrink-0">
                #{entry.best_possible_finish}
              </div>

              {/* Key prop (most impactful pending pick) */}
              <div className="flex-1 text-right min-w-0">
                {bestKeyProp ? (
                  <span className="text-[1.1vh] text-white/40 truncate block">
                    <span className="text-white/60 font-medium">&ldquo;{bestKeyProp.pick}&rdquo;</span>
                    {" "}
                    <span className="font-mono text-blue-400">
                      {Math.round(bestKeyProp.probability * 100)}%
                    </span>
                  </span>
                ) : (
                  <span className="text-[1.1vh] text-white/20">-</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TVContestSidebar({
  props,
  commentary,
  recentResolution,
}: {
  props: ContestProp[];
  commentary: string;
  recentResolution: { question: string; answer: string } | null;
}) {
  const resolved = props.filter((p) => p.resolved && !p.is_tiebreaker);
  const pending = props.filter((p) => !p.resolved && !p.is_tiebreaker);

  return (
    <div className="flex flex-col h-full gap-[0.8vh]">
      {/* Resolution flash */}
      {recentResolution && (
        <div
          className="shrink-0 rounded-xl px-[1vw] py-[0.8vh] text-center"
          style={{
            background: "linear-gradient(135deg, #69BE28, #C60C30)",
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        >
          <div className="text-[1.3vh] font-bold uppercase tracking-wider opacity-80">
            Prop Resolved!
          </div>
          <div className="text-[1.1vh] opacity-70 mt-[0.2vh]">
            {recentResolution.question}
          </div>
          <div className="text-[1.8vh] font-bold mt-[0.2vh]">
            {recentResolution.answer}
          </div>
        </div>
      )}

      {/* AI Commentary */}
      {commentary && (
        <div className="shrink-0 bg-gradient-to-r from-[#1a1a2e] to-[#16213e] rounded-xl px-[1vw] py-[0.6vh] border border-white/5">
          <div className="text-[0.9vh] text-white/30 uppercase tracking-wider font-bold mb-[0.2vh]">
            AI Commentary
          </div>
          <div className="text-[1.2vh] text-white/70 leading-relaxed">
            {commentary}
          </div>
        </div>
      )}

      {/* Recently Resolved */}
      {resolved.length > 0 && (
        <div className="shrink-0">
          <h4 className="text-[1vh] text-white/30 uppercase tracking-wider font-bold mb-[0.3vh]">
            Resolved ({resolved.length})
          </h4>
          <div className="space-y-[0.2vh]">
            {resolved.slice(-6).reverse().map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-[0.4vw] text-[1.1vh]"
              >
                <span className="text-emerald-400 shrink-0">&#10003;</span>
                <span className="text-white/40 truncate flex-1">{p.question}</span>
                <span className="text-emerald-400 font-medium shrink-0 text-right">
                  {p.correct_answer}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming Props */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <h4 className="text-[1vh] text-white/30 uppercase tracking-wider font-bold mb-[0.3vh]">
          Upcoming ({pending.length})
        </h4>
        <div className="space-y-[0.3vh] overflow-y-auto h-full">
          {pending.slice(0, 10).map((p) => {
            const topChoice = Object.entries(p.choices).sort(
              (a, b) => b[1] - a[1]
            )[0];
            return (
              <div key={p.id} className="text-[1.1vh]">
                <div className="text-white/50 truncate leading-tight">
                  {p.question}
                </div>
                {topChoice && (
                  <div className="flex items-center gap-[0.3vw] mt-[0.1vh]">
                    <div
                      className="h-[0.4vh] rounded-full bg-blue-500/50"
                      style={{ width: `${topChoice[1] * 100}%`, maxWidth: "60%" }}
                    />
                    <span className="text-white/30 text-[0.9vh]">
                      {topChoice[0]} ({Math.round(topChoice[1] * 100)}%)
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main TV Page
// ---------------------------------------------------------------------------
export default function TVPage({ params }: TVPageProps) {
  const eventId = parseInt(params.id, 10);
  const [confettiActive, setConfettiActive] = useState(false);
  const prevFavoriteRef = useRef<string | null>(null);
  const [confettiColors, setConfettiColors] = useState<string[]>([]);

  // Contest state
  const [contestData, setContestData] = useState<ContestData | null>(null);
  const [commentary, setCommentary] = useState("");
  const [recentResolution, setRecentResolution] = useState<{
    question: string;
    answer: string;
  } | null>(null);
  const prevResolvedRef = useRef<Set<string>>(new Set());

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

  // ---- Contest data polling ----
  const fetchContest = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/contest/leaderboard`);
      if (!resp.ok) return;
      const data: ContestData = await resp.json();
      setContestData(data);

      // Detect newly resolved props
      const currentResolved = new Set(
        data.props.filter((p) => p.resolved).map((p) => p.id)
      );
      const newlyResolved = Array.from(currentResolved).filter(
        (id) => !prevResolvedRef.current.has(id)
      );

      if (newlyResolved.length > 0 && prevResolvedRef.current.size > 0) {
        // Fire confetti for prop resolution
        setConfettiColors(["#69BE28", "#C60C30", "#FFD700", "#00D4FF", "#FF1493"]);
        setConfettiActive(true);
        setTimeout(() => setConfettiActive(false), 5000);

        // Show resolution flash
        const resolved = newlyResolved
          .map((id) => data.props.find((p) => p.id === id))
          .filter(Boolean);

        if (resolved.length > 0 && resolved[0]) {
          setRecentResolution({
            question: resolved[0].question,
            answer: resolved[0].correct_answer || "",
          });
          setTimeout(() => setRecentResolution(null), 12000);
        }
      }

      prevResolvedRef.current = currentResolved;
    } catch {
      // Silently ignore contest fetch failures
    }
  }, []);

  const fetchContestCommentary = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/contest/commentary`);
      if (!resp.ok) return;
      const data = await resp.json();
      setCommentary(data.commentary);
    } catch {
      // Silently ignore
    }
  }, []);

  useEffect(() => {
    fetchContest();
    const interval = setInterval(fetchContest, CONTEST_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchContest]);

  useEffect(() => {
    fetchContestCommentary();
    const interval = setInterval(fetchContestCommentary, COMMENTARY_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchContestCommentary]);

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
    <div className="fixed inset-0 z-[9999] bg-[#0a0a0f] text-white overflow-hidden flex flex-col">
      <Confetti
        active={confettiActive}
        colors={confettiColors.length > 0 ? confettiColors : undefined}
      />

      {/* === TOP BAR (compact — ~4vh) === */}
      <header className="shrink-0 bg-gradient-to-r from-[#111118] to-[#16161f] border-b border-white/10 px-[2vw] py-[0.6vh]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-[1vw]">
            <span className="text-[2.2vh]">{sportEmoji}</span>
            <span className="text-white/70 font-semibold text-[1.8vh] tracking-wide uppercase">
              {leagueName}
            </span>
            {isLive && (
              <span className="flex items-center gap-[0.5vw] bg-red-500/20 text-red-400 px-[1vw] py-[0.3vh] rounded-full text-[1.5vh] font-bold">
                <span className="w-[1.2vh] h-[1.2vh] rounded-full bg-red-500 animate-pulse" />
                LIVE
              </span>
            )}
            {isFinished && (
              <span className="text-white/40 text-[1.5vh] px-[1vw] py-[0.3vh] rounded-full bg-white/5">
                FINAL
              </span>
            )}
          </div>

          <div className="flex items-center gap-[1.5vw]">
            {/* Contest progress */}
            {contestData && (
              <div className="flex items-center gap-[0.5vw] bg-white/5 px-[1vw] py-[0.3vh] rounded-full">
                <span className="text-white/40 text-[1.2vh] uppercase tracking-wider">
                  Contest
                </span>
                <span className="text-emerald-400 font-mono font-bold text-[1.5vh]">
                  {contestData.summary.resolved_count}/{contestData.summary.total_props}
                </span>
                <span className="text-white/30 text-[1.2vh]">
                  &middot; {contestData.summary.entrant_count} players
                </span>
              </div>
            )}
            {event.espn?.broadcast && (
              <span className="text-white/40 text-[1.5vh]">
                {event.espn.broadcast}
              </span>
            )}
            {isLive && event.espn?.game_clock && event.espn?.period && (
              <span className="text-emerald-400 font-mono font-bold text-[2vh]">
                {event.espn.period} &middot; {event.espn.game_clock}
              </span>
            )}
            {event.pulse && (
              <div className="flex items-center gap-[0.5vw]">
                <span className="text-white/40 text-[1.3vh] uppercase tracking-wider">
                  Pulse
                </span>
                <span
                  className="font-bold text-[2vh] font-mono px-[0.8vw] py-[0.2vh] rounded-lg"
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
      <div className="flex-1 min-h-0 flex flex-col px-[2vw] py-[1vh] gap-[1vh]">
        {/* Score + Probability Hero (compact — ~24vh) */}
        <div className="shrink-0">
          {/* Teams + Score row */}
          <div className="flex items-center justify-center gap-[2vw] mb-[0.8vh]">
            {/* Home Team */}
            <div className="flex items-center gap-[1.2vw] flex-1 justify-end">
              <div className="text-right">
                <span className="text-white/80 font-semibold text-[2.2vh] tracking-wide block">
                  {event.home_team}
                </span>
                {event.home_team_data?.record && (
                  <span className="text-white/30 text-[1.3vh]">
                    {event.home_team_data.record}
                  </span>
                )}
              </div>
              {event.home_team_data?.logo_large && (
                <img
                  src={event.home_team_data.logo_large}
                  alt=""
                  className="object-contain drop-shadow-2xl"
                  style={{ width: "9vh", height: "9vh" }}
                />
              )}
            </div>

            {/* Score */}
            <div className="text-center shrink-0">
              {(isLive || isFinished) &&
              event.home_score != null &&
              event.away_score != null ? (
                <div className="flex items-center gap-[1.5vw]">
                  <span
                    className="font-bold font-mono text-white tabular-nums"
                    style={{ fontSize: "7.5vh", lineHeight: 1 }}
                  >
                    {event.home_score}
                  </span>
                  <span className="text-white/30" style={{ fontSize: "4vh" }}>
                    &mdash;
                  </span>
                  <span
                    className="font-bold font-mono text-white tabular-nums"
                    style={{ fontSize: "7.5vh", lineHeight: 1 }}
                  >
                    {event.away_score}
                  </span>
                </div>
              ) : (
                <div className="text-white/30" style={{ fontSize: "3vh" }}>VS</div>
              )}
            </div>

            {/* Away Team */}
            <div className="flex items-center gap-[1.2vw] flex-1">
              {event.away_team_data?.logo_large && (
                <img
                  src={event.away_team_data.logo_large}
                  alt=""
                  className="object-contain drop-shadow-2xl"
                  style={{ width: "9vh", height: "9vh" }}
                />
              )}
              <div>
                <span className="text-white/80 font-semibold text-[2.2vh] tracking-wide block">
                  {event.away_team}
                </span>
                {event.away_team_data?.record && (
                  <span className="text-white/30 text-[1.3vh]">
                    {event.away_team_data.record}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Probability Display */}
          <div className="flex items-center justify-center gap-[2vw] mb-[0.5vh]">
            <span
              className={`font-mono font-bold tabular-nums ${
                homeFavorite ? "text-white" : "text-white/40"
              }`}
              style={{ fontSize: "5.5vh", lineHeight: 1 }}
            >
              {formatProbability(homeProb)}
            </span>
            <span className="text-white/20" style={{ fontSize: "1.5vh", letterSpacing: "0.15em" }}>
              WIN PROBABILITY
            </span>
            <span
              className={`font-mono font-bold tabular-nums ${
                !homeFavorite ? "text-white" : "text-white/40"
              }`}
              style={{ fontSize: "5.5vh", lineHeight: 1 }}
            >
              {formatProbability(awayProb)}
            </span>
          </div>

          {/* Probability Bar */}
          <div className="max-w-[60%] mx-auto mb-[0.5vh]">
            <div className="w-full rounded-full overflow-hidden flex bg-white/10" style={{ height: "0.8vh", minHeight: "4px" }}>
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
              <span className="inline-flex items-center gap-[0.5vw] bg-white/5 px-[1.2vw] py-[0.4vh] rounded-full text-[1.4vh]">
                <span
                  className={momentum.delta >= 0.05 ? "animate-bounce" : ""}
                  style={{ fontSize: "2vh" }}
                >
                  {momentum.direction === "up" ? "\u2197\uFE0F" : "\u2197\uFE0F"}
                </span>
                <span className="text-white/60">Momentum:</span>
                <span className="text-white font-semibold">
                  {momentum.team}
                </span>
                <span className="text-emerald-400 font-mono">
                  +{Math.round(momentum.delta * 100)}% in 5 min
                </span>
              </span>
            </div>
          )}
        </div>

        {/* === CHARTS + KEY MOMENTS ROW === */}
        <div className="flex-[2] min-h-0 grid grid-cols-1 lg:grid-cols-5 gap-[0.6vw]">
          {/* Win Probability Chart */}
          <div className="lg:col-span-2 bg-[#111118] rounded-2xl p-[0.8vw] border border-white/5 flex flex-col min-h-0 overflow-hidden">
            <h3 className="text-white/50 text-[1.2vh] uppercase tracking-wider mb-[0.3vh] font-semibold shrink-0">
              Win Probability
            </h3>
            {historyData?.history && historyData.history.length > 0 ? (
              <div className="flex-1 min-h-0 [&_.recharts-cartesian-grid_line]:!stroke-white/10 [&_.recharts-xAxis_text]:!fill-white/40 [&_.recharts-yAxis_text]:!fill-white/40 [&_.recharts-reference-line_line]:!stroke-white/20">
                <OddsChart
                  history={historyData.history}
                  homeTeam={event.home_team}
                  awayTeam={event.away_team}
                  commenceTime={event.commence_time}
                  isLive={isLive}
                  bookmakerHistory={historyData?.bookmaker_history}
                  espnHistory={historyData?.espn_history}
                  eventStatus={event.status}
                  fillContainer
                />
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-white/20 text-[1.4vh]">
                Waiting for data...
              </div>
            )}

            {/* Pulse ECG Animation */}
            {event.pulse && (
              <div className="shrink-0 mt-[0.3vh] border-t border-white/5 pt-[0.3vh]">
                <div className="flex items-center justify-between mb-[0.2vh]">
                  <span className="text-white/30 text-[1.1vh] uppercase tracking-wider">
                    {event.pulse.emoji} Pulse: {event.pulse.label}
                  </span>
                  <span
                    className="font-mono text-[1.2vh] font-bold"
                    style={{ color: pulseColor }}
                  >
                    {event.pulse.score}/100
                  </span>
                </div>
                <PulseECG score={event.pulse.score} color={pulseColor} height={30} />
              </div>
            )}
          </div>

          {/* Score Differential Chart */}
          <div className="lg:col-span-2 bg-[#111118] rounded-2xl p-[0.8vw] border border-white/5 flex flex-col min-h-0 overflow-hidden">
            <h3 className="text-white/50 text-[1.2vh] uppercase tracking-wider mb-[0.3vh] font-semibold shrink-0">
              Score Differential
            </h3>
            {historyData?.history && historyData.history.length > 0 ? (
              <div className="flex-1 min-h-0 [&_.recharts-cartesian-grid_line]:!stroke-white/10 [&_.recharts-xAxis_text]:!fill-white/40 [&_.recharts-yAxis_text]:!fill-white/40 [&_.recharts-reference-line_line]:!stroke-white/20 [&_.recharts-legend-wrapper]:!text-white/40">
                <ScoreDifferentialChart
                  history={historyData.history}
                  homeTeam={event.home_team}
                  awayTeam={event.away_team}
                  commenceTime={event.commence_time}
                  isLive={isLive}
                  bookmakerHistory={historyData?.bookmaker_history}
                  scoreHistory={historyData?.score_history}
                  currentHomeScore={event.home_score}
                  currentAwayScore={event.away_score}
                  eventStatus={event.status}
                  fillContainer
                />
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-white/20 text-[1.4vh]">
                Waiting for data...
              </div>
            )}
          </div>

          {/* Key Moments */}
          <div className="bg-[#111118] rounded-2xl p-[0.8vw] border border-white/5 flex flex-col min-h-0 overflow-hidden">
            <h3 className="text-white/50 text-[1.2vh] uppercase tracking-wider mb-[0.5vh] font-semibold shrink-0">
              Key Moments
            </h3>
            {keyMoments.length > 0 ? (
              <div className="flex-1 min-h-0 overflow-y-auto space-y-[0.4vh] pr-1">
                {keyMoments.map((moment, i) => (
                  <div
                    key={`${moment.timestamp}-${i}`}
                    className={`flex gap-[0.5vw] py-[0.2vh] ${
                      i === 0 ? "text-white" : "text-white/50"
                    }`}
                  >
                    <span className="text-[1.1vh] font-mono whitespace-nowrap opacity-60 pt-[0.1vh]">
                      {moment.time}
                    </span>
                    <span className="text-[1.2vh] leading-tight">
                      {moment.description}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-white/20 text-[1.2vh]">
                {isLive
                  ? "Waiting for notable shifts..."
                  : "Moments appear during live games"}
              </div>
            )}
          </div>
        </div>

        {/* === CONTEST LEADERBOARD + SIDEBAR + COMMERCIALS (~55% of remaining) === */}
        <div className="flex-[3] min-h-0 grid grid-cols-1 lg:grid-cols-4 gap-[0.8vw]">
          {/* Leaderboard (2 columns) */}
          <div className="lg:col-span-2 bg-[#111118] rounded-2xl p-[1vw] border border-white/5 min-h-0 overflow-hidden">
            {contestData ? (
              <TVLeaderboard
                leaderboard={contestData.leaderboard}
                resolvedCount={contestData.summary.resolved_count}
                totalProps={contestData.summary.total_props}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-white/20 text-[1.5vh]">
                Loading contest...
              </div>
            )}
          </div>

          {/* Contest Sidebar (1 column) */}
          <div className="bg-[#111118] rounded-2xl p-[1vw] border border-white/5 min-h-0 overflow-hidden">
            {contestData ? (
              <TVContestSidebar
                props={contestData.props}
                commentary={commentary}
                recentResolution={recentResolution}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-white/20 text-[1.3vh]">
                Loading props...
              </div>
            )}
          </div>

          {/* Commercial Leaderboard (1 column) */}
          <div className="min-h-0">
            <CommercialLeaderboard />
          </div>
        </div>
      </div>

      {/* Exit TV mode link */}
      <div className="fixed bottom-[1vh] left-[1vw] z-50">
        <a
          href={`/events/${eventId}`}
          className="text-white/20 hover:text-white/60 text-[1.2vh] transition-colors bg-black/50 px-[1vw] py-[0.4vh] rounded-full backdrop-blur"
        >
          Exit TV Mode
        </a>
      </div>
    </div>
  );
}
