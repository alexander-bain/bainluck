"use client";

import { useState, useEffect } from "react";
import { fetchLineMovement, type LineMovementResponse, type LineMovement } from "@/lib/api";

interface LineMovementExplainerProps {
  eventId: number;
  homeTeam: string;
  awayTeam: string;
  eventStatus: string;
}

export default function LineMovementExplainer({
  eventId,
  homeTeam,
  awayTeam,
  eventStatus,
}: LineMovementExplainerProps) {
  const [data, setData] = useState<LineMovementResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const result = await fetchLineMovement(eventId);
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }

    load();

    // Refresh for live events
    let interval: NodeJS.Timeout | undefined;
    if (eventStatus === "live") {
      interval = setInterval(load, 60000); // Every minute
    }

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [eventId, eventStatus]);

  // Don't render if no significant data
  if (loading || error || !data) return null;
  if (!data.movements?.length && !data.disagreement_explanation) return null;

  return (
    <div className="bg-surface-card rounded-card shadow-card p-4 sm:p-5 space-y-4">
      {/* Line Movement Section */}
      {data.movements?.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text-secondary mb-2 flex items-center gap-2">
            <span className="text-lg">📈</span>
            Why Did the Line Move?
          </h3>

          {/* AI Explanation */}
          {data.explanation && (
            <p className="text-sm text-gray-700 leading-relaxed mb-3">
              {data.explanation}
            </p>
          )}

          {/* Movement Details */}
          <div className="space-y-2">
            {data.movements.slice(0, 3).map((movement, idx) => (
              <MovementCard
                key={idx}
                movement={movement}
                homeTeam={homeTeam}
                awayTeam={awayTeam}
              />
            ))}
          </div>

          {!data.explanation && (
            <p className="text-xs text-text-muted mt-2">
              AI explanation unavailable
            </p>
          )}
        </div>
      )}

      {/* Prediction Market Disagreement Section */}
      {data.disagreement_data && (
        <div className={data.movements?.length ? "pt-3 border-t border-gray-100" : ""}>
          <h3 className="text-sm font-semibold text-text-secondary mb-2 flex items-center gap-2">
            <span className="text-lg">🔮</span>
            Market Divergence
          </h3>

          {/* Divergence visual */}
          <div className="flex items-center gap-3 mb-2">
            <div className="flex-1">
              <div className="text-xs text-gray-500 mb-1">Sportsbooks</div>
              <div className="text-lg font-bold text-gray-900">
                {Math.round(data.disagreement_data.sportsbook_home_prob * 100)}%
              </div>
            </div>

            <div className="flex flex-col items-center">
              <div className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                data.disagreement_data.divergence >= 0.10
                  ? "bg-purple-100 text-purple-700"
                  : "bg-blue-100 text-blue-700"
              }`}>
                {Math.round(data.disagreement_data.divergence * 100)}% gap
              </div>
              <span className="text-text-muted text-xs">vs</span>
            </div>

            <div className="flex-1 text-right">
              <div className="text-xs text-gray-500 mb-1">
                {data.disagreement_data.source === "kalshi" ? "Kalshi" : "Polymarket"}
              </div>
              <div className="text-lg font-bold text-gray-900">
                {Math.round(data.disagreement_data.prediction_market_home_prob * 100)}%
              </div>
            </div>
          </div>

          <div className="text-xs text-text-muted mb-2">
            {homeTeam} win probability
          </div>

          {/* AI Explanation */}
          {data.disagreement_explanation && (
            <p className="text-sm text-gray-700 leading-relaxed">
              {data.disagreement_explanation}
            </p>
          )}
        </div>
      )}

      {/* Attribution */}
      <div className="text-xs text-text-muted pt-1">
        Powered by AI analysis · Not betting advice
      </div>
    </div>
  );
}

function MovementCard({
  movement,
  homeTeam,
  awayTeam,
}: {
  movement: LineMovement;
  homeTeam: string;
  awayTeam: string;
}) {
  const isTowardHome = movement.change > 0;
  const beneficiary = isTowardHome ? homeTeam : awayTeam;
  const magnitude = Math.round(movement.magnitude * 100);
  const isMajor = movement.is_major;

  // Color based on magnitude
  const bgColor = isMajor
    ? "bg-amber-50 border-amber-200"
    : "bg-gray-50 border-gray-200";
  const textColor = isMajor ? "text-amber-700" : "text-text-secondary";

  // Format time
  const startTime = new Date(movement.timestamp_start);
  const timeStr = startTime.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  return (
    <div className={`rounded-lg border px-3 py-2 ${bgColor}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${textColor}`}>
            {isMajor ? "⚡" : "↗"} {magnitude}% swing
          </span>
          <span className="text-xs text-text-muted">
            toward {beneficiary}
          </span>
        </div>
        <span className="text-xs text-text-muted">{timeStr}</span>
      </div>
      <div className="text-xs text-gray-500 mt-0.5">
        {Math.round(movement.home_prob_before * 100)}% → {Math.round(movement.home_prob_after * 100)}%
        <span className="text-text-muted ml-1">({homeTeam})</span>
      </div>
    </div>
  );
}
