"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchGolfTournament, fetchGolfLeaderboard, fetchSportHierarchyDetail, fetchFuturesHistory } from "@/lib/api";
import type {
  GolfTournamentDetailResponse,
  GolfGolfer,
  GolfLeaderboardPlayer,
  GolfMarketGroup,
  SportHierarchy,
  SportLeague,
} from "@/lib/types";
import { EvolutionView } from "@/components/EvolutionView";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

type MergedLeaderboardPlayer = GolfLeaderboardPlayer & { _golfer?: GolfGolfer };

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
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketId, hours]);

  if (hasData === null) {
    return <div className="h-64 bg-gray-900 rounded-xl border border-gray-800 animate-pulse" />;
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
// Leaderboard row
// ============================================================================

function LeaderboardRow({
  player,
  golfer,
  isEven,
}: {
  player: GolfLeaderboardPlayer;
  golfer?: GolfGolfer;
  isEven: boolean;
}) {
  // Prefer golfer odds data, fallback to leaderboard win_prob
  const prob = golfer?.probability ?? (player.win_prob > 0 ? player.win_prob / 100 : null);
  return (
    <div
      className={`grid grid-cols-[2.5rem_1fr_3rem_3rem_3rem_4rem] sm:grid-cols-[2.5rem_1fr_3.5rem_3.5rem_3.5rem_5rem] items-center px-3 py-2 text-sm ${
        isEven ? "bg-gray-900/30" : ""
      }`}
    >
      <span className="text-gray-400 font-mono text-xs">{player.position || "-"}</span>
      <span className="text-white truncate">{player.name}</span>
      <span className="text-gray-300 text-right font-mono text-xs">{player.score || "-"}</span>
      <span className="text-gray-400 text-right font-mono text-xs">{player.today || "-"}</span>
      <span className="text-gray-500 text-right font-mono text-xs">{player.thru || player.hole || "-"}</span>
      <span className="text-right font-mono text-xs">
        {prob != null ? (
          <span className={prob > 0.1 ? "text-emerald-400" : "text-gray-400"}>
            {(prob * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-gray-600">-</span>
        )}
      </span>
    </div>
  );
}

// ============================================================================
// Main Page
// ============================================================================

export default function SportEventDetailPage() {
  const params = useParams();
  const sportSlug = params.sport as string;
  const leagueSlug = params.league as string;
  const slug = params.slug as string;

  const [hierarchy, setHierarchy] = useState<SportHierarchy | null>(null);
  const [league, setLeague] = useState<SportLeague | null>(null);
  const [tournament, setTournament] = useState<GolfTournamentDetailResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<GolfLeaderboardPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Analytics
  usePageTracking({ pageType: "sport_event", pageTitle: `${slug} - BainLuck` });
  useScrollDepth({ pageType: "sport_event" });
  useEngagementTime({ pageType: "sport_event" });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [hierResult, tournResult, lbResult] = await Promise.allSettled([
        fetchSportHierarchyDetail(sportSlug),
        fetchGolfTournament(slug),
        fetchGolfLeaderboard(leagueSlug === "dpworld" ? "euro" : leagueSlug),
      ]);

      if (hierResult.status === "fulfilled") {
        setHierarchy(hierResult.value);
        setLeague(hierResult.value.leagues.find((l) => l.slug === leagueSlug) || null);
      }
      if (tournResult.status === "fulfilled") {
        setTournament(tournResult.value);
      } else {
        setError("Tournament not found");
      }
      if (lbResult.status === "fulfilled") {
        setLeaderboard(lbResult.value.players || []);
      }
    } catch {
      setError("Failed to load tournament");
    } finally {
      setLoading(false);
    }
  }, [sportSlug, leagueSlug, slug]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh for live tournaments
  useEffect(() => {
    if (!tournament) return;
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [tournament, load]);

  // Merge leaderboard with odds data
  const mergedLeaderboard: MergedLeaderboardPlayer[] = useMemo(() => {
    if (!leaderboard.length || !tournament?.golfers) return leaderboard;
    const golferMap = new Map<string, GolfGolfer>();
    for (const g of tournament.golfers) {
      golferMap.set(g.name.toLowerCase(), g);
    }
    return leaderboard.map((p) => ({
      ...p,
      _golfer: golferMap.get(p.name.toLowerCase()),
    }));
  }, [leaderboard, tournament]);

  // Market IDs for evolution chart
  const allMarketIds = useMemo(() => {
    if (!tournament?.markets) return [];
    // Winner markets first, then others
    const markets: GolfMarketGroup[] = tournament.markets;
    const winner = markets.find((m) => m.type === "winner");
    const others = markets.filter((m) => m.type !== "winner");
    const ids: number[] = [];
    if (winner) ids.push(...winner.market_ids);
    for (const m of others) ids.push(...m.market_ids);
    return ids;
  }, [tournament]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  if (error || !tournament) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 mb-4">{error || "Tournament not found"}</p>
          <Link
            href={`/sport/${sportSlug}/${leagueSlug}`}
            className="text-blue-400 hover:text-blue-300"
          >
            Back to {league?.name || leagueSlug}
          </Link>
        </div>
      </div>
    );
  }

  const t = tournament.tournament;
  const isLive = t.start_date && t.end_date &&
    new Date() >= new Date(t.start_date) &&
    new Date() <= new Date(new Date(t.end_date).getTime() + 24 * 3600_000);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-b from-gray-900 to-gray-950 border-b border-gray-800">
        <div className="max-w-5xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <span>/</span>
            <Link href={`/sport/${sportSlug}`} className="hover:text-white transition-colors">
              {hierarchy?.name || sportSlug}
            </Link>
            <span>/</span>
            <Link
              href={`/sport/${sportSlug}/${leagueSlug}`}
              className="hover:text-white transition-colors"
            >
              {league?.name || leagueSlug}
            </Link>
            <span>/</span>
            <span className="text-white truncate">{t.name}</span>
          </div>

          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">{t.name}</h1>
            {isLive && (
              <span className="bg-red-500/20 text-red-400 text-xs font-semibold px-2 py-1 rounded-full">
                LIVE
              </span>
            )}
          </div>

          {(t.venue || t.location) && (
            <p className="text-gray-400 mt-2">
              {t.venue}{t.venue && t.location ? " · " : ""}{t.location}
            </p>
          )}
          {t.start_date && t.end_date && (
            <p className="text-gray-500 text-sm mt-1">
              {new Date(t.start_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              {" - "}
              {new Date(t.end_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            </p>
          )}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-10">

        {/* Evolution Chart */}
        {allMarketIds.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-4">Odds Movement</h2>
            <EvolutionViewWithFallback
              marketIds={allMarketIds}
              marketName={t.name}
              defaultTopN={10}
              hours={168}
            />
          </section>
        )}

        {/* Live Leaderboard */}
        {mergedLeaderboard.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-4">Leaderboard</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              {/* Header */}
              <div className="grid grid-cols-[2.5rem_1fr_3rem_3rem_3rem_4rem] sm:grid-cols-[2.5rem_1fr_3.5rem_3.5rem_3.5rem_5rem] items-center px-3 py-2 text-xs text-gray-500 border-b border-gray-800 bg-gray-900/50">
                <span>Pos</span>
                <span>Player</span>
                <span className="text-right">Total</span>
                <span className="text-right">Today</span>
                <span className="text-right">Thru</span>
                <span className="text-right">Win %</span>
              </div>
              {mergedLeaderboard.slice(0, 30).map((p: MergedLeaderboardPlayer, i: number) => (
                <LeaderboardRow
                  key={p.name}
                  player={p}
                  golfer={p._golfer}
                  isEven={i % 2 === 0}
                />
              ))}
            </div>
          </section>
        )}

        {/* Top Golfers by Odds (if no leaderboard) */}
        {mergedLeaderboard.length === 0 && tournament.golfers && tournament.golfers.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-4">Odds to Win</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="grid grid-cols-[2.5rem_1fr_5rem_5rem] items-center px-3 py-2 text-xs text-gray-500 border-b border-gray-800">
                <span>#</span>
                <span>Player</span>
                <span className="text-right">Win %</span>
                <span className="text-right">24h</span>
              </div>
              {tournament.golfers.slice(0, 30).map((g: GolfGolfer, i: number) => (
                <div
                  key={g.name}
                  className={`grid grid-cols-[2.5rem_1fr_5rem_5rem] items-center px-3 py-2 text-sm ${
                    i % 2 === 0 ? "bg-gray-900/30" : ""
                  }`}
                >
                  <span className="text-gray-400 font-mono text-xs">{g.rank}</span>
                  <span className="text-white truncate">{g.name}</span>
                  <span className="text-right font-mono text-xs text-emerald-400">
                    {(g.probability * 100).toFixed(1)}%
                  </span>
                  <span className={`text-right font-mono text-xs ${
                    g.movement_24h && g.movement_24h > 0 ? "text-green-400" :
                    g.movement_24h && g.movement_24h < 0 ? "text-red-400" : "text-gray-500"
                  }`}>
                    {g.movement_24h != null
                      ? `${g.movement_24h > 0 ? "+" : ""}${(g.movement_24h * 100).toFixed(1)}%`
                      : "-"}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Market Groups */}
        {tournament.markets && tournament.markets.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-4">Markets</h2>
            <div className="flex flex-wrap gap-2">
              {tournament.markets.map((m: GolfMarketGroup) => (
                <span
                  key={m.type}
                  className="bg-gray-800 text-gray-300 text-sm px-3 py-1.5 rounded-full"
                >
                  {m.label} ({m.market_ids.length} source{m.market_ids.length !== 1 ? "s" : ""})
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Sources */}
        {tournament.golfers && tournament.golfers.length > 0 && (
          <div className="text-xs text-gray-600 pt-4 border-t border-gray-800">
            Sources:{" "}
            {[...new Set(tournament.golfers.flatMap((g) => Object.keys(g.sources)))].join(", ") || "Various sportsbooks"}
          </div>
        )}
      </div>
    </div>
  );
}
