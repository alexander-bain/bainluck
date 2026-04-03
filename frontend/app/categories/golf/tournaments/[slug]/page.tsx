"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchGolfTournament, fetchGolfLeaderboard, fetchFuturesHistory } from "@/lib/api";
import type {
  GolfTournamentDetailResponse,
  GolfGolfer,
  GolfLeaderboardResponse,
  GolfLeaderboardPlayer,
} from "@/lib/types";
import { TOURNAMENT_EMOJI } from "@/lib/golfData";
import { EvolutionView } from "@/components/EvolutionView";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// ============================================================================
// Evolution chart with fallback — tries market IDs in order
// ============================================================================

function EvolutionViewWithFallback({
  marketIds,
  marketName,
  defaultTopN,
  hours,
}: {
  marketIds: number[];
  marketName: string;
  defaultTopN: number;
  hours: number;
}) {
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    setCurrentIndex(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketIds.join(",")]);

  const marketId = marketIds[currentIndex];
  if (!marketId) return null;

  return (
    <EvolutionViewWithCallback
      key={marketId}
      marketId={marketId}
      marketName={marketName}
      defaultTopN={defaultTopN}
      hours={hours}
      onEmpty={() => {
        if (currentIndex + 1 < marketIds.length) {
          setCurrentIndex(currentIndex + 1);
        }
      }}
    />
  );
}

function EvolutionViewWithCallback({
  marketId,
  marketName,
  defaultTopN,
  hours,
  onEmpty,
}: {
  marketId: number;
  marketName: string;
  defaultTopN: number;
  hours: number;
  onEmpty: () => void;
}) {
  const [hasData, setHasData] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFuturesHistory(marketId, hours, undefined, 30)
      .then((data) => {
        if (cancelled) return;
        if (data.outcomes.length === 0) {
          setHasData(false);
          onEmpty();
        } else {
          setHasData(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHasData(false);
          onEmpty();
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketId, hours]);

  if (hasData === null) {
    return <div className="h-64 bg-gray-50 rounded-xl border border-gray-200 animate-pulse" />;
  }
  if (!hasData) return null;

  return (
    <EvolutionView
      marketId={marketId}
      marketName={marketName}
      defaultTopN={defaultTopN}
      hours={hours}
    />
  );
}

// ============================================================================
// Data merging — combine tournament odds with live leaderboard scores
// ============================================================================

interface MergedGolfer {
  position: string;
  name: string;
  score: string;
  totalScoreRaw: number | null;
  today: string;
  todayRaw: number | null;
  thru: string;
  hole: string;
  winProb: number; // 0-100 percentage
  winProbChange: number | null;
  top5Prob: number | null;
  top10Prob: number | null;
  top20Prob: number | null;
  makeCutProb: number | null;
  movement24h: number | null; // decimal (0-1)
  rank: number;
  hasLiveData: boolean;
}

function normalizeGolferName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z\s]/g, "")
    .trim();
}

function buildMergedGolfers(
  oddsGolfers: GolfGolfer[],
  leaderboard: GolfLeaderboardResponse | null
): MergedGolfer[] {
  if (leaderboard && leaderboard.status === "live" && leaderboard.players.length > 0) {
    const oddsMap = new Map<string, GolfGolfer>();
    for (const g of oddsGolfers) {
      oddsMap.set(normalizeGolferName(g.name), g);
    }

    return leaderboard.players.map((p, i) => {
      const oddsGolfer = oddsMap.get(normalizeGolferName(p.name));
      return {
        position: p.position,
        name: p.name,
        score: p.score,
        totalScoreRaw: p.total_score_raw,
        today: p.today,
        todayRaw: p.today_raw,
        thru: p.thru,
        hole: p.hole,
        winProb: p.win_prob,
        winProbChange: p.win_prob_change,
        top5Prob: p.top_5_prob,
        top10Prob: p.top_10_prob,
        top20Prob: p.top_20_prob,
        makeCutProb: p.make_cut_prob,
        movement24h: oddsGolfer?.movement_24h ?? null,
        rank: i + 1,
        hasLiveData: true,
      };
    });
  }

  return oddsGolfers.map((g, i) => ({
    position: String(g.rank ?? i + 1),
    name: g.name,
    score: "\u2014",
    totalScoreRaw: null,
    today: "\u2014",
    todayRaw: null,
    thru: "\u2014",
    hole: "",
    winProb: g.probability * 100,
    winProbChange: null,
    top5Prob: null,
    top10Prob: null,
    top20Prob: null,
    makeCutProb: null,
    movement24h: g.movement_24h,
    rank: g.rank ?? i + 1,
    hasLiveData: false,
  }));
}

