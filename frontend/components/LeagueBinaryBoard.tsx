"use client";

/**
 * LeagueBinaryBoard — every yes/no question on a league page, once.
 *
 * UX-1052 item 8. Alex, shopping the MLB league page on 2026-09-03:
 *
 *     "Yes/No section: needs to be formatted WAY better; very high-potential —
 *      and there is a SECOND Yes/No section at the bottom of the page. Remove
 *      the duplicate; design the one that stays (question, one bar, the number,
 *      the mover, the venue badges). The Awards section is the reference:
 *      GREAT."
 *
 * THE DUPLICATE. `LeagueMarketSection` partitioned its own markets and rendered
 * its own "Yes / no" block, so the page grew one per section that happened to
 * contain a binary — measured on `/api/leagues/baseball_mlb`: 55 in `props`, 9
 * in `more_markets`, 1 in `awards`. Three blocks, one of them a header over a
 * single row. The partition now happens once, at page level
 * (`partitionLeagueMarkets`), and lands here.
 *
 * THE DESIGN. Four things per row, in Alex's order — question, one bar, the
 * number, the mover — plus the venue badge, which is what makes a merged board
 * legible: these rows no longer sit under a section that implied where they
 * came from, so each says its own.
 *
 * The bar is the change that matters most on a phone. The old row hid it
 * (`hidden sm:block`), so at 390px the block was a column of naked percentages
 * — which is what "needs to be formatted WAY better" was about. Here the bar
 * is always drawn, under the question, where it has the full card width.
 *
 * Ruling 047 is unchanged and load-bearing: ONE row per binary, stating the YES
 * side by name (`binaryAnswer`), never `top_outcomes[0]` by rank — 15 of 21 MLB
 * binaries are sorted No-first, so rank would print the complement of the
 * question.
 */

import { useState } from "react";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import { probabilityHeat } from "@/lib/probabilityColors";
import { cleanMarketName, sortBinariesByAnswer, type LeagueBinary } from "@/lib/leagueCards";

/** How many rows the board shows before asking. */
const COLLAPSED_ROWS = 12;

/** Below this the movement is noise, not a mover — the pre-existing bar. */
const MOVER_MIN = 0.02;

/** The venues we name. An unknown source prints nothing rather than a guess. */
const VENUE_LABEL: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api: "Books",
  datagolf: "DataGolf",
};

function VenueBadge({ source }: { source: string | null | undefined }) {
  const label = VENUE_LABEL[(source ?? "").toLowerCase()];
  if (!label) return null;
  return (
    <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-surface-elevated text-text-muted">
      {label}
    </span>
  );
}

function BinaryRow({ market, answer }: LeagueBinary) {
  const p = answer.probability;
  const heat = probabilityHeat(p);
  const moved = answer.movement != null && Math.abs(answer.movement) >= MOVER_MIN;

  return (
    <Link
      href={`/futures/${market.id}`}
      className="block py-2.5 px-2 -mx-2 rounded-lg hover:bg-surface-elevated/60 transition-colors"
    >
      <div className="flex items-center gap-2">
        <span className="flex-1 min-w-0 text-sm text-text-primary truncate">
          {cleanMarketName(market.name)}
        </span>
        {moved && (
          <span
            className={`shrink-0 text-[11px] font-semibold tabular-nums ${
              answer.movement! > 0 ? "text-accent-live" : "text-accent-danger"
            }`}
          >
            {answer.movement! > 0 ? "+" : ""}
            {(answer.movement! * 100).toFixed(1)}
          </span>
        )}
        <span className="w-11 shrink-0 text-right font-mono text-sm font-bold tabular-nums text-text-primary">
          {p == null ? "—" : formatProbability(p)}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        {/* A null probability draws NO track at all — never a 0%-wide bar inside
            a visible one, which is the same claim with extra steps (register
            E2). The bar is no longer `hidden sm:block`: on a phone it was the
            only thing that made the column scannable, and it was the thing
            being hidden. */}
        {p != null ? (
          <span className="flex-1 h-[6px] rounded-full bg-surface-elevated overflow-hidden">
            <span
              className={`block h-full rounded-full ${heat.bar}`}
              style={{ width: `${Math.max(2, Math.round(p * 100))}%` }}
            />
          </span>
        ) : (
          <span className="flex-1 text-[11px] text-text-muted">No probability yet</span>
        )}
        <VenueBadge source={market.source} />
      </div>
    </Link>
  );
}

interface LeagueBinaryBoardProps {
  binaries: LeagueBinary[];
}

export default function LeagueBinaryBoard({ binaries }: LeagueBinaryBoardProps) {
  const [expanded, setExpanded] = useState(false);
  if (binaries.length === 0) return null;

  const ordered = sortBinariesByAnswer(binaries);
  const shown = expanded ? ordered : ordered.slice(0, COLLAPSED_ROWS);
  const hidden = ordered.length - shown.length;

  return (
    <section data-league-block="binaries">
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4 flex items-center gap-2">
        <span>🎯</span>
        Yes / no
        <span className="text-text-muted font-normal">({ordered.length})</span>
      </h2>
      <div className="rounded-2xl border border-surface-border bg-surface-card px-4 py-2">
        <div className="flex items-center gap-2 pb-2 mb-1 border-b border-surface-elevated">
          {/* The column is the chance the answer is YES. Saying so once is what
              lets each row be one line instead of two. */}
          <span className="ml-auto text-[11px] text-text-muted">chance of yes</span>
        </div>
        <div className="divide-y divide-surface-border/60">
          {shown.map(({ market, answer }) => (
            <BinaryRow key={market.id} market={market} answer={answer} />
          ))}
        </div>
        {hidden > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="w-full py-2.5 text-[12px] font-semibold text-accent-brand hover:underline"
          >
            Show {hidden} more question{hidden === 1 ? "" : "s"}
          </button>
        )}
      </div>
    </section>
  );
}
