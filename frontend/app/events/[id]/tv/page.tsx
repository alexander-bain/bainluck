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
// CommercialLeaderboard removed — replaced by TVAdLeaderboard with YouTube API
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
// Ad Leaderboard Types
// ---------------------------------------------------------------------------
interface YouTubeAd {
  rank: number;
  brand: string;
  title: string;
  video_id: string;
  channel: string;
  thumbnail: string;
  views: number;
  likes: number;
  comments: number;
  views_formatted: string;
  likes_formatted: string;
  views_delta: number;
  views_delta_formatted: string;
  published_at: string;
}

interface AdLeaderboardData {
  ads: YouTubeAd[];
  count: number;
  youtube_configured: boolean;
}

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
const CONTEST_REFRESH_INTERVAL = 20000;
const COMMENTARY_REFRESH_INTERVAL = 90000;

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

      {/* Auto-scrolling rows */}
      <AutoScrollContainer className="flex-1 min-h-0" speed={0.2}>
        <div className="space-y-[0.2vh]">
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
      </AutoScrollContainer>
    </div>
  );
}

function TVContestSidebar({
  props,
  commentary,
}: {
  props: ContestProp[];
  commentary: string;
}) {
  const resolved = props.filter((p) => p.resolved && !p.is_tiebreaker);
  const pending = props.filter((p) => !p.resolved && !p.is_tiebreaker);

  return (
    <div className="flex flex-col h-full gap-[0.8vh]">
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
// Ad Leaderboard (YouTube Super Bowl commercials ranked by views)
// ---------------------------------------------------------------------------
const AD_MEDAL_EMOJIS = ["\uD83E\uDD47", "\uD83E\uDD48", "\uD83E\uDD49"]; // gold, silver, bronze

function TVAdLeaderboard({ ads }: { ads: YouTubeAd[] }) {
  const [playingId, setPlayingId] = useState<string | null>(null);

  if (playingId) {
    const ad = ads.find((a) => a.video_id === playingId);
    return (
      <div className="flex flex-col h-full">
        <div className="shrink-0 flex items-center justify-between mb-[0.5vh]">
          <button
            onClick={() => setPlayingId(null)}
            className="text-blue-400 text-[1.2vh] hover:text-blue-300 flex items-center gap-[0.3vw]"
          >
            &larr; Back
          </button>
          <span className="text-white/50 text-[1.1vh] font-semibold truncate">
            {ad?.brand}
          </span>
        </div>
        <div className="flex-1 min-h-0 flex items-center justify-center">
          <iframe
            src={`https://www.youtube.com/embed/${playingId}?autoplay=1&controls=1`}
            className="w-full rounded-xl"
            style={{ aspectRatio: "16/9", maxHeight: "100%" }}
            allow="autoplay; encrypted-media"
            allowFullScreen
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 flex items-center justify-between mb-[0.5vh]">
        <h3 className="text-white/50 text-[1.3vh] uppercase tracking-wider font-semibold">
          Ad Leaderboard
        </h3>
        <span className="text-white/30 text-[1.1vh]">
          {ads.length} ads
        </span>
      </div>

      <AutoScrollContainer className="flex-1 min-h-0" speed={0.2}>
        <div className="space-y-[0.3vh]">
          {ads.map((ad, i) => {
            const isTop3 = i < 3;
            return (
              <div
                key={ad.video_id}
                className={`flex items-center gap-[0.4vw] px-[0.3vw] py-[0.3vh] rounded-lg ${
                  isTop3 ? "bg-white/5" : ""
                }`}
              >
                {/* Rank */}
                <div className="w-[1.5vw] text-center shrink-0">
                  {isTop3 ? (
                    <span className="text-[1.6vh]">{AD_MEDAL_EMOJIS[i]}</span>
                  ) : (
                    <span className="text-white/30 font-mono text-[1.2vh]">
                      {ad.rank}
                    </span>
                  )}
                </div>

                {/* Brand + title */}
                <div className="flex-1 min-w-0">
                  <span
                    className={`text-[1.3vh] font-semibold truncate block ${
                      isTop3 ? "text-white" : "text-white/70"
                    }`}
                  >
                    {ad.brand}
                  </span>
                  <div className="text-white/30 text-[0.85vh] truncate leading-tight">
                    {ad.title}
                  </div>
                </div>

                {/* Play button */}
                <button
                  onClick={() => setPlayingId(ad.video_id)}
                  className="shrink-0 text-blue-400 hover:text-blue-300 text-[1.5vh] w-[1.8vw] h-[2.5vh] flex items-center justify-center rounded bg-blue-400/10 hover:bg-blue-400/20 transition-colors"
                  title={`Play ${ad.brand}`}
                >
                  &#9654;
                </button>

                {/* Views + delta */}
                <div className="text-right shrink-0 w-[3.5vw]">
                  <div className="text-white font-mono font-bold text-[1.2vh]">
                    {ad.views_formatted}
                  </div>
                  {ad.views_delta > 0 && (
                    <div className="text-emerald-400 font-mono text-[0.8vh] leading-tight">
                      {ad.views_delta_formatted}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </AutoScrollContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sportsbook Props from The Odds API (live-updating, auto-scroll)
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

function TVSportsbookProps({ eventId }: { eventId: number }) {
  const [data, setData] = useState<SportsbookPropsResponse | null>(null);

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

  if (!data || data.categories.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-white/20 text-[1.3vh]">
        Loading sportsbook props...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 flex items-center justify-between mb-[0.5vh]">
        <h3 className="text-white/50 text-[1.3vh] uppercase tracking-wider font-semibold">
          Prop Odds
        </h3>
        <div className="flex items-center gap-[0.3vw]">
          <span className="inline-block w-[0.6vh] h-[0.6vh] rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-white/30 text-[1vh] font-mono">
            {data.total_props} live
          </span>
        </div>
      </div>

      <AutoScrollContainer className="flex-1 min-h-0" speed={0.35}>
        <div className="space-y-[0.8vh]">
          {data.categories.map((cat) => {
            const catColor = PROP_CAT_COLORS[cat.category] || "#64748b";
            const catIcon = PROP_CAT_ICONS[cat.category] || "\uD83D\uDCCA";
            return (
              <div key={cat.category}>
                {/* Category header with colored accent */}
                <div className="flex items-center gap-[0.3vw] mb-[0.3vh]">
                  <div
                    className="w-[0.3vw] h-[1.8vh] rounded-full shrink-0"
                    style={{ backgroundColor: catColor }}
                  />
                  <span className="text-[1vh]">{catIcon}</span>
                  <span
                    className="text-[0.9vh] uppercase tracking-widest font-bold"
                    style={{ color: catColor }}
                  >
                    {cat.category}
                  </span>
                  <span className="text-white/15 text-[0.8vh] font-mono">
                    {cat.props.length}
                  </span>
                </div>

                <div className="space-y-[0.15vh]">
                  {cat.props.map((prop, i) => {
                    // Calculate the primary probability for the bar
                    const barPct =
                      prop.probability != null
                        ? Math.round(prop.probability * 100)
                        : prop.over_probability != null
                          ? Math.round(prop.over_probability * 100)
                          : null;

                    return (
                      <div
                        key={`${prop.player}-${prop.market_key}-${i}`}
                        className="relative rounded overflow-hidden"
                        style={{ minHeight: "2.2vh" }}
                      >
                        {/* Background probability bar */}
                        {barPct != null && (
                          <div
                            className="absolute inset-y-0 left-0 rounded-r transition-all duration-700"
                            style={{
                              width: `${Math.min(barPct, 100)}%`,
                              backgroundColor: catColor,
                              opacity: 0.12,
                            }}
                          />
                        )}

                        {/* Content over bar */}
                        <div className="relative flex items-center px-[0.3vw] py-[0.2vh]">
                          {/* Player name */}
                          <span className="text-white/80 text-[0.95vh] font-semibold truncate flex-1 min-w-0">
                            {prop.player}
                          </span>

                          {/* Line (for O/U props) */}
                          {prop.line != null && (
                            <span className="text-blue-400/70 font-mono text-[0.85vh] shrink-0 mx-[0.2vw]">
                              {prop.line}
                            </span>
                          )}

                          {/* Probabilities */}
                          {prop.over_probability != null &&
                          prop.under_probability != null ? (
                            <div className="flex items-center gap-[0.2vw] shrink-0">
                              <span
                                className="font-mono font-bold text-[0.95vh] px-[0.2vw] rounded"
                                style={{
                                  color: "#34d399",
                                  backgroundColor: "rgba(52,211,153,0.1)",
                                }}
                              >
                                O{Math.round(prop.over_probability * 100)}
                              </span>
                              <span
                                className="font-mono font-bold text-[0.95vh] px-[0.2vw] rounded"
                                style={{
                                  color: "#f87171",
                                  backgroundColor: "rgba(248,113,113,0.1)",
                                }}
                              >
                                U{Math.round(prop.under_probability * 100)}
                              </span>
                            </div>
                          ) : prop.probability != null ? (
                            <span
                              className="font-mono font-bold text-[1vh] shrink-0"
                              style={{ color: catColor }}
                            >
                              {Math.round(prop.probability * 100)}%
                            </span>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </AutoScrollContainer>
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
  const [showQR, setShowQR] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);

  // Contest state
  const [contestData, setContestData] = useState<ContestData | null>(null);
  const [commentary, setCommentary] = useState("");
  const [adData, setAdData] = useState<AdLeaderboardData | null>(null);

  // Resolution notification queue — full-screen, shown one at a time
  const [resolutionQueue, setResolutionQueue] = useState<
    { question: string; answer: string }[]
  >([]);
  const [activeResolution, setActiveResolution] = useState<{
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

        // Queue ALL newly resolved props for full-screen display
        const resolvedProps = newlyResolved
          .map((id) => data.props.find((p) => p.id === id))
          .filter(Boolean)
          .map((p) => ({
            question: p!.question,
            answer: p!.correct_answer || "",
          }));

        if (resolvedProps.length > 0) {
          setResolutionQueue((prev) => [...prev, ...resolvedProps]);
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

  // ---- Ad Leaderboard polling (every 2 minutes) ----
  const fetchAds = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/contest/ads`);
      if (!resp.ok) return;
      const data: AdLeaderboardData = await resp.json();
      setAdData(data);
    } catch {
      // Silently ignore
    }
  }, []);

  useEffect(() => {
    fetchAds();
    const interval = setInterval(fetchAds, 120000); // 2 minutes
    return () => clearInterval(interval);
  }, [fetchAds]);

  // Process resolution queue: show one at a time for 8 seconds each
  useEffect(() => {
    if (activeResolution || resolutionQueue.length === 0) return;
    const [next, ...rest] = resolutionQueue;
    setActiveResolution(next);
    setResolutionQueue(rest);
    // Fire confetti for each resolution in the queue
    setConfettiColors(["#69BE28", "#C60C30", "#FFD700", "#00D4FF", "#FF1493"]);
    setConfettiActive(true);
    const timer = setTimeout(() => {
      setActiveResolution(null);
      setConfettiActive(false);
    }, 8000);
    return () => clearTimeout(timer);
  }, [activeResolution, resolutionQueue]);

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

          {/* Sportsbook Prop Odds (from The Odds API) */}
          <div className="bg-[#111118] rounded-2xl p-[1vw] border border-white/5 flex flex-col min-h-0 overflow-hidden">
            <TVSportsbookProps eventId={eventId} />
          </div>
        </div>

        {/* === CONTEST LEADERBOARD + ADS + SIDEBAR (~55% of remaining) === */}
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

          {/* Ad Leaderboard (1 column) */}
          <div className="bg-[#111118] rounded-2xl p-[1vw] border border-white/5 min-h-0 overflow-hidden">
            {adData && adData.ads.length > 0 ? (
              <TVAdLeaderboard ads={adData.ads} />
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-white/20 text-[1.3vh] gap-[0.5vh]">
                <span className="text-[2vh]">{"\uD83D\uDCFA"}</span>
                {adData && !adData.youtube_configured ? (
                  <span>YouTube API key not configured</span>
                ) : (
                  <span>Loading ad leaderboard...</span>
                )}
              </div>
            )}
          </div>

          {/* Contest Sidebar (1 column) */}
          <div className="bg-[#111118] rounded-2xl p-[1vw] border border-white/5 min-h-0 overflow-hidden">
            {contestData ? (
              <TVContestSidebar
                props={contestData.props}
                commentary={commentary}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-white/20 text-[1.3vh]">
                Loading props...
              </div>
            )}
          </div>

        </div>
      </div>

      {/* ===== FULL-SCREEN RESOLUTION OVERLAY ===== */}
      {activeResolution && (
        <div className="fixed inset-0 z-[10001] flex items-center justify-center pointer-events-none">
          {/* Dark backdrop */}
          <div className="absolute inset-0 bg-black/60" />
          {/* Animated banner */}
          <div
            className="relative z-10 w-[80vw] max-w-[1200px] rounded-3xl px-[4vw] py-[4vh] text-center"
            style={{
              background: "linear-gradient(135deg, #69BE28 0%, #003831 40%, #C60C30 100%)",
              animation: "resolutionSlideIn 0.5s ease-out",
              boxShadow: "0 0 80px rgba(105, 190, 40, 0.3), 0 0 80px rgba(198, 12, 48, 0.3)",
            }}
          >
            <div
              className="text-[2.5vh] font-black uppercase tracking-[0.3em] mb-[1vh]"
              style={{ color: "#FFD700" }}
            >
              Prop Resolved!
            </div>
            <div className="text-white/80 text-[2vh] mb-[1.5vh] leading-snug">
              {activeResolution.question}
            </div>
            <div
              className="text-[5vh] font-black uppercase tracking-wide"
              style={{
                color: "#FFFFFF",
                textShadow: "0 0 30px rgba(255,215,0,0.5)",
              }}
            >
              {activeResolution.answer}
            </div>
            {/* Progress bar showing how long it'll stay */}
            <div className="mt-[2vh] mx-auto w-[40%] h-[0.4vh] bg-white/20 rounded-full overflow-hidden">
              <div
                className="h-full bg-white/60 rounded-full"
                style={{
                  animation: "resolutionProgress 8s linear",
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ===== ADMIN PANEL (phone-friendly) ===== */}
      {showAdmin && contestData && (
        <div
          className="fixed inset-0 z-[10002] bg-black/90 overflow-y-auto p-[2vw]"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowAdmin(false);
          }}
        >
          <div className="max-w-2xl mx-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white text-xl font-bold">Contest Admin</h2>
              <button
                onClick={() => setShowAdmin(false)}
                className="text-white/50 hover:text-white text-2xl px-2"
              >
                &times;
              </button>
            </div>

            {/* Resolved props */}
            <div className="mb-6">
              <h3 className="text-white/50 text-sm uppercase tracking-wider mb-2">
                Resolved ({contestData.props.filter((p) => p.resolved).length})
              </h3>
              <div className="space-y-2">
                {contestData.props
                  .filter((p) => p.resolved)
                  .map((prop) => (
                    <div
                      key={prop.id}
                      className="bg-white/5 rounded-lg p-3 flex items-center justify-between"
                    >
                      <div>
                        <div className="text-white/60 text-sm">
                          {prop.question}
                        </div>
                        <div className="text-emerald-400 font-bold">
                          {prop.correct_answer}
                        </div>
                      </div>
                      <button
                        onClick={async () => {
                          if (!confirm(`Unresolve "${prop.question}"?`)) return;
                          await fetch(
                            `${API_URL}/api/contest/unresolve?prop_id=${prop.id}&secret=admin`,
                            { method: "POST" }
                          );
                          fetchContest();
                        }}
                        className="bg-red-500/20 text-red-400 px-3 py-1 rounded text-sm font-bold hover:bg-red-500/30 shrink-0 ml-2"
                      >
                        Undo
                      </button>
                    </div>
                  ))}
              </div>
            </div>

            {/* Unresolved props — tap to resolve */}
            <div>
              <h3 className="text-white/50 text-sm uppercase tracking-wider mb-2">
                Unresolved ({contestData.props.filter((p) => !p.resolved && !p.is_tiebreaker).length})
              </h3>
              <div className="space-y-2">
                {contestData.props
                  .filter((p) => !p.resolved && !p.is_tiebreaker)
                  .map((prop) => (
                    <div key={prop.id} className="bg-white/5 rounded-lg p-3">
                      <div className="text-white/80 text-sm mb-2">
                        {prop.question}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {Object.keys(prop.choices).map((choice) => (
                          <button
                            key={choice}
                            onClick={async () => {
                              if (!confirm(`Resolve "${prop.question}" as "${choice}"?`)) return;
                              await fetch(
                                `${API_URL}/api/contest/resolve?prop_id=${prop.id}&correct_answer=${encodeURIComponent(choice)}&secret=admin`,
                                { method: "POST" }
                              );
                              fetchContest();
                            }}
                            className="bg-blue-500/20 text-blue-300 px-2 py-1 rounded text-xs font-medium hover:bg-blue-500/30"
                          >
                            {choice}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Keyframe animations for resolution overlay */}
      <style jsx global>{`
        @keyframes resolutionSlideIn {
          from { transform: scale(0.8) translateY(20px); opacity: 0; }
          to { transform: scale(1) translateY(0); opacity: 1; }
        }
        @keyframes resolutionProgress {
          from { width: 100%; }
          to { width: 0%; }
        }
      `}</style>

      {/* QR Code Overlay */}
      {showQR && (
        <div
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/80 backdrop-blur-sm cursor-pointer"
          onClick={() => setShowQR(false)}
        >
          <div className="bg-white rounded-3xl p-[2vw] flex flex-col items-center gap-[1.5vh]">
            <img
              src="/sb-contest-qr.png"
              alt="Scan to join the contest"
              style={{ width: "35vh", height: "35vh" }}
              className="rounded-xl"
            />
            <div className="text-black text-center">
              <div className="font-bold text-[2.5vh]">Join the Contest!</div>
              <div className="text-[1.5vh] text-gray-500 mt-[0.3vh]">
                Scan to submit your picks
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Bottom bar: Exit + QR toggle */}
      <div className="fixed bottom-[1vh] left-[1vw] right-[1vw] z-50 flex items-center justify-between">
        <a
          href={`/events/${eventId}`}
          className="text-white/20 hover:text-white/60 text-[1.2vh] transition-colors bg-black/50 px-[1vw] py-[0.4vh] rounded-full backdrop-blur"
        >
          Exit TV Mode
        </a>
        <div className="flex items-center gap-[0.5vw]">
          <button
            onClick={() => setShowAdmin(true)}
            className="text-white/20 hover:text-white/50 text-[1.2vh] transition-colors bg-black/50 px-[0.8vw] py-[0.4vh] rounded-full backdrop-blur"
          >
            Admin
          </button>
          <button
            onClick={() => setShowQR(true)}
            className="text-white/30 hover:text-white/70 text-[1.5vh] transition-colors bg-black/50 px-[1vw] py-[0.4vh] rounded-full backdrop-blur flex items-center gap-[0.4vw]"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-[1.8vh] h-[1.8vh]">
              <path d="M3 3h8v8H3V3zm2 2v4h4V5H5zm8-2h8v8h-8V3zm2 2v4h4V5h-4zM3 13h8v8H3v-8zm2 2v4h4v-4H5zm11-2h2v2h-2v-2zm-4 0h2v2h-2v-2zm0 4h2v2h-2v-2zm4 0h2v2h-2v-2zm2 2h2v2h-2v-2zm-4 2h2v2h-2v-2zm4 0h2v2h-2v-2z"/>
            </svg>
            QR Code
          </button>
        </div>
      </div>
    </div>
  );
}
