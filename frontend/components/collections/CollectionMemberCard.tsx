"use client";

import Link from "next/link";
import FeedCard from "@/components/FeedCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import { outcomeRowVerdict, type GradedRow } from "@/components/futures/OutcomeRow";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type { FeedFuturesData, FeedFuturesOutcome } from "@/lib/types";
import type { CollectionMember } from "@/lib/collections";
import MidtermsMarketCard from "./MidtermsMarketCard";
import { SourceBadge } from "@/components/politics/atoms";
import { MIDTERMS_PARTY_COLOR, midtermsOutcomeParty } from "@/lib/midtermsParty";

// #10089: Polymarket's mixed game listing (totals, spreads and a team-win leg)
// shown under its own game would print that game's winner a second time with a
// different number. In that related-to-this-game context only, it becomes a
// link to the full listing with no percentages. The relation is the served one
// (the hub passed this game, the market's event id is that game, the market is
// a Polymarket `field`); nothing is inferred from names.
export function isRelatedMixedListing(member: CollectionMember, relatedGame?: CollectionMember): boolean {
  if (member.type !== "market" || relatedGame?.type !== "event" || member.eventId !== relatedGame.id) return false;
  const market = member.item.data as FeedFuturesData;
  return market.market_type === "field" && market.source === "polymarket";
}

export function CollectionMemberCard({ member, relatedGame, presentation }: { member: CollectionMember; relatedGame?: CollectionMember; presentation?: string }) {
  const market = member.type === "market" ? member.item.data as FeedFuturesData : null;
  if (market && isRelatedMixedListing(member, relatedGame)) {
    const count = market.outcome_count > 0 ? market.outcome_count : 0;
    return <Link href={member.href} data-related-listing-link className="flex items-center justify-between gap-3 rounded-card border border-surface-border bg-surface-card p-4 hover:bg-surface-elevated transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand">
      <span className="min-w-0">
        <span className="block font-semibold text-text-primary">{market.name}</span>
        <span className="block text-sm text-text-secondary">{count ? `${count} ${count === 1 ? "market" : "markets"} on this game` : "More markets on this game"}</span>
      </span>
      <span aria-hidden className="shrink-0 text-text-secondary">›</span>
    </Link>;
  }
  const outcomes = market?.top_outcomes as (FeedFuturesOutcome & GradedRow)[] | undefined;
  const resolved = !!market && ["resolved", "closed", "settled", "finalized", "final"].includes(market.status);
  // #11872: an unpriced open outcome is absence, not nineteen separate errors.
  // Keep authoritative results even when they have no price; settled rows keep
  // their existing result vocabulary and order.
  const unpriced = resolved ? [] : (outcomes ?? []).filter(outcome => outcome.probability == null && outcomeRowVerdict(outcome, false) === null);
  const shownOutcomes = unpriced.length ? outcomes?.filter(outcome => outcome.probability != null || outcomeRowVerdict(outcome, false) !== null)
    .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1)) : outcomes;
  const hasVerdict = outcomes?.some((outcome) => outcomeRowVerdict(outcome, resolved) !== null) ?? false;
  const missingPrices = !!market && (!outcomes?.length || (presentation && outcomes.length < market.outcome_count) || outcomes.some((outcome) => outcome.probability == null));
  const winner = (market as (FeedFuturesData & { settled_winner?: string }) | null)?.settled_winner;
  if (presentation && market && !resolved && !hasVerdict && !missingPrices) {
    return <MidtermsMarketCard market={market} presentation={presentation} />;
  }
  // The existing sports card owns game lifecycle and probabilities. A missing
  // price or served result uses the existing verdict/format rule, never nil -> 0%.
  const card = market && (resolved || hasVerdict || missingPrices) ? (
    <Link href={member.href} className="block rounded-card border border-surface-border bg-surface-card p-4 hover:bg-surface-elevated transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand">
      {presentation && market.source && <SourceBadge source={market.source} />}
      <h3 className="font-semibold text-text-primary mb-3">{market.name}</h3>
      {winner ? <p className="font-semibold text-text-primary">Settled - {winner}</p> : <div className="space-y-2 text-sm">
        {shownOutcomes?.map((outcome, index) => {
          const verdict = outcomeRowVerdict(outcome, resolved);
          const party = presentation && !resolved && !verdict ? midtermsOutcomeParty(market.id, outcome) : null;
          const label = verdict === "won" ? "Won" : verdict === "lost" ? "Lost" : resolved ? "Result unavailable" : outcome.probability == null ? "Probability unavailable" : formatProbabilityPercent(outcome.probability);
          return <div key={`${outcome.id ?? index}:${outcome.name}`} className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 text-text-secondary">{outcome.name}</span>
            <span className={`shrink-0 font-semibold ${verdict === "won" ? "text-accent-brand" : "text-text-primary"}`} style={party ? { color: MIDTERMS_PARTY_COLOR[party] } : undefined}>{label}</span>
          </div>;
        })}
        {unpriced.length > 0 && <p data-unpriced-outcomes={unpriced.length} className="text-text-secondary">
          {shownOutcomes?.length ? `${unpriced.length} more without a price yet` : `${unpriced.length} ${unpriced.length === 1 ? "outcome" : "outcomes"} without a price yet`}
        </p>}
        {!outcomes?.length && <p className="text-text-secondary">{resolved ? "Result unavailable" : "Probabilities aren't available right now."}</p>}
      </div>}
    </Link>
  ) : <FeedCard item={member.item} />;
  // #11040: the card a collection draws has no action bar, so its
  // existing age mark never shows. Say when an open market's number is old, with
  // the same mark and the same futures cadence (draws nothing when fresh).
  const hasDisplayedProbability =
    !!market &&
    !resolved &&
    !!outcomes?.some(
      (outcome) =>
        outcomeRowVerdict(outcome, resolved) === null &&
        typeof outcome.probability === "number" &&
        Number.isFinite(outcome.probability),
    );
  const age = hasDisplayedProbability
    ? <div data-collection-price-age className="flex justify-end px-1 pt-1"><PriceAgeMark observedAt={(market as FeedFuturesData & { prices_updated_at?: string | null }).prices_updated_at} scope="card" cadence={market.status === "live" ? "live" : "futures"} /></div>
    : null;
  return <ErrorBoundary resetKey={member.item.data} fallback={<p role="status" className="rounded-card border border-surface-border bg-surface-card p-4 text-text-secondary">{presentation ? "This market isn’t available right now." : "This game or market isn’t available right now."}</p>}>{card}{age}</ErrorBoundary>;
}
