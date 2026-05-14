"use client";

import type { LeagueMarket } from "@/lib/api";
import SeriesCard from "./SeriesCard";
import AwardCard from "./AwardCard";
import PropGroupCard from "./PropGroupCard";

interface LeagueMarketSectionProps {
  sectionKey: string;
  label: string;
  markets: LeagueMarket[];
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

export default function LeagueMarketSection({ sectionKey, label, markets }: LeagueMarketSectionProps) {
  if (markets.length === 0) return null;

  const cols = sectionKey === "series"
    ? "grid-cols-1 sm:grid-cols-2"
    : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";

  return (
    <section>
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4 flex items-center gap-2">
        <span>{SECTION_EMOJI[sectionKey] || "📋"}</span>
        {label}
        <span className="text-text-muted font-normal">({markets.length})</span>
      </h2>
      <div className={`grid ${cols} gap-3`}>
        {markets.map((m) => (
          <MarketCardForSection key={m.id} market={m} sectionKey={sectionKey} />
        ))}
      </div>
    </section>
  );
}
