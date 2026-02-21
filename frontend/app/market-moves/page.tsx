"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchMarketMoves } from "@/lib/api";
import type { MarketMovesItem } from "@/lib/api";

/**
 * "The Market Was Wrong" Page
 *
 * Shows recent upsets, big market errors, and futures movers.
 * A daily highlight reel of when the betting market got it wrong.
 */
export default function MarketMovesPage() {
  const [items, setItems] = useState<MarketMovesItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(48);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchMarketMoves({ hours, limit: 30 });
        setItems(data.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [hours]);

  const upsets = items.filter((i) => i.type === "upset");
  const marketErrors = items.filter((i) => i.type === "market_error");
  const futuresMovers = items.filter((i) => i.type === "futures_mover");

  return (
    <div className="min-h-screen bg-snow">
      {/* Header */}
      <header className="bg-white border-b border-mist">
        <div className="max-w-4xl mx-auto px-4 py-4 sm:py-6">
          <Link
            href="/"
            className="text-sm text-slate hover:text-graphite transition-colors mb-2 inline-block"
          >
            &larr; Back to feed
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold text-graphite">
            The Market Was Wrong
          </h1>
          <p className="text-slate mt-1">
            When the betting market got it wrong — upsets, surprises, and big
            shifts.
          </p>

          {/* Time range selector */}
          <div className="flex gap-2 mt-3">
            {[
              { label: "24h", value: 24 },
              { label: "48h", value: 48 },
              { label: "7 days", value: 168 },
            ].map(({ label, value }) => (
              <button
                key={value}
                onClick={() => setHours(value)}
                className={`px-3 py-1 text-sm rounded-full transition-colors ${
                  hours === value
                    ? "bg-graphite text-white"
                    : "bg-white border border-mist text-slate hover:bg-snow"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-8">
        {loading && (
          <div className="text-center py-12 text-slate">Loading...</div>
        )}

        {error && (
          <div className="text-center py-12 text-red-500">{error}</div>
        )}

        {!loading && !error && items.length === 0 && (
          <div className="text-center py-12">
            <p className="text-lg text-slate">
              No big market surprises in the last {hours} hours.
            </p>
            <p className="text-sm text-gray-400 mt-1">
              Check back after more games finish.
            </p>
          </div>
        )}

        {/* UPSETS SECTION */}
        {upsets.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-graphite mb-3 flex items-center gap-2">
              <span className="text-xl">&#x1f92f;</span> Upsets
            </h2>
            <div className="space-y-3">
              {upsets.map((item, idx) => (
                <UpsetCard key={`upset-${idx}`} item={item} />
              ))}
            </div>
          </section>
        )}

        {/* MARKET ERRORS SECTION */}
        {marketErrors.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-graphite mb-3 flex items-center gap-2">
              <span className="text-xl">&#x1f4c9;</span> Market Misreads
            </h2>
            <div className="space-y-3">
              {marketErrors.map((item, idx) => (
                <MarketErrorCard key={`error-${idx}`} item={item} />
              ))}
            </div>
          </section>
        )}

        {/* FUTURES MOVERS SECTION */}
        {futuresMovers.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-graphite mb-3 flex items-center gap-2">
              <span className="text-xl">&#x1f4c8;</span> Biggest Futures Shifts
            </h2>
            <div className="space-y-3">
              {futuresMovers.map((item, idx) => (
                <FuturesMoverCard key={`mover-${idx}`} item={item} />
              ))}
            </div>
          </section>
        )}

        {/* Attribution */}
        {!loading && items.length > 0 && (
          <p className="text-xs text-gray-300 text-center pt-4">
            Based on opening odds vs actual results. Not betting advice.
          </p>
        )}
      </main>
    </div>
  );
}

// ============================================================================
// Card Components
// ============================================================================

function UpsetCard({ item }: { item: MarketMovesItem }) {
  const favoritePct = Math.round((item.loser_opening_prob || 0) * 100);
  const underdogPct = Math.round((item.winner_opening_prob || 0) * 100);
  const errorPct = Math.round((item.market_error || 0) * 100);

  return (
    <Link href={`/events/${item.event_id}`}>
      <div className="bg-white rounded-xl shadow-sm border border-mist p-4 hover:shadow-md transition-shadow cursor-pointer">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Sport badge */}
            {item.sport_name && (
              <span className="text-xs text-slate bg-snow px-2 py-0.5 rounded-full">
                {item.sport_name}
              </span>
            )}

            {/* Result */}
            <div className="mt-2">
              <span className="font-semibold text-graphite">
                {item.winner}
              </span>{" "}
              <span className="text-sm text-slate">beat</span>{" "}
              <span className="font-medium text-graphite">{item.loser}</span>
              <span className="text-slate ml-2">
                {item.winner_score}&ndash;{item.loser_score}
              </span>
            </div>

            {/* Explanation */}
            <p className="text-sm text-slate mt-1">
              {item.loser} was a{" "}
              <span className="font-medium text-red-600">{favoritePct}%</span>{" "}
              favorite. {item.winner} only had a {underdogPct}% chance.
            </p>

            {/* Time */}
            {item.commence_time && (
              <p className="text-xs text-gray-400 mt-1">
                {formatRelativeTime(item.commence_time)}
              </p>
            )}
          </div>

          {/* Error badge */}
          <div className="flex-shrink-0 text-right">
            <div
              className={`text-lg font-bold ${
                errorPct >= 30
                  ? "text-red-600"
                  : errorPct >= 20
                  ? "text-orange-500"
                  : "text-amber-500"
              }`}
            >
              {errorPct}%
            </div>
            <div className="text-xs text-gray-400">off</div>
          </div>
        </div>
      </div>
    </Link>
  );
}

function MarketErrorCard({ item }: { item: MarketMovesItem }) {
  const errorPct = Math.round((item.market_error || 0) * 100);

  return (
    <Link href={`/events/${item.event_id}`}>
      <div className="bg-white rounded-xl shadow-sm border border-mist p-4 hover:shadow-md transition-shadow cursor-pointer">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {item.sport_name && (
              <span className="text-xs text-slate bg-snow px-2 py-0.5 rounded-full">
                {item.sport_name}
              </span>
            )}

            <div className="mt-2">
              <span className="font-semibold text-graphite">
                {item.winner}
              </span>{" "}
              <span className="text-sm text-slate">beat</span>{" "}
              <span className="font-medium text-graphite">{item.loser}</span>
              <span className="text-slate ml-2">
                {item.winner_score}&ndash;{item.loser_score}
              </span>
            </div>

            <p className="text-sm text-slate mt-1">{item.description}</p>

            {item.commence_time && (
              <p className="text-xs text-gray-400 mt-1">
                {formatRelativeTime(item.commence_time)}
              </p>
            )}
          </div>

          <div className="flex-shrink-0 text-right">
            <div className="text-lg font-bold text-amber-500">{errorPct}%</div>
            <div className="text-xs text-gray-400">off</div>
          </div>
        </div>
      </div>
    </Link>
  );
}

function FuturesMoverCard({ item }: { item: MarketMovesItem }) {
  const changePct = Math.round(Math.abs(item.change_24h || 0) * 100);
  const currentPct = Math.round((item.current_probability || 0) * 100);
  const isUp = (item.change_24h || 0) > 0;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-mist p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {item.sport_name && (
            <span className="text-xs text-slate bg-snow px-2 py-0.5 rounded-full">
              {item.sport_name}
            </span>
          )}

          <div className="mt-2">
            <span className="font-semibold text-graphite">
              {item.outcome_name}
            </span>
          </div>

          <p className="text-sm text-slate mt-1">
            {isUp ? "Surged" : "Dropped"} {changePct}% to {currentPct}% in{" "}
            <span className="font-medium">{item.market_name}</span>
          </p>

          {item.market_tier === 1 && (
            <span className="inline-block text-xs text-purple-600 bg-purple-50 px-2 py-0.5 rounded-full mt-1">
              Championship
            </span>
          )}
        </div>

        <div className="flex-shrink-0 text-right">
          <div
            className={`text-lg font-bold ${
              isUp ? "text-green-600" : "text-red-600"
            }`}
          >
            {isUp ? "+" : "-"}
            {changePct}%
          </div>
          <div className="text-xs text-gray-400">24h</div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

  if (diffHours < 1) return "Just now";
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
