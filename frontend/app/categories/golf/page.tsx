"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchGolfData, fetchFuturesHistory } from "@/lib/api";
import type {
  GolfResponse,
  GolfTournament,
  GolfGolfer,
  GolfMover,
  FuturesOutcomeHistory,
} from "@/lib/types";
import {
  MAJOR_TOURNAMENTS,
  TOURNAMENT_VENUES,
  TOURNAMENT_EMOJI,
} from "@/lib/golfData";
import { FuturesChart } from "@/components/FuturesChart";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

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
  const [modalTournament, setModalTournament] = useState<GolfTournament | null>(null);
  const [historyByTournament, setHistoryByTournament] = useState<
    Record<string, FuturesOutcomeHistory[]>
  >({});
  const [expandedOther, setExpandedOther] = useState<Set<string>>(new Set());
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());

  // Phase 1: Fetch golf data
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const result = await fetchGolfData();
        setData(result);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load golf data"
        );
      } finally {
        setLoading(false);
      }
    }
    load();

    const interval = setInterval(() => {
      fetchGolfData()
        .then(setData)
        .catch(() => {});
    }, 120_000);
    return () => clearInterval(interval);
  }, []);

  // Phase 2: Lazy-load chart history when modal opens
  useEffect(() => {
    if (!modalTournament) return;
    const key = modalTournament.key;
    if (historyByTournament[key]) return;
    if (!modalTournament.market_ids[0]) return;

    fetchFuturesHistory(modalTournament.market_ids[0], 168)
      .then((h) => {
        if (h?.outcomes) {
          setHistoryByTournament((prev) => ({
            ...prev,
            [key]: h.outcomes,
          }));
        }
      })
      .catch(() => {});
  }, [modalTournament]);

  // Derived data
  const majors = data?.tournaments.filter((t) => t.is_major) || [];
  const otherTournaments = data?.tournaments.filter((t) => !t.is_major) || [];

  // Find next Major for countdown
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
            Tournament odds from Polymarket, Kalshi &amp; sportsbooks
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
          <div className="text-center py-16 text-text-secondary">
            Loading golf data...
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
                      expandedSources={expandedSources}
                      onToggleSource={(key) =>
                        setExpandedSources((prev) => {
                          const next = new Set(prev);
                          if (next.has(key)) next.delete(key);
                          else next.add(key);
                          return next;
                        })
                      }
                      onClick={() => setModalTournament(tournament)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Other Tournaments */}
            {otherTournaments.length > 0 && (
              <section>
                <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
                  <span className="text-[#006747]">&#x1F3CC;&#xFE0F;</span>
                  Other Tournaments
                </h2>
                <div className="space-y-2">
                  {otherTournaments.map((tournament) => (
                    <OtherTournamentRow
                      key={tournament.key}
                      tournament={tournament}
                      expanded={expandedOther.has(tournament.key)}
                      expandedSources={expandedSources}
                      onToggle={() =>
                        setExpandedOther((prev) => {
                          const next = new Set(prev);
                          if (next.has(tournament.key)) next.delete(tournament.key);
                          else next.add(tournament.key);
                          return next;
                        })
                      }
                      onToggleSource={(key) =>
                        setExpandedSources((prev) => {
                          const next = new Set(prev);
                          if (next.has(key)) next.delete(key);
                          else next.add(key);
                          return next;
                        })
                      }
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
                            {
                              weekday: "short",
                              month: "short",
                              day: "numeric",
                            }
                          )}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}
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
// Tournament Card (Majors)
// ============================================================================

function TournamentCard({
  tournament,
  expandedSources,
  onToggleSource,
  onClick,
}: {
  tournament: GolfTournament;
  expandedSources: Set<string>;
  onToggleSource: (key: string) => void;
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
      {venue && (
        <p className="text-xs text-text-muted mb-3">{venue}</p>
      )}
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
            showSources={expandedSources.has(`${tournament.key}_${golfer.name}`)}
            onToggleSource={() =>
              onToggleSource(`${tournament.key}_${golfer.name}`)
            }
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
// Golfer Row
// ============================================================================

function GolferRow({
  golfer,
  tournamentKey,
  showSources,
  onToggleSource,
}: {
  golfer: GolfGolfer;
  tournamentKey: string;
  showSources: boolean;
  onToggleSource: () => void;
}) {
  const pct = Math.round(golfer.probability * 100);
  const barWidth = Math.max(pct, 2);
  const isLeader = golfer.rank === 1;
  const sourceCount = Object.keys(golfer.sources).length;

  return (
    <div>
      <div
        className="flex items-center gap-2 group/row"
        onClick={(e) => {
          e.stopPropagation();
          if (sourceCount > 1) onToggleSource();
        }}
      >
        {/* Rank */}
        <span
          className={`text-xs font-mono w-5 text-right ${
            isLeader ? "text-[#006747] font-bold" : "text-text-muted"
          }`}
        >
          {golfer.rank}
        </span>

        {/* Name */}
        <span
          className={`text-sm flex-1 truncate ${
            isLeader ? "text-text-primary font-medium" : "text-text-secondary"
          }`}
        >
          {golfer.name}
        </span>

        {/* Movement */}
        {golfer.movement_24h !== null && Math.abs(golfer.movement_24h) >= 0.005 && (
          <MovementBadge movement={golfer.movement_24h} />
        )}

        {/* Probability */}
        <span className="text-sm font-mono text-text-primary w-10 text-right">
          {pct}%
        </span>

        {/* Source indicator */}
        {sourceCount > 1 && (
          <span className="text-[10px] text-text-muted cursor-pointer group-hover/row:text-text-secondary">
            {sourceCount}src
          </span>
        )}
      </div>

      {/* Probability bar */}
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

      {/* Source breakdown (expandable) */}
      {showSources && sourceCount > 1 && (
        <div className="ml-7 mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(golfer.sources)
            .sort(([, a], [, b]) => b - a)
            .map(([source, prob]) => (
              <span key={source} className="text-[10px] text-text-muted">
                {source}: {Math.round(prob * 100)}%
              </span>
            ))}
        </div>
      )}
    </div>
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
// Other Tournament Row (Expandable)
// ============================================================================

function OtherTournamentRow({
  tournament,
  expanded,
  expandedSources,
  onToggle,
  onToggleSource,
  onClickFull,
}: {
  tournament: GolfTournament;
  expanded: boolean;
  expandedSources: Set<string>;
  onToggle: () => void;
  onToggleSource: (key: string) => void;
  onClickFull: () => void;
}) {
  const emoji = TOURNAMENT_EMOJI[tournament.key] || "\u1F3CC\uFE0F";
  const leader = tournament.golfers[0];

  return (
    <div className="bg-surface-card rounded-lg border border-surface-border overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-3 text-left hover:bg-surface-elevated/50 transition-colors"
      >
        <span>{emoji}</span>
        <span className="text-sm text-text-primary font-medium flex-1">
          {tournament.name}
        </span>
        {leader && (
          <span className="text-xs text-text-muted">
            {leader.name} ({Math.round(leader.probability * 100)}%)
          </span>
        )}
        <span className="text-text-muted text-xs">
          {expanded ? "\u25B2" : "\u25BC"}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-1.5 border-t border-surface-border pt-2">
          {tournament.golfers.slice(0, 10).map((golfer) => (
            <GolferRow
              key={golfer.name}
              golfer={golfer}
              tournamentKey={tournament.key}
              showSources={expandedSources.has(`${tournament.key}_${golfer.name}`)}
              onToggleSource={() =>
                onToggleSource(`${tournament.key}_${golfer.name}`)
              }
            />
          ))}
          {tournament.golfers.length > 10 && (
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

  // Close on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Prevent body scroll
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
          {tournament.golfers.map((golfer) => {
            const pct = Math.round(golfer.probability * 100);
            const barWidth = Math.max(pct, 2);
            const isLeader = golfer.rank === 1;
            const sourceCount = Object.keys(golfer.sources).length;

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
                    className={`text-sm flex-1 ${
                      isLeader ? "text-text-primary font-medium" : "text-text-secondary"
                    }`}
                  >
                    {golfer.name}
                  </span>
                  {golfer.movement_24h !== null && Math.abs(golfer.movement_24h) >= 0.005 && (
                    <MovementBadge movement={golfer.movement_24h} />
                  )}
                  <span className="text-sm font-mono text-text-primary w-12 text-right">
                    {pct}%
                  </span>
                  {golfer.american_odds !== null && (
                    <span className="text-xs text-text-muted w-16 text-right">
                      {golfer.american_odds > 0 ? "+" : ""}
                      {golfer.american_odds}
                    </span>
                  )}
                </div>
                <div className="ml-7 mr-28 mt-0.5 mb-0.5">
                  <div className="h-1 bg-surface-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${barWidth}%`,
                        backgroundColor: isLeader ? "#006747" : "#2d8659",
                        opacity: isLeader ? 1 : 0.6,
                      }}
                    />
                  </div>
                </div>
                {/* Source breakdown in modal */}
                {sourceCount > 1 && (
                  <div className="ml-7 mb-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                    {Object.entries(golfer.sources)
                      .sort(([, a], [, b]) => b - a)
                      .map(([source, prob]) => (
                        <span key={source} className="text-[10px] text-text-muted">
                          {source}: {Math.round(prob * 100)}%
                        </span>
                      ))}
                  </div>
                )}
              </div>
            );
          })}
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
