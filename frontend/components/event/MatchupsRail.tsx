"use client";

// #999 L2-64 Event Concept Page — matchups & props rail. Live matchups render as
// cards (top outcomes with probability bars); decided ones are grouped under a
// collapsed "Completed (N)" so a settled 99% never reads as live (L2-63 Item 2).
// Probability-only, no source names.
//
// L2-130: soccer bracket games are TEAM duels (home vs away crest + score + win
// probability), not fight-card outcome lists — they render via MatchupDuel. The
// combat/golf outcome-card path is unchanged for non-matchup children.

import Link from "next/link";
import { formatProbability } from "@/lib/api";
import {
  childLeader,
  awardsResult,
  childReactKey,
  isMatchupChild,
  splitChildren,
} from "@/lib/eventConceptDisplay";
import { groupMatchupsByFamily } from "@/lib/matchupFamilies";
import { servedBoutPercents } from "@/lib/servedBoutPercents";
import type { EventConceptChild } from "@/lib/types";
import FighterAvatar from "./FighterAvatar";
import MatchupDuel from "./MatchupDuel";

function topOutcomes(
  child: EventConceptChild,
): { name: string; probability: number | null; rendered_percent?: number | null }[] {
  const outs = child.outcomes || [];
  if (outs.length > 0) {
    return [...outs]
      .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))
      .slice(0, 2);
  }
  const lead = childLeader(child);
  return lead ? [lead] : [];
}

