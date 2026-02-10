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
import Confetti from "@/components/party/Confetti";
import PulseECG from "@/components/party/PulseECG";
import type { OddsHistoryPoint } from "@/lib/types";

// ---------------------------------------------------------------------------
// Sportsbook Props Types (from The Odds API)
// ---------------------------------------------------------------------------
interface SportsbookProp {
  player: string;
  type: string;
  market_key: string;
  line: number | null;
  over_probability?: number;
  under_probability?: number;
  probability?: number;
  bookmaker_count?: number;
}

interface PropCategoryData {
  category: string;
  props: SportsbookProp[];
}

interface SportsbookPropsResponse {
  categories: PropCategoryData[];
  total_props: number;
}

// ---------------------------------------------------------------------------
// Page Types
// ---------------------------------------------------------------------------
interface TVPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000;
const SCHEDULED_REFRESH_INTERVAL = 60000;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
// Auto-Scroll Container (infinite seamless loop, pauses on hover)
// ---------------------------------------------------------------------------
function AutoScrollContainer({
  children,
  speed = 0.3,
  className = "",
}: {
  children: React.ReactNode;
  speed?: number;
  className?: string;
}) {
  const outerRef = useRef<HTMLDivElement>(null);
  const firstRef = useRef<HTMLDivElement>(null);
  const scrollPos = useRef(0);
  const paused = useRef(false);
  const rafRef = useRef<number>();
  const [needsScroll, setNeedsScroll] = useState(false);

  useEffect(() => {
    const outer = outerRef.current;
    const first = firstRef.current;
    if (!outer || !first) return;
    const check = () => {
      setNeedsScroll(first.scrollHeight > outer.clientHeight + 10);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(first);
    observer.observe(outer);
    return () => observer.disconnect();
  }, [children]);

  useEffect(() => {
    if (!needsScroll) return;
    const outer = outerRef.current;
    const first = firstRef.current;
    if (!outer || !first) return;
    const singleH = first.scrollHeight;

    const animate = () => {
      if (!paused.current) {
        scrollPos.current += speed;
        if (scrollPos.current >= singleH) {
          scrollPos.current -= singleH;
        }
        outer.scrollTop = scrollPos.current;
      }
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [needsScroll, speed]);

  return (
    <div
      ref={outerRef}
      className={`overflow-hidden ${className}`}
      onMouseEnter={() => {
        paused.current = true;
      }}
      onMouseLeave={() => {
        paused.current = false;
      }}
    >
      <div ref={firstRef}>{children}</div>
      {needsScroll && <div className="pt-[1vh]">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Prop Odds Carousel — grouped comparisons with animated transitions
// ---------------------------------------------------------------------------
const PROP_CAT_COLORS: Record<string, string> = {
  Passing: "#60a5fa",
  Rushing: "#34d399",
  Receiving: "#f472b6",
  Scoring: "#fbbf24",
  Kicking: "#a78bfa",
};

const PROP_CAT_ICONS: Record<string, string> = {
  Passing: "\uD83C\uDFC8",
  Rushing: "\uD83C\uDFC3",
  Receiving: "\uD83D\uDD90\uFE0F",
  Scoring: "\uD83C\uDF1F",
  Kicking: "\uD83E\uDD7E",
};

interface PropGroup {
  category: string;
  type: string;
  isOverUnder: boolean;
  players: {
    name: string;
    pct: number;
    line: number | null;
  }[];
}

function TVPropCarousel({ eventId }: { eventId: number }) {
  const [data, setData] = useState<SportsbookPropsResponse | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [animClass, setAnimClass] = useState("opacity-100 translate-x-0");
  const timerKeyRef = useRef(0);

  const fetchProps = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/events/${eventId}/props`);
      if (!resp.ok) return;
      setData(await resp.json());
    } catch {
      /* ignore */
    }
  }, [eventId]);

  useEffect(() => {
    fetchProps();
    const iv = setInterval(fetchProps, 120000);
    return () => clearInterval(iv);
  }, [fetchProps]);

  // Group props by category + type (e.g., all "Anytime TD" together)
  const groups: PropGroup[] = useMemo(() => {
    if (!data) return [];
    const groupMap: Record<string, PropGroup> = {};

    for (const cat of data.categories) {
      for (const prop of cat.props) {
        const key = `${cat.category}::${prop.type}`;
        if (!groupMap[key]) {
          groupMap[key] = {
            category: cat.category,
            type: prop.type,
            isOverUnder: prop.over_probability != null,
            players: [],
          };
        }
        const pct = prop.probability ?? prop.over_probability ?? 0;
        groupMap[key].players.push({
          name: prop.player,
          pct: Math.round(pct * 100),
          line: prop.line,
        });
      }
    }

    // Sort players within each group by probability descending
    for (const group of Object.values(groupMap)) {
      group.players.sort((a, b) => b.pct - a.pct);
    }

    // Only show groups with 2+ players (comparisons are interesting)
    // Put single-player groups at the end
    const multi = Object.values(groupMap).filter((g) => g.players.length >= 2);
    const single = Object.values(groupMap).filter((g) => g.players.length === 1);
    return [...multi, ...single];
  }, [data]);

  // Auto-rotate every 8 seconds
  useEffect(() => {
    if (groups.length <= 1) return;
    const timer = setInterval(() => {
      setAnimClass("opacity-0 -translate-x-[2vw]");
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % groups.length);
        setAnimClass("opacity-0 translate-x-[2vw]");
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setAnimClass("opacity-100 translate-x-0");
          });
        });
        timerKeyRef.current += 1;
      }, 350);
    }, 8000);
    return () => clearInterval(timer);
  }, [groups.length]);

  if (!data || groups.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-white/20 text-[1.3vh]">
        Loading prop odds...
      </div>
    );
  }

  const group = groups[currentIndex % groups.length];
  const catColor = PROP_CAT_COLORS[group.category] || "#64748b";
  const catIcon = PROP_CAT_ICONS[group.category] || "\uD83D\uDCCA";
  // Max probability in group for scaling bars relative to each other
  const maxPct = Math.max(...group.players.map((p) => p.pct), 1);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between mb-[0.4vh]">
        <div className="flex items-center gap-[0.4vw]">
          <h3 className="text-white/50 text-[1.3vh] uppercase tracking-wider font-semibold">
            Prop Odds
          </h3>
          <span className="inline-block w-[0.5vh] h-[0.5vh] rounded-full bg-emerald-400 animate-pulse" />
        </div>
        <span className="text-white/20 text-[1vh] font-mono">
          {(currentIndex % groups.length) + 1}/{groups.length}
        </span>
      </div>

      {/* Animated group slide */}
      <div className={`flex-1 min-h-0 flex flex-col transition-all duration-300 ease-out ${animClass}`}>
        {/* Category + type */}
        <div className="shrink-0 mb-[0.4vh]">
          <div className="flex items-center gap-[0.3vw] mb-[0.15vh]">
            <span className="text-[1.1vh]">{catIcon}</span>
            <span
              className="text-[0.9vh] uppercase tracking-widest font-bold"
              style={{ color: catColor }}
            >
              {group.category}
            </span>
          </div>
          <div className="text-white font-bold text-[1.7vh] leading-tight">
            {group.type}
            {group.isOverUnder && (
              <span className="text-white/30 font-normal text-[1.1vh] ml-[0.3vw]">
                (Over)
              </span>
            )}
          </div>
        </div>

        {/* Player comparison bar chart */}
        <AutoScrollContainer className="flex-1 min-h-0" speed={0.25}>
          <div className="space-y-[0.4vh]">
            {group.players.map((player, i) => {
              const barWidth = (player.pct / maxPct) * 100;
              const lastName = player.name.split(" ").pop() || player.name;
              return (
                <div key={`${player.name}-${i}`}>
                  {/* Name + line + percentage */}
                  <div className="flex items-baseline justify-between mb-[0.1vh]">
                    <div className="flex items-baseline gap-[0.3vw] min-w-0">
                      <span className="text-white/80 text-[1.1vh] font-semibold truncate">
                        {lastName}
                      </span>
                      {player.line != null && (
                        <span className="text-white/25 font-mono text-[0.85vh] shrink-0">
                          {player.line}
                        </span>
                      )}
                    </div>
                    <span
                      className="font-mono font-bold text-[1.6vh] shrink-0 ml-[0.3vw]"
                      style={{ color: catColor }}
                    >
                      {player.pct}%
                    </span>
                  </div>
                  {/* Bar */}
                  <div
                    className="w-full rounded-full overflow-hidden"
                    style={{ height: "1vh", backgroundColor: "rgba(255,255,255,0.04)" }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-1000 ease-out"
                      style={{
                        width: `${barWidth}%`,
                        background: `linear-gradient(90deg, ${catColor}99, ${catColor})`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </AutoScrollContainer>
      </div>

      {/* Auto-advance progress bar */}
      <div className="shrink-0 mt-[0.3vh]">
        <div className="w-full bg-white/5 rounded-full overflow-hidden" style={{ height: "0.3vh" }}>
          <div
            key={timerKeyRef.current}
            className="h-full bg-white/20 rounded-full"
            style={{ animation: "propTimer 8s linear" }}
          />
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

        {/* === CHARTS ROW === */}
        <div className="flex-[3] min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-[0.8vw]">
          {/* Win Probability Chart */}
          <div className="bg-[#111118] rounded-2xl p-[0.8vw] border border-white/5 flex flex-col min-h-0 overflow-hidden">
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
                  winProbHistory={historyData?.win_prob_history}
                  winProbSources={historyData?.win_prob_sources}
                  eventId={eventId}
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
          <div className="bg-[#111118] rounded-2xl p-[0.8vw] border border-white/5 flex flex-col min-h-0 overflow-hidden">
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
        </div>

        {/* === PROP ODDS CAROUSEL === */}
        <div className="flex-[2] min-h-0">
          <div className="bg-[#111118] rounded-2xl p-[1vw] border border-white/5 h-full overflow-hidden">
            <TVPropCarousel eventId={eventId} />
          </div>
        </div>
      </div>

      {/* Keyframe animations */}
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes propTimer {
          from { width: 0%; }
          to { width: 100%; }
        }
      ` }} />

      {/* Bottom bar: Exit */}
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
