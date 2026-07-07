"use client";

/**
 * #993 L2-42: renders a backend-composed topical family on /search.
 * headline row prominent; members as inline answers (question · leader +
 * probability · 24h movement arrow ≥2pts · resolution date if <30d). One tap →
 * /futures/{id}. D1: probabilities only — NO odds, NO source/venue names.
 * Design-system tokens only (light mode). Leader-pick + #23 normalization are
 * applied server-side; we display top_outcomes as given.
 */

import Link from "next/link";
import type { FuturesFamily, FuturesMarket } from "@/lib/types";
import {
  leaderOutcome,
  movementArrow,
  resolutionLabel,
  cleanName,
} from "@/components/searchFamilyDisplay";

function AnswerRow({
  market,
  prominent,
  onClick,
}: {
  market: FuturesMarket;
  prominent?: boolean;
  onClick?: () => void;
}) {
  const ld = leaderOutcome(market);
  const arrow = ld ? movementArrow(ld.movement) : null;
  const reso = resolutionLabel(market.resolution_date);
  return (
    <Link
      href={`/futures/${market.id}`}
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 hover:bg-surface-elevated transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div
          className={`truncate ${prominent ? "text-sm font-medium text-text-primary" : "text-sm text-text-secondary"}`}
        >
          {cleanName(market.name)}
        </div>
      </div>
      {ld && ld.probability != null ? (
        <div className="flex items-center gap-1 flex-shrink-0 text-sm">
          <span className="text-text-primary font-medium">
            {ld.name} {Math.round(ld.probability * 100)}%
          </span>
          {arrow && (
            <span className={arrow.up ? "text-accent-live" : "text-accent-danger"}>
              {arrow.up ? "↑" : "↓"}
              {arrow.points}
            </span>
          )}
        </div>
      ) : (
        <span className="text-xs text-text-muted flex-shrink-0">
          {market.outcome_count} outcome{market.outcome_count !== 1 ? "s" : ""}
        </span>
      )}
      {reso && <span className="text-xs text-text-muted flex-shrink-0">{reso}</span>}
    </Link>
  );
}

export default function SearchFamilyCard({
  family,
  onRowClick,
}: {
  family: FuturesFamily;
  onRowClick?: (type: "family_headline" | "family_member", marketId: number) => void;
}) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
      <div className="px-3 pt-2 text-xs font-medium text-accent-brand uppercase tracking-wide">
        {family.label}
      </div>
      <AnswerRow
        market={family.headline}
        prominent
        onClick={() => onRowClick?.("family_headline", family.headline.id)}
      />
      {family.members.length > 0 && (
        <div className="border-t border-surface-border divide-y divide-surface-border">
          {family.members.map((m) => (
            <AnswerRow
              key={m.id}
              market={m}
              onClick={() => onRowClick?.("family_member", m.id)}
            />
          ))}
        </div>
      )}
      {family.more_count > 0 && (
        <div className="px-3 py-1.5 text-xs text-text-muted border-t border-surface-border">
          +{family.more_count} more market{family.more_count !== 1 ? "s" : ""} below
        </div>
      )}
    </div>
  );
}
