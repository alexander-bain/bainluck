"use client";

import { useState, useMemo } from "react";
import { SOURCE_COLORS as SOURCE_COLOR_REGISTRY, canonicalSourceKey } from "@/lib/sourceColors";

/** Shared with backend SOURCE_DISAGREEMENT_THRESHOLD_PP and Discover comparison card. */
export const SOURCE_DISAGREEMENT_PP = 5;

// Individual sportsbook BRAND colors. Registry sources (kalshi/polymarket) are
// NOT listed here — they resolve through the one source-color registry so their
// identity color matches every other surface (they used to be indigo/#0052FF
// here, green/blue everywhere else — the class-E drift this queue kills).
const BOOKMAKER_COLORS: Record<string, string> = {
  draftkings: "#53B94B",
  fanduel: "#1493FF",
  betmgm: "#C1A96D",
  bovada: "#CC0000",
  pointsbet: "#E34E2E",
  williamhill: "#1B3668",
  caesars: "#AA8B2A",
  bet365: "#027B5B",
  unibet: "#147B45",
  barstool: "#FF4500",
  betrivers: "#1E5D9C",
  mybookieag: "#232323",
  superbook: "#002D62",
  lowvig: "#333333",
  betonlineag: "#DC143C",
  betus: "#003366",
  wynnbet: "#001F3F",
  espnbet: "#FF3F3F",
  fanatics: "#1E90FF",
  fliff: "#9B59B6",
  hardrockbet: "#FF6B35",
};

/** Color for any source dot: registry sources win, then sportsbook brand, then neutral. */
function aggSourceColor(source: string): string {
  return SOURCE_COLOR_REGISTRY[canonicalSourceKey(source)]?.hex ?? BOOKMAKER_COLORS[source] ?? "#888";
}

const SOURCE_LABELS: Record<string, string> = {
  draftkings: "DraftKings",
  fanduel: "FanDuel",
  betmgm: "BetMGM",
  bovada: "Bovada",
  pointsbet: "PointsBet",
  williamhill: "William Hill",
  caesars: "Caesars",
  bet365: "Bet365",
  unibet: "Unibet",
  barstool: "Barstool",
  betrivers: "BetRivers",
  mybookieag: "MyBookie",
  superbook: "SuperBook",
  lowvig: "LowVig",
  betonlineag: "BetOnline",
  betus: "BetUS",
  wynnbet: "WynnBet",
  espnbet: "ESPN Bet",
  fanatics: "Fanatics",
  fliff: "Fliff",
  hardrockbet: "Hard Rock",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};

interface SourceRow {
  source: string;
  outcomes: Record<number, number>; // outcome_id → probability (%)
  captured_at: string | null;
  stale?: boolean;
}

interface SourceAggregationBlockProps {
  sources: SourceRow[];
  primaryOutcomeId: number | null;
  aggregatedProbability: number | null;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function SourceAggregationBlock({
  sources,
  primaryOutcomeId,
  aggregatedProbability,
}: SourceAggregationBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const { spread, isDisagreement, freshCount, sortedSources } = useMemo(() => {
    const fresh = sources.filter((s) => !s.stale);
    if (!primaryOutcomeId || fresh.length < 2) {
      return { spread: 0, isDisagreement: false, freshCount: fresh.length, sortedSources: sources };
    }
    const probs = fresh
      .map((s) => s.outcomes[primaryOutcomeId])
      .filter((p): p is number => p != null);
    const max = Math.max(...probs);
    const min = Math.min(...probs);
    const sp = Math.round((max - min) * 10) / 10;
    // Sort: fresh alphabetically, then stale alphabetically
    const sorted = [...sources].sort((a, b) => {
      if (a.stale !== b.stale) return a.stale ? 1 : -1;
      return a.source.localeCompare(b.source);
    });
    return {
      spread: sp,
      isDisagreement: sp >= SOURCE_DISAGREEMENT_PP,
      freshCount: fresh.length,
      sortedSources: sorted,
    };
  }, [sources, primaryOutcomeId]);

  if (freshCount < 2) return null;

  const autoExpand = isDisagreement;
  const isOpen = expanded || autoExpand;

  return (
    <div
      className={`rounded-card border transition-colors ${
        isDisagreement
          ? "border-amber-300/60 bg-amber-50/30"
          : "border-surface-border bg-surface-card"
      }`}
    >
      {/* Collapsed pill / header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2 text-[13px]">
          <span className="text-text-muted">
            Aggregated from{" "}
            <span className="font-semibold text-text-secondary">
              {freshCount} sources
            </span>
          </span>
          {spread > 0 && (
            <>
              <span className="text-text-muted/50">·</span>
              <span
                className={
                  isDisagreement
                    ? "font-semibold text-amber-600"
                    : "text-text-muted"
                }
              >
                {isDisagreement
                  ? `${spread}pt spread — sources disagree`
                  : `within ${spread} points`}
              </span>
            </>
          )}
        </div>
        <span className="text-[12px] text-text-muted font-medium">
          {isOpen ? "Hide" : "Show"} ›
        </span>
      </button>

      {/* Expanded per-source rows */}
      {isOpen && (
        <div className="px-4 pb-3">
          <div className="border-t border-surface-border pt-2.5">
            {sortedSources.map((src) => {
              const prob = primaryOutcomeId
                ? src.outcomes[primaryOutcomeId]
                : null;
              const color = aggSourceColor(src.source);
              const label =
                SOURCE_LABELS[src.source] ||
                src.source.charAt(0).toUpperCase() + src.source.slice(1);

              const diff =
                prob != null && aggregatedProbability != null
                  ? Math.round((prob - aggregatedProbability) * 10) / 10
                  : null;

              return (
                <div
                  key={src.source}
                  className={`flex items-center justify-between py-1.5 ${src.stale ? "opacity-40" : ""}`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: src.stale ? "#aaa" : color }}
                    />
                    <span className={`text-[13px] truncate ${src.stale ? "text-text-muted" : "text-text-primary"}`}>
                      {label}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    {prob != null && (
                      <span className={`font-mono text-[13px] font-semibold tabular-nums ${src.stale ? "text-text-muted" : "text-text-primary"}`}>
                        {prob.toFixed(1)}%
                      </span>
                    )}
                    {diff != null && diff !== 0 && (
                      <span
                        className={`font-mono text-[11px] tabular-nums ${
                          diff > 0 ? "text-accent-live" : "text-accent-danger"
                        }`}
                      >
                        {diff > 0 ? "+" : ""}
                        {diff.toFixed(1)}
                      </span>
                    )}
                    {src.captured_at && (
                      <span className="text-[11px] text-text-muted w-[52px] text-right">
                        {timeAgo(src.captured_at)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-text-muted/60 mt-2 text-center">
            Sources listed alphabetically, never ranked
          </p>
        </div>
      )}
    </div>
  );
}
