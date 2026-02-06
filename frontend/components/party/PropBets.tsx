"use client";

import useSWR from "swr";
import { fetchEventProps } from "@/lib/api";
import type { PropBet, PropCategory } from "@/lib/types";

interface PropBetsProps {
  eventId: number;
}

const CATEGORY_ICONS: Record<string, string> = {
  Passing: "\uD83C\uDFC8",
  Rushing: "\uD83C\uDFC3",
  Receiving: "\uD83D\uDC50",
  Scoring: "\uD83C\uDFAF",
  Kicking: "\uD83E\uDDB6",
};

function PropRow({ prop }: { prop: PropBet }) {
  // For over/under props
  if (prop.over_probability != null) {
    const overPct = Math.round(prop.over_probability * 100);
    const isOverFavored = overPct >= 50;

    return (
      <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
        <div className="flex-1 min-w-0">
          <span className="text-white font-medium text-sm truncate block">
            {prop.player}
          </span>
          <span className="text-white/50 text-xs">
            {prop.type} {prop.line != null ? `O/U ${prop.line}` : ""}
          </span>
        </div>
        <div className="flex items-center gap-3 ml-3">
          <div className={`text-right ${isOverFavored ? "text-emerald-400" : "text-white/60"}`}>
            <div className="text-lg font-bold font-mono">{overPct}%</div>
            <div className="text-[10px] uppercase tracking-wide opacity-60">Over</div>
          </div>
          <div className="w-px h-8 bg-white/20" />
          <div className={`text-right ${!isOverFavored ? "text-emerald-400" : "text-white/60"}`}>
            <div className="text-lg font-bold font-mono">{100 - overPct}%</div>
            <div className="text-[10px] uppercase tracking-wide opacity-60">Under</div>
          </div>
        </div>
      </div>
    );
  }

  // For yes/no props (anytime TD, first TD)
  if (prop.probability != null) {
    const pct = Math.round(prop.probability * 100);
    return (
      <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
        <div className="flex-1 min-w-0">
          <span className="text-white font-medium text-sm truncate block">
            {prop.player}
          </span>
          <span className="text-white/50 text-xs">{prop.type}</span>
        </div>
        <div className="text-emerald-400 text-lg font-bold font-mono ml-3">
          {pct}%
        </div>
      </div>
    );
  }

  return null;
}

function CategorySection({ category }: { category: PropCategory }) {
  const icon = CATEGORY_ICONS[category.category] || "\u26BD";
  // Show top 6 props per category for TV readability
  const visibleProps = category.props.slice(0, 6);

  return (
    <div>
      <h4 className="text-white/70 text-xs font-semibold uppercase tracking-widest mb-2 flex items-center gap-2">
        <span>{icon}</span>
        {category.category}
        <span className="text-white/30">({category.props.length})</span>
      </h4>
      <div className="space-y-1">
        {visibleProps.map((prop, i) => (
          <PropRow key={`${prop.player}-${prop.type}-${prop.line}-${i}`} prop={prop} />
        ))}
        {category.props.length > 6 && (
          <div className="text-white/30 text-xs text-center py-1">
            +{category.props.length - 6} more
          </div>
        )}
      </div>
    </div>
  );
}

export default function PropBets({ eventId }: PropBetsProps) {
  const { data, error, isLoading } = useSWR(
    ["props", eventId],
    () => fetchEventProps(eventId),
    { refreshInterval: 120000 } // Refresh every 2 minutes
  );

  if (isLoading) {
    return (
      <div className="text-white/40 text-sm text-center py-8">
        Loading props...
      </div>
    );
  }

  if (error || !data || data.total_props === 0) {
    return (
      <div className="text-white/30 text-sm text-center py-8">
        {error ? "Props unavailable" : "No props available for this event"}
      </div>
    );
  }

  return (
    <div className="space-y-4 overflow-y-auto max-h-[500px] pr-1 scrollbar-thin">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold text-sm uppercase tracking-wider">
          Player Props
        </h3>
        <span className="text-white/30 text-xs">{data.total_props} props</span>
      </div>
      {data.categories.map((cat) => (
        <CategorySection key={cat.category} category={cat} />
      ))}
    </div>
  );
}
