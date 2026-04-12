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
// Unified leaderboard + odds table
// ============================================================================
//
// Row source of truth:
//   live leaderboard → DataGolf in-play field (authoritative for "who is
//     competing" — if a player isn't here, they're not in the tournament)
//   fallback → tournament.golfers (DataGolf pre-tournament field)
//
// Odds are merged in from tournament.golfers by normalized name match.
// Score columns (Total/Today/Thru) only render when the leaderboard source
// is being used.
// ============================================================================

function formatProb(value: number | null | undefined, unit: "percent" | "fraction"): string {
  if (value == null) return "-";
  const pct = unit === "percent" ? value : value * 100;
  if (pct >= 10) return `${pct.toFixed(0)}%`;
  return `${pct.toFixed(1)}%`;
}

/** Normalize a golfer name for cross-source matching. */
function normalizeName(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[.,'"]/g, "")
    .replace(/\s+(jr|sr|ii|iii|iv)\b/g, "")
    .trim();
}

type UnifiedRow = {
  name: string;
  position?: string;
  total?: string;
  today?: string;
  thru?: string;
  win?: number | null;          // fraction 0..1
  top_5?: number | null;        // percent
  top_10?: number | null;
  top_20?: number | null;
  make_cut?: number | null;
  round_leader?: number | null;
  movement_24h?: number | null; // fraction delta
};

type OddsColumnKey = "win" | "top_5" | "top_10" | "top_20" | "make_cut" | "round_leader";

function UnifiedBoard({
  leaderboard,
  golfers,
}: {
  leaderboard: GolfLeaderboardPlayer[];
  golfers: GolfGolfer[];
}) {
  const hasLeaderboard = leaderboard.length > 0;

  // Build name -> odds index from tournament.golfers
  const oddsByName = useMemo(() => {
    const map = new Map<string, GolfGolfer>();
    for (const g of golfers) {
      map.set(normalizeName(g.name), g);
    }
    return map;
  }, [golfers]);

  const rows: UnifiedRow[] = useMemo(() => {
    if (hasLeaderboard) {
      // DataGolf in-play leaderboard is the source of truth for "who's playing"
      return leaderboard.map((p) => {
        const g = oddsByName.get(normalizeName(p.name));
        return {
          name: p.name,
          position: p.position || undefined,
          total: p.score || undefined,
          today: p.today || undefined,
          thru: p.thru || p.hole || undefined,
          win: g?.probability ?? (p.win_prob > 0 ? p.win_prob / 100 : null),
          top_5: g?.top_5_prob ?? p.top_5_prob ?? null,
          top_10: g?.top_10_prob ?? p.top_10_prob ?? null,
          top_20: g?.top_20_prob ?? p.top_20_prob ?? null,
          make_cut: g?.make_cut_prob ?? p.make_cut_prob ?? null,
          round_leader: g?.round_leader_prob ?? null,
          movement_24h: g?.movement_24h ?? null,
        };
      });
    }
    // Pre-tournament fallback: tournament.golfers (backend-filtered to field)
    return golfers.map((g) => ({
      name: g.name,
      win: g.probability,
      top_5: g.top_5_prob ?? null,
      top_10: g.top_10_prob ?? null,
      top_20: g.top_20_prob ?? null,
      make_cut: g.make_cut_prob ?? null,
      round_leader: g.round_leader_prob ?? null,
      movement_24h: g.movement_24h ?? null,
    }));
  }, [hasLeaderboard, leaderboard, golfers, oddsByName]);

  // Conditional odds columns — hide columns with no data anywhere
  const oddsColumns: { key: OddsColumnKey; label: string }[] = useMemo(() => {
    const all: { key: OddsColumnKey; label: string }[] = [
      { key: "win", label: "Win" },
      { key: "top_5", label: "Top 5" },
      { key: "top_10", label: "Top 10" },
      { key: "top_20", label: "Top 20" },
      { key: "make_cut", label: "Make Cut" },
      { key: "round_leader", label: "Rd Leader" },
    ];
    return all.filter((col) => {
      if (col.key === "win") return true;
      return rows.some((r) => r[col.key] != null);
    });
  }, [rows]);

  const showMovement = !hasLeaderboard && rows.some((r) => r.movement_24h != null);

  // Grid template: [Pos/#] Player [Total Today Thru]? ...odds [24h]?
  const posCol = hasLeaderboard ? "3rem " : "2.5rem ";
  const scoreCols = hasLeaderboard ? " 3.5rem 3.5rem 3.5rem" : "";
  const oddsCols = Array(oddsColumns.length).fill(" minmax(3.5rem,4.5rem)").join("");
  const movementCols = showMovement ? " 4rem" : "";
  const templateCols = `${posCol}minmax(8rem,1fr)${scoreCols}${oddsCols}${movementCols}`;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <div
          className="grid items-center px-3 py-2 text-xs text-text-muted border-b border-surface-border bg-surface-elevated"
          style={{ gridTemplateColumns: templateCols, minWidth: "min-content" }}
        >
          <span>{hasLeaderboard ? "Pos" : "#"}</span>
          <span>Player</span>
          {hasLeaderboard && (
            <>
              <span className="text-right">Total</span>
              <span className="text-right">Today</span>
              <span className="text-right">Thru</span>
            </>
          )}
          {oddsColumns.map((c) => (
            <span key={c.key} className="text-right">{c.label}</span>
          ))}
          {showMovement && <span className="text-right">24h</span>}
        </div>
        {rows.slice(0, 60).map((r, i) => (
          <div
            key={r.name}
            className={`grid items-center px-3 py-2 text-sm ${
              i % 2 === 0 ? "bg-surface-elevated/50" : ""
            }`}
            style={{ gridTemplateColumns: templateCols, minWidth: "min-content" }}
          >
            <span className="text-text-muted font-mono text-xs">
              {hasLeaderboard ? (r.position || "-") : (i + 1)}
            </span>
            <span className="text-text-primary truncate">{r.name}</span>
            {hasLeaderboard && (
              <>
                <span className="text-text-primary text-right font-mono text-xs">
                  {r.total || "-"}
                </span>
                <span className="text-text-secondary text-right font-mono text-xs">
                  {r.today || "-"}
                </span>
                <span className="text-text-muted text-right font-mono text-xs">
                  {r.thru || "-"}
                </span>
              </>
            )}
            {oddsColumns.map((c) => {
              const raw = r[c.key];
              if (c.key === "win") {
                return (
                  <span
                    key={c.key}
                    className={`text-right font-mono text-xs ${
                      raw != null && raw > 0.05 ? "text-emerald-600" : "text-text-primary"
                    }`}
                  >
                    {formatProb(raw, "fraction")}
                  </span>
                );
              }
              return (
                <span key={c.key} className="text-right font-mono text-xs text-text-secondary">
                  {formatProb(raw, "percent")}
                </span>
              );
            })}
            {showMovement && (
              <span
                className={`text-right font-mono text-xs ${
                  r.movement_24h && r.movement_24h > 0
                    ? "text-accent-live"
                    : r.movement_24h && r.movement_24h < 0
                      ? "text-accent-danger"
                      : "text-text-muted"
                }`}
              >
                {r.movement_24h != null
                  ? `${r.movement_24h > 0 ? "+" : ""}${(r.movement_24h * 100).toFixed(1)}%`
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

        {/* Unified leaderboard + odds — DataGolf in-play field is the source of
            truth for "who's competing"; odds are merged in by name match. */}
        {(leaderboard.length > 0 || (tournament.golfers && tournament.golfers.length > 0)) && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
              {leaderboard.length > 0 ? "Leaderboard & Odds" : "Odds"}
            </h2>
            <UnifiedBoard
              leaderboard={leaderboard}
              golfers={tournament.golfers || []}
            />
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