function MatchupCard({ child, dim }: { child: EventConceptChild; dim?: boolean }) {
  const outs = topOutcomes(child);
  // #6816: a bout's two numbers are ONE decision, made by the server for a pair
  // it has proven is one question. Both served or neither — `null` prints exactly
  // what this card printed before. Only when the card shows the WHOLE market:
  // two rows sliced off a longer field are not a pair.
  const served =
    (child.outcomes || []).length === 2 ? servedBoutPercents(outs) : outs.map(() => null);
  const lead = childLeader(child);
  return (
    <div
      className={`flex-shrink-0 w-60 md:w-auto bg-surface-card rounded-card shadow-card border border-surface-border p-3.5 transition-shadow hover:shadow-card-hover ${
        dim ? "opacity-70" : ""
      }`}
    >
      <div className="text-xs text-text-muted truncate mb-2.5">
        {child.market_name || child.name || "Market"}
      </div>
      {dim ? (
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {lead?.name && <FighterAvatar name={lead.name} size={28} dim />}
            <span className="text-sm text-text-secondary truncate">{lead?.name}</span>
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-text-muted/15 text-text-secondary shrink-0">
            Final
          </span>
        </div>
      ) : (
        <div className="space-y-2.5">
          {outs.map((o, i) => {
            const pct = o.probability != null ? Math.round(o.probability * 100) : null;
            return (
              <div key={`${o.name}-${i}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FighterAvatar name={o.name} size={32} />
                    <span className="text-sm text-text-primary truncate">{o.name}</span>
                  </div>
                  <span className="font-mono text-xs font-semibold text-text-primary tabular-nums shrink-0">
                    {formatProbability(o.probability, { rendered: served[i] })}
                  </span>
                </div>
                {pct != null && (
                  <div className="mt-1.5 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent-brand"
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Render one child in the rail: a soccer team duel (crest + score + win prob) or
 *  the combat/golf outcome card. `dim` is passed to the combat card for the
 *  completed group; MatchupDuel handles its own settled treatment internally. */
function RailChild({ child, index, dim, sport }: { child: EventConceptChild; index: number; dim?: boolean; sport?: string | null }) {
  if (isMatchupChild(child)) {
    return <MatchupDuel child={child} sport={sport} />;
  }
  return <MatchupCard child={child} dim={dim} />;
}

const GRID_CLASS =
  "flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 md:grid md:grid-cols-2 lg:grid-cols-3 md:gap-4 md:overflow-visible md:mx-0 md:px-0 md:pb-0";

/** #1602: one block of the rail — a flat grid, or, only when the field is large
 *  enough to be a wall, collapsed family groups. `groupMatchupsByFamily` returns
 *  null for every field at or under MATCHUP_GROUPING_THRESHOLD and for any field
 *  that is all one family, so the flat path below is byte-for-byte today's
 *  behaviour for a UFC card, a cycling GC or a soccer bracket. */
function RailBody({
  items,
  dim,
  className,
  sport,
}: {
  items: EventConceptChild[];
  dim?: boolean;
  className?: string;
  /** #6238 — the container's domain, forwarded to the duel card. */
  sport?: string | null;
}) {
  const groups = groupMatchupsByFamily(items);
  const extra = className ? ` ${className}` : "";

  if (!groups) {
    return (
      <div className={`${GRID_CLASS}${extra}`}>
        {items.map((child, i) => (
          <RailChild key={childReactKey(child, i)} child={child} index={i} dim={dim} sport={sport} />
        ))}
      </div>
    );
  }

  return (
    <div className={`space-y-1${extra}`}>
      {groups.map((g) => (
        // Deliberately an UNCONTROLLED <details>: nothing passes `open`, so React
        // never rewrites it and a group the user opened survives the page's 30s
        // live refresh — SWR swaps data in place, the rail is not remounted, and
        // `g.key` is a stable family id rather than an index. Same reason the
        // "Completed" disclosure below has always held its state.
        // Collapsed by default, all of them: the census showed no single lead
        // family (match winners 399 vs completed 338), so auto-opening one would
        // be inventing a relevance ranking.
        <details
          key={g.key}
          className="border-b border-surface-border last:border-b-0 pb-1.5"
        >
          <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer py-2">
            {g.label} ({g.items.length})
          </summary>
          <div className={`${GRID_CLASS} mt-2 mb-1`}>
            {g.items.map((child, i) => (
              <RailChild key={childReactKey(child, i)} child={child} index={i} dim={dim} sport={sport} />
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

export function AwardsCategoryCard({ child }: { child: EventConceptChild }) {
  const result = awardsResult(child);
  const display = (name: string) => name.toLowerCase() === "other" ? "Another nominee" : name;
  const title = child.market_name || child.name || "Category";
  return <article id={`awards-category-${child.market_id}`} className="scroll-mt-20 min-w-0 rounded-card border border-surface-border bg-surface-card p-4 space-y-2">
    <h3 className="text-sm font-semibold text-text-primary">{typeof child.market_id === "number" ? <Link href={`/futures/${child.market_id}`} className="hover:underline">{title}</Link> : title}</h3>
    {result.state === "announced" ? <>
      <p className="text-xs font-semibold text-text-secondary">{result.prop ? "Result" : result.names.length > 1 ? "Joint winners" : "Winner"}</p>
      <ul className="space-y-1 text-base font-semibold text-text-primary">{result.names.map((name) => <li key={name}>{display(name)}</li>)}</ul>
    </> : result.state === "closed" ? <p className="text-sm text-text-secondary">Trading closed · Result not yet confirmed</p> : <>
      <p className="text-xs font-semibold text-text-secondary">Not announced</p>
      <ul className="space-y-1 text-sm text-text-secondary">{topOutcomes(child).map((outcome) => <li key={outcome.name} className="flex justify-between gap-3"><span>{display(outcome.name)}</span><span className="shrink-0 font-mono">{formatProbability(outcome.probability)}</span></li>)}</ul>
    </>}
  </article>;
}

interface MatchupsRailProps {
  items: EventConceptChild[];
  /** L2-130: a child already shown in the container hero — excluded from the rail
   *  so the headliner isn't rendered twice. Matched by reference identity. */
  exclude?: EventConceptChild | null;
  /** Optional section heading override (soccer reads "Matches", not "Matchups"). */
  title?: string;
  /** #6238 — the container's domain, so a soccer duel can withhold the away
   *  number instead of printing the home side's complement. See `MatchupDuel`. */
  sport?: string | null;
}

export default function MatchupsRail({ items, exclude, title, sport }: MatchupsRailProps) {
  const shown = (items || []).filter((c) => c !== exclude);
  if (shown.length === 0) return null;
  if (sport === "awards") return <section id={title === "Nominations and more" ? "props" : "matchups"} className="scroll-mt-20 rounded-card bg-surface-card p-4 sm:p-6 space-y-4">
    <h2 className="text-title-3 font-semibold text-text-primary">{title || "Categories"}</h2>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{shown.map((child, index) => <AwardsCategoryCard key={childReactKey(child, index)} child={child} />)}</div>
  </section>;
  const { live, settled } = splitChildren(shown, sport);

  return (
    <section id="matchups" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">{title || "Matchups & props"}</h2>
      {/* Mobile: a horizontal-scroll rail. Desktop (L2-113): a responsive 2–3-col
          grid so wide viewports don't hide bouts behind a scroll gutter. #1602:
          above MATCHUP_GROUPING_THRESHOLD that grid becomes collapsed family
          groups instead of one 52,000px wall. */}
      {live.length > 0 && <RailBody items={live} sport={sport} />}
      {settled.length > 0 && (
        <details className="mt-4">
          <summary className="text-xs font-semibold uppercase tracking-wide text-text-muted cursor-pointer">
            Completed ({settled.length})
          </summary>
          {/* The settled tail costs no height while collapsed, but on this page it
              is 744 cards — opening it would be the identical wall one click in,
              so it groups by the same rule. */}
          <RailBody items={settled} dim className="mt-2" sport={sport} />
        </details>
      )}
      {live.length === 0 && settled.length === 0 && (
        <p className="text-sm text-text-secondary">No matchups yet.</p>
      )}
    </section>
  );
}
