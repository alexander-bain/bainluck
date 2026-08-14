"use client";

import Link from "next/link";
import type { LeagueMarket } from "@/lib/api";
import { formatProbability } from "@/lib/api";
import SeriesCard from "./SeriesCard";
import AwardCard from "./AwardCard";
import PropGroupCard from "./PropGroupCard";
import QuantityGroup from "./QuantityGroup";
import { probabilityHeat } from "@/lib/probabilityColors";
import { binaryAnswer, cleanMarketName, dateLadder } from "@/lib/leagueCards";
import { earnsSectionHeader, earnsCountChip, type EntityTier } from "@/lib/entityPageChrome";

interface LeagueMarketSectionProps {
  sectionKey: string;
  label: string;
  markets: LeagueMarket[];
  /**
   * How many sections the page is rendering in total, and the tier the BACKEND
   * declared. UX-P062 (#1743), register E1: a header over one card labels a pair
   * rather than organizing a group, and a header needs something to be
   * distinguished FROM. Both are count questions, and the count chip is a stat
   * that spec §3 bans at T1 — so the component is told, never left to guess.
   *
   * Optional so the hub and any other caller keep working unchanged; omitted
   * means "render as before".
   */
  sectionCount?: number;
  tier?: EntityTier | null;
}

const SECTION_EMOJI: Record<string, string> = {
  series: "🏆",
  awards: "🏅",
  props: "📊",
  season_stats: "📈",
  more_markets: "🎲",
};

function MarketCardForSection({ market, sectionKey }: { market: LeagueMarket; sectionKey: string }) {
  switch (sectionKey) {
    case "series":
      return <SeriesCard market={market} />;
    case "awards":
      return <AwardCard market={market} />;
    default:
      return <PropGroupCard market={market} />;
  }
}

/**
 * ── UX-P074 (#1860), ruling 047, retrofit 3 ──
 *
 * ONE ROW PER BINARY. "A yes/no market is one question with one answer;
 * rendering it as two rows makes the reader do the arithmetic of noticing that
 * the rows are complements, and invites the eye to read them as two independent
 * markets."
 *
 * The row states the YES side by name, never `top_outcomes[0]` by rank — see
 * `binaryAnswer`, and the 15-of-21 measurement behind it.
 */
function BinaryRow({ market, answer }: { market: LeagueMarket; answer: { probability: number | null; movement: number | null } }) {
  const p = answer.probability;
  const heat = probabilityHeat(p);
  const width = p == null ? 0 : Math.max(2, Math.round(p * 100));

  return (
    <Link
      href={`/futures/${market.id}`}
      className="flex items-center gap-3 py-2 px-2 -mx-2 rounded-lg hover:bg-surface-elevated/60 transition-colors"
    >
      <span className="flex-1 min-w-0 text-sm text-text-primary truncate">
        {cleanMarketName(market.name)}
      </span>
      {/* A null probability draws NO track at all — never a 0%-wide bar inside a
          visible one, which is the same claim with extra steps (register E2). */}
      {p != null && (
        <span className="hidden sm:block w-24 h-[14px] rounded-md bg-surface-elevated overflow-hidden shrink-0">
          <span className={`block h-full rounded-md ${heat.bar}`} style={{ width: `${width}%` }} />
        </span>
      )}
      {answer.movement != null && Math.abs(answer.movement) >= 0.02 && (
        <span
          className={`text-[10px] font-medium shrink-0 ${answer.movement > 0 ? "text-accent-live" : "text-accent-danger"}`}
        >
          {answer.movement > 0 ? "+" : ""}
          {(answer.movement * 100).toFixed(1)}
        </span>
      )}
      <span className="w-11 shrink-0 text-right font-mono text-sm font-bold tabular-nums text-text-primary">
        {p == null ? "—" : formatProbability(p)}
      </span>
    </Link>
  );
}

export default function LeagueMarketSection({
  sectionKey,
  label,
  markets,
  sectionCount,
  tier,
}: LeagueMarketSectionProps) {
  if (markets.length === 0) return null;

  // ── Ruling 047: three shapes, three shared presentations ──
  // Partitioning happens here rather than inside a card because "what IS this
  // market" is a question about the market, and the answer decides which shared
  // component renders it. Order is preserved within each bucket, so the
  // backend's importance sort still governs.
  const ladders: { market: LeagueMarket; ladder: NonNullable<ReturnType<typeof dateLadder>> }[] = [];
  const binaries: { market: LeagueMarket; answer: NonNullable<ReturnType<typeof binaryAnswer>> }[] = [];
  const cards: LeagueMarket[] = [];
  for (const m of markets) {
    const answer = binaryAnswer(m);
    if (answer) {
      binaries.push({ market: m, answer });
      continue;
    }
    const ladder = dateLadder(m);
    if (ladder) {
      ladders.push({ market: m, ladder });
      continue;
    }
    cards.push(m);
  }

  const cols = sectionKey === "series"
    ? "grid-cols-1 sm:grid-cols-2"
    : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";

  // When the caller does not declare a page context, behave exactly as before —
  // a silent behaviour change on every other caller is not this queue's to make.
  const chromeAware = sectionCount != null;
  const showHeader = !chromeAware || earnsSectionHeader(markets.length, sectionCount);
  const showChip = !chromeAware || earnsCountChip(tier);

  return (
    <section data-section-key={sectionKey}>
      {showHeader && (
        <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4 flex items-center gap-2">
          <span>{SECTION_EMOJI[sectionKey] || "📋"}</span>
          {label}
          {showChip && (
            <span className="text-text-muted font-normal">({markets.length})</span>
          )}
        </h2>
      )}

      {cards.length > 0 && (
        <div className={`grid ${cols} gap-3`}>
          {cards.map((m) => (
            <MarketCardForSection key={m.id} market={m} sectionKey={sectionKey} />
          ))}
        </div>
      )}

      {/* Date ladders — the SHARED Quantity kernel, one continuous question in
          date order, whole ladder. `wideLabels` is the "by WHEN" variant L2-119
          built for exactly this shape. */}
      {ladders.length > 0 && (
        <div className={`grid ${cols} gap-3 ${cards.length > 0 ? "mt-3" : ""}`} data-league-block="ladders">
          {ladders.map(({ market, ladder }) => (
            <QuantityGroup
              key={market.id}
              title={cleanMarketName(market.name)}
              rungs={ladder.rungs}
              hint={ladder.hint ?? undefined}
              wideLabels
            />
          ))}
        </div>
      )}

      {binaries.length > 0 && (
        <div
          className={`rounded-2xl border border-surface-border bg-surface-card px-4 py-2 ${cards.length > 0 || ladders.length > 0 ? "mt-3" : ""}`}
          data-league-block="binaries"
        >
          <div className="flex items-center gap-2 pb-2 mb-1 border-b border-surface-elevated">
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Yes / no
            </span>
            {/* The column is the chance the answer is YES. Saying so once is what
                lets each row be one line instead of two. */}
            <span className="ml-auto text-[11px] text-text-muted">chance of yes</span>
          </div>
          <div className="divide-y divide-surface-border/60">
            {binaries.map(({ market, answer }) => (
              <BinaryRow key={market.id} market={market} answer={answer} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
