"use client";

import type { LeagueMarket } from "@/lib/api";
import SeriesCard from "./SeriesCard";
import AwardCard from "./AwardCard";
import PropGroupCard from "./PropGroupCard";
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

export default function LeagueMarketSection({
  sectionKey,
  label,
  markets,
  sectionCount,
  tier,
}: LeagueMarketSectionProps) {
  if (markets.length === 0) return null;

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
      <div className={`grid ${cols} gap-3`}>
        {markets.map((m) => (
          <MarketCardForSection key={m.id} market={m} sectionKey={sectionKey} />
        ))}
      </div>
    </section>
  );
}
