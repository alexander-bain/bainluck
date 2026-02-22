"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import type { WinProbSourceMeta, ESPNHistoryPoint } from "@/lib/types";

/** Fallback source info for legacy events without win_prob_sources */
const FALLBACK_SOURCES: Record<string, WinProbSourceMeta> = {
  betting: {
    display_name: "Betting Odds",
    type: "market",
    color: "#374151",
    description:
      "Consensus win probability derived from sportsbook moneyline odds, aggregated across multiple bookmakers.",
    methodology:
      "Moneyline odds from each bookmaker are converted to implied probabilities, then the vig (overround) is removed. The median probability across all reporting bookmakers is used as the consensus.",
    attribution_url: "https://the-odds-api.com",
    attribution_name: "The Odds API",
    snapshot_count: 0,
  },
  espn: {
    display_name: "ESPN",
    type: "model",
    color: "#f97316",
    dash_pattern: "6 3",
    description:
      "ESPN's proprietary predictive model that updates on every play during live games.",
    methodology:
      "ESPN's internal win probability model, same data shown on ESPN.com game pages. Methodology is not publicly documented.",
    attribution_url: "https://www.espn.com",
    attribution_name: "ESPN",
    snapshot_count: 0,
  },
  stat_model: {
    display_name: "Bain Luck Model",
    type: "model",
    color: "#8b5cf6",
    dash_pattern: "4 4",
    description:
      "An open win probability model inspired by nflfastR and Pro-Football-Reference. Uses current score, time remaining, and the pregame Vegas spread.",
    methodology:
      "Based on the methodology from Hal Stern's research and Wayne Winston's Mathletics. The final margin of victory is modeled as a normal distribution where: (1) the mean equals the current score differential plus the pregame spread scaled by remaining game fraction, and (2) the standard deviation equals a sport-specific base value (NFL: 13.45 points) multiplied by the square root of the remaining game fraction. Win probability is then P(final margin > 0) using the normal CDF.",
    attribution_url:
      "https://www.pro-football-reference.com/about/win_prob.htm",
    attribution_name: "nflfastR / PFR methodology",
    snapshot_count: 0,
  },
};

interface ModelsPageProps {
  params: { id: string };
}

export default function ModelsPage({ params }: ModelsPageProps) {
  const eventId = parseInt(params.id, 10);

  const { data: event, error: eventError } = useSWR(
    `/api/events/${eventId}`,
    () => fetchEvent(eventId)
  );

  const { data: historyData } = useSWR(
    event ? `/api/events/${eventId}/history` : null,
    () => fetchEventHistory(eventId)
  );

  if (eventError) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <ErrorMessage message="Failed to load event" />
      </div>
    );
  }

  if (!event) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <LoadingSpinner />
      </div>
    );
  }

  // Build sources list from API data or fallbacks
  const apiSources = historyData?.win_prob_sources ?? {};
  const hasApiSources = Object.keys(apiSources).length > 0;

  // Build the display list: always show betting, then any model sources
  const displaySources: Array<{
    key: string;
    meta: WinProbSourceMeta;
    currentValue: number | null;
  }> = [];

  // Betting odds (always available)
  const bettingMeta = apiSources.betting ?? FALLBACK_SOURCES.betting;
  displaySources.push({
    key: "betting",
    meta: {
      ...bettingMeta,
      snapshot_count: bettingMeta.snapshot_count ?? historyData?.points ?? 0,
    },
    currentValue: event.current_odds?.home_probability ?? null,
  });

  // Model sources from API
  if (hasApiSources) {
    for (const [key, meta] of Object.entries(apiSources)) {
      if (key === "betting") continue;
      const currentVal = event.win_probability_sources?.[key]?.value ?? null;
      displaySources.push({ key, meta, currentValue: currentVal });
    }
  } else {
    // Legacy: check for ESPN data
    if (
      historyData?.espn_history &&
      (historyData.espn_history as ESPNHistoryPoint[]).length > 0
    ) {
      const espnFallback = FALLBACK_SOURCES.espn;
      displaySources.push({
        key: "espn",
        meta: {
          ...espnFallback,
          snapshot_count: (historyData.espn_history as ESPNHistoryPoint[])
            .length,
        },
        currentValue: event.espn?.win_probability ?? null,
      });
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div>
        <Link
          href={`/events/${eventId}`}
          className="text-sm text-blue-600 hover:text-blue-800 mb-2 inline-block"
        >
          &larr; Back to {event.home_team} vs {event.away_team}
        </Link>
        <h1 className="text-xl font-bold text-gray-900">
          Win Probability Sources
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {event.home_team} vs {event.away_team} &mdash; How each source
          calculates who will win
        </p>
      </div>

      {/* Source cards */}
      {displaySources.map(({ key, meta, currentValue }) => (
        <div
          key={key}
          className="bg-surface-card rounded-lg shadow-card border border-gray-200 overflow-hidden"
        >
          {/* Source header with color accent */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-100">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: meta.color }}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-gray-900">
                  {meta.display_name}
                </h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-surface-elevated text-gray-500">
                  {meta.type}
                </span>
              </div>
              {meta.attribution_name && meta.attribution_url && (
                <a
                  href={meta.attribution_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-500 hover:text-blue-700"
                >
                  {meta.attribution_name} &rarr;
                </a>
              )}
            </div>
            {currentValue !== null && (
              <div className="text-right shrink-0">
                <p className="text-lg font-bold text-gray-900">
                  {(currentValue * 100).toFixed(1)}%
                </p>
                <p className="text-xs text-text-muted">{event.home_team}</p>
              </div>
            )}
          </div>

          {/* Description + methodology */}
          <div className="px-5 py-4 space-y-3">
            {meta.description && (
              <p className="text-sm text-text-secondary">{meta.description}</p>
            )}
            {meta.methodology && (
              <div>
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-1">
                  Methodology
                </h3>
                <p className="text-sm text-gray-500">{meta.methodology}</p>
              </div>
            )}
            {meta.snapshot_count > 0 && (
              <p className="text-xs text-text-muted">
                {meta.snapshot_count} data points captured for this event
              </p>
            )}
          </div>

          {/* Chart line preview */}
          <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 flex items-center gap-2">
            <svg width="30" height="4" className="shrink-0">
              <line
                x1="0"
                y1="2"
                x2="30"
                y2="2"
                stroke={meta.color}
                strokeWidth="2.5"
                strokeDasharray={meta.dash_pattern ?? undefined}
              />
            </svg>
            <span className="text-xs text-text-muted">
              Shown as this line on the chart
            </span>
          </div>
        </div>
      ))}

      {/* Explanation footer */}
      <div className="bg-blue-50 rounded-lg p-4 text-sm text-blue-800">
        <p className="font-medium mb-1">Why show multiple sources?</p>
        <p className="text-blue-600">
          Market-implied probabilities (betting odds) reflect where real money
          is positioned. Model-based probabilities compute win chances from game
          state alone. When these diverge, it often means the market is pricing
          in information the model doesn&apos;t have (like injuries or momentum),
          or the model is reacting faster to score changes.
        </p>
      </div>
    </div>
  );
}
