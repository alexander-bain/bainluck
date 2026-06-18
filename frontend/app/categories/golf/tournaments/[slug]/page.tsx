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
import type { PositionOption } from "@/components/EvolutionView";
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
        if (data.outcomes.length < 3) {
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
  if (leaderboard && leaderboard.players.length > 0) {
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
    top5Prob: g.top_5_prob ?? null,
    top10Prob: g.top_10_prob ?? null,
    top20Prob: g.top_20_prob ?? null,
    makeCutProb: g.make_cut_prob ?? null,
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

  // Date-based validation: tournament must be within its scheduled window
  // to prevent stale "LIVE" badges on completed tournaments
  if (tournament.end_date) {
    const endDate = new Date(tournament.end_date);
    // Add 1 day buffer after end_date (tournaments can finish late)
    endDate.setDate(endDate.getDate() + 1);
    if (new Date() > endDate) return false;
  }

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

  // Build position options for the evolution chart toggle (must be before early returns)
  const positionOptions = useMemo(() => {
    if (!data) return [];
    const opts: PositionOption[] = [];
    const typeMap: { type: string; key: string; label: string }[] = [
      { type: "top_20", key: "top_20", label: "Top 20" },
      { type: "top_10", key: "top_10", label: "Top 10" },
      { type: "top_5", key: "top_5", label: "Top 5" },
      { type: "winner", key: "win", label: "Win" },
    ];
    for (const { type, key, label } of typeMap) {
      const group = data.markets.find((g) => g.type === type);
      if (group && group.market_ids.length > 0) {
        let primary = group.market_ids[0];
        let marketIds = group.market_ids;
        // #955: the "winner" group still contains the "Winner Nationality" prop
        // market (US/England/Spain) + Yes/No binaries, so market_ids[0] plotted
        // nationalities, not golfers. The backend (_NON_CONTENDER_WINNER_RE)
        // already picked the real golfer winner field as evolution_market_id —
        // use it as the primary series, keeping the rest as ordered fallbacks.
        if (type === "winner" && data.evolution_market_id) {
          primary = data.evolution_market_id;
          marketIds = [
            data.evolution_market_id,
            ...group.market_ids.filter((id) => id !== data.evolution_market_id),
          ];
        }
        opts.push({ key, label, marketId: primary, marketIds });
      }
    }
    return opts;
  }, [data]);

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
  const isCompleted = tournament.schedule_status === "completed" ||
    (tournament.end_date && new Date() > new Date(new Date(tournament.end_date).getTime() + 86_400_000));
  let statusLabel = "";
  let statusBg = "";
  if (isCompleted) {
    statusLabel = "Completed";
    statusBg = "bg-gray-100 text-gray-500 border-gray-200";
  } else if (isLive) {
    statusLabel = currentRound ? `Round ${currentRound}` : "In Progress";
  } else if (tournament.start_date && tournament.end_date) {
    const start = new Date(tournament.start_date);
    const days = Math.ceil((start.getTime() - Date.now()) / 86400000);
    statusLabel =
      days <= 7
        ? `Starts ${start.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" })}`
        : "Upcoming";
    statusBg = "bg-blue-50 text-blue-700 border-blue-200";
  }

  // Use leaderboard data for both live AND completed tournaments (final scores)
  const useLeaderboard = (isLive || isCompleted) && leaderboard && leaderboard.players.length > 0;
  const mergedGolfers = buildMergedGolfers(golfers, useLeaderboard ? leaderboard : null);

  const winnerGroup = markets.find((g) => g.type === "winner");
  // #955: prefer the backend's corrected winner field (evolution_market_id, which
  // excludes the nationality/binary prop markets) as the primary chart series.
  const evolutionMarketIds = evolution_market_id
    ? [evolution_market_id, ...(winnerGroup?.market_ids || []).filter((id) => id !== evolution_market_id)]
    : (winnerGroup?.market_ids || []);

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
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
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
                      {new Date(tournament.start_date).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })}
                      {"\u2013"}
                      {new Date(tournament.end_date).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                        timeZone: "UTC",
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
        {positionOptions.length > 0 && (
          <section>
            <EvolutionView
              marketId={positionOptions[positionOptions.length - 1].marketId}
              marketName={tournament.name}
              defaultTopN={8}
              hours={168}
              positionOptions={positionOptions.length > 1 ? positionOptions : undefined}
              tournamentStart={tournament.start_date}
              tournamentEnd={tournament.end_date}
            />
          </section>
        )}
        {positionOptions.length === 0 && evolutionMarketIds.length > 0 && (
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

        {/* Related Futures — tournament-specific markets not in the grid */}
        {data.related_futures && data.related_futures.length > 0 && (
          <TournamentRelatedFutures markets={data.related_futures} accentColor={accentColor} />
        )}

        {/* Footer — #957: scope the DataGolf claim to the leaderboard; the
            "More Markets" cards carry their own per-source attribution. */}
        <p className="text-center text-[11px] text-gray-400">
          {isLive
            ? "Leaderboard probabilities from DataGolf in-play model; market cards labeled by source."
            : "Leaderboard probabilities from sportsbook consensus; market cards labeled by source."}
          {isLive && " Auto-refreshes every 60s."}
          {isLive && lastRefresh && <> Last: {lastRefresh.toLocaleTimeString()}</>}
        </p>
      </div>
    </main>
  );
}

// ============================================================================
// Tournament Related Futures
// ============================================================================

interface RelatedFutureMarket {
  market_id: number;
  market_name: string;
  source?: string;
  sources?: { source: string; market_id: number; probability: number | null }[];
  outcomes: {
    name: string;
    probability: number | null;
    american_odds: number | null;
    probability_change_24h: number | null;
  }[];
}

// #957: per-card source attribution — the footer's blanket "DataGolf in-play
// model" was wrong for these cards (playoff = Polymarket/Kalshi, etc.).
const SOURCE_LABELS: Record<string, string> = {
  datagolf: "DataGolf",
  polymarket: "Polymarket",
  kalshi: "Kalshi",
  odds_api: "Sportsbooks",
};
function sourceLabel(src: string | undefined): string {
  if (!src) return "";
  return SOURCE_LABELS[src] || src.charAt(0).toUpperCase() + src.slice(1);
}

function TournamentRelatedFutures({
  markets,
  accentColor,
}: {
  markets: RelatedFutureMarket[];
  accentColor: string;
}) {
  if (!markets.length) return null;

  return (
    <section>
      <h2 className="text-sm font-semibold text-gray-900 mb-3">More Markets</h2>
      <div className="space-y-3">
        {markets.map((market) => (
          <div
            key={market.market_id}
            className="border border-gray-200 rounded-xl p-4 bg-white"
          >
            <div className="flex items-start justify-between gap-2 mb-3">
              <h3 className="text-xs font-semibold text-gray-700">
                {market.market_name}
              </h3>
              {market.source && (
                <span className="text-[10px] text-gray-400 shrink-0">
                  {sourceLabel(market.source)}
                </span>
              )}
            </div>
            {/* #956/#957: cross-source comparison when the same question trades on
                multiple venues (e.g. "Polymarket 27% · Kalshi 22%"). */}
            {market.sources && market.sources.length > 1 && (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 mb-2 text-[11px] text-gray-500">
                {market.sources.map((s) => (
                  <span key={`${s.source}-${s.market_id}`}>
                    {sourceLabel(s.source)}{" "}
                    <span className="font-semibold text-gray-700">
                      {s.probability != null ? `${(s.probability * 100).toFixed(0)}%` : "—"}
                    </span>
                  </span>
                ))}
              </div>
            )}
            <div className="space-y-1.5">
              {market.outcomes.slice(0, 10).map((outcome, i) => (
                <div
                  key={`${outcome.name}-${i}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-gray-50"
                >
                  <span className="text-sm text-gray-800 truncate mr-3">
                    {outcome.name}
                  </span>
                  <div className="flex items-center gap-3 shrink-0">
                    {outcome.probability_change_24h != null &&
                      Math.abs(outcome.probability_change_24h) >= 0.005 && (
                        <span
                          className={`text-[11px] font-medium ${
                            outcome.probability_change_24h > 0
                              ? "text-green-600"
                              : "text-red-500"
                          }`}
                        >
                          {outcome.probability_change_24h > 0 ? "+" : ""}
                          {(outcome.probability_change_24h * 100).toFixed(1)}
                        </span>
                      )}
                    <span
                      className="text-sm font-semibold min-w-[48px] text-right"
                      style={{ color: accentColor }}
                    >
                      {outcome.probability != null
                        ? `${(outcome.probability * 100).toFixed(0)}%`
                        : "—"}
                    </span>
                  </div>
                </div>
              ))}
              {market.outcomes.length > 10 && (
                <p className="text-[11px] text-gray-400 text-center pt-1">
                  +{market.outcomes.length - 10} more
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}


// ============================================================================
// Leaderboard Grid
// ============================================================================

// Grid template columns for desktop — always show all columns (including Make Cut)
const GRID_COLS = "grid-cols-[40px_1fr_64px_56px_48px_88px_72px_72px_72px_72px]";

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
      {/* ── Desktop grid ── */}
      <div className="hidden sm:block border border-gray-200 rounded-xl overflow-hidden bg-white">
        {/* Header row */}
        <div className={`grid ${GRID_COLS} gap-1 text-[10px] text-gray-500 uppercase tracking-wider font-semibold px-3 py-2.5 border-b border-gray-200`}>
          <div>Pos</div>
          <div>Golfer</div>
          <div className="text-center">Score</div>
          <div className="text-center">Today</div>
          <div className="text-center">Thru</div>
          <div className="text-center" style={{ color: accentColor }}>Win</div>
          <div className="text-center">Top 5</div>
          <div className="text-center">Top 10</div>
          <div className="text-center">Top 20</div>
          <div className="text-center">Cut</div>
        </div>

        {/* Golfer rows */}
        <div className="space-y-0.5 p-1">
          {displayGolfers.map((golfer, i) => (
            <DesktopRow
              key={`${golfer.name}-${i}`}
              golfer={golfer}
              isLeader={i === 0}
              accentColor={accentColor}
              hasSnapshot={hasSnapshot}
            />
          ))}
        </div>

        {/* Show more / show less */}
        {golfers.length > INITIAL_SHOW && (
          <div className="py-3 text-center border-t border-gray-100">
            <button
              onClick={() => setShowAll((s) => !s)}
              className="text-xs font-medium hover:underline"
              style={{ color: accentColor }}
            >
              {showAll
                ? "Show top 30"
                : `\u00B7 \u00B7 \u00B7 ${golfers.length - INITIAL_SHOW} more golfers \u00B7 \u00B7 \u00B7`}
            </button>
          </div>
        )}

        {/* Source agreement legend */}
        {isLive && (
          <div className="flex gap-5 px-4 py-3 border-t border-gray-100 text-[10px] text-gray-500">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500" />
              Sources agree (&plusmn;2pp)
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              Moderate disagreement (2-5pp)
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500" />
              Large disagreement (&gt;5pp)
            </div>
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
  hasSnapshot,
}: {
  golfer: MergedGolfer;
  isLeader: boolean;
  accentColor: string;
  hasSnapshot: boolean;
}) {
  const scoreColor =
    golfer.totalScoreRaw != null && golfer.totalScoreRaw < 0
      ? "text-green-600"
      : golfer.score === "\u2014" ? "text-gray-300" : "";

  const todayColor =
    golfer.todayRaw != null && golfer.todayRaw < 0
      ? "text-green-600"
      : golfer.todayRaw != null && golfer.todayRaw > 0
        ? "text-red-500"
        : "text-gray-300";

  // Win prob change indicator (live snapshot or 24h movement for pre-tournament)
  const wpc = golfer.winProbChange;
  const mv = golfer.movement24h;
  let changeDisplay = "";
  let changeColor = "";
  if (hasSnapshot && wpc != null && Math.abs(wpc) >= 0.1) {
    changeDisplay = wpc > 0 ? `\u2191${wpc.toFixed(1)}` : `\u2193${Math.abs(wpc).toFixed(1)}`;
    changeColor = wpc > 0 ? "text-green-600" : "text-red-500";
  } else if (mv != null && Math.abs(mv) >= 0.005) {
    const delta = Math.abs(Math.round(mv * 100));
    changeDisplay = mv > 0 ? `\u2191${delta}` : `\u2193${delta}`;
    changeColor = mv > 0 ? "text-green-600" : "text-red-500";
  }

  return (
    <div
      className={`grid ${GRID_COLS} gap-1 items-center rounded-lg px-3 py-3 ${
        isLeader ? "border" : "hover:bg-gray-50"
      }`}
      style={
        isLeader
          ? { backgroundColor: `${accentColor}08`, borderColor: `${accentColor}25` }
          : undefined
      }
    >
      {/* Position */}
      <div
        className="text-sm font-bold tabular-nums"
        style={{ color: isLeader ? accentColor : "#9ca3af" }}
      >
        {golfer.position}
      </div>

      {/* Name */}
      <div>
        <div className="text-sm font-semibold text-gray-900">{golfer.name}</div>
      </div>

      {/* Score */}
      <div className={`text-center font-mono text-sm font-bold tabular-nums ${scoreColor}`}>
        {golfer.score}
      </div>

      {/* Today */}
      <div className={`text-center font-mono text-xs tabular-nums ${todayColor}`}>
        {golfer.today}
      </div>

      {/* Thru */}
      <div className="text-center font-mono text-xs tabular-nums text-gray-300">
        {golfer.thru || "\u2014"}
      </div>

      {/* Win probability */}
      <div className="text-center">
        <span
          className="text-sm font-bold tabular-nums"
          style={isLeader ? { color: accentColor } : undefined}
        >
          {golfer.winProb.toFixed(1)}%
        </span>
        {changeDisplay && (
          <span className={`text-[9px] ml-1 ${changeColor}`}>{changeDisplay}</span>
        )}
      </div>

      {/* Top 5 */}
      <div className="text-center font-mono text-xs tabular-nums text-gray-500">
        {golfer.top5Prob != null ? `${Math.round(golfer.top5Prob)}%` : "\u2014"}
      </div>

      {/* Top 10 */}
      <div className="text-center font-mono text-xs tabular-nums text-gray-500">
        {golfer.top10Prob != null ? `${Math.round(golfer.top10Prob)}%` : "\u2014"}
      </div>

      {/* Top 20 */}
      <div className="text-center font-mono text-xs tabular-nums text-gray-500">
        {golfer.top20Prob != null ? `${Math.round(golfer.top20Prob)}%` : "\u2014"}
      </div>

      {/* Make Cut */}
      <div className="text-center font-mono text-xs tabular-nums text-gray-500">
        {golfer.makeCutProb != null ? `${Math.round(golfer.makeCutProb)}%` : "\u2014"}
      </div>
    </div>
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
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
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
