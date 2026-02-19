"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchPulseRankings } from "@/lib/api";
import type { RankedEvent } from "@/lib/types";
import PulseBadge from "@/components/PulseBadge";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";

/**
 * Pulse Hall of Fame Page
 *
 * Shows the all-time highest and lowest Pulse games ever tracked.
 */
export default function PulseHallOfFamePage() {
  const [highest, setHighest] = useState<RankedEvent[]>([]);
  const [lowest, setLowest] = useState<RankedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"highest" | "lowest">("highest");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await fetchPulseRankings({ limit: 25 });
        setHighest(data.highest);
        setLowest(data.lowest);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load rankings");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const events = activeTab === "highest" ? highest : lowest;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Hero Section */}
      <div className="text-center space-y-4 pb-6 border-b border-mist">
        <div className="text-6xl">
          {activeTab === "highest" ? "🏆" : "😴"}
        </div>
        <h1 className="text-title-1 text-graphite">Pulse Hall of Fame</h1>
        <p className="text-lg text-slate max-w-xl mx-auto">
          {activeTab === "highest"
            ? "The most exciting games ever tracked. These are the ones people talk about for years."
            : "The least exciting games we've seen. Sometimes the outcome was never in doubt."}
        </p>
      </div>

      {/* Tab Selector */}
      <div className="flex justify-center">
        <div className="inline-flex bg-snow rounded-full p-1 border border-mist">
          <button
            onClick={() => setActiveTab("highest")}
            className={`px-6 py-2 rounded-full text-sm font-semibold transition-colors ${
              activeTab === "highest"
                ? "bg-white text-graphite shadow-sm"
                : "text-slate hover:text-graphite"
            }`}
          >
            Most Exciting
          </button>
          <button
            onClick={() => setActiveTab("lowest")}
            className={`px-6 py-2 rounded-full text-sm font-semibold transition-colors ${
              activeTab === "lowest"
                ? "bg-white text-graphite shadow-sm"
                : "text-slate hover:text-graphite"
            }`}
          >
            Least Exciting
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex justify-center py-12">
          <div className="animate-pulse text-slate">Loading rankings...</div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
          <p className="text-red-700">{error}</p>
        </div>
      )}

      {/* Rankings List */}
      {!loading && !error && (
        <div className="space-y-3">
          {events.length === 0 ? (
            <div className="text-center py-12 text-slate">
              No events with Pulse scores yet. Check back soon!
            </div>
          ) : (
            events.map((event) => (
              <Link
                key={event.id}
                href={`/events/${event.id}`}
                className="block"
              >
                <div
                  className={`bg-white rounded-xl border shadow-sm p-4 hover:shadow-md transition-shadow ${
                    activeTab === "highest"
                      ? event.rank <= 3
                        ? "border-amber-300 bg-gradient-to-r from-amber-50 to-white"
                        : "border-mist"
                      : "border-mist"
                  }`}
                >
                  <div className="flex items-center gap-4">
                    {/* Rank */}
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg ${
                        activeTab === "highest"
                          ? event.rank === 1
                            ? "bg-amber-400 text-white"
                            : event.rank === 2
                            ? "bg-slate-300 text-white"
                            : event.rank === 3
                            ? "bg-amber-600 text-white"
                            : "bg-slate-100 text-slate"
                          : "bg-slate-100 text-slate"
                      }`}
                    >
                      {event.rank}
                    </div>

                    {/* Event Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {event.sport && (
                          <span className="text-sm bg-slate/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <span>{getEmojiForLeague(event.sport)}</span>
                            <span className="text-slate font-medium">
                              {getLeagueDisplay(event.sport)}
                            </span>
                          </span>
                        )}
                        <span className="text-xs text-slate">
                          {formatDate(event.commence_time)}
                        </span>
                      </div>
                      <div className="font-semibold text-graphite truncate">
                        {event.away_team} @ {event.home_team}
                      </div>
                      {event.home_score !== null && event.away_score !== null && (
                        <div className="text-sm text-slate">
                          Final: {event.away_score} - {event.home_score}
                        </div>
                      )}
                    </div>

                    {/* Pulse Badge */}
                    <div className="flex-shrink-0">
                      {event.pulse && (
                        <PulseBadge pulse={event.pulse} size="md" showTooltip={false} />
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>
      )}

      {/* Back to Pulse Explainer */}
      <div className="text-center pt-4 pb-8 space-y-4">
        <Link
          href="/pulse"
          className="inline-flex items-center gap-2 text-slate hover:text-graphite transition-colors"
        >
          <span>←</span>
          <span>Learn more about Pulse</span>
        </Link>
        <div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-graphite text-white px-6 py-3 rounded-full font-semibold hover:bg-graphite/90 transition-colors"
          >
            <span>🍀</span>
            Find Exciting Games Now
          </Link>
        </div>
      </div>
    </div>
  );
}
