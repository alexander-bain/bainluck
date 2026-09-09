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
  familyRowTitles,
} from "@/components/searchFamilyDisplay";

function AnswerRow({
  market,
  title,
  prominent,
  onClick,
}: {
  market: FuturesMarket;
  title: { head: string; tail: string };
  prominent?: boolean;
  onClick?: () => void;
}) {
  const ld = leaderOutcome(market);
  const arrow = ld ? movementArrow(ld.movement) : null;
  const reso = resolutionLabel(market.resolution_date);
  const nameClass = prominent
    ? "text-sm font-medium text-text-primary"
    : "text-sm text-text-secondary";
  return (
    <Link
      href={`/futures/${market.id}`}
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 hover:bg-surface-elevated transition-colors"
    >
      {/* #4136: head truncates, tail does not. When `tail` is empty — the
          ordinary case, a row that shares no long prefix with a sibling — this
          is exactly the single truncating div it has always been.

          #4518: the tail used to be `flex-shrink-0` inside a `min-w-0` container
          whose overflow is VISIBLE, so on the one row where the head had already
          collapsed to nothing and the tail STILL did not fit, the tail had no
          room to shrink into and no clip to stop it — it painted straight
          through the outcome text (−26px at 390, −47px at 360, clean by 430).

          What is wanted is an ORDER, not a ratio: the head gives up everything
          before the tail gives up anything. CSS has no "shrink this one first",
          but shrinkage is distributed proportional to `basis × shrink-factor`
          and an item that reaches its min size freezes and hands the remaining
          deficit to the others — so a head factor several orders of magnitude
          above the tail's IS that order, expressed the one way the box model
          offers. The tail keeps `truncate` so that when it finally must give,
          it ellipsises inside its own box instead of over its neighbour.

          Not `overflow-hidden` on the container: that stops the overlap by
          hard-cutting the tail, which silently eats the bytes #4136 exists to
          preserve — a visible bug traded for an invisible one. */}
      <div className="flex-1 min-w-0 flex items-center">
        <div className={`truncate shrink-[9999] ${nameClass}`}>{title.head}</div>
        {title.tail && (
          <div className={`truncate shrink ${nameClass}`}>{title.tail}</div>
        )}
      </div>
      {ld && ld.probability != null ? (
        /* #4136: the outcome NAME may be arbitrarily long — production served an
           outcome called "Istanbul 3: Timofey Skatov vs Yanki Erel Set 2 O/U 9.5"
           — and this column used to be `flex-shrink-0`, so one row like that blew
           the name and the date clean off the card. Capped and truncatable, with
           the percentage itself pinned: the reader may lose the outcome's name,
           never the answer. */
        <div className="flex items-center gap-1 min-w-0 max-w-[55%] text-sm">
          <span className="truncate text-text-primary font-medium">{ld.name}</span>
          <span className="flex-shrink-0 text-text-primary font-medium">
            {Math.round(ld.probability * 100)}%
          </span>
          {arrow && (
            <span
              className={`flex-shrink-0 ${arrow.up ? "text-accent-live" : "text-accent-danger"}`}
            >
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
  // #4136: computed over the WHOLE card, headline included. "Do these two rows
  // look the same?" is a property of the set, so it cannot be decided inside a
  // row — the same market name is fine alone and unreadable beside its sibling.
  const rows = [family.headline, ...family.members];
  const titles = familyRowTitles(rows.map((m) => m.name));
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
      <div className="px-3 pt-2 text-xs font-medium text-accent-brand uppercase tracking-wide">
        {family.label}
      </div>
      <AnswerRow
        market={family.headline}
        title={titles[0]}
        prominent
        onClick={() => onRowClick?.("family_headline", family.headline.id)}
      />
      {family.members.length > 0 && (
        <div className="border-t border-surface-border divide-y divide-surface-border">
          {family.members.map((m, i) => (
            <AnswerRow
              key={m.id}
              market={m}
              title={titles[i + 1]}
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
