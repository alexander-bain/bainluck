"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchGolfTournament, fetchFuturesHistory } from "@/lib/api";
import type {
  GolfTournamentDetailResponse,
  GolfGolfer,
  GolfMover,
  GolfMarketGroup,
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
    return () => { cancelled = true; };
  }, [marketId, hours]);

  if (hasData === null) {
    return (
      <div className="h-64 bg-surface-card rounded-xl border border-surface-border animate-pulse" />
    );
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
// Main page component
// ============================================================================

export default function GolfTournamentPage() {
  const params = useParams();
  const slug = params?.slug as string;

  usePageTracking({ pageType: "golf_tournament", pageTitle: `Golf Tournament: ${slug}` });
  useScrollDepth({ pageType: "golf_tournament" });
  useEngagementTime({ pageType: "golf_tournament" });

  const [data, setData] = useState<GolfTournamentDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    (async () => {
      try {
        const result = await fetchGolfTournament(slug);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load tournament");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorState message={error} />;
  if (!data) return <ErrorState message="Tournament not found" />;

  const { tournament, golfers, markets, evolution_market_id, biggest_movers } = data;
  const emoji = TOURNAMENT_EMOJI[tournament.key || ""] || "\u26F3";

  // Determine status badge
  let statusLabel = "";
  let statusColor = "";
  if (tournament.start_date && tournament.end_date) {
    const start = new Date(tournament.start_date);
    const end = new Date(tournament.end_date);
    const now = new Date();
    if (now >= start && now <= end) {
      statusLabel = "In Progress";
      statusColor = "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
    } else if (now > end) {
      statusLabel = "Completed";
      statusColor = "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
    } else {
      const days = Math.ceil((start.getTime() - now.getTime()) / 86400000);
      statusLabel = days <= 7 ? `Starts ${start.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}` : "Coming Up";
      statusColor = "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400";
    }
  } else if (tournament.schedule_status) {
    statusLabel = tournament.schedule_status;
    statusColor = "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  }

  // Collect all winner market IDs for evolution chart
  const winnerGroup = markets.find((g) => g.type === "winner");
  const evolutionMarketIds = winnerGroup?.market_ids || (evolution_market_id ? [evolution_market_id] : []);

  return (
    <main className="min-h-screen bg-surface-primary">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Breadcrumb */}
        <nav className="text-xs text-text-muted">
          <Link href="/categories/golf" className="hover:text-text-primary hover:underline">
            Golf
          </Link>
          <span className="mx-1.5">/</span>
          <span className="text-text-primary">{tournament.name}</span>
        </nav>

        {/* Tournament Header */}
        <header className="space-y-2">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-2xl">{emoji}</span>
            <h1 className="text-2xl font-bold text-text-primary">{tournament.name}</h1>
            {statusLabel && (
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusColor}`}>
                {statusLabel}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm text-text-muted flex-wrap">
            {tournament.venue && <span>{tournament.venue}</span>}
            {tournament.location && <span>{tournament.location}</span>}
            {tournament.start_date && tournament.end_date && (
              <span>
                {new Date(tournament.start_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                {" \u2013 "}
                {new Date(tournament.end_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
              </span>
            )}
          </div>
        </header>

        {/* Evolution Chart */}
        {evolutionMarketIds.length > 0 && (
          <section className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Odds Trend
            </h2>
            <EvolutionViewWithFallback
              marketIds={evolutionMarketIds}
              marketName={`${tournament.name} - Winner`}
              defaultTopN={8}
              hours={168}
            />
          </section>
        )}

        {/* Biggest Movers */}
        {biggest_movers.length > 0 && <MoversStrip movers={biggest_movers} />}

        {/* Market Sections */}
        {markets.map((group) => (
          <MarketGroupSection
            key={group.type}
            group={group}
            golfers={golfers}
            tournamentKey={tournament.key || slug}
          />
        ))}
      </div>
    </main>
  );
}

// ============================================================================
// Market Group Section
// ============================================================================

function MarketGroupSection({
  group,
  golfers,
  tournamentKey,
}: {
  group: GolfMarketGroup;
  golfers: GolfGolfer[];
  tournamentKey: string;
}) {
  const [expanded, setExpanded] = useState(group.type === "winner");
  const MAX_COLLAPSED = 10;

  return (
    <section className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-surface-elevated/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-text-primary">{group.label}</h2>
          <span className="text-xs text-text-muted">
            {group.market_ids.length} market{group.market_ids.length !== 1 ? "s" : ""}
          </span>
        </div>
        <span className="text-text-muted text-xs">{expanded ? "\u25B2" : "\u25BC"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-1.5 border-t border-surface-border pt-3">
          {golfers.slice(0, MAX_COLLAPSED).map((golfer) => (
            <GolferRow key={golfer.name} golfer={golfer} tournamentKey={tournamentKey} showSourceBreakdown />
          ))}
          {golfers.length > MAX_COLLAPSED && (
            <p className="text-xs text-text-muted mt-2">
              +{golfers.length - MAX_COLLAPSED} more golfers
            </p>
          )}
          {group.market_names && group.market_names.length > 0 && (
            <div className="mt-3 pt-2 border-t border-surface-border">
              <p className="text-[11px] text-text-muted">
                Markets: {group.market_names.join(" \u00B7 ")}
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ============================================================================
// Golfer Row (duplicated from golf page for self-containment)
// ============================================================================

function GolferRow({
  golfer,
  tournamentKey,
  showSourceBreakdown,
}: {
  golfer: GolfGolfer;
  tournamentKey: string;
  showSourceBreakdown?: boolean;
}) {
  const pct = Math.round(golfer.probability * 100);
  const barWidth = Math.max(pct, 2);

  return (
    <div className="flex items-center gap-2 group">
      {/* Rank */}
      <span className="text-[11px] text-text-muted w-5 text-right shrink-0">
        {golfer.rank ?? ""}
      </span>

      {/* Name */}
      <span className="text-sm text-text-primary truncate flex-1 min-w-0">
        {golfer.name}
      </span>

      {/* Movement badge */}
      {golfer.movement_24h !== null && golfer.movement_24h !== undefined && Math.abs(golfer.movement_24h) >= 0.005 && (
        <MovementBadge movement={golfer.movement_24h} />
      )}

      {/* Probability bar */}
      <div className="w-20 sm:w-28 h-4 bg-surface-elevated rounded-full overflow-hidden shrink-0 relative">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${barWidth}%`,
            backgroundColor: "#006747",
            opacity: 0.6 + (pct / 100) * 0.4,
          }}
        />
        <span className="absolute inset-0 flex items-center justify-center text-[10px] font-medium text-text-primary">
          {pct}%
        </span>
      </div>

      {/* Source breakdown */}
      {showSourceBreakdown && golfer.sources && Object.keys(golfer.sources).length > 0 && (
        <div className="hidden sm:flex gap-0.5 items-center shrink-0">
          {Object.entries(golfer.sources).map(([source, prob]) => (
            <span
              key={source}
              title={`${source}: ${Math.round((prob as number) * 100)}%`}
              className="w-1.5 h-1.5 rounded-full inline-block"
              style={{ backgroundColor: SOURCE_COLORS[source] || "#6b7280" }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const SOURCE_COLORS: Record<string, string> = {
  draftkings: "#53b94d",
  fanduel: "#1493ff",
  bovada: "#cc0000",
  betmgm: "#c4a55e",
  betonlineag: "#2d2d2d",
  pointsbetus: "#00a4e4",
  betrivers: "#1a3c6e",
  unibet_us: "#147b45",
  superbook: "#ef4444",
  kalshi: "#22c55e",
  polymarket: "#3b82f6",
  williamhill_us: "#00385e",
  betus: "#d4a843",
  mybookieag: "#1e3a5f",
  lowvig: "#6366f1",
  espnbet: "#cc0000",
  fliff: "#f59e0b",
};

// ============================================================================
// Movement Badge
// ============================================================================

function MovementBadge({ movement }: { movement: number }) {
  const isUp = movement > 0;
  const delta = Math.abs(Math.round(movement * 100));
  if (delta === 0) return null;

  return (
    <span
      className={`text-[10px] font-medium px-1 py-0.5 rounded shrink-0 ${
        isUp
          ? "text-green-700 bg-green-50 dark:text-green-400 dark:bg-green-900/30"
          : "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/30"
      }`}
    >
      {isUp ? "\u25B2" : "\u25BC"}
      {delta}%
    </span>
  );
}

// ============================================================================
// Movers Strip
// ============================================================================

function MoversStrip({ movers }: { movers: GolfMover[] }) {
  return (
    <section>
      <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
        Biggest Movers (24h)
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0">
        {movers.map((mover, i) => {
          const isUp = mover.movement_24h > 0;
          const delta = Math.abs(Math.round(mover.movement_24h * 100));
          const pct = Math.round(mover.probability * 100);
          return (
            <div
              key={`${mover.name}-${i}`}
              className={`flex-shrink-0 w-36 rounded-lg border p-3 ${
                isUp
                  ? "border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-900/20"
                  : "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/20"
              }`}
            >
              <p className="text-xs font-medium text-text-primary truncate">{mover.name}</p>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-lg font-bold text-text-primary">{pct}%</span>
                <span
                  className={`text-xs font-medium ${
                    isUp ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                  }`}
                >
                  {isUp ? "+" : "-"}{delta}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ============================================================================
// Loading & Error states
// ============================================================================

function LoadingSkeleton() {
  return (
    <main className="min-h-screen bg-surface-primary">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        <div className="h-4 w-24 bg-surface-elevated rounded animate-pulse" />
        <div className="space-y-2">
          <div className="h-8 w-64 bg-surface-elevated rounded animate-pulse" />
          <div className="h-4 w-48 bg-surface-elevated rounded animate-pulse" />
        </div>
        <div className="h-64 bg-surface-card rounded-xl border border-surface-border animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-surface-elevated rounded animate-pulse" />
          ))}
        </div>
      </div>
    </main>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <main className="min-h-screen bg-surface-primary flex items-center justify-center">
      <div className="text-center space-y-4">
        <p className="text-lg text-text-muted">{message}</p>
        <Link
          href="/categories/golf"
          className="inline-block text-sm text-[#006747] hover:underline"
        >
          &larr; Back to Golf
        </Link>
      </div>
    </main>
  );
}
