"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchGolfTournament, fetchGolfLeaderboard, fetchSportHierarchyDetail, fetchFuturesHistory } from "@/lib/api";
import type {
  GolfTournamentDetailResponse,
  GolfGolfer,
  GolfH2HMatchup,
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
  tournamentStart,
  tournamentEnd,
}: {
  marketIds: number[];
  marketName: string;
  defaultTopN: number;
  hours: number;
  tournamentStart?: string | null;
  tournamentEnd?: string | null;
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
      tournamentStart={tournamentStart}
      tournamentEnd={tournamentEnd}
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
  tournamentStart,
  tournamentEnd,
  onEmpty,
}: {
  marketId: number;
  marketName: string;
  defaultTopN: number;
  hours: number;
  tournamentStart?: string | null;
  tournamentEnd?: string | null;
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
    return <div className="h-64 bg-surface-elevated rounded-xl border border-surface-border animate-pulse" />;
  }
  if (!hasData) return null;

  return (
    <EvolutionView
      marketId={marketId}
      marketName={marketName}
      defaultTopN={defaultTopN}
      hours={hours}
      tournamentStart={tournamentStart ?? null}
      tournamentEnd={tournamentEnd ?? null}
    />
  );
}

// ============================================================================
// Odds grid — multi-column (Win / Top 5 / Top 10 / Top 20 / Make Cut / Round Leader)
// ============================================================================

type OddsColumn = {
  key: "probability" | "top_5_prob" | "top_10_prob" | "top_20_prob" | "make_cut_prob" | "round_leader_prob" | "movement_24h";
  label: string;
};

function formatProb(value: number | null | undefined, isUnit: "percent" | "fraction"): string {
  if (value == null) return "-";
  const pct = isUnit === "percent" ? value : value * 100;
  if (pct >= 10) return `${pct.toFixed(0)}%`;
  if (pct >= 1) return `${pct.toFixed(1)}%`;
  return `${pct.toFixed(1)}%`;
}