function isTournamentLive(
  tournament: GolfTournamentDetailResponse["tournament"],
  leaderboard: GolfLeaderboardResponse | null
): boolean {
  if (!leaderboard || leaderboard.status !== "live" || !leaderboard.event_name) return false;
  const tName = tournament.name.toLowerCase();
  const eName = leaderboard.event_name.toLowerCase();
  if (eName.includes("masters") && tName.includes("masters")) return true;
  if (eName.includes("pga championship") && tName.includes("pga championship")) return true;
  if (eName.includes("u.s. open") && tName.includes("u.s. open")) return true;
  if (eName.includes("open championship") && tName.includes("open")) return true;
  const tWords = tName.split(/\s+/).filter((w) => w.length > 3);
  return tWords.some((w) => eName.includes(w));
}

// ============================================================================
// Main page component
// ============================================================================

export default function GolfTournamentPage() {
  const params = useParams();
  const slug = params?.slug as string;

  usePageTracking({ pageType: "golf_tournament", pageTitle: `Golf Tournament: ${slug}` });
  useScrollDepth({ pageType: "golf_tournament" });
  useEngagementTime({ pageType: "golf_tournament" });

  const [data, setData] = useState<GolfTournamentDetailResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<GolfLeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    if (!slug) return;
    try {
      const [tResult, lbResult] = await Promise.allSettled([
        fetchGolfTournament(slug),
        fetchGolfLeaderboard("pga"),
      ]);

      if (tResult.status === "fulfilled") {
        setData(tResult.value);
      } else {
        setError("Failed to load tournament");
        return;
      }

      if (lbResult.status === "fulfilled") {
        setLeaderboard(lbResult.value);
      }

      setError(null);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading) return <LoadingSkeleton />;
  if (error && !data) return <ErrorState message={error} />;
  if (!data) return <ErrorState message="Tournament not found" />;

  const { tournament, golfers, markets, evolution_market_id } = data;
  const emoji = TOURNAMENT_EMOJI[tournament.key || ""] || "\u26F3";
  const isMasters = /masters/i.test(tournament.name);
  const accentColor = isMasters ? "#006747" : "#059669";

  const isLive = isTournamentLive(tournament, leaderboard);
  const currentRound = isLive && leaderboard ? leaderboard.current_round : null;
  const showBubbleWatch = isLive && currentRound != null && currentRound <= 2;

  // Tournament status badge
  let statusLabel = "";
  let statusBg = "";
  if (isLive) {
    statusLabel = currentRound ? `Round ${currentRound}` : "In Progress";
  } else if (tournament.start_date && tournament.end_date) {
    const now = new Date();
    const start = new Date(tournament.start_date);
    const end = new Date(tournament.end_date);
    if (now > end) {
      statusLabel = "Completed";
      statusBg = "bg-gray-100 text-gray-500 border-gray-200";
    } else {
      const days = Math.ceil((start.getTime() - now.getTime()) / 86400000);
      statusLabel =
        days <= 7
          ? `Starts ${start.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`
          : "Upcoming";
      statusBg = "bg-blue-50 text-blue-700 border-blue-200";
    }
  }

  const mergedGolfers = buildMergedGolfers(golfers, isLive ? leaderboard : null);

  const winnerGroup = markets.find((g) => g.type === "winner");
  const evolutionMarketIds = winnerGroup?.market_ids || (evolution_market_id ? [evolution_market_id] : []);

  // Collect sources for attribution
  const sources: string[] = [];
  if (isLive) sources.push("DataGolf");
  if (golfers.length > 0) {
    const allSources = new Set<string>();
    golfers.forEach((g) => Object.keys(g.sources).forEach((s) => allSources.add(s)));
    if (allSources.has("kalshi")) sources.push("Kalshi");
    if (allSources.has("polymarket")) sources.push("Polymarket");
    const sbCount = [...allSources].filter(
      (s) => !["kalshi", "polymarket", "datagolf"].includes(s)
    ).length;
    if (sbCount > 0) sources.push("Sportsbooks");
  }

  return (
    <main className="min-h-screen bg-white">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Breadcrumb */}
        <nav className="text-xs text-gray-400">
          <Link href="/categories/golf" className="hover:text-gray-700 hover:underline">
            Golf
          </Link>
          <span className="mx-1.5">/</span>
          <span className="text-gray-700">{tournament.name}</span>
        </nav>

        {/* Tournament Header */}
        <header className="border border-gray-200 rounded-xl p-5">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                {isMasters ? (
                  <span
                    className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full text-white uppercase tracking-wider"
                    style={{ backgroundColor: accentColor }}
                  >
                    The Masters
                  </span>
                ) : (
                  <span className="text-xl">{emoji}</span>
                )}
                {isLive && (
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-green-50 text-green-600 border border-green-200">
                    <span className="w-[6px] h-[6px] rounded-full bg-green-500 animate-pulse" />
                    {statusLabel}
                  </span>
                )}
                {!isLive && statusLabel && (
                  <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full border ${statusBg}`}>
                    {statusLabel}
                  </span>
                )}
              </div>
              <h1 className="text-xl font-bold text-gray-900">{tournament.name}</h1>
              <div className="flex items-center gap-2 text-sm text-gray-500 mt-0.5 flex-wrap">
                {tournament.venue && <span>{tournament.venue}</span>}
                {tournament.start_date && tournament.end_date && (
                  <>
                    <span className="text-gray-300">&middot;</span>
                    <span>
                      {new Date(tournament.start_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      {"\u2013"}
                      {new Date(tournament.end_date).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="text-right">
              {sources.length > 0 && (
                <div className="flex gap-1.5 flex-wrap justify-end">
                  {sources.map((src) => (
                    <span
                      key={src}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-200"
                    >
                      {src}
                    </span>
                  ))}
                </div>
              )}
              {isLive && lastRefresh && (
                <p className="text-[10px] text-gray-400 mt-1">
                  Updated {lastRefresh.toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        </header>

        {/* Evolution Chart */}
        {evolutionMarketIds.length > 0 && (
          <section>
            <EvolutionViewWithFallback
              marketIds={evolutionMarketIds}
              marketName={`${tournament.name} - Winner`}
              defaultTopN={8}
              hours={168}
            />
          </section>
        )}

        {/* Bubble Watch — Rounds 1-2 only */}
        {showBubbleWatch && leaderboard && (
          <BubbleWatch players={leaderboard.players} currentRound={currentRound} />
        )}

        {/* Leaderboard Grid */}
        <LeaderboardGrid
          golfers={mergedGolfers}
          accentColor={accentColor}
          isLive={isLive}
          hasSnapshot={leaderboard?.has_snapshot || false}
        />

        {/* Footer */}
        <p className="text-center text-[11px] text-gray-400">
          Probabilities from {isLive ? "DataGolf in-play model" : "sportsbook consensus"}.
          {isLive && " Auto-refreshes every 60s."}
          {isLive && lastRefresh && <> Last: {lastRefresh.toLocaleTimeString()}</>}
        </p>
      </div>
    </main>
  );
}

// ============================================================================
// Leaderboard Grid
// ============================================================================

function LeaderboardGrid({
  golfers,
  accentColor,
  isLive,
  hasSnapshot,
}: {
  golfers: MergedGolfer[];
  accentColor: string;
  isLive: boolean;
  hasSnapshot: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const INITIAL_SHOW = 30;
  const displayGolfers = showAll ? golfers : golfers.slice(0, INITIAL_SHOW);

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          {isLive ? "Leaderboard" : "Field & Odds"}
        </h2>
        <span className="text-[10px] text-gray-400">
          {golfers.length} golfer{golfers.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* ── Desktop table ── */}
      <div className="hidden sm:block border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b-2 border-gray-200 bg-gray-50/80">
              <th className="text-left text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-3 py-2.5 w-10">
                Pos
              </th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-3 py-2.5">
                Golfer
              </th>
              {isLive && (
                <>
                  <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-14">
                    Score
                  </th>
                  <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-12">
                    Today
                  </th>
                  <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-10">
                    Thru
                  </th>
                </>
              )}
              <th
                className="text-center text-[10px] font-semibold uppercase tracking-wide px-2 py-2.5 w-20"
                style={{ color: accentColor }}
              >
                Win
              </th>
              {isLive && (
                <>
                  <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-14">
                    Top 5
                  </th>
                  <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-14">
                    Top 10
                  </th>
                  <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-14">
                    Top 20
                  </th>
                </>
              )}
              {!isLive && (
                <th className="text-center text-[10px] font-semibold uppercase tracking-wide text-gray-400 px-2 py-2.5 w-14">
                  24h
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {displayGolfers.map((golfer, i) => (
              <DesktopRow
                key={`${golfer.name}-${i}`}
                golfer={golfer}
                isLeader={i === 0}
                accentColor={accentColor}
                isLive={isLive}
                hasSnapshot={hasSnapshot}
              />
            ))}
          </tbody>
        </table>
        {golfers.length > INITIAL_SHOW && (
          <div className="px-3 py-2 border-t border-gray-100 text-center">
            <button
              onClick={() => setShowAll((s) => !s)}
              className="text-xs font-medium hover:underline"
              style={{ color: accentColor }}
            >
              {showAll ? "Show top 30" : `Show all ${golfers.length} golfers`}
            </button>
          </div>
        )}
      </div>

      {/* ── Mobile layout ── */}
      <div className="sm:hidden space-y-0.5">
        <div className="flex items-center text-[9px] text-gray-400 uppercase tracking-wider font-medium px-1 mb-1">
          <div className="w-7">Pos</div>
          <div className="flex-1">Golfer</div>
          {isLive && (
            <>
              <div className="w-10 text-center">Tot</div>
              <div className="w-10 text-center">Tdy</div>
            </>
          )}
          <div className="w-14 text-center font-semibold" style={{ color: accentColor }}>
            Win
          </div>
          {isLive && <div className="w-9 text-center">T5</div>}
          {!isLive && <div className="w-9 text-center">24h</div>}
        </div>

        {displayGolfers.map((golfer, i) => (
          <MobileRow
            key={`m-${golfer.name}-${i}`}
            golfer={golfer}
            isLeader={i === 0}
            accentColor={accentColor}
            isLive={isLive}
          />
        ))}

        {golfers.length > INITIAL_SHOW && (
          <div className="text-center py-2">
            <button
              onClick={() => setShowAll((s) => !s)}
              className="text-xs font-medium hover:underline"
              style={{ color: accentColor }}
            >
              {showAll ? "Show top 30" : `Show all ${golfers.length}`}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

// ── Desktop row ──

function DesktopRow({
  golfer,
  isLeader,
  accentColor,
  isLive,
  hasSnapshot,
}: {
  golfer: MergedGolfer;
  isLeader: boolean;
  accentColor: string;
  isLive: boolean;
  hasSnapshot: boolean;
}) {
  const scoreColor =
    golfer.totalScoreRaw != null && golfer.totalScoreRaw < 0
      ? "text-green-600 font-semibold"
      : golfer.totalScoreRaw != null && golfer.totalScoreRaw > 0
        ? "font-semibold"
        : "";

  const todayColor =
    golfer.todayRaw != null && golfer.todayRaw < 0
      ? "text-green-600"
      : golfer.todayRaw != null && golfer.todayRaw > 0
        ? "text-red-500"
        : "text-gray-400";

  // Win prob change indicator
  const wpc = golfer.winProbChange;
  let wpcDisplay = "";
  let wpcColor = "";
  if (hasSnapshot && wpc != null && Math.abs(wpc) >= 0.1) {
    wpcDisplay = wpc > 0 ? `\u2191${wpc.toFixed(1)}` : `\u2193${Math.abs(wpc).toFixed(1)}`;
    wpcColor = wpc > 0 ? "text-green-600" : "text-red-500";
  }

  // 24h movement for pre-tournament
  const mv = golfer.movement24h;
  const hasMv = mv != null && Math.abs(mv) >= 0.005;
  const mvDelta = hasMv ? Math.abs(Math.round(mv! * 100)) : 0;
  const mvUp = hasMv && mv! > 0;

  return (
    <tr
      className={`border-b border-gray-100 ${isLeader ? "border-l-2" : "hover:bg-gray-50/50"}`}
      style={
        isLeader
          ? { borderLeftColor: accentColor, backgroundColor: `${accentColor}08` }
          : undefined
      }
    >
      <td
        className="px-3 py-2.5 font-semibold tabular-nums"
        style={{ color: isLeader ? accentColor : "#9ca3af" }}
      >
        {golfer.position}
      </td>
      <td className="px-3 py-2.5 font-medium text-gray-900">{golfer.name}</td>
      {isLive && (
        <>
          <td className={`px-2 py-2.5 text-center font-mono text-sm tabular-nums ${scoreColor}`}>
            {golfer.score}
          </td>
          <td className={`px-2 py-2.5 text-center font-mono text-xs tabular-nums ${todayColor}`}>
            {golfer.today}
          </td>
          <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-gray-400">
            {golfer.thru}
          </td>
        </>
      )}
      <td className="px-2 py-2.5 text-center tabular-nums">
        <span
          className="text-sm font-bold"
          style={isLeader ? { color: accentColor } : undefined}
        >
          {golfer.winProb.toFixed(1)}%
        </span>
        {wpcDisplay && (
          <span className={`text-[9px] ml-0.5 ${wpcColor}`}>{wpcDisplay}</span>
        )}
      </td>
      {isLive && (
        <>
          <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-gray-500">
            {golfer.top5Prob != null ? `${Math.round(golfer.top5Prob)}%` : "\u2014"}
          </td>
          <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-gray-500">
            {golfer.top10Prob != null ? `${Math.round(golfer.top10Prob)}%` : "\u2014"}
          </td>
          <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-gray-500">
            {golfer.top20Prob != null ? `${Math.round(golfer.top20Prob)}%` : "\u2014"}
          </td>
        </>
      )}
      {!isLive && (
        <td
          className={`px-2 py-2.5 text-center tabular-nums text-xs ${
            hasMv
              ? mvUp
                ? "text-green-600 font-semibold"
                : "text-red-500 font-semibold"
              : "text-gray-300"
          }`}
        >
          {hasMv ? (mvUp ? `\u25B2${mvDelta}%` : `\u25BC${mvDelta}%`) : "\u2014"}
        </td>
      )}
    </tr>
  );
}

// ── Mobile row ──

function MobileRow({
  golfer,
  isLeader,
  accentColor,
  isLive,
}: {
  golfer: MergedGolfer;
  isLeader: boolean;
  accentColor: string;
  isLive: boolean;
}) {
  const scoreColor =
    golfer.totalScoreRaw != null && golfer.totalScoreRaw < 0
      ? "text-green-600 font-bold"
      : "text-gray-700 font-bold";

  const todayColor =
    golfer.todayRaw != null && golfer.todayRaw < 0
      ? "text-green-600"
      : golfer.todayRaw != null && golfer.todayRaw > 0
        ? "text-red-500"
        : "text-gray-400";

  const mv = golfer.movement24h;
  const hasMv = mv != null && Math.abs(mv) >= 0.005;
  const mvDelta = hasMv ? Math.abs(Math.round(mv! * 100)) : 0;
  const mvUp = hasMv && mv! > 0;

  const lastName = golfer.name.split(" ").pop() || golfer.name;

  return (
    <div
      className={`flex items-center px-2 py-2.5 rounded-lg ${
        isLeader ? "border" : ""
      }`}
      style={
        isLeader
          ? { backgroundColor: `${accentColor}08`, borderColor: `${accentColor}30` }
          : undefined
      }
    >
      <div
        className="w-7 text-xs font-bold tabular-nums"
        style={{ color: isLeader ? accentColor : "#9ca3af" }}
      >
        {golfer.position}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-gray-900 truncate">{lastName}</div>
        {isLive && (
          <div className="text-[9px] text-gray-400">
            {golfer.thru === "F" ? "F" : `Thru ${golfer.thru}`}
          </div>
        )}
      </div>
      {isLive && (
        <>
          <div className={`w-10 text-center font-mono text-sm tabular-nums ${scoreColor}`}>
            {golfer.score}
          </div>
          <div className={`w-10 text-center font-mono text-xs tabular-nums ${todayColor}`}>
            {golfer.today}
          </div>
        </>
      )}
      <div className="w-14 text-center">
        <div
          className="text-sm font-bold tabular-nums"
          style={isLeader ? { color: accentColor } : undefined}
        >
          {golfer.winProb.toFixed(1)}%
        </div>
        {isLive && golfer.winProbChange != null && Math.abs(golfer.winProbChange) >= 0.1 && (
          <div
            className={`text-[8px] ${golfer.winProbChange > 0 ? "text-green-600" : "text-red-500"}`}
          >
            {golfer.winProbChange > 0 ? "\u2191" : "\u2193"}
            {Math.abs(golfer.winProbChange).toFixed(1)}
          </div>
        )}
      </div>
      {isLive && (
        <div className="w-9 text-center font-mono text-xs tabular-nums text-gray-500">
          {golfer.top5Prob != null ? `${Math.round(golfer.top5Prob)}%` : "\u2014"}
        </div>
      )}
      {!isLive && (
        <div
          className={`w-9 text-center text-[10px] tabular-nums ${
            hasMv
              ? mvUp
                ? "text-green-600 font-semibold"
                : "text-red-500 font-semibold"
              : "text-gray-300"
          }`}
        >
          {hasMv ? (mvUp ? `\u25B2${mvDelta}` : `\u25BC${mvDelta}`) : "\u2014"}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Bubble Watch — Cut Line Tracker (R1-R2 only)
// ============================================================================

function BubbleWatch({
  players,
  currentRound,
}: {
  players: GolfLeaderboardPlayer[];
  currentRound: number | null;
}) {
  const bubblePlayers = players
    .filter((p) => p.make_cut_prob != null && p.make_cut_prob >= 15 && p.make_cut_prob <= 85)
    .sort((a, b) => (b.make_cut_prob ?? 0) - (a.make_cut_prob ?? 0));

  if (bubblePlayers.length === 0) return null;

  // Estimate projected cut from the median bubble player
  const midIdx = Math.floor(bubblePlayers.length / 2);
  const projectedCut = bubblePlayers[midIdx]?.score || "+4";

  const safe = bubblePlayers.filter((p) => (p.make_cut_prob ?? 0) >= 50).slice(-3);
  const bubble = bubblePlayers.filter((p) => (p.make_cut_prob ?? 0) < 50).slice(0, 3);

  return (
    <section className="border border-amber-200 rounded-xl overflow-hidden bg-amber-50/30">
      <div className="px-4 py-3 flex items-center gap-2 flex-wrap">
        <span className="text-base">{"\u2702\uFE0F"}</span>
        <h2 className="text-xs font-semibold text-amber-700 uppercase tracking-wider">
          Bubble Watch
        </h2>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">
          Projected Cut: {projectedCut}
        </span>
        {currentRound && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100/50 text-amber-600 border border-amber-200/50">
            Round {currentRound} in progress
          </span>
        )}
      </div>

      <div className="px-4 pb-4 space-y-1">
        {/* Safe side label */}
        <div className="text-[9px] text-gray-400 uppercase tracking-wider font-medium px-2 mb-0.5">
          Safe &mdash; will make cut
        </div>

        {safe.map((p) => (
          <BubbleRow key={p.name} player={p} side="safe" />
        ))}

        {/* Cut line */}
        <div className="relative my-2.5">
          <div className="border-t-2 border-dashed border-amber-400" />
          <div className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-3 py-0.5 bg-white border border-amber-300 rounded-full">
            <span className="text-[10px] font-bold text-amber-600">
              {"\u2702\uFE0F"} CUT LINE &middot; {projectedCut}
            </span>
          </div>
        </div>

        {/* Bubble side label */}
        <div className="text-[9px] text-gray-400 uppercase tracking-wider font-medium px-2 mb-0.5">
          On the bubble
        </div>

        {bubble.map((p) => (
          <BubbleRow key={p.name} player={p} side="bubble" />
        ))}

        <p className="text-[10px] text-amber-600/70 text-center mt-2">
          {safe.length + bubble.length} golfers near the cut
        </p>
      </div>
    </section>
  );
}

function BubbleRow({
  player,
  side,
}: {
  player: GolfLeaderboardPlayer;
  side: "safe" | "bubble";
}) {
  const prob = player.make_cut_prob ?? 0;
  const probColor = prob >= 70 ? "text-green-600" : prob >= 40 ? "text-amber-600" : "text-red-500";
  const barColor = prob >= 70 ? "bg-green-500" : prob >= 40 ? "bg-amber-500" : "bg-red-500";

  return (
    <div
      className={`flex items-center justify-between rounded-lg px-3 py-2 ${
        side === "bubble" ? "bg-red-50/50 border border-red-100" : "bg-white"
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="text-xs font-bold text-gray-400 w-6">{player.position}</span>
        <span className="text-sm font-medium text-gray-900">{player.name}</span>
      </div>
      <div className="flex items-center gap-4">
        <span
          className={`font-mono text-sm ${
            player.total_score_raw != null && player.total_score_raw > 0
              ? "text-gray-700"
              : "text-green-600"
          }`}
        >
          {player.score}
        </span>
        <div className="w-24">
          <div className="flex items-center justify-between text-xs mb-0.5">
            <span className={`font-semibold ${probColor}`}>{Math.round(prob)}%</span>
            <span className="text-[9px] text-gray-400">make cut</span>
          </div>
          <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${barColor}`} style={{ width: `${prob}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Loading & Error states
// ============================================================================

function LoadingSkeleton() {
  return (
    <main className="min-h-screen bg-white">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        <div className="h-4 w-24 bg-gray-100 rounded animate-pulse" />
        <div className="border border-gray-200 rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-5 w-20 bg-gray-100 rounded-full animate-pulse" />
            <div className="h-5 w-16 bg-gray-100 rounded-full animate-pulse" />
          </div>
          <div className="h-7 w-64 bg-gray-100 rounded animate-pulse" />
          <div className="h-4 w-48 bg-gray-100 rounded animate-pulse" />
        </div>
        <div className="space-y-1">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} className="h-10 bg-gray-50 rounded animate-pulse" />
          ))}
        </div>
      </div>
    </main>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <main className="min-h-screen bg-white flex items-center justify-center">
      <div className="text-center space-y-4">
        <p className="text-lg text-gray-500">{message}</p>
        <Link
          href="/categories/golf"
          className="inline-block text-sm hover:underline"
          style={{ color: "#006747" }}
        >
          &larr; Back to Golf
        </Link>
      </div>
    </main>
  );
}
