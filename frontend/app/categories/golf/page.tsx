"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchGolfData, fetchFuturesHistory } from "@/lib/api";
import type {
  GolfResponse,
  GolfTournament,
  GolfGolfer,
  GolfCurrentEvent,
  GolfMover,
  FuturesOutcomeHistory,
  FuturesHistoryPoint,
} from "@/lib/types";
import {
  MAJOR_TOURNAMENTS,
  TOURNAMENT_VENUES,
  TOURNAMENT_EMOJI,
} from "@/lib/golfData";
import { FuturesChart } from "@/components/FuturesChart";
import { EvolutionView } from "@/components/EvolutionView";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// ============================================================================
// Evolution Chart with market fallback — tries market IDs in order until
// one has history data. Backend sorts Winner markets first.
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
  const [failedIds, setFailedIds] = useState<Set<number>>(new Set());

  // Reset when marketIds change
  useEffect(() => {
    setCurrentIndex(0);
    setFailedIds(new Set());
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
        // Try next market_id if this one has no data
        setFailedIds((prev) => new Set([...prev, marketId]));
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

  // Check if this market has history data before rendering EvolutionView
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
  }, [marketId, hours]);

  if (hasData === null) {
    return (
      <div className="animate-pulse">
        <div className="h-8 bg-gray-800 rounded w-48 mb-4" />
        <div className="h-[400px] bg-gray-800/50 rounded-lg" />
      </div>
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
// Main Page
// ============================================================================

export default function GolfPage() {
  usePageTracking({ pageType: "golf", pageTitle: "Golf Odds & Futures" });
  useScrollDepth({ pageType: "golf" });
  useEngagementTime({ pageType: "golf" });

  const [data, setData] = useState<GolfResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalTournament, setModalTournament] =
    useState<GolfTournament | null>(null);
  const [historyByTournament, setHistoryByTournament] = useState<
    Record<string, FuturesOutcomeHistory[]>
  >({});
  const [currentEventHistory, setCurrentEventHistory] = useState<
    FuturesOutcomeHistory[] | null
  >(null);

  // Phase 1: Fetch golf data
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await fetchGolfData();
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load golf data"
          );
          setLoading(false);
        }
      }
    }
    load();

    const interval = setInterval(() => {
      fetchGolfData()
        .then((r) => { if (!cancelled) setData(r); })
        .catch(() => {});
    }, 120_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Phase 2: Lazy-load chart history when modal opens
  useEffect(() => {
    if (!modalTournament) return;
    const key = modalTournament.key;
    if (historyByTournament[key]) return;
    const marketId = modalTournament.market_ids[0];
    if (!marketId) return;

    fetchFuturesHistory(marketId, 168)
      .then((h) => {
        if (h?.outcomes) {
          setHistoryByTournament((prev) => ({
            ...prev,
            [key]: h.outcomes,
          }));
        }
      })
      .catch(() => {});
  }, [modalTournament, historyByTournament]);

  // Phase 2b: Lazy-load history for current event sparkline
  useEffect(() => {
    if (!data?.current_event?.market_ids?.length) return;
    if (currentEventHistory) return;
    const marketId = data.current_event.market_ids[0];
    fetchFuturesHistory(marketId, 168)
      .then((h) => {
        if (h?.outcomes) setCurrentEventHistory(h.outcomes);
      })
      .catch(() => {});
  }, [data?.current_event, currentEventHistory]);

  // Derived data
  const majors = data?.tournaments.filter((t) => t.is_major) ?? [];
  const pgaTourEvents =
    data?.tournaments.filter((t) => !t.is_major && t.is_tour_event && !t.is_womens) ?? [];
  const lpgaTourEvents =
    data?.tournaments.filter((t) => !t.is_major && t.is_tour_event && t.is_womens) ?? [];
  const otherTournaments =
    data?.tournaments.filter((t) => !t.is_major && !t.is_tour_event) ?? [];

  // Next Major countdown
  const nextMajor = majors.find(
    (t) => t.commence_time && new Date(t.commence_time) > new Date()
  );

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <div className="relative overflow-hidden bg-gradient-to-b from-[#002e1f] via-surface-deep to-surface-deep">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(0,103,71,0.12)_0%,_transparent_70%)]" />
        <div className="relative max-w-4xl mx-auto px-4 pt-8 pb-6 text-center">
          <Link
            href="/"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors mb-4 inline-block"
          >
            &larr; Back to feed
          </Link>
          <div className="text-4xl mb-3">&#x26F3;</div>
          <h1 className="text-3xl sm:text-4xl font-bold text-[#FFF8E7] tracking-tight">
            Golf Odds &amp; Futures
          </h1>
          <p className="text-text-secondary mt-2 text-lg">
            Tournament odds from Polymarket, Kalshi, sportsbooks &amp; DataGolf
          </p>

          {nextMajor && nextMajor.commence_time && (
            <div className="mt-4">
              <p className="text-xs text-[#006747] font-medium uppercase tracking-wider mb-1">
                Next Major: {nextMajor.name}
                {TOURNAMENT_VENUES[nextMajor.key] && (
                  <span className="text-text-muted">
                    {" "}
                    &mdash; {TOURNAMENT_VENUES[nextMajor.key]}
                  </span>
                )}
              </p>
              <Countdown targetDate={nextMajor.commence_time} />
            </div>
          )}

          {data && (
            <p className="text-xs text-text-muted mt-4">
              {data.total_tournaments} tournaments &middot;{" "}
              {data.total_golfers} golfers tracked
            </p>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-10">
        {loading && (
          <div className="text-center py-16">
            <div className="animate-pulse space-y-6 max-w-md mx-auto">
              <div className="h-8 bg-surface-card rounded w-48 mx-auto" />
              <div className="h-24 bg-surface-card/50 rounded-xl" />
              <div className="h-64 bg-surface-card/30 rounded-xl" />
            </div>
          </div>
        )}

        {error && (
          <div className="text-center py-16 text-red-400">{error}</div>
        )}

        {data && !loading && data.tournaments.length === 0 && (
          <div className="text-center py-16">
            <p className="text-lg text-text-secondary">
              No golf futures available right now.
            </p>
            <p className="text-sm text-text-muted mt-1">
              Markets typically appear a few weeks before tournaments.
            </p>
          </div>
        )}

        {data && !loading && data.tournaments.length > 0 && (
          <>
            {/* Current Event Banner */}
            {data.current_event && (
              <CurrentEventBanner
                event={data.current_event}
                historyData={currentEventHistory}
              />
            )}

            {/* Evolution Chart for current tournament */}
            {data.current_event?.market_ids?.length > 0 && (
              <section>
                <EvolutionViewWithFallback
                  marketIds={data.current_event.market_ids}
                  marketName={`${data.current_event.name} — Win Probability`}
                  defaultTopN={8}
                  hours={168}
                />
              </section>
            )}

            {/* Biggest Movers Strip */}
            {data.biggest_movers.length > 0 && (
              <MoversStrip movers={data.biggest_movers} />
            )}

            {/* The Majors */}
            {majors.length > 0 && (
              <section>
                <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
                  <span className="text-[#006747]">&#x2B50;</span>
                  The Majors
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {majors.map((tournament) => (
                    <TournamentCard
                      key={tournament.key}
                      tournament={tournament}
                      onClick={() => setModalTournament(tournament)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Tour Events (PGA) */}
            {pgaTourEvents.length > 0 && (
              <section>
                <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
                  <span className="text-[#006747]">&#x1F3CC;&#xFE0F;</span>
                  Tour Events
                </h2>
                <div className="space-y-2">
                  {pgaTourEvents.map((tournament) => (
                    <ExpandableTournamentRow
                      key={tournament.key}
                      tournament={tournament}
                      onClickFull={() => setModalTournament(tournament)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* LPGA & Women's Events */}
            {lpgaTourEvents.length > 0 && (
              <section>
                <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
                  <span className="text-[#006747]">&#x1F3CC;&#xFE0F;&#x200D;&#x2640;&#xFE0F;</span>
                  LPGA &amp; Women&apos;s Events
                </h2>
                <div className="space-y-2">
                  {lpgaTourEvents.map((tournament) => (
                    <ExpandableTournamentRow
                      key={tournament.key}
                      tournament={tournament}
                      onClickFull={() => setModalTournament(tournament)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Other Markets */}
            {otherTournaments.length > 0 && (
              <section>
                <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
                  <span className="text-text-secondary">&#x26F3;</span>
                  Other Markets
                </h2>
                <div className="space-y-2">
                  {otherTournaments.map((tournament) => (
                    <ExpandableTournamentRow
                      key={tournament.key}
                      tournament={tournament}
                      onClickFull={() => setModalTournament(tournament)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Schedule */}
            {data.upcoming_events.length > 0 && (
              <section>
                <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
                  <span className="text-[#006747]">&#x1F4C5;</span>
                  Upcoming Events
                </h2>
                <div className="space-y-2">
                  {data.upcoming_events.map((event) => (
                    <div
                      key={event.id}
                      className="bg-surface-card rounded-lg border border-surface-border p-3 flex items-center justify-between"
                    >
                      <span className="text-sm text-text-primary">
                        {event.name}
                      </span>
                      {event.commence_time && (
                        <span className="text-xs text-text-muted">
                          {new Date(event.commence_time).toLocaleDateString(
                            "en-US",
                            { weekday: "short", month: "short", day: "numeric" }
                          )}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Source Legend */}
            <div className="flex items-center justify-center gap-4 text-xs text-text-muted pt-4 border-t border-surface-border flex-wrap">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
                Sportsbooks
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
                Kalshi
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-purple-500 inline-block" />
                Polymarket
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-500 inline-block ring-1 ring-amber-400/50" />
                DG Model
                <span className="text-amber-400/60 text-[9px]">(model)</span>
              </span>
            </div>
          </>
        )}
      </div>

      {/* Modal */}
      {modalTournament && (
        <TournamentModal
          tournament={modalTournament}
          historyData={historyByTournament[modalTournament.key]}
          onClose={() => setModalTournament(null)}
        />
      )}
    </div>
  );
}

// ============================================================================
// Current Event Banner
// ============================================================================

function CurrentEventBanner({
  event,
  historyData,
}: {
  event: GolfCurrentEvent;
  historyData: FuturesOutcomeHistory[] | null;
}) {
  const now = new Date();
  let statusLabel = "Coming Up";
  let dateLabel = "";

  // Detect active tournament from golfer movement (fallback when no schedule dates)
  const topGolfers = event.top_golfers ?? [];
  const hasActiveMovement = topGolfers.some(
    (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01
  );

  if (event.start_date && event.end_date) {
    const start = new Date(event.start_date);
    const end = new Date(event.end_date);
    if (now >= start && now <= end) {
      statusLabel = "This Week";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} \u2013 ${end.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
    } else if (now > end) {
      statusLabel = "Just Finished";
    } else {
      const daysUntil = Math.ceil(
        (start.getTime() - now.getTime()) / 86400000
      );
      statusLabel = daysUntil <= 7 ? "This Week" : "Coming Up";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} \u2013 ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
    }
  } else if (hasActiveMovement) {
    // No schedule dates but significant odds movement → tournament is in progress
    statusLabel = "In Progress";
    // Don't show resolution_date — it's market close, not tournament date
  } else if (event.resolution_date) {
    const resDate = new Date(event.resolution_date);
    const daysUntil = Math.ceil(
      (resDate.getTime() - now.getTime()) / 86400000
    );
    if (daysUntil < 0) {
      statusLabel = "Just Finished";
    } else if (daysUntil <= 7) {
      statusLabel = "This Week";
      dateLabel = `Ends ${resDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
    } else {
      dateLabel = resDate.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
    }
  }

  const leaderProb = topGolfers.length > 0 ? topGolfers[0].probability : 0;

  return (
    <div className="bg-gradient-to-r from-[#006747]/20 via-[#006747]/10 to-[#006747]/20 border border-[#006747]/30 rounded-xl p-5">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <p className="text-[#006747] text-xs font-semibold uppercase tracking-wider mb-1">
            {statusLabel}
          </p>
          <h2 className="text-xl font-bold text-text-primary">{event.name}</h2>
          <p className="text-text-muted text-sm mt-1">
            {event.venue && <span>{event.venue} &middot; </span>}
            {event.golfer_count} golfers with odds
            {dateLabel && <span> &middot; {dateLabel}</span>}
          </p>
        </div>
      </div>

      {/* Odds Trend Sparkline */}
      {historyData && historyData.length > 0 && (
        <TrendSparkline historyData={historyData} topGolfers={topGolfers} />
      )}

      {/* Mini-Leaderboard */}
      {topGolfers.length > 0 && (
        <div className="space-y-2">
          {topGolfers.map((golfer) => {
            const pct = Math.round(golfer.probability * 100);
            const barWidth = leaderProb > 0
              ? Math.max(Math.round((golfer.probability / leaderProb) * 100), 4)
              : pct;
            const isLeader = golfer.rank === 1;

            return (
              <div key={golfer.name}>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs font-mono w-5 text-right ${
                      isLeader ? "text-[#006747] font-bold" : "text-text-muted"
                    }`}
                  >
                    {golfer.rank}
                  </span>
                  <span
                    className={`text-sm flex-1 truncate ${
                      isLeader ? "text-text-primary font-medium" : "text-text-secondary"
                    }`}
                  >
                    {golfer.name}
                  </span>
                  <MovementBadge movement={golfer.movement_24h} />
                  <span className="text-sm font-mono text-text-primary w-10 text-right">
                    {pct}%
                  </span>
                </div>
                <div className="ml-7 mr-14 mt-0.5 mb-0.5">
                  <div className="h-1.5 bg-[#006747]/10 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${barWidth}%`,
                        background: isLeader
                          ? "linear-gradient(90deg, #006747, #2d8659)"
                          : "#2d8659",
                        opacity: isLeader ? 1 : 0.5,
                      }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Fallback if no top_golfers (shouldn't happen, but safe) */}
      {topGolfers.length === 0 && event.leader && event.leader_probability !== null && (
        <div className="text-right">
          <p className="text-xs text-text-muted uppercase tracking-wider">
            Favorite
          </p>
          <p className="text-lg font-semibold text-text-primary">
            {event.leader}
          </p>
          <p className="text-[#006747] font-mono text-sm">
            {Math.round(event.leader_probability * 100)}%
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Trend Sparkline (SVG chart for current event)
// ============================================================================

const SPARKLINE_COLORS = [
  "#006747", // leader — dark green
  "#2d8659", // 2nd
  "#4a9e6e", // 3rd
  "#6bb585", // 4th
  "#8ecc9d", // 5th
];

function TrendSparkline({
  historyData,
  topGolfers,
}: {
  historyData: FuturesOutcomeHistory[];
  topGolfers: GolfGolfer[];
}) {
  // Match history outcomes to top golfers by name
  const topNames = new Set(topGolfers.map((g) => g.name.toLowerCase()));
  const matched = historyData
    .filter((o) => topNames.has(o.name.toLowerCase()))
    .slice(0, 5);

  if (matched.length === 0) return null;

  // Find global time and probability bounds
  const allPoints = matched.flatMap((o) => o.history.filter((p) => p.probability !== null));
  if (allPoints.length < 2) return null;

  const allTimes = allPoints.map((p) => new Date(p.timestamp).getTime());
  const allProbs = allPoints.map((p) => p.probability!);
  const minTime = Math.min(...allTimes);
  const maxTime = Math.max(...allTimes);
  const minProb = Math.max(0, Math.min(...allProbs) - 0.02);
  const maxProb = Math.min(1, Math.max(...allProbs) + 0.02);

  if (maxTime === minTime || maxProb === minProb) return null;

  const w = 320;
  const h = 80;
  const pad = { top: 4, right: 4, bottom: 4, left: 4 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;

  function toX(t: number) {
    return pad.left + ((t - minTime) / (maxTime - minTime)) * plotW;
  }
  function toY(p: number) {
    return pad.top + plotH - ((p - minProb) / (maxProb - minProb)) * plotH;
  }

  // Build SVG paths for each golfer
  const lines = matched.map((outcome, idx) => {
    const golferIdx = topGolfers.findIndex(
      (g) => g.name.toLowerCase() === outcome.name.toLowerCase()
    );
    const color = SPARKLINE_COLORS[golferIdx >= 0 ? golferIdx : idx] || SPARKLINE_COLORS[4];

    const points = outcome.history
      .filter((p) => p.probability !== null)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    if (points.length < 2) return null;

    const d = points
      .map((p, i) => {
        const x = toX(new Date(p.timestamp).getTime());
        const y = toY(p.probability!);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    return (
      <path
        key={outcome.outcome_id}
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={golferIdx === 0 ? 2 : 1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={golferIdx === 0 ? 1 : 0.6}
      />
    );
  });

  // Time axis labels
  const timeSpan = maxTime - minTime;
  const daysAgo = Math.round(timeSpan / 86400000);
  const timeLabel = daysAgo <= 1 ? "24h" : `${daysAgo}d`;

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-text-muted uppercase tracking-wider">
          Odds trend ({timeLabel})
        </span>
        <div className="flex gap-2">
          {matched.slice(0, 3).map((o, i) => {
            const golferIdx = topGolfers.findIndex(
              (g) => g.name.toLowerCase() === o.name.toLowerCase()
            );
            const color = SPARKLINE_COLORS[golferIdx >= 0 ? golferIdx : i];
            const lastName = o.name.split(" ").pop() || o.name;
            return (
              <span key={o.outcome_id} className="flex items-center gap-1 text-[10px] text-text-muted">
                <span
                  className="w-2 h-0.5 rounded-full inline-block"
                  style={{ backgroundColor: color }}
                />
                {lastName}
              </span>
            );
          })}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ maxHeight: "80px" }}
        preserveAspectRatio="none"
      >
        {lines}
      </svg>
    </div>
  );
}

// ============================================================================
// Countdown
// ============================================================================

function Countdown({ targetDate }: { targetDate: string }) {
  const [timeLeft, setTimeLeft] = useState<{
    days: number;
    hours: number;
    minutes: number;
  } | null>(null);

  useEffect(() => {
    const target = new Date(targetDate).getTime();

    function update() {
      const now = Date.now();
      const diff = target - now;
      if (diff <= 0) {
        setTimeLeft(null);
        return;
      }
      setTimeLeft({
        days: Math.floor(diff / (1000 * 60 * 60 * 24)),
        hours: Math.floor((diff / (1000 * 60 * 60)) % 24),
        minutes: Math.floor((diff / (1000 * 60)) % 60),
      });
    }

    update();
    const interval = setInterval(update, 60_000);
    return () => clearInterval(interval);
  }, [targetDate]);

  if (!timeLeft) return null;

  return (
    <div className="flex items-center justify-center gap-4 mt-2">
      {[
        { value: timeLeft.days, label: "days" },
        { value: timeLeft.hours, label: "hrs" },
        { value: timeLeft.minutes, label: "min" },
      ].map(({ value, label }) => (
        <div key={label} className="text-center">
          <div className="text-2xl sm:text-3xl font-mono font-bold text-[#006747]">
            {String(value).padStart(2, "0")}
          </div>
          <div className="text-xs text-text-muted uppercase tracking-wider">
            {label}
          </div>
        </div>
      ))}
    </div>
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
          const pct = Math.round(mover.probability * 100);
          const delta = Math.abs(Math.round(mover.movement_24h * 100));

          return (
            <div
              key={`${mover.name}-${i}`}
              className="flex-shrink-0 bg-surface-card rounded-lg border border-surface-border p-3 w-[160px]"
            >
              <div className="flex items-center gap-1 mb-1">
                <span
                  className={`text-sm font-bold ${
                    isUp ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {isUp ? "\u25B2" : "\u25BC"} {delta}%
                </span>
              </div>
              <div className="text-sm text-text-primary font-medium truncate">
                {mover.name}
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-xs text-text-muted truncate">
                  {mover.tournament_name}
                </span>
                <span className="text-xs font-mono text-text-secondary">
                  {pct}%
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
// Movement Badge
// ============================================================================

function MovementBadge({ movement }: { movement: number | null }) {
  if (movement === null || Math.abs(movement) < 0.005) return null;
  const isUp = movement > 0;
  const delta = Math.abs(Math.round(movement * 100));
  return (
    <span
      className={`text-[10px] font-medium px-1 py-0.5 rounded ${
        isUp
          ? "text-green-400 bg-green-400/10"
          : "text-red-400 bg-red-400/10"
      }`}
    >
      {isUp ? "\u25B2" : "\u25BC"}
      {delta}%
    </span>
  );
}

// ============================================================================
// Golfer Row
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
  const isLeader = golfer.rank === 1;
  const sourceCount = Object.keys(golfer.sources).length;

  // Compute model-vs-market divergence
  const modelProb = golfer.sources["datagolf_model"];
  const marketProbs = Object.entries(golfer.sources)
    .filter(([k]) => SOURCE_META[k]?.type === "market")
    .map(([, v]) => v);
  const avgMarketProb =
    marketProbs.length > 0
      ? marketProbs.reduce((a, b) => a + b, 0) / marketProbs.length
      : null;
  const divergence =
    modelProb != null && avgMarketProb != null
      ? modelProb - avgMarketProb
      : null;
  const hasDivergence = divergence != null && Math.abs(divergence) > 0.03;

  return (
    <div>
      <div className="flex items-center gap-2">
        <span
          className={`text-xs font-mono w-5 text-right ${
            isLeader ? "text-[#006747] font-bold" : "text-text-muted"
          }`}
        >
          {golfer.rank}
        </span>
        <span
          className={`text-sm flex-1 truncate ${
            isLeader ? "text-text-primary font-medium" : "text-text-secondary"
          }`}
        >
          {golfer.name}
        </span>
        {hasDivergence && (
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
              divergence! > 0
                ? "bg-amber-500/15 text-amber-400"
                : "bg-blue-500/15 text-blue-400"
            }`}
            title={`DataGolf model ${divergence! > 0 ? "higher" : "lower"} than market consensus by ${Math.round(Math.abs(divergence!) * 100)}%`}
          >
            {divergence! > 0 ? "Model +" : "Model "}
            {Math.round(divergence! * 100)}%
          </span>
        )}
        <MovementBadge movement={golfer.movement_24h} />
        <span className="text-sm font-mono text-text-primary w-10 text-right">
          {pct}%
        </span>
        {sourceCount > 1 && (
          <SourceDots sources={golfer.sources} />
        )}
      </div>
      <div className="ml-7 mr-16 mt-0.5 mb-0.5">
        <div className="h-1 bg-surface-elevated rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${barWidth}%`,
              backgroundColor: isLeader ? "#006747" : "#2d8659",
              opacity: isLeader ? 1 : 0.6,
            }}
          />
        </div>
      </div>
      {showSourceBreakdown && sourceCount > 1 && (
        <div className="ml-7 mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(golfer.sources)
            .sort(([, a], [, b]) => b - a)
            .map(([source, prob]) => {
              const meta = SOURCE_META[source];
              return (
                <span key={source} className="text-[10px] text-text-muted">
                  {source === "odds_api"
                    ? "Sportsbooks"
                    : source === "kalshi"
                      ? "Kalshi"
                      : source === "polymarket"
                        ? "Polymarket"
                        : source === "datagolf_model"
                          ? "DG Model"
                          : source}
                  {meta?.type === "model" && (
                    <span className="ml-0.5 text-amber-400/70 text-[9px]">M</span>
                  )}
                  : {Math.round(prob * 100)}%
                </span>
              );
            })}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Source Dots
// ============================================================================

/** Source metadata: color and type (model vs market) */
const SOURCE_META: Record<string, { color: string; type: "model" | "market" }> = {
  odds_api: { color: "#3b82f6", type: "market" },
  kalshi: { color: "#22c55e", type: "market" },
  polymarket: { color: "#8b5cf6", type: "market" },
  datagolf_model: { color: "#f59e0b", type: "model" },
};

function SourceDots({ sources }: { sources: Record<string, number> }) {
  return (
    <div className="flex gap-1 items-center">
      {Object.keys(sources).map((s) => {
        const meta = SOURCE_META[s];
        return (
          <span
            key={s}
            className={`w-1.5 h-1.5 rounded-full inline-block ${
              meta?.type === "model" ? "ring-1 ring-amber-400/50" : ""
            }`}
            style={{ backgroundColor: meta?.color || "#6b7280" }}
          />
        );
      })}
    </div>
  );
}

// ============================================================================
// Tournament Card (Majors — compact grid)
// ============================================================================

function TournamentCard({
  tournament,
  onClick,
}: {
  tournament: GolfTournament;
  onClick: () => void;
}) {
  const emoji = TOURNAMENT_EMOJI[tournament.key] || "\u26F3";
  const venue = TOURNAMENT_VENUES[tournament.key];
  const topGolfers = tournament.golfers.slice(0, 8);

  return (
    <div
      onClick={onClick}
      className="group bg-surface-card rounded-xl border border-l-4 border-surface-border border-l-[#006747] p-4 hover:shadow-card-hover hover:border-[#006747]/30 transition-all cursor-pointer h-full"
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{emoji}</span>
        <h3 className="text-body-strong text-text-primary">{tournament.name}</h3>
      </div>
      {venue && <p className="text-xs text-text-muted mb-3">{venue}</p>}
      {tournament.commence_time && (
        <p className="text-xs text-text-muted mb-3">
          {new Date(tournament.commence_time).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </p>
      )}
      <div className="space-y-1.5">
        {topGolfers.map((golfer) => (
          <GolferRow
            key={golfer.name}
            golfer={golfer}
            tournamentKey={tournament.key}
          />
        ))}
      </div>
      {tournament.golfers.length > 8 && (
        <p className="text-xs text-[#006747] mt-3 group-hover:underline">
          View all {tournament.golfers.length} golfers &rarr;
        </p>
      )}
    </div>
  );
}

// ============================================================================
// Expandable Tournament Row (Tour Events / Other)
// ============================================================================

function ExpandableTournamentRow({
  tournament,
  onClickFull,
}: {
  tournament: GolfTournament;
  onClickFull: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const emoji = TOURNAMENT_EMOJI[tournament.key] || "\u26F3";
  const leader = tournament.golfers[0];

  let timingLabel = "";
  if (tournament.start_date && tournament.end_date) {
    const start = new Date(tournament.start_date);
    const end = new Date(tournament.end_date);
    const now = new Date();
    if (now >= start && now <= end) timingLabel = "In Progress";
    else if (now > end) timingLabel = "Completed";
    else {
      const days = Math.ceil((start.getTime() - now.getTime()) / 86400000);
      timingLabel =
        days <= 7
          ? `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} \u2013 ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`
          : start.toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            });
    }
  } else if (tournament.golfers.some((g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01)) {
    // No schedule dates but significant odds movement → tournament is in progress
    timingLabel = "In Progress";
  } else if (tournament.resolution_date) {
    const res = new Date(tournament.resolution_date);
    const days = Math.ceil(
      (res.getTime() - Date.now()) / 86400000
    );
    if (days < 0) timingLabel = "Completed";
    else if (days <= 7)
      timingLabel = res.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    else
      timingLabel = res.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
  }

  return (
    <div className="bg-surface-card rounded-lg border border-surface-border overflow-hidden">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-3 p-3 text-left hover:bg-surface-elevated/50 transition-colors"
      >
        <span>{emoji}</span>
        <div className="flex-1 min-w-0">
          <span className="text-sm text-text-primary font-medium">
            {tournament.name}
          </span>
          {(tournament.venue || timingLabel) && (
            <span className="text-xs text-text-muted ml-2">
              {tournament.venue && tournament.venue}
              {tournament.venue && timingLabel && " \u00B7 "}
              {timingLabel}
            </span>
          )}
          {/* Market description subtitle */}
          {tournament.market_names && tournament.market_names.length > 0 && !tournament.is_tour_event && (
            <div className="text-[11px] text-text-muted mt-0.5 truncate">
              {tournament.market_names.length === 1
                ? tournament.market_names[0]
                : tournament.market_names.join(" \u00B7 ")}
            </div>
          )}
        </div>
        {leader && (
          <span className="text-xs text-text-muted hidden sm:inline">
            {leader.name} ({Math.round(leader.probability * 100)}%)
          </span>
        )}
        <span className="text-text-muted text-xs">
          {expanded ? "\u25B2" : "\u25BC"}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-1.5 border-t border-surface-border pt-2">
          {tournament.golfers.slice(0, 15).map((golfer) => (
            <GolferRow
              key={golfer.name}
              golfer={golfer}
              tournamentKey={tournament.key}
              showSourceBreakdown
            />
          ))}
          {tournament.golfers.length > 15 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClickFull();
              }}
              className="text-xs text-[#006747] hover:underline mt-1"
            >
              View all {tournament.golfers.length} golfers &rarr;
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Tournament Modal
// ============================================================================

function TournamentModal({
  tournament,
  historyData,
  onClose,
}: {
  tournament: GolfTournament;
  historyData?: FuturesOutcomeHistory[];
  onClose: () => void;
}) {
  const emoji = TOURNAMENT_EMOJI[tournament.key] || "\u26F3";

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-start justify-center pt-8 sm:pt-16 px-4"
      onClick={onClose}
    >
      <div
        className="bg-surface-deep rounded-xl border border-surface-border w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-surface-deep/95 backdrop-blur-md border-b border-surface-border px-5 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <span className="text-xl">{emoji}</span>
            <h2 className="text-lg font-bold text-text-primary">
              {tournament.name}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-lg"
          >
            &times;
          </button>
        </div>

        {/* Chart */}
        {historyData && historyData.length > 0 && (
          <div className="px-5 py-4 border-b border-surface-border">
            <FuturesChart
              historyData={historyData}
              greenTheme
              height={240}
            />
          </div>
        )}
        {!historyData && (
          <div className="px-5 py-6 text-center text-sm text-text-muted border-b border-surface-border">
            Loading chart data...
          </div>
        )}

        {/* Full golfer list */}
        <div className="px-5 py-4 space-y-2">
          {tournament.golfers.map((golfer) => (
            <GolferRow
              key={golfer.name}
              golfer={golfer}
              tournamentKey={tournament.key}
              showSourceBreakdown
            />
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-surface-border text-center">
          <p className="text-xs text-text-muted">
            {tournament.golfers.length} golfers &middot;{" "}
            {tournament.market_ids.length} market
            {tournament.market_ids.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
