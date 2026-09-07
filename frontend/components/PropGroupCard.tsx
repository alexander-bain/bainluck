"use client";

import Link from "next/link";
import { formatProbability } from "@/lib/api";
import type { LeagueMarket } from "@/lib/api";

interface PropGroupCardProps {
  market: LeagueMarket;
}

function cleanPropName(name: string): string {
  return name
    .replace(/^(NBA|NHL|MLB|NFL|WNBA|MLS)\s+/i, "")
    .replace(/\s*(2025|2026|2024)(-\d+)?\s*$/i, "")
    .trim();
}

/**
 * #3868 (CERT-2215) — SETTLED MEANS SETTLED, on this card too.
 *
 * `/sport/tennis/atp` showed Carlos Alcaraz at 78% to reach a quarterfinal he
 * had already reached. The backend half of #3868 taught the refresh rail to read
 * the venue's settlement, which fixed the NUMBER — and a settled leg then
 * arrived here as a bare `probability: 1.0` and was drawn as an ordinary "100%".
 * A result rendered as a probability is still the card offering odds on a
 * question that has been answered.
 *
 * The words and the colours are `FuturesCard`'s, character for character, not a
 * second settled vocabulary invented on a second card — Alex's standing ruling
 * is one system-wide settled language.
 *
 * Reads the GRADE the payload carries and never `probability === 1`. Inferring
 * settlement from certainty would stamp a result on a live book at 0.9995,
 * which is what the Alcaraz leg genuinely read for a day before it closed.
 */
function SettledMark({ won }: { won: boolean }) {
  return won ? (
    <span className="text-xs font-mono font-bold text-emerald-600">Won</span>
  ) : (
    <span className="text-xs font-mono text-text-muted">Lost</span>
  );
}

function isSettled(o: { settled?: boolean }): boolean {
  return o.settled === true;
}

export default function PropGroupCard({ market }: PropGroupCardProps) {
  const outcomes = market.top_outcomes.slice(0, 6);
  if (outcomes.length === 0) return null;

  const isThreshold = outcomes.every((o) =>
    /^\d|^over|^under|^yes|^no|^\+|^-/i.test(o.name.trim())
  );

  return (
    <Link href={`/futures/${market.id}`}>
      <div className="rounded-2xl border border-surface-border bg-surface-card p-4 hover:shadow-md transition-all cursor-pointer h-full">
        <div className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-3">
          {cleanPropName(market.name)}
        </div>

        {isThreshold ? (
          <div className="space-y-1">
            {outcomes.map((o) => (
              <div key={o.id} className="flex items-center gap-2">
                <span className="text-xs text-text-secondary truncate flex-1 min-w-0">{o.name}</span>
                {/* #3868: the bar is a reading of a live book, so a settled row
                    does not draw one — a full purple bar beside the word "Won"
                    is the same claim twice, in two different vocabularies. */}
                {!isSettled(o) && (
                  <div className="w-20 h-2 rounded-full overflow-hidden bg-surface-elevated flex-shrink-0">
                    <div
                      className="h-full rounded-full bg-purple-500/50 transition-all"
                      style={{ width: `${Math.max(2, Math.round((o.probability ?? 0) * 100))}%` }}
                    />
                  </div>
                )}
                <span className="text-xs font-mono font-semibold text-text-primary w-10 text-right flex-shrink-0">
                  {isSettled(o) ? (
                    <SettledMark won={o.is_winner === true} />
                  ) : o.probability !== null ? (
                    formatProbability(o.probability)
                  ) : (
                    "—"
                  )}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-1.5">
            {outcomes.map((o, i) => (
              <div key={o.id} className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  {/* #3868: a settled row is not ranked among the live
                      contenders. The backend already queues it behind them, so
                      numbering it "#6" would invite the reader to read a result
                      as sixth place in a race that no longer includes it. */}
                  <span className="text-[10px] text-text-muted/50 w-4 flex-shrink-0">
                    {isSettled(o) ? "" : `#${i + 1}`}
                  </span>
                  <span className="text-xs text-text-secondary truncate">{o.name}</span>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {/* A 24h move is a statement about a live book. A settled row
                      has none to make. */}
                  {!isSettled(o) && o.movement_24h !== null && o.movement_24h !== 0 && Math.abs(o.movement_24h) >= 0.02 && (
                    <span className={`text-[10px] font-medium ${o.movement_24h > 0 ? "text-accent-live" : "text-accent-danger"}`}>
                      {o.movement_24h > 0 ? "+" : ""}{(o.movement_24h * 100).toFixed(1)}
                    </span>
                  )}
                  {isSettled(o) ? (
                    <SettledMark won={o.is_winner === true} />
                  ) : (
                    <span className={`text-xs font-mono font-semibold ${i === 0 ? "text-text-primary" : "text-text-muted"}`}>
                      {o.probability !== null ? formatProbability(o.probability) : "—"}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {market.outcome_count > 6 && (
          <div className="text-[10px] text-text-muted mt-2 text-right">
            +{market.outcome_count - 6} more
          </div>
        )}
      </div>
    </Link>
  );
}