function OddsGrid({ golfers }: { golfers: GolfGolfer[] }) {
  // Build dynamic column set — only include placement columns with any data
  const columns: OddsColumn[] = useMemo(() => {
    const all: OddsColumn[] = [
      { key: "probability", label: "Win" },
      { key: "top_5_prob", label: "Top 5" },
      { key: "top_10_prob", label: "Top 10" },
      { key: "top_20_prob", label: "Top 20" },
      { key: "make_cut_prob", label: "Make Cut" },
      { key: "round_leader_prob", label: "Rd Leader" },
    ];
    const kept = all.filter((col) => {
      if (col.key === "probability") return true;
      return golfers.some((g) => (g as unknown as Record<string, number | null | undefined>)[col.key] != null);
    });
    return kept;
  }, [golfers]);

  const showMovement = golfers.some((g) => g.movement_24h != null);

  // Column layout: # | Player | ...data columns | 24h?
  const dataColsCount = columns.length;
  const movementCols = showMovement ? 1 : 0;
  const templateCols = `2.5rem minmax(7rem,1fr) ${Array(dataColsCount).fill("minmax(3.5rem,4.5rem)").join(" ")}${movementCols ? " 4rem" : ""}`;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <div
          className="grid items-center px-3 py-2 text-xs text-text-muted border-b border-surface-border bg-surface-elevated"
          style={{ gridTemplateColumns: templateCols, minWidth: "min-content" }}
        >
          <span>#</span>
          <span>Player</span>
          {columns.map((c) => (
            <span key={c.key} className="text-right">{c.label}</span>
          ))}
          {showMovement && <span className="text-right">24h</span>}
        </div>
        {golfers.slice(0, 30).map((g: GolfGolfer, i: number) => (
          <div
            key={g.name}
            className={`grid items-center px-3 py-2 text-sm ${
              i % 2 === 0 ? "bg-surface-elevated/50" : ""
            }`}
            style={{ gridTemplateColumns: templateCols, minWidth: "min-content" }}
          >
            <span className="text-text-muted font-mono text-xs">{g.rank}</span>
            <span className="text-text-primary truncate">{g.name}</span>
            {columns.map((c) => {
              if (c.key === "probability") {
                return (
                  <span
                    key={c.key}
                    className={`text-right font-mono text-xs ${
                      g.probability > 0.05 ? "text-emerald-600" : "text-text-primary"
                    }`}
                  >
                    {formatProb(g.probability, "fraction")}
                  </span>
                );
              }
              const raw = (g as unknown as Record<string, number | null | undefined>)[c.key];
              return (
                <span key={c.key} className="text-right font-mono text-xs text-text-secondary">
                  {formatProb(raw, "percent")}
                </span>
              );
            })}
            {showMovement && (
              <span
                className={`text-right font-mono text-xs ${
                  g.movement_24h && g.movement_24h > 0
                    ? "text-accent-live"
                    : g.movement_24h && g.movement_24h < 0
                      ? "text-accent-danger"
                      : "text-text-muted"
                }`}
              >
                {g.movement_24h != null
                  ? `${g.movement_24h > 0 ? "+" : ""}${(g.movement_24h * 100).toFixed(1)}%`
                  : "-"}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Head-to-head matchups card
// ============================================================================

function H2HMatchupsCard({ matchups }: { matchups: GolfH2HMatchup[] }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div className="divide-y divide-surface-border">
        {matchups.map((m) => {
          const aPct = m.golfer_a.probability * 100;
          const bPct = m.golfer_b.probability * 100;
          return (
            <div
              key={m.market_id}
              className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 py-3"
            >
              {/* Left golfer */}
              <div className="flex flex-col min-w-0">
                <span className="text-sm text-text-primary truncate font-medium">
                  {m.golfer_a.name}
                </span>
                <span className="text-xs text-emerald-600 font-mono">
                  {aPct.toFixed(0)}%
                </span>
              </div>

              {/* Center bar */}
              <div className="w-24 sm:w-40">
                <div className="flex h-1.5 rounded-full overflow-hidden bg-surface-elevated">
                  <div
                    className="bg-emerald-600"
                    style={{ width: `${aPct}%` }}
                  />
                  <div
                    className="bg-gray-300"
                    style={{ width: `${bPct}%` }}
                  />
                </div>
                <div className="text-[10px] text-text-muted text-center mt-1 uppercase tracking-wide">
                  vs
                </div>
              </div>

              {/* Right golfer */}
              <div className="flex flex-col items-end min-w-0">
                <span className="text-sm text-text-primary truncate font-medium text-right">
                  {m.golfer_b.name}
                </span>
                <span className="text-xs text-text-secondary font-mono">
                  {bPct.toFixed(0)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
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
  const prob = golfer?.probability ?? (player.win_prob > 0 ? player.win_prob / 100 : null);
  return (
    <div
      className={`grid grid-cols-[2.5rem_1fr_3rem_3rem_3rem_4rem] sm:grid-cols-[2.5rem_1fr_3.5rem_3.5rem_3.5rem_5rem] items-center px-3 py-2 text-sm ${
        isEven ? "bg-surface-elevated/50" : ""
      }`}
    >
      <span className="text-text-muted font-mono text-xs">{player.position || "-"}</span>
      <span className="text-text-primary truncate">{player.name}</span>
      <span className="text-text-primary text-right font-mono text-xs">{player.score || "-"}</span>
      <span className="text-text-secondary text-right font-mono text-xs">{player.today || "-"}</span>
      <span className="text-text-muted text-right font-mono text-xs">{player.thru || player.hole || "-"}</span>
      <span className="text-right font-mono text-xs">
        {prob != null ? (
          <span className={prob > 0.1 ? "text-emerald-600" : "text-text-muted"}>
            {(prob * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-text-muted">-</span>
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

  useEffect(() => {
    if (!tournament) return;
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [tournament, load]);

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

  const allMarketIds = useMemo(() => {
    if (!tournament?.markets) return [];
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
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-text-muted">Loading...</div>
      </div>
    );
  }

  if (error || !tournament) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-text-muted mb-4">{error || "Tournament not found"}</p>
          <Link
            href={`/sport/${sportSlug}/${leagueSlug}`}
            className="text-accent-brand hover:underline"
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
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-surface-border">
        <div className="max-w-5xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-text-muted mb-4">
            <Link href="/" className="hover:text-text-primary transition-colors">Home</Link>
            <span>/</span>
            <Link href="/sport" className="hover:text-text-primary transition-colors">Sports</Link>
            <span>/</span>
            <Link href={`/sport/${sportSlug}`} className="hover:text-text-primary transition-colors">
              {hierarchy?.name || sportSlug}
            </Link>
            <span>/</span>
            <Link
              href={`/sport/${sportSlug}/${leagueSlug}`}
              className="hover:text-text-primary transition-colors"
            >
              {league?.name || leagueSlug}
            </Link>
            <span>/</span>
            <span className="text-text-primary truncate">{t.name}</span>
          </div>

          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold text-text-primary">{t.name}</h1>
            {isLive && (
              <span className="bg-accent-live/15 text-accent-live text-xs font-semibold px-2 py-1 rounded-full">
                LIVE
              </span>
            )}
          </div>

          {(t.venue || t.location) && (
            <p className="text-text-secondary mt-2">
              {t.venue}{t.venue && t.location ? " \u00b7 " : ""}{t.location}
            </p>
          )}
          {t.start_date && t.end_date && (
            <p className="text-text-muted text-sm mt-1">
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
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Odds Movement</h2>
            <EvolutionViewWithFallback
              marketIds={allMarketIds}
              marketName={t.name}
              defaultTopN={10}
              hours={168}
              tournamentStart={t.start_date}
              tournamentEnd={t.end_date}
            />
          </section>
        )}

        {/* Live Leaderboard */}
        {mergedLeaderboard.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Leaderboard</h2>
            <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
              <div className="grid grid-cols-[2.5rem_1fr_3rem_3rem_3rem_4rem] sm:grid-cols-[2.5rem_1fr_3.5rem_3.5rem_3.5rem_5rem] items-center px-3 py-2 text-xs text-text-muted border-b border-surface-border bg-surface-elevated">
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

        {/* Odds Grid — multi-column placement probabilities */}
        {tournament.golfers && tournament.golfers.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Odds</h2>
            <OddsGrid golfers={tournament.golfers} />
          </section>
        )}

        {/* Head-to-head matchups */}
        {tournament.h2h_matchups && tournament.h2h_matchups.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
              Head-to-head Matchups
            </h2>
            <H2HMatchupsCard matchups={tournament.h2h_matchups} />
          </section>
        )}

        {/* Sources */}
        {tournament.golfers && tournament.golfers.length > 0 && (
          <div className="text-xs text-text-muted pt-4 border-t border-surface-border">
            Sources:{" "}
            {[...new Set(tournament.golfers.flatMap((g) => Object.keys(g.sources)))].join(", ") || "Various sportsbooks"}
          </div>
        )}
      </div>
    </div>
  );
}
